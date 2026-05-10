"""
Tracks all open positions in memory during the trading day.
Resets at market open. Persisted state lives in the trades DB table.
"""
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class PositionTracker:
    def __init__(self):
        self._positions: dict[int, dict] = {}  # trade_id → position dict

    def add(self, trade_id: int, symbol: str, direction: str,
            entry_price: float, stop_loss: float, target: float, quantity: int):
        self._positions[trade_id] = {
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "quantity": quantity,
        }
        logger.info(f"Position opened: {direction.upper()} {symbol} @ ₹{entry_price} "
                    f"| SL: ₹{stop_loss} | Target: ₹{target} | Qty: {quantity}")

    def remove(self, trade_id: int):
        pos = self._positions.pop(trade_id, None)
        if pos:
            logger.info(f"Position closed: {pos['symbol']} (trade_id={trade_id})")

    def get_all(self) -> list[dict]:
        return list(self._positions.values())

    def get(self, trade_id: int) -> dict | None:
        return self._positions.get(trade_id)

    def count(self) -> int:
        return len(self._positions)

    def reset(self):
        count = len(self._positions)
        self._positions.clear()
        logger.info(f"Position tracker reset ({count} positions cleared)")


# Singleton — shared across the entire trading session
_tracker = None

def get_position_tracker() -> PositionTracker:
    global _tracker
    if _tracker is None:
        _tracker = PositionTracker()
    return _tracker
