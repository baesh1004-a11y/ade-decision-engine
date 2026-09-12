"""Transactional run ledger shared by CLI, API and recommendation services."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from core.run_models import (
    TERMINAL_RUNS,
    TERMINAL_STAGES,
    RunRequest,
    RunResult,
    StageResult,
    canonical_json,
    content_hash,
    utc_now,
)


class RunStateError(ValueError):
    pass


class RunStateStore:
    def __init__(self, database: str | Path | sqlite3.Connection) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        if self._owns_connection:
            path = Path(database)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path), timeout=10)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        else:
            self.conn = database
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        if self.conn.in_transaction:
            raise RunStateError(
                "Initialize the run ledger before opening a transaction"
            )
        migration = (
            Path(__file__).resolve().parents[1]
            / "db/migrations/001_create_run_state.sql"
        )
        with self.atomic():
            for statement in migration.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    self.conn.execute(statement)
            self.conn.execute(
                "INSERT OR IGNORE INTO ade_schema_migrations VALUES(1, ?)", (utc_now(),)
            )

    @contextmanager
    def atomic(self):
        """Nested operations never commit or roll back their caller's transaction."""
        nested = self.conn.in_transaction
        savepoint = "ade_" + uuid4().hex
        self.conn.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
        try:
            yield
            if nested:
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                self.conn.commit()
        except BaseException:
            if nested:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                self.conn.rollback()
            raise

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def create(self, request: RunRequest, stages: tuple[str, ...]) -> str:
        if not request.kind or request.market not in {"kr", "us"} or not request.run_id:
            raise RunStateError("A run requires kind, market (kr/us), and run_id")
        if not stages or len(set(stages)) != len(stages) or not all(stages):
            raise RunStateError("Stage names must be nonempty and unique")
        request_hash = content_hash(
            {"request": request.fingerprint(), "stages": stages}
        )
        with self.atomic():
            if request.idempotency_key:
                existing = self.conn.execute(
                    "SELECT run_id, request_hash FROM ade_runs WHERE kind=? AND market=? AND idempotency_key=?",
                    (request.kind, request.market, request.idempotency_key),
                ).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise RunStateError(
                            "Idempotency key already belongs to a different request"
                        )
                    return str(existing["run_id"])
            self.conn.execute(
                "INSERT INTO ade_runs(run_id,kind,market,ticker,status,request_json,request_hash,idempotency_key,created_at) "
                "VALUES(?,?,?,?, 'CREATED',?,?,?,?)",
                (
                    request.run_id,
                    request.kind,
                    request.market,
                    request.ticker,
                    canonical_json(asdict(request)),
                    request_hash,
                    request.idempotency_key,
                    utc_now(),
                ),
            )
            self.conn.executemany(
                "INSERT INTO ade_run_stages(run_id,name,ordinal,status) VALUES(?,?,?,'PENDING')",
                [(request.run_id, name, index) for index, name in enumerate(stages)],
            )
        return request.run_id

    def _run(self, run_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM ade_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise RunStateError("Unknown run")
        return row

    def start(self, run_id: str) -> None:
        with self.atomic():
            if self._run(run_id)["status"] != "CREATED":
                raise RunStateError(
                    "Only a new run can start; reruns need a new run_id"
                )
            self.conn.execute(
                "UPDATE ade_runs SET status='VALIDATING' WHERE run_id=?", (run_id,)
            )
            self.conn.execute(
                "UPDATE ade_runs SET status='RUNNING',started_at=? WHERE run_id=?",
                (utc_now(), run_id),
            )

    def start_stage(self, run_id: str, name: str) -> None:
        with self.atomic():
            if self._run(run_id)["status"] != "RUNNING":
                raise RunStateError("Stages can start only inside a running run")
            stage = self.conn.execute(
                "SELECT * FROM ade_run_stages WHERE run_id=? AND name=?", (run_id, name)
            ).fetchone()
            if stage is None or stage["status"] != "PENDING":
                raise RunStateError("Only a pending stage can start")
            blocked = self.conn.execute(
                "SELECT 1 FROM ade_run_stages WHERE run_id=? AND ordinal<? AND status NOT IN ('SUCCEEDED','SKIPPED')",
                (run_id, stage["ordinal"]),
            ).fetchone()
            if blocked:
                raise RunStateError(
                    "Previous stages must finish before starting the next stage"
                )
            self.conn.execute(
                "UPDATE ade_run_stages SET status='RUNNING',started_at=? WHERE run_id=? AND name=?",
                (utc_now(), run_id, name),
            )

    def complete_stage(
        self, run_id: str, name: str, artifacts: dict | None = None
    ) -> None:
        # Serialize before touching the DB: invalid numbers cannot leave partial artifacts.
        payloads = [
            (key, canonical_json(value), content_hash(value))
            for key, value in (artifacts or {}).items()
        ]
        with self.atomic():
            if self._run(run_id)["status"] != "RUNNING":
                raise RunStateError("Terminal runs are immutable")
            cursor = self.conn.execute(
                "UPDATE ade_run_stages SET status='SUCCEEDED',finished_at=? WHERE run_id=? AND name=? AND status='RUNNING'",
                (utc_now(), run_id, name),
            )
            if cursor.rowcount != 1:
                raise RunStateError("Only a running stage can complete")
            self.conn.executemany(
                "INSERT INTO ade_run_artifacts VALUES(?,?,?,?,?,?)",
                [
                    (run_id, name, key, payload, digest, utc_now())
                    for key, payload, digest in payloads
                ],
            )

    def fail_stage(self, run_id: str, name: str, error: str) -> None:
        with self.atomic():
            if self._run(run_id)["status"] != "RUNNING":
                raise RunStateError("Terminal runs are immutable")
            cursor = self.conn.execute(
                "UPDATE ade_run_stages SET status='FAILED',finished_at=?,error=? "
                "WHERE run_id=? AND name=? AND status='RUNNING'",
                (utc_now(), error, run_id, name),
            )
            if cursor.rowcount != 1:
                raise RunStateError("Only a running stage can fail")

    def finish(
        self, run_id: str, status: str = "SUCCEEDED", error: str | None = None
    ) -> RunResult:
        if status not in TERMINAL_RUNS:
            raise RunStateError("Invalid terminal run status")
        with self.atomic():
            allowed = {"RUNNING"}
            if status in {"FAILED", "CANCELLED"}:
                allowed.update({"CREATED", "VALIDATING"})
            if self._run(run_id)["status"] not in allowed:
                raise RunStateError("Only running runs can finish")
            if status in {"FAILED", "CANCELLED"}:
                self.conn.execute(
                    "UPDATE ade_run_stages SET status=CASE WHEN status='RUNNING' THEN 'FAILED' ELSE 'SKIPPED' END, "
                    "finished_at=?, error=? WHERE run_id=? AND status IN ('RUNNING','PENDING')",
                    (utc_now(), error, run_id),
                )
            states = [
                row[0]
                for row in self.conn.execute(
                    "SELECT status FROM ade_run_stages WHERE run_id=?", (run_id,)
                )
            ]
            if any(state not in TERMINAL_STAGES for state in states):
                raise RunStateError("All stages must be terminal before finishing")
            if status == "SUCCEEDED" and "FAILED" in states:
                raise RunStateError("A run with failed stages cannot succeed")
            self.conn.execute(
                "UPDATE ade_runs SET status=?,finished_at=?,error=? WHERE run_id=?",
                (status, utc_now(), error, run_id),
            )
        return self.get(run_id)

    def get(self, run_id: str) -> RunResult:
        run = self._run(run_id)
        stages = []
        output = {}
        for row in self.conn.execute(
            "SELECT * FROM ade_run_stages WHERE run_id=? ORDER BY ordinal", (run_id,)
        ):
            artifacts = {}
            for artifact in self.conn.execute(
                "SELECT * FROM ade_run_artifacts WHERE run_id=? AND stage_name=?",
                (run_id, row["name"]),
            ):
                payload = json.loads(artifact["payload_json"])
                if content_hash(payload) != artifact["content_hash"]:
                    raise RunStateError("Run artifact integrity check failed")
                artifacts[artifact["name"]] = payload
            if isinstance(artifacts.get("output"), dict):
                output = artifacts["output"]
            stages.append(
                StageResult(
                    row["name"],
                    row["status"],
                    row["started_at"],
                    row["finished_at"],
                    row["error"],
                    artifacts,
                )
            )
        return RunResult(
            run_id,
            run["kind"],
            run["market"],
            run["status"],
            run["created_at"],
            run["finished_at"],
            tuple(stages),
            output,
            run["error"],
        )

    def recent(self, market: str, limit: int = 30) -> list[dict]:
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT run_id,kind,market,ticker,status,created_at,started_at,finished_at,error FROM ade_runs "
                "WHERE market=? ORDER BY created_at DESC LIMIT ?",
                (market, max(1, min(int(limit), 200))),
            )
        ]
