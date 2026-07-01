-- ADE migration 003: Probability Calibration

CREATE TABLE IF NOT EXISTS probability_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    prediction_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    predicted_probability REAL NOT NULL,
    actual_outcome INTEGER NOT NULL,
    expected_return REAL NOT NULL,
    realized_return REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS probability_calibration_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine_version TEXT NOT NULL,
    horizon TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    bins_json TEXT NOT NULL,
    global_bias REAL NOT NULL,
    brier_score REAL NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_probability_observations_lookup
ON probability_observations (ticker, prediction_date, horizon, predicted_probability, actual_outcome);

CREATE INDEX IF NOT EXISTS idx_probability_calibration_tables_lookup
ON probability_calibration_tables (horizon, created_at);
