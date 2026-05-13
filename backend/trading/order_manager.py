"""
Order manager — controls the full lifecycle of a trade:
  open → monitor (stop loss / target check) → close

Called by the scheduler every 5 minutes during trading hours.
"""
from datetime import datetime
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade, TradeSignal
from backend.trading.risk_manager import get_risk_manager
from backend.trading.position_tracker import get_position_tracker
from backend.paper_trading.paper_broker import get_broker
from backend.paper_trading.pnl_calculator import calc_pnl
from backend.utils.type_utils import to_python
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def open_trade(features: dict, direction: str, signal_id: int | None = None) -> bool:
    """
    Attempts to open a new trade.
    Returns True if trade was placed, False if rejected.
    """
    symbol = features["symbol"]
    entry_price = features.get("close_price")

    if not entry_price:
        logger.warning(f"{symbol}: no close_price in features — cannot open trade")
        return False

    risk = get_risk_manager()
    tracker = get_position_tracker()

    # Risk gate — read open positions from DB so duplicate check survives server restarts
    db_check = SessionLocal()
    try:
        db_open = db_check.query(Trade).filter(Trade.status == "open").all()
        db_positions = [{"symbol": t.symbol} for t in db_open]
    finally:
        db_check.close()

    approved, reason = risk.approve(symbol, direction, db_positions)
    if not approved:
        logger.info(f"{symbol}: trade rejected — {reason}")
        return False

    # Compute trade parameters
    params = risk.compute_trade_params(symbol, direction, entry_price)

    # Place order via broker (paper or live)
    broker = get_broker()
    order = broker.place_order(symbol, direction, params.quantity, params.entry_price)

    if order["status"] != "filled":
        logger.error(f"{symbol}: order not filled — {order}")
        return False

    fill_price = float(order["fill_price"])

    # Recalculate params at actual fill price (may differ slightly in live mode)
    params = risk.compute_trade_params(symbol, direction, fill_price)

    db = SessionLocal()
    try:
        trade = Trade(
            symbol=symbol,
            direction=direction,
            entry_price=float(fill_price),
            stop_loss=float(params.stop_loss),
            target=float(params.target),
            quantity=int(params.quantity),
            exposure=float(params.exposure),
            entry_time=datetime.now(IST),
            trading_mode="paper",
            status="open",
        )
        db.add(trade)
        db.flush()  # get trade.id before commit

        # Mark signal as trade taken
        if signal_id:
            signal = db.query(TradeSignal).filter(TradeSignal.id == signal_id).first()
            if signal:
                signal.trade_taken = True
                signal.trade_id = trade.id

        db.commit()

        # Track in memory
        tracker.add(
            trade_id=trade.id,
            symbol=symbol,
            direction=direction,
            entry_price=fill_price,
            stop_loss=params.stop_loss,
            target=params.target,
            quantity=params.quantity,
        )

        logger.info(
            f"TRADE OPENED #{trade.id}: {direction.upper()} {symbol} "
            f"@ ₹{fill_price} | SL ₹{params.stop_loss} | Target ₹{params.target}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to save trade for {symbol}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def monitor_positions(current_prices: dict[str, float]):
    """
    Called every 5 minutes. Checks if any open position has hit stop loss or target.
    current_prices: { 'RELIANCE': 2450.5, 'TCS': 3200.0, ... }
    """
    tracker = get_position_tracker()
    risk = get_risk_manager()

    for position in tracker.get_all():
        symbol = position["symbol"]
        price = current_prices.get(symbol)

        if price is None:
            continue

        direction = position["direction"]
        stop_loss = position["stop_loss"]
        target = position["target"]

        exit_reason = None

        if direction == "long":
            if price <= stop_loss:
                exit_reason = "stop_hit"
            elif price >= target:
                exit_reason = "target_hit"
        else:  # short
            if price >= stop_loss:
                exit_reason = "stop_hit"
            elif price <= target:
                exit_reason = "target_hit"

        if exit_reason:
            close_trade(position["trade_id"], price, exit_reason)


def close_trade(trade_id: int, exit_price: float, exit_reason: str):
    """Closes a trade — updates DB, removes from tracker, records PnL."""
    tracker = get_position_tracker()
    risk = get_risk_manager()
    position = tracker.get(trade_id)

    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        if not trade:
            logger.warning(f"close_trade: trade_id {trade_id} not found in DB")
            return

        # Fall back to DB values if not in memory tracker (e.g. after server restart)
        direction = position["direction"] if position else trade.direction
        entry_price = position["entry_price"] if position else trade.entry_price
        quantity = position["quantity"] if position else trade.quantity
        symbol = position["symbol"] if position else trade.symbol

        pnl = calc_pnl(direction, entry_price, exit_price, quantity)

        trade.exit_price = exit_price
        trade.exit_time = datetime.now(IST)
        trade.exit_reason = exit_reason
        trade.pnl = pnl
        trade.status = "closed"
        db.commit()

        tracker.remove(trade_id)
        risk.record_pnl(pnl)

        result = "WIN" if pnl > 0 else "LOSS"
        logger.info(
            f"TRADE CLOSED #{trade_id}: {symbol} | {exit_reason} | "
            f"₹{exit_price} | PnL: ₹{pnl:+,.0f} [{result}]"
        )

    except Exception as e:
        logger.error(f"Failed to close trade {trade_id}: {e}")
        db.rollback()
    finally:
        db.close()


def square_off_all():
    """
    Called at 3:20 PM — force closes all open positions at current market price.
    Reads from DB so it works correctly even after a server restart.
    """
    db = SessionLocal()
    try:
        open_trades = db.query(Trade).filter(Trade.status == "open").all()
    finally:
        db.close()

    if not open_trades:
        logger.info("Square off: no open positions")
        return

    logger.info(f"Square off: closing {len(open_trades)} open position(s)")

    from backend.data.upstox_client import get_upstox_client
    client = get_upstox_client()

    for trade in open_trades:
        try:
            ltp = client.fetch_ltp(trade.symbol)
            close_trade(trade.id, ltp, "eod_squareoff")
        except Exception as e:
            logger.error(f"Failed to square off {trade.symbol}: {e}")
