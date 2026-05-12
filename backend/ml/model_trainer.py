"""
XGBoost model trainer.
Uses walk-forward validation (NOT random split) to evaluate performance.
Walk-forward = train on past months, validate on next month — respects time ordering.
"""
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score
from backend.ml.dataset_builder import FEATURE_COLS
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def get_xgb_params(neg_count: int, pos_count: int) -> dict:
    """XGBoost hyperparameters. scale_pos_weight handles class imbalance."""
    return {
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 10,
        "scale_pos_weight": neg_count / max(pos_count, 1),
        "eval_metric": "auc",
        "early_stopping_rounds": 50,  # passed in constructor for newer XGBoost
        "random_state": 42,
        "n_jobs": 2,
    }


def train_model(df: pd.DataFrame) -> tuple:
    """
    Trains XGBoost on the full dataset.
    Used for the initial v1 model and nightly retraining.
    Returns (model, eval_auc).
    """
    feature_cols = [c for c in FEATURE_COLS if c in df.columns]
    X = df[feature_cols].values
    y = df["label"].values

    neg = int((y == 0).sum())
    pos = int((y == 1).sum())
    logger.info(f"Training on {len(X):,} rows | pos={pos:,} neg={neg:,} | ratio={neg/max(pos,1):.2f}")

    params = get_xgb_params(neg, pos)

    # Use last 10% as eval set for early stopping
    split = int(len(X) * 0.9)
    X_train, X_eval = X[:split], X[split:]
    y_train, y_eval = y[:split], y[split:]

    model = XGBClassifier(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_eval, y_eval)],
        verbose=False,
    )

    eval_auc = roc_auc_score(y_eval, model.predict_proba(X_eval)[:, 1])
    logger.info(f"Eval AUC: {eval_auc:.4f}")

    return model, eval_auc


def walk_forward_validate(df: pd.DataFrame, n_splits: int = 4) -> dict:
    """
    Walk-forward cross-validation.
    Splits the dataset into time-ordered folds.
    Each fold: train on all previous months, validate on next month.

    Returns dict with avg AUC and per-fold results.
    """
    df = df.sort_values("timestamp").reset_index(drop=True)
    feature_cols = [c for c in FEATURE_COLS if c in df.columns]

    fold_size = len(df) // (n_splits + 1)
    results = []

    for i in range(n_splits):
        train_end = fold_size * (i + 1)
        val_end = train_end + fold_size

        train_df = df.iloc[:train_end]
        val_df = df.iloc[train_end:val_end]

        if len(train_df) < 1000 or len(val_df) < 100:
            continue

        X_train = train_df[feature_cols].values
        y_train = train_df["label"].values
        X_val = val_df[feature_cols].values
        y_val = val_df["label"].values

        neg = int((y_train == 0).sum())
        pos = int((y_train == 1).sum())
        params = get_xgb_params(neg, pos)
        params.pop("early_stopping_rounds")  # no early stopping in walk-forward folds

        model = XGBClassifier(**params)
        model.fit(X_train, y_train, verbose=False)

        val_proba = model.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, val_proba)

        # Win rate at threshold 0.60
        mask = val_proba >= 0.60
        wr_60 = y_val[mask].mean() if mask.sum() > 0 else 0.0
        signals_60 = mask.sum()

        results.append({
            "fold": i + 1,
            "train_rows": len(train_df),
            "val_rows": len(val_df),
            "auc": round(auc, 4),
            "win_rate_at_60": round(float(wr_60), 4),
            "signals_at_60": int(signals_60),
        })
        logger.info(
            f"Fold {i+1}: AUC={auc:.4f} | Win@60%={wr_60:.1%} ({signals_60} signals)"
        )

    avg_auc = np.mean([r["auc"] for r in results]) if results else 0.0
    logger.info(f"Walk-forward avg AUC: {avg_auc:.4f}")

    return {
        "avg_auc": round(float(avg_auc), 4),
        "folds": results,
    }
