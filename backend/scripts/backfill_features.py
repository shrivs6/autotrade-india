"""
One-time backfill script — computes features for all historical 5-min candles
and stores them in signal_features table. Creates the initial ML training dataset.

Run after Phase 2 is complete:
    cd "Trading Simulater"
    source venv/bin/activate
    python -m backend.scripts.backfill_features

Expected runtime: 10-20 minutes (50 stocks x ~975k candles total).
Safe to re-run — skips timestamps already in signal_features.
"""
import time
import pandas as pd
from datetime import datetime, time as dtime

from backend.database.connection import SessionLocal
from backend.database.models import OHLCV5Min
from backend.features.technical_indicators import compute_all_indicators
from backend.features.feature_store import bulk_save_features
from backend.utils.constants import NIFTY50_SYMBOLS
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Only evaluate signals during trading hours
TRADING_START = dtime(9, 30)
TRADING_END = dtime(14, 0)

# How many candles to fetch per symbol at once (memory management)
BATCH_SIZE = 2000


def is_trading_hour(ts) -> bool:
    t = ts.time() if hasattr(ts, "time") else ts
    return TRADING_START <= t <= TRADING_END


def backfill_symbol(symbol: str, db):
    """
    Fetches all 5-min candles for a symbol, computes indicators,
    and saves features for candles that fall during trading hours.
    """
    rows = (
        db.query(OHLCV5Min)
        .filter(OHLCV5Min.symbol == symbol)
        .order_by(OHLCV5Min.timestamp.asc())
        .all()
    )

    if not rows:
        logger.warning(f"{symbol}: no candles found")
        return 0

    df = pd.DataFrame([{
        "timestamp": r.timestamp,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume,
    } for r in rows])

    # Compute all indicators on the full series (needs full history for accuracy)
    enriched = compute_all_indicators(df)

    # Only keep trading-hours rows with valid indicators
    trading_rows = enriched[
        enriched["timestamp"].apply(is_trading_hour)
    ].dropna(subset=["rsi", "macd_histogram", "bb_pct", "volume_spike"])

    if trading_rows.empty:
        logger.warning(f"{symbol}: no valid trading-hour rows after indicator computation")
        return 0

    # Build records for bulk insert
    records = []
    for _, row in trading_rows.iterrows():
        features = {
            col: (float(row[col]) if pd.notna(row[col]) else None)
            for col in row.index
            if col not in ("timestamp",)
        }
        records.append({
            "symbol": symbol,
            "timestamp": row["timestamp"],
            "features": features,
        })

    bulk_save_features(records, db=db)
    return len(records)


def run_backfill():
    db = SessionLocal()
    total = 0

    try:
        logger.info("=" * 60)
        logger.info("Starting feature backfill for all Nifty 50 stocks")
        logger.info("=" * 60)

        for i, symbol in enumerate(NIFTY50_SYMBOLS, 1):
            logger.info(f"[{i}/{len(NIFTY50_SYMBOLS)}] Computing features for {symbol}...")
            start = time.time()
            count = backfill_symbol(symbol, db)
            elapsed = time.time() - start
            logger.info(f"  {symbol}: {count:,} feature rows saved ({elapsed:.1f}s)")
            total += count

        logger.info("=" * 60)
        logger.info(f"Backfill complete! Total feature rows: {total:,}")
        logger.info("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
