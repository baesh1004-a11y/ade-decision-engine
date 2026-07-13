# 15. Configuration & Policy Engine v1

## 1. 목적

Configuration & Policy Engine은 ADE 전체 엔진이 사용하는 설정값과 정책을 중앙에서 관리하고, 실행 시점에 검증된 불변 설정 스냅샷을 제공하는 제어 계층이다.

이 엔진은 매수·매도 판단을 직접 생성하지 않는다. Signal, Risk, Decision, Order, Execution, Backtest, Report, Orchestrator가 동일한 정책 버전과 설정 해시를 사용하도록 보장한다.

주요 목적은 다음과 같다.

- 엔진별 임계값과 가중치 중앙 관리
- 운영 모드별 허용 정책 강제
- 정책 버전 및 변경 이력 관리
- 실행별 설정 스냅샷과 재현성 보장
- 잘못된 설정의 실행 전 차단
- 승인되지 않은 LIVE 설정 사용 금지
- 정책 롤백과 감사 추적 지원

## 2. 문제 정의

현재 설계 문서에는 각 엔진의 기본값이 개별적으로 정의되어 있다.

예:

- Signal Engine: 점수 가중치와 분류 임계값
- Risk Engine: 최대 포지션, 최대 노출도, 일일 손실 한도
- Decision Engine: 매수·매도·손절·익절 임계값
- Order Engine: 거래 모드, 주문 유형, 중복 주문 정책
- Execution Monitor: 재시도, 만료, 부분체결 처리
- Backtest Engine: 수수료, 세금, 슬리피지, 체결 규칙

이 값들이 코드에 직접 분산되면 다음 문제가 발생한다.

1. 동일 실행에서 엔진별 정책 버전이 달라질 수 있다.
2. 설정 변경이 결과에 미친 영향을 추적하기 어렵다.
3. 백테스트 결과 재현성이 약해진다.
4. LIVE 모드에서 위험한 설정이 실수로 적용될 수 있다.
5. 설정 변경에 대한 승인·롤백·감사 기록이 남지 않는다.

Configuration & Policy Engine은 이 문제를 해결하기 위한 단일 정책 진입점이다.

## 3. 책임 경계

### 3.1 담당

- 정책 정의와 스키마 관리
- 정책 버전 생성, 검증, 활성화, 폐기
- 실행 모드별 정책 선택
- 엔진별 설정 조합 및 상속
- 정책 간 교차 검증
- 실행 시 불변 설정 스냅샷 생성
- canonical JSON 및 SHA-256 해시 생성
- 민감정보 제거와 허용 필드 검증
- 정책 변경 이력 및 승인 상태 저장

### 3.2 담당하지 않음

- 시장 데이터 수집
- 투자 신호 계산
- 리스크 점수 계산
- 매수·매도 의사결정
- 주문 생성 또는 전송
- 체결 상태 조회
- 백테스트 실행
- API 키와 계좌 비밀번호 저장

## 4. ADE 내 위치

```text
Policy Author / Operator
          ↓
Configuration & Policy Engine
  ├─ Schema Registry
  ├─ Policy Validator
  ├─ Cross-Policy Guard
  ├─ Version Manager
  ├─ Approval Gate
  ├─ Snapshot Builder
  └─ Policy Repository
          ↓
Immutable Policy Snapshot
          ↓
Integration Orchestrator
  ├─ DataHub / Quality
  ├─ Portfolio State
  ├─ Signal
  ├─ Risk
  ├─ Decision
  ├─ Order
  ├─ Execution
  ├─ Backtest
  └─ Report
```

모든 엔진은 설정 저장소를 직접 조회하지 않는다. Orchestrator가 실행 시작 시 정책 스냅샷을 생성하고 각 단계에 전달한다.

## 5. 핵심 원칙

1. 실행 중인 정책 스냅샷은 변경할 수 없다.
2. 모든 실행 결과에는 `policy_version`과 `config_hash`가 포함되어야 한다.
3. 정책 변경은 새 버전을 생성하며 기존 버전을 덮어쓰지 않는다.
4. LIVE 정책은 명시적 승인 없이는 활성화할 수 없다.
5. 정책 스키마와 정책 데이터는 각각 버전 관리한다.
6. 엔진은 전달받은 설정만 사용하고 전역 설정을 직접 읽지 않는다.
7. 알 수 없는 필드와 잘못된 타입은 기본적으로 거부한다.
8. 민감정보는 정책 저장소와 실행 스냅샷에 저장하지 않는다.
9. 같은 정책·같은 입력은 같은 `config_hash`를 생성해야 한다.
10. 백테스트 정책과 실거래 정책은 명시적으로 구분한다.

## 6. 정책 구성

### 6.1 최상위 정책 모델

```python
PolicyBundle(
    policy_id="ade_default",
    version="1.0.0",
    schema_version="1.0",
    status="ACTIVE",
    environment="PRODUCTION",
    allowed_modes=["DRY_RUN", "PAPER", "LIVE_BLOCKED"],
    signal=SignalPolicy(...),
    risk=RiskPolicy(...),
    decision=DecisionPolicy(...),
    order=OrderPolicy(...),
    execution=ExecutionPolicy(...),
    backtest=BacktestPolicy(...),
    report=ReportPolicy(...),
    metadata=PolicyMetadata(...),
)
```

### 6.2 Signal 정책

```python
@dataclass(frozen=True)
class SignalPolicy:
    trend_weight: float = 0.30
    momentum_weight: float = 0.25
    volume_weight: float = 0.20
    volatility_weight: float = 0.15
    portfolio_weight: float = 0.10
    strong_buy_threshold: float = 80.0
    buy_candidate_threshold: float = 65.0
    watch_threshold: float = 50.0
    minimum_history_days: int = 120
```

검증 규칙:

- 모든 가중치는 0 이상 1 이하
- 가중치 합은 허용 오차 내에서 1.0
- `strong_buy > buy_candidate > watch`
- 점수 임계값은 0~100
- 최소 이력은 장기 지표 계산 기간 이상

### 6.3 Risk 정책

```python
@dataclass(frozen=True)
class RiskPolicy:
    max_position_pct: float = 0.10
    max_total_exposure_pct: float = 0.90
    max_daily_loss_pct: float = 0.02
    min_cash_buffer_pct: float = 0.10
    max_volatility_pct: float = 0.08
    min_avg_volume_value: float = 1_000_000_000
    max_risk_score: float = 70.0
```

검증 규칙:

- 비율은 0~1
- `max_position_pct <= max_total_exposure_pct`
- `min_cash_buffer_pct + max_total_exposure_pct <= 1.0` 권고
- 유동성 하한은 음수 불가
- 위험 점수 상한은 0~100
- LIVE 정책은 `max_total_exposure_pct > 0.95` 금지

### 6.4 Decision 정책

```python
@dataclass(frozen=True)
class DecisionPolicy:
    strong_buy_threshold: float = 80.0
    buy_threshold: float = 65.0
    watch_threshold: float = 50.0
    sell_threshold: float = 35.0
    stop_loss_pct: float = -0.07
    reduce_loss_pct: float = -0.04
    take_profit_pct: float = 0.12
    min_confidence_to_buy: float = 0.65
    max_position_weight: float = 0.10
```

검증 규칙:

- Signal 분류 임계값과 의미가 충돌하지 않아야 한다.
- `stop_loss_pct < reduce_loss_pct < 0`
- `take_profit_pct > 0`
- 신뢰도는 0~1
- 최대 포지션 비중은 Risk 정책 상한 이하

### 6.5 Order 정책

```python
@dataclass(frozen=True)
class OrderPolicy:
    default_mode: str = "LIVE_BLOCKED"
    allowed_order_types: tuple[str, ...] = ("MARKET", "LIMIT")
    allowed_time_in_force: tuple[str, ...] = ("DAY",)
    duplicate_window_seconds: int = 300
    max_order_amount: float = 10_000_000
    live_enabled: bool = False
    require_market_open: bool = True
```

검증 규칙:

- `default_mode`는 정책 번들의 허용 모드에 포함
- `live_enabled=True`이면 승인 상태가 `APPROVED_FOR_LIVE`
- 최대 주문 금액은 양수
- 중복 주문 방지 시간은 0 이상
- LIVE 정책은 주문 상한 필수

### 6.6 Execution 정책

```python
@dataclass(frozen=True)
class ExecutionPolicy:
    poll_interval_seconds: int = 5
    max_poll_attempts: int = 60
    order_expiry_seconds: int = 300
    max_api_retries: int = 2
    retry_backoff_seconds: float = 1.0
    allow_partial_fill: bool = True
    duplicate_event_guard: bool = True
```

검증 규칙:

- 재시도 횟수는 0~5
- 폴링 간격과 만료 시간은 양수
- `poll_interval_seconds * max_poll_attempts`는 비정상적으로 큰 값을 제한
- 중복 체결 방지는 LIVE/PAPER에서 반드시 활성화

### 6.7 Backtest 정책

```python
@dataclass(frozen=True)
class BacktestPolicy:
    fee_rate: float = 0.00015
    tax_rate: float = 0.0018
    slippage_bps: float = 5.0
    fill_at_next_bar: bool = True
    allow_partial_fill: bool = False
    enforce_no_lookahead: bool = True
    max_positions: int = 10
```

검증 규칙:

- 수수료, 세금, 슬리피지는 음수 불가
- `enforce_no_lookahead`는 항상 True
- 백테스트에서 LIVE 브로커 설정 금지
- 최대 포지션 수는 1 이상

### 6.8 Report 정책

```python
@dataclass(frozen=True)
class ReportPolicy:
    output_formats: tuple[str, ...] = ("MARKDOWN", "JSON")
    include_raw_payload: bool = False
    include_policy_snapshot: bool = True
    mask_account_identifiers: bool = True
    critical_severity_threshold: int = 1
```

## 7. 정책 상태 모델

```text
DRAFT
  ↓ validate
VALIDATED
  ↓ approve
APPROVED
  ↓ activate
ACTIVE
  ├─→ DEPRECATED
  └─→ REVOKED
```

LIVE 전용 상태:

```text
APPROVED
  ↓ live safety review
APPROVED_FOR_LIVE
  ↓ activate
ACTIVE
```

상태 의미:

| 상태 | 의미 |
|---|---|
| DRAFT | 작성 중, 실행 사용 불가 |
| VALIDATED | 스키마·교차 검증 통과 |
| APPROVED | 운영자 승인 완료 |
| APPROVED_FOR_LIVE | 실계좌 안전 승인 완료 |
| ACTIVE | 신규 실행에서 선택 가능 |
| DEPRECATED | 신규 실행 사용 중단, 과거 재현 가능 |
| REVOKED | 보안·안전 사유로 즉시 사용 금지 |

## 8. 입력과 출력

### 8.1 입력

```python
PolicyResolutionRequest(
    policy_id="ade_default",
    version="1.0.0",
    mode="PAPER",
    environment="PRODUCTION",
    run_id="run_20260713_001",
    overrides={
        "backtest.slippage_bps": 7.5,
    },
    requested_by="scheduler",
)
```

### 8.2 출력

```python
PolicySnapshot(
    snapshot_id="cfg_20260713_001",
    policy_id="ade_default",
    policy_version="1.0.0",
    schema_version="1.0",
    mode="PAPER",
    resolved_config={...},
    config_hash="b5f0...a91c",
    created_at="2026-07-13T00:00:00Z",
    warnings=[],
)
```

## 9. 설정 상속과 오버라이드

정책 해석 순서:

```text
System Defaults
      ↓
Environment Policy
      ↓
Named Policy Version
      ↓
Mode Policy
      ↓
Allowed Run Overrides
      ↓
Validated Immutable Snapshot
```

오버라이드 원칙:

- 허용 목록에 포함된 필드만 변경 가능
- LIVE 모드에서는 실행 단위 오버라이드 기본 금지
- 임계값 완화보다 강화 방향만 허용할 수 있음
- 변경 후 전체 교차 검증을 다시 수행
- 오버라이드 내용도 `config_hash`에 포함

예:

| 필드 | DRY_RUN | PAPER | LIVE_BLOCKED | LIVE |
|---|---:|---:|---:|---:|
| backtest.slippage_bps | 허용 | 허용 | 무관 | 금지 |
| risk.max_position_pct | 허용 | 축소만 허용 | 축소만 허용 | 금지 |
| order.live_enabled | 금지 | 금지 | 금지 | 승인 정책만 허용 |
| report.output_formats | 허용 | 허용 | 허용 | 허용 |

## 10. 교차 정책 검증

개별 엔진 정책이 유효해도 정책 간 충돌이 발생할 수 있다.

필수 교차 검증:

1. `decision.max_position_weight <= risk.max_position_pct`
2. Decision과 Signal의 매수 임계값 의미 일치
3. `order.max_order_amount`가 Risk 계산 한도를 우회하지 않음
4. LIVE 모드에서 `order.live_enabled=True`와 LIVE 승인 상태 동시 충족
5. Backtest에서 브로커 어댑터 접근 설정 금지
6. Execution 만료 시간이 Order 유효시간 정책과 충돌하지 않음
7. Report의 원본 payload 출력 시 계좌·인증정보 마스킹 필수
8. Risk 현금 버퍼와 최대 노출도 합이 정책 허용 범위 내 존재

```python
def validate_cross_policy(bundle: PolicyBundle) -> list[PolicyViolation]:
    violations = []

    if bundle.decision.max_position_weight > bundle.risk.max_position_pct:
        violations.append(
            PolicyViolation(
                code="DECISION_POSITION_EXCEEDS_RISK_LIMIT",
                path="decision.max_position_weight",
                severity="ERROR",
            )
        )

    if bundle.order.live_enabled and bundle.status != "APPROVED_FOR_LIVE":
        violations.append(
            PolicyViolation(
                code="LIVE_POLICY_NOT_APPROVED",
                path="order.live_enabled",
                severity="CRITICAL",
            )
        )

    return violations
```

## 11. 데이터베이스 설계

### 11.1 `policy_definitions`

```sql
CREATE TABLE IF NOT EXISTS policy_definitions (
    policy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    environment TEXT NOT NULL,
    status TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    description TEXT,
    created_by TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    activated_at TEXT,
    deprecated_at TEXT,
    PRIMARY KEY (policy_id, version),
    CHECK (status IN (
        'DRAFT','VALIDATED','APPROVED','APPROVED_FOR_LIVE',
        'ACTIVE','DEPRECATED','REVOKED'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_policy_hash
ON policy_definitions(policy_hash);

CREATE INDEX IF NOT EXISTS ix_policy_status_environment
ON policy_definitions(status, environment, activated_at DESC);
```

### 11.2 `policy_components`

```sql
CREATE TABLE IF NOT EXISTS policy_components (
    component_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    engine_name TEXT NOT NULL,
    component_json TEXT NOT NULL,
    component_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (policy_id, policy_version)
        REFERENCES policy_definitions(policy_id, version)
        ON DELETE CASCADE,
    UNIQUE (policy_id, policy_version, engine_name)
);
```

### 11.3 `policy_approvals`

```sql
CREATE TABLE IF NOT EXISTS policy_approvals (
    approval_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    approval_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    approver TEXT NOT NULL,
    reason TEXT,
    evidence_ref TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (policy_id, policy_version)
        REFERENCES policy_definitions(policy_id, version)
        ON DELETE CASCADE,
    CHECK (approval_type IN ('STANDARD','LIVE_SAFETY','EMERGENCY')),
    CHECK (decision IN ('APPROVED','REJECTED','REVOKED'))
);
```

### 11.4 `policy_snapshots`

```sql
CREATE TABLE IF NOT EXISTS policy_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    mode TEXT NOT NULL,
    environment TEXT NOT NULL,
    resolved_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    override_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (run_id),
    FOREIGN KEY (policy_id, policy_version)
        REFERENCES policy_definitions(policy_id, version)
);

CREATE INDEX IF NOT EXISTS ix_policy_snapshots_hash
ON policy_snapshots(config_hash);
```

### 11.5 `policy_audit_events`

```sql
CREATE TABLE IF NOT EXISTS policy_audit_events (
    event_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL
);
```

이벤트 유형:

- CREATED
- VALIDATED
- APPROVED
- LIVE_APPROVED
- ACTIVATED
- DEPRECATED
- REVOKED
- SNAPSHOT_CREATED
- RESOLUTION_REJECTED

## 12. 도메인 모델

```python
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    path: str
    message: str
    severity: str = "ERROR"


@dataclass(frozen=True)
class PolicyBundle:
    policy_id: str
    version: str
    schema_version: str
    status: str
    environment: str
    allowed_modes: tuple[str, ...]
    signal: SignalPolicy
    risk: RiskPolicy
    decision: DecisionPolicy
    order: OrderPolicy
    execution: ExecutionPolicy
    backtest: BacktestPolicy
    report: ReportPolicy
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicySnapshot:
    snapshot_id: str
    run_id: str
    policy_id: str
    policy_version: str
    schema_version: str
    mode: str
    environment: str
    resolved_config: Mapping[str, Any]
    config_hash: str
    warnings: tuple[str, ...] = ()
```

## 13. Repository 인터페이스

```python
from typing import Protocol


class PolicyRepository(Protocol):
    def save_draft(self, bundle: PolicyBundle, actor: str) -> None: ...
    def get_policy(self, policy_id: str, version: str) -> PolicyBundle | None: ...
    def get_active_policy(self, environment: str, mode: str) -> PolicyBundle | None: ...
    def transition_status(
        self,
        policy_id: str,
        version: str,
        target_status: str,
        actor: str,
        reason: str | None = None,
    ) -> PolicyBundle: ...
    def save_approval(self, approval: dict) -> str: ...
    def save_snapshot(self, snapshot: PolicySnapshot) -> None: ...
    def get_snapshot_by_run(self, run_id: str) -> PolicySnapshot | None: ...
    def list_versions(self, policy_id: str) -> list[PolicyBundle]: ...
```

## 14. 핵심 알고리즘

### 14.1 정책 등록

```text
정책 입력 수신
→ schema_version 확인
→ 알 수 없는 필드 검사
→ 엔진별 타입·범위 검증
→ 교차 정책 검증
→ canonical JSON 생성
→ policy_hash 계산
→ DRAFT 또는 VALIDATED 상태 저장
→ 감사 이벤트 기록
```

### 14.2 정책 활성화

```text
정책 조회
→ 현재 상태 APPROVED 또는 APPROVED_FOR_LIVE 확인
→ 환경·모드 적합성 확인
→ 동일 환경의 기존 ACTIVE 정책 조회
→ 트랜잭션 시작
→ 기존 ACTIVE 정책 DEPRECATED 전환
→ 신규 정책 ACTIVE 전환
→ 감사 이벤트 저장
→ 커밋
```

### 14.3 실행 정책 해석

```python
def resolve_policy(request, repository, validator, override_guard):
    existing = repository.get_snapshot_by_run(request.run_id)
    if existing is not None:
        return existing

    bundle = repository.get_policy(request.policy_id, request.version)
    if bundle is None:
        raise PolicyNotFound(request.policy_id, request.version)

    if bundle.status != "ACTIVE":
        raise PolicyNotActive(bundle.status)

    if request.mode not in bundle.allowed_modes:
        raise PolicyModeNotAllowed(request.mode)

    resolved = merge_policy(bundle, request.mode)
    resolved = override_guard.apply(resolved, request.overrides, request.mode)

    violations = validator.validate(resolved, request.mode)
    errors = [v for v in violations if v.severity in {"ERROR", "CRITICAL"}]
    if errors:
        raise PolicyValidationError(errors)

    snapshot = build_snapshot(request, resolved, violations)
    repository.save_snapshot(snapshot)
    return snapshot
```

### 14.4 해시 생성

```python
import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def config_hash(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

### 14.5 안전한 오버라이드

```python
class OverrideGuard:
    ALLOWED = {
        "DRY_RUN": {
            "backtest.slippage_bps",
            "backtest.fee_rate",
            "report.output_formats",
            "risk.max_position_pct",
        },
        "PAPER": {
            "report.output_formats",
            "risk.max_position_pct",
            "order.max_order_amount",
        },
        "LIVE_BLOCKED": {
            "report.output_formats",
            "risk.max_position_pct",
        },
        "LIVE": set(),
    }

    def apply(self, config: dict, overrides: dict, mode: str) -> dict:
        allowed = self.ALLOWED.get(mode, set())
        unknown = set(overrides) - allowed
        if unknown:
            raise OverrideNotAllowed(sorted(unknown))

        updated = deep_copy(config)
        for path, value in overrides.items():
            set_by_path(updated, path, value)
        return updated
```

## 15. Orchestrator 통합

Orchestrator의 실행 단계 앞에 정책 해석 단계를 추가한다.

```text
1. validate_request
2. resolve_policy
3. persist_policy_snapshot
4. load_market_data
5. validate_market_data
6. build_decision_context
7. run_existing_pipeline
8. aggregate_result
9. build_report_fixture
```

`RunResult` 확장:

```python
@dataclass
class RunResult:
    run_id: str
    correlation_id: str
    mode: str
    status: str
    policy_id: str
    policy_version: str
    config_hash: str
    stages: list[dict]
    decisions: dict
    errors: list[str]
    warnings: list[str]
```

각 엔진 입력은 정책 컴포넌트를 명시적으로 포함한다.

```python
signal_result = signal_engine.score(
    indicators=indicators,
    policy=snapshot.signal,
)

risk_result = risk_engine.evaluate(
    risk_input=risk_input,
    policy=snapshot.risk,
)
```

## 16. 오류 모델

| 오류 | 의미 | 처리 |
|---|---|---|
| POLICY_NOT_FOUND | 정책 버전 없음 | 실행 실패 |
| POLICY_NOT_ACTIVE | 비활성 정책 사용 | 실행 실패 |
| POLICY_SCHEMA_UNSUPPORTED | 스키마 버전 미지원 | 실행 실패 |
| POLICY_VALIDATION_FAILED | 범위·타입 검증 실패 | 실행 실패 |
| CROSS_POLICY_CONFLICT | 엔진 간 정책 충돌 | 실행 실패 |
| MODE_NOT_ALLOWED | 실행 모드 불허 | 실행 실패 |
| OVERRIDE_NOT_ALLOWED | 금지된 오버라이드 | 실행 실패 |
| LIVE_POLICY_NOT_APPROVED | LIVE 승인 없음 | 치명 실패 |
| SNAPSHOT_HASH_MISMATCH | 저장 데이터 무결성 오류 | 치명 실패 및 수동 검토 |

## 17. 코드 구조

```text
config/
├── __init__.py
├── models.py              # 정책 dataclass와 snapshot
├── schema.py              # 스키마 버전과 필드 정의
├── validator.py           # 개별 정책 검증
├── cross_validator.py     # 교차 정책 검증
├── resolver.py            # 정책 선택, 병합, snapshot 생성
├── override.py            # 모드별 오버라이드 통제
├── hash.py                # canonical JSON과 SHA-256
├── repository.py          # PolicyRepository protocol
├── sqlite_repository.py   # SQLite 구현
├── approval.py            # 승인 및 상태 전이
└── defaults.py            # 안전한 시스템 기본값

migrations/
└── 015_configuration_policy.sql

tests/
├── test_policy_models.py
├── test_policy_validator.py
├── test_policy_cross_validator.py
├── test_policy_resolver.py
├── test_policy_override.py
├── test_policy_repository.py
├── test_policy_approval.py
└── test_policy_integration.py
```

## 18. 참조 구현

```python
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4


class ConfigurationPolicyEngine:
    def __init__(self, repository, validator, override_guard):
        self.repository = repository
        self.validator = validator
        self.override_guard = override_guard

    def resolve(self, request) -> PolicySnapshot:
        previous = self.repository.get_snapshot_by_run(request.run_id)
        if previous is not None:
            return previous

        bundle = self.repository.get_policy(request.policy_id, request.version)
        if bundle is None:
            raise PolicyNotFound(
                f"policy not found: {request.policy_id}@{request.version}"
            )

        self._validate_access(bundle, request)

        resolved = asdict(bundle)
        resolved = apply_mode_defaults(resolved, request.mode)
        resolved = self.override_guard.apply(
            resolved,
            request.overrides,
            request.mode,
        )

        violations = self.validator.validate(resolved, request.mode)
        blocking = [
            violation
            for violation in violations
            if violation.severity in {"ERROR", "CRITICAL"}
        ]
        if blocking:
            raise PolicyValidationError(blocking)

        snapshot = PolicySnapshot(
            snapshot_id=f"cfg_{uuid4().hex}",
            run_id=request.run_id,
            policy_id=bundle.policy_id,
            policy_version=bundle.version,
            schema_version=bundle.schema_version,
            mode=request.mode,
            environment=request.environment,
            resolved_config=resolved,
            config_hash=config_hash(resolved),
            warnings=tuple(
                violation.code
                for violation in violations
                if violation.severity == "WARNING"
            ),
        )
        self.repository.save_snapshot(snapshot)
        return snapshot

    def _validate_access(self, bundle, request) -> None:
        if bundle.status != "ACTIVE":
            raise PolicyNotActive(bundle.status)
        if request.mode not in bundle.allowed_modes:
            raise PolicyModeNotAllowed(request.mode)
        if request.mode == "LIVE":
            if not bundle.order.live_enabled:
                raise LivePolicyNotApproved("live_enabled is false")
            if not self.repository.has_live_approval(
                bundle.policy_id,
                bundle.version,
            ):
                raise LivePolicyNotApproved("live approval missing")
```

## 19. 테스트 계획

### 19.1 단위 테스트

정책 모델:

- 기본 정책 객체가 생성된다.
- dataclass가 불변 객체로 동작한다.
- 알 수 없는 정책 필드는 거부된다.
- 타입 불일치가 명확한 오류를 반환한다.

Signal 정책:

- 가중치 합이 1이면 통과한다.
- 가중치 합이 1이 아니면 거부된다.
- 임계값 순서가 잘못되면 거부된다.
- 최소 이력이 장기 지표보다 짧으면 거부된다.

Risk 정책:

- 정상 기본값이 통과한다.
- 단일 포지션 한도가 총 노출도보다 크면 거부된다.
- 음수 유동성 하한이 거부된다.
- LIVE에서 95% 초과 노출도가 거부된다.

Decision 정책:

- 손절·축소 임계값 순서가 검증된다.
- 신뢰도가 0~1 범위를 벗어나면 거부된다.
- Decision 포지션 비중이 Risk 한도를 넘으면 교차 검증 실패한다.

Order 정책:

- LIVE_BLOCKED가 안전 기본값으로 허용된다.
- 승인되지 않은 LIVE 설정은 거부된다.
- 최대 주문 금액 0 이하가 거부된다.
- 허용되지 않은 주문 유형이 거부된다.

Execution 정책:

- 음수 재시도 횟수가 거부된다.
- 과도한 재시도 횟수가 거부된다.
- LIVE/PAPER에서 중복 이벤트 방지 비활성화가 거부된다.

Backtest 정책:

- 음수 슬리피지가 거부된다.
- no-lookahead 비활성화가 거부된다.
- 백테스트 정책에서 LIVE 브로커 설정이 거부된다.

### 19.2 Resolver 테스트

- 활성 정책을 정상적으로 해석한다.
- 존재하지 않는 정책은 `POLICY_NOT_FOUND`를 반환한다.
- 비활성 정책 사용을 차단한다.
- 허용되지 않은 모드를 차단한다.
- 허용된 오버라이드를 적용한다.
- 금지된 오버라이드를 차단한다.
- 동일 `run_id` 재호출 시 동일 snapshot을 반환한다.
- 같은 정책과 오버라이드는 같은 해시를 생성한다.
- 오버라이드 변경 시 해시가 달라진다.

### 19.3 Repository 테스트

- 정책 버전이 중복 저장되지 않는다.
- 정책 상태 전이가 허용 규칙을 따른다.
- ACTIVE 정책 활성화 시 기존 정책이 DEPRECATED 된다.
- snapshot과 config hash가 원자적으로 저장된다.
- rollback 발생 시 부분 데이터가 남지 않는다.
- run ID당 snapshot이 하나만 저장된다.
- 정책 조회 시 저장 해시와 재계산 해시가 일치한다.

### 19.4 승인 테스트

- APPROVED 정책만 ACTIVE가 될 수 있다.
- LIVE 정책은 LIVE_SAFETY 승인이 필요하다.
- 승인자와 승인 사유가 기록된다.
- REVOKED 정책은 신규 실행에서 선택되지 않는다.
- 긴급 철회 후 기존 실행 스냅샷은 감사 목적으로 조회 가능하다.

### 19.5 통합 테스트

1. 정책 생성 → 검증 → 승인 → 활성화 전 과정을 수행한다.
2. Orchestrator가 실행 시작 시 snapshot을 생성한다.
3. Signal/Risk/Decision이 동일 `config_hash`를 사용한다.
4. Report 결과에 정책 버전과 해시가 포함된다.
5. Backtest를 같은 입력·정책으로 두 번 실행하면 동일 설정 해시를 사용한다.
6. LIVE_BLOCKED 정책에서 브로커 전송이 발생하지 않는다.
7. 승인되지 않은 LIVE 실행은 첫 단계에서 차단된다.

### 19.6 실패 주입 테스트

- 정책 DB 읽기 실패
- snapshot 저장 중 DB 오류
- 해시 불일치
- 잘못된 JSON payload
- 지원하지 않는 schema version
- 두 정책 동시 활성화 경쟁 조건
- 정책 활성화 트랜잭션 중단
- 승인 레코드 누락

### 19.7 회귀 테스트

- 기본 정책 값이 기존 엔진 문서의 기본값과 일치한다.
- 정책 엔진 도입 전 Candidate 알고리즘 결과가 호환 모드에서 유지된다.
- config key 정렬 순서가 달라도 같은 해시를 생성한다.
- Python 버전이 달라도 canonical JSON 결과가 동일하다.
- 기존 실행 snapshot은 신규 정책 버전 생성 후에도 변경되지 않는다.

## 20. 보안 및 운영 통제

- API 키, 비밀번호, 토큰, 계좌 인증정보 저장 금지
- 정책 변경 권한과 실행 권한 분리
- LIVE 승인 권한은 일반 정책 승인 권한과 분리
- 정책 JSON 크기 제한
- 모든 변경 이벤트 감사 로그 저장
- 승인자 자기 승인 방지 권고
- 정책 철회 시 신규 실행 즉시 차단
- 환경 간 정책 복사 시 새 승인 필요
- 정책 조회 결과에 민감 메타데이터 마스킹

## 21. 마이그레이션 전략

### 1단계: 기본 정책 추출

- 기존 엔진 문서와 코드의 기본값을 `config/defaults.py`로 이동
- 기존 코드 동작을 바꾸지 않고 dataclass로 감싼다.

### 2단계: 명시적 주입

- Signal, Risk, Decision 함수에 `policy` 인자 추가
- 인자를 생략하면 기존 기본 정책 사용
- 회귀 테스트로 결과 동일성 확인

### 3단계: Snapshot 도입

- Orchestrator에 `resolve_policy` 단계 추가
- 실행마다 `policy_snapshots` 저장
- Report에 `policy_version`, `config_hash` 출력

### 4단계: 중앙 저장소 활성화

- SQLite 정책 저장소 도입
- 버전·승인·활성화 상태 사용
- 코드 내 하드코딩된 임계값 제거

### 5단계: LIVE 안전 통제

- LIVE_SAFETY 승인 워크플로 도입
- 기본 모드는 계속 `LIVE_BLOCKED`
- 실계좌 연동 전 별도 안전 리뷰 수행

## 22. 구현 우선순위

1. 정책 dataclass와 안전 기본값
2. 개별 정책 validator
3. 교차 정책 validator
4. canonical JSON과 config hash
5. PolicySnapshot 생성
6. SQLite schema와 repository
7. Orchestrator `resolve_policy` 단계
8. Signal/Risk/Decision 명시적 정책 주입
9. Report 정책 메타데이터 출력
10. 승인·활성화·철회 워크플로

## 23. 완료 기준

Configuration & Policy Engine v1은 다음 조건을 만족하면 구현 완료로 본다.

1. ADE 주요 엔진의 설정이 하나의 정책 번들로 표현된다.
2. 개별·교차 정책 검증이 자동화된다.
3. 실행마다 불변 정책 snapshot과 config hash가 저장된다.
4. 동일 정책과 입력은 동일 해시를 생성한다.
5. 모든 엔진이 동일 snapshot을 사용한다.
6. 정책 버전과 변경 이력이 추적된다.
7. 승인되지 않은 LIVE 정책은 실행 전에 차단된다.
8. 기존 실행은 정책 변경 후에도 재현 가능하다.
9. Orchestrator와 Report가 정책 메타데이터를 포함한다.
10. 단위·통합·실패 주입·회귀 테스트가 통과한다.

## 24. 다음 단계

다음 설계 대상으로는 **Data Snapshot & Lineage Engine**이 적합하다.

이 엔진은 다음을 담당한다.

- 시장 데이터 스냅샷 식별
- 입력 데이터 버전과 출처 추적
- 실행 결과와 원천 데이터 연결
- 백테스트 재현성 강화
- 데이터 변경·정정 이력 관리
- Report와 감사 로그의 lineage 제공
