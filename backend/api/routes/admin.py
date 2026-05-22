"""
Admin endpoints — one-off operational tasks.
Protected by ADMIN_SECRET env variable.
"""
import os
import threading
from fastapi import APIRouter, HTTPException, Query
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")


def _check_secret(secret: str):
    if not ADMIN_SECRET:
        raise HTTPException(status_code=500, detail="ADMIN_SECRET not configured on server")
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")


_backfill_status = {"running": False, "log": [], "done": False, "error": None}


def _run_backfill_job():
    global _backfill_status
    _backfill_status = {"running": True, "log": [], "done": False, "error": None}

    def append_log(msg):
        _backfill_status["log"].append(msg)

    try:
        from backend.scripts.backfill_index_history import (
            run_index_backfill,
            run_feature_backfill,
            run_retrain,
        )
        append_log("Step 1/3: Fetching 2 years of NSE_INDEX candles...")
        results = run_index_backfill(status_callback=append_log)
        append_log(f"Candles done: {results}")

        append_log("Step 2/3: Computing signal features on new candles...")
        run_feature_backfill()
        append_log("Features done.")

        append_log("Step 3/3: Retraining ML model on full dataset...")
        run_retrain()
        append_log("Retrain done. Backfill complete!")

        _backfill_status["done"] = True
    except Exception as e:
        logger.error(f"Backfill job failed: {e}")
        _backfill_status["error"] = str(e)
    finally:
        _backfill_status["running"] = False


@router.post("/backfill-history")
def trigger_backfill(secret: str = Query(...)):
    """
    Triggers a background job that:
    1. Fetches 2 years of NSE_INDEX (NIFTY + BANKNIFTY) 5-min candles
    2. Recomputes signal_features on the full history
    3. Retrains the ML model

    Expected runtime: ~5-10 minutes.
    Poll GET /admin/backfill-status to track progress.
    """
    _check_secret(secret)

    if _backfill_status["running"]:
        raise HTTPException(status_code=409, detail="Backfill already running")

    thread = threading.Thread(target=_run_backfill_job, daemon=True)
    thread.start()

    return {"status": "started", "message": "Backfill running in background. Poll /admin/backfill-status for progress."}


@router.get("/backfill-status")
def backfill_status(secret: str = Query(...)):
    """Returns current backfill job status and log."""
    _check_secret(secret)
    return _backfill_status
