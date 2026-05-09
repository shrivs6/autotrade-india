"""
Upstox API client.
Currently STUBBED — returns dummy data until real API key is available.
Replace STUB_MODE = True with False once Upstox KYC is approved and API key is set.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.config import UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Flip to False once real Upstox API key is available
STUB_MODE = True


class UpstoxClient:
    def __init__(self):
        self.access_token = None
        if not STUB_MODE:
            self._authenticate()

    def _authenticate(self):
        """OAuth 2.0 flow — opens browser on first run, refreshes token daily after that."""
        try:
            import upstox_client
            config = upstox_client.Configuration()
            config.access_token = self._get_or_refresh_token()
            self.access_token = config.access_token
            logger.info("Upstox authenticated successfully")
        except Exception as e:
            logger.error(f"Upstox authentication failed: {e}")
            raise

    def _get_or_refresh_token(self) -> str:
        """
        Handles the OAuth token flow.
        On first run: opens browser for user login, saves token locally.
        On subsequent runs: reads saved token, refreshes if expired.
        """
        import upstox_client
        from upstox_client.rest import ApiException

        auth_api = upstox_client.LoginApi()
        token_path = ".upstox_token"

        import os, json
        if os.path.exists(token_path):
            with open(token_path) as f:
                saved = json.load(f)
            # Token expires daily — check if still valid
            if datetime.fromisoformat(saved["expires_at"]) > datetime.now():
                logger.info("Using saved Upstox token")
                return saved["access_token"]

        # Need fresh token — start OAuth flow
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code&client_id={UPSTOX_API_KEY}"
            f"&redirect_uri={UPSTOX_REDIRECT_URI}"
        )
        logger.info(f"Open this URL in browser to authorize: {auth_url}")
        auth_code = input("Paste the authorization code from the redirect URL: ").strip()

        response = auth_api.token(
            code=auth_code,
            client_id=UPSTOX_API_KEY,
            client_secret=UPSTOX_API_SECRET,
            redirect_uri=UPSTOX_REDIRECT_URI,
            grant_type="authorization_code"
        )

        token_data = {
            "access_token": response.access_token,
            "expires_at": (datetime.now() + timedelta(hours=23)).isoformat()
        }
        with open(token_path, "w") as f:
            json.dump(token_data, f)

        logger.info("New Upstox token obtained and saved")
        return response.access_token

    def fetch_historical(
        self,
        symbol: str,
        interval: str,
        from_date: str,
        to_date: str
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles for a symbol.
        interval: '5minute' | '1day'
        from_date / to_date: 'YYYY-MM-DD'
        Returns DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if STUB_MODE:
            return self._stub_historical(symbol, interval, from_date, to_date)

        try:
            import upstox_client
            api = upstox_client.HistoryApi()
            response = api.get_historical_candle_data1(
                instrument_key=f"NSE_EQ|{symbol}",
                interval=interval,
                to_date=to_date,
                from_date=from_date,
                api_version="2.0"
            )
            candles = response.data.candles
            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")
            logger.info(f"Fetched {len(df)} candles for {symbol} ({interval})")
            return df
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise

    def fetch_ltp(self, symbol: str) -> float:
        """Fetch last traded price for a symbol."""
        if STUB_MODE:
            return round(np.random.uniform(500, 3000), 2)

        try:
            import upstox_client
            api = upstox_client.MarketQuoteApi()
            response = api.ltp(
                symbol=f"NSE_EQ|{symbol}",
                api_version="2.0"
            )
            return response.data[f"NSE_EQ:{symbol}"].last_price
        except Exception as e:
            logger.error(f"Failed to fetch LTP for {symbol}: {e}")
            raise

    def _stub_historical(self, symbol: str, interval: str, from_date: str, to_date: str) -> pd.DataFrame:
        """Generates realistic-looking fake OHLCV data for development."""
        logger.warning(f"STUB MODE: returning fake data for {symbol} ({interval})")

        start = pd.Timestamp(from_date)
        end = pd.Timestamp(to_date)

        if interval == "5minute":
            timestamps = pd.date_range(start=start, end=end, freq="5min")
            # Filter to market hours only (9:15 to 15:30)
            timestamps = timestamps[
                (timestamps.time >= pd.Timestamp("09:15").time()) &
                (timestamps.time <= pd.Timestamp("15:30").time()) &
                (timestamps.dayofweek < 5)
            ]
        else:
            timestamps = pd.date_range(start=start, end=end, freq="B")

        n = len(timestamps)
        base_price = np.random.uniform(500, 3000)
        returns = np.random.normal(0, 0.002, n)
        closes = base_price * np.exp(np.cumsum(returns))
        opens = closes * np.random.uniform(0.998, 1.002, n)
        highs = np.maximum(opens, closes) * np.random.uniform(1.001, 1.005, n)
        lows = np.minimum(opens, closes) * np.random.uniform(0.995, 0.999, n)
        volumes = np.random.uniform(10000, 500000, n)

        return pd.DataFrame({
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })


# Singleton instance
_client = None

def get_upstox_client() -> UpstoxClient:
    global _client
    if _client is None:
        _client = UpstoxClient()
    return _client
