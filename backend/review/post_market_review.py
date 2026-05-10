"""
Post-market review — runs at 3:45 PM after all positions are closed.
Analyses today's trades and saves a daily performance snapshot.
"""
from datetime import date, datetime
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade, ModelPerformance
from backend.trading.risk_manager import get_risk_manager
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def run_review() -> dict:
    """
    Analyses today's closed trades. Returns summary dict.
    """
    today = date.today()
    db = SessionLocal()

    try:
        trades = (
            db.query(Trade)
            .filter(Trade.status == "closed")
            .filter(Trade.trading_mode == "paper")
            .all()
        )

        # Filter to today's trades
        today_trades = [
            t for t in trades
            if t.exit_time and t.exit_time.astimezone(IST).date() == today
        ]

        total = len(today_trades)
        if total == 0:
            logger.info("Post-market review: no trades today")
            return {"total": 0}

        winners = [t for t in today_trades if t.pnl and t.pnl > 0]
        losers  = [t for t in today_trades if t.pnl and t.pnl <= 0]
        total_pnl = sum(t.pnl for t in today_trades if t.pnl)
        win_rate = len(winners) / total if total > 0 else 0

        # Exit reason breakdown
        reasons = {}
        for t in today_trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

        summary = {
            "date": today.isoformat(),
            "total_trades": total,
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 2),
            "exit_reasons": reasons,
        }

        logger.info(
            f"Post-market summary: {total} trades | "
            f"Win rate: {win_rate:.1%} | PnL: ₹{total_pnl:+,.0f}"
        )

        # Save daily performance snapshot
        existing = db.query(ModelPerformance).filter(ModelPerformance.date == today).first()
        if existing:
            existing.total_trades = total
            existing.winning_trades = len(winners)
            existing.win_rate = win_rate
            existing.total_pnl = total_pnl
        else:
            perf = ModelPerformance(
                date=today,
                total_trades=total,
                winning_trades=len(winners),
                win_rate=win_rate,
                total_pnl=total_pnl,
                model_version="rule_based_v1",
                trading_mode="paper",
            )
            db.add(perf)
        db.commit()

        return summary

    except Exception as e:
        logger.error(f"Post-market review failed: {e}")
        return {}
    finally:
        db.close()
