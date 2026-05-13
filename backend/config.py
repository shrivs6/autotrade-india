from dotenv import load_dotenv
import os

load_dotenv()

UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

DATABASE_URL = os.getenv("DATABASE_URL", "")

# paper | live | disabled
TRADING_MODE = os.getenv("TRADING_MODE", "paper")

ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")

# Risk parameters
MAX_POSITION_EXPOSURE = 100000   # ₹1,00,000 capital per trade
INTRADAY_MARGIN_MULTIPLIER = 5   # 5x MIS margin (SEBI standard for intraday)
MAX_CONCURRENT_POSITIONS = 3
DAILY_LOSS_LIMIT = -5000         # halt trading if PnL drops below this
STOP_LOSS_PCT = 0.005            # 0.5%
TARGET_PCT = 0.0075              # 0.75%

# Market hours (IST, 24h)
MARKET_OPEN = "09:15"
TRADING_START = "09:30"
TRADING_END = "14:00"            # no new entries after 2pm
SQUARE_OFF_TIME = "15:20"        # force close all positions
