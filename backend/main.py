from fastapi import FastAPI
from contextlib import asynccontextmanager
from backend.scheduler import create_scheduler
from backend.api.routes.health import router as health_router
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
app.include_router(health_router)
