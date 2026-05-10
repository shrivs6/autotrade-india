from fastapi import APIRouter
from datetime import date, timedelta
from backend.database.connection import SessionLocal
from backend.database.models import ModelPerformance, Trade

router = APIRouter(prefix="/api/performance")


@router.get("/stats")
def get_stats():
    db = SessionLocal()
    try:
        all_trades = db.query(Trade).filter(Trade.status == "closed").all()
        if not all_trades:
            return {"message": "No trades yet"}

        total = len(all_trades)
        wins = sum(1 for t in all_trades if t.pnl and t.pnl > 0)
        total_pnl = sum(t.pnl for t in all_trades if t.pnl)
        avg_win = sum(t.pnl for t in all_trades if t.pnl and t.pnl > 0) / max(wins, 1)
        avg_loss = sum(t.pnl for t in all_trades if t.pnl and t.pnl <= 0) / max(total - wins, 1)

        # Last 30 days
        cutoff_30 = date.today() - timedelta(days=30)
        recent = [
            t for t in all_trades
            if t.entry_time and t.entry_time.date() >= cutoff_30
        ]
        recent_wr = sum(1 for t in recent if t.pnl and t.pnl > 0) / max(len(recent), 1)

        return {
            "total_trades": total,
            "win_rate": round(wins / total, 4),
            "win_rate_last_30d": round(recent_wr, 4),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
        }
    finally:
        db.close()
