-- ADE migration 001: Pattern Memory DB

CREATE TABLE IF NOT EXISTS pattern_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    memory_version TEXT NOT NULL,
    vector_version TEXT NOT NULL,
    window INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    close REAL NOT NULL,
    forward_returns_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, memory_version, vector_version, window)
);

CREATE INDEX IF NOT EXISTS idx_pattern_memory_lookup
ON pattern_memory (market, ticker, trade_date, memory_version, vector_version, window);

CREATE INDEX IF NOT EXISTS idx_pattern_memory_search_scope
ON pattern_memory (market, ticker, window);
