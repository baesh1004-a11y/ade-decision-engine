# Scheduler & Trigger Engine v1

## 1. 목적

Scheduler & Trigger Engine은 ADE의 분석, 장중 점검, 주문 전 검증, 장 마감 처리, 리포트, 재처리, 백테스트 실행을 **시장 일정과 운영 정책에 맞게 생성·통제하는 실행 진입 계층**이다.

이 엔진은 투자 판단을 직접 생성하지 않는다. 실행해야 할 작업을 결정하고 Integration Orchestrator에 표준 `RunRequest`를 전달한다.

핵심 목표:

- 거래소 달력과 시장 세션을 반영한 실행 예약
- 시간 기반, 이벤트 기반, 수동 기반 Trigger 통합
- 동일 작업의 중복 실행 방지
- 지연, 누락, 휴장, 조기 폐장에 대한 안전한 처리
- 재처리와 백필 실행의 범위 통제
- LIVE/PAPER/BACKTEST 모드별 실행 제한
- 모든 Trigger와 실행 생성 이력의 감사 가능성 확보

## 2. 책임 경계

### 담당

- 거래일, 휴장일, 조기 폐장, 시장 세션 판정
- 시간 기반 Schedule 등록과 다음 실행 시각 계산
- 데이터 도착, 품질 통과, 정책 활성화 등 이벤트 Trigger 처리
- Trigger를 `RunRequest`로 변환
- 멱등성 키 생성과 중복 실행 억제
- 지연 실행, 누락 실행, 재시도, 백필 정책 적용
- 동시 실행 제한과 실행 슬롯 관리
- Trigger 상태, 실행 요청, 실패 사유 기록
- Orchestrator 호출 전 정책·모드·시장 상태 확인

### 담당하지 않음

- Signal, Risk, Decision 판단 생성
- 주문 가격과 수량 결정
- 시장 데이터 품질 자체 평가
- 정책 승인 여부 최종 판정
- 실행 단계 내부 재시도
- 브로커 주문 전송
- Report 내용 생성

Scheduler는 **언제, 무엇을 실행할지** 책임지고 Orchestrator는 **어떻게 실행할지** 책임진다.

## 3. 아키텍처

```text
Clock / Exchange Calendar / Event Bus / Operator
                     ↓
          Scheduler & Trigger Engine
          ├─ Schedule Registry
          ├─ Market Calendar Service
          ├─ Trigger Evaluator
          ├─ Idempotency Guard
          ├─ Concurrency Guard
          ├─ Misfire Handler
          ├─ Backfill Planner
          ├─ Dispatch Queue
          └─ Trigger Repository
                     ↓
           Integration Orchestrator
                     ↓
 DataHub → Data Quality → Signal → Risk → Decision
                     ↓
       Order → Execution → Backtest → Report
```

외부 연동:

```text
Configuration & Policy Engine
    └─ 실행 모드, 허용 시간, 동시 실행 수, 재처리 정책

Data Snapshot & Lineage Engine
    └─ 데이터 도착 이벤트, snapshot_id, dataset_version

Audit & Compliance Engine
    └─ Trigger 생성, 변경, 수동 실행, 백필 감사 이벤트

Run State Store
    └─ 생성된 run_id, 상태, idempotency_key 조회
```

## 4. Trigger 유형

### 4.1 시간 기반 Trigger

| 유형 | 예시 |
|---|---|
| `CRON` | 매 거래일 08:40 사전 분석 |
| `MARKET_OFFSET` | 장 시작 10분 전, 장 마감 5분 후 |
| `INTERVAL` | 장중 5분마다 위험 점검 |
| `ONE_TIME` | 특정 시각 단발 실행 |

### 4.2 이벤트 기반 Trigger

| 유형 | 발생 조건 |
|---|---|
| `DATA_READY` | 필수 시장 데이터 snapshot 잠금 완료 |
| `QUALITY_PASSED` | Data Quality 검사 통과 |
| `POLICY_ACTIVATED` | 새 정책 버전 활성화 |
| `RUN_COMPLETED` | 선행 실행 완료 |
| `ORDER_FILLED` | 체결 후 포지션·리스크 재평가 필요 |
| `CORRECTION_RECEIVED` | 정정 데이터로 영향 실행 재처리 필요 |

### 4.3 운영자 Trigger

| 유형 | 설명 |
|---|---|
| `MANUAL` | 운영자가 단일 실행 요청 |
| `REPLAY` | 기존 Trigger payload 재생 |
| `BACKFILL` | 기간과 대상 범위를 제한한 과거 실행 |
| `RECOVERY` | 장애 복구 후 누락된 실행 재생성 |

## 5. 시장 세션 모델

```text
CLOSED
  ↓
PRE_OPEN
  ↓
OPENING_AUCTION
  ↓
CONTINUOUS
  ↓
CLOSING_AUCTION
  ↓
POST_CLOSE
  ↓
CLOSED
```

시장별 세션은 코드에 하드코딩하지 않고 `exchange_calendars`와 정책 스냅샷으로 관리한다.

예시:

```python
@dataclass(frozen=True)
class MarketSession:
    market: str
    trading_date: date
    timezone: str
    is_trading_day: bool
    open_at: datetime | None
    close_at: datetime | None
    pre_open_at: datetime | None = None
    post_close_at: datetime | None = None
    early_close: bool = False
    calendar_version: str = "v1"
```

필수 규칙:

- 모든 내부 시각은 UTC로 저장한다.
- 사용자·거래소 표시 시각만 현지 시간대로 변환한다.
- 휴장일에는 거래 세션 Trigger를 생성하지 않는다.
- 조기 폐장일은 고정 시각이 아니라 실제 `close_at` 기준으로 offset을 계산한다.
- 달력 버전 변경 시 이미 생성된 Trigger는 자동 수정하지 않고 변경 이력을 남긴다.
- LIVE 주문 관련 Trigger는 시장 상태가 허용 세션인지 재확인한다.

## 6. 상태 모델

### 6.1 Schedule 상태

```text
DRAFT → ACTIVE → PAUSED → ACTIVE
               └→ RETIRED
```

### 6.2 Trigger 상태

```text
CREATED → EVALUATING → READY → DISPATCHED → ACKNOWLEDGED
                    ├→ SUPPRESSED
                    ├→ MISFIRED
                    ├→ FAILED
                    └→ CANCELLED
```

### 6.3 Dispatch 상태

```text
PENDING → CLAIMED → SENT → ACCEPTED
                 ├→ RETRY_WAIT
                 ├→ DEAD_LETTER
                 └→ CANCELLED
```

상태 정의:

- `SUPPRESSED`: 휴장, 중복, 정책 차단, 동시 실행 제한 등으로 실행하지 않음
- `MISFIRED`: 허용 지연 시간을 초과해 예정 시각에 실행되지 못함
- `FAILED`: Trigger 평가 또는 RunRequest 생성 실패
- `DEAD_LETTER`: Dispatch 재시도 한도 초과

## 7. 입력·출력 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ScheduleDefinition:
    schedule_id: str
    name: str
    trigger_type: str
    run_mode: str
    market: str
    expression: str
    timezone: str
    target_stage: str = "FULL_PIPELINE"
    enabled: bool = True
    misfire_policy: str = "SKIP"
    max_lateness_seconds: int = 300
    max_concurrent_runs: int = 1
    policy_version: str = "v1"
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TriggerEvent:
    trigger_id: str
    schedule_id: str | None
    trigger_type: str
    event_key: str
    occurred_at: datetime
    effective_at: datetime
    market: str
    ticker: str | None
    payload: dict[str, Any]
    correlation_id: str


@dataclass(frozen=True)
class DispatchRequest:
    dispatch_id: str
    trigger_id: str
    idempotency_key: str
    run_request: dict[str, Any]
    available_at: datetime
    priority: int = 100
    attempt: int = 0
```

Scheduler의 출력은 Orchestrator용 표준 요청이다.

```python
RunRequest(
    mode="PAPER",
    market="KR",
    ticker="005930",
    start=None,
    end=None,
    account_balance=10_000_000,
    cash=9_000_000,
    market_regime="SIDEWAY",
    correlation_id="corr-...",
    requested_by="scheduler:pre_open_analysis",
)
```

추가 metadata:

```python
{
    "trigger_id": "trg-...",
    "schedule_id": "sch-...",
    "scheduled_for": "2026-07-16T23:40:00Z",
    "calendar_version": "KRX-2026.07",
    "policy_snapshot_id": "pol-...",
    "data_snapshot_id": "snap-...",
    "idempotency_key": "sha256:..."
}
```

## 8. 데이터베이스

### 8.1 `ade_schedules`

```sql
CREATE TABLE IF NOT EXISTS ade_schedules (
    schedule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    run_mode TEXT NOT NULL,
    market TEXT NOT NULL,
    expression TEXT NOT NULL,
    timezone TEXT NOT NULL,
    target_stage TEXT NOT NULL,
    status TEXT NOT NULL,
    misfire_policy TEXT NOT NULL,
    max_lateness_seconds INTEGER NOT NULL DEFAULT 300,
    max_concurrent_runs INTEGER NOT NULL DEFAULT 1,
    policy_version TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (trigger_type IN (
        'CRON','MARKET_OFFSET','INTERVAL','ONE_TIME',
        'DATA_READY','QUALITY_PASSED','POLICY_ACTIVATED',
        'RUN_COMPLETED','ORDER_FILLED','CORRECTION_RECEIVED'
    )),
    CHECK (status IN ('DRAFT','ACTIVE','PAUSED','RETIRED')),
    CHECK (misfire_policy IN ('SKIP','FIRE_ONCE','CATCH_UP','FAIL')),
    CHECK (max_lateness_seconds >= 0),
    CHECK (max_concurrent_runs >= 1)
);

CREATE INDEX IF NOT EXISTS ix_ade_schedules_active_market
ON ade_schedules(status, market, trigger_type);
```

### 8.2 `ade_triggers`

```sql
CREATE TABLE IF NOT EXISTS ade_triggers (
    trigger_id TEXT PRIMARY KEY,
    schedule_id TEXT,
    trigger_type TEXT NOT NULL,
    event_key TEXT NOT NULL,
    market TEXT NOT NULL,
    ticker TEXT,
    status TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    evaluated_at TEXT,
    dispatched_at TEXT,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    suppression_reason TEXT,
    error_type TEXT,
    error_message TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES ade_schedules(schedule_id),
    UNIQUE (idempotency_key),
    CHECK (status IN (
        'CREATED','EVALUATING','READY','DISPATCHED','ACKNOWLEDGED',
        'SUPPRESSED','MISFIRED','FAILED','CANCELLED'
    ))
);

CREATE INDEX IF NOT EXISTS ix_ade_triggers_schedule_time
ON ade_triggers(schedule_id, scheduled_for DESC);

CREATE INDEX IF NOT EXISTS ix_ade_triggers_status_time
ON ade_triggers(status, scheduled_for);

CREATE INDEX IF NOT EXISTS ix_ade_triggers_correlation
ON ade_triggers(correlation_id);
```

### 8.3 `ade_dispatch_queue`

```sql
CREATE TABLE IF NOT EXISTS ade_dispatch_queue (
    dispatch_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    available_at TEXT NOT NULL,
    claimed_by TEXT,
    claimed_at TEXT,
    lease_expires_at TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    run_id TEXT,
    request_json TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (trigger_id) REFERENCES ade_triggers(trigger_id) ON DELETE CASCADE,
    UNIQUE (trigger_id),
    CHECK (status IN (
        'PENDING','CLAIMED','SENT','ACCEPTED','RETRY_WAIT',
        'DEAD_LETTER','CANCELLED'
    )),
    CHECK (attempt >= 0),
    CHECK (max_attempts >= 1)
);

CREATE INDEX IF NOT EXISTS ix_ade_dispatch_ready
ON ade_dispatch_queue(status, available_at, priority);
```

### 8.4 `ade_market_calendars`

```sql
CREATE TABLE IF NOT EXISTS ade_market_calendars (
    market TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    is_trading_day INTEGER NOT NULL,
    pre_open_at TEXT,
    open_at TEXT,
    close_at TEXT,
    post_close_at TEXT,
    early_close INTEGER NOT NULL DEFAULT 0,
    calendar_version TEXT NOT NULL,
    source TEXT NOT NULL,
    loaded_at TEXT NOT NULL,
    PRIMARY KEY (market, trading_date, calendar_version)
);
```

### 8.5 `ade_backfill_jobs`

```sql
CREATE TABLE IF NOT EXISTS ade_backfill_jobs (
    backfill_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    market TEXT NOT NULL,
    ticker_scope_json TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    max_runs INTEGER NOT NULL,
    generated_runs INTEGER NOT NULL DEFAULT 0,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    CHECK (status IN (
        'REQUESTED','APPROVED','RUNNING','COMPLETED',
        'PARTIAL','REJECTED','CANCELLED','FAILED'
    )),
    CHECK (max_runs >= 1)
);
```

## 9. 핵심 알고리즘

### 9.1 다음 실행 시각 계산

```text
활성 Schedule 조회
→ 거래소 달력 버전 확인
→ 기준 시각을 Schedule timezone으로 변환
→ CRON 또는 시장 offset 계산
→ 휴장일 여부 확인
→ 조기 폐장 반영
→ UTC scheduled_for 생성
→ 다음 Trigger 후보 저장
```

`MARKET_OFFSET` 예:

```python
scheduled_for = market_session.open_at - timedelta(minutes=10)
```

고정 `08:50`으로 계산하지 않는다.

### 9.2 Trigger 평가

```text
Trigger CREATED
→ EVALUATING 전환
→ Schedule ACTIVE 확인
→ 시장/세션 조건 확인
→ 정책 스냅샷 확인
→ 필수 데이터 snapshot 확인
→ idempotency_key 계산
→ 동일 key 존재 여부 확인
→ 동시 실행 수 확인
→ 지연 시간과 misfire 정책 평가
→ READY 또는 SUPPRESSED/MISFIRED/FAILED 결정
```

### 9.3 멱등성 키

```python
def build_idempotency_key(
    schedule_id: str,
    effective_time: datetime,
    market: str,
    ticker: str | None,
    run_mode: str,
    policy_snapshot_id: str,
    data_snapshot_id: str | None,
) -> str:
    value = {
        "schedule_id": schedule_id,
        "effective_time": effective_time.isoformat(),
        "market": market,
        "ticker": ticker,
        "run_mode": run_mode,
        "policy_snapshot_id": policy_snapshot_id,
        "data_snapshot_id": data_snapshot_id,
    }
    return payload_hash(value)
```

시간 기반 반복 실행은 `effective_time`을 스케줄 슬롯 단위로 정규화한다.

예:

- 5분 interval: `10:03:41` 이벤트를 `10:00:00` 슬롯으로 정규화
- 장 마감 Trigger: 실제 달력의 해당 거래일 `close_at` 사용
- 데이터 이벤트: 원천 event ID와 snapshot ID 포함

### 9.4 Misfire 처리

```text
lateness = now - scheduled_for

if lateness <= max_lateness:
    정상 실행
elif policy == SKIP:
    MISFIRED 후 종료
elif policy == FIRE_ONCE:
    가장 최근 누락 슬롯 1회 실행
elif policy == CATCH_UP:
    허용 범위 내 누락 슬롯 순차 생성
elif policy == FAIL:
    FAILED 및 운영 경보
```

모드별 기본값:

| 모드 | 기본 Misfire 정책 |
|---|---|
| LIVE | `SKIP` |
| PAPER | `FIRE_ONCE` |
| BACKTEST | `CATCH_UP` |
| REPORT | `FIRE_ONCE` |

LIVE에서 과거 주문 판단을 몰아서 실행하지 않는다.

### 9.5 동시 실행 제한

```text
동일 schedule_id + market + ticker의 RUNNING run 수 조회
→ max_concurrent_runs 이상이면 SUPPRESSED 또는 지연
→ portfolio 단위 mutex 정책 확인
→ LIVE 주문 경로는 account_id 단위 단일 실행
→ lease 기반 Dispatch claim
```

권장 잠금 범위:

```text
analysis:{market}:{ticker}
risk:{account_id}
order:{account_id}:{ticker}
report:{trading_date}
backfill:{schedule_id}
```

### 9.6 Dispatch Queue Claim

SQLite 초기 구현:

```sql
BEGIN IMMEDIATE;

SELECT dispatch_id
FROM ade_dispatch_queue
WHERE status IN ('PENDING','RETRY_WAIT')
  AND available_at <= :now
ORDER BY priority ASC, available_at ASC
LIMIT 1;

UPDATE ade_dispatch_queue
SET status = 'CLAIMED',
    claimed_by = :worker_id,
    claimed_at = :now,
    lease_expires_at = :lease_expires,
    attempt = attempt + 1
WHERE dispatch_id = :dispatch_id
  AND status IN ('PENDING','RETRY_WAIT');

COMMIT;
```

worker 장애 시 `lease_expires_at`이 지난 CLAIMED 항목을 재회수한다.

### 9.7 Backfill 계획

```text
요청 기간 검증
→ 최대 기간과 최대 실행 수 확인
→ LIVE 모드 금지
→ 운영자 승인 확인
→ 거래일 목록 생성
→ ticker scope 확장
→ 예상 실행 수 계산
→ max_runs 초과 시 거부
→ 낮은 우선순위 Trigger 생성
→ 현재 거래 세션 작업보다 후순위 처리
```

안전 규칙:

- Backfill은 `BACKTEST` 또는 `REPLAY` 모드만 허용
- 실브로커 adapter 호출 금지
- 현재 운영 DB와 결과 namespace 분리
- 정정 데이터 backfill은 기존 run을 수정하지 않고 새 run 생성
- 모든 재처리 결과는 원본 run ID와 lineage 연결

## 10. 정책 규칙

### ST-001 거래일 확인

거래 세션 기반 Trigger는 해당 시장의 거래일에만 실행한다.

### ST-002 세션 허용

LIVE 주문 관련 Trigger는 정책에 정의된 세션에서만 실행한다.

### ST-003 중복 실행 금지

동일 idempotency key의 Trigger 또는 Run이 존재하면 새 실행을 생성하지 않는다.

### ST-004 데이터 준비 확인

Signal 실행 전 필요한 데이터 snapshot이 잠금 상태여야 한다.

### ST-005 정책 준비 확인

실행 시점의 승인된 PolicySnapshot ID가 존재해야 한다.

### ST-006 최대 지연 제한

LIVE Trigger가 허용 지연 시간을 넘으면 과거 판단을 실행하지 않고 MISFIRED 처리한다.

### ST-007 동시 주문 실행 제한

동일 계좌의 Order/Execution 경로는 기본 1개만 허용한다.

### ST-008 휴장 억제

휴장일 Trigger 생성은 SUPPRESSED 상태와 사유를 기록한다.

### ST-009 수동 실행 감사

MANUAL, REPLAY, BACKFILL은 요청자, 사유, 승인자, 범위를 필수 기록한다.

### ST-010 Backfill 격리

Backfill은 LIVE adapter와 운영 주문 테이블을 사용할 수 없다.

### ST-011 이벤트 순서 검증

이벤트의 `occurred_at`, source sequence, snapshot version이 역행하면 보류한다.

### ST-012 달력 최신성

달력 버전이 정책 허용 기간보다 오래되면 LIVE Trigger를 차단한다.

## 11. 코드 구조

```text
core/
├── scheduler/
│   ├── __init__.py
│   ├── models.py
│   ├── calendar_service.py
│   ├── schedule_registry.py
│   ├── trigger_evaluator.py
│   ├── idempotency.py
│   ├── concurrency.py
│   ├── misfire.py
│   ├── backfill.py
│   ├── dispatcher.py
│   └── repository.py
├── orchestrator.py
├── run_models.py
└── run_repository.py

migrations/
└── 018_scheduler_trigger.sql

tests/
├── scheduler/
│   ├── test_calendar_service.py
│   ├── test_schedule_registry.py
│   ├── test_trigger_evaluator.py
│   ├── test_idempotency.py
│   ├── test_misfire.py
│   ├── test_concurrency.py
│   ├── test_dispatcher.py
│   └── test_backfill.py
├── integration/
│   └── test_scheduler_orchestrator.py
└── fixtures/
    ├── krx_calendar_2026.json
    └── scheduler_events.json
```

## 12. Repository 인터페이스

```python
from datetime import datetime
from typing import Protocol


class SchedulerRepository(Protocol):
    def create_schedule(self, definition: ScheduleDefinition) -> None: ...
    def get_schedule(self, schedule_id: str) -> ScheduleDefinition | None: ...
    def list_active_schedules(self, market: str | None = None) -> list[ScheduleDefinition]: ...
    def update_schedule_status(self, schedule_id: str, status: str) -> None: ...

    def create_trigger(self, event: TriggerEvent, idempotency_key: str) -> bool: ...
    def transition_trigger(self, trigger_id: str, target: str, reason: str | None = None) -> None: ...
    def find_trigger_by_idempotency_key(self, key: str) -> TriggerEvent | None: ...

    def enqueue(self, request: DispatchRequest) -> None: ...
    def claim_next(self, worker_id: str, now: datetime) -> DispatchRequest | None: ...
    def accept_dispatch(self, dispatch_id: str, run_id: str) -> None: ...
    def retry_dispatch(self, dispatch_id: str, available_at: datetime, error: str) -> None: ...
    def dead_letter(self, dispatch_id: str, error: str) -> None: ...
```

## 13. 핵심 서비스 코드

```python
from dataclasses import asdict
from datetime import datetime, timezone


class TriggerService:
    def __init__(
        self,
        repository,
        calendar_service,
        policy_service,
        snapshot_service,
        run_repository,
        concurrency_guard,
    ):
        self.repository = repository
        self.calendar_service = calendar_service
        self.policy_service = policy_service
        self.snapshot_service = snapshot_service
        self.run_repository = run_repository
        self.concurrency_guard = concurrency_guard

    def evaluate(self, trigger: TriggerEvent) -> DispatchRequest | None:
        self.repository.transition_trigger(trigger.trigger_id, "EVALUATING")

        schedule = self.repository.get_schedule(trigger.schedule_id)
        if schedule is None or not schedule.enabled:
            self._suppress(trigger, "SCHEDULE_INACTIVE")
            return None

        session = self.calendar_service.get_session(
            trigger.market,
            trigger.effective_at,
        )
        if not self._market_allowed(schedule, session, trigger):
            self._suppress(trigger, "MARKET_SESSION_NOT_ALLOWED")
            return None

        policy = self.policy_service.get_active_snapshot(
            mode=schedule.run_mode,
            market=trigger.market,
            effective_at=trigger.effective_at,
        )
        if policy is None:
            self._suppress(trigger, "POLICY_SNAPSHOT_MISSING")
            return None

        snapshot = self.snapshot_service.resolve_for_trigger(trigger)
        if self._requires_snapshot(schedule) and snapshot is None:
            self._suppress(trigger, "DATA_SNAPSHOT_NOT_READY")
            return None

        key = build_idempotency_key(
            schedule_id=schedule.schedule_id,
            effective_time=trigger.effective_at,
            market=trigger.market,
            ticker=trigger.ticker,
            run_mode=schedule.run_mode,
            policy_snapshot_id=policy.snapshot_id,
            data_snapshot_id=getattr(snapshot, "snapshot_id", None),
        )

        if self.repository.find_trigger_by_idempotency_key(key):
            self._suppress(trigger, "DUPLICATE_TRIGGER")
            return None

        if self.run_repository.find_by_idempotency_key(key):
            self._suppress(trigger, "DUPLICATE_RUN")
            return None

        if not self.concurrency_guard.can_dispatch(schedule, trigger):
            self._suppress(trigger, "CONCURRENCY_LIMIT")
            return None

        request = self._build_run_request(
            schedule=schedule,
            trigger=trigger,
            policy=policy,
            snapshot=snapshot,
            idempotency_key=key,
        )
        self.repository.transition_trigger(trigger.trigger_id, "READY")
        self.repository.enqueue(request)
        return request

    def _suppress(self, trigger: TriggerEvent, reason: str) -> None:
        self.repository.transition_trigger(
            trigger.trigger_id,
            "SUPPRESSED",
            reason=reason,
        )
```

Dispatcher:

```python
class DispatchWorker:
    def __init__(self, repository, orchestrator, worker_id: str):
        self.repository = repository
        self.orchestrator = orchestrator
        self.worker_id = worker_id

    def run_once(self) -> str | None:
        now = datetime.now(timezone.utc)
        item = self.repository.claim_next(self.worker_id, now)
        if item is None:
            return None

        try:
            run_result = self.orchestrator.run(item.run_request)
            self.repository.accept_dispatch(item.dispatch_id, run_result.run_id)
            self.repository.transition_trigger(item.trigger_id, "ACKNOWLEDGED")
            return run_result.run_id
        except TransientDispatchError as exc:
            self._schedule_retry(item, exc)
            return None
        except Exception as exc:
            self.repository.dead_letter(item.dispatch_id, str(exc))
            self.repository.transition_trigger(
                item.trigger_id,
                "FAILED",
                reason=str(exc),
            )
            return None
```

## 14. Orchestrator 통합

실행 흐름:

```text
Scheduler Trigger
→ 정책·달력·데이터 준비 검증
→ Dispatch Queue 저장
→ Worker claim
→ Orchestrator.run(RunRequest)
→ Run State Store에 run_id 생성
→ dispatch ACCEPTED
→ trigger ACKNOWLEDGED
```

Orchestrator는 Scheduler가 제공한 다음 필드를 보존한다.

- `trigger_id`
- `schedule_id`
- `scheduled_for`
- `idempotency_key`
- `calendar_version`
- `policy_snapshot_id`
- `data_snapshot_id`
- `correlation_id`

Orchestrator가 요청을 거부한 경우 Scheduler는 원인을 변경하지 않고 기록한다.

```text
POLICY_REJECTED
DATA_SNAPSHOT_INVALID
INVALID_RUN_MODE
DUPLICATE_RUN
CONCURRENCY_CONFLICT
```

## 15. Audit & Compliance 연계

필수 감사 이벤트:

```text
SCHEDULE_CREATED
SCHEDULE_UPDATED
SCHEDULE_ACTIVATED
SCHEDULE_PAUSED
TRIGGER_CREATED
TRIGGER_SUPPRESSED
TRIGGER_MISFIRED
TRIGGER_DISPATCHED
DISPATCH_RETRIED
DISPATCH_DEAD_LETTERED
MANUAL_RUN_REQUESTED
BACKFILL_REQUESTED
BACKFILL_APPROVED
BACKFILL_COMPLETED
```

감사 payload 최소 필드:

```python
{
    "actor": "scheduler-worker-01",
    "schedule_id": "sch-...",
    "trigger_id": "trg-...",
    "run_id": "run-...",
    "market": "KR",
    "ticker": "005930",
    "scheduled_for": "...",
    "actual_dispatch_at": "...",
    "policy_snapshot_id": "pol-...",
    "data_snapshot_id": "snap-...",
    "reason": "..."
}
```

## 16. 장애 처리

### 달력 조회 실패

- 캐시된 승인 버전이 유효하면 사용
- 유효 버전이 없으면 LIVE Trigger 차단
- PAPER/BACKTEST는 정책에 따라 degraded mode 허용

### DB 잠금

- `busy_timeout` 적용
- 짧은 지수 backoff
- Trigger 생성은 idempotency unique index로 보호
- 최대 재시도 후 Dead Letter 이동

### Worker 장애

- lease 만료 후 다른 worker가 재claim
- Orchestrator run 생성 여부를 idempotency key로 먼저 확인
- 이미 run이 있으면 중복 실행하지 않고 ACCEPTED 처리

### 이벤트 중복 수신

- source event ID와 idempotency key로 억제
- 중복 이벤트도 감사용 수신 횟수는 별도 metric 기록 가능

### 시계 오차

- 시스템 clock health 점검
- 허용 오차 초과 시 LIVE dispatch 차단
- 이벤트 발생 시각과 수신 시각 모두 저장

## 17. 관측성과 운영 지표

핵심 지표:

```text
scheduler_trigger_created_total
scheduler_trigger_suppressed_total{reason}
scheduler_trigger_misfired_total{schedule_id}
scheduler_dispatch_latency_seconds
scheduler_dispatch_retry_total
scheduler_dead_letter_total
scheduler_active_schedule_count
scheduler_queue_depth
scheduler_queue_oldest_age_seconds
scheduler_calendar_version_age_days
scheduler_duplicate_prevented_total
scheduler_backfill_remaining_runs
```

서비스 수준 목표 초안:

| 항목 | 목표 |
|---|---:|
| 장 시작 전 분석 dispatch 지연 p95 | 10초 이내 |
| 장중 위험 점검 dispatch 지연 p95 | 5초 이내 |
| 중복 Run 생성 | 0건 |
| LIVE 휴장일 주문 Trigger | 0건 |
| Dead Letter 미처리 시간 | 30분 이내 |

## 18. 테스트 계획

### 18.1 단위 테스트

- 정상 거래일 다음 실행 시각 계산
- 주말 Trigger 억제
- 공휴일 Trigger 억제
- 조기 폐장일 offset 계산
- timezone과 DST 변환
- CRON 표현식 검증
- interval 슬롯 정규화
- 동일 Trigger 멱등성 확인
- 데이터 snapshot 미준비 차단
- 정책 snapshot 미존재 차단
- 동시 실행 제한
- misfire `SKIP`
- misfire `FIRE_ONCE`
- misfire `CATCH_UP`
- misfire `FAIL`
- lease 만료 재claim
- 최대 재시도 후 Dead Letter

### 18.2 DB 테스트

- schedule 상태 CHECK 제약
- trigger idempotency unique index
- trigger와 dispatch cascade
- claim 트랜잭션 경쟁 조건
- 동일 dispatch의 이중 claim 차단
- rollback 시 상태 일관성
- 잘못된 상태 전이 차단

### 18.3 통합 테스트

1. 거래일 장 시작 10분 전 Trigger 생성
2. 승인된 PolicySnapshot 조회
3. 잠긴 DataSnapshot 연결
4. Dispatch Queue 저장
5. Worker가 Orchestrator 호출
6. Run State Store에 run 생성
7. Trigger `ACKNOWLEDGED` 확인
8. Audit 이벤트 해시 체인 확인

### 18.4 휴장일 테스트

```text
2026-01-01 KR 시장
→ 장전 분석 Trigger 생성 시도
→ SUPPRESSED
→ run 미생성
→ suppression_reason = MARKET_CLOSED
```

### 18.5 조기 폐장 테스트

```text
calendar close_at = 12:00 local
schedule = close + 5분
expected scheduled_for = 12:05 local
고정 15:35로 계산되지 않아야 함
```

### 18.6 장애 주입 테스트

- 달력 DB unavailable
- Schedule repository timeout
- Dispatch 저장 직후 프로세스 종료
- Orchestrator timeout
- Orchestrator가 run 생성 후 응답 유실
- worker lease 만료
- 중복 이벤트 100회 수신
- 시스템 시계 10분 오차
- Audit Engine unavailable

### 18.7 Backfill 테스트

- 주말 제외 거래일만 생성
- ticker 100개 × 거래일 30일 실행 수 계산
- max_runs 초과 차단
- LIVE mode Backfill 거부
- 우선순위가 운영 Trigger보다 낮음
- 취소 시 미실행 Trigger 취소
- 부분 완료 상태 계산

### 18.8 성능 테스트

초기 목표:

- Trigger 10,000개 일괄 생성 10초 이내
- Queue depth 100,000에서 claim p95 100ms 이내
- 동시 worker 8개에서 중복 claim 0건
- 이벤트 Trigger 초당 100건 처리
- 1년 Backtest schedule 생성 메모리 512MB 이내

### 18.9 회귀 테스트

- 기존 CLI 직접 실행 유지
- Scheduler 없이 `main.py` 실행 가능
- ExistingPipelineAdapter 결과 동일
- Scheduler 경유 실행과 직접 실행의 Decision 결과 동일
- 동일 policy/data/code 버전에서 재현성 유지

## 19. 구현 순서

1. `ScheduleDefinition`, `TriggerEvent`, `DispatchRequest` 모델
2. SQLite migration과 Repository
3. Market Calendar Service와 고정 fixture
4. 시간 기반 Trigger 생성
5. idempotency와 Trigger 상태 전이
6. Dispatch Queue와 단일 worker
7. Orchestrator adapter
8. misfire 정책
9. concurrency guard와 lease
10. 이벤트 기반 Trigger
11. Backfill Planner
12. Audit & Compliance 연계
13. 운영 metric과 Dead Letter 관리

## 20. 완료 기준

- 거래일과 시장 세션에 맞게 Trigger가 생성된다.
- 휴장일과 허용되지 않은 세션의 실행이 차단된다.
- 동일 스케줄 슬롯에서 Run이 중복 생성되지 않는다.
- 조기 폐장과 timezone이 정확히 반영된다.
- Trigger가 표준 RunRequest로 변환되어 Orchestrator에 전달된다.
- worker 장애 후에도 lease 기반으로 안전하게 복구된다.
- LIVE misfire가 과거 주문 실행으로 이어지지 않는다.
- Backfill이 LIVE 경로와 격리된다.
- 수동 실행과 재처리 이력이 감사 이벤트로 남는다.
- 고정 거래소 달력 fixture 기반 통합 테스트가 통과한다.

## 21. 다음 설계 대상

다음 엔진은 **Portfolio Accounting & Performance Engine v1**으로 한다.

이 엔진은 주문·체결 결과를 기반으로 다음을 계산하고 보존한다.

- 현금, 보유 수량, 평균단가, 실현·미실현 손익
- 수수료, 세금, 배당, 환율 반영
- 일간·누적 수익률과 벤치마크 대비 성과
- 포지션 및 포트폴리오 시점 스냅샷
- 가상투자, PAPER, BACKTEST 결과의 동일 회계 규칙
- ADE 의사결정 품질 검증을 위한 성과 attribution
