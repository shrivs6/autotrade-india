from fastapi import APIRouter
from datetime import datetime
import pytz

router = APIRouter()
IST = pytz.timezone("Asia/Kolkata")

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "time_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }
