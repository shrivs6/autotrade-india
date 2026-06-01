"""
Fetches free public data from NSE India:
- India VIX
- FII net buy/sell data
No API key required — uses public NSE endpoints with browser-like headers.
"""
import requests
import time
from backend.utils.logger import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}


def _make_session() -> requests.Session:
    """Create a fresh NSE session by visiting the homepage to get cookies."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=15)
        time.sleep(0.5)  # brief pause after homepage — NSE rate limits aggressive clients
    except Exception:
        pass
    return session


def _fetch_with_retry(url: str) -> dict | list | None:
    """Fetch NSE API URL, retrying once with a fresh session on failure."""
    for attempt in range(2):
        try:
            session = _make_session()
            response = session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt == 0:
                logger.warning(f"NSE fetch attempt 1 failed ({e}), retrying with fresh session...")
                time.sleep(2)
            else:
                logger.error(f"NSE fetch failed after 2 attempts: {e}")
    return None


def fetch_vix() -> float | None:
    """Returns current India VIX value."""
    data = _fetch_with_retry("https://www.nseindia.com/api/allIndices")
    if not data:
        return None
    for index in data.get("data", []):
        if index.get("index") == "INDIA VIX":
            vix = float(index["last"])
            logger.info(f"India VIX: {vix}")
            return vix
    logger.warning("VIX not found in NSE response")
    return None


def fetch_fii_data() -> dict | None:
    """
    Returns FII net buy/sell in crores for the latest available date.
    Returns dict: { 'date': str, 'fii_net_crores': float }
    """
    data = _fetch_with_retry("https://www.nseindia.com/api/fiidiiTradeReact")
    if not data:
        return None
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
