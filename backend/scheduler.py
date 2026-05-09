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
    """8:30 AM — fetch overnight data, compute morning bias."""
    logger.info("=== [8:30 AM] Fetching morning data ===")
    try:
        from backend.data.nse_client import fetch_vix, fetch_fii_data
        vix = fetch_vix()
        fii = fetch_fii_data()
        logger.info(f"VIX: {vix} | FII: {fii}")
        # TODO Phase 2: compute and store morning bias
    except Exception as e:
        logger.error(f"Morning data job failed: {e}")


def job_confirm_bias():
    """9:15 AM — confirm morning bias with Nifty opening direction."""
    logger.info("=== [9:15 AM] Confirming market bias ===")
    # TODO Phase 2: compare Nifty open vs previous close, finalize bias


def job_scan_and_trade():
    """9:30 AM–3:20 PM every 5 min — scan stocks and place trades."""
    from datetime import datetime
    now = datetime.now(IST).strftime("%H:%M")
    logger.info(f"=== [{now}] Scanning for trade signals ===")
    # TODO Phase 3: feature build → signal evaluate → order manager


def job_square_off():
    """3:20 PM — force close all open positions."""
    logger.info("=== [3:20 PM] Squaring off all open positions ===")
    # TODO Phase 3: close all open trades in position tracker


def job_post_market():
    """3:45 PM — post-market review and lesson extraction."""
    logger.info("=== [3:45 PM] Running post-market review ===")
    # TODO Phase 3: post_market_review + lesson_extractor


def job_nightly_retrain():
    """11:00 PM — nightly model retrain."""
    logger.info("=== [11:00 PM] Starting nightly model retrain ===")
    # TODO Phase 4: incremental_trainer


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)

    # Morning data fetch
    scheduler.add_job(job_morning_data, CronTrigger(hour=8, minute=30, timezone=IST), id="morning_data")

    # Bias confirmation
    scheduler.add_job(job_confirm_bias, CronTrigger(hour=9, minute=15, timezone=IST), id="confirm_bias")

    # Trading loop: every 5 min from 9:30 to 15:20, Mon-Fri
    scheduler.add_job(
        job_scan_and_trade,
        CronTrigger(hour="9-15", minute="*/5", day_of_week="mon-fri", timezone=IST),
        id="scan_and_trade"
    )

    # Square off
    scheduler.add_job(job_square_off, CronTrigger(hour=15, minute=20, timezone=IST), id="square_off")

    # Post-market review
    scheduler.add_job(job_post_market, CronTrigger(hour=15, minute=45, timezone=IST), id="post_market")

    # Nightly retrain
    scheduler.add_job(job_nightly_retrain, CronTrigger(hour=23, minute=0, timezone=IST), id="nightly_retrain")

    return scheduler
