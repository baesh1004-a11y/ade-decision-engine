# 48. Model Governance, Promotion, Rollback & Audit Engine v1

## 1. 목적

Model Governance, Promotion, Rollback & Audit Engine은 ADE에서 생성되는 모델, 정책, 파라미터 세트, 룰셋의 **등록, 검증, 승인, 승격, 활성화, 감시, 롤백, 폐기, 감사 추적**을 하나의 공통 통제면(control plane)으로 관리하는 계층이다.

47번 Execution Calibration Engine이 challenger를 만들 수 있다면, 48번은 그 challenger가 실제 ADE 의사결정 경로에 들어가도 되는지 최종 통제한다.

핵심 목표는 다음과 같다.

1. 승인되지 않은 모델/정책의 ACTIVE 사용 차단
2. champion/challenger 승격 기준의 표준화
3. 모델 성능뿐 아니라 안정성, tail risk, regime robustness, lineage 검증
4. 단계적 배포와 rollback point 보존
5. 모든 변경의 immutable audit trail 생성
6. 누가, 언제, 어떤 근거로 무엇을 승인했는지 재현
7. 긴급 kill switch와 deterministic rollback 제공
8. 과거 백테스트에서 당시 ACTIVE 버전을 정확히 재현
9. 모델과 정책 dependency graph 관리
10. 자동 학습과 production activation의 분리

본 엔진은 종목 선택, 주문 생성, 포트폴리오 비중 계산, 모델 학습 자체를 수행하지 않는다.

---

## 2. 책임 경계

### 수행 책임

- model/policy artifact registry
- artifact versioning
- lineage 및 dependency graph 검증
- governance state machine
- validation evidence 수집
- promotion gate 평가
- human/system approval 기록
- canary/shadow/staged activation 정책
- ACTIVE pointer 관리
- rollback target 관리
- kill switch
- drift/incident 기반 rollback trigger
- immutable audit event 생성
- historical active-version resolution
- reproducibility manifest 생성

### 수행하지 않는 책임

- signal 계산
- factor 계산
- execution model 학습
- market data 수집
- live 주문 전송
- P&L 회계
- 모델 하이퍼파라미터 최적화

---

## 3. 상위 아키텍처

```text
Model / Policy Producers
────────────────────────────────────────
20 Regime
34 Transaction Cost
38 Fundamental
39 Factor
40 Expectations
41 Market Behavior
42 Signal Integration
43 Regime Adaptation
44 Portfolio Construction
45 Trade Lifecycle
46 Execution Simulation
47 Calibration
        ↓
Candidate Artifact
        ↓
┌──────────────────────────────────────┐
│ 48 Model Governance Engine           │
├──────────────────────────────────────┤
│ Artifact Registry                    │
│ Lineage / Dependency Validation      │
│ Evidence Validation                  │
│ Promotion Gate                       │
│ Approval Workflow                    │
│ Deployment Stage Controller          │
│ ACTIVE Pointer Manager               │
│ Drift / Incident Monitor Interface   │
│ Rollback Controller                  │
│ Kill Switch                          │
│ Audit Ledger                         │
└──────────────────────────────────────┘
        ↓
APPROVED / ACTIVE Artifact Snapshot
        ↓
ADE Runtime Engines
```

48번은 ADE의 **control plane**이며, 실제 투자 판단을 수행하는 engine들은 **data plane**으로 취급한다.

---

## 4. Artifact 유형

모든 변경 대상을 공통 `governed_artifact`로 추상화한다.

```text
MODEL
POLICY
RULESET
PARAMETER_SET
FEATURE_SCHEMA
SCORING_PROFILE
RISK_PROFILE
EXECUTION_PROFILE
CALIBRATION_PROFILE
```

예:

```text
MODEL
execution_slippage_huber_v3

POLICY
signal_integration_policy_v5

PARAMETER_SET
risk_off_profile_202608

RULESET
trade_lifecycle_exit_rules_v2
```

---

## 5. Governance State Machine

모든 artifact는 하나의 상태를 가진다.

```text
DRAFT
  ↓
REGISTERED
  ↓
VALIDATING
  ↓
VALIDATED
  ↓
CHALLENGER
  ↓
APPROVAL_PENDING
  ↓
APPROVED
  ↓
SHADOW
  ↓
CANARY
  ↓
ACTIVE
  ↓
DEPRECATED
  ↓
RETIRED
```

예외 상태:

```text
REJECTED
QUARANTINED
ROLLBACK_PENDING
ROLLED_BACK
EMERGENCY_DISABLED
```

허용되지 않는 직접 전이:

```text
DRAFT → ACTIVE
REGISTERED → ACTIVE
VALIDATED → ACTIVE
CHALLENGER → ACTIVE
```

---

## 6. 핵심 원칙

### 6.1 학습 완료와 실전 승격을 분리한다

```text
TRAINED != APPROVED
APPROVED != ACTIVE
```

### 6.2 ACTIVE는 pointer다

모델 파일이나 정책 row를 UPDATE하여 현재 버전을 바꾸지 않는다.

```text
artifact version immutable
        ↓
active_binding pointer 변경
```

따라서 rollback은 이전 artifact를 다시 작성하는 것이 아니라 ACTIVE pointer를 이전 승인 버전으로 이동시키는 방식이다.

### 6.3 과거 ACTIVE 상태를 수정하지 않는다

모든 binding에는 유효시점을 둔다.

```text
valid_from
valid_to
```

과거 백테스트에서:

```text
resolve_active_artifact(as_of_time)
```

를 호출하면 당시 실제 ACTIVE였던 버전을 반환해야 한다.

### 6.4 자동 activation 금지

v1 기본 정책:

```text
system may:
  REGISTER
  VALIDATE
  REJECT
  QUARANTINE
  recommend promotion

system may not:
  ACTIVE production artifact automatically
```

PAPER 전용 환경은 정책으로 자동승격을 허용할 수 있으나 LIVE/PRODUCTION은 별도 승인 requirement를 갖는다.

---

## 7. Artifact Identity

artifact를 단순 이름으로 식별하지 않는다.

```text
artifact_id
artifact_type
artifact_name
version
semantic_version
content_hash
code_commit_sha
schema_hash
policy_hash
created_at
known_at
```

동일 이름이라도 content hash가 다르면 다른 artifact다.

```text
identity = hash(
    artifact_type,
    artifact_name,
    semantic_version,
    content_hash,
    code_commit_sha,
    schema_hash
)
```

---

## 8. Lineage Graph

승격 전에 dependency를 완전히 고정한다.

예:

```text
Signal Integration v5
├── Fundamental schema v3
├── Factor policy v4
├── Expectations policy v2
├── Market Behavior feature registry v6
├── Regime profile v3
└── normalization policy v2
```

artifact는 다음 정보를 저장한다.

```text
parent_artifact_ids
input_schema_ids
feature_registry_ids
training_dataset_snapshot_id
validation_dataset_snapshot_id
source_commit_sha
runtime_dependency_hash
```

Dependency가 승인되지 않았거나 폐기됐으면 승격을 차단한다.

Reason Code:

```text
DEPENDENCY_NOT_APPROVED
DEPENDENCY_RETIRED
LINEAGE_INCOMPLETE
LINEAGE_HASH_MISMATCH
```

---

## 9. Promotion Gate

Promotion은 단일 성능지표가 아니라 다단계 gate다.

```text
Gate 1 Integrity
Gate 2 Reproducibility
Gate 3 Performance
Gate 4 Risk
Gate 5 Robustness
Gate 6 Operational
Gate 7 Approval
```

### Gate 1. Integrity

필수:

```text
future_information_violations == 0
schema_validation_errors == 0
lineage_errors == 0
missing_required_artifacts == 0
```

하나라도 실패하면 즉시 REJECTED.

### Gate 2. Reproducibility

동일 snapshot에서 반복 실행한다.

```text
run_1.output_hash
== run_2.output_hash
== run_3.output_hash
```

deterministic engine인데 불일치하면 승격 금지.

### Gate 3. Performance

artifact 유형별 metric registry를 사용한다.

예: execution model

```text
MAE
RMSE
Brier Score
Implementation Shortfall Error
Fill Ratio Error
```

signal model 예:

```text
IC
Rank IC
Hit Rate
Precision@K
Forward Return Spread
```

포트폴리오 정책 예:

```text
Net Return
Sharpe
Sortino
Max Drawdown
Turnover
Transaction Cost
```

### Gate 4. Risk

평균성능이 좋아도 tail risk 악화 시 실패할 수 있다.

```text
P95 Error
P99 Error
Max Drawdown
Worst 5D
Worst Regime Loss
Liquidity Stress Loss
```

### Gate 5. Robustness

최소 다음 cohort를 평가한다.

```text
BULL
NORMAL
RECOVERY
RISK_OFF
CRISIS

HIGH_VOL
LOW_VOL

MEGA_CAP
LARGE_CAP
MID_CAP
SMALL_CAP
```

특정 cohort에서 catastrophic degradation이 있으면 승격 금지.

### Gate 6. Operational

```text
runtime_latency
memory_usage
failure_rate
fallback_success_rate
schema_compatibility
migration_readiness
```

### Gate 7. Approval

승인 정책을 만족해야 한다.

예:

```text
PAPER:
1 system approval 가능

LIVE_SHADOW:
1 human approval

LIVE:
2 independent approvals
```

역할과 인원은 policy로 관리한다.

---

## 10. Promotion Score는 보조값이다

여러 metric을 종합한 score는 만들 수 있지만 hard gate를 대체하지 않는다.

```text
PromotionScore
= 0.30 × performance
+ 0.25 × robustness
+ 0.20 × risk
+ 0.15 × reproducibility
+ 0.10 × operational
```

하지만:

```text
future info violation > 0
```

이면 PromotionScore가 99여도 승격 불가.

---

## 11. Champion / Challenger

동일 scope에는 기본적으로 하나의 champion이 존재한다.

```text
scope_key
= engine + market + universe + mode
```

예:

```text
engine=execution_cost
market=KRX
universe=KOSPI_KOSDAQ
mode=PAPER
```

비교는 동일한 frozen evaluation dataset으로 수행한다.

```text
Champion
vs
Challenger
```

비교 결과:

```text
DOMINATES
IMPROVES_WITH_TRADEOFF
NO_MATERIAL_DIFFERENCE
DEGRADES
INCONCLUSIVE
```

`INCONCLUSIVE`면 기본적으로 현재 champion 유지.

---

## 12. Material Improvement Threshold

통계적으로 사소한 개선으로 모델을 자주 교체하지 않는다.

예:

```text
minimum_relative_improvement = 3%
minimum_absolute_improvement = metric-specific
```

그리고 변경비용도 고려한다.

```text
change_utility
= expected_improvement
- migration_risk
- operational_risk
- model_complexity_penalty
```

새 모델이 0.2% 좋아졌지만 복잡성이 3배라면 `NO_MATERIAL_DIFFERENCE`가 가능하다.

---

## 13. Shadow → Canary → Active

승인 모델을 즉시 100% 경로에 넣지 않는다.

```text
APPROVED
  ↓
SHADOW
  ↓
CANARY
  ↓
ACTIVE
```

### SHADOW

의사결정에 영향을 주지 않고 기존 champion과 병렬 실행한다.

```text
champion result → 실제 ADE 경로
challenger result → 기록만
```

### CANARY

제한된 scope에서만 challenger 사용.

예:

```text
5% securities
또는
10% paper orders
또는
specific universe
```

### ACTIVE

모든 지정 scope의 default artifact가 된다.

---

## 14. Canary Allocation

v1은 deterministic assignment를 사용한다.

```text
bucket
= hash(security_id, deployment_id) % 100
```

예:

```text
canary_percent = 10
bucket < 10
→ challenger
else
→ champion
```

동일 security가 실행마다 다른 모델로 이동하지 않는다.

---

## 15. Rollback Trigger

Rollback은 수동 또는 자동 trigger를 받을 수 있다.

자동 trigger 예:

```text
CRITICAL_RUNTIME_FAILURE
OUTPUT_SCHEMA_BREAK
DATA_CORRUPTION_DETECTED
LOOKAHEAD_VIOLATION
RISK_LIMIT_BREACH
TAIL_LOSS_BREACH
PERFORMANCE_DRIFT_SEVERE
CALIBRATION_DRIFT_SEVERE
```

Trigger severity:

```text
INFO
WARNING
HIGH
CRITICAL
```

정책 예:

```text
CRITICAL
→ immediate rollback eligible

HIGH
→ rollback_pending + approval
```

---

## 16. Rollback Target

항상 ACTIVE 이전 버전을 쓴다고 가정하지 않는다.

각 deployment는 검증된 rollback target을 명시한다.

```text
rollback_artifact_id
rollback_binding_id
rollback_manifest_hash
```

Rollback target 요구사항:

```text
state in {APPROVED, DEPRECATED}
compatibility_verified = true
artifact_integrity = true
```

RETIRED 또는 QUARANTINED artifact로 rollback 금지.

---

## 17. Deterministic Rollback

```text
1. incident 생성
2. current ACTIVE binding freeze
3. rollback target 검증
4. 새 binding event 생성
5. runtime cache invalidate
6. health check
7. audit event finalize
```

과거 ACTIVE row를 수정하지 않는다.

---

## 18. Kill Switch

즉시 차단이 필요한 경우 artifact 단위 또는 engine scope 단위 kill switch를 둔다.

```text
ARTIFACT_KILL
ENGINE_KILL
SCOPE_KILL
GLOBAL_NEW_ENTRY_KILL
```

예:

```text
Signal engine 이상
→ GLOBAL_NEW_ENTRY_KILL
→ 신규 BUY 차단
→ 기존 SELL/REDUCE 허용
```

안전 원칙:

```text
kill switch는 risk-reducing action을 막지 않는다.
```

---

## 19. Audit Ledger

모든 governance 이벤트는 append-only로 기록한다.

```text
REGISTER
VALIDATION_STARTED
VALIDATION_PASSED
VALIDATION_FAILED
CHALLENGER_CREATED
PROMOTION_REQUESTED
APPROVAL_GRANTED
APPROVAL_REJECTED
SHADOW_STARTED
CANARY_STARTED
ACTIVATED
ROLLBACK_TRIGGERED
ROLLED_BACK
KILL_SWITCH_ENABLED
KILL_SWITCH_DISABLED
DEPRECATED
RETIRED
```

각 이벤트:

```text
audit_event_id
artifact_id
event_type
event_time
actor_type
actor_id
previous_state
new_state
reason_codes
evidence_ids
request_hash
result_hash
previous_event_hash
```

`previous_event_hash`를 포함해 hash chain을 구성할 수 있다.

---

## 20. Approval Separation of Duties

동일 사용자가 challenger 생성과 최종 LIVE 승인을 모두 수행하지 못하도록 정책화할 수 있다.

```text
creator_id != final_approver_id
```

고위험 artifact:

```text
signal logic
risk limits
position sizing
execution routing
```

에는 더 강한 approval policy를 적용한다.

---

## 21. Environment 분리

```text
DEV
BACKTEST
PAPER
LIVE_SHADOW
LIVE
```

승격은 환경별로 독립적이다.

```text
PAPER ACTIVE
!= LIVE ACTIVE
```

PAPER에서 성공해도 LIVE로 자동 복제되지 않는다.

---

## 22. 데이터베이스

### 22.1 `governance_artifacts`

```text
artifact_id PK
artifact_type
artifact_name
semantic_version
content_hash
code_commit_sha
schema_hash
created_at
known_at
created_by
metadata_json
```

### 22.2 `governance_artifact_dependencies`

```text
artifact_id
parent_artifact_id
dependency_type
required_state
relationship_hash
```

### 22.3 `governance_validation_runs`

```text
validation_run_id PK
artifact_id
environment
started_at
completed_at
status
validation_policy_id
input_snapshot_hash
output_hash
```

### 22.4 `governance_validation_metrics`

```text
validation_run_id
metric_name
cohort_key
champion_value
challenger_value
delta
threshold
pass_flag
```

### 22.5 `governance_promotion_requests`

```text
promotion_request_id PK
artifact_id
scope_key
from_state
target_state
requested_at
requested_by
champion_artifact_id
promotion_score
status
request_hash
```

### 22.6 `governance_approvals`

```text
approval_id PK
promotion_request_id
approver_id
approver_role
decision
reason
approved_at
approval_hash
```

### 22.7 `governance_deployments`

```text
deployment_id PK
artifact_id
scope_key
environment
deployment_stage
canary_percent
started_at
ended_at
rollback_artifact_id
status
deployment_hash
```

### 22.8 `governance_active_bindings`

```text
binding_id PK
scope_key
environment
artifact_id
valid_from
valid_to
activation_event_id
binding_hash
```

`valid_to IS NULL`인 row가 현재 binding.

### 22.9 `governance_incidents`

```text
incident_id PK
scope_key
artifact_id
severity
incident_type
detected_at
resolved_at
status
trigger_snapshot_hash
```

### 22.10 `governance_rollbacks`

```text
rollback_id PK
incident_id
from_artifact_id
to_artifact_id
requested_at
executed_at
status
rollback_hash
```

### 22.11 `governance_kill_switches`

```text
kill_switch_id PK
scope_type
scope_key
reason
severity
enabled_at
disabled_at
enabled_by
state_hash
```

### 22.12 `governance_audit_events`

```text
audit_event_id PK
artifact_id
event_type
event_time
actor_type
actor_id
previous_state
new_state
reason_codes_json
evidence_json
previous_event_hash
event_hash
```

### 22.13 `governance_manifests`

```text
manifest_id PK
artifact_id
lineage_hash
validation_hash
approval_hash
deployment_hash
runtime_dependency_hash
manifest_hash
created_at
```

---

## 23. Promotion Policy 예시

```yaml
environment: LIVE
minimum_approvals: 2
require_independent_approver: true
require_reproducibility: true
require_shadow_stage: true
require_canary_stage: true
minimum_shadow_trading_days: 10
minimum_canary_trading_days: 5
maximum_canary_percent: 20
future_information_tolerance: 0
critical_validation_failures_allowed: 0
rollback_target_required: true
```

PAPER:

```yaml
environment: PAPER
minimum_approvals: 0
allow_system_approval: true
require_shadow_stage: false
require_canary_stage: false
future_information_tolerance: 0
rollback_target_required: true
```

---

## 24. Promotion Algorithm

```python
def evaluate_promotion(ctx):
    artifact = registry.get(ctx.artifact_id)
    policy = policies.resolve(ctx.environment, ctx.scope_key)

    validate_artifact_integrity(artifact)
    validate_lineage(artifact)
    validate_dependencies(artifact)

    validation = run_validation_suite(
        artifact=artifact,
        frozen_snapshot=ctx.validation_snapshot,
        champion=ctx.champion,
        policy=policy,
    )

    if validation.future_information_violations > 0:
        return reject("FUTURE_INFORMATION_VIOLATION")

    if not validation.reproducible:
        return reject("NON_DETERMINISTIC_OUTPUT")

    if not validation.performance_gate_passed:
        return reject("PERFORMANCE_GATE_FAILED")

    if not validation.risk_gate_passed:
        return reject("RISK_GATE_FAILED")

    if not validation.robustness_gate_passed:
        return reject("ROBUSTNESS_GATE_FAILED")

    if not validation.operational_gate_passed:
        return reject("OPERATIONAL_GATE_FAILED")

    request = create_promotion_request(
        artifact=artifact,
        validation=validation,
        policy=policy,
    )

    return request
```

---

## 25. Activation Algorithm

```python
def activate_artifact(ctx):
    request = load_promotion_request(ctx.request_id)
    policy = load_governance_policy(request.environment)

    assert request.status == "APPROVED"
    assert approvals_satisfied(request, policy)
    assert rollback_target_verified(request)
    assert artifact_integrity_verified(request.artifact_id)

    current = resolve_current_binding(
        request.scope_key,
        request.environment,
    )

    deployment = create_deployment(
        artifact_id=request.artifact_id,
        rollback_artifact_id=current.artifact_id,
        stage=next_stage(policy),
    )

    append_audit_event("DEPLOYMENT_STARTED", deployment)
    return deployment
```

---

## 26. Rollback Algorithm

```python
def execute_rollback(ctx):
    incident = incidents.get(ctx.incident_id)
    current = resolve_current_binding(
        incident.scope_key,
        incident.environment,
    )

    target = resolve_verified_rollback_target(current)

    if target.state in {"RETIRED", "QUARANTINED"}:
        raise GovernanceBlock("INVALID_ROLLBACK_TARGET")

    close_current_binding(current, ctx.event_time)

    new_binding = create_binding(
        scope_key=current.scope_key,
        environment=current.environment,
        artifact_id=target.artifact_id,
        valid_from=ctx.event_time,
    )

    append_audit_event(
        "ROLLED_BACK",
        from_artifact=current.artifact_id,
        to_artifact=target.artifact_id,
    )

    return new_binding
```

---

## 27. Historical Resolution Algorithm

백테스트와 감사에서 핵심이다.

```python
def resolve_artifact(scope_key, environment, as_of_time):
    return repository.find_binding(
        scope_key=scope_key,
        environment=environment,
        valid_from_lte=as_of_time,
        valid_to_gt=as_of_time,
    )
```

현재 ACTIVE 모델을 과거 시점에 소급 적용하지 않는다.

---

## 28. 코드 구조

```text
governance/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── registry.py
├── repository.py
├── engine.py
│
├── identity.py
├── lineage.py
├── dependencies.py
├── integrity.py
├── states.py
├── transitions.py
│
├── validation/
│   ├── reproducibility.py
│   ├── performance.py
│   ├── risk.py
│   ├── robustness.py
│   ├── operational.py
│   └── temporal.py
│
├── promotion.py
├── approvals.py
├── champion_challenger.py
├── deployment.py
├── shadow.py
├── canary.py
├── bindings.py
│
├── incidents.py
├── rollback.py
├── kill_switch.py
├── health.py
│
├── audit.py
├── manifests.py
├── hashing.py
├── reason_codes.py
└── explainability.py
```

---

## 29. 주요 Reason Code

```text
ARTIFACT_REGISTERED
ARTIFACT_HASH_MISMATCH
SCHEMA_HASH_MISMATCH

LINEAGE_INCOMPLETE
LINEAGE_HASH_MISMATCH
DEPENDENCY_NOT_APPROVED
DEPENDENCY_RETIRED

FUTURE_INFORMATION_VIOLATION
TEMPORAL_SPLIT_INVALID
NON_DETERMINISTIC_OUTPUT

PERFORMANCE_GATE_FAILED
RISK_GATE_FAILED
TAIL_RISK_DEGRADED
ROBUSTNESS_GATE_FAILED
REGIME_ROBUSTNESS_FAILED
OPERATIONAL_GATE_FAILED

NO_MATERIAL_IMPROVEMENT
CHALLENGER_DOMINATES
PROMOTION_INCONCLUSIVE

APPROVAL_REQUIRED
APPROVAL_SEPARATION_VIOLATION
PROMOTION_APPROVED
PROMOTION_REJECTED

SHADOW_REQUIRED
CANARY_REQUIRED
CANARY_HEALTH_FAILED

ROLLBACK_TRIGGERED
ROLLBACK_TARGET_INVALID
ROLLBACK_COMPLETED

KILL_SWITCH_ENABLED
KILL_SWITCH_DISABLED

AUDIT_CHAIN_MISMATCH
ACTIVE_BINDING_CONFLICT
HISTORICAL_BINDING_NOT_FOUND
```

---

## 30. 테스트 계획

### A. 정상 승격

```text
Challenger
→ validation all pass
→ approvals satisfied
→ SHADOW
→ CANARY
→ ACTIVE
```

기대:

```text
모든 상태전이 순서 보존
새 ACTIVE binding 생성
이전 champion rollback target 보존
```

### B. 미래정보 위반

```text
future_information_violations = 1
```

기대:

```text
REJECTED
승격 0건
```

### C. 비결정론적 결과

동일 snapshot을 3회 실행했는데 output hash가 다름.

기대:

```text
NON_DETERMINISTIC_OUTPUT
승격 차단
```

### D. 평균성능 개선, tail risk 악화

```text
mean metric +8%
P99 loss -25% 악화
```

기대:

```text
TAIL_RISK_DEGRADED
승격 차단
```

### E. Regime robustness 실패

```text
NORMAL +10%
RISK_OFF -30%
```

기대:

```text
REGIME_ROBUSTNESS_FAILED
```

### F. 미미한 개선

```text
relative improvement = 0.5%
minimum = 3%
```

기대:

```text
NO_MATERIAL_IMPROVEMENT
champion 유지
```

### G. 승인 분리 위반

creator와 final approver가 동일하고 정책이 separation 요구.

기대:

```text
APPROVAL_SEPARATION_VIOLATION
```

### H. Canary 실패

```text
runtime failure rate > threshold
```

기대:

```text
CANARY_HEALTH_FAILED
ACTIVE 승격 금지
```

### I. Critical incident 자동 rollback

ACTIVE v3에서 critical schema failure.

기대:

```text
v3 binding 종료
v2 신규 binding 생성
v2 artifact 수정 없음
```

### J. invalid rollback target

rollback target이 RETIRED.

기대:

```text
ROLLBACK_TARGET_INVALID
fallback governance policy 실행
```

### K. Kill switch

```text
GLOBAL_NEW_ENTRY_KILL enabled
```

기대:

```text
신규 BUY 차단
SELL/REDUCE 허용
```

### L. Historical active resolution

```text
v1 active Jan-Mar
v2 active Apr-Jun
v3 active Jul-
```

5월 백테스트.

기대:

```text
v2 반환
현재 v3 사용 금지
```

### M. 동일 content 중복 등록

동일 hash artifact 재등록.

기대:

```text
중복 artifact version 생성 금지 또는 deterministic dedup
```

### N. dependency 미승인

부모 feature schema가 DRAFT.

기대:

```text
DEPENDENCY_NOT_APPROVED
```

### O. Audit chain 변조

과거 audit event 하나를 변경.

기대:

```text
AUDIT_CHAIN_MISMATCH
```

### P. 동일 입력 재실행

```text
same artifact
same validation snapshot
same policy
same champion
```

기대:

```text
동일 gate result
동일 promotion result
동일 evidence hash
```

---

## 31. 통합 테스트

### 31.1 47 → 48 → 34/46

```text
47 challenger parameter 생성
→ 48 validation
→ approval
→ ACTIVE binding
→ 34/46이 새 parameter resolve
```

검증:

```text
activation 이전 실행은 champion
activation 이후 실행은 challenger
과거 snapshot 결과 불변
```

### 31.2 42 Signal 정책 승격

```text
Signal Integration policy v6 challenger
→ backtest 개선
→ robustness 통과
→ PAPER ACTIVE
```

LIVE 환경에는 자동 적용되지 않아야 한다.

### 31.3 rollback 후 재현성

```text
v3 activation
→ incident
→ v2 rollback
```

각 시점의 decision replay가 당시 ACTIVE artifact와 정확히 일치해야 한다.

---

## 32. 핵심 불변식

```text
승인 없는 LIVE ACTIVE = 0

DRAFT artifact의 runtime 사용 = 0
REJECTED artifact의 runtime 사용 = 0
QUARANTINED artifact의 runtime 사용 = 0

미래 artifact의 과거 사용 = 0
현재 ACTIVE artifact의 과거 소급 = 0

future-information violation artifact 승격 = 0
non-deterministic artifact 승격 = 0
critical gate 실패 artifact 승격 = 0

RETIRED artifact로 rollback = 0
QUARANTINED artifact로 rollback = 0

ACTIVE binding 동일 scope 중복 = 0

과거 artifact content 수정 = 0
과거 audit event 수정 = 0
과거 deployment event 수정 = 0

kill switch 상태에서 신규 위험 확대 = 0

PAPER ACTIVE가 LIVE로 자동 승격 = 0

동일 artifact + 동일 validation snapshot + 동일 policy
→ 동일 validation result
→ 동일 promotion recommendation
→ 동일 hash
```

---

## 33. Failure Policy

48번 자체가 실패하는 경우 가장 보수적으로 처리한다.

```text
Governance DB unavailable
→ 현재 검증된 ACTIVE artifact 유지
→ 신규 activation 금지

ACTIVE binding resolve 실패
→ 해당 engine 신규 위험확대 차단

Audit write 실패
→ governance state change commit 금지

Rollback target resolve 실패
→ kill switch 활성화 가능
→ 자동 임의 버전 선택 금지
```

즉 governance 장애가 신규 모델 활성화로 이어질 수 없다.

---

## 34. Explainability 출력

각 promotion/rollback은 최소 다음 설명을 제공한다.

```text
Artifact
Previous Champion
Candidate Version
Validation Period
Performance Delta
Risk Delta
Worst Cohort
Gate Results
Approval Results
Deployment Stage
Rollback Target
Final Decision
Reason Codes
Evidence Hash
```

예:

```text
Candidate: execution_slippage_v4
Champion: execution_slippage_v3

MAE: -8.2%
P95 error: -4.1%
RISK_OFF MAE: -6.0%
Runtime latency: +1.2ms

Integrity: PASS
Reproducibility: PASS
Performance: PASS
Risk: PASS
Robustness: PASS
Operational: PASS

Decision: APPROVED_FOR_SHADOW
```

---

## 35. 구현 순서

```text
1. enums / immutable models
2. artifact registry
3. DB migration
4. identity / hash
5. lineage graph
6. state machine
7. active binding resolver
8. validation contracts
9. promotion gates
10. approvals
11. shadow/canary deployment
12. rollback controller
13. kill switch
14. audit hash chain
15. manifests
16. replay / historical resolver
17. integration tests
```

---

## 36. ADE 전체에서의 위치

```text
38 Fundamental
39 Valuation / Factor
40 Expectations
41 Market Behavior
42 Signal Integration
43 Regime Adaptation
44 Portfolio Construction
45 Trade Lifecycle
34 Transaction Cost
46 Execution Simulation
47 Calibration
        ↓
48 Model Governance
        ↓
Approved ACTIVE versions
        ↓
전체 ADE Runtime
```

48번을 통해 ADE는 단순히 모델을 계속 개선하는 시스템을 넘어,

```text
누가 만들었는가
무엇으로 검증했는가
왜 승격했는가
어디에 적용됐는가
언제부터 활성화됐는가
문제 발생 시 어디로 돌아가는가
```

를 전부 재현할 수 있는 통제 구조를 갖는다.

---

## 37. v1 완료 기준

다음 조건을 모두 만족하면 v1 설계를 구현 완료로 본다.

```text
Artifact Registry 동작
Immutable Version 저장
Dependency Graph 검증
Promotion Gate 실행
Approval Policy 실행
Shadow/Canary 상태전이
ACTIVE binding 시점관리
Deterministic Rollback
Kill Switch
Audit Hash Chain
Historical Artifact Resolution
동일 입력 재현성 테스트 통과
```

48번 완료 후 다음 단계는 49번 **Decision Outcome Attribution & Learning Feedback Engine**이 적절하다. 이는 실제 PAPER/LIVE_SHADOW 결과를 Signal, Regime, Portfolio Construction, Lifecycle, Execution 각 단계별로 분해하여 어떤 엔진이 수익과 손실에 기여했는지 attribution하고, 그 결과를 다음 모델 개선의 학습 피드백으로 연결하는 계층이다.
