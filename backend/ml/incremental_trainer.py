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


def _update_signal_features():
    """
    Converts all ohlcv_5min candles to signal_features rows.
    Must run before build_dataset() so today's new candles are included in training.
    ON CONFLICT DO NOTHING — safe to call nightly; only new rows are inserted.
    """
    import pandas as pd
    from datetime import time as dtime
    from backend.database.connection import SessionLocal
    from backend.database.models import OHLCV5Min
    from backend.features.technical_indicators import compute_all_indicators
    from backend.features.feature_store import bulk_save_features
    from backend.utils.constants import NIFTY50_SYMBOLS

    TRADING_START = dtime(9, 30)
    TRADING_END = dtime(14, 0)
    db = SessionLocal()
    total = 0
    try:
        for symbol in NIFTY50_SYMBOLS:
            rows = (
                db.query(OHLCV5Min)
                .filter(OHLCV5Min.symbol == symbol)
                .order_by(OHLCV5Min.timestamp.asc())
                .all()
            )
            if not rows:
                logger.warning(f"Feature update: no candles found for {symbol}")
                continue

            df = pd.DataFrame([{
                "timestamp": r.timestamp, "open": r.open, "high": r.high,
                "low": r.low, "close": r.close, "volume": r.volume,
            } for r in rows])

            enriched = compute_all_indicators(df)
            trading_rows = enriched[
                enriched["timestamp"].apply(lambda ts: TRADING_START <= ts.time() <= TRADING_END)
            ].dropna(subset=["rsi", "macd_histogram", "bb_pct", "volume_spike"])

            records = [
                {
                    "symbol": symbol,
                    "timestamp": row["timestamp"],
                    "features": {
                        col: (float(row[col]) if pd.notna(row[col]) else None)
                        for col in row.index if col not in ("timestamp",)
                    },
                }
                for _, row in trading_rows.iterrows()
            ]
            bulk_save_features(records, db=db)
            total += len(records)
            logger.info(f"Feature update: {symbol} — {len(records)} rows upserted")
    finally:
        db.close()

    logger.info(f"Feature update complete: {total} total rows processed")


def run_incremental_retrain():
    """
    Called nightly by the scheduler.
    Rebuilds dataset (last 12 months), retrains, promotes if better.
    Skips walk-forward validation to save memory — uses simple 90/10 eval split instead.
    """
    logger.info("=== Nightly Retrain Starting ===")
    start = datetime.now()

    try:
        # Convert today's new candles to signal_features before building the dataset
        logger.info("Updating signal_features from latest candles...")
        _update_signal_features()

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
