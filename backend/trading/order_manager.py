"""
Order manager — controls the full lifecycle of a trade:
  open → monitor (stop loss / target check) → close

Called by the scheduler every 5 minutes during trading hours.
"""
from datetime import datetime, timedelta
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

# Per-symbol stop-loss cooldown: symbol → datetime until which re-entry is blocked.
# Prevents re-entering the same symbol immediately after a stop-loss exit,
# which caused a loss-ladder pattern in choppy/reversing markets.
_stop_cooldowns: dict[str, datetime] = {}
STOP_COOLDOWN_MINUTES = 60


def _is_in_cooldown(symbol: str) -> bool:
    """Returns True if the symbol is still within its post-stop-loss cooldown window."""
    until = _stop_cooldowns.get(symbol)
    if until is None:
        return False
    if datetime.now(IST) >= until:
        _stop_cooldowns.pop(symbol, None)
        return False
    return True


def _set_cooldown(symbol: str):
    """Starts a 60-minute re-entry block for the symbol after a stop-loss."""
    _stop_cooldowns[symbol] = datetime.now(IST) + timedelta(minutes=STOP_COOLDOWN_MINUTES)
    logger.info(f"{symbol}: stop-loss cooldown set — no new entries for {STOP_COOLDOWN_MINUTES} min")


def open_trade(features: dict, direction: str, signal_id: int | None = None, confidence: float | None = None) -> bool:
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

    # Cooldown gate — block re-entry after a stop-loss for 60 minutes
    if _is_in_cooldown(symbol):
        until = _stop_cooldowns[symbol].strftime("%H:%M")
        logger.info(f"{symbol}: trade rejected — in stop-loss cooldown until {until} IST")
        return False

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
        # Resolve full contract name (e.g. NIFTY26MAYFUT) for display
        contract = symbol
        try:
            from backend.data.upstox_client import get_upstox_client
            contract = get_upstox_client().get_contract_name(symbol)
        except Exception:
            pass

        trade = Trade(
            symbol=symbol,
            contract=contract,
            direction=direction,
            entry_price=float(fill_price),
            stop_loss=float(params.stop_loss),
            target=float(params.target),
            quantity=int(params.quantity),
            exposure=float(params.exposure),
            entry_time=datetime.now(IST),
            trading_mode="paper",
            status="open",
            signal_confidence=float(confidence) if confidence is not None else None,
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


def monitor_positions(current_prices: dict[str, float],
                      candle_highs: dict[str, float] | None = None,
                      candle_lows: dict[str, float] | None = None):
    """
    Called every 5 minutes. Checks if any open position has hit stop loss or target.

    Uses candle high/low to detect intraday touches — matching how the model was trained.
    Falls back to close price if high/low not available.

    current_prices: { 'NIFTY': 24050.0, ... }  — used as exit price when SL/target triggered
    candle_highs:   { 'NIFTY': 24120.0, ... }  — candle high for target detection (long) / SL (short)
    candle_lows:    { 'NIFTY': 23980.0, ... }  — candle low for SL detection (long) / target (short)
    """
    tracker = get_position_tracker()
    risk = get_risk_manager()

    candle_highs = candle_highs or {}
    candle_lows = candle_lows or {}

    for position in tracker.get_all():
        symbol = position["symbol"]
        close = current_prices.get(symbol)

        if close is None:
            continue

        direction = position["direction"]
        stop_loss = position["stop_loss"]
        target = position["target"]

        # Use candle high/low where available — matches training label logic.
        # Fall back to close price if high/low missing.
        high = candle_highs.get(symbol, close)
        low = candle_lows.get(symbol, close)

        exit_reason = None
        exit_price = close

        if direction == "long":
            if low <= stop_loss:
                exit_reason = "stop_hit"
                exit_price = stop_loss  # exit at SL level, not close
            elif high >= target:
                exit_reason = "target_hit"
                exit_price = target  # exit at target level, not close
        else:  # short
            if high >= stop_loss:
                exit_reason = "stop_hit"
                exit_price = stop_loss
            elif low <= target:
                exit_reason = "target_hit"
                exit_price = target

        if exit_reason:
            close_trade(position["trade_id"], exit_price, exit_reason)


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

        # After a stop-loss, block re-entry for 60 minutes to prevent loss-ladder whipsawing
        if exit_reason == "stop_hit":
            _set_cooldown(symbol)

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
    from backend.database.models import OHLCV5Min
    client = get_upstox_client()

    for trade in open_trades:
        ltp = None
        try:
            ltp = client.fetch_ltp(trade.symbol)
        except Exception as e:
            logger.warning(f"fetch_ltp failed for {trade.symbol}: {e} — trying last candle price")

        if ltp is None:
            # Fallback: use last known candle close from DB (~2:55 PM price)
            try:
                db2 = SessionLocal()
                try:
                    last = (
                        db2.query(OHLCV5Min)
                        .filter(OHLCV5Min.symbol == trade.symbol)
                        .order_by(OHLCV5Min.timestamp.desc())
                        .first()
                    )
                    if last:
                        ltp = last.close
                        logger.info(f"{trade.symbol}: using last candle price ₹{ltp} for square-off")
                finally:
                    db2.close()
            except Exception as e2:
                logger.warning(f"Last candle lookup failed for {trade.symbol}: {e2}")

        if ltp is None:
            ltp = trade.entry_price
            logger.warning(f"{trade.symbol}: no price available — squaring off at entry price ₹{ltp}")

        close_trade(trade.id, ltp, "eod_squareoff")
