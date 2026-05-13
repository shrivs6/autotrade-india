"""
One-time script to backfill historical OHLCV data for all Nifty 50 stocks.

Run once after Upstox API key is available:
    python -m backend.scripts.run_historical_fetch

What it does:
- Downloads 1 year of 5-minute candles for all 50 stocks → ohlcv_5min table
- Downloads 5 years of daily candles for all 50 stocks  → ohlcv_daily table

Upstox rate limit: ~2 requests/second → expect 30-45 minutes total.
Safe to re-run — skips candles that already exist (upsert logic).
"""
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.data.upstox_client import get_upstox_client
from backend.database.connection import SessionLocal
from backend.database.models import OHLCV5Min, OHLCVDaily, Stock
from backend.utils.constants import NIFTY50_SYMBOLS
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Upstox 1-minute data: max 30 days per request
# We fetch in 30-day chunks (12 months = ~12 requests per symbol)
CHUNK_DAYS = 30
RATE_LIMIT_SLEEP = 0.6   # seconds between requests (~1.6 req/sec, safely under the 2/sec limit)


def seed_stocks(db):
    """Insert Nifty 50 stocks into the stocks master table if not already there."""
    existing = {s.symbol for s in db.query(Stock).all()}
    new_stocks = [
        Stock(symbol=sym, name=sym, sector="NSE")
        for sym in NIFTY50_SYMBOLS
        if sym not in existing
    ]
    if new_stocks:
        db.bulk_save_objects(new_stocks)
        db.commit()
        logger.info(f"Seeded {len(new_stocks)} stocks into stocks table")
    else:
        logger.info("Stocks table already seeded")


def upsert_5min(db, df: pd.DataFrame, symbol: str):
    """Insert 5-min candles, skip rows that already exist."""
    if df.empty:
        return 0

    records = [
        {
            "symbol": symbol,
            "timestamp": row.timestamp,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in df.itertuples(index=False)
    ]

    stmt = pg_insert(OHLCV5Min).values(records)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["symbol", "timestamp"]
    )
    db.execute(stmt)
    db.commit()
    return len(records)


def upsert_daily(db, df: pd.DataFrame, symbol: str):
    """Insert daily candles, skip rows that already exist."""
    if df.empty:
        return 0

    records = [
        {
            "symbol": symbol,
            "date": row.timestamp.date() if hasattr(row.timestamp, "date") else row.timestamp,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in df.itertuples(index=False)
    ]

    stmt = pg_insert(OHLCVDaily).values(records)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["symbol", "date"]
    )
    db.execute(stmt)
    db.commit()
    return len(records)


def fetch_5min_for_symbol(client, db, symbol: str, months_back: int = 12):
    """
    Fetches 5-min candles for a symbol going back `months_back` months.
    Splits into 3-month chunks because Upstox limits range per request.
    """
    total_inserted = 0
    end = datetime.today()
    start = end - relativedelta(months=months_back)

    # Build list of (chunk_start, chunk_end) date ranges — 30-day chunks for 1-min data
    chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end

    for chunk_start, chunk_end in chunks:
        from_str = chunk_start.strftime("%Y-%m-%d")
        to_str = chunk_end.strftime("%Y-%m-%d")
        try:
            df = client.fetch_historical(symbol, "5minute", from_str, to_str)
            inserted = upsert_5min(db, df, symbol)
            total_inserted += inserted
            logger.info(f"  {symbol} 5min {from_str}→{to_str}: {inserted} candles")
        except Exception as e:
            logger.error(f"  {symbol} 5min {from_str}→{to_str} FAILED: {e}")

        time.sleep(RATE_LIMIT_SLEEP)

    return total_inserted


def fetch_daily_for_symbol(client, db, symbol: str, years_back: int = 5):
    """Fetches daily candles for a symbol going back `years_back` years."""
    end = datetime.today()
    start = end - relativedelta(years=years_back)
    from_str = start.strftime("%Y-%m-%d")
    to_str = end.strftime("%Y-%m-%d")

    try:
        df = client.fetch_historical(symbol, "1day", from_str, to_str)
        inserted = upsert_daily(db, df, symbol)
        logger.info(f"  {symbol} daily {from_str}→{to_str}: {inserted} candles")
        return inserted
    except Exception as e:
        logger.error(f"  {symbol} daily FAILED: {e}")
        return 0


def refresh_todays_candles():
    """
    Fetches today's 5-min candles for all Nifty 50 symbols and upserts to DB.
    Called at the start of each scan cycle so feature builder has live data.
    Safe to call repeatedly — upsert skips already-stored candles.
    """
    client = get_upstox_client()
    db = SessionLocal()
    today_str = datetime.today().strftime("%Y-%m-%d")
    total = 0
    failed = []

    try:
        for symbol in NIFTY50_SYMBOLS:
            try:
                df = client.fetch_historical(symbol, "5minute", today_str, today_str)
                inserted = upsert_5min(db, df, symbol)
                total += inserted
                time.sleep(RATE_LIMIT_SLEEP)
            except Exception as e:
                logger.error(f"refresh_todays_candles: {symbol} failed: {e}")
                failed.append(symbol)

        logger.info(f"Live candle refresh: {total} new candles upserted, {len(failed)} failed")
        if failed:
            logger.warning(f"Failed symbols: {failed}")
    finally:
        db.close()


def run_full_backfill():
    """
    Main entry point. Fetches all historical data for all Nifty 50 stocks.
    Expected runtime: 30-45 minutes with real Upstox API.
    In STUB MODE: completes in seconds with fake data.
    """
    client = get_upstox_client()
    db = SessionLocal()

    try:
        logger.info("=" * 60)
        logger.info("Starting full historical data backfill")
        logger.info(f"Symbols: {len(NIFTY50_SYMBOLS)}")
        logger.info("=" * 60)

        seed_stocks(db)

        total_5min = 0
        total_daily = 0
        failed = []

        for i, symbol in enumerate(NIFTY50_SYMBOLS, 1):
            logger.info(f"[{i}/{len(NIFTY50_SYMBOLS)}] Processing {symbol}...")

            inserted_5min = fetch_5min_for_symbol(client, db, symbol, months_back=12)
            time.sleep(RATE_LIMIT_SLEEP)

            inserted_daily = fetch_daily_for_symbol(client, db, symbol, years_back=5)
            time.sleep(RATE_LIMIT_SLEEP)

            total_5min += inserted_5min
            total_daily += inserted_daily

            if inserted_5min == 0 and inserted_daily == 0:
                failed.append(symbol)

        logger.info("=" * 60)
        logger.info("Backfill complete!")
        logger.info(f"  5-min candles inserted : {total_5min:,}")
        logger.info(f"  Daily candles inserted : {total_daily:,}")
        if failed:
            logger.warning(f"  Failed symbols        : {failed}")
        logger.info("=" * 60)

    finally:
        db.close()
