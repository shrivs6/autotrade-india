from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.scheduler import create_scheduler
from backend.api.routes.health import router as health_router
from backend.api.routes.dashboard import router as dashboard_router
from backend.api.routes.trades import router as trades_router
from backend.api.routes.performance import router as performance_router
from backend.utils.logger import get_logger

logger = get_logger(__name__)
scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AutoTrade India backend...")
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
    allow_origins=["*"],   # tighten to Vercel URL after deployment
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(trades_router)
app.include_router(performance_router)
