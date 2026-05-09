from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, JSON, Text, Index
from sqlalchemy.sql import func
from backend.database.connection import Base


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False)
    name = Column(String(100))
    sector = Column(String(50))
    is_active = Column(Boolean, default=True)


class OHLCV5Min(Base):
    __tablename__ = "ohlcv_5min"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_ohlcv_5min_symbol_timestamp", "symbol", "timestamp", unique=True),
    )


class OHLCVDaily(Base):
    __tablename__ = "ohlcv_daily"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_ohlcv_daily_symbol_date", "symbol", "date", unique=True),
    )


class MarketContext(Base):
    __tablename__ = "market_context"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    vix = Column(Float)
    fii_net_crores = Column(Float)          # FII net buy/sell in crores
    fii_z_score = Column(Float)             # normalized vs 20-day rolling
    morning_bias = Column(Float)            # -1 to +1
    nifty_open = Column(Float)
    nifty_close = Column(Float)
    nifty_prev_return = Column(Float)       # previous day % return


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    direction = Column(String(5), nullable=False)       # long | short
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    exposure = Column(Float, nullable=False)            # entry_price * quantity
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True))
    exit_price = Column(Float)
    exit_reason = Column(String(20))                    # target_hit | stop_hit | eod_squareoff
    pnl = Column(Float)
    signal_confidence = Column(Float)                   # ML model probability (null for rule-based)
    model_version = Column(String(20))
    trading_mode = Column(String(10), default="paper")  # paper | live
    status = Column(String(10), default="open")         # open | closed
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    direction = Column(String(5), nullable=False)       # long | short
    confidence = Column(Float)
    features = Column(JSON)                             # full feature vector at signal time
    trade_taken = Column(Boolean, default=False)
    skip_reason = Column(String(100))                   # why trade was not taken
    trade_id = Column(Integer)                          # FK to trades.id if trade was taken
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ModelPerformance(Base):
    __tablename__ = "model_performance"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    win_rate = Column(Float)
    total_pnl = Column(Float, default=0.0)
    model_version = Column(String(20))
    trading_mode = Column(String(10), default="paper")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    lesson_text = Column(Text, nullable=False)
    conditions = Column(JSON)                           # structured context (VIX level, bias, etc.)
    trade_id = Column(Integer)                          # related trade if applicable
    created_at = Column(DateTime(timezone=True), server_default=func.now())
