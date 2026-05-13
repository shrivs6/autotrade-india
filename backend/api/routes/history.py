from fastapi import APIRouter, BackgroundTasks
from datetime import date, timedelta, datetime
from collections import defaultdict
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade, OHLCV5Min
from backend.paper_trading.pnl_calculator import calc_pnl

router = APIRouter(prefix="/api/history")
IST = pytz.timezone("Asia/Kolkata")


@router.get("/daily")
def get_daily_summary(days: int = 30):
    db = SessionLocal()
    try:
        if days == 0:
            trades = db.query(Trade).filter(Trade.status == "closed").all()
        else:
            cutoff = date.today() - timedelta(days=days)
            trades = (
                db.query(Trade)
                .filter(Trade.status == "closed")
                .filter(Trade.exit_time >= str(cutoff))
                .all()
            )

        # Group by exit date in IST
        by_date = defaultdict(list)
        for t in trades:
            if t.exit_time:
                d = t.exit_time.astimezone(IST).date()
                by_date[d].append(t)

        rows = []
        cumulative = 0.0
        for d in sorted(by_date.keys()):
            day_trades = by_date[d]
            wins = sum(1 for t in day_trades if t.pnl and t.pnl > 0)
            pnl = sum(t.pnl for t in day_trades if t.pnl)
            cumulative += pnl
            rows.append({
                "date": d.isoformat(),
                "trades": len(day_trades),
                "wins": wins,
                "win_rate": round(wins / len(day_trades), 4) if day_trades else 0,
                "pnl": round(pnl, 2),
                "cumulative_pnl": round(cumulative, 2),
            })

        return rows
    finally:
        db.close()


@router.post("/admin/retrain")
def trigger_retrain(background_tasks: BackgroundTasks):
    """Manually trigger nightly retrain. Runs in background — check Railway logs for progress."""
    from backend.ml.incremental_trainer import run_incremental_retrain
    background_tasks.add_task(run_incremental_retrain)
    return {"status": "retrain started — check Railway logs"}


@router.post("/admin/cleanup-stale")
def cleanup_stale_positions():
    """Close any trades stuck in 'open' status due to server restarts. Safe to call multiple times."""
    db = SessionLocal()
    try:
        open_trades = db.query(Trade).filter(Trade.status == "open").all()
        if not open_trades:
            return {"status": "nothing to clean", "closed": 0}

        results = []
        for trade in open_trades:
            last_candle = (
                db.query(OHLCV5Min)
                .filter(
                    OHLCV5Min.symbol == trade.symbol,
                    OHLCV5Min.timestamp >= datetime.combine(date.today(), datetime.min.time()),
                )
                .order_by(OHLCV5Min.timestamp.desc())
                .first()
            )
            exit_price = last_candle.close if last_candle else trade.entry_price
            pnl = calc_pnl(trade.direction, trade.entry_price, exit_price, trade.quantity)

            trade.exit_price = exit_price
            trade.exit_time = datetime.now(IST)
            trade.exit_reason = "stale_cleanup"
            trade.pnl = round(pnl, 2)
            trade.status = "closed"

            results.append({
                "id": trade.id,
                "symbol": trade.symbol,
                "direction": trade.direction,
                "pnl": round(pnl, 2),
            })

        db.commit()
        return {"status": "done", "closed": len(results), "trades": results}
    except Exception as e:
        db.rollback()
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()
