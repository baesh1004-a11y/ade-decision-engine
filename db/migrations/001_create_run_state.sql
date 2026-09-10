CREATE TABLE IF NOT EXISTS ade_runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    market TEXT NOT NULL,
    ticker TEXT,
    status TEXT NOT NULL CHECK(status IN
        ('CREATED','VALIDATING','RUNNING','SUCCEEDED','PARTIAL_SUCCESS','FAILED','CANCELLED')),
    request_json TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    idempotency_key TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ade_runs_idempotency
    ON ade_runs(kind, market, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ade_runs_market_created ON ade_runs(market, created_at DESC);
CREATE TABLE IF NOT EXISTS ade_run_stages (
    run_id TEXT NOT NULL REFERENCES ade_runs(run_id),
    name TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED')),
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    PRIMARY KEY(run_id, name),
    UNIQUE(run_id, ordinal)
);
CREATE TABLE IF NOT EXISTS ade_run_artifacts (
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, stage_name, name),
    FOREIGN KEY(run_id, stage_name) REFERENCES ade_run_stages(run_id, name)
);
CREATE TABLE IF NOT EXISTS ade_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
