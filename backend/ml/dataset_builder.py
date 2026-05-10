"""
Builds the labeled training dataset for XGBoost.

For each feature row in signal_features, we look forward in the OHLCV data
to determine the label:
  label = 1 → trade hit 0.75% target before 0.5% stop (WIN)
  label = 0 → trade hit 0.5% stop before 0.75% target (LOSS or timeout)

We create two rows per candle — one for LONG, one for SHORT — with
'direction' as a binary feature (0=long, 1=short). This trains one model
that understands both directions.
"""
import pandas as pd
import numpy as np
from backend.database.connection import SessionLocal
from backend.database.models import SignalFeature, OHLCV5Min
from backend.config import STOP_LOSS_PCT, TARGET_PCT
from backend.utils.constants import NIFTY50_SYMBOLS
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Maximum candles to look forward before declaring timeout (LOSS)
MAX_FORWARD_CANDLES = 78  # full trading day

# Features used by the model (exclude metadata fields)
FEATURE_COLS = [
    "rsi", "macd_line", "macd_histogram", "macd_histogram_rising",
    "bb_pct", "volume_spike", "trend_slope",
    "body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "time_sin", "time_cos", "session_morning", "session_midday", "session_afternoon",
    "vix", "vix_high", "vix_extreme", "fii_z_score", "morning_bias",
    "direction",   # 0=long, 1=short — added by dataset builder
]


def compute_label(
    entry_price: float,
    direction: str,
    future_candles: pd.DataFrame,
) -> int:
    """
    Looks forward through future_candles and returns:
      1 if target hit before stop
      0 if stop hit first OR timed out
    """
    target_pct = TARGET_PCT    # 0.75%
    stop_pct = STOP_LOSS_PCT   # 0.50%

    if direction == "long":
        target_price = entry_price * (1 + target_pct)
        stop_price = entry_price * (1 - stop_pct)
        for _, candle in future_candles.iterrows():
            if candle["high"] >= target_price:
                return 1
            if candle["low"] <= stop_price:
                return 0
    else:  # short
        target_price = entry_price * (1 - target_pct)
        stop_price = entry_price * (1 + stop_pct)
        for _, candle in future_candles.iterrows():
            if candle["low"] <= target_price:
                return 1
            if candle["high"] >= stop_price:
                return 0

    return 0  # timeout = loss


def build_dataset(symbols: list = None, limit_per_symbol: int = None) -> pd.DataFrame:
    """
    Main function. Returns labeled DataFrame ready for XGBoost training.

    Args:
        symbols: list of symbols to include (default: all Nifty 50)
        limit_per_symbol: cap rows per symbol (useful for quick testing)

    Returns:
        DataFrame with FEATURE_COLS + 'label' column
    """
    if symbols is None:
        symbols = NIFTY50_SYMBOLS

    db = SessionLocal()
    all_rows = []

    try:
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"[{i}/{len(symbols)}] Building dataset for {symbol}...")

            # Fetch all feature rows for this symbol
            feature_rows = (
                db.query(SignalFeature)
                .filter(SignalFeature.symbol == symbol)
                .order_by(SignalFeature.timestamp.asc())
                .all()
            )

            if not feature_rows:
                logger.warning(f"{symbol}: no feature rows found")
                continue

            if limit_per_symbol:
                feature_rows = feature_rows[:limit_per_symbol]

            # Fetch all OHLCV candles for this symbol (for forward label computation)
            ohlcv_rows = (
                db.query(OHLCV5Min)
                .filter(OHLCV5Min.symbol == symbol)
                .order_by(OHLCV5Min.timestamp.asc())
                .all()
            )
            ohlcv_df = pd.DataFrame([{
                "timestamp": r.timestamp,
                "high": r.high,
                "low": r.low,
                "close": r.close,
            } for r in ohlcv_rows]).set_index("timestamp")

            symbol_rows = []
            for sf in feature_rows:
                features = sf.features
                if not features:
                    continue

                entry_price = features.get("close_price") or features.get("close")
                if not entry_price or entry_price <= 0:
                    continue

                # Get future candles for label computation
                future = ohlcv_df[ohlcv_df.index > sf.timestamp].head(MAX_FORWARD_CANDLES)
                if len(future) < 5:
                    continue  # not enough forward data

                # Create one row for LONG and one for SHORT
                for direction, dir_flag in [("long", 0), ("short", 1)]:
                    label = compute_label(entry_price, direction, future)

                    row = {col: features.get(col) for col in FEATURE_COLS if col != "direction"}
                    row["direction"] = dir_flag
                    row["label"] = label
                    row["symbol"] = symbol
                    row["timestamp"] = sf.timestamp
                    symbol_rows.append(row)

            logger.info(f"  {symbol}: {len(symbol_rows)//2:,} candles → {len(symbol_rows):,} labeled rows")
            all_rows.extend(symbol_rows)

    finally:
        db.close()

    if not all_rows:
        raise ValueError("No labeled rows generated — check signal_features table")

    df = pd.DataFrame(all_rows)

    # Fill NaN market context features with neutral defaults
    # (historical backfill didn't have live VIX/FII data)
    neutral_defaults = {
        "vix": 15.0, "vix_high": 0, "vix_extreme": 0,
        "fii_z_score": 0.0, "morning_bias": 0.0,
    }
    for col, val in neutral_defaults.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)

    # Drop rows only if core technical indicators are NaN
    core_cols = ["rsi", "macd_histogram", "bb_pct", "volume_spike", "trend_slope"]
    df = df.dropna(subset=[c for c in core_cols if c in df.columns])

    wins = df["label"].sum()
    total = len(df)
    logger.info(f"Dataset built: {total:,} rows | Win rate: {wins/total:.1%}")

    return df
