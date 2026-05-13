"""
One-time script to close stale open positions that were stuck due to the
in-memory tracker being wiped on server restarts before the DB-based fix.

For each open trade, uses the last available 5-min candle close as exit price
so PnL is realistic. Falls back to entry price (0 PnL) if no candle found.

Run once on Railway shell or locally with prod DB:
    python -m backend.scripts.cleanup_stale_positions
"""
from datetime import datetime, date
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade, OHLCV5Min
from backend.paper_trading.pnl_calculator import calc_pnl
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def run():
    db = SessionLocal()
    try:
        open_trades = db.query(Trade).filter(Trade.status == "open").all()

        if not open_trades:
            print("No stale open positions found.")
            return

        print(f"Found {len(open_trades)} stale open position(s) to close.\n")

        closed = 0
        for trade in open_trades:
            # Try to get last 5-min candle close for this symbol today
            last_candle = (
                db.query(OHLCV5Min)
                .filter(
                    OHLCV5Min.symbol == trade.symbol,
                    OHLCV5Min.timestamp >= datetime.combine(date.today(), datetime.min.time()),
                )
                .order_by(OHLCV5Min.timestamp.desc())
                .first()
            )

            if last_candle:
                exit_price = last_candle.close
                price_source = f"last candle @ {last_candle.timestamp.astimezone(IST).strftime('%H:%M')}"
            else:
                exit_price = trade.entry_price
                price_source = "entry price (no candle found, PnL=0)"

            pnl = calc_pnl(trade.direction, trade.entry_price, exit_price, trade.quantity)

            trade.exit_price = exit_price
            trade.exit_time = datetime.now(IST)
            trade.exit_reason = "stale_cleanup"
            trade.pnl = pnl
            trade.status = "closed"

            result = "WIN" if pnl > 0 else "LOSS"
            print(
                f"  Closed #{trade.id}: {trade.direction.upper()} {trade.symbol} "
                f"entry ₹{trade.entry_price} → exit ₹{exit_price:.2f} "
                f"({price_source}) | PnL ₹{pnl:+,.0f} [{result}]"
            )
            closed += 1

        db.commit()
        print(f"\nDone. {closed} position(s) closed.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
