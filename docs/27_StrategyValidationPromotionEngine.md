# Strategy Validation & Promotion Engine v1

## 1. 목적

Strategy Validation & Promotion Engine은 새로운 Signal, Risk, Decision 정책 또는 모델이 백테스트에서 좋은 성과를 냈다는 이유만으로 PAPER나 LIVE 경로에 즉시 반영되는 것을 방지한다.

이 엔진은 후보 전략을 동일한 검증 절차로 평가하고, 충분한 증거가 확보된 전략만 다음 운영 단계로 승격하며, 성능 저하나 통제 위반이 발생하면 자동 또는 승인 기반으로 강등한다.

핵심 목표는 다음과 같다.

- 전략·정책·모델 변경의 검증 기준 표준화
- 연구 결과와 운영 전략의 명확한 분리
- 과적합, 데이터 누수, 생존자 편향, 비용 누락 탐지
- 동일 데이터·설정에 대한 재현성 검증
- Champion–Challenger 비교
- RESEARCH → BACKTEST_APPROVED → PAPER → SHADOW → LIVE_BLOCKED → LIVE 승격 통제
- 성능 저하, 위험 증가, 데이터 드리프트 발생 시 강등 또는 중단
- 승인자, 검증 결과, 사용 데이터, 코드 버전의 감사 추적

이 엔진은 직접 매수·매도 판단을 생성하지 않는다.

---

## 2. 책임 경계

### 담당

- 후보 전략 등록과 버전 관리
- 검증 계획 생성
- 필수 검증 항목 실행 상태 관리
- 백테스트·워크포워드·스트레스·재현성 결과 집계
- Champion 대비 Challenger 성과 비교
- 통계적 유의성과 실질적 개선폭 평가
- 운영 단계 승격·강등 제안
- 승인 워크플로와 만료 관리
- 운영 중 성능 감시 기준 생성
- Promotion Manifest와 검증 증거 저장

### 담당하지 않음

- 시장 데이터 생성 또는 정정
- Feature, Signal, Risk, Decision 결과 생성
- 주문 생성 또는 브로커 전송
- 백테스트 거래 체결 자체 수행
- 운영 포트폴리오 손익 계산
- 사람이 승인해야 하는 LIVE 승격을 독단적으로 확정

---

## 3. ADE 내 위치

```text
Strategy / Policy / Model Candidate
            ↓
Validation Plan Builder
            ↓
Evidence Collector
   ├─ Data Snapshot & Lineage
   ├─ Backtest Engine
   ├─ Portfolio Accounting & Performance
   ├─ Audit & Compliance
   └─ Configuration & Policy
            ↓
Validation Evaluator
   ├─ Data integrity
   ├─ Reproducibility
   ├─ Bias controls
   ├─ Performance
   ├─ Risk
   ├─ Robustness
   ├─ Cost sensitivity
   └─ Operational safety
            ↓
Champion–Challenger Comparator
            ↓
Promotion Decision
   ├─ REJECTED
   ├─ NEEDS_REWORK
   ├─ BACKTEST_APPROVED
   ├─ PAPER_APPROVED
   ├─ SHADOW_APPROVED
   ├─ LIVE_BLOCKED_APPROVED
   └─ LIVE_APPROVAL_REQUIRED
            ↓
Configuration & Policy Engine
Scheduler / Orchestrator
Audit / Report
```

---

## 4. 전략 생명주기

```text
DRAFT
  ↓
RESEARCH
  ↓
VALIDATING
  ├─→ REJECTED
  ├─→ NEEDS_REWORK
  └─→ BACKTEST_APPROVED
              ↓
          PAPER
              ↓
          SHADOW
              ↓
       LIVE_BLOCKED
              ↓
            LIVE
```

강등 흐름:

```text
LIVE → LIVE_BLOCKED → SHADOW → PAPER → SUSPENDED
```

### 상태 정의

| 상태 | 의미 |
|---|---|
| DRAFT | 미완성 전략 정의 |
| RESEARCH | 연구와 실험 허용, 운영 금지 |
| VALIDATING | 표준 검증 실행 중 |
| REJECTED | 필수 기준 미달 |
| NEEDS_REWORK | 수정 후 재검증 필요 |
| BACKTEST_APPROVED | 백테스트 검증 통과 |
| PAPER | 가상 체결 기반 검증 |
| SHADOW | 실제 시장 입력을 사용하되 주문 미전송 |
| LIVE_BLOCKED | 운영 파이프라인 연결, 실주문 차단 |
| LIVE | 승인된 실운영 |
| SUSPENDED | 신규 실행 중단 |
| RETIRED | 영구 종료 |

완료된 검증 결과는 수정하지 않는다. 전략 변경은 새로운 `strategy_version_id`와 새로운 validation run을 생성한다.

---

## 5. 입력 모델

```python
StrategyCandidate(
    strategy_id="ade_signal_rank_v2",
    strategy_version="2.1.0",
    code_commit="abc1234",
    feature_snapshot_version="feature-v3",
    signal_policy_id="signal-policy-202607",
    risk_policy_id="risk-policy-202607",
    decision_policy_id="decision-policy-202607",
    universe_definition_id="krx-liquid-1000-v4",
    benchmark_id="KOSPI_TR",
    proposed_by="research-team",
)
```

추가 입력:

- 검증 기간과 시장 구간
- 학습·검증·테스트 기간 분리
- 비용·세금·슬리피지 가정
- 데이터 스냅샷 ID
- 코드 의존성 lock hash
- 랜덤 시드
- Champion 전략 버전
- 최소 성과·위험·운영 기준
- 승격 대상 단계

---

## 6. 출력 모델

```python
ValidationDecision(
    validation_id="VAL-20260726-0001",
    strategy_version_id="STV-00042",
    status="BACKTEST_APPROVED",
    target_stage="PAPER",
    overall_score=82.6,
    mandatory_checks_passed=True,
    performance_score=78.0,
    risk_score=88.0,
    robustness_score=81.0,
    operational_score=85.0,
    champion_delta_return=0.021,
    champion_delta_mdd=0.014,
    blocking_reasons=[],
    warnings=["SMALL_SAMPLE_IN_BEAR_REGIME"],
    approval_required=True,
    evidence_manifest_hash="sha256:...",
)
```

---

## 7. 검증 기준

### 7.1 필수 차단 항목

다음 중 하나라도 실패하면 승격할 수 없다.

- 데이터 스냅샷 잠금 실패
- 코드 버전 또는 정책 버전 미확정
- 동일 입력 재실행 결과 불일치
- 미래 데이터 참조 탐지
- 테스트 기간과 학습 기간 혼합
- 거래 비용·세금·슬리피지 미적용
- 실브로커 호출 경로 존재
- Risk hard block 우회 가능
- Order 수량이 Risk/Decision 승인값을 초과할 가능성
- 감사 이벤트 누락
- 치명적 테스트 실패

### 7.2 성과 기준 예시

| 항목 | 기본 기준 |
|---|---:|
| 테스트 구간 총수익률 | 벤치마크 대비 양의 초과수익 |
| Sharpe Ratio | 0.8 이상 |
| Sortino Ratio | 1.0 이상 |
| Maximum Drawdown | 정책 한도 이내 |
| Profit Factor | 1.15 이상 |
| 최소 폐쇄 거래 수 | 30건 이상 |
| 월별 양(+) 수익 비율 | 50% 이상 |
| 거래 비용 2배 스트레스 | 손익 구조 유지 |

기준은 시장·전략 유형별 Policy로 관리하며 코드에 하드코딩하지 않는다.

### 7.3 위험 기준

- 최대 낙폭
- 일간 손실 꼬리 위험
- Expected Shortfall
- 종목·섹터·상관 군집 집중도
- 최대 익스포저
- 현금 하한 위반 횟수
- 유동성 한도 위반 횟수
- 변동성 급등 구간 손실
- 연속 손실 횟수
- 손절·강제청산 작동 여부

### 7.4 강건성 기준

- Walk-forward validation
- 기간 이동 테스트
- 상승·하락·횡보·고변동·유동성 스트레스 국면별 테스트
- 파라미터 인접값 민감도
- 종목 Universe 변경 민감도
- 수수료·세금·슬리피지 민감도
- 주문 체결 지연 민감도
- 결측·지연·정정 데이터 테스트
- Monte Carlo trade-order reshuffling
- Bootstrap confidence interval

---

## 8. Champion–Challenger 비교

Challenger는 절대 성과뿐 아니라 현재 Champion 대비 개선 여부를 평가한다.

```text
Challenger Score
= Performance Improvement
+ Risk Improvement
+ Stability Improvement
+ Operational Simplicity
- Turnover Penalty
- Complexity Penalty
- Evidence Uncertainty
```

기본 비교 원칙:

1. 동일 데이터 스냅샷과 동일 비용 가정을 사용한다.
2. 동일 Universe와 동일 테스트 기간을 사용한다.
3. 수익률 개선만으로 승격하지 않는다.
4. MDD 증가, 회전율 증가, 유동성 악화가 있으면 감점한다.
5. 개선폭이 통계적으로 불확실하면 Champion을 유지한다.
6. Challenger가 복잡하지만 개선폭이 미미하면 승격하지 않는다.

예시:

```python
promotion_gain = (
    excess_return_delta * 0.30
    + sharpe_delta * 0.20
    + drawdown_improvement * 0.20
    + regime_stability_delta * 0.15
    + execution_quality_delta * 0.10
    - turnover_increase * 0.05
)
```

---

## 9. 종합 점수

```python
overall_score = (
    performance_score * 0.30
    + risk_score * 0.25
    + robustness_score * 0.25
    + operational_score * 0.15
    + explainability_score * 0.05
)
```

단, 필수 차단 항목은 종합 점수보다 우선한다.

```python
if mandatory_failure:
    decision = "REJECTED"
elif overall_score < 65:
    decision = "NEEDS_REWORK"
elif target_stage == "PAPER" and overall_score >= 70:
    decision = "PAPER_APPROVAL_REQUIRED"
elif target_stage == "SHADOW" and overall_score >= 75:
    decision = "SHADOW_APPROVAL_REQUIRED"
elif target_stage == "LIVE_BLOCKED" and overall_score >= 80:
    decision = "LIVE_BLOCKED_APPROVAL_REQUIRED"
elif target_stage == "LIVE" and overall_score >= 85:
    decision = "LIVE_APPROVAL_REQUIRED"
```

LIVE 승격은 자동 확정하지 않는다.

---

## 10. 운영 단계별 최소 증거

| 승격 | 최소 요구 증거 |
|---|---|
| RESEARCH → BACKTEST_APPROVED | 재현 가능한 테스트, 편향 통제, 비용 포함 성과 |
| BACKTEST_APPROVED → PAPER | 고정 fixture 통합 테스트, PAPER 체결 시뮬레이션 |
| PAPER → SHADOW | 최소 운영 기간, 주문·체결·회계 대사 안정성 |
| SHADOW → LIVE_BLOCKED | 실시간 데이터 지연·오류·재시작 검증 |
| LIVE_BLOCKED → LIVE | 승인, 브로커 안전검증, 대사·복구·감사·Kill Switch 검증 |

운영 기간과 최소 거래 수는 정책으로 관리한다.

---

## 11. 강등과 중단 기준

### 자동 LIVE_BLOCKED 전환 후보

- 실현 MDD가 승인 한도의 80% 초과
- 최근 성과가 검증 신뢰구간 하단 이탈
- 데이터 드리프트 또는 Feature 분포 급변
- 주문 거부·오류율 급증
- 체결 슬리피지가 검증 가정 초과
- 브로커 대사 불일치 지속
- Risk hard block 우회 탐지
- 감사 이벤트 누락

### 즉시 SUSPENDED 후보

- 중복 실주문
- 승인량 초과 주문
- LIVE_BLOCKED에서 실주문 API 호출
- 내부 체결이 브로커 체결보다 큼
- 원장 불균형
- 데이터 계보 또는 정책 스냅샷 불명
- Kill Switch 작동 실패

강등·중단은 Audit & Compliance Engine에 사건으로 기록한다.

---

## 12. 데이터베이스

### 12.1 `strategy_definitions`

| 컬럼 | 설명 |
|---|---|
| strategy_id | 전략 식별자 |
| name | 전략명 |
| owner | 책임자 |
| strategy_type | RULE/MODEL/HYBRID |
| created_at | 생성 시각 |
| retired_at | 종료 시각 |

### 12.2 `strategy_versions`

| 컬럼 | 설명 |
|---|---|
| strategy_version_id | 버전 PK |
| strategy_id | 전략 FK |
| semantic_version | 버전 문자열 |
| code_commit | Git commit |
| config_snapshot_id | 정책 스냅샷 |
| feature_version | 특징량 버전 |
| universe_definition_id | Universe 버전 |
| status | DRAFT/RESEARCH/... |
| definition_json | 전략 정의 |
| definition_hash | 불변 해시 |
| created_at | 생성 시각 |

### 12.3 `validation_plans`

| 컬럼 | 설명 |
|---|---|
| validation_plan_id | 계획 PK |
| strategy_version_id | 전략 버전 |
| target_stage | 목표 승격 단계 |
| benchmark_id | 비교 벤치마크 |
| champion_version_id | Champion 버전 |
| periods_json | 학습/검증/테스트 기간 |
| thresholds_json | 기준 스냅샷 |
| plan_hash | 계획 해시 |
| created_at | 생성 시각 |

### 12.4 `validation_runs`

| 컬럼 | 설명 |
|---|---|
| validation_id | 실행 PK |
| validation_plan_id | 계획 FK |
| run_id | Orchestrator run ID |
| status | PENDING/RUNNING/COMPLETED/FAILED |
| started_at | 시작 시각 |
| finished_at | 종료 시각 |
| overall_score | 종합 점수 |
| mandatory_passed | 필수 검증 통과 |
| decision | 승격 판단 |
| evidence_manifest_hash | 증거 해시 |

### 12.5 `validation_checks`

| 컬럼 | 설명 |
|---|---|
| check_id | 검사 PK |
| validation_id | 검증 실행 FK |
| check_type | REPRODUCIBILITY/BIAS/PERFORMANCE/... |
| check_name | 검사명 |
| status | PASS/WARN/FAIL/ERROR |
| observed_value | 관측값 |
| threshold_value | 기준값 |
| evidence_ref | 증거 참조 |
| message | 설명 |

### 12.6 `promotion_requests`

| 컬럼 | 설명 |
|---|---|
| promotion_request_id | 요청 PK |
| strategy_version_id | 전략 버전 |
| from_stage | 현재 단계 |
| to_stage | 목표 단계 |
| validation_id | 근거 검증 |
| requested_by | 요청자 |
| status | PENDING/APPROVED/REJECTED/EXPIRED |
| expires_at | 승인 만료 |
| created_at | 생성 시각 |

### 12.7 `promotion_approvals`

| 컬럼 | 설명 |
|---|---|
| approval_id | 승인 PK |
| promotion_request_id | 요청 FK |
| approver | 승인자 |
| role | 승인 역할 |
| decision | APPROVE/REJECT |
| reason | 사유 |
| decided_at | 결정 시각 |

### 12.8 `strategy_stage_history`

| 컬럼 | 설명 |
|---|---|
| history_id | 이력 PK |
| strategy_version_id | 전략 버전 |
| previous_stage | 이전 단계 |
| new_stage | 새 단계 |
| reason_code | 승격·강등 사유 |
| validation_id | 검증 참조 |
| changed_by | 변경 주체 |
| changed_at | 변경 시각 |

---

## 13. 핵심 알고리즘

```python
def evaluate_strategy(candidate, plan, evidence):
    assert candidate.definition_hash == evidence.strategy_definition_hash
    assert plan.plan_hash == evidence.validation_plan_hash

    mandatory = evaluate_mandatory_checks(candidate, plan, evidence)
    if mandatory.failed:
        return reject(mandatory.reasons)

    performance = score_performance(evidence.backtest_metrics, plan.thresholds)
    risk = score_risk(evidence.risk_metrics, plan.thresholds)
    robustness = score_robustness(evidence.robustness_results, plan.thresholds)
    operational = score_operational(evidence.operational_tests, plan.thresholds)
    explainability = score_explainability(evidence.explanations, plan.thresholds)

    champion_comparison = compare_with_champion(
        challenger=evidence,
        champion=evidence.champion_evidence,
        same_snapshot_required=True,
    )

    overall = weighted_score(
        performance,
        risk,
        robustness,
        operational,
        explainability,
    )

    decision = resolve_promotion_decision(
        target_stage=plan.target_stage,
        overall_score=overall,
        mandatory_passed=True,
        champion_comparison=champion_comparison,
    )

    manifest = build_evidence_manifest(candidate, plan, evidence, decision)
    persist_immutable_result(candidate, plan, decision, manifest)
    return decision
```

---

## 14. 증거 Manifest

Promotion 판단은 다음 정보를 하나의 불변 Manifest로 묶는다.

```text
Strategy definition hash
Code commit
Dependency lock hash
Policy snapshot IDs
Data snapshot IDs
Feature snapshot IDs
Universe snapshot ID
Backtest run IDs
Stress test run IDs
Paper/Shadow run IDs
Cost and slippage assumptions
Random seeds
Validation thresholds
Validation check results
Champion comparison result
Approval records
```

Manifest 해시는 SHA-256으로 계산하고 Audit & Compliance Engine에 기록한다.

---

## 15. 코드 구조

```text
strategy_validation/
├── __init__.py
├── models.py
├── plan.py
├── mandatory.py
├── performance.py
├── risk.py
├── robustness.py
├── operational.py
├── champion.py
├── scoring.py
├── promotion.py
├── degradation.py
├── manifest.py
├── repository.py
└── service.py

tests/
├── test_validation_plan.py
├── test_mandatory_checks.py
├── test_strategy_scoring.py
├── test_champion_comparison.py
├── test_promotion_policy.py
├── test_demotion_policy.py
├── test_evidence_manifest.py
└── test_strategy_validation_integration.py
```

---

## 16. Python 모델 초안

```python
from dataclasses import dataclass, field
from typing import Any, Literal

Stage = Literal[
    "DRAFT", "RESEARCH", "VALIDATING", "BACKTEST_APPROVED",
    "PAPER", "SHADOW", "LIVE_BLOCKED", "LIVE",
    "SUSPENDED", "RETIRED",
]


@dataclass(frozen=True)
class StrategyVersion:
    strategy_version_id: str
    strategy_id: str
    semantic_version: str
    code_commit: str
    definition_hash: str
    current_stage: Stage
    config_snapshot_id: str
    data_contract_version: str


@dataclass(frozen=True)
class ValidationCheckResult:
    check_name: str
    category: str
    status: Literal["PASS", "WARN", "FAIL", "ERROR"]
    observed_value: float | str | None = None
    threshold_value: float | str | None = None
    evidence_ref: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ValidationDecision:
    validation_id: str
    strategy_version_id: str
    target_stage: Stage
    decision: str
    overall_score: float
    mandatory_checks_passed: bool
    checks: tuple[ValidationCheckResult, ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    evidence_manifest_hash: str = ""
```

---

## 17. 테스트 계획

### 17.1 단위 테스트

- 동일 입력으로 동일 종합 점수 생성
- 필수 검사 실패 시 점수와 무관하게 REJECTED
- 비용 미포함 백테스트 차단
- 미래 데이터 참조 탐지 시 차단
- 재현성 불일치 시 차단
- Champion보다 수익률은 높지만 MDD가 크게 악화되면 승격 거절
- 최소 거래 수 미달 시 경고 또는 차단
- LIVE 목표 점수가 기준 미달이면 승인 요청 생성 금지
- 만료된 승인으로 단계 변경 금지
- 전략 정의가 변경되면 기존 validation 재사용 금지

### 17.2 데이터베이스 테스트

- 전략 버전 definition hash 불변성
- validation result 수정 금지
- promotion request와 approval FK 무결성
- 동일 전략 버전의 동시에 충돌하는 stage 변경 차단
- 승인자와 요청자 분리 정책
- 만료된 요청 상태 자동 EXPIRED 전환

### 17.3 통합 테스트

1. 고정 데이터 Snapshot으로 Backtest 실행
2. Performance·Risk·Robustness 결과 수집
3. Champion과 동일 조건 비교
4. ValidationDecision 생성
5. Promotion Request 생성
6. 승인 후 Configuration & Policy Engine에 새 단계 반영
7. Audit 이벤트와 Report 생성 확인

### 17.4 실패 주입 테스트

- Backtest Engine 실패
- 데이터 스냅샷 hash 불일치
- 일부 스트레스 테스트 누락
- Report 저장 실패
- DB 중복 승인 요청
- 승인 직전 정책 버전 변경
- Git commit 조회 불가
- 증거 Manifest 저장 실패

### 17.5 회귀 테스트

- 동일 전략·데이터·정책은 동일 판단 생성
- 거래 비용 증가 시 성과 점수가 증가하지 않음
- 슬리피지 증가 시 총수익률이 증가하지 않음
- MDD 악화 시 Risk 점수가 증가하지 않음
- 증거가 줄어들면 승격 단계가 높아지지 않음

### 17.6 운영 안전 테스트

- RESEARCH 전략의 LIVE 실행 차단
- PAPER 전략의 실브로커 호출 차단
- LIVE_BLOCKED 전략의 submit 호출 0회
- 승인되지 않은 strategy version의 Scheduler dispatch 차단
- SUSPENDED 전략의 신규 RunRequest 생성 차단
- 이전 Champion은 승격 완료 전까지 활성 상태 유지

---

## 18. 완료 기준

Strategy Validation & Promotion Engine v1은 다음 조건을 만족할 때 구현 완료로 간주한다.

1. 전략 버전과 검증 계획을 불변으로 저장한다.
2. 필수 검증과 점수 기반 검증을 분리한다.
3. Backtest 결과와 비용·위험·강건성 증거를 집계한다.
4. Champion–Challenger를 동일 조건으로 비교한다.
5. 승격 요청과 승인 이력을 저장한다.
6. 승인되지 않은 전략의 상위 운영 단계 실행을 차단한다.
7. 성능·위험·운영 이상에 따라 강등 제안을 생성한다.
8. 모든 판단이 Evidence Manifest로 재현 가능하다.
9. LIVE 승격은 자동 확정하지 않는다.
10. Audit & Compliance Engine이 모든 변경을 추적할 수 있다.

---

## 19. 구현 우선순위

1. `StrategyVersion`, `ValidationPlan`, `ValidationCheckResult` 모델
2. 필수 검증 순수 함수
3. 성과·위험·강건성 점수 계산기
4. Champion–Challenger 비교기
5. Evidence Manifest 생성기
6. SQLite repository와 migration
7. BACKTEST_APPROVED 승격 규칙
8. PAPER·SHADOW 단계 확장
9. 성능 저하 기반 강등 제안
10. Configuration/Policy, Orchestrator, Audit 통합

---

## 20. 핵심 운영 원칙

```text
좋은 백테스트 결과는 LIVE 승격의 충분조건이 아니다.

필수 안전 검증 실패는 높은 수익률로 상쇄할 수 없다.

동일 데이터·정책·코드에서 재현되지 않는 전략은 승격하지 않는다.

Champion보다 명확히 우수하다는 증거가 부족하면 기존 전략을 유지한다.

LIVE 승격은 명시적 승인 없이는 불가능하다.

운영 중 통제 위반이나 성능 저하가 발생하면 승격 상태를 유지하지 않는다.
```
