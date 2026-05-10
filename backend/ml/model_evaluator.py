"""
Evaluates model performance at different confidence thresholds.
Key metric: win rate and expected PnL per trade at each threshold.
"""
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from backend.ml.dataset_builder import FEATURE_COLS
from backend.config import STOP_LOSS_PCT, TARGET_PCT
from backend.utils.logger import get_logger

logger = get_logger(__name__)

THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70]


def evaluate_thresholds(model: XGBClassifier, df: pd.DataFrame) -> pd.DataFrame:
    """
    For each confidence threshold, computes:
    - win_rate: fraction of trades that win
    - signals_per_day: how many trades would be taken per trading day
    - expected_pnl_per_trade: (win_rate * reward) - (loss_rate * risk)
    - expected_pnl_daily: expected_pnl_per_trade * signals_per_day

    Uses ₹1,00,000 exposure: reward = ₹750 per win, risk = ₹500 per loss.
    """
    feature_cols = [c for c in FEATURE_COLS if c in df.columns]
    X = df[feature_cols].values
    y = df["label"].values

    proba = model.predict_proba(X)[:, 1]

    # Estimate trading days in dataset
    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df_copy["timestamp"]).dt.date
    n_days = df_copy["date"].nunique()
    n_days = max(n_days, 1)

    reward_per_win = 100000 * TARGET_PCT      # ₹750
    risk_per_loss = 100000 * STOP_LOSS_PCT    # ₹500

    rows = []
    for threshold in THRESHOLDS:
        mask = proba >= threshold
        n_signals = mask.sum()
        if n_signals == 0:
            rows.append({
                "threshold": threshold,
                "win_rate": 0.0,
                "signals_total": 0,
                "signals_per_day": 0.0,
                "expected_pnl_per_trade": 0.0,
                "expected_pnl_daily": 0.0,
            })
            continue

        win_rate = float(y[mask].mean())
        loss_rate = 1 - win_rate
        expected_pnl_per_trade = (win_rate * reward_per_win) - (loss_rate * risk_per_loss)
        signals_per_day = n_signals / n_days

        rows.append({
            "threshold": threshold,
            "win_rate": round(win_rate, 4),
            "signals_total": int(n_signals),
            "signals_per_day": round(signals_per_day, 2),
            "expected_pnl_per_trade": round(expected_pnl_per_trade, 2),
            "expected_pnl_daily": round(expected_pnl_per_trade * signals_per_day, 2),
        })

    results = pd.DataFrame(rows)

    logger.info("\n=== Threshold Evaluation ===")
    logger.info(results.to_string(index=False))

    # Recommend best threshold: maximizes expected daily PnL with >= 2 signals/day
    viable = results[results["signals_per_day"] >= 2]
    if not viable.empty:
        best = viable.loc[viable["expected_pnl_daily"].idxmax()]
        logger.info(f"\nRecommended threshold: {best['threshold']} "
                    f"(win rate: {best['win_rate']:.1%}, "
                    f"~{best['signals_per_day']:.1f} signals/day, "
                    f"~₹{best['expected_pnl_daily']:,.0f}/day expected)")

    return results


def get_feature_importance(model: XGBClassifier, top_n: int = 10) -> pd.DataFrame:
    """Returns top N most important features by XGBoost gain score."""
    feature_cols = FEATURE_COLS
    importance = model.get_booster().get_score(importance_type="gain")

    rows = []
    for i, col in enumerate(feature_cols):
        fname = f"f{i}"
        rows.append({
            "feature": col,
            "importance": importance.get(fname, 0.0),
        })

    df = pd.DataFrame(rows).sort_values("importance", ascending=False).head(top_n)
    logger.info(f"\nTop {top_n} features by importance:\n{df.to_string(index=False)}")
    return df
