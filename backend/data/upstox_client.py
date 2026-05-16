"""
Upstox API client.
STUB_MODE is controlled by the STUB_MODE env variable (True/False).
When False, reads the access token from the DB (saved via /auth/callback).

Instruments traded: NIFTY and BANKNIFTY index futures (NSE_FO segment).
The near-month futures contract is resolved dynamically from the NSE_FO
instrument CSV published by Upstox, and cached for the trading day.
"""
import os
import gzip
import io
import csv
import requests as req
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from backend.config import UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI
from backend.utils.logger import get_logger

logger = get_logger(__name__)

STUB_MODE = os.getenv("STUB_MODE", "True").strip().lower() not in ("false", "0", "no")

# Realistic stub price ranges for index futures
_STUB_PRICES = {
    "NIFTY": (22000, 26000),
    "BANKNIFTY": (47000, 54000),
}
_STUB_PRICE_DEFAULT = (500, 3000)


def _build_futures_instrument_map(base_symbols: list) -> dict:
    """
    Download the NSE_FO instruments CSV from Upstox and return a dict mapping
    {base_symbol: near_month_instrument_key} for the given futures symbols.

    Near-month = the non-expired contract with the earliest expiry date.
    """
    try:
        # complete.csv.gz is publicly accessible and contains all exchanges including NSE_FO
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = req.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        today = date.today()
        # Collect all non-expired index futures contracts per base symbol
        candidates: dict[str, list] = {sym: [] for sym in base_symbols}

        with gzip.open(io.BytesIO(r.content), "rt") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("exchange") != "NSE_FO":
                    continue
                if row.get("instrument_type") != "FUTIDX":
                    continue
                name = row.get("name", "")
                if name not in candidates:
                    continue
                expiry_str = row.get("expiry", "")
                try:
                    expiry_date = date.fromisoformat(expiry_str)
                except ValueError:
                    continue
                if expiry_date < today:
                    continue  # skip expired contracts
                candidates[name].append((expiry_date, row["instrument_key"]))

        result = {}
        for symbol, contracts in candidates.items():
            if not contracts:
                logger.warning(f"No active futures contract found for {symbol}")
                continue
            contracts.sort(key=lambda x: x[0])  # nearest expiry first
            expiry, key = contracts[0]
            result[symbol] = key
            logger.info(f"Futures key resolved: {symbol} → {key} (expiry {expiry})")

        return result
    except Exception as e:
        logger.error(f"Failed to load futures instrument map: {e}")
        return {}


def _load_token_from_db() -> str | None:
    """Load the latest valid token from DB."""
    try:
        import pytz
        from backend.database.connection import SessionLocal
        from backend.database.models import UpstoxToken
        IST = pytz.timezone("Asia/Kolkata")
        db = SessionLocal()
        try:
            token = db.query(UpstoxToken).order_by(UpstoxToken.id.desc()).first()
            if token and token.expires_at.astimezone(IST) > datetime.now(IST):
                return token.access_token
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load token from DB: {e}")
    return None


class UpstoxClient:
    def __init__(self):
        self.access_token = None
        self._instrument_map: dict = {}      # {base_symbol: instrument_key}
        self._instrument_map_date: date | None = None
        if not STUB_MODE:
            self._load_token()
            self._refresh_instrument_map()

    def _load_token(self):
        token = _load_token_from_db()
        if token:
            self.access_token = token
            logger.info("Upstox token loaded from DB.")
        else:
            logger.warning(
                "No valid Upstox token found. Visit "
                "https://web-production-0db02.up.railway.app/auth/login to authenticate."
            )

    def _refresh_instrument_map(self):
        """Rebuild futures instrument map. Called at startup and once per trading day."""
        from backend.utils.constants import NIFTY50_SYMBOLS
        self._instrument_map = _build_futures_instrument_map(NIFTY50_SYMBOLS)
        self._instrument_map_date = date.today()

    def _get_instrument_key(self, symbol: str) -> str:
        """Return the live futures instrument key for a base symbol, refreshing daily."""
        if not STUB_MODE:
            if self._instrument_map_date != date.today():
                self._refresh_instrument_map()
        return self._instrument_map.get(symbol, f"NSE_FO|{symbol}")

    def reload_token(self, access_token: str):
        """Called after /callback saves a new token."""
        self.access_token = access_token
        self._refresh_instrument_map()
        logger.info("Upstox token reloaded in client.")

    def fetch_historical(
        self,
        symbol: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame:
        if STUB_MODE:
            return self._stub_historical(symbol, interval, from_date, to_date)

        if not self.access_token:
            raise RuntimeError("No Upstox token. Visit /auth/login to authenticate.")

        try:
            import upstox_client
            config = upstox_client.Configuration()
            config.access_token = self.access_token
            client = upstox_client.ApiClient(config)
            api = upstox_client.HistoryApi(client)

            instrument_key = self._get_instrument_key(symbol)
            # Upstox v2 dropped "5minute" — fetch 1min and resample
            api_interval = "1minute" if interval == "5minute" else interval
            response = api.get_historical_candle_data1(
                instrument_key=instrument_key,
                interval=api_interval,
                to_date=to_date,
                from_date=from_date,
                api_version="2.0",
            )
            candles = response.data.candles
            df = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume", "oi"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")

            if interval == "5minute":
                df = df.set_index("timestamp").resample("5min").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }).dropna().reset_index()

            logger.info(f"Fetched {len(df)} candles for {symbol} ({interval})")
            return df
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise

    def fetch_intraday(self, symbol: str, interval: str = "5minute") -> pd.DataFrame:
        """Fetch today's intraday candles using Upstox intraday endpoint."""
        if STUB_MODE:
            return self._stub_historical(symbol, interval,
                                         datetime.today().strftime("%Y-%m-%d"),
                                         datetime.today().strftime("%Y-%m-%d"))
        if not self.access_token:
            raise RuntimeError("No Upstox token. Visit /auth/login to authenticate.")
        try:
            import upstox_client
            config = upstox_client.Configuration()
            config.access_token = self.access_token
            client = upstox_client.ApiClient(config)
            api = upstox_client.HistoryApi(client)

            instrument_key = self._get_instrument_key(symbol)
            api_interval = "1minute" if interval == "5minute" else interval
            response = api.get_intra_day_candle_data(
                instrument_key=instrument_key,
                interval=api_interval,
                api_version="2.0",
            )
            candles = response.data.candles
            if not candles:
                logger.info(f"Fetched 0 intraday candles for {symbol}")
                return pd.DataFrame()

            df = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume", "oi"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")

            if interval == "5minute":
                df = df.set_index("timestamp").resample("5min").agg({
                    "open": "first", "high": "max",
                    "low": "min", "close": "last", "volume": "sum",
                }).dropna().reset_index()

            logger.info(f"Fetched {len(df)} intraday candles for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Failed to fetch intraday data for {symbol}: {e}")
            raise

    def fetch_ltp(self, symbol: str) -> float:
        if STUB_MODE:
            lo, hi = _STUB_PRICES.get(symbol, _STUB_PRICE_DEFAULT)
            return round(np.random.uniform(lo, hi), 2)

        if not self.access_token:
            raise RuntimeError("No Upstox token. Visit /auth/login to authenticate.")

        try:
            import upstox_client
            config = upstox_client.Configuration()
            config.access_token = self.access_token
            client = upstox_client.ApiClient(config)
            api = upstox_client.MarketQuoteApi(client)
            instrument_key = self._get_instrument_key(symbol)
            response = api.ltp(
                symbol=instrument_key,
                api_version="2.0",
            )
            return response.data[instrument_key].last_price
        except Exception as e:
            logger.error(f"Failed to fetch LTP for {symbol}: {e}")
            raise

    def _stub_historical(self, symbol, interval, from_date, to_date) -> pd.DataFrame:
        logger.warning(f"STUB MODE: returning fake data for {symbol} ({interval})")
        start = pd.Timestamp(from_date)
        end = pd.Timestamp(to_date)
        if interval == "5minute":
            timestamps = pd.date_range(start=start, end=end, freq="5min")
            timestamps = timestamps[
                (timestamps.time >= pd.Timestamp("09:15").time()) &
                (timestamps.time <= pd.Timestamp("15:30").time()) &
                (timestamps.dayofweek < 5)
            ]
        else:
            timestamps = pd.date_range(start=start, end=end, freq="B")
        n = len(timestamps)
        lo, hi = _STUB_PRICES.get(symbol, _STUB_PRICE_DEFAULT)
        base_price = np.random.uniform(lo, hi)
        returns = np.random.normal(0, 0.002, n)
        closes = base_price * np.exp(np.cumsum(returns))
        opens = closes * np.random.uniform(0.998, 1.002, n)
        highs = np.maximum(opens, closes) * np.random.uniform(1.001, 1.005, n)
        lows = np.minimum(opens, closes) * np.random.uniform(0.995, 0.999, n)
        volumes = np.random.uniform(100000, 5000000, n)
        return pd.DataFrame({
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })


# Singleton
_client = None


def get_upstox_client() -> UpstoxClient:
    global _client
    if _client is None:
        _client = UpstoxClient()
    return _client


def reload_token(access_token: str):
    """Called by /auth/callback to hot-reload the token without restart."""
    global _client
    if _client is None:
        _client = UpstoxClient()
    _client.reload_token(access_token)
