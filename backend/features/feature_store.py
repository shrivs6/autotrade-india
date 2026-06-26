"""
Saves computed feature vectors to the signal_features table.
Called during live trading for every signal evaluated,
and by the backfill script for historical data.
"""
from datetime import datetime
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal
from backend.database.models import SignalFeature
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def save_features(symbol: str, timestamp: datetime, features: dict, db: Session = None):
    """
    Saves a feature vector to the DB. Skips if already exists (safe to call repeatedly).
    Strips non-numeric keys (symbol, timestamp) before saving to JSON.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Remove non-feature keys before storing
        clean = {
            k: v for k, v in features.items()
            if k not in ("symbol", "timestamp")
        }

        stmt = pg_insert(SignalFeature).values(
            symbol=symbol,
            timestamp=timestamp,
            features=clean,
        ).on_conflict_do_nothing(
            index_elements=["symbol", "timestamp"]
        )
        db.execute(stmt)
        db.commit()

    except Exception as e:
        logger.error(f"Failed to save features for {symbol} at {timestamp}: {e}")
        db.rollback()

    finally:
        if close_db:
            db.close()


def bulk_save_features(records: list[dict], db: Session = None):
    """
    Saves a batch of feature records at once.
    Each record: { 'symbol': str, 'timestamp': datetime, 'features': dict }
    Used by the backfill script for performance.
    Skips rows that already exist (safe to call repeatedly during live trading).
    """
    if not records:
        return

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        values = [
            {
                "symbol": r["symbol"],
                "timestamp": r["timestamp"],
                "features": {
                    k: v for k, v in r["features"].items()
                    if k not in ("symbol", "timestamp")
                },
            }
            for r in records
        ]

        stmt = pg_insert(SignalFeature).values(values).on_conflict_do_nothing(
            index_elements=["symbol", "timestamp"]
        )
        db.execute(stmt)
        db.commit()
        logger.info(f"Bulk saved {len(values)} feature records")

    except Exception as e:
        logger.error(f"Bulk feature save failed: {e}")
        db.rollback()

    finally:
        if close_db:
            db.close()


def bulk_upsert_features(records: list[dict], db: Session = None):
    """
    Upserts feature records — inserts new rows and UPDATES existing ones.
    Used by the nightly retrain to inject VIX/bias context into historical rows
    that were inserted before the VIX injection code existed.

    Unlike bulk_save_features (ON CONFLICT DO NOTHING), this overwrites the
    features JSON on conflict. Safe because technical indicators are computed
    deterministically from the same OHLCV data.
    """
    if not records:
        return

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        values = [
            {
                "symbol": r["symbol"],
                "timestamp": r["timestamp"],
                "features": {
                    k: v for k, v in r["features"].items()
                    if k not in ("symbol", "timestamp")
                },
            }
            for r in records
        ]

        insert_stmt = pg_insert(SignalFeature).values(values)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["symbol", "timestamp"],
            set_={"features": insert_stmt.excluded.features},
        )
        db.execute(stmt)
        db.commit()
        logger.info(f"Bulk upserted {len(values)} feature records (VIX injected)")

    except Exception as e:
        logger.error(f"Bulk feature upsert failed: {e}")
        db.rollback()

    finally:
        if close_db:
            db.close()
