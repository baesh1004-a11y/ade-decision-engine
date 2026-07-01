-- ADE migration 002: Backtest Persistence

CREATE TABLE IF NOT EXISTS backtest_runs_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    final_equity REAL NOT NULL,
    total_return REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    trade_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    exit_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    shares INTEGER NOT NULL,
    gross_return REAL NOT NULL,
    holding_days INTEGER NOT NULL,
    reason TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs_v2(id)
);

CREATE TABLE IF NOT EXISTS backtest_daily_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    cash REAL NOT NULL,
    position_value REAL NOT NULL,
    equity REAL NOT NULL,
    drawdown REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs_v2(id)
);

CREATE TABLE IF NOT EXISTS backtest_performance_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_return REAL NOT NULL,
    avg_win REAL NOT NULL,
    avg_loss REAL NOT NULL,
    profit_factor REAL NOT NULL,
    expectancy REAL NOT NULL,
    total_return REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs_v2(id)
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_v2_lookup
ON backtest_runs_v2 (ticker, start_date, end_date, total_return, max_drawdown);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_lookup
ON backtest_trades (run_id, ticker, entry_date, exit_date, gross_return);

CREATE INDEX IF NOT EXISTS idx_backtest_daily_equity_lookup
ON backtest_daily_equity (run_id, trade_date, equity, drawdown);
