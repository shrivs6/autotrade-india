from fastapi import APIRouter
from datetime import date, timedelta
import pytz
from backend.database.connection import SessionLocal
from backend.database.models import Trade

router = APIRouter(prefix="/api/trades")
IST = pytz.timezone("Asia/Kolkata")


@router.get("/open")
def get_open_trades():
    db = SessionLocal()
    try:
        trades = (
            db.query(Trade)
            .filter(Trade.status == "open")
            .order_by(Trade.entry_time.asc())
            .all()
        )
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "contract": t.contract or t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "stop_loss": t.stop_loss,
                "target": t.target,
                "quantity": t.quantity,
                "exposure": t.exposure,
                "entry_time": t.entry_time.astimezone(IST).strftime("%H:%M") if t.entry_time else None,
                "confidence": round(t.signal_confidence * 100, 1) if t.signal_confidence else None,
            }
            for t in trades
        ]
    finally:
        db.close()


@router.get("/recent")
def get_recent_trades(days: int = 7):
    cutoff = date.today() - timedelta(days=days)
    db = SessionLocal()
    try:
        trades = (
            db.query(Trade)
            .filter(Trade.status == "closed")
            .filter(Trade.entry_time >= str(cutoff))
            .order_by(Trade.entry_time.desc())
            .limit(100)
            .all()
        )
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": round(t.pnl or 0, 2),
                "exit_reason": t.exit_reason,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "trading_mode": t.trading_mode,
            }
            for t in trades
        ]
    finally:
        db.close()
