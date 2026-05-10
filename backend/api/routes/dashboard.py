from fastapi import APIRouter
from datetime import date, datetime, timedelta
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade, ModelPerformance, Lesson, MarketContext
from backend.trading.position_tracker import get_position_tracker
from backend.trading.risk_manager import get_risk_manager
from backend.ml.model_registry import get_production_version

router = APIRouter(prefix="/api/dashboard")
IST = pytz.timezone("Asia/Kolkata")


@router.get("/summary")
def get_summary():
    today = date.today()
    now = datetime.now(IST)
    db = SessionLocal()
    try:
        # Today's trades
        all_trades = db.query(Trade).filter(Trade.status == "closed").all()
        today_trades = [
            t for t in all_trades
            if t.exit_time and t.exit_time.astimezone(IST).date() == today
        ]
        today_pnl = sum(t.pnl for t in today_trades if t.pnl) or 0
        today_wins = sum(1 for t in today_trades if t.pnl and t.pnl > 0)
        today_wr = round(today_wins / len(today_trades), 4) if today_trades else 0

        # All-time win rate
        total = len(all_trades)
        all_wins = sum(1 for t in all_trades if t.pnl and t.pnl > 0)
        all_time_wr = round(all_wins / total, 4) if total > 0 else 0

        # Market status
        market_open = now.weekday() < 5 and (
            (now.hour == 9 and now.minute >= 15) or
            (10 <= now.hour <= 14) or
            (now.hour == 15 and now.minute < 20)
        )
        status = "TRADING" if market_open else "MARKET CLOSED"

        return {
            "date": today.isoformat(),
            "status": status,
            "today_pnl": round(today_pnl, 2),
            "today_trades": len(today_trades),
            "today_win_rate": today_wr,
            "all_time_win_rate": all_time_wr,
            "all_time_trades": total,
            "open_positions": get_position_tracker().count(),
            "daily_pnl_limit_hit": get_risk_manager().trading_halted,
            "model_version": get_production_version() or "none",
        }
    finally:
        db.close()


@router.get("/win-rate-history")
def get_win_rate_history(days: int = 90):
    cutoff = date.today() - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = (
            db.query(ModelPerformance)
            .filter(ModelPerformance.date >= cutoff)
            .order_by(ModelPerformance.date.asc())
            .all()
        )
        return [
            {
                "date": r.date.isoformat(),
                "win_rate": round(r.win_rate or 0, 4),
                "total_trades": r.total_trades or 0,
                "total_pnl": round(r.total_pnl or 0, 2),
            }
            for r in rows
        ]
    finally:
        db.close()


@router.get("/todays-trades")
def get_todays_trades():
    today = date.today()
    db = SessionLocal()
    try:
        all_trades = db.query(Trade).filter(Trade.status == "closed").all()
        today_trades = [
            t for t in all_trades
            if t.exit_time and t.exit_time.astimezone(IST).date() == today
        ]
        today_trades.sort(key=lambda t: t.entry_time)

        result = []
        for t in today_trades:
            win = t.pnl and t.pnl > 0
            duration_min = 0
            if t.entry_time and t.exit_time:
                duration_min = int((t.exit_time - t.entry_time).seconds / 60)

            result.append({
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_time": t.entry_time.astimezone(IST).strftime("%H:%M") if t.entry_time else None,
                "exit_time": t.exit_time.astimezone(IST).strftime("%H:%M") if t.exit_time else None,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "exposure": round((t.entry_price or 0) * (t.quantity or 0), 2),
                "pnl": round(t.pnl or 0, 2),
                "result": "WIN" if win else "LOSS",
                "exit_reason": t.exit_reason,
                "duration_min": duration_min,
                "description": _describe_trade(t, duration_min),
            })
        return result
    finally:
        db.close()


def _describe_trade(trade, duration_min: int) -> str:
    direction = "Long" if trade.direction == "long" else "Short"
    result = "hit target" if trade.exit_reason == "target_hit" else \
             "hit stop loss" if trade.exit_reason == "stop_hit" else "closed at end of day"
    pnl_str = f"₹{abs(trade.pnl or 0):,.0f} {'profit' if (trade.pnl or 0) > 0 else 'loss'}"
    return f"{direction} trade {result} after {duration_min} min — {pnl_str}."


@router.get("/lessons")
def get_lessons(days: int = 1):
    cutoff = date.today() - timedelta(days=days - 1)
    db = SessionLocal()
    try:
        rows = (
            db.query(Lesson)
            .filter(Lesson.date >= cutoff)
            .order_by(Lesson.created_at.desc())
            .all()
        )
        return [
            {
                "date": r.date.isoformat(),
                "lesson": r.lesson_text,
                "conditions": r.conditions,
            }
            for r in rows
        ]
    finally:
        db.close()
