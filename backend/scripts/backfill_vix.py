"""
One-time script: backfill 2+ years of India VIX into market_context table.

Fetches ^INDIAVIX daily close from Yahoo Finance (free, no auth).
Only fills missing rows — never overwrites dates that already have real VIX data.

For historical rows we only have VIX (no FII history), so morning_bias is computed
from VIX only: bias = 0.4 * clip((20 - vix) / 20, -1, 1)
This is partial but still useful — high-VIX days get negative bias, low-VIX = positive.

Run via: railway run python -m backend.scripts.backfill_vix
"""
import numpy as np
import yfinance as yf
from backend.database.connection import SessionLocal
from backend.database.models import MarketContext
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def run_vix_backfill(start: str = "2024-05-01") -> dict:
    logger.info(f"Fetching ^INDIAVIX from Yahoo Finance (from {start})...")
    df = yf.download("^INDIAVIX", start=start, progress=False, auto_adjust=True)

    if df.empty:
        raise RuntimeError("yfinance returned empty data for ^INDIAVIX")

    logger.info(f"Downloaded {len(df)} trading days of VIX data")

    db = SessionLocal()
    inserted = 0
    updated = 0
    skipped = 0

    try:
        for idx, row in df.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            close_val = row["Close"]
            if hasattr(close_val, '__len__'):
                close_val = float(close_val.iloc[0])
            else:
                close_val = float(close_val)

            if np.isnan(close_val):
                skipped += 1
                continue

            vix = round(close_val, 2)
            # Partial bias from VIX only — FII component = 0 (no historical FII data)
            vix_score = float(np.clip((20 - vix) / 20, -1, 1))
            bias = round(0.4 * vix_score, 4)

            existing = db.query(MarketContext).filter(MarketContext.date == d).first()
            if existing:
                if existing.vix is None:
                    existing.vix = vix
                    if existing.morning_bias is None:
                        existing.morning_bias = bias
                    updated += 1
                else:
                    skipped += 1  # already has real VIX — don't overwrite
            else:
                ctx = MarketContext(
                    date=d,
                    vix=vix,
                    morning_bias=bias,
                    fii_net_crores=None,
                    fii_z_score=None,
                )
                db.add(ctx)
                inserted += 1

        db.commit()
        logger.info(f"VIX backfill complete: {inserted} inserted, {updated} updated, {skipped} skipped")
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    except Exception as e:
        db.rollback()
        logger.error(f"VIX backfill failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = run_vix_backfill()
    print(result)
