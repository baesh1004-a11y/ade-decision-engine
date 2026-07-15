# 17. Audit & Compliance Engine v1

## 1. 목적

Audit & Compliance Engine은 ADE에서 발생한 정책 변경, 데이터 사용, 의사결정, 주문, 체결, 운영자 개입을 변경 불가능한 감사 기록으로 통합하고, 사전에 정의된 통제 규칙 위반을 탐지하는 거버넌스 계층이다.

이 엔진은 새로운 투자 판단을 생성하지 않으며 기존 Signal, Risk, Decision, Order 결과를 수정하지 않는다. 대신 누가, 언제, 어떤 데이터와 정책을 사용하여 무엇을 실행했고 어떤 결과가 발생했는지를 재구성할 수 있도록 증거를 수집·검증·보존한다.

주요 목적은 다음과 같다.

- 실행 전·중·후 전 단계의 감사 증거 수집
- 정책 승인, 데이터 계보, 의사결정, 주문, 체결의 연결 추적
- LIVE 관련 안전 통제 위반 탐지
- 운영자 수동 개입과 예외 승인 기록
- 변경 불가능한 이벤트 저널과 해시 체인 생성
- 규칙 위반의 심각도 분류, 사건 생성, 조치 추적
- 감사 보고서와 규제·내부통제 증빙 생성
- 사고 발생 시 실행 단위의 완전한 재구성 지원

## 2. 문제 정의

ADE는 여러 엔진이 연속적으로 판단과 실행을 수행하므로 단순 애플리케이션 로그만으로는 다음 질문에 답하기 어렵다.

1. 특정 BUY 결정은 어떤 데이터와 정책에서 생성되었는가?
2. 해당 주문은 승인된 실행 모드와 계좌에서 생성되었는가?
3. LIVE 주문 전 안전 검토가 실제로 통과했는가?
4. 정책 변경자는 누구이며 승인자는 누구인가?
5. 데이터 정정 이후 영향을 받은 과거 실행은 무엇인가?
6. 운영자가 자동 판단을 덮어쓴 경우 사유와 승인 근거가 있는가?
7. 감사 기록 자체가 변경되거나 삭제되지 않았는가?
8. 동일 주문 또는 체결 이벤트가 중복 처리되지 않았는가?

일반 로그는 포맷이 일정하지 않고 수정·삭제될 수 있으며, 엔진별 저장소가 분리되어 있어 하나의 실행을 완전하게 재구성하기 어렵다. Audit & Compliance Engine은 모든 핵심 이벤트를 표준 감사 이벤트로 변환하고 해시 체인으로 연결하여 이 문제를 해결한다.

## 3. 책임 경계

### 3.1 담당

- 감사 대상 이벤트의 표준화
- 실행, 정책, 데이터, 결정, 주문, 체결, 운영자 행위 간 연결
- Append-only 감사 저널 저장
- 이벤트 해시 및 이전 이벤트 해시 연결
- 필수 증거 누락 탐지
- 통제 규칙 평가 및 위반 사건 생성
- 예외 승인, 수동 개입, 재처리 이력 기록
- 사건 상태와 시정조치 추적
- 감사 리포트용 증거 패키지 생성
- 보존 기간, 법적 보존, 폐기 승인 상태 관리
- 민감정보 마스킹 및 접근 기록

### 3.2 담당하지 않음

- 매수·매도 판단 생성
- Risk 정책 자체의 계산
- 주문 가격·수량 변경
- 체결 상태 결정
- 정책 승인 권한의 조직적 부여
- 외부 규제 해석 또는 법률 자문
- 인증정보, API 키, 계좌 비밀번호 저장
- 원본 업무 데이터를 감사 저장소에서 임의 수정

## 4. ADE 내 위치

```text
Configuration & Policy Engine ─────┐
Data Snapshot & Lineage Engine ────┤
Integration Orchestrator ──────────┤
Signal / Risk / Decision ──────────┤
Order / Execution / Portfolio ─────┤
Operator / Scheduler / API ────────┘
                 ↓
       Audit Event Collector
                 ↓
       Event Normalizer / Redactor
                 ↓
        Evidence Link Resolver
                 ↓
      Append-only Audit Journal
                 ↓
        Compliance Rule Engine
          ├─ PASS
          ├─ WARNING
          ├─ VIOLATION
          └─ CRITICAL INCIDENT
                 ↓
      Incident / Remediation Store
                 ↓
       Report Engine / Dashboard
```

모든 엔진은 감사 저장소에 직접 업무 로직을 구현하지 않는다. 공통 `AuditPublisher` 인터페이스를 통해 이벤트를 발행하고, Audit & Compliance Engine이 정규화와 저장을 담당한다.

## 5. 핵심 원칙

1. 감사 이벤트는 Append-only로 저장한다.
2. 기존 이벤트는 수정하지 않고 보정 이벤트를 추가한다.
3. 모든 핵심 이벤트는 `run_id`, `correlation_id`, `actor`, `occurred_at`을 가져야 한다.
4. 의사결정·주문·체결 이벤트는 원천 정책 및 데이터 스냅샷을 참조해야 한다.
5. 이벤트 해시는 canonical JSON 기준으로 계산한다.
6. 각 이벤트는 동일 스트림의 이전 이벤트 해시를 포함한다.
7. 민감정보는 저장 전 마스킹하고 비밀값은 저장하지 않는다.
8. 통제 위반은 업무 결과를 자동 변경하지 않고 별도 사건으로 기록한다.
9. CRITICAL 통제 위반은 Orchestrator 또는 Order Gate가 후속 단계를 중단할 수 있도록 신호를 반환한다.
10. 감사 규칙 자체도 버전과 승인 이력을 가져야 한다.
11. 이벤트 시간과 저장 시간은 분리하여 기록한다.
12. 모든 수동 개입은 사유, 요청자, 승인자, 만료시간을 가져야 한다.

## 6. 감사 이벤트 분류

| 범주 | 주요 이벤트 |
|---|---|
| RUN | RUN_CREATED, RUN_STARTED, RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED |
| POLICY | POLICY_CREATED, POLICY_CHANGED, POLICY_APPROVED, POLICY_ACTIVATED, POLICY_RETIRED |
| DATA | SNAPSHOT_CREATED, SNAPSHOT_LOCKED, DATA_QUARANTINED, LINEAGE_CHANGED |
| DECISION | SIGNAL_GENERATED, RISK_EVALUATED, DECISION_CREATED, DECISION_REJECTED |
| ORDER | ORDER_CREATED, ORDER_VALIDATED, ORDER_BLOCKED, ORDER_SUBMITTED, ORDER_FAILED |
| EXECUTION | EXECUTION_PARTIAL_FILL, EXECUTION_FILLED, EXECUTION_REJECTED, EXECUTION_CANCELLED |
| PORTFOLIO | PORTFOLIO_UPDATED, POSITION_OPENED, POSITION_REDUCED, POSITION_CLOSED |
| OPERATOR | MANUAL_OVERRIDE_REQUESTED, MANUAL_OVERRIDE_APPROVED, MANUAL_OVERRIDE_APPLIED |
| SECURITY | ACCESS_DENIED, SECRET_DETECTED, AUDIT_CHAIN_BROKEN, UNAUTHORIZED_MODE_CHANGE |
| COMPLIANCE | CONTROL_EVALUATED, VIOLATION_OPENED, EXCEPTION_GRANTED, REMEDIATION_COMPLETED |
| SYSTEM | COMPONENT_STARTED, COMPONENT_STOPPED, RETRY_SCHEDULED, INTERNAL_ERROR |

## 7. 입력 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditEventInput:
    event_type: str
    category: str
    action: str
    outcome: str
    actor_type: str
    actor_id: str
    occurred_at: datetime
    run_id: str | None = None
    correlation_id: str | None = None
    stage_name: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    policy_snapshot_id: str | None = None
    data_snapshot_id: str | None = None
    source_engine: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
```

추가 입력:

- Orchestrator 단계 상태
- Run State Store의 run/stage/artifact 참조
- Configuration & Policy snapshot
- Data Snapshot & Lineage manifest
- Decision, Order, Execution 식별자
- 사용자·서비스 계정 식별 정보
- 수동 예외 승인 정보
- 감사 규칙 버전

## 8. 출력 모델

```python
@dataclass(frozen=True)
class AuditRecord:
    audit_event_id: str
    stream_id: str
    sequence_no: int
    event_type: str
    category: str
    action: str
    outcome: str
    severity: str
    actor_type: str
    actor_id: str
    run_id: str | None
    correlation_id: str | None
    resource_type: str | None
    resource_id: str | None
    occurred_at: datetime
    ingested_at: datetime
    payload_hash: str
    previous_event_hash: str | None
    event_hash: str
    schema_version: str
```

```python
@dataclass(frozen=True)
class ComplianceEvaluation:
    evaluation_id: str
    audit_event_id: str
    control_id: str
    control_version: str
    result: str
    severity: str
    reason: str
    incident_id: str | None
    evaluated_at: datetime
```

```python
@dataclass(frozen=True)
class ComplianceIncident:
    incident_id: str
    control_id: str
    severity: str
    status: str
    title: str
    description: str
    run_id: str | None
    resource_refs: tuple[str, ...]
    detected_at: datetime
    owner: str | None = None
    due_at: datetime | None = None
```

## 9. 상태 모델

### 9.1 감사 이벤트 수집 상태

```text
RECEIVED → NORMALIZING → VALIDATED → PERSISTED → EVALUATED
             ├─→ QUARANTINED
             └─→ FAILED
```

### 9.2 Compliance Incident 상태

```text
OPEN → ACKNOWLEDGED → INVESTIGATING → REMEDIATING → RESOLVED → CLOSED
  ├─→ ACCEPTED_RISK
  ├─→ FALSE_POSITIVE
  └─→ ESCALATED
```

### 9.3 Exception 상태

```text
REQUESTED → APPROVED → ACTIVE → EXPIRED
          ├─→ REJECTED
          └─→ REVOKED
```

## 10. 데이터베이스 설계

### 10.1 `audit_event_streams`

```sql
CREATE TABLE IF NOT EXISTS audit_event_streams (
    stream_id TEXT PRIMARY KEY,
    stream_type TEXT NOT NULL,
    stream_key TEXT NOT NULL,
    last_sequence_no INTEGER NOT NULL DEFAULT 0,
    last_event_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (stream_type, stream_key),
    CHECK (stream_type IN ('RUN','POLICY','DATA','ORDER','EXECUTION','SECURITY','SYSTEM'))
);
```

`stream_key`는 일반적으로 `run_id`, `policy_id`, `snapshot_id`, `order_id` 중 하나이다.

### 10.2 `audit_events`

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    severity TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    run_id TEXT,
    correlation_id TEXT,
    stage_name TEXT,
    resource_type TEXT,
    resource_id TEXT,
    source_engine TEXT,
    policy_snapshot_id TEXT,
    data_snapshot_id TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    previous_event_hash TEXT,
    event_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY (stream_id) REFERENCES audit_event_streams(stream_id),
    UNIQUE (stream_id, sequence_no),
    UNIQUE (event_hash),
    CHECK (outcome IN ('SUCCESS','FAILURE','DENIED','BLOCKED','PARTIAL','UNKNOWN')),
    CHECK (severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')),
    CHECK (actor_type IN ('USER','SERVICE','SCHEDULER','SYSTEM','BROKER','EXTERNAL'))
);

CREATE INDEX IF NOT EXISTS ix_audit_events_run_time
ON audit_events(run_id, occurred_at);

CREATE INDEX IF NOT EXISTS ix_audit_events_resource
ON audit_events(resource_type, resource_id, occurred_at);

CREATE INDEX IF NOT EXISTS ix_audit_events_type_time
ON audit_events(event_type, occurred_at);

CREATE INDEX IF NOT EXISTS ix_audit_events_correlation
ON audit_events(correlation_id);
```

### 10.3 `compliance_controls`

```sql
CREATE TABLE IF NOT EXISTS compliance_controls (
    control_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    evaluation_point TEXT NOT NULL,
    rule_expression TEXT NOT NULL,
    action_on_failure TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    approved_by TEXT,
    approved_at TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (control_id, version),
    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CHECK (evaluation_point IN ('PRE_RUN','PRE_STAGE','POST_STAGE','EVENT','DAILY','ON_DEMAND')),
    CHECK (action_on_failure IN ('LOG','WARN','BLOCK_STAGE','BLOCK_RUN','OPEN_INCIDENT'))
);
```

### 10.4 `compliance_evaluations`

```sql
CREATE TABLE IF NOT EXISTS compliance_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    audit_event_id TEXT,
    run_id TEXT,
    control_id TEXT NOT NULL,
    control_version TEXT NOT NULL,
    result TEXT NOT NULL,
    severity TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    incident_id TEXT,
    evaluated_at TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,
    FOREIGN KEY (audit_event_id) REFERENCES audit_events(audit_event_id),
    FOREIGN KEY (control_id, control_version)
        REFERENCES compliance_controls(control_id, version),
    CHECK (result IN ('PASS','FAIL','NOT_APPLICABLE','ERROR','EXEMPTED'))
);

CREATE INDEX IF NOT EXISTS ix_compliance_evaluations_run
ON compliance_evaluations(run_id, evaluated_at);

CREATE INDEX IF NOT EXISTS ix_compliance_evaluations_control
ON compliance_evaluations(control_id, result, evaluated_at);
```

### 10.5 `compliance_incidents`

```sql
CREATE TABLE IF NOT EXISTS compliance_incidents (
    incident_id TEXT PRIMARY KEY,
    control_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    run_id TEXT,
    correlation_id TEXT,
    owner TEXT,
    due_at TEXT,
    detected_at TEXT NOT NULL,
    acknowledged_at TEXT,
    resolved_at TEXT,
    closed_at TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CHECK (status IN (
        'OPEN','ACKNOWLEDGED','INVESTIGATING','REMEDIATING','RESOLVED',
        'CLOSED','ACCEPTED_RISK','FALSE_POSITIVE','ESCALATED'
    ))
);
```

### 10.6 `compliance_incident_events`

```sql
CREATE TABLE IF NOT EXISTS compliance_incident_events (
    incident_event_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    note TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES compliance_incidents(incident_id)
        ON DELETE CASCADE
);
```

### 10.7 `compliance_exceptions`

```sql
CREATE TABLE IF NOT EXISTS compliance_exceptions (
    exception_id TEXT PRIMARY KEY,
    control_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_value TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    requested_at TEXT NOT NULL,
    approved_at TEXT,
    valid_from TEXT,
    valid_until TEXT,
    revoked_at TEXT,
    evidence_ref TEXT,
    CHECK (scope_type IN ('RUN','POLICY','ACCOUNT','SYMBOL','ENVIRONMENT')),
    CHECK (status IN ('REQUESTED','APPROVED','ACTIVE','EXPIRED','REJECTED','REVOKED'))
);
```

### 10.8 `audit_access_log`

```sql
CREATE TABLE IF NOT EXISTS audit_access_log (
    access_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    query_scope TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    CHECK (action IN ('SEARCH','READ','EXPORT','VERIFY','LEGAL_HOLD','PURGE_REQUEST'))
);
```

## 11. 해시 체인 설계

### 11.1 Canonical Event

```python
canonical_event = {
    "stream_id": stream_id,
    "sequence_no": sequence_no,
    "event_type": event_type,
    "category": category,
    "action": action,
    "outcome": outcome,
    "actor_type": actor_type,
    "actor_id": actor_id,
    "run_id": run_id,
    "resource_type": resource_type,
    "resource_id": resource_id,
    "occurred_at": occurred_at_utc,
    "payload_hash": payload_hash,
    "previous_event_hash": previous_event_hash,
    "schema_version": schema_version,
}
```

### 11.2 해시 계산

```python
payload_hash = sha256(canonical_json(redacted_payload).encode()).hexdigest()
event_hash = sha256(canonical_json(canonical_event).encode()).hexdigest()
```

### 11.3 체인 검증

```text
stream 조회
→ sequence_no 오름차순 정렬
→ 첫 이벤트의 previous_event_hash가 NULL인지 확인
→ 각 이벤트의 canonical event 재계산
→ 저장 event_hash와 비교
→ 다음 이벤트의 previous_event_hash와 연결 확인
→ 누락 sequence 확인
→ 검증 결과 저장
```

해시 체인은 데이터베이스 관리자 수준의 변조를 완전히 방지하지는 못한다. 운영 단계에서는 주기적으로 체인 루트 해시를 외부 불변 저장소 또는 별도 보안 계정에 서명·보관한다.

## 12. 핵심 통제 규칙 v1

| Control ID | 규칙 | 실패 조치 |
|---|---|---|
| AC-001 | 모든 run은 승인된 policy snapshot을 가져야 한다 | BLOCK_RUN |
| AC-002 | 모든 run은 잠긴 data snapshot을 가져야 한다 | BLOCK_RUN |
| AC-003 | LIVE mode는 승인된 LIVE 정책과 명시적 enable flag를 요구한다 | BLOCK_RUN |
| AC-004 | Decision 생성 시 signal, risk, policy, data 참조가 모두 존재해야 한다 | OPEN_INCIDENT |
| AC-005 | Order는 source decision ID와 risk approval을 가져야 한다 | BLOCK_STAGE |
| AC-006 | LIVE_BLOCKED에서 broker submit 호출이 발생하면 안 된다 | BLOCK_RUN + CRITICAL |
| AC-007 | 주문 수량은 decision target과 허용 오차 내에서 일치해야 한다 | BLOCK_STAGE |
| AC-008 | 중복 open order는 승인된 override 없이는 허용하지 않는다 | BLOCK_STAGE |
| AC-009 | 체결 누적 수량은 요청 수량을 초과할 수 없다 | OPEN_INCIDENT |
| AC-010 | 수동 override는 요청자와 승인자가 달라야 한다 | BLOCK_STAGE |
| AC-011 | 수동 override는 사유와 만료시간을 가져야 한다 | BLOCK_STAGE |
| AC-012 | 정책 작성자와 승인자는 동일할 수 없다 | WARN/BLOCK activation |
| AC-013 | 감사 이벤트 체인 검증에 실패하면 CRITICAL incident를 생성한다 | BLOCK_RUN |
| AC-014 | secret pattern이 payload에서 탐지되면 저장을 격리한다 | QUARANTINE |
| AC-015 | Backtest path에서 live broker connector 호출은 금지한다 | BLOCK_RUN |
| AC-016 | Report 수치는 source_ref 또는 lineage_ref를 가져야 한다 | OPEN_INCIDENT |
| AC-017 | 실패한 critical stage 이후 주문 단계가 실행되면 안 된다 | CRITICAL |
| AC-018 | 동일 idempotency key의 중복 성공 run은 정책상 허용되지 않는다 | WARN/INCIDENT |

## 13. 규칙 표현 방식

v1은 임의 Python 실행을 허용하지 않고 제한된 선언형 조건식을 사용한다.

예:

```json
{
  "all": [
    {"field": "event.category", "eq": "ORDER"},
    {"field": "event.action", "eq": "SUBMIT"},
    {"field": "context.mode", "eq": "LIVE_BLOCKED"}
  ]
}
```

지원 연산자:

- `eq`, `ne`
- `in`, `not_in`
- `gt`, `gte`, `lt`, `lte`
- `exists`, `not_exists`
- `all`, `any`, `not`
- `matches_safe_pattern`
- `ref_exists`
- `hash_matches`

규칙은 입력 필드의 allowlist를 사용하고, 실행 시간과 메모리 사용량을 제한한다.

## 14. 핵심 알고리즘

### 14.1 감사 이벤트 수집

```python
def record_event(input_event, repository, redactor, clock):
    normalized = normalize_event(input_event)
    redacted_payload = redactor.redact(normalized.payload)

    with repository.lock_stream(normalized.stream_key) as stream:
        sequence_no = stream.last_sequence_no + 1
        previous_hash = stream.last_event_hash
        payload_hash = hash_payload(redacted_payload)
        event_hash = hash_event(
            normalized,
            sequence_no=sequence_no,
            previous_event_hash=previous_hash,
            payload_hash=payload_hash,
        )

        record = repository.append_event(
            event=normalized,
            payload=redacted_payload,
            sequence_no=sequence_no,
            previous_event_hash=previous_hash,
            payload_hash=payload_hash,
            event_hash=event_hash,
            ingested_at=clock.now(),
        )
        repository.advance_stream(stream.stream_id, sequence_no, event_hash)

    return record
```

이벤트 저장과 stream의 마지막 sequence/hash 갱신은 동일 트랜잭션에서 수행한다.

### 14.2 Compliance 평가

```python
def evaluate_event(record, context, control_repository, evaluator):
    controls = control_repository.active_controls(
        category=record.category,
        evaluation_point="EVENT",
        at=record.occurred_at,
    )

    results = []
    for control in controls:
        exception = control_repository.find_active_exception(control, context)
        if exception:
            results.append(save_exempted(control, record, exception))
            continue

        result = evaluator.evaluate(control.rule_expression, record, context)
        evaluation = save_evaluation(control, record, result)
        results.append(evaluation)

        if result.failed:
            apply_failure_action(control, evaluation, context)

    return results
```

### 14.3 실행 완료 감사 검증

```text
run 종료 요청
→ 필수 이벤트 체크리스트 로드
→ run mode와 실행 단계에 따른 기대 이벤트 계산
→ 존재 여부 및 순서 확인
→ 정책·데이터·결정·주문·체결 참조 무결성 확인
→ 감사 체인 검증
→ 통제 평가 결과 집계
→ PASS / PASS_WITH_WARNINGS / FAIL 결정
→ 감사 요약 artifact 저장
→ Orchestrator 최종 상태에 반영
```

### 14.4 사건 생성 중복 방지

사건 deduplication key:

```text
control_id + run_id + resource_type + resource_id + normalized_reason
```

동일 키의 OPEN 사건이 있으면 새 사건을 만들지 않고 증거 이벤트만 추가한다.

## 15. 코드 구조

```text
audit/
├── __init__.py
├── models.py              # AuditRecord, ComplianceEvaluation, Incident
├── publisher.py           # AuditPublisher interface and adapters
├── collector.py           # event ingestion service
├── normalizer.py          # schema validation and normalization
├── redactor.py            # secret and PII redaction
├── hashing.py             # canonical JSON and hash chain
├── repository.py          # repository protocols
├── sqlite_repository.py   # SQLite implementation
├── controls.py            # control definitions and loader
├── evaluator.py           # safe declarative rule evaluator
├── incidents.py           # incident lifecycle service
├── exceptions.py          # exception approval and expiration
├── verifier.py            # chain and completeness verification
├── export.py              # evidence package export
└── service.py             # AuditComplianceService facade

tests/
├── test_audit_collector.py
├── test_audit_hash_chain.py
├── test_audit_redaction.py
├── test_compliance_evaluator.py
├── test_compliance_incident.py
├── test_compliance_exception.py
├── test_audit_run_completeness.py
├── test_audit_integration.py
└── test_audit_failure_injection.py
```

## 16. 인터페이스 초안

```python
from typing import Protocol, Any


class AuditPublisher(Protocol):
    def publish(self, event: AuditEventInput) -> str: ...


class AuditRepository(Protocol):
    def append(self, event: AuditEventInput) -> AuditRecord: ...
    def get_event(self, audit_event_id: str) -> AuditRecord | None: ...
    def list_run_events(self, run_id: str) -> list[AuditRecord]: ...
    def verify_stream(self, stream_id: str) -> dict[str, Any]: ...
    def find_by_resource(self, resource_type: str, resource_id: str) -> list[AuditRecord]: ...


class ComplianceService(Protocol):
    def evaluate_event(self, event: AuditRecord, context: dict[str, Any]) -> list[ComplianceEvaluation]: ...
    def evaluate_run(self, run_id: str) -> list[ComplianceEvaluation]: ...
    def open_incident(self, evaluation: ComplianceEvaluation) -> ComplianceIncident: ...
    def grant_exception(self, request: dict[str, Any]) -> str: ...
```

## 17. 엔진별 통합 방식

### 17.1 Integration Orchestrator

Orchestrator는 다음 시점에 감사 이벤트를 발행한다.

- run 생성, 검증, 시작, 완료, 실패, 취소
- stage 시작, 성공, 실패, 재시도, 건너뜀
- policy/data snapshot 바인딩
- critical compliance 결과 수신
- 최종 감사 검증 결과

CRITICAL control의 `BLOCK_RUN` 결과는 후속 단계 실행을 중단한다.

### 17.2 Configuration & Policy Engine

- 정책 생성·변경·승인·활성화·폐기 이벤트 발행
- 작성자/승인자 분리 통제
- 활성 정책의 해시와 승인 증거 연결
- 감사 통제 규칙 자체의 버전 관리

### 17.3 Data Snapshot & Lineage Engine

- snapshot 생성, 검증, 잠금, 격리 이벤트 발행
- `snapshot_id`, `manifest_id`, `lineage_root_id`, `data_hash` 연결
- 데이터 정정 영향 분석 결과를 사건 증거로 연결

### 17.4 Decision Engine

- 입력 signal/risk/policy/data 참조와 결과 decision 저장
- 판단 이유와 적용된 rule ID 저장
- 결정 결과를 변경하지 않고 감사 이벤트만 생성

### 17.5 Order Engine

- 주문 생성 전 AC-005, AC-006, AC-007, AC-008 평가
- `BLOCK_STAGE` 결과 시 broker adapter를 호출하지 않음
- blocked/rejected 주문도 감사 기록 저장

### 17.6 Execution Monitor

- 체결 이벤트별 고유 broker event ID 기록
- 부분체결 누적과 중복 이벤트 무시 결과 기록
- 요청 수량 초과 탐지 시 incident 생성

### 17.7 Report Engine

- Daily Audit Summary
- Open Compliance Incidents
- Manual Overrides and Exceptions
- Run Evidence Package
- Hash Chain Verification Result
- Policy/Data/Decision/Order/Execution trace

## 18. 보안 및 개인정보 처리

### 18.1 저장 금지 항목

- API key
- access token / refresh token
- 계좌 비밀번호
- 주민등록번호 또는 이에 준하는 고유 식별정보
- broker 인증 전문 원문
- 세션 쿠키
- 암호화되지 않은 개인 연락처

### 18.2 마스킹 규칙

```python
SENSITIVE_KEYS = {
    "api_key", "access_token", "refresh_token", "password",
    "secret", "authorization", "cookie", "account_password"
}
```

- 계좌번호: 마지막 4자리만 유지
- 사용자 식별자: 내부 pseudonymous ID 사용
- 원본 broker payload: allowlist 필드만 저장
- 예외 상황에서 원본이 필요한 경우 별도 암호화 저장소 참조만 기록

### 18.3 접근 통제

역할 예시:

| 역할 | 권한 |
|---|---|
| AUDIT_READER | 조회 |
| AUDIT_EXPORTER | 조회 및 증거 패키지 생성 |
| COMPLIANCE_ANALYST | 사건 조사·상태 변경 |
| COMPLIANCE_APPROVER | 예외 승인 |
| AUDIT_ADMIN | 규칙 배포·보존 정책 관리 |

감사 기록 조회와 내보내기 자체도 `audit_access_log`에 남긴다.

## 19. 보존 및 폐기 정책

v1 기본 원칙:

- 감사 이벤트: 장기 보존 대상
- 원본 payload: 최소화 후 정책 기간 보존
- 해시와 메타데이터: payload보다 길게 보존
- 열린 incident 관련 이벤트: 사건 종료 전 폐기 금지
- legal hold 상태: 자동 폐기 금지
- 폐기 작업도 승인자, 대상 범위, 이유, 결과 해시를 감사 기록으로 남김

실제 보존 기간은 조직의 법무·보안·내부통제 정책으로 확정한다.

## 20. 오류 처리

| 오류 | 처리 |
|---|---|
| 이벤트 스키마 오류 | QUARANTINED, 원 엔진에는 명시적 실패 반환 |
| 감사 DB 일시 장애 | 제한적 재시도 후 fail-closed 여부를 mode별 적용 |
| 해시 불일치 | CRITICAL incident, 관련 run 차단 |
| sequence 충돌 | 트랜잭션 재시도 |
| secret 탐지 | payload 격리, SECURITY 이벤트 생성 |
| 규칙 평가 오류 | result=ERROR, 통제 severity에 따라 경고 또는 차단 |
| 사건 저장 실패 | 원 evaluation 유지, 재처리 큐 등록 |
| 외부 서명 저장 실패 | HIGH 경고, 다음 주기에 재시도 |

Mode별 원칙:

- DRY_RUN: 감사 저장 실패를 경고로 처리 가능
- PAPER: 핵심 order/execution 감사 저장 실패 시 stage 실패
- LIVE_BLOCKED: broker 호출은 원래 차단, 감사 실패는 run 실패
- LIVE: 핵심 감사 기록 저장 실패 시 fail-closed
- BACKTEST/SIMULATED: 재현성 manifest 및 결과 감사 저장 실패 시 run 실패

## 21. 성능 및 확장성

v1 목표:

- 단일 이벤트 저장 p95 50ms 이하(SQLite 로컬 기준 목표)
- 이벤트 hash 계산 deterministic
- 동일 stream 순서 보장
- run 단위 이벤트 조회 인덱스 제공
- batch append 지원 준비
- 대량 payload는 외부 artifact 참조 방식 사용

확장 전략:

1. SQLite WAL mode
2. 이벤트 append와 compliance evaluation 분리
3. outbox 기반 비동기 평가
4. PostgreSQL 전환
5. 외부 불변 객체 저장소와 root hash 서명
6. SIEM 또는 관제 플랫폼 연동

## 22. 테스트 계획

### 22.1 단위 테스트

- 정상 이벤트를 canonical schema로 정규화한다.
- 민감 키가 저장 전 마스킹된다.
- 동일 payload는 동일 payload hash를 생성한다.
- 이벤트 순서에 따라 hash chain이 연결된다.
- 잘못된 이전 hash가 탐지된다.
- sequence gap이 탐지된다.
- 기존 audit event update API가 존재하지 않는다.
- 보정은 새 CORRECTION 이벤트로 추가된다.
- 선언형 규칙의 `all`, `any`, `not`이 정확히 동작한다.
- 허용되지 않은 field 또는 operator를 거부한다.
- active exception이 있으면 EXEMPTED 결과를 생성한다.
- 만료된 exception은 적용되지 않는다.
- 사건 deduplication key가 중복 사건 생성을 막는다.

### 22.2 데이터베이스 테스트

- 동일 stream/sequence 중복 insert가 실패한다.
- 동일 event_hash 중복 insert가 실패한다.
- event append와 stream advance가 원자적으로 처리된다.
- foreign key가 없는 evaluation 저장을 거부한다.
- incident 상태 제약조건이 동작한다.
- query index가 run/resource 검색에 사용된다.
- audit event 삭제 기능이 repository interface에 노출되지 않는다.

### 22.3 통제 규칙 테스트

- policy snapshot이 없는 run은 AC-001에 실패한다.
- 잠기지 않은 data snapshot은 AC-002에 실패한다.
- LIVE_BLOCKED broker submit은 AC-006 CRITICAL이다.
- source decision이 없는 order는 AC-005에 실패한다.
- risk approval이 false인 order는 차단된다.
- target quantity와 주문 수량 불일치가 탐지된다.
- 승인 없는 duplicate order가 차단된다.
- 체결 누적 수량 초과가 incident를 생성한다.
- 요청자와 승인자가 같은 override를 거부한다.
- Backtest에서 broker connector 호출을 차단한다.

### 22.4 통합 테스트

1. fixture 시장 데이터로 전체 분석 run 실행
2. policy snapshot과 data snapshot 바인딩 확인
3. Signal → Risk → Decision → Order 이벤트 연결 확인
4. DRY_RUN order가 broker submit 없이 감사 기록되는지 확인
5. run 완료 시 필수 이벤트 완전성 검증
6. Report Engine이 audit summary를 생성하는지 확인
7. 하나의 decision에서 원천 데이터까지 trace 가능한지 확인
8. policy 변경 후 이전 run이 기존 snapshot을 계속 참조하는지 확인

### 22.5 실패 주입 테스트

- audit DB lock timeout
- compliance evaluator 예외
- hash calculator 오류
- redactor가 secret을 탐지한 경우
- stream sequence 충돌
- incident 저장 실패
- 외부 root hash 저장 실패
- Orchestrator critical stage 실패 후 order stage 강제 호출

### 22.6 보안 테스트

- access token pattern이 payload에 남지 않는다.
- SQL injection 문자열이 query scope를 변경하지 못한다.
- rule expression에서 임의 코드 실행이 불가능하다.
- 권한 없는 사용자가 audit export를 수행하지 못한다.
- 감사 조회도 접근 로그에 남는다.
- export artifact에는 마스킹 정책이 동일하게 적용된다.

### 22.7 회귀 테스트

- 같은 이벤트 집합은 같은 chain root hash를 생성한다.
- 규칙 버전이 같으면 같은 입력에 같은 평가 결과를 생성한다.
- 새로운 optional field 추가가 기존 schema version 처리에 영향을 주지 않는다.
- 감사 엔진 비활성화가 LIVE mode에서 허용되지 않는다.
- 기존 Decision/Order 결과는 감사 엔진 추가 전후 동일하다.

### 22.8 성능 테스트

- 10만 건 감사 이벤트 append 처리량 측정
- run 1건당 1천 이벤트 조회 시간 측정
- 전체 stream chain 검증 시간 측정
- 규칙 100개 동시 평가 시간 측정
- payload 1MB 초과 시 외부 artifact 참조 전환 확인

## 23. 구현 순서

1. AuditEventInput, AuditRecord, ComplianceEvaluation 모델
2. canonical JSON, redaction, hash 함수
3. SQLite schema와 append-only repository
4. stream sequence 및 hash chain
5. AuditPublisher와 Orchestrator 연동
6. 핵심 통제 AC-001~AC-006 구현
7. 사건 저장소와 상태 전이
8. Decision/Order/Execution 이벤트 연동
9. run completeness verifier
10. Report fixture와 감사 요약
11. 예외 승인 모델
12. 외부 root hash 서명 또는 별도 저장

## 24. 최소 구현 범위 v1

v1은 다음 범위까지 구현한다.

- SQLite append-only audit journal
- run stream 기준 hash chain
- policy/data/decision/order/execution 참조 저장
- 핵심 통제 AC-001~AC-006
- CRITICAL incident 생성
- secret redaction
- run 완료 시 체인과 필수 이벤트 검증
- Markdown/JSON audit summary fixture

다음 항목은 후속 버전으로 둔다.

- 복수 조직·법인별 규제 템플릿
- 외부 전자서명 서비스 연동
- 실시간 SIEM 연동
- 복잡한 통계 기반 이상 탐지
- 법적 보존 자동 워크플로
- 대규모 분산 event streaming

## 25. 완료 기준

Audit & Compliance Engine v1은 다음 조건을 만족하면 설계·구현 완료로 본다.

1. 모든 run의 핵심 이벤트를 표준 형식으로 저장한다.
2. 이벤트가 append-only이며 stream별 hash chain으로 연결된다.
3. policy snapshot과 data snapshot을 decision/order까지 추적할 수 있다.
4. LIVE_BLOCKED broker 호출과 필수 증거 누락을 탐지한다.
5. CRITICAL 통제 위반이 Orchestrator의 후속 단계 차단으로 이어진다.
6. 수동 override와 예외 승인 이력이 저장된다.
7. run 완료 시 감사 완전성과 hash chain 검증 결과가 생성된다.
8. Report Engine이 감사 요약과 열린 사건을 출력할 수 있다.
9. 민감정보가 감사 payload에 평문으로 저장되지 않는다.
10. 단위·통합·보안·실패 주입 테스트가 통과한다.

## 26. 다음 단계

다음 설계 대상으로 **Scheduler & Trigger Engine v1**을 권장한다.

이 엔진은 시장 개장 전 분석, 장중 점검, 장 마감 리포트, 데이터 재수집, 백테스트, 장애 재처리를 시간·이벤트 조건에 따라 안전하게 실행하며 다음 기능을 담당한다.

- 시간 기반 및 이벤트 기반 실행 요청 생성
- 거래일·시장 세션 인식
- 중복 실행 방지와 misfire 정책
- 실행 우선순위와 동시성 제한
- 실패 재시도와 dead-letter 관리
- Orchestrator RunRequest 생성
- 운영 모드별 허용 trigger 통제
- 스케줄 변경 감사 기록
