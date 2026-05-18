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
