"""
Nightly incremental retrainer — runs at 11 PM every trading day.
Adds today's completed trades to the training set and retrains the model.
Only promotes the new model if its validation AUC > current production AUC.
Target: complete in < 10 minutes.
"""
from datetime import date, datetime
from backend.ml.dataset_builder import build_dataset
from backend.ml.model_trainer import train_model, walk_forward_validate
from backend.ml.model_registry import save_model, promote_if_better, get_production_version
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def run_incremental_retrain():
    """
    Called nightly by the scheduler.
    Rebuilds dataset (includes today's new trade outcomes), retrains, promotes if better.
    """
    logger.info("=== Nightly Retrain Starting ===")
    start = datetime.now()

    try:
        # Build full dataset (includes all historical + today's new labeled data)
        logger.info("Building dataset...")
        df = build_dataset()

        if len(df) < 500:
            logger.warning(f"Dataset too small ({len(df)} rows) — skipping retrain")
            return

        # Quick walk-forward validation (2 folds to keep it fast)
        logger.info("Running walk-forward validation...")
        wf_results = walk_forward_validate(df, n_splits=2)
        new_auc = wf_results["avg_auc"]

        # Train on full dataset
        logger.info("Training on full dataset...")
        model = train_model(df)

        # Version by date
        version = date.today().strftime("v%Y%m%d")
        save_model(model, version, auc=new_auc, metadata={"rows": len(df), "folds": wf_results})

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
