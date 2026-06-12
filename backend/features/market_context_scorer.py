"""
Converts raw VIX and FII numbers into model-ready features.
Computes the morning bias score (-1 to +1) used by the trading engine.
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta
from backend.database.connection import SessionLocal
from backend.database.models import MarketContext
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def compute_fii_zscore(fii_net: float, db) -> float:
    """
    Normalize today's FII activity vs last 20 trading days.
    z-score > 1.5 = unusually strong buying
    z-score < -1.5 = unusually strong selling
    """
    cutoff = date.today() - timedelta(days=30)
    recent = (
        db.query(MarketContext.fii_net_crores)
        .filter(MarketContext.date >= cutoff)
        .filter(MarketContext.fii_net_crores.isnot(None))
        .all()
    )
    values = [r[0] for r in recent]

    if len(values) < 5:
        # Not enough history — return neutral
        return 0.0

    mean = np.mean(values)
    std = np.std(values)
    if std < 1:
        return 0.0

    return float((fii_net - mean) / std)


def compute_morning_bias(
    vix: float,
    fii_z: float,
    prev_day_return: float
) -> float:
    """
    Combines VIX direction, FII sentiment, and previous day's Nifty return
    into a single bias score from -1 (strongly bearish) to +1 (strongly bullish).

    Logic:
    - High VIX (>18) pulls bias toward bearish (market is fearful)
    - Positive FII z-score pulls bias bullish (foreign money flowing in)
    - Positive prev day return slightly pulls bias bullish (momentum)

    Weights: VIX=40%, FII=40%, prev return=20%
    """
    # VIX component: VIX 10 = +0.5 (low fear), VIX 20 = 0 (neutral), VIX 30 = -0.5 (high fear)
    vix_score = np.clip((20 - vix) / 20, -1, 1)

    # FII component: clip to [-1, +1]
    fii_score = np.clip(fii_z / 2, -1, 1)

    # Previous day return component: +1% = +0.5 score, -1% = -0.5 score
    ret_score = np.clip(prev_day_return * 50, -1, 1)

    bias = 0.4 * vix_score + 0.4 * fii_score + 0.2 * ret_score
    return round(float(bias), 4)


def get_vix_features(vix: float) -> dict:
    """Returns all VIX-derived features."""
    return {
        "vix": vix,
        "vix_high": int(vix > 20),      # binary flag: elevated fear
        "vix_extreme": int(vix > 25),   # binary flag: extreme fear → reduce position size
    }


def get_today_context(db=None) -> dict | None:
    """
    Fetches today's market context from the DB.
    Returns None if not yet computed (pre-market).
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        ctx = (
            db.query(MarketContext)
            .filter(MarketContext.date == date.today())
            .first()
        )
        if ctx is None:
            return None
        return {
            "vix": ctx.vix,  # None if both fetch attempts failed — callers must handle
            "fii_net_crores": ctx.fii_net_crores or 0.0,
            "fii_z_score": ctx.fii_z_score or 0.0,
            "morning_bias": ctx.morning_bias or 0.0,
            "vix_high": int((ctx.vix or 0) > 20),
            "vix_extreme": int((ctx.vix or 0) > 25),
        }
    finally:
        if close_db:
            db.close()


def save_morning_context(vix: float | None, fii_net: float, prev_day_return: float, db=None):
    """
    Called at 8:30 AM by the scheduler.
    Computes and saves today's market context to the DB.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        fii_z = compute_fii_zscore(fii_net, db)
        bias = compute_morning_bias(vix, fii_z, prev_day_return) if vix is not None else None

        today = date.today()
        existing = db.query(MarketContext).filter(MarketContext.date == today).first()

        if existing:
            existing.vix = vix
            existing.fii_net_crores = fii_net
            existing.fii_z_score = fii_z
            existing.morning_bias = bias
        else:
            ctx = MarketContext(
                date=today,
                vix=vix,
                fii_net_crores=fii_net,
                fii_z_score=fii_z,
                morning_bias=bias,
                nifty_prev_return=prev_day_return,
            )
            db.add(ctx)

        db.commit()
        logger.info(f"Morning context saved: VIX={vix}, FII z={fii_z:.2f}, bias={bias}")
        return bias

    finally:
        if close_db:
            db.close()
