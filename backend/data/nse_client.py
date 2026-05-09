"""
Fetches free public data from NSE India:
- India VIX
- FII net buy/sell data
No API key required — uses public NSE endpoints with browser-like headers.
"""
import requests
from backend.utils.logger import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

SESSION = None

def _get_session() -> requests.Session:
    """NSE requires a session cookie — visit homepage first."""
    global SESSION
    if SESSION is None:
        SESSION = requests.Session()
        SESSION.headers.update(HEADERS)
        SESSION.get("https://www.nseindia.com", timeout=10)
    return SESSION


def fetch_vix() -> float | None:
    """Returns current India VIX value."""
    try:
        session = _get_session()
        response = session.get(
            "https://www.nseindia.com/api/allIndices",
            timeout=10
        )
        data = response.json()
        for index in data.get("data", []):
            if index.get("index") == "INDIA VIX":
                vix = float(index["last"])
                logger.info(f"India VIX: {vix}")
                return vix
        logger.warning("VIX not found in NSE response")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch VIX: {e}")
        return None


def fetch_fii_data() -> dict | None:
    """
    Returns FII net buy/sell in crores for the latest available date.
    Returns dict: { 'date': str, 'fii_net_crores': float }
    """
    try:
        session = _get_session()
        response = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            timeout=10
        )
        data = response.json()
        # Data is a list, first item is most recent
        if data:
            latest = data[0]
            fii_net = float(latest.get("netVal", 0))
            result = {
                "date": latest.get("date", ""),
                "fii_net_crores": fii_net
            }
            logger.info(f"FII net: ₹{fii_net:.0f} crores on {result['date']}")
            return result
        return None
    except Exception as e:
        logger.error(f"Failed to fetch FII data: {e}")
        return None
