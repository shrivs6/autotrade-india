"""
Paper broker — simulates order execution without real money.
Assumes fills at the last traded price (no slippage in paper mode).

Implements the same interface as live_broker.py (Phase 6).
Switching from paper to live = one config change in .env (TRADING_MODE=live).
"""
from datetime import datetime
import pytz
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class PaperBroker:
    def place_order(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        price: float,
    ) -> dict:
        """
        Simulates placing an order. Returns a fake order result.
        In live mode this would call Upstox PlaceOrder API.
        """
        order_id = f"PAPER-{symbol}-{datetime.now(IST).strftime('%H%M%S%f')}"
        fill_price = price  # paper trading: always fills at requested price

        logger.info(
            f"[PAPER] ORDER PLACED: {direction.upper()} {quantity} {symbol} @ ₹{fill_price:.2f} "
            f"| order_id={order_id}"
        )

        return {
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "fill_price": fill_price,
            "status": "filled",
            "timestamp": datetime.now(IST).isoformat(),
        }

    def cancel_order(self, order_id: str) -> bool:
        """Simulates cancelling an order."""
        logger.info(f"[PAPER] ORDER CANCELLED: {order_id}")
        return True


_broker = None

def get_broker():
    """Returns the correct broker based on TRADING_MODE in .env."""
    global _broker
    if _broker is None:
        from backend.config import TRADING_MODE
        if TRADING_MODE == "paper":
            _broker = PaperBroker()
        elif TRADING_MODE == "live":
            # Phase 6: swap in live broker here
            from backend.trading.live_broker import LiveBroker
            _broker = LiveBroker()
        else:
            raise ValueError(f"Unknown TRADING_MODE: {TRADING_MODE}. Must be 'paper' or 'live'.")
    return _broker
