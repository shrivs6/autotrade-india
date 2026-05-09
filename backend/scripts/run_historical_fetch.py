"""
Run this once after Upstox KYC is approved and API key is set in .env.

Usage:
    cd "Trading Simulater"
    source venv/bin/activate
    python -m backend.scripts.run_historical_fetch
"""
from backend.data.historical_fetcher import run_full_backfill

if __name__ == "__main__":
    run_full_backfill()
