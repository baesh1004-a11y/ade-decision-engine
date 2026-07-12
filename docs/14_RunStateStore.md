# Run State Store v1

## 1. 목적

Run State Store는 Integration Orchestrator가 생성하는 실행 상태를 SQLite에 일관되게 저장하고 조회하는 영속성 계층이다.

이 계층은 투자 판단을 생성하지 않는다. 다음 정보만 책임진다.

- 실행 단위(`run`)의 생성, 시작, 완료, 실패 상태
- 단계 단위(`stage`)의 실행 순서, 시도 횟수, 처리 시간, 오류
- 입력·출력·리포트 산출물의 스키마 버전과 무결성 해시
- 동일 요청의 중복 실행 방지와 감사 추적

## 2. 책임 경계

### 담당

- 트랜잭션 기반 실행 상태 기록
- 허용된 상태 전이 검증
- run/stage/artifact 원자적 저장
- 실행 이력과 최근 성공 결과 조회
- 멱등성 키와 correlation ID 관리
- JSON payload 직렬화 및 SHA-256 해시 생성

### 담당하지 않음

- 단계 실행 순서 결정
- 실패 재시도 여부 결정
- 시장 데이터 품질 판단
- Signal, Risk, Decision 결과 수정
- 주문 또는 체결 상태의 업무적 해석

## 3. 아키텍처

```text
Integration Orchestrator
        ↓
RunStateRepository Interface
        ↓
SQLiteRunStateStore
   ├─ Transaction Manager
   ├─ State Transition Guard
   ├─ JSON Serializer
   ├─ Hash Generator
   └─ Query Mapper
        ↓
SQLite
   ├─ ade_runs
   ├─ ade_run_stages
   └─ ade_run_artifacts
```

Orchestrator는 저장 기술에 의존하지 않고 `RunStateRepository` 인터페이스만 사용한다. 초기 구현은 SQLite이며 이후 PostgreSQL로 교체할 수 있어야 한다.

## 4. 상태 모델

### Run 상태 전이

```text
CREATED → VALIDATING → RUNNING → SUCCEEDED
                           ├──→ PARTIAL_SUCCESS
                           ├──→ FAILED
                           └──→ CANCELLED
```

허용하지 않는 예:

- `SUCCEEDED → RUNNING`
- `FAILED → SUCCEEDED`
- `CREATED → SUCCEEDED`

재실행은 기존 run을 되살리지 않고 새로운 `run_id`를 생성한다.

### Stage 상태 전이

```text
PENDING → RUNNING → SUCCEEDED
                  ├──→ RETRYING → RUNNING
                  ├──→ FAILED
                  └──→ SKIPPED
```

`attempt`는 실제 실행 시작 시 증가한다. `SKIPPED`는 선행 단계 실패 등 실행되지 않은 경우에만 사용한다.

## 5. 데이터베이스

### 5.1 `ade_runs`

```sql
CREATE TABLE IF NOT EXISTS ade_runs (
    run_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT,
    run_mode TEXT NOT NULL,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL,
    result_summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (status IN (
        'CREATED','VALIDATING','RUNNING','SUCCEEDED',
        'PARTIAL_SUCCESS','FAILED','CANCELLED'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ade_runs_idempotency
ON ade_runs(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ade_runs_ticker_started
ON ade_runs(ticker, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_ade_runs_status_started
ON ade_runs(status, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_ade_runs_correlation
ON ade_runs(correlation_id);
```

### 5.2 `ade_run_stages`

```sql
CREATE TABLE IF NOT EXISTS ade_run_stages (
    stage_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    input_hash TEXT,
    output_hash TEXT,
    error_type TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES ade_runs(run_id) ON DELETE CASCADE,
    UNIQUE (run_id, stage_name),
    CHECK (status IN (
        'PENDING','RUNNING','RETRYING','SUCCEEDED','FAILED','SKIPPED'
    )),
    CHECK (attempt >= 0),
    CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX IF NOT EXISTS ix_ade_run_stages_run_sequence
ON ade_run_stages(run_id, sequence_no);

CREATE INDEX IF NOT EXISTS ix_ade_run_stages_status
ON ade_run_stages(status, updated_at DESC);
```

### 5.3 `ade_run_artifacts`

```sql
CREATE TABLE IF NOT EXISTS ade_run_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES ade_runs(run_id) ON DELETE CASCADE,
    CHECK (artifact_type IN ('INPUT','OUTPUT','REPORT','LOG'))
);

CREATE INDEX IF NOT EXISTS ix_ade_run_artifacts_run_stage
ON ade_run_artifacts(run_id, stage_name, artifact_type);
```

민감정보, API 키, 접근 토큰, 계좌 인증정보는 payload에 저장하지 않는다.

## 6. 도메인 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    run_id: str
    stage_name: str
    sequence_no: int
    status: str
    attempt: int = 0
    duration_ms: int | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    correlation_id: str
    mode: str
    market: str
    ticker: str
    status: str
    requested_by: str
    config: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

## 7. Repository 인터페이스

```python
from typing import Protocol, Any


class RunStateRepository(Protocol):
    def create_run(self, request: Any, idempotency_key: str | None = None) -> RunRecord: ...
    def transition_run(self, run_id: str, target_status: str) -> RunRecord: ...
    def create_stage(self, run_id: str, name: str, sequence_no: int) -> StageResult: ...
    def start_stage(self, run_id: str, name: str) -> StageResult: ...
    def complete_stage(self, run_id: str, name: str, output: Any) -> StageResult: ...
    def fail_stage(self, run_id: str, name: str, exc: Exception) -> StageResult: ...
    def skip_stage(self, run_id: str, name: str, reason: str) -> StageResult: ...
    def save_artifact(
        self,
        run_id: str,
        stage_name: str,
        artifact_type: str,
        schema_version: str,
        payload: Any,
    ) -> str: ...
    def get_run(self, run_id: str) -> RunRecord | None: ...
    def list_stages(self, run_id: str) -> list[StageResult]: ...
```

## 8. 핵심 알고리즘

### 8.1 실행 생성

```text
RunRequest 정규화
→ 안정적 JSON 직렬화
→ 선택적으로 idempotency_key 계산
→ BEGIN IMMEDIATE
→ 동일 멱등성 키 조회
→ 존재하면 기존 run 반환
→ 없으면 CREATED 상태 INSERT
→ stage plan을 PENDING 상태로 일괄 INSERT
→ COMMIT
```

### 8.2 Stage 시작

```text
현재 stage 조회
→ 현재 상태가 PENDING 또는 RETRYING인지 확인
→ 선행 stage 성공 여부는 Orchestrator가 검증
→ attempt + 1
→ started_at 기록
→ RUNNING 전환
→ COMMIT
```

### 8.3 Stage 완료

```text
현재 상태 RUNNING 확인
→ output을 canonical JSON으로 직렬화
→ SHA-256 output_hash 계산
→ artifact 저장
→ duration_ms 계산
→ stage를 SUCCEEDED로 변경
→ COMMIT
```

Stage 상태와 산출물 저장은 같은 트랜잭션에서 처리한다.

### 8.4 최종 Run 상태 결정 지원

Store는 최종 상태를 스스로 판단하지 않는다. Orchestrator가 결정한 상태가 허용된 전이인지 검증한 뒤 저장한다.

## 9. 참조 코드

```python
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class InvalidStateTransition(ValueError):
    pass


class SQLiteRunStateStore:
    RUN_TRANSITIONS = {
        "CREATED": {"VALIDATING", "CANCELLED", "FAILED"},
        "VALIDATING": {"RUNNING", "FAILED", "CANCELLED"},
        "RUNNING": {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"},
        "SUCCEEDED": set(),
        "PARTIAL_SUCCESS": set(),
        "FAILED": set(),
        "CANCELLED": set(),
    }

    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def transition_run(self, run_id: str, target: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT status FROM ade_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"run not found: {run_id}")

            current = row["status"]
            if target not in self.RUN_TRANSITIONS[current]:
                raise InvalidStateTransition(f"{current} -> {target}")

            now = utc_now()
            finished_at = now if target in {
                "SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"
            } else None
            conn.execute(
                """
                UPDATE ade_runs
                   SET status = ?,
                       started_at = CASE
                           WHEN ? = 'RUNNING' AND started_at IS NULL THEN ?
                           ELSE started_at
                       END,
                       finished_at = COALESCE(?, finished_at),
                       updated_at = ?
                 WHERE run_id = ?
                """,
                (target, target, now, finished_at, now, run_id),
            )
            return {"run_id": run_id, "status": target}

    def save_artifact(
        self,
        run_id: str,
        stage_name: str,
        artifact_type: str,
        schema_version: str,
        payload: Any,
    ) -> str:
        artifact_id = str(uuid4())
        serialized = canonical_json(payload)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO ade_run_artifacts (
                    artifact_id, run_id, stage_name, artifact_type,
                    schema_version, payload_json, payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id, run_id, stage_name, artifact_type,
                    schema_version, serialized, digest, utc_now(),
                ),
            )
        return artifact_id
```

실제 구현에서는 schema 생성 코드를 migration 파일로 분리하고, 오류 메시지 길이 제한 및 민감정보 마스킹을 추가한다.

## 10. 파일 구조

```text
core/
├── run_models.py
├── run_repository.py
└── run_state_store.py

db/
└── migrations/
    └── 001_create_run_state.sql

tests/
├── test_run_state_store_unit.py
├── test_run_state_transitions.py
├── test_run_state_transactions.py
├── test_run_state_idempotency.py
└── test_run_state_integration.py
```

## 11. 테스트 계획

### 단위 테스트

- run 생성 시 `CREATED` 상태 확인
- 동일 idempotency key 재요청 시 중복 INSERT 방지
- 허용 상태 전이 성공
- 금지 상태 전이 시 `InvalidStateTransition`
- stage 시작 시 attempt 증가
- payload JSON 키 순서와 무관하게 동일 해시 생성
- 존재하지 않는 run/stage 처리
- 음수 duration 및 attempt 제약조건 확인

### 트랜잭션 테스트

- artifact 저장 실패 시 stage 완료도 rollback
- stage 완료 실패 시 artifact가 남지 않음
- foreign key 위반 시 전체 rollback
- DB lock 발생 시 busy timeout 후 명확한 오류 반환

### 통합 테스트

```text
Run 생성
→ 4개 Stage PENDING 생성
→ Run RUNNING 전환
→ Stage 1 SUCCEEDED + artifact 저장
→ Stage 2 FAILED
→ Stage 3, 4 SKIPPED
→ Run FAILED 전환
→ DB 조회 결과와 Orchestrator 결과 비교
```

확인 항목:

- stage 실행 순서 보존
- 오류 유형과 메시지 기록
- run error_count 갱신
- 입력/출력 해시 존재
- 최종 상태와 종료 시간 일치

### 복구 테스트

- 프로세스 강제 종료 후 `RUNNING` 상태 조회
- 설정된 stale threshold 초과 run을 복구 대상으로 식별
- 자동 성공 처리 금지
- 운영자 또는 복구 정책을 통해 `FAILED`/`CANCELLED` 전환

### 성능 기준

초기 단일 프로세스 SQLite 기준:

- run 생성 p95 50ms 이하
- stage 상태 갱신 p95 30ms 이하
- 단일 run 100개 artifact 저장 가능
- 최근 1,000개 run 조회 200ms 이하

성능 수치는 구현 환경에서 측정 후 조정한다.

## 12. 보안 및 감사 원칙

- 인증정보와 토큰은 저장하지 않는다.
- payload 저장 전 민감 필드를 제거한다.
- 오류 메시지는 최대 길이를 제한한다.
- 모든 시간은 UTC ISO-8601로 저장한다.
- 생성된 artifact는 수정하지 않고 새 버전으로 추가한다.
- SQLite 파일 권한은 최소 권한으로 제한한다.
- WAL 모드는 동시 조회가 필요할 때만 명시적으로 활성화한다.

## 13. 구현 순서

1. migration SQL 작성
2. `RunRecord`, `StageResult` 모델 구현
3. Repository 인터페이스 정의
4. SQLite 연결 및 트랜잭션 관리
5. run/stage 상태 전이 구현
6. artifact 저장과 해시 구현
7. 멱등성 처리
8. Orchestrator adapter 연결
9. fixture 기반 통합 테스트

## 14. 완료 기준

- SQLite migration으로 3개 테이블 생성
- run/stage의 허용 상태 전이만 저장
- stage 결과와 artifact가 원자적으로 기록
- 동일 멱등성 요청의 중복 실행 방지
- 기존 Orchestrator 참조 코드가 Repository 인터페이스를 통해 동작
- fixture 기반 실패·성공 통합 테스트 통과
- 민감정보가 DB payload에 포함되지 않음
