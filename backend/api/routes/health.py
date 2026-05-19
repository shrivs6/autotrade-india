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
