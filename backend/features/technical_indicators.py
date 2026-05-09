"""
Computes technical indicators on a DataFrame of OHLCV candles.
All functions take a DataFrame with columns: open, high, low, close, volume
and return the same DataFrame with new indicator columns added.
"""
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    RSI (Relative Strength Index) — momentum indicator.
    Range: 0 to 100.
    Below 30 = oversold (potential bounce), Above 70 = overbought (potential drop).
    """
    rsi = RSIIndicator(close=df["close"], window=period)
    df["rsi"] = rsi.rsi()
    return df


def add_macd(df: pd.DataFrame) -> pd.DataFrame:
    """
    MACD — trend + momentum indicator.
    macd_line: fast EMA - slow EMA
    macd_signal: 9-period EMA of MACD line
    macd_histogram: MACD line - signal line
      - Positive and rising = bullish momentum building
      - Negative and falling = bearish momentum building
    """
    macd = MACD(close=df["close"])
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()
    # Whether histogram is rising compared to previous candle
    df["macd_histogram_rising"] = (df["macd_histogram"] > df["macd_histogram"].shift(1)).astype(int)
    return df


def add_bollinger_bands(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    Bollinger Bands — volatility indicator.
    bb_upper, bb_middle, bb_lower: the three bands
    bb_pct: where price sits within the bands (percent B)
      - 0 = at lower band, 1 = at upper band
      - Below 0 = below lower band (strong oversold)
      - Above 1 = above upper band (strong overbought)
    """
    bb = BollingerBands(close=df["close"], window=period)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_pct"] = bb.bollinger_pband()
    return df


def add_volume_spike(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    Volume spike — how unusual today's volume is vs recent average.
    1.0 = average volume, 2.0 = double average (significant), 3.0+ = very unusual.
    """
    avg_volume = df["volume"].rolling(window=period).mean()
    df["volume_spike"] = df["volume"] / avg_volume
    return df


def add_trend_slope(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    Trend slope — direction and strength of recent price movement.
    Uses linear regression on the last `period` closing prices.
    Normalized to a z-score so values are comparable across stocks.
    Positive = uptrend, negative = downtrend.
    """
    def calc_slope(series):
        if series.isna().any():
            return np.nan
        x = np.arange(len(series))
        slope = np.polyfit(x, series, 1)[0]
        return slope

    slopes = df["close"].rolling(window=period).apply(calc_slope, raw=False)

    # Z-score normalize so RELIANCE slope is comparable to a ₹500 stock
    # min_periods=5 ensures we get values even with limited history
    mean = slopes.rolling(window=50, min_periods=5).mean()
    std = slopes.rolling(window=50, min_periods=5).std()
    df["trend_slope"] = (slopes - mean) / (std + 1e-9)
    return df


def add_candle_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Candle shape features — encode candlestick structure numerically.
    body_ratio: how much of the candle range is the body (0=doji, 1=full body)
    upper_wick_ratio: upper wick as fraction of total range
    lower_wick_ratio: lower wick as fraction of total range
    """
    candle_range = df["high"] - df["low"]
    candle_range = candle_range.replace(0, np.nan)  # avoid division by zero

    body = (df["close"] - df["open"]).abs()
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    df["body_ratio"] = body / candle_range
    df["upper_wick_ratio"] = upper_wick / candle_range
    df["lower_wick_ratio"] = lower_wick / candle_range
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Time-of-day encoded as sin/cos so the model understands time is cyclical.
    (9:30 and 9:35 are close together, not far apart like raw numbers would suggest.)
    Also adds session flags: morning (9:30-11), midday (11-1), afternoon (1-3:20).
    """
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")

    minutes_since_open = (df.index.hour - 9) * 60 + df.index.minute - 30
    total_minutes = 370  # 9:30 to 15:40

    df["time_sin"] = np.sin(2 * np.pi * minutes_since_open / total_minutes)
    df["time_cos"] = np.cos(2 * np.pi * minutes_since_open / total_minutes)

    hour = df.index.hour
    df["session_morning"] = ((hour >= 9) & (hour < 11)).astype(int)
    df["session_midday"] = ((hour >= 11) & (hour < 13)).astype(int)
    df["session_afternoon"] = ((hour >= 13)).astype(int)

    df = df.reset_index()
    return df


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Master function — runs all indicators on a DataFrame.
    Input: DataFrame with columns: timestamp, open, high, low, close, volume
    Output: Same DataFrame with all indicator columns added.
    Requires at least 20 candles for indicators to be non-NaN.
    """
    df = df.copy().sort_values("timestamp").reset_index(drop=True)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_volume_spike(df)
    df = add_trend_slope(df)
    df = add_candle_features(df)
    df = add_time_features(df)
    return df
