"""
Master feature builder.
Given a symbol and timestamp, fetches recent candles from the DB,
computes all technical indicators, adds market context, and returns
a single feature dictionary ready for ML model input.

This is the central function that the trading engine calls every 5 minutes.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal
from backend.database.models import OHLCV5Min
from backend.features.technical_indicators import compute_all_indicators
from backend.features.market_context_scorer import get_today_context
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Minimum candles needed before indicators are reliable
MIN_CANDLES = 50

# How many recent candles to fetch for indicator computation
LOOKBACK_CANDLES = 100


def fetch_recent_candles(symbol: str, as_of: datetime, db: Session) -> pd.DataFrame:
    """
    Fetches the last LOOKBACK_CANDLES 5-min candles for a symbol up to `as_of` timestamp.
    """
    rows = (
        db.query(OHLCV5Min)
        .filter(OHLCV5Min.symbol == symbol)
        .filter(OHLCV5Min.timestamp <= as_of)
        .order_by(OHLCV5Min.timestamp.desc())
        .limit(LOOKBACK_CANDLES)
        .all()
    )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "timestamp": r.timestamp,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume,
    } for r in rows])

    return df.sort_values("timestamp").reset_index(drop=True)


def extract_latest_features(df: pd.DataFrame) -> dict | None:
    """
    Takes an indicator-enriched DataFrame and extracts the last row as a feature dict.
    Returns None if any critical feature is NaN.
    """
    if df.empty or len(df) < MIN_CANDLES:
        return None

    row = df.iloc[-1]

    features = {
        # RSI
        "rsi": row.get("rsi"),
        # MACD
        "macd_line": row.get("macd_line"),
        "macd_histogram": row.get("macd_histogram"),
        "macd_histogram_rising": row.get("macd_histogram_rising"),
        # Bollinger Bands
        "bb_pct": row.get("bb_pct"),
        "bb_upper": row.get("bb_upper"),
        "bb_middle": row.get("bb_middle"),
        "bb_lower": row.get("bb_lower"),
        # Volume
        "volume_spike": row.get("volume_spike"),
        # Trend
        "trend_slope": row.get("trend_slope"),
        # Candle shape
        "body_ratio": row.get("body_ratio"),
        "upper_wick_ratio": row.get("upper_wick_ratio"),
        "lower_wick_ratio": row.get("lower_wick_ratio"),
        # Time
        "time_sin": row.get("time_sin"),
        "time_cos": row.get("time_cos"),
        "session_morning": row.get("session_morning"),
        "session_midday": row.get("session_midday"),
        "session_afternoon": row.get("session_afternoon"),
        # Price (not a model feature — used for order sizing)
        "close_price": row.get("close"),
    }

    # Check for NaN in critical features
    critical = ["rsi", "macd_histogram", "bb_pct", "volume_spike", "trend_slope"]
    for key in critical:
        val = features.get(key)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            logger.debug(f"NaN in critical feature '{key}' — skipping")
            return None

    return features


def build_features(symbol: str, as_of: datetime = None, db: Session = None) -> dict | None:
    """
    Main entry point. Returns a complete feature dictionary for (symbol, as_of).

    Args:
        symbol: Stock ticker e.g. 'RELIANCE'
        as_of: Timestamp to compute features at (default: now)
        db: Optional DB session (creates one if not provided)

    Returns:
        dict with 25+ features, or None if insufficient data
    """
    if as_of is None:
        import pytz
        as_of = datetime.now(pytz.utc)
    elif as_of.tzinfo is None:
        import pytz
        as_of = pytz.utc.localize(as_of)

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # 1. Fetch recent candles
        candles = fetch_recent_candles(symbol, as_of, db)
        if candles.empty or len(candles) < MIN_CANDLES:
            logger.debug(f"{symbol}: insufficient candles ({len(candles)}) at {as_of}")
            return None

        # 2. Compute technical indicators
        enriched = compute_all_indicators(candles)

        # 3. Extract latest row as features
        features = extract_latest_features(enriched)
        if features is None:
            return None

        # 4. Add market context (VIX, FII, morning bias)
        context = get_today_context(db)
        if context:
            features.update(context)
        else:
            # Market not yet open or context not fetched — use neutral defaults
            features.update({
                "vix": 15.0,
                "fii_net_crores": 0.0,
                "fii_z_score": 0.0,
                "morning_bias": 0.0,
                "vix_high": 0,
                "vix_extreme": 0,
            })

        features["symbol"] = symbol
        features["timestamp"] = as_of.isoformat()

        return features

    except Exception as e:
        logger.error(f"build_features failed for {symbol} at {as_of}: {e}")
        return None

    finally:
        if close_db:
            db.close()
