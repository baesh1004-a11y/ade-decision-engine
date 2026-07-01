-- ADE migration 004: Adaptive Learning v2

CREATE TABLE IF NOT EXISTS rule_statistics_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_return REAL NOT NULL,
    avg_win REAL NOT NULL,
    avg_loss REAL NOT NULL,
    profit_factor REAL NOT NULL,
    expectancy REAL NOT NULL,
    performance_score REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rule_weights_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    weight REAL NOT NULL,
    previous_weight REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_updates_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine_version TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    statistics_json TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rule_statistics_v2_lookup
ON rule_statistics_v2 (rule_name, performance_score, created_at);

CREATE INDEX IF NOT EXISTS idx_rule_weights_v2_lookup
ON rule_weights_v2 (rule_name, created_at);
