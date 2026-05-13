"""
Risk Manager — the financial safety net.
Every trade must pass through here before being placed.
Bugs in this file = real money loss. Test thoroughly.

Rules enforced:
- Max ₹1,00,000 exposure per trade
- Stop loss: 0.5% from entry
- Target: 0.75% from entry (1.5:1 R:R)
- Max 3 concurrent open positions
- Daily loss limit: halt trading if PnL < -₹5,000
"""
import math
from dataclasses import dataclass
from backend.config import (
    MAX_POSITION_EXPOSURE,
    INTRADAY_MARGIN_MULTIPLIER,
    MAX_CONCURRENT_POSITIONS,
    DAILY_LOSS_LIMIT,
    STOP_LOSS_PCT,
    TARGET_PCT,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeParams:
    symbol: str
    direction: str          # 'long' | 'short'
    entry_price: float
    stop_loss: float
    target: float
    quantity: int
    exposure: float         # entry_price * quantity


class RiskManager:
    def __init__(self):
        self.daily_pnl = 0.0
        self.trading_halted = False

    def reset_daily(self):
        """Called at 8:30 AM every trading day."""
        self.daily_pnl = 0.0
        self.trading_halted = False
        logger.info("Risk manager daily reset — trading active")

    def record_pnl(self, pnl: float):
        """Called when a trade closes. Updates daily PnL and checks loss limit."""
        self.daily_pnl += pnl
        logger.info(f"Daily PnL updated: ₹{self.daily_pnl:,.0f}")

        if self.daily_pnl <= DAILY_LOSS_LIMIT and not self.trading_halted:
            self.trading_halted = True
            logger.warning(
                f"DAILY LOSS LIMIT HIT: ₹{self.daily_pnl:,.0f} <= ₹{DAILY_LOSS_LIMIT:,.0f}. "
                f"Trading halted for today."
            )

    def compute_trade_params(self, symbol: str, direction: str, entry_price: float) -> TradeParams:
        """
        Given a symbol, direction, and entry price — compute all trade parameters.
        quantity = floor(MAX_EXPOSURE / entry_price)
        stop_loss = 0.5% from entry
        target = 0.75% from entry
        """
        quantity = math.floor(MAX_POSITION_EXPOSURE * INTRADAY_MARGIN_MULTIPLIER / entry_price)
        if quantity == 0:
            quantity = 1  # minimum 1 share

        exposure = entry_price * quantity

        if direction == "long":
            stop_loss = round(entry_price * (1 - STOP_LOSS_PCT), 2)
            target = round(entry_price * (1 + TARGET_PCT), 2)
        else:  # short
            stop_loss = round(entry_price * (1 + STOP_LOSS_PCT), 2)
            target = round(entry_price * (1 - TARGET_PCT), 2)

        return TradeParams(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            quantity=quantity,
            exposure=exposure,
        )

    def approve(self, symbol: str, direction: str, open_positions: list) -> tuple[bool, str]:
        """
        Final gate before any trade is placed.
        Returns (approved: bool, reason: str)
        """
        if self.trading_halted:
            return False, f"Daily loss limit hit (PnL: ₹{self.daily_pnl:,.0f})"

        if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
            return False, f"Max concurrent positions reached ({MAX_CONCURRENT_POSITIONS})"

        # No duplicate positions on same symbol
        open_symbols = [p["symbol"] for p in open_positions]
        if symbol in open_symbols:
            return False, f"Already have open position in {symbol}"

        return True, "approved"


# Singleton
_risk_manager = None

def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
