"""
ML-powered signal evaluator — Phase 5.
Replaces rule_engine.py. Same interface: takes features, returns (direction, signal_id).
Uses production XGBoost model to score signals instead of hard-coded rules.
"""
import numpy as np
from backend.ml.model_registry import load_production_model
from backend.ml.dataset_builder import FEATURE_COLS
from backend.database.connection import SessionLocal
from backend.database.models import TradeSignal
from backend.utils.type_utils import to_python
from backend.utils.logger import get_logger
from datetime import datetime
import pytz

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# Only trade when model confidence exceeds this
CONFIDENCE_THRESHOLD = 0.50

_model = None


def get_model():
    global _model
    if _model is None:
        _model = load_production_model()
    return _model


def reload_model():
    """Called after nightly retrain to pick up new production model."""
    global _model
    _model = load_production_model()
    logger.info("ML signal evaluator: production model reloaded")


def evaluate_ml(features: dict, db=None) -> tuple[str | None, int | None, float | None]:
    """
    Scores features with the ML model for both long and short directions.
    Takes the higher-confidence direction if it exceeds CONFIDENCE_THRESHOLD.
    Returns (direction, signal_id, confidence) or (None, None, None).
    """
    model = get_model()
    if model is None:
        logger.warning("No production model — falling back to no signal")
        return None, None, None

    feature_cols = [c for c in FEATURE_COLS if c != "direction"]

    best_direction = None
    best_confidence = 0.0

    for direction, dir_flag in [("long", 0), ("short", 1)]:
        row = [features.get(col, 0) or 0 for col in feature_cols]
        row_with_dir = row + [dir_flag]

        try:
            X = np.array([row_with_dir])
            confidence = float(model.predict_proba(X)[0][1])
        except Exception as e:
            logger.error(f"Model prediction failed: {e}")
            continue

        if confidence > best_confidence:
            best_confidence = confidence
            best_direction = direction

    if best_confidence < CONFIDENCE_THRESHOLD:
        best_direction = None

    # Log signal to DB
    symbol = features.get("symbol", "UNKNOWN")
    ts_str = features.get("timestamp")
    ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(IST)

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    signal_id = None
    try:
        record = TradeSignal(
            symbol=symbol,
            timestamp=ts,
            direction=best_direction or "none",
            confidence=best_confidence if best_direction else None,
            features=to_python(features),
            trade_taken=False,
            skip_reason=None if best_direction else f"confidence {best_confidence:.2f} < {CONFIDENCE_THRESHOLD}",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        signal_id = record.id

        if best_direction:
            logger.info(f"{symbol} — ML {best_direction.upper()} | confidence={best_confidence:.2f}")

    except Exception as e:
        logger.error(f"Failed to log ML signal for {symbol}: {e}")
        db.rollback()
    finally:
        if close_db:
            db.close()

    return best_direction, signal_id, best_confidence if best_direction else None
