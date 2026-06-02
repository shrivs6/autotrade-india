from fastapi import APIRouter
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone("Asia/Kolkata")


@router.get("/health")
def health_check():
    now = pytz.timezone("Asia/Kolkata")
    checks = {}
    all_ok = True

    # --- DB ---
    try:
        from backend.database.connection import SessionLocal
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        checks["db"] = {"ok": True}
    except Exception as e:
        checks["db"] = {"ok": False, "error": str(e)}
        all_ok = False

    # --- Upstox token ---
    try:
        import os
        stub_mode = os.getenv("STUB_MODE", "True").strip().lower() not in ("false", "0", "no")
        if stub_mode:
            checks["token"] = {"ok": True, "note": "STUB_MODE — no token needed"}
        else:
            from backend.data.upstox_client import get_upstox_client
            client = get_upstox_client()
            if client.access_token:
                checks["token"] = {"ok": True}
            else:
                checks["token"] = {
                    "ok": False,
                    "error": "No valid token — visit /auth/login to authenticate",
                }
                all_ok = False
    except Exception as e:
        checks["token"] = {"ok": False, "error": str(e)}
        all_ok = False

    # --- Instrument keys ---
    try:
        import os
        stub_mode = os.getenv("STUB_MODE", "True").strip().lower() not in ("false", "0", "no")
        from backend.utils.constants import NIFTY50_SYMBOLS
        from backend.data.upstox_client import get_upstox_client
        client = get_upstox_client()

        if stub_mode:
            checks["instrument_keys"] = {"ok": True, "note": "STUB_MODE — keys not needed"}
        else:
            missing = [s for s in NIFTY50_SYMBOLS if s not in client._instrument_map]
            if missing:
                checks["instrument_keys"] = {
                    "ok": False,
                    "error": f"Missing keys for: {missing} — instrument map failed to load",
                }
                all_ok = False
            else:
                keys = {s: client._instrument_map[s]["tradingsymbol"] for s in NIFTY50_SYMBOLS}
                checks["instrument_keys"] = {"ok": True, "contracts": keys}
    except Exception as e:
        checks["instrument_keys"] = {"ok": False, "error": str(e)}
        all_ok = False

    # --- VIX (last known value + age) ---
    try:
        from backend.database.connection import SessionLocal
        from backend.database.models import MarketContext
        from datetime import date
        db = SessionLocal()
        try:
            today_ctx = db.query(MarketContext).filter(
                MarketContext.date == date.today()
            ).first()
        finally:
            db.close()
        from datetime import datetime, time as dtime
        past_trading_start = datetime.now(IST).time() >= dtime(9, 30)
        if today_ctx and today_ctx.vix and today_ctx.vix > 0:
            checks["vix"] = {"ok": True, "value": today_ctx.vix, "bias": round(today_ctx.morning_bias or 0, 3)}
        elif not past_trading_start:
            checks["vix"] = {"ok": True, "note": "Pre-market — VIX will be fetched at 9:00 AM"}
        else:
            checks["vix"] = {
                "ok": False,
                "error": "VIX not fetched today — morning bias defaulting to 0, model features corrupted",
            }
            all_ok = False
    except Exception as e:
        checks["vix"] = {"ok": False, "error": str(e)}
        all_ok = False

    # --- Candle freshness (only meaningful during market hours) ---
    try:
        from backend.database.connection import SessionLocal
        from backend.database.models import OHLCV5Min
        from backend.utils.constants import NIFTY50_SYMBOLS
        from datetime import datetime, timezone, time as dtime
        now_ist = datetime.now(IST)
        market_open = dtime(9, 15)
        market_close = dtime(15, 30)
        during_market = market_open <= now_ist.time() <= market_close
        if not during_market:
            checks["candles"] = {"ok": True, "note": "Market closed — candle freshness not checked"}
        else:
            db = SessionLocal()
            try:
                stale = []
                for sym in NIFTY50_SYMBOLS:
                    last = db.query(OHLCV5Min).filter(
                        OHLCV5Min.symbol == sym
                    ).order_by(OHLCV5Min.timestamp.desc()).first()
                    if last:
                        age_min = (datetime.now(timezone.utc) - last.timestamp.replace(tzinfo=timezone.utc)).seconds // 60
                        if age_min > 15:
                            stale.append(f"{sym} ({age_min}m old)")
            finally:
                db.close()
            if stale:
                checks["candles"] = {
                    "ok": False,
                    "error": f"Stale candles: {stale} — features may be built on old data",
                }
                all_ok = False
            else:
                checks["candles"] = {"ok": True}
    except Exception as e:
        checks["candles"] = {"ok": False, "error": str(e)}
        all_ok = False

    # --- Open positions ---
    try:
        from backend.database.connection import SessionLocal
        from backend.database.models import Trade
        from backend.trading.position_tracker import get_position_tracker
        db = SessionLocal()
        try:
            db_open = db.query(Trade).filter(Trade.status == "open").count()
        finally:
            db.close()
        tracker_count = get_position_tracker().count()
        in_sync = db_open == tracker_count
        checks["positions"] = {
            "ok": in_sync,
            "db_open": db_open,
            "tracker": tracker_count,
        }
        if not in_sync:
            checks["positions"]["warning"] = "Tracker out of sync with DB — container may have restarted"
            all_ok = False
    except Exception as e:
        checks["positions"] = {"ok": False, "error": str(e)}
        all_ok = False

    return {
        "status": "ok" if all_ok else "degraded",
        "time_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
    }
