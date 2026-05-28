NIFTY50_SYMBOLS = ["NIFTY", "BANKNIFTY"]

# NSE exchange segment for Upstox — NSE_FO for index futures
NSE_SEGMENT = "NSE_FO"

# Lot sizes per futures instrument (SEBI-mandated contract sizes)
LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
}

# Candle intervals
INTERVAL_5MIN = "5minute"
INTERVAL_DAY = "1day"

# NSE trading holidays 2026 — update each December for the following year
# Source: https://www.nseindia.com/resources/exchange-communication-holidays
from datetime import date
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 17),   # Holi
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Id-Ul-Adha (Bakri Id)
    date(2026, 8, 15),   # Independence Day
    date(2026, 8, 27),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 22),  # Diwali (Laxmi Pujan)
    date(2026, 10, 23),  # Diwali (Balipratipada)
    date(2026, 11, 4),   # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}


def is_market_holiday(d: date = None) -> bool:
    """Returns True if the given date (default today) is an NSE trading holiday."""
    if d is None:
        d = date.today()
    return d in NSE_HOLIDAYS_2026
