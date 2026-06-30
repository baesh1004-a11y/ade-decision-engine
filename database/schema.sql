-- ADE v0.2 decision engine database schema
-- Target: SQLite first, portable to PostgreSQL later.

CREATE TABLE IF NOT EXISTS market_bars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date)
);

CREATE TABLE IF NOT EXISTS indicator_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close REAL NOT NULL,
    ma20 REAL,
    ma60 REAL,
    ma120 REAL,
    vol20_ratio REAL,
    body_ratio REAL,
    is_bullish INTEGER,
    sto533_k REAL,
    sto533_d REAL,
    sto1066_k REAL,
    sto1066_d REAL,
    sto201212_k REAL,
    sto201212_d REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date)
);

CREATE TABLE IF NOT EXISTS candidate_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    score INTEGER NOT NULL,
    grade TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    close REAL NOT NULL,
    risk_level TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    min_score INTEGER NOT NULL,
    horizons TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS backtest_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    close REAL NOT NULL,
    score INTEGER NOT NULL,
    grade TEXT,
    reasons TEXT NOT NULL,
    return_5d REAL,
    return_10d REAL,
    return_20d REAL,
    return_40d REAL,
    return_60d REAL,
    return_120d REAL,
    mdd_5d REAL,
    mdd_10d REAL,
    mdd_20d REAL,
    mdd_40d REAL,
    mdd_60d REAL,
    mdd_120d REAL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_market_bars_lookup
ON market_bars (market, ticker, trade_date);

CREATE INDEX IF NOT EXISTS idx_candidate_decisions_lookup
ON candidate_decisions (market, ticker, trade_date, score, grade);
