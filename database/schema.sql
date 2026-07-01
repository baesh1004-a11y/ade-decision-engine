-- ADE v1.0 decision engine database schema
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

CREATE TABLE IF NOT EXISTS pattern_vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    vector_version TEXT NOT NULL,
    window INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, vector_version, window)
);

CREATE TABLE IF NOT EXISTS pattern_match_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    vector_version TEXT NOT NULL,
    window INTEGER NOT NULL,
    top_k INTEGER NOT NULL,
    match_count INTEGER NOT NULL,
    avg_similarity REAL NOT NULL,
    expected_returns TEXT NOT NULL,
    win_rates TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    matches_json TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, engine_version, window, top_k)
);

CREATE TABLE IF NOT EXISTS pattern_context_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    pattern_similarity REAL NOT NULL,
    context_similarity REAL NOT NULL,
    combined_similarity REAL NOT NULL,
    expected_returns TEXT NOT NULL,
    win_rates TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    current_context TEXT NOT NULL,
    pattern_json TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS probability_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    horizon TEXT NOT NULL,
    upside_probability REAL NOT NULL,
    downside_probability REAL NOT NULL,
    expected_return REAL NOT NULL,
    expected_mdd REAL NOT NULL,
    risk_reward REAL NOT NULL,
    confidence REAL NOT NULL,
    recommendation TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, engine_version, horizon)
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

CREATE TABLE IF NOT EXISTS position_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    account_balance REAL NOT NULL,
    cash REAL,
    price REAL NOT NULL,
    recommended_weight REAL NOT NULL,
    buy_amount REAL NOT NULL,
    shares INTEGER NOT NULL,
    max_loss REAL NOT NULL,
    risk_score INTEGER NOT NULL,
    kelly_weight REAL NOT NULL,
    atr_risk REAL NOT NULL,
    sector_weight REAL NOT NULL,
    portfolio_heat REAL NOT NULL,
    cash_limited INTEGER NOT NULL DEFAULT 0,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (decision_id) REFERENCES candidate_decisions(id),
    UNIQUE (market, ticker, trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS entry_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_decision_id INTEGER,
    position_recommendation_id INTEGER,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    entry_score INTEGER NOT NULL,
    action TEXT NOT NULL,
    order_type TEXT NOT NULL,
    entry_price REAL NOT NULL,
    limit_price REAL NOT NULL,
    risk_level TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    reasons TEXT NOT NULL,
    signal_hits TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_decision_id) REFERENCES candidate_decisions(id),
    FOREIGN KEY (position_recommendation_id) REFERENCES position_recommendations(id),
    UNIQUE (market, ticker, trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS exit_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_decision_id INTEGER,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    sell_score INTEGER NOT NULL,
    action TEXT NOT NULL,
    sell_ratio REAL NOT NULL,
    sell_shares INTEGER NOT NULL,
    remaining_shares INTEGER NOT NULL,
    current_price REAL NOT NULL,
    pnl_pct REAL NOT NULL,
    risk_level TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    reasons TEXT NOT NULL,
    signal_hits TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_decision_id) REFERENCES entry_decisions(id),
    UNIQUE (market, ticker, trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS portfolio_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    portfolio_score INTEGER NOT NULL,
    action TEXT NOT NULL,
    total_value REAL NOT NULL,
    cash_weight REAL NOT NULL,
    target_cash_weight REAL NOT NULL,
    position_count INTEGER NOT NULL,
    max_position_weight REAL NOT NULL,
    max_sector_weight REAL NOT NULL,
    risk_flags TEXT NOT NULL,
    recommendations TEXT NOT NULL,
    sector_weights TEXT NOT NULL,
    market_weights TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    risk_level TEXT NOT NULL,
    action TEXT NOT NULL,
    trade_allowed INTEGER NOT NULL,
    max_new_position_weight REAL NOT NULL,
    target_cash_weight REAL NOT NULL,
    daily_loss_pct REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    risk_flags TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trade_date, engine_version)
);

CREATE TABLE IF NOT EXISTS learning_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    learning_score INTEGER NOT NULL,
    action TEXT NOT NULL,
    recommendations TEXT NOT NULL,
    weak_rules TEXT NOT NULL,
    strong_rules TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trade_date, engine_version)
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

CREATE INDEX IF NOT EXISTS idx_pattern_vectors_lookup
ON pattern_vectors (market, ticker, trade_date, vector_version, window);

CREATE INDEX IF NOT EXISTS idx_pattern_match_decisions_lookup
ON pattern_match_decisions (market, ticker, trade_date, avg_similarity, match_count);

CREATE INDEX IF NOT EXISTS idx_pattern_context_decisions_lookup
ON pattern_context_decisions (market, ticker, trade_date, combined_similarity);

CREATE INDEX IF NOT EXISTS idx_probability_decisions_lookup
ON probability_decisions (market, ticker, trade_date, upside_probability, recommendation);

CREATE INDEX IF NOT EXISTS idx_candidate_decisions_lookup
ON candidate_decisions (market, ticker, trade_date, score, grade);

CREATE INDEX IF NOT EXISTS idx_position_recommendations_lookup
ON position_recommendations (market, ticker, trade_date, recommended_weight, risk_score);

CREATE INDEX IF NOT EXISTS idx_entry_decisions_lookup
ON entry_decisions (market, ticker, trade_date, entry_score, action);

CREATE INDEX IF NOT EXISTS idx_exit_decisions_lookup
ON exit_decisions (market, ticker, trade_date, sell_score, action);

CREATE INDEX IF NOT EXISTS idx_portfolio_decisions_lookup
ON portfolio_decisions (trade_date, portfolio_score, action);

CREATE INDEX IF NOT EXISTS idx_risk_decisions_lookup
ON risk_decisions (trade_date, risk_score, risk_level, action);

CREATE INDEX IF NOT EXISTS idx_learning_decisions_lookup
ON learning_decisions (trade_date, learning_score, action);
