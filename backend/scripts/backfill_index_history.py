"""
Backfills 2 years of historical 5-min OHLCV data for NIFTY and BANKNIFTY
using NSE_INDEX instruments (continuous — no contract rolling, no price gaps).

Why NSE_INDEX instead of futures contracts:
- Each futures contract has a unique instrument key and only goes back ~2 months
- NSE_INDEX|Nifty 50 and NSE_INDEX|Nifty Bank are continuous instruments
- Price patterns (RSI, MACD, trend slope) are identical to futures (~0.2% basis difference)
- Gives us 2 years of training data vs the current 6 weeks

Run via POST /admin/backfill-history (triggers in background on Railway).
"""
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.connection import SessionLocal
from backend.database.models import OHLCV5Min
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# NSE_INDEX instrument keys — continuous, no rollover
INDEX_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}

CHUNK_DAYS = 30       # Upstox 1-min data limit per request
RATE_LIMIT_SLEEP = 0.7
YEARS_BACK = 2


def _fetch_index_chunk(
    access_token: str,
    instrument_key: str,
    from_date: str,
    to_date: str,
) -> pd.DataFrame:
    """Fetch 1-min candles from Upstox for an index instrument and resample to 5-min."""
    import upstox_client

    config = upstox_client.Configuration()
    config.access_token = access_token
    client = upstox_client.ApiClient(config)
    api = upstox_client.HistoryApi(client)

    response = api.get_historical_candle_data1(
        instrument_key=instrument_key,
        interval="1minute",
        to_date=to_date,
        from_date=from_date,
        api_version="2.0",
    )
    candles = response.data.candles
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(
        candles,
        columns=["timestamp", "open", "high", "low", "close", "volume", "oi"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")

    # Resample 1-min → 5-min
    df = (
        df.set_index("timestamp")
        .resample("5min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "close"])
        .reset_index()
    )

    # If index returns zero volume, replace with NaN so volume_spike
    # falls back to neutral (1.0) in feature computation
    if df["volume"].sum() == 0:
        df["volume"] = float("nan")

    return df


def _upsert_candles(db, df: pd.DataFrame, symbol: str) -> int:
    if df.empty:
        return 0
    records = [
        {
            "symbol": symbol,
            "timestamp": row.timestamp,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume) if pd.notna(row.volume) else 0.0,
        }
        for row in df.itertuples(index=False)
    ]
    stmt = pg_insert(OHLCV5Min).values(records)
    stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
    db.execute(stmt)
    db.commit()
    return len(records)


def run_index_backfill(status_callback=None) -> dict:
    """
    Main entry point. Fetches 2 years of NSE_INDEX data for NIFTY + BANKNIFTY.
    Existing candles (March-May 2026 futures data) are preserved — upsert skips duplicates.

    status_callback: optional callable(msg) for streaming progress to logs.
    """
    from backend.data.upstox_client import _load_token_from_db

    def log(msg):
        logger.info(msg)
        if status_callback:
            status_callback(msg)

    access_token = _load_token_from_db()
    if not access_token:
        raise RuntimeError("No valid Upstox token in DB — visit /auth/login first")

    db = SessionLocal()
    results = {}

    try:
        end = datetime.today()
        start = end - relativedelta(years=YEARS_BACK)

        # Build 30-day chunks
        chunks = []
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end)
            chunks.append((chunk_start, chunk_end))
            chunk_start = chunk_end

        log(f"=== Index History Backfill Starting ===")
        log(f"Range: {start.date()} → {end.date()} | {len(chunks)} chunks per symbol")

        for symbol, instrument_key in INDEX_KEYS.items():
            log(f"[{symbol}] Fetching {YEARS_BACK} years of 5-min data...")
            total = 0
            errors = 0

            for i, (cs, ce) in enumerate(chunks, 1):
                from_str = cs.strftime("%Y-%m-%d")
                to_str = ce.strftime("%Y-%m-%d")
                try:
                    df = _fetch_index_chunk(access_token, instrument_key, from_str, to_str)
                    inserted = _upsert_candles(db, df, symbol)
                    total += inserted
                    if i % 5 == 0 or i == len(chunks):
                        log(f"  {symbol}: chunk {i}/{len(chunks)} done — {total:,} candles so far")
                except Exception as e:
                    logger.error(f"  {symbol} chunk {from_str}→{to_str} failed: {e}")
                    errors += 1
                time.sleep(RATE_LIMIT_SLEEP)

            log(f"[{symbol}] Done: {total:,} candles inserted, {errors} chunk errors")
            results[symbol] = {"inserted": total, "errors": errors}

        log("=== Candle backfill complete ===")
        return results

    finally:
        db.close()


def run_feature_backfill() -> int:
    """Re-runs the signal_features backfill on the newly loaded candles."""
    from backend.scripts.backfill_features import run_backfill
    logger.info("=== Starting feature backfill on new candles ===")
    run_backfill()
    logger.info("=== Feature backfill complete ===")


def run_retrain():
    """Triggers the ML retrain immediately after backfill."""
    from backend.ml.incremental_trainer import run_incremental_retrain
    logger.info("=== Triggering immediate retrain ===")
    run_incremental_retrain()
    logger.info("=== Retrain complete ===")
