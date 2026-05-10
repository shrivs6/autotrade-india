"""
Signal evaluator — sits between feature builder and order manager.
Calls the rule engine (Phase 3) or ML model (Phase 5) to get a signal,
logs every evaluation to trade_signals table, and returns approved signals.
"""
from datetime import datetime
import pytz
from backend.trading.rule_engine import get_signal
from backend.database.connection import SessionLocal
from backend.database.models import TradeSignal
from backend.utils.type_utils import to_python
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def evaluate_and_log(features: dict, db=None) -> tuple[str | None, float | None]:
    """
    Evaluates a feature dict and logs the signal to trade_signals table.
    Returns (direction, confidence) or (None, None) if no signal.
    confidence is None for rule-based (Phase 3), float for ML (Phase 5).
    """
    symbol = features.get("symbol", "UNKNOWN")
    ts_str = features.get("timestamp")
    ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(IST)

    direction, reason = get_signal(features)

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        signal_record = TradeSignal(
            symbol=symbol,
            timestamp=ts,
            direction=direction or "none",
            confidence=None,            # filled by ML evaluator in Phase 5
            features=to_python(features),
            trade_taken=False,          # updated by order_manager if trade is placed
            skip_reason=None if direction else reason,
        )
        db.add(signal_record)
        db.commit()
        db.refresh(signal_record)

        return direction, signal_record.id

    except Exception as e:
        logger.error(f"Failed to log signal for {symbol}: {e}")
        db.rollback()
        return direction, None

    finally:
        if close_db:
            db.close()
