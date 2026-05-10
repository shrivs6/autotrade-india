"""
Calculates PnL for trades.
"""


def calc_pnl(direction: str, entry_price: float, exit_price: float, quantity: int) -> float:
    """
    Returns realized PnL in rupees.
    Long:  (exit - entry) * qty
    Short: (entry - exit) * qty
    """
    if direction == "long":
        return round((exit_price - entry_price) * quantity, 2)
    else:
        return round((entry_price - exit_price) * quantity, 2)


def calc_unrealized_pnl(direction: str, entry_price: float, current_price: float, quantity: int) -> float:
    """Returns unrealized PnL for an open position."""
    return calc_pnl(direction, entry_price, current_price, quantity)
