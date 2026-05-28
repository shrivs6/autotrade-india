# AutoTrade India — Master Plan

> **How to use this file:** This is the single source of truth for the entire project.
> When starting a new conversation with Claude, say: "Read PLAN.md and continue from Phase X."
> Update the STATUS section below as phases are completed.

---

## Current Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 — Prerequisites | ✅ Done | Neon DB (Singapore), shrivs6 GitHub, Railway + Vercel accounts created. Upstox KYC approved. |
| Phase 1 — Foundation | ✅ Done | FastAPI, scheduler, DB models, upstox_client (STUB_MODE=True), historical backfill run |
| Phase 2 — Feature Engineering | ✅ Done | 27-feature vector, signal_features table backfilled (716k rows) |
| Phase 3 — Rule-Based Paper Trading | ✅ Done | Paper broker, risk manager, order manager, post-market review, lessons |
| Phase 4 — ML Training + Backtesting | ✅ Done | XGBoost trained (v1_initial), walk-forward validated, backtester built |
| Phase 5 — Live Paper Trading + Dashboard | 🔄 Active | Pivoted to NIFTY + BANKNIFTY futures (2026-05-16). ~10 months of NSE_INDEX history backfilled. Nightly self-updating retrains running. AUC=0.5729 (v20260525). |
| Phase 6 — Real Money + Claude Layer | ⏳ Blocked | Gate: 60%+ win rate for 30 consecutive days on NIFTY/BANKNIFTY data. |

### Instrument Pivot (2026-05-16)
Switched from 50 individual Nifty 50 equity stocks → **NIFTY + BANKNIFTY index futures (NSE_FO)** only.

**Why:** Higher liquidity, fewer instruments to scan, multiple intraday re-entries on same instrument.

**What changed:**
- `constants.py`: `NIFTY50_SYMBOLS = ["NIFTY", "BANKNIFTY"]`, `NSE_SEGMENT = "NSE_FO"`, `LOT_SIZES = {"NIFTY": 65, "BANKNIFTY": 30}` (65 is SEBI-mandated, not 75)
- `upstox_client.py`: Near-month futures contract resolved dynamically from `complete.csv.gz` (FUTIDX type, NSE_FO exchange). Stores both `instrument_key` and `tradingsymbol` per symbol. `get_contract_name()` returns e.g. `NIFTY26MAYFUT`. Refreshes daily.
- `risk_manager.py`: Lot-based MIS sizing at 15% margin. `MAX_POSITION_EXPOSURE = ₹3,00,000`.
- `scheduler.py`: Square-off moved from 3:20 PM → **3:00 PM** (Upstox stops serving quotes ~3:15 PM).
- `order_manager.py`: Resolves and stores full contract name on trade open. Square-off uses last OHLCV candle close as fallback if fetch_ltp fails (never falls back to entry price).
- `models.py`: Added `contract` column to `Trade` table (stores e.g. `NIFTY26MAYFUT`). ALTER TABLE run on Neon.
- `main.py`: On startup, restores open positions from DB into in-memory tracker so stop/target monitoring survives Railway container restarts.
- `health.py`: Expanded `/health` endpoint checks DB, Upstox token, instrument key loading, and tracker/DB position sync. Hit this every morning before 9:30 AM.
- DB cleared: ohlcv_5min, signal_features, trade_signals, old equity trades all removed. Fresh start.
- Backfilled: ~10 months of NSE_INDEX continuous history (Nifty 50 + Nifty Bank) via `backend/scripts/backfill_index_history.py`. Signal features: ~5,548 rows (2,776 NIFTY + 2,772 BANKNIFTY). Older chunks (>14 months) rejected by Upstox — handled gracefully.
- `RETRAIN_MONTHS_BACK = 12` in `incremental_trainer.py` — uses full available history each night.
- Admin endpoints added (`backend/api/routes/admin.py`): `POST /admin/backfill-history` and `GET /admin/backfill-status`, protected by `ADMIN_SECRET` env var.

**Futures data limitation:** Each futures contract only carries ~2 months of history. Data accumulates organically each trading day.

### Annual Maintenance
- **Each December**: Update `NSE_HOLIDAYS_2026` in `backend/utils/constants.py` with next year's NSE holiday list. Source: nseindia.com/resources/exchange-communication-holidays

### Daily Morning Checklist (before 9:30 AM)
1. Visit `https://web-production-0db02.up.railway.app/auth/login` to refresh Upstox token
2. Hit `/health` — all checks must show `"ok": true` before market opens
3. If `instrument_keys` check fails → container restart may fix it (token reload triggers map refresh)

### Known Issues
- **`fetch_ltp` errors at 3 PM square-off** — Upstox stops serving quotes ~3:15 PM so `fetch_ltp` raises an error at 3:00 PM. Fallback to last OHLCV candle close price works correctly. Not a crash — just noisy logs. Root cause unresolved; acceptable for paper trading.

### Known Issues (resolved)
- ~~`fetch_ltp` startup race condition~~ — confirmed resolved 2026-05-20. Was a container startup race before token loaded, not the 3 PM quote issue above.
- ~~Confidence blank on open trades dashboard~~ — `ml_signal_evaluator.evaluate_ml()` now returns a 3-tuple `(direction, signal_id, confidence)`. `order_manager.open_trade()` accepts `confidence` kwarg and stores it as `Trade.signal_confidence`. Scheduler unpacks and passes confidence. (2026-05-25)
- ~~Nightly retrain not learning from today's candles~~ — `run_incremental_retrain()` now calls `_update_signal_features()` before `build_dataset()`. This converts any new `ohlcv_5min` rows to `signal_features` rows (ON CONFLICT DO NOTHING) so each day's live candles are included in the next night's retrain without manual backfill triggers. (2026-05-25)

### Parameter Changes for Futures
| Parameter | Old (equity) | New (futures) | Reason |
|-----------|-------------|---------------|--------|
| `MAX_POSITION_EXPOSURE` | ₹1,00,000 | ₹3,00,000 | 1 NIFTY lot MIS margin |
| `DAILY_LOSS_LIMIT` | -₹5,000 | -₹50,000 | Each futures stop = ~₹7-8k. Old limit halted after 1st loss. |
| `STOP_LOSS_PCT` | 0.5% | 0.5% | Unchanged |
| `TARGET_PCT` | 0.75% | 0.75% | Unchanged |

> **Note:** When moving to real money, tighten `DAILY_LOSS_LIMIT` back to ~-₹20,000 (2-3 stops max).

### Known Fixes Applied
- `upstox-python-sdk` pinned to `2.26.0` (v2.8.0 no longer exists on PyPI)
- Railway env vars must be set without quotes in the Variables tab
- Upstox v2.26 API changes:
  - `ApiClient` no longer supports context manager (`with` syntax) — use direct instantiation
  - `5minute` interval removed — fetch `1minute` and resample to 5-min via pandas `resample("5min").agg()`
  - NSE-FO.csv.gz returns 403 publicly — use `complete.csv.gz` with `instrument_type=FUTIDX` filter instead
  - Daily candle interval for NSE_FO must be `"day"` not `"1day"`
  - 1-minute data limited to 30 days per request — chunk size 30 days
- OAuth token stored in `upstox_token` DB table (Railway filesystem is ephemeral, files reset on redeploy)
- NIFTY lot size is **65** (SEBI revised from 75 in late 2024) — verify at contract rollover
- In-memory PositionTracker resets on container restart → fixed by restoring from DB at startup

---

## Project Overview

Fully automated intraday trading system for Indian stock markets (NSE, Nifty 50 stocks).
Evolves: rule-based paper trading → ML-driven paper trading → real money with Claude verification.

**Stack:**
- Backend: Python 3.11, FastAPI, APScheduler (hosted on Railway — runs 24/7 in cloud)
- ML: XGBoost
- Database: PostgreSQL on Neon.tech
- Frontend: React (hosted on Vercel — read-only dashboard)
- Broker API: Upstox (Indian broker, free API for account holders, OAuth 2.0)

**Key constraint:** Backend runs on Railway (cloud), NOT on personal laptop.

---

## Phase 0: Prerequisites

### What You Need

| Item | Status | How to Get It |
|------|--------|--------------|
| **NEW GitHub account** | ❌ | Create with a different email — Railway/Vercel must connect to this new account, not existing one |
| **Upstox trading account** | ❌ | upstox.com — needs PAN, Aadhaar, bank account. KYC takes 1-3 days. **Start today — longest blocker.** |
| **Upstox API key + secret** | ❌ | developer.upstox.com → create app after account is active. Redirect URI: `http://localhost:8000/callback` |
| **Neon PostgreSQL** | ❌ | neon.tech → sign up → New Project → region: `ap-south-1` (Mumbai) → copy connection string |
| **Railway account** | ❌ | railway.app → sign up with NEW GitHub account (not existing) |
| **Vercel account** | ❌ | vercel.com → sign up with NEW GitHub account. Not needed until Phase 5. |
| **Python 3.11+** | ✅ | Already installed |
| **Node.js 18+** | ✅ | Already installed |

### .env file (create this in project root, never commit it)
```
UPSTOX_API_KEY=
UPSTOX_API_SECRET=
DATABASE_URL=         # from neon.tech, looks like: postgresql://user:pass@host/db?sslmode=require
TRADING_MODE=paper    # paper | live | disabled
```

### Action Order (do in this sequence)
1. Apply for Upstox account (longest wait — do first)
2. Create new GitHub account
3. Create Neon DB — copy connection string
4. (Later, Phase 5) Create Railway + Vercel accounts with new GitHub

---

## Phase 1: Foundation — Infrastructure + Data Pipeline

**Goal:** Running backend, connected DB, working Upstox API, scheduler firing on market schedule.

### Project Structure to Create
```
autotrade-india/
    backend/
        main.py                    # FastAPI app entry point
        scheduler.py               # APScheduler — all timed jobs defined here
        config.py                  # All env vars loaded here, imported everywhere
        database/
            connection.py          # SQLAlchemy engine + session factory
            models.py              # ALL table definitions (design all upfront — avoid migrations later)
            migrations/            # Alembic migration files
        data/
            upstox_client.py       # Upstox API wrapper (OAuth 2.0 + data fetch)
            nse_client.py          # NSE India scraper (VIX, FII — no API key needed)
            historical_fetcher.py  # One-time bulk OHLCV backfill (run once)
            live_feed.py           # Real-time 5-min candle fetcher
        utils/
            logger.py              # Structured logging
            constants.py           # NIFTY50_SYMBOLS list, market hours
    frontend/                      # Scaffold only in Phase 1
    .env                           # Never commit
    .env.example                   # Commit this — shows what keys are needed
    requirements.txt
```

### Database Tables (all defined in models.py from day 1)
| Table | Purpose | Est. Rows |
|-------|---------|-----------|
| `stocks` | Nifty 50 master list (symbol, name, sector) | 50 |
| `ohlcv_5min` | 5-min candles, 1 year history. Index on (symbol, timestamp) | ~975k |
| `ohlcv_daily` | Daily candles, 5 year history | ~62.5k |
| `market_context` | One row/day: VIX, FII net, morning bias, Nifty open/close | ~250/yr |
| `trades` | Every paper/live trade: entry, exit, PnL, signal_confidence, exit_reason | grows daily |
| `trade_signals` | Every signal evaluated (even skipped) — critical for ML training | grows daily |
| `model_performance` | Daily snapshot: win_rate, total_pnl, model_version | ~250/yr |
| `lessons` | Post-market structured learning entries | grows daily |

### Scheduler Daily Schedule (IST)
- **8:30 AM** — fetch overnight data, build morning bias
- **9:15 AM** — confirm bias with live Nifty direction
- **9:30 AM → 3:20 PM (every 5 min)** — scan all stocks + place trades
- **3:20 PM** — force-close all open positions
- **3:45 PM** — post-market review + lesson extraction
- **11:00 PM** — nightly model retrain (active from Phase 4)

### Key Implementation Notes
- **upstox_client.py**: OAuth 2.0 with daily token expiry. First run opens browser for auth. Scheduler must refresh token before 9:15am every day.
- **historical_fetcher.py**: One-time bulk download. Rate-limited to ~2 req/sec → takes 30-45 min. Run once after API connected.
- **nse_client.py**: Scrape `nseindia.com/api/allIndices` (VIX) and `nseindia.com/api/fiidiiTradeReact` (FII). Must send browser-like headers or NSE blocks the request.

### Python Libraries (install in Phase 1)
```
upstox-python-sdk, pandas, numpy, sqlalchemy, psycopg2-binary,
alembic, fastapi, uvicorn, apscheduler, ta, python-dotenv
```

### Success Criteria
- `fetch_historical('RELIANCE', '5minute', ...)` returns populated DataFrame
- All DB tables created via Alembic migration
- `ohlcv_5min` populated for all 50 Nifty stocks
- Scheduler fires at 8:30am IST and logs output
- `GET /health` returns `{"status": "ok"}`

---

## Phase 2: Feature Engineering

**Goal:** Single function `build_features(symbol, timestamp)` returns complete 25-feature vector with no NaN values.

### New Files
```
backend/features/
    technical_indicators.py    # RSI(14), MACD, Bollinger Bands, Volume spike, Trend slope
    market_context_scorer.py   # VIX + FII → morning bias score (-1 to +1)
    feature_builder.py         # Master function: (symbol, timestamp) → feature dict
    feature_store.py           # Save features for evaluated signals to DB
backend/scripts/
    backfill_features.py       # One-time: compute features on all historical candles
```

### Feature Vector (~25 features)
| Feature | Description |
|---------|-------------|
| RSI(14) | 0-100. Zones below 30 and above 70 matter most |
| MACD line | Raw value |
| MACD histogram | Direction (rising/falling) more important than value |
| Bollinger %B | <0 = below lower band, >1 = above upper band |
| Volume spike | Current vol / 20-period average vol |
| Trend slope | Linear regression slope of last 20 closes, z-score normalized |
| Candle body ratio | Body size / total candle range |
| Upper wick ratio | Upper wick / total range |
| Lower wick ratio | Lower wick / total range |
| Time-of-day (sin) | Cyclical encoding of time |
| Time-of-day (cos) | Cyclical encoding of time |
| VIX raw | Continuous value |
| VIX high flag | Binary: VIX > 20 |
| VIX extreme flag | Binary: VIX > 25 (triggers reduced position size) |
| FII z-score | Net FII buy/sell normalized by 20-day rolling z-score |
| Morning bias | -1 to +1, computed at 9:15am from VIX direction + FII z-score + prev day return |

### Key Notes
- Features computed on-the-fly during live trading — not pre-stored for every candle
- `features` table stores features only for signals that were evaluated → becomes ML training data
- `backfill_features.py` runs once after Phase 2 to create initial ML training dataset

### Success Criteria
- `build_features('RELIANCE', timestamp)` returns dict with all features, zero NaN
- All values in expected ranges (RSI 0-100, bias -1 to +1, volume spike > 0)
- Backfill produces > 100k rows in features table

---

## Phase 3: Rule-Based Trading Engine (Paper Trading)

**Goal:** First live paper trades. Validates trade infrastructure. Establishes 45-55% win rate baseline for ML to beat.

### New Files
```
backend/trading/
    rule_engine.py         # Hard-coded entry rules (replaced by ML in Phase 5)
    signal_evaluator.py    # Features → trade decision
    order_manager.py       # Trade lifecycle: open → monitor → close
    risk_manager.py        # ⚠️ MOST CRITICAL FILE — bugs here = real money loss
    position_tracker.py    # In-memory state of open positions
backend/paper_trading/
    paper_broker.py        # Simulates fills at last traded price
    pnl_calculator.py      # Real-time PnL tracking
backend/review/
    post_market_review.py  # End-of-day analysis (runs at 3:45pm)
    lesson_extractor.py    # Generates structured lessons → lessons table
```

### Entry Rules — LONG (all conditions must be true simultaneously)
- Morning bias >= 0 (neutral to bullish)
- RSI between 40 and 65
- MACD histogram positive AND rising
- Price above Bollinger midline
- Volume spike > 1.5
- Time between 9:30am and 2:00pm
- Open positions < 3
- Daily PnL > -₹5,000

**SHORT** = mirror: bias <= 0, RSI 35-60, MACD negative+falling, price below midline. Same time/position/loss gates.

### Risk Manager Rules (enforce without exception)
| Rule | Value |
|------|-------|
| Position size | `qty = floor(100000 / entry_price)` — ₹1,00,000 exposure per trade |
| Stop loss | 0.5% from entry |
| Target | 0.75% from entry (1.5:1 reward:risk) |
| Daily loss limit | Halt all trading when PnL < -₹5,000. Flag resets next morning. |
| Max concurrent positions | 3 |

### Broker Adapter Pattern
`paper_broker.py` (Phase 3) and `live_broker.py` (Phase 6) implement identical interfaces:
- `place_order(symbol, direction, qty, order_type, price)`
- `cancel_order(order_id)`

Switch via `TRADING_MODE=paper|live` in `.env`. One config change = switch to real money.

### Success Criteria
- Full trading day runs without crash
- 20+ trades in `trades` table with correct PnL after 5 trading days
- No trade loses more than 0.5% (stop loss enforced)
- Daily loss limit correctly halts trading when triggered
- Lessons table populated after each session

---

## Phase 4: ML Model Training + Backtesting

**Goal:** XGBoost model trained on historical data. Backtest validates it beats rule-based baseline before going live.

### New Files
```
backend/ml/
    dataset_builder.py       # DB → labeled training DataFrame
    feature_selector.py      # Drop low-importance features
    model_trainer.py         # XGBoost training pipeline
    model_evaluator.py       # Walk-forward CV, win rate at confidence thresholds
    model_registry.py        # Save/load versioned models (joblib). Only promote if AUC improves.
    backtester.py            # Full historical replay (with 0.1% slippage + ₹20 brokerage)
    incremental_trainer.py   # Nightly retrain on new data — must complete in < 10 min
backend/scripts/
    train_initial_model.py   # One-time v1 training run
    run_backtest.py          # 6-month historical backtest
```

### ML Design Decisions
**Target variable:** Binary — 1 if trade hits 0.75% target before 0.5% stop, else 0.
Computed by forward-looking into historical OHLCV. Never done on live data.

**Validation method:** Walk-forward only (NOT random split).
Train months 1-6 → validate month 7. Train 1-7 → validate month 8. Etc.
Random splits inflate results because financial data has temporal autocorrelation.

**XGBoost starting params:**
```python
n_estimators=500, max_depth=6, learning_rate=0.05,
subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
scale_pos_weight=(neg_count / pos_count),
eval_metric='auc', early_stopping_rounds=50
```

**Confidence threshold:** Test at 0.55, 0.60, 0.65, 0.70.
Use threshold that maximizes `(win_rate × 0.75%) - (loss_rate × 0.5%)`.

### Success Criteria
- Walk-forward AUC > 0.55
- Backtest win rate > 52% (must beat rule-based baseline)
- Backtest max drawdown < ₹30,000 over 6 months
- 2-6 signals generated per trading day at chosen threshold
- Nightly retrain completes in < 10 minutes

---

## Phase 5: Live Paper Trading + Dashboard

**Goal:** ML replaces rules. React dashboard deployed. System runs autonomously 60+ trading days.

### New Files
```
backend/trading/
    ml_signal_evaluator.py     # Replaces rule_engine.py — same interface, ML-powered
    live_monitor.py            # Real-time position monitoring
backend/api/routes/
    dashboard.py               # /api/dashboard/* endpoints
    trades.py
    performance.py
    health.py
frontend/src/
    components/
        WinRateChart.jsx       # Line chart with 60% target reference line (Recharts)
        DailyTradeLog.jsx      # Today's trades table
        LearningSummary.jsx    # Today's lessons (auto-generated)
        PerformanceStats.jsx   # Top bar: Today PnL | Win Rate | System Status
    services/api.js            # All backend API calls
```

### API Endpoints
| Endpoint | Returns |
|----------|---------|
| `GET /api/dashboard/summary` | Today PnL, win rates, open positions count, system status |
| `GET /api/dashboard/win-rate-history` | Array of {date, win_rate, trade_count} for 90 days |
| `GET /api/dashboard/todays-trades` | Today's trades in plain English |
| `GET /api/dashboard/lessons` | Today's post-market lessons |

### Email Alerts (smtplib + Gmail)
- System fails to start before 9:15am
- Upstox token refresh fails
- Daily loss limit hit
- Uncaught exception in trading loop
- No trades placed in 3 consecutive trading days

### Deployment
- Backend → Railway (connected to new GitHub account)
- Frontend → Vercel (connected to new GitHub account)
- All code pushed to new GitHub account repo

### Success Criteria
- 30 consecutive autonomous trading days, zero manual intervention
- Dashboard live on Vercel URL showing correct real-time data
- Win rate tracked and showing upward trend month-over-month
- **Gate to Phase 6:** 60%+ win rate sustained for 30 consecutive trading days

---

## Phase 6: Real Money + Claude Verification Layer

**Gate (all must be true — no exceptions, enforced programmatically):**
1. >= 60 trading days of paper data in DB
2. Win rate >= 60% averaged over last 30 days
3. Win rate trend flat or improving (not declining)
4. Max single-day loss never exceeded ₹8,000 in paper trading
5. Zero crashes in last 30 consecutive trading days

### New Files
```
backend/trading/
    live_broker.py             # Real Upstox order execution (identical interface to paper_broker.py)
    phase_gate_checker.py      # Checks all 5 gate conditions. Returns bool. No manual override.
backend/claude_layer/
    signal_verifier.py         # Claude API call inserted between ML evaluator and order manager
    verification_prompt.py     # Short, numerical, factual prompt template
    verification_logger.py     # Logs every Claude decision + eventual trade outcome
```

### Claude Verification Layer Logic
- Triggers **only** when model confidence is 0.60–0.75 (medium zone)
- High-confidence signals (> 0.75) bypass Claude and go straight to order manager
- Input to Claude: proposed trade, VIX, FII z-score, top-5 XGBoost feature importances, last 5 trades on that symbol
- Claude output: `CONFIRM` | `SKIP <reason>` | `REDUCE` (half position size)
- All decisions + outcomes logged → after 30 days, verify Claude's CONFIRM win rate > overall win rate

### Real Money Ramp-Up (never increase after a losing week)
| Period | Max exposure/trade |
|--------|-------------------|
| Week 1-2 | ₹10,000 |
| Week 3-4 | ₹25,000 |
| Month 2 | ₹50,000 |
| Month 3+ | ₹1,00,000 |

### Kill Switch
Set `TRADING_MODE=disabled` in Railway environment variables → halts within one 5-min scheduler cycle.

### Success Criteria
- `phase_gate_checker.py` passes all 5 conditions before any real order is placed
- First real order appears in Upstox order history
- Real money win rate matches paper win rate after 30 trading days
- Claude CONFIRM decisions show higher win rate than overall after 30 days

---

## Win Rate Progression Targets

| Period | Target Win Rate |
|--------|----------------|
| Phase 3 (Week 1-4) | 48-52% — rule-based baseline |
| Phase 5 Month 1 | 52-55% |
| Phase 5 Month 2 | 55-58% |
| Phase 5 Month 3-4 | 58-62% |
| Phase 6 (real money) | 62-65% with Claude layer |

---

## Critical Files — Get These Right First

| File | Why It Matters |
|------|---------------|
| `backend/database/models.py` | Schema used by everything — wrong design = painful migrations |
| `backend/data/upstox_client.py` | Entire data supply — fragile wrapper breaks all downstream |
| `backend/features/feature_builder.py` | Directly determines ML model quality |
| `backend/trading/risk_manager.py` | Financial safety net — bugs = real money loss |
| `backend/scheduler.py` | Missed jobs = silent failure for that trading day |
