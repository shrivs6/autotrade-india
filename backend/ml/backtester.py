"""
Backtester — replays 6 months of historical data through the full trading system.
Simulates realistic conditions: 0.1% slippage, ₹20 brokerage per trade.
Uses the ML model for signal generation (not rule engine).
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from xgboost import XGBClassifier
from backend.ml.dataset_builder import FEATURE_COLS
from backend.database.connection import SessionLocal
from backend.database.models import SignalFeature, OHLCV5Min
from backend.config import STOP_LOSS_PCT, TARGET_PCT, MAX_CONCURRENT_POSITIONS, DAILY_LOSS_LIMIT
from backend.utils.constants import NIFTY50_SYMBOLS
from backend.utils.logger import get_logger

logger = get_logger(__name__)

SLIPPAGE = 0.001        # 0.1% slippage on entry
BROKERAGE = 20          # ₹20 per trade (round trip)
EXPOSURE = 100000       # ₹1,00,000 per trade
CONFIDENCE_THRESHOLD = 0.60


def run_backtest(
    model: XGBClassifier,
    months: int = 6,
    threshold: float = CONFIDENCE_THRESHOLD,
) -> dict:
    """
    Runs a walk-forward backtest on the last `months` of historical data.
    Returns a summary dict with PnL, win rate, drawdown, etc.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=months * 30)

    logger.info(f"Backtesting from {start_date} to {end_date} | threshold={threshold}")

    db = SessionLocal()
    feature_cols = [c for c in FEATURE_COLS if c != "direction"]

    trades = []
    daily_pnl = {}

    try:
        for symbol in NIFTY50_SYMBOLS:
            # Fetch feature rows in backtest window
            sf_rows = (
                db.query(SignalFeature)
                .filter(SignalFeature.symbol == symbol)
                .filter(SignalFeature.timestamp >= str(start_date))
                .filter(SignalFeature.timestamp <= str(end_date))
                .order_by(SignalFeature.timestamp.asc())
                .all()
            )

            if not sf_rows:
                continue

            # Fetch OHLCV for forward label check
            ohlcv_rows = (
                db.query(OHLCV5Min)
                .filter(OHLCV5Min.symbol == symbol)
                .filter(OHLCV5Min.timestamp >= str(start_date))
                .order_by(OHLCV5Min.timestamp.asc())
                .all()
            )
            ohlcv_df = pd.DataFrame([{
                "timestamp": r.timestamp,
                "high": r.high,
                "low": r.low,
            } for r in ohlcv_rows]).set_index("timestamp")

            for sf in sf_rows:
                features = sf.features
                if not features:
                    continue

                entry_price = features.get("close_price")
                if not entry_price:
                    continue

                trade_date = sf.timestamp.date()

                # Daily loss limit check
                if daily_pnl.get(trade_date, 0) <= DAILY_LOSS_LIMIT:
                    continue

                # Count open positions that day
                open_today = sum(
                    1 for t in trades
                    if t["date"] == trade_date and t["status"] == "open"
                )
                if open_today >= MAX_CONCURRENT_POSITIONS:
                    continue

                # Score both directions
                for direction, dir_flag in [("long", 0), ("short", 1)]:
                    row = {col: features.get(col) for col in feature_cols}
                    row["direction"] = dir_flag
                    X = np.array([[row.get(col, 0) or 0 for col in FEATURE_COLS]])

                    try:
                        confidence = float(model.predict_proba(X)[0][1])
                    except Exception:
                        continue

                    if confidence < threshold:
                        continue

                    # Apply slippage to entry price
                    if direction == "long":
                        fill_price = entry_price * (1 + SLIPPAGE)
                        target_price = fill_price * (1 + TARGET_PCT)
                        stop_price = fill_price * (1 - STOP_LOSS_PCT)
                    else:
                        fill_price = entry_price * (1 - SLIPPAGE)
                        target_price = fill_price * (1 - TARGET_PCT)
                        stop_price = fill_price * (1 + STOP_LOSS_PCT)

                    quantity = int(EXPOSURE / fill_price)

                    # Look forward to determine outcome
                    future = ohlcv_df[ohlcv_df.index > sf.timestamp].head(78)
                    win = False
                    exit_reason = "timeout"

                    for _, candle in future.iterrows():
                        if direction == "long":
                            if candle["high"] >= target_price:
                                win = True
                                exit_reason = "target_hit"
                                break
                            if candle["low"] <= stop_price:
                                exit_reason = "stop_hit"
                                break
                        else:
                            if candle["low"] <= target_price:
                                win = True
                                exit_reason = "target_hit"
                                break
                            if candle["high"] >= stop_price:
                                exit_reason = "stop_hit"
                                break

                    exit_price = target_price if win else stop_price
                    if direction == "long":
                        pnl = (exit_price - fill_price) * quantity - BROKERAGE
                    else:
                        pnl = (fill_price - exit_price) * quantity - BROKERAGE

                    trades.append({
                        "symbol": symbol,
                        "date": trade_date,
                        "direction": direction,
                        "confidence": confidence,
                        "entry_price": fill_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "win": win,
                        "exit_reason": exit_reason,
                        "status": "closed",
                    })

                    daily_pnl[trade_date] = daily_pnl.get(trade_date, 0) + pnl
                    break  # only one trade per symbol per 5-min candle

    finally:
        db.close()

    return _compute_summary(trades, start_date, end_date)


def _compute_summary(trades: list, start_date, end_date) -> dict:
    if not trades:
        return {"error": "No trades generated in backtest"}

    df = pd.DataFrame(trades)
    total = len(df)
    wins = df["win"].sum()
    win_rate = wins / total if total > 0 else 0
    total_pnl = df["pnl"].sum()

    # Daily PnL for drawdown calculation
    daily = df.groupby("date")["pnl"].sum().sort_index()
    cumulative = daily.cumsum()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max)
    max_drawdown = float(drawdown.min())

    # Signals per day
    n_days = max((end_date - start_date).days, 1)
    signals_per_day = total / n_days

    summary = {
        "period": f"{start_date} to {end_date}",
        "total_trades": int(total),
        "winners": int(wins),
        "losers": int(total - wins),
        "win_rate": round(float(win_rate), 4),
        "total_pnl": round(float(total_pnl), 2),
        "avg_pnl_per_trade": round(float(df["pnl"].mean()), 2),
        "max_drawdown": round(max_drawdown, 2),
        "signals_per_day": round(signals_per_day, 2),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
    }

    logger.info("=== Backtest Results ===")
    for k, v in summary.items():
        logger.info(f"  {k}: {v}")

    return summary
