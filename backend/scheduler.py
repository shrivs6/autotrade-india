"""
All scheduled trading jobs.
Times are in IST (Asia/Kolkata).
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def job_morning_data():
    """8:30 AM — fetch overnight data, compute and save morning bias."""
    from datetime import datetime
    from backend.utils.constants import is_market_holiday
    if is_market_holiday(datetime.now(IST).date()):
        logger.info("=== [8:30 AM] NSE holiday — skipping morning data ===")
        return
    logger.info("=== [8:30 AM] Fetching morning data ===")
    try:
        from backend.data.nse_client import fetch_vix, fetch_fii_data
        from backend.features.market_context_scorer import save_morning_context
        from backend.trading.risk_manager import get_risk_manager
        from backend.database.connection import SessionLocal
        from backend.database.models import OHLCVDaily
        from datetime import date, timedelta

        vix = fetch_vix()  # may be None if NSE is unreliable pre-market — retry at 9:15 AM
        fii = fetch_fii_data()
        fii_net = fii["fii_net_crores"] if fii else 0.0

        # Get previous day Nifty return from daily candles
        db = SessionLocal()
        try:
            rows = (
                db.query(OHLCVDaily)
                .filter(OHLCVDaily.symbol == "NIFTY 50")
                .order_by(OHLCVDaily.date.desc())
                .limit(2)
                .all()
            )
            prev_return = 0.0
            if len(rows) >= 2:
                prev_return = (rows[0].close - rows[1].close) / rows[1].close
        finally:
            db.close()

        save_morning_context(vix, fii_net, prev_return)

        # Reset daily risk limits
        get_risk_manager().reset_daily()

        logger.info(f"Morning data done: VIX={vix if vix is not None else 'N/A (fetch failed)'}, FII=₹{fii_net:.0f}cr")
    except Exception as e:
        logger.error(f"Morning data job failed: {e}")


def job_retry_vix():
    """9:15 AM — retry VIX fetch if 8:30 AM attempt failed (NSE unreliable pre-market)."""
    from datetime import datetime
    from backend.utils.constants import is_market_holiday
    if is_market_holiday(datetime.now(IST).date()):
        return
    try:
        from backend.features.market_context_scorer import get_today_context, save_morning_context
        from backend.data.nse_client import fetch_vix, fetch_fii_data
        ctx = get_today_context()
        vix_ok = ctx and ctx.get("vix") and ctx.get("vix") != 15.0
        if vix_ok:
            logger.info("[9:15 AM] VIX already fetched successfully — skipping retry")
            return
        logger.info("[9:15 AM] VIX missing — retrying NSE fetch...")
        vix = fetch_vix()

        if not vix:
            # NSE scraping unreliable from cloud IPs — fall back to Upstox LTP API
            logger.warning("[9:15 AM] NSE failed — trying Upstox as VIX source...")
            from backend.data.upstox_client import get_upstox_client
            vix = get_upstox_client().fetch_vix()
            if vix:
                logger.info(f"[9:15 AM] VIX fetched via Upstox fallback: {vix}")

        if vix:
            fii = fetch_fii_data()
            fii_net = fii["fii_net_crores"] if fii else (ctx.get("fii_net_crores", 0.0) if ctx else 0.0)
            prev_return = ctx.get("prev_day_return", 0.0) if ctx else 0.0
            save_morning_context(vix, fii_net, prev_return)
            logger.info(f"[9:15 AM] VIX confirmed: {vix}")
        else:
            logger.warning("[9:15 AM] VIX unavailable from both NSE and Upstox — new entries will be blocked today")
    except Exception as e:
        logger.error(f"VIX retry job failed: {e}")


def job_confirm_bias():
    """9:20 AM — log bias confirmation (Nifty open vs prev close)."""
    logger.info("=== [9:20 AM] Confirming market bias ===")
    try:
        from backend.features.market_context_scorer import get_today_context
        ctx = get_today_context()
        if ctx:
            bias = ctx.get("morning_bias", 0)
            vix = ctx.get("vix", 0)
            direction = "BULLISH" if bias > 0.1 else "BEARISH" if bias < -0.1 else "NEUTRAL"
            logger.info(f"Bias confirmed: {direction} (score={bias:.2f}, VIX={vix:.1f})")
    except Exception as e:
        logger.error(f"Bias confirmation failed: {e}")


def job_scan_and_trade():
    """9:30 AM–2:55 PM every 5 min — scan all stocks and place trades."""
    from datetime import datetime
    from backend.utils.constants import is_market_holiday
    now = datetime.now(IST)

    # Skip NSE trading holidays
    if is_market_holiday(now.date()):
        return

    # Only trade during market hours — no new entries at or after 3:00 PM (square-off time)
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return
    if now.hour >= 15:
        return

    try:
        from backend.features.feature_builder import build_features
        from backend.trading.signal_evaluator import evaluate_and_log
        from backend.trading.order_manager import open_trade, monitor_positions
        from backend.data.upstox_client import get_upstox_client
        from backend.utils.constants import NIFTY50_SYMBOLS

        logger.info(f"=== [{now.strftime('%H:%M')}] Scanning {len(NIFTY50_SYMBOLS)} instruments ===")

        # Fetch today's live candles so feature builder has fresh data
        from backend.data.historical_fetcher import refresh_todays_candles
        failed_count = refresh_todays_candles()

        # If all symbols failed (no token / API down), skip new entries entirely.
        # Still monitor existing open positions using last known prices.
        skip_new_entries = (failed_count >= len(NIFTY50_SYMBOLS))
        if skip_new_entries:
            logger.warning(f"[{now.strftime('%H:%M')}] Candle refresh failed for all symbols — skipping new entries to avoid stale-price trades")

        # VIX halt — retry live fetch every scan until 12:30 PM if VIX is still missing.
        # Model is weakest after 12:30 PM so no point entering trades without context that late.
        from backend.features.market_context_scorer import get_today_context, save_morning_context
        ctx = get_today_context()
        if ctx is None or ctx.get("vix") is None:
            if now.hour < 12 or (now.hour == 12 and now.minute <= 30):
                # Still within retry window — attempt live fetch (NSE → Upstox fallback)
                from backend.data.nse_client import fetch_vix, fetch_fii_data
                from backend.data.upstox_client import get_upstox_client
                vix = fetch_vix()
                source = "NSE"
                if not vix:
                    vix = get_upstox_client().fetch_vix()
                    source = "Upstox"
                if vix:
                    fii = fetch_fii_data()
                    fii_net = fii["fii_net_crores"] if fii else (ctx.get("fii_net_crores", 0.0) if ctx else 0.0)
                    prev_return = ctx.get("prev_day_return", 0.0) if ctx else 0.0
                    save_morning_context(vix, fii_net, prev_return)
                    ctx = get_today_context()
                    logger.info(f"[{now.strftime('%H:%M')}] VIX fetched via {source}: {vix} — trading unblocked")
                else:
                    if not skip_new_entries:
                        logger.warning(f"[{now.strftime('%H:%M')}] VIX unavailable — skipping entries, will retry next scan")
                    skip_new_entries = True
            else:
                if not skip_new_entries:
                    logger.warning(f"[{now.strftime('%H:%M')}] VIX still unavailable after 12:30 PM — blocking rest of day")
                skip_new_entries = True

        morning_bias = ctx.get("morning_bias") if ctx else None

        client = get_upstox_client()
        current_prices = {}
        signals_found = 0

        for symbol in NIFTY50_SYMBOLS:
            try:
                features = build_features(symbol)
                if features is None:
                    continue

                current_prices[symbol] = features.get("close_price", 0)

                # Phase 5: use ML evaluator instead of rule engine
                from backend.trading.ml_signal_evaluator import evaluate_ml
                direction, signal_id, confidence = evaluate_ml(features)

                if direction and not skip_new_entries:
                    # Bias direction filter — avoid trading against confirmed market direction.
                    # On NEUTRAL days (|bias| <= 0.15), require higher confidence since we lack
                    # directional conviction.
                    bias = morning_bias or 0.0
                    if bias > 0.15 and direction == "short":
                        logger.info(f"{symbol}: skipping SHORT — bullish bias ({bias:.2f})")
                        direction = None
                    elif bias < -0.15 and direction == "long":
                        logger.info(f"{symbol}: skipping LONG — bearish bias ({bias:.2f})")
                        direction = None
                    elif abs(bias) <= 0.15 and confidence < 0.65:
                        logger.info(f"{symbol}: skipping {direction.upper()} — NEUTRAL bias, confidence {confidence:.2f} < 0.65")
                        direction = None

                if direction and not skip_new_entries:
                    signals_found += 1
                    open_trade(features, direction, signal_id, confidence)

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

        # Check stop loss / target for open positions
        monitor_positions(current_prices)

        logger.info(f"Scan complete: {signals_found} signal(s) found")

    except Exception as e:
        logger.error(f"Scan and trade job failed: {e}")


def job_square_off():
    """3:00 PM — force close all open positions."""
    from datetime import datetime
    from backend.utils.constants import is_market_holiday
    if is_market_holiday(datetime.now(IST).date()):
        logger.info("=== [3:00 PM] NSE holiday — skipping square-off ===")
        return
    logger.info("=== [3:00 PM] Squaring off all open positions ===")
    try:
        from backend.trading.order_manager import square_off_all
        square_off_all()
    except Exception as e:
        logger.error(f"Square off failed: {e}")


def job_post_market():
    """3:45 PM — post-market review and lesson extraction."""
    logger.info("=== [3:45 PM] Running post-market review ===")
    try:
        from backend.review.post_market_review import run_review
        from backend.review.lesson_extractor import extract_lessons
        summary = run_review()
        extract_lessons(summary)
    except Exception as e:
        logger.error(f"Post-market review failed: {e}")


def job_nightly_retrain():
    """11:00 PM — nightly model retrain."""
    logger.info("=== [11:00 PM] Starting nightly model retrain ===")
    try:
        from backend.ml.incremental_trainer import run_incremental_retrain
        run_incremental_retrain()
    except Exception as e:
        logger.error(f"Nightly retrain failed: {e}")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)

    scheduler.add_job(job_morning_data, CronTrigger(hour=8, minute=30, timezone=IST), id="morning_data")
    scheduler.add_job(job_retry_vix, CronTrigger(hour=9, minute=15, timezone=IST), id="retry_vix")
    scheduler.add_job(job_confirm_bias, CronTrigger(hour=9, minute=20, timezone=IST), id="confirm_bias")
    scheduler.add_job(
        job_scan_and_trade,
        CronTrigger(hour="9-15", minute="*/5", day_of_week="mon-fri", timezone=IST),
        id="scan_and_trade"
    )
    scheduler.add_job(job_square_off, CronTrigger(hour=15, minute=0, timezone=IST), id="square_off")
    scheduler.add_job(job_post_market, CronTrigger(hour=15, minute=45, timezone=IST), id="post_market")
    scheduler.add_job(job_nightly_retrain, CronTrigger(hour=23, minute=0, timezone=IST), id="nightly_retrain")

    return scheduler
