"""
Rule-based signal generator — Phase 3.
Hard-coded entry rules using technical indicators + market context.
Expected win rate: 45-55% (baseline for ML to beat in Phase 4).

Replaced by ml_signal_evaluator.py in Phase 5, but kept here for reference.
"""
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def evaluate_long(features: dict) -> tuple[bool, str]:
    """
    Returns (signal: bool, reason: str).
    All conditions must be true for a LONG signal.
    """
    checks = {
        "bias_ok":        features.get("morning_bias", 0) >= 0,
        "rsi_ok":         40 <= features.get("rsi", 0) <= 65,
        "macd_positive":  features.get("macd_histogram", 0) > 0,
        "macd_rising":    features.get("macd_histogram_rising", 0) == 1,
        "price_above_bb": features.get("bb_pct", 0) >= 0.5,
        "volume_ok":      features.get("volume_spike", 0) >= 1.5,
    }

    failed = [k for k, v in checks.items() if not v]

    if not failed:
        return True, "all long conditions met"
    return False, f"failed: {', '.join(failed)}"


def evaluate_short(features: dict) -> tuple[bool, str]:
    """
    Returns (signal: bool, reason: str).
    All conditions must be true for a SHORT signal.
    """
    checks = {
        "bias_ok":        features.get("morning_bias", 0) <= 0,
        "rsi_ok":         35 <= features.get("rsi", 0) <= 60,
        "macd_negative":  features.get("macd_histogram", 0) < 0,
        "macd_falling":   features.get("macd_histogram_rising", 0) == 0,
        "price_below_bb": features.get("bb_pct", 0) <= 0.5,
        "volume_ok":      features.get("volume_spike", 0) >= 1.5,
    }

    failed = [k for k, v in checks.items() if not v]

    if not failed:
        return True, "all short conditions met"
    return False, f"failed: {', '.join(failed)}"


def get_signal(features: dict) -> tuple[str | None, str]:
    """
    Main entry point. Returns (direction, reason).
    direction: 'long' | 'short' | None
    """
    # Check long first
    long_ok, long_reason = evaluate_long(features)
    if long_ok:
        logger.info(f"{features.get('symbol')} — LONG signal | {long_reason}")
        return "long", long_reason

    # Check short
    short_ok, short_reason = evaluate_short(features)
    if short_ok:
        logger.info(f"{features.get('symbol')} — SHORT signal | {short_reason}")
        return "short", short_reason

    return None, long_reason  # return why long failed (most common case)
