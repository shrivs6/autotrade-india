"""
Nightly incremental retrainer — runs at 11 PM every trading day.
Adds today's completed trades to the training set and retrains the model.
Only promotes the new model if its validation AUC > current production AUC.
Target: complete in < 10 minutes.
"""
from datetime import date, datetime
from backend.ml.dataset_builder import build_dataset
from backend.ml.model_trainer import train_model
from backend.ml.model_registry import save_model, promote_if_better
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Use last 12 months so the model trains on all available backfilled history.
# Memory impact is negligible — NIFTY+BANKNIFTY produce ~10k rows/year, well within Railway limits.
RETRAIN_MONTHS_BACK = 12


def run_incremental_retrain():
    """
    Called nightly by the scheduler.
    Rebuilds dataset (last 3 months), retrains, promotes if better.
    Skips walk-forward validation to save memory — uses simple 90/10 eval split instead.
    """
    logger.info("=== Nightly Retrain Starting ===")
    start = datetime.now()

    try:
        logger.info(f"Building dataset (last {RETRAIN_MONTHS_BACK} months)...")
        df = build_dataset(months_back=RETRAIN_MONTHS_BACK)

        if len(df) < 500:
            logger.warning(f"Dataset too small ({len(df)} rows) — skipping retrain")
            return

        # Train on dataset — returns (model, eval_auc)
        logger.info("Training model...")
        model, new_auc = train_model(df)

        # Version by date
        version = date.today().strftime("v%Y%m%d")
        save_model(model, version, auc=new_auc, metadata={"rows": len(df), "months_back": RETRAIN_MONTHS_BACK})

        # Promote only if AUC improves
        promoted = promote_if_better(version)

        elapsed = (datetime.now() - start).seconds
        logger.info(
            f"=== Retrain complete in {elapsed}s | "
            f"AUC={new_auc:.4f} | promoted={promoted} ==="
        )

    except Exception as e:
        logger.error(f"Nightly retrain failed: {e}")
        raise
