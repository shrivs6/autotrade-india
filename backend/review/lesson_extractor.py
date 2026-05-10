"""
Lesson extractor — generates structured lessons from today's trade results.
Runs after post_market_review. Saves lessons to the lessons table.
"""
from datetime import date
from backend.database.connection import SessionLocal
from backend.database.models import Trade, Lesson, MarketContext
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def extract_lessons(summary: dict):
    """
    Takes the post-market summary dict and generates lessons.
    Each lesson is a plain-English observation about what happened today.
    """
    if not summary or summary.get("total_trades", 0) == 0:
        return

    today = date.today()
    db = SessionLocal()
    lessons = []

    try:
        today_trades = (
            db.query(Trade)
            .filter(Trade.status == "closed")
            .filter(Trade.trading_mode == "paper")
            .all()
        )
        today_trades = [
            t for t in today_trades
            if t.exit_time and t.exit_time.date() == today
        ]

        ctx = db.query(MarketContext).filter(MarketContext.date == today).first()
        vix = ctx.vix if ctx else None
        bias = ctx.morning_bias if ctx else None

        total = summary.get("total_trades", 0)
        win_rate = summary.get("win_rate", 0)
        total_pnl = summary.get("total_pnl", 0)
        exit_reasons = summary.get("exit_reasons", {})

        # Lesson 1: Overall day quality
        if win_rate >= 0.6:
            lessons.append(f"Strong day: {win_rate:.0%} win rate with ₹{total_pnl:+,.0f} PnL. "
                           f"Conditions were favorable — replicate setup.")
        elif win_rate <= 0.4:
            lessons.append(f"Difficult day: {win_rate:.0%} win rate with ₹{total_pnl:+,.0f} PnL. "
                           f"Review what failed — avoid repeating.")

        # Lesson 2: High VIX warning
        if vix and vix > 20:
            stop_hits = exit_reasons.get("stop_hit", 0)
            if stop_hits > total * 0.5:
                lessons.append(
                    f"High VIX ({vix:.1f}) correlated with {stop_hits} stop hits today. "
                    f"Consider reducing position size when VIX > 20."
                )

        # Lesson 3: EOD squareoffs (late entries that didn't resolve)
        eod_count = exit_reasons.get("eod_squareoff", 0)
        if eod_count > 0:
            eod_trades = [t for t in today_trades if t.exit_reason == "eod_squareoff"]
            eod_pnl = sum(t.pnl for t in eod_trades if t.pnl)
            lessons.append(
                f"{eod_count} position(s) closed at EOD with ₹{eod_pnl:+,.0f} PnL. "
                f"These trades didn't resolve — review entry timing."
            )

        # Lesson 4: Bias accuracy
        if bias is not None:
            winners = [t for t in today_trades if t.pnl and t.pnl > 0]
            long_winners = [t for t in winners if t.direction == "long"]
            short_winners = [t for t in winners if t.direction == "short"]

            if bias > 0.3 and len(long_winners) > len(short_winners):
                lessons.append(
                    f"Bullish morning bias ({bias:.2f}) proved correct — "
                    f"long trades outperformed today."
                )
            elif bias < -0.3 and len(short_winners) > len(long_winners):
                lessons.append(
                    f"Bearish morning bias ({bias:.2f}) proved correct — "
                    f"short trades outperformed today."
                )
            elif abs(bias) > 0.3:
                lessons.append(
                    f"Morning bias ({bias:.2f}) did not align with trade outcomes today. "
                    f"Market may have reversed intraday."
                )

        # Save all lessons
        for text in lessons:
            lesson = Lesson(
                date=today,
                lesson_text=text,
                conditions={
                    "vix": vix,
                    "morning_bias": bias,
                    "total_trades": total,
                    "win_rate": win_rate,
                },
            )
            db.add(lesson)

        db.commit()
        logger.info(f"Extracted {len(lessons)} lesson(s) for {today}")
        for l in lessons:
            logger.info(f"  → {l}")

    except Exception as e:
        logger.error(f"Lesson extraction failed: {e}")
        db.rollback()
    finally:
        db.close()
