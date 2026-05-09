# AutoTrade India — Project Vision

## What This Is

A fully automated intraday trading system built for the Indian stock market (NSE) that trades by itself every day, learns from its own mistakes, and gradually gets better at making profitable decisions. The human's only job is to check the dashboard occasionally and watch the win rate improve over time.

This is not a tool where the user clicks buttons, analyzes charts, or makes trading decisions. The system makes all decisions by itself. The user is the observer, not the operator.

---

## The Core Philosophy

Most trading tools give you signals and expect you to act on them. This system acts on its own. It places trades, monitors them, closes them, reviews what happened, learns from mistakes, and comes back the next day slightly smarter than before.

The goal is not perfection on day one. The goal is a system that starts at roughly 50% win rate — barely better than random — and through daily learning, pushes that number toward 60%, then 65%, over months of real market exposure. At 60% consistent win rate, the system starts making money reliably.

When the ML engine proves it can hit 60% on its own, a Claude verification layer gets added on top to further filter and confirm signals. Until then, Claude is not involved in trading decisions — the ML earns that right.

---

## The Market

India NSE only. Specifically the Nifty 50 stocks — the 50 largest and most liquid companies on the Indian stock exchange. These are chosen because:

- High liquidity means trades fill easily at expected prices
- Price data is reliable and consistent
- These stocks react predictably to market-wide sentiment
- Upstox API provides free historical and live data for all of them

No crypto, no US stocks, no international markets. Single focused market makes the ML model's job significantly easier.

---

## Trading Style

Pure intraday. Every position opened during market hours is closed before 3:20pm the same day. No overnight positions, no swing trades, no holding across days.

The system uses 5x intraday margin available through Upstox. This means ₹2,00,000 of capital behaves like ₹10,00,000 of buying power during market hours. All margin positions are force-closed before the 3:20pm market auto-squareoff time.

Capital is unlimited for paper trading purposes. The system never runs out of money to trade with. However every single trade is capped at ₹1,00,000 per position including the 5x margin effect. This means the actual cash committed per trade is ₹20,000 (which becomes ₹1,00,000 with 5x margin). This cap is hardcoded and non-negotiable — no single trade ever risks more than ₹1,00,000 of exposure regardless of how much virtual capital is available. This discipline exists because when real money is eventually introduced, ₹1,00,000 per trade is the intended real position size. Training the system and yourself on this limit from day one ensures the habits and risk parameters carry over cleanly to live trading.

---

## Data Sources

Everything comes from Upstox API which is free with a standard Upstox trading account.

For price data the system uses two timeframes together. Five minute candles going back one year give the intraday pattern detail needed for entry and exit timing. Daily candles going back five years give the broader market context that helps the model understand whether today is a trending day, a reversal day, or a choppy sideways day.

For market sentiment the system uses three free proxy indicators instead of trying to read news headlines. India VIX is the fear index — when it is above 20 the market is fearful and the system reduces position sizes or skips low-confidence signals entirely. FII data published daily by NSE shows whether foreign institutional investors are net buyers or sellers — this is the single most powerful market direction indicator for Indian markets. The Nifty 50 index direction in the first fifteen minutes of trading confirms or contradicts the morning bias set by VIX and FII data.

These three together give roughly 80% of the value of full sentiment analysis at a fraction of the complexity.

---

## How a Typical Day Works

Before market opens the system fetches overnight data — what US markets did, what SGX Nifty futures suggest, current VIX level, and yesterday's FII activity. From this it builds a morning market bias: bullish, bearish, or neutral.

When market opens at 9:15am the system watches the first fifteen minutes to confirm the bias. A Nifty that opens strongly up confirms bullish bias. A weak open questions it.

From 9:30am onwards the ML model scans all 50 Nifty stocks looking for setups that match both the technical conditions and today's market bias. It finds the two or three strongest opportunities and places paper trades automatically with predefined entry prices, targets, and stop losses.

Throughout the day the system checks prices every few minutes. When a target is hit the trade closes with a profit. When a stop loss is hit the trade closes with a small controlled loss. No human intervention needed.

At 3:20pm any remaining open positions are force-closed regardless of whether they are profitable or not. This is non-negotiable — no overnight positions ever.

After market closes the system reviews every trade from the day. For each trade it asks: was the signal right? If the trade lost, why? Was it a bad signal or did the market do something unexpected? What conditions were present when winning trades were placed? What was different about losing trades? These answers become structured lessons stored in the database.

The ML model then retrains overnight incorporating today's outcomes. Tomorrow it wakes up slightly smarter.

---

## What the User Sees

A minimal dashboard with three things.

The win rate chart shows how the model's accuracy has evolved over time — starting near 50% and the trend over weeks and months. This is the single most important number. Everything else serves this number.

The daily trade log shows what happened today in plain English. Which stocks were traded, whether they made or lost money, how long positions were held, and a one-line explanation of why the system made each decision.

The learning summary shows what the model learned today. Not technical jargon — plain language like "trades taken during high VIX periods had lower success rate" or "banking sector stocks performed better than IT sector this week."

There are no analyze buttons, no manual trade buttons, no chart with indicators to study. The system does not need the user to operate it. The user's job is to observe, understand what is working, and trust the process.

---

## The Learning Loop

This is the most important part of the system. Without genuine learning the win rate stays flat forever.

Every trade outcome gets labelled clearly — win or loss, how much, under what market conditions, what signals triggered the entry. Over time the model builds a rich picture of what works in which situations.

The system learns things like: this particular candlestick pattern on RELIANCE during low VIX days has a 70% success rate, but during high VIX days the same pattern fails 60% of the time. Or: MACD crossovers on banking stocks work better in the afternoon session than morning session. These are the kinds of market-specific insights that take a human trader years to develop through experience. The system accumulates them automatically.

Each day adds more data. Each week the model's understanding of the market deepens. The win rate improvement is slow in the first month, accelerates in months two and three as patterns solidify, and should reach the 60% target somewhere between month three and month six depending on market conditions.

---

## When Claude Gets Added

Claude is not part of the initial system. The ML engine must earn Claude's involvement by demonstrating consistent above-60% win rate first.

When that threshold is reached, Claude gets added as a verification layer only. The ML still generates all signals. Claude's job is to review the signal against current market context and either confirm it or flag concerns. Claude cannot initiate a trade — it can only approve or question what the ML proposes.

This keeps the system's performance attributable to the ML engine, not to Claude's reasoning. The goal is a robust ML system that Claude makes marginally better, not a Claude system that ML feeds data to.

---

## When Real Money Gets Added

Paper trading continues until the system demonstrates 60%+ win rate sustained over at least 60 trading days — roughly three months. This sample size is large enough to distinguish genuine edge from luck.

At that point real trading begins with a small amount — perhaps ₹10,000 to ₹20,000 initially. The same Upstox API used for paper trading handles real order placement with minimal code changes. The transition from paper to real is deliberately small and slow, increasing capital only as the real-money win rate confirms what paper trading showed.

---

## What This Is Not

This is not a get-rich-quick system. Win rates improve slowly over months, not days. The first month will likely be unprofitable.

This is not a black box that cannot be understood. Every trade decision is logged with its reasoning. Every lesson learned is stored in plain language. The user should be able to look at any trade and understand why the system made that call.

This is not dependent on predicting the future. A 60% win rate means losing 40% of the time. The edge comes from making more on winners than losing on losers, combined with disciplined position sizing that prevents any single loss from being catastrophic.

---

## Technical Approach

Backend: Python. Handles all data fetching, feature engineering, ML training, trade execution, and learning loop. Runs as a persistent service so scheduled jobs fire at the right times daily.

ML Model: XGBoost as the primary classifier for signal generation. Chosen because it is fast, interpretable, works well with tabular financial data, and can be retrained incrementally as new data arrives. LSTM layer considered for later phases once sufficient training data accumulates.

Database: PostgreSQL. Stores all OHLCV data, trade history, model performance metrics, and learned lessons.

Frontend: React. Minimal UI. Three panels — win rate trend, daily trade log, learning summary. No trading controls. Read-only dashboard.

Data: Upstox API exclusively. One source, one integration, no complexity from managing multiple data providers.

Deployment: Railway for backend (always on, scheduler runs reliably), Vercel for frontend (free, fast). No local machine dependency — system runs 24/7 in the cloud.

---

## Success Metrics

The only metric that matters is win rate trend over time. Everything else — number of trades, individual trade PnL, model complexity — is secondary.

Week 1-4: Establishing baseline, expect 48-52%
Month 2: Learning market structure, expect 52-55%  
Month 3: Patterns solidifying, expect 55-58%
Month 4-6: Approaching target, expect 58-62%
Month 6+: Claude layer added, target 62-65%

If win rate is not improving month over month, the learning loop is broken and needs diagnosis before anything else is changed.
