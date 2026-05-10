from fastapi import APIRouter
from datetime import date, timedelta
from collections import defaultdict
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade

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
