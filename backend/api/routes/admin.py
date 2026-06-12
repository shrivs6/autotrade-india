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


# ── VIX backfill + feature rebuild + retrain ─────────────────────────────────

_rebuild_status = {"running": False, "log": [], "done": False, "error": None}


def _run_rebuild_job():
    global _rebuild_status
    _rebuild_status = {"running": True, "log": [], "done": False, "error": None}

    def log(msg):
        logger.info(msg)
        _rebuild_status["log"].append(msg)

    try:
        # Step 1: VIX backfill from Yahoo Finance
        log("Step 1/3: Backfilling India VIX from Yahoo Finance...")
        from backend.scripts.backfill_vix import run_vix_backfill
        result = run_vix_backfill()
        log(f"VIX backfill done: {result}")

        # Step 2: Wipe signal_features and rebuild with VIX injected
        log("Step 2/3: Rebuilding signal_features with VIX context...")
        from backend.database.connection import SessionLocal
        from backend.database.models import SignalFeature
        db = SessionLocal()
        try:
            deleted = db.query(SignalFeature).delete()
            db.commit()
            log(f"Cleared {deleted} old signal_features rows")
        finally:
            db.close()

        from backend.ml.incremental_trainer import _update_signal_features
        _update_signal_features()
        log("signal_features rebuilt with VIX context")

        # Step 3: Retrain model on clean data
        log("Step 3/3: Retraining ML model...")
        from backend.ml.incremental_trainer import run_incremental_retrain
        run_incremental_retrain()
        log("Retrain complete — check logs for new AUC")

        _rebuild_status["done"] = True

    except Exception as e:
        logger.error(f"Rebuild job failed: {e}")
        _rebuild_status["error"] = str(e)
    finally:
        _rebuild_status["running"] = False


@router.post("/rebuild-with-vix")
def trigger_rebuild(secret: str = Query(...)):
    """
    Full pipeline:
    1. Backfill 2 years of India VIX from Yahoo Finance into market_context
    2. Wipe and rebuild signal_features with VIX injected per date
    3. Retrain the ML model on clean data

    Poll GET /admin/rebuild-status for progress. Expected runtime: ~5-8 min.
    """
    _check_secret(secret)
    if _rebuild_status["running"]:
        raise HTTPException(status_code=409, detail="Rebuild already running")
    thread = threading.Thread(target=_run_rebuild_job, daemon=True)
    thread.start()
    return {"status": "started", "message": "Poll /admin/rebuild-status for progress"}


@router.get("/rebuild-status")
def rebuild_status(secret: str = Query(...)):
    """Returns current rebuild job status and log."""
    _check_secret(secret)
    return _rebuild_status
