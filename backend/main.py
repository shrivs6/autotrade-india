from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.scheduler import create_scheduler
from backend.database.connection import engine
from backend.database.models import Base
from backend.api.routes.health import router as health_router
from backend.api.routes.dashboard import router as dashboard_router
from backend.api.routes.trades import router as trades_router
from backend.api.routes.performance import router as performance_router
from backend.api.routes.history import router as history_router
from backend.api.routes.auth import router as auth_router
from backend.utils.logger import get_logger

logger = get_logger(__name__)
scheduler = create_scheduler()


def _restore_open_positions():
    """On startup, reload any open positions from DB into the in-memory tracker.
    This prevents monitor_positions from skipping stop/target checks after a container restart."""
    try:
        from backend.database.connection import SessionLocal
        from backend.database.models import Trade
        from backend.trading.position_tracker import get_position_tracker
        db = SessionLocal()
        try:
            open_trades = db.query(Trade).filter(Trade.status == "open").all()
        finally:
            db.close()
        if not open_trades:
            return
        tracker = get_position_tracker()
        for t in open_trades:
            tracker.add(
                trade_id=t.id,
                symbol=t.symbol,
                direction=t.direction,
                entry_price=t.entry_price,
                stop_loss=t.stop_loss,
                target=t.target,
                quantity=t.quantity,
            )
        logger.info(f"Startup: restored {len(open_trades)} open position(s) into tracker")
    except Exception as e:
        logger.error(f"Startup position restore failed: {e}")


def _startup_square_off():
    """If server restarts after 3:20pm on a weekday, close any positions that were missed."""
    from datetime import datetime
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return  # weekend
    market_closed = now.hour > 15 or (now.hour == 15 and now.minute >= 0)
    if not market_closed:
        return
    try:
        from backend.trading.order_manager import square_off_all
        from backend.database.connection import SessionLocal
        from backend.database.models import Trade
        db = SessionLocal()
        try:
            count = db.query(Trade).filter(Trade.status == "open").count()
        finally:
            db.close()
        if count > 0:
            logger.warning(f"Startup: found {count} open position(s) after market close — squaring off")
            square_off_all()
    except Exception as e:
        logger.error(f"Startup square-off failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AutoTrade India backend...")
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("DB tables verified.")
    _restore_open_positions()
    _startup_square_off()
    scheduler.start()
    logger.info("Scheduler started. Jobs registered:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.id}: next run {job.next_run_time}")
    yield
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()


app = FastAPI(title="AutoTrade India", lifespan=lifespan)

# Allow React frontend (Vercel) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(trades_router)
app.include_router(performance_router)
app.include_router(history_router)
app.include_router(auth_router)

# Root-level /callback so Upstox redirect URI matches
from backend.api.routes.auth import callback as _auth_callback
app.add_api_route("/callback", _auth_callback, methods=["GET"])
