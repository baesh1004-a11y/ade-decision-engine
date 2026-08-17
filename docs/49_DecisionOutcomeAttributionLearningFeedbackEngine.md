# 49. Decision Outcome Attribution & Learning Feedback Engine v1

## 1. 목적

Decision Outcome Attribution & Learning Feedback Engine은 ADE에서 발생한 **실제 PAPER/LIVE_SHADOW 결과를 의사결정 파이프라인의 각 단계로 분해하여 귀속(attribution)하고, 검증 가능한 학습 피드백으로 변환하는 계층**이다.

이 엔진의 핵심 질문은 다음과 같다.

```text
수익 또는 손실이 발생했다.

그 결과는
- 종목 Signal이 좋아서였는가?
- 시장 Regime 판단이 맞아서였는가?
- 자본배분이 적절해서였는가?
- 보유/청산 Lifecycle 판단이 좋았는가?
- Execution이 잘됐는가?
- 단순히 시장 전체가 움직였기 때문인가?
- 운이었는가, 반복 가능한 edge였는가?
```

본 엔진은 과거 결과를 보고 기존 Signal을 소급 수정하지 않는다. 결과를 **immutable attribution snapshot**으로 기록하고, 이후 모델 개선을 위한 evidence를 제공한다.

---

## 2. 책임 경계

### 수행 책임

- realized portfolio outcome 수집
- benchmark-relative return 계산
- decision chain lineage 복원
- Signal contribution attribution
- Regime contribution attribution
- Portfolio construction contribution attribution
- Lifecycle contribution attribution
- Execution contribution attribution
- cash / benchmark / residual contribution 분리
- counterfactual baseline 비교
- horizon별 성과 측정
- calibration / hit-rate / payoff 분석
- false positive / false negative 분류
- missed opportunity 분석
- no-action outcome 분석
- engine-level scorecard 생성
- learning feedback candidate 생성
- reproducibility manifest 생성
- downstream governance evidence 제공

### 수행하지 않는 책임

- 새로운 매매 Signal 생성
- 모델 weight 자동 변경
- production policy 자동 수정
- 모델 자동 승격
- live 주문 생성
- 실제 회계 원장 수정
- 과거 decision snapshot 수정

---

## 3. 상위 아키텍처

```text
38 Fundamental
39 Factor
40 Expectations
41 Market Behavior
        ↓
42 Signal Integration
        ↓
43 Regime Adaptation
        ↓
44 Portfolio Construction
        ↓
45 Trade Lifecycle
        ↓
23 Decision / Position Sizing
        ↓
34 Transaction Cost
46 Execution Simulation
        ↓
31 Paper Trading / LIVE_SHADOW
19 Portfolio Accounting
25 Reconciliation
        ↓
┌──────────────────────────────────────┐
│ 49 Outcome Attribution & Feedback    │
├──────────────────────────────────────┤
│ Outcome Resolver                     │
│ Decision Lineage Builder             │
│ Benchmark Attribution                │
│ Signal Attribution                   │
│ Regime Attribution                   │
│ Allocation Attribution               │
│ Lifecycle Attribution                │
│ Execution Attribution                │
│ Counterfactual Engine                │
│ Missed Opportunity Analyzer          │
│ NO_ACTION Analyzer                   │
│ Engine Scorecards                    │
│ Feedback Candidate Builder           │
└──────────────────────────────────────┘
        ↓
Learning Evidence
        ↓
47 Calibration
48 Governance
Future Signal / Risk / Portfolio model research
```

49번은 **learning plane**이며, runtime decision path와 분리한다.

---

## 4. 핵심 원칙

### 4.1 Outcome은 미래에 확정된다

Decision 시점에는 outcome을 알 수 없다.

```text
decision_time < outcome_observation_time
```

따라서 미래 outcome은 과거 decision 생성에 절대 들어갈 수 없다.

### 4.2 Attribution과 optimization을 분리한다

```text
Attribution
= 무엇이 결과에 기여했는가?

Optimization
= 다음에는 무엇을 바꿀 것인가?
```

49번은 attribution까지만 수행한다.

### 4.3 결과가 좋았다고 의사결정이 항상 좋은 것은 아니다

예:

```text
잘못된 Signal
+ 시장 전체 급등
→ 결과는 수익

그러나 decision quality는 낮을 수 있음
```

반대도 가능하다.

```text
좋은 risk-controlled decision
+ 예상 불가능한 gap shock
→ 결과는 손실

decision quality는 반드시 낮다고 볼 수 없음
```

따라서 P&L과 decision quality를 분리한다.

### 4.4 NO_ACTION도 의사결정이다

매수하지 않은 날도 결과를 평가한다.

```text
NO_ACTION
→ 시장 급락 회피
→ positive defensive attribution

NO_ACTION
→ 강한 후보가 이후 급등
→ missed opportunity
```

### 4.5 과거 Snapshot은 수정하지 않는다

Signal, Regime, Portfolio, Lifecycle, Execution snapshot을 당시 값 그대로 참조한다.

---

## 5. Attribution 단위

49번은 네 가지 분석 단위를 지원한다.

```text
TRADE
POSITION
DECISION_DAY
PORTFOLIO_PERIOD
```

### TRADE

각 체결별 결과.

### POSITION

진입부터 최종 청산까지 하나의 포지션 생명주기.

### DECISION_DAY

특정 평가일의 BUY/HOLD/REDUCE/EXIT/NO_ACTION 판단.

### PORTFOLIO_PERIOD

일간 / 주간 / 월간 / 전략기간 전체 성과.

---

## 6. Outcome Horizon

단일 시점 성과만 보면 왜곡될 수 있으므로 horizon을 고정한다.

초기 v1:

```text
1D
5D
20D
60D
POSITION_CLOSE
```

예:

```text
BUY decision
1D  -2%
5D  +4%
20D +12%
```

단기 noise와 중기 alpha를 구분할 수 있다.

모든 horizon은 trading calendar 기준이다.

---

## 7. Return 정의

### 7.1 Portfolio Return

```text
portfolio_return_t
= NAV_t / NAV_{t-1} - 1
```

### 7.2 Benchmark Return

```text
benchmark_return_t
= BenchmarkClose_t / BenchmarkClose_{t-1} - 1
```

### 7.3 Active Return

```text
active_return_t
= portfolio_return_t - benchmark_return_t
```

기본 benchmark는 당시 portfolio policy에 기록된 benchmark를 사용한다.

현재의 benchmark를 과거 기간에 소급 적용하지 않는다.

---

## 8. Total P&L Decomposition

포트폴리오 결과를 다음으로 분해한다.

```text
Total P&L
=
Market/Beta Contribution
+ Security Selection Contribution
+ Allocation Contribution
+ Regime/Risk Budget Contribution
+ Lifecycle Contribution
+ Execution Contribution
+ Cash Contribution
+ Explicit Cost
+ Residual
```

각 component의 합은 회계 P&L과 tolerance 내에서 일치해야 한다.

```text
abs(
  accounting_pnl
  - sum(attribution_components)
) <= attribution_tolerance
```

불일치 시:

```text
ATTRIBUTION_RECONCILIATION_FAILED
```

---

## 9. Market / Beta Contribution

종목 수익의 시장 성분을 분리한다.

v1 기본:

```text
market_component_i
= beta_i × benchmark_return
```

잔여 초과수익:

```text
security_specific_return_i
= security_return_i - market_component_i
```

beta가 유효하지 않으면 단순 active return 방식으로 backoff한다.

```text
security_specific_return_i
= security_return_i - benchmark_return
```

Reason:

```text
BETA_UNAVAILABLE_BACKOFF
```

---

## 10. Signal Attribution

Signal attribution은 42번의 family contribution을 그대로 참조한다.

```text
Business Quality
Valuation
Expectations
Market Behavior
```

42번이 최종 Alpha를 만들 때 각 family의 signed contribution을 저장해야 한다.

예:

```text
Quality       +18
Valuation     +12
Expectations  +20
Behavior      +25
Conflict      -5
-----------------
Alpha          70
```

이후 실현 active return이 +8%라면 단순히 8%를 18:12:20:25 비율로 나누는 것이 아니다.

49번은 두 레이어로 평가한다.

```text
Ex-Ante Contribution
= 당시 Signal score contribution

Ex-Post Validation
= 이후 outcome이 해당 direction을 지지했는가?
```

예:

```text
Expectations positive
→ 이후 실적 revision / return positive
→ EXPECTATION_SIGNAL_VALIDATED
```

반대:

```text
Behavior positive
→ 이후 20D relative return negative
→ MARKET_BEHAVIOR_FALSE_POSITIVE
```

---

## 11. Signal Direction Validation

feature family별 direction을 검증한다.

초기 예:

```text
positive signal
+ future active return > +threshold
→ TRUE_POSITIVE

positive signal
+ future active return < -threshold
→ FALSE_POSITIVE

negative signal
+ future active return < -threshold
→ TRUE_NEGATIVE

negative signal
+ future active return > +threshold
→ FALSE_NEGATIVE
```

중립 zone은 별도 처리한다.

```text
abs(future_active_return) < neutral_band
→ INCONCLUSIVE
```

PAPER 초기 neutral band 예:

```text
1D  : 0.5%
5D  : 1.0%
20D : 2.0%
60D : 3.0%
```

정책 Snapshot으로 관리한다.

---

## 12. Confidence Calibration

42번 Confidence가 실제 적중률과 일치하는지 평가한다.

예:

```text
Confidence 80~90
100건 중 방향 적중 84건
→ well calibrated

Confidence 80~90
100건 중 방향 적중 55건
→ overconfident
```

측정:

```text
Expected Accuracy
Observed Accuracy
Calibration Error
Brier Score
Reliability Curve Bucket
```

Reason:

```text
SIGNAL_CONFIDENCE_OVERCONFIDENT
SIGNAL_CONFIDENCE_UNDERCONFIDENT
SIGNAL_CONFIDENCE_WELL_CALIBRATED
```

---

## 13. Regime Attribution

43번 Risk Budget이 실제로 도움이 되었는지 분석한다.

예:

```text
RISK_OFF
risk_budget = 0.50
시장 -8%

실제 portfolio -3%
full-risk counterfactual -6%

→ +3%p protection attributable to regime de-risking
```

반대:

```text
RECOVERY
risk_budget = 0.50
시장 +10%
full-risk counterfactual +8%
actual +4%

→ -4%p opportunity cost from conservative risk budget
```

중요:

```text
opportunity cost != error
```

당시 정보 기준으로 위험 축소가 합리적이었는지 별도 평가한다.

---

## 14. Regime Counterfactual

기본 counterfactual:

```text
CF_NORMAL_RISK_BUDGET
```

즉 43번 효과를 제거하고 NORMAL risk budget을 적용했을 때의 목표 익스포저를 재구성한다.

단, 반드시 당시 known data만 사용한다.

```text
historical signal snapshot
historical prices
historical portfolio state
historical policy
```

현재 정보를 사용해 과거 포트폴리오를 다시 최적화하지 않는다.

---

## 15. Portfolio Construction Attribution

44번 효과를 평가한다.

주요 attribution:

```text
Single-name cap effect
Sector cap effect
Industry cap effect
Correlation penalty effect
Liquidity cap effect
Cash reserve effect
Turnover constraint effect
New-position daily limit effect
```

예:

```text
Rank 1 반도체 A
Rank 2 자동차 B

산업 cap 때문에 A 대신 B 편입

이후
A +2%
B +9%

→ diversification constraint positive contribution
```

반대로 A가 +20%, B가 +2%였다면 opportunity cost를 기록하되 제약 자체를 자동 해제하지 않는다.

---

## 16. Marginal Allocation Attribution

각 포지션의 실제 비중과 baseline 비중을 비교한다.

```text
allocation_effect_i
= (actual_weight_i - baseline_weight_i)
  × security_active_return_i
```

baseline은 policy에서 고정한다.

v1 옵션:

```text
EQUAL_WEIGHT_ELIGIBLE
SIGNAL_PROPORTIONAL
PRE_CONSTRAINT_RAW_WEIGHT
```

기본은:

```text
PRE_CONSTRAINT_RAW_WEIGHT
```

이다.

---

## 17. Lifecycle Attribution

45번의 HOLD/ADD/REDUCE/EXIT이 성과에 어떻게 기여했는지 분석한다.

### HOLD

```text
HOLD 이후 positive active return
→ HOLD_VALIDATED
```

### ADD

```text
ADD quantity 이후 incremental return
→ ADD_CONTRIBUTION
```

### REDUCE

```text
reduced quantity가 이후 하락
→ LOSS_AVOIDED_BY_REDUCE
```

### EXIT

```text
exit 이후 추가 하락
→ LOSS_AVOIDED_BY_EXIT
```

반대로 exit 이후 급등:

```text
POST_EXIT_OPPORTUNITY_COST
```

---

## 18. Exit Quality

청산가격 이후 horizon return을 분석한다.

예:

```text
EXIT at 100
20D later = 80

loss avoided = +20%
```

반대:

```text
EXIT at 100
20D later = 130

opportunity cost = -30%
```

하지만 이후 결과만 보고 청산을 잘못이라고 확정하지 않는다.

다음과 함께 평가한다.

```text
exit reason
risk state
signal state
regime state
thesis state
```

Hard Risk exit은 outcome이 좋았더라도 governance 목적상 정당할 수 있다.

---

## 19. Execution Attribution

46번 실제 simulated/live-shadow fill과 ideal reference를 비교한다.

```text
execution_effect
= ideal_fill_pnl - realized_fill_pnl
```

또는 bps:

```text
implementation_shortfall_bps
```

주요 분류:

```text
SPREAD_COST
MARKET_IMPACT
SLIPPAGE
DELAY_COST
PARTIAL_FILL_COST
MISSED_FILL_OPPORTUNITY
EXPLICIT_FEE
TAX
```

47번 calibration에 직접 전달 가능하다.

---

## 20. NO_ACTION Attribution

NO_ACTION은 세 종류로 구분한다.

```text
NO_CANDIDATE
RISK_BLOCKED
DATA_BLOCKED
```

각각 별도 평가한다.

### NO_CANDIDATE

후보가 없었고 시장이 하락:

```text
DEFENSIVE_NO_ACTION_VALIDATED
```

후보가 없었지만 시장이 크게 상승:

```text
UNIVERSE_OR_SIGNAL_MISSED_OPPORTUNITY
```

### RISK_BLOCKED

Signal 후보는 있었으나 Risk가 차단.

이후 후보가 급락:

```text
RISK_GATE_VALIDATED
```

이후 후보가 급등:

```text
RISK_GATE_OPPORTUNITY_COST
```

### DATA_BLOCKED

시장 결과와 상관없이 데이터 차단 자체는 정상 안전동작일 수 있다.

```text
DATA_GOVERNANCE_PROTECTED
```

---

## 21. Missed Opportunity Engine

매수하지 않은 종목의 이후 성과를 추적한다.

대상:

```text
WATCH
REJECTED_CONFIDENCE
REJECTED_SIGNAL
REJECTED_REGIME
REJECTED_RISK
REJECTED_CONCENTRATION
NO_ACTION top candidate
```

단 전체 Universe를 hindsight로 탐색해 최고 상승주를 찾는 방식은 금지한다.

오직 당시 실제 평가된 candidate snapshot 안에서만 분석한다.

---

## 22. False Positive / False Negative

### False Positive

```text
ELIGIBLE / BUY
→ 이후 유의미한 negative active return
```

원인 태깅:

```text
SIGNAL_FAILURE
REGIME_FAILURE
EVENT_SHOCK
EXECUTION_FAILURE
THESIS_BREAK
UNEXPLAINED
```

### False Negative

```text
REJECTED / WATCH
→ 이후 유의미한 positive active return
```

원인:

```text
THRESHOLD_TOO_STRICT
CONFIDENCE_GATE_TOO_STRICT
REGIME_TOO_CONSERVATIVE
CONCENTRATION_LIMIT
LIQUIDITY_LIMIT
SIGNAL_UNDERSCORED
```

원인 태깅은 자동 확정이 아니라 evidence score로 저장한다.

---

## 23. Decision Quality Score

P&L과 별도로 decision quality를 계산한다.

초기 구조:

```text
DecisionQuality
=
30% Ex-Ante Rule Compliance
+ 25% Signal Outcome Consistency
+ 15% Risk Discipline
+ 10% Portfolio Constraint Quality
+ 10% Lifecycle Quality
+ 10% Execution Quality
```

각 항목 0~100.

중요:

```text
high P&L + rule violation
→ DecisionQuality 낮을 수 있음

negative P&L + perfect risk discipline
→ DecisionQuality가 반드시 0은 아님
```

---

## 24. Engine Scorecard

엔진별 rolling scorecard를 생성한다.

```text
38 Fundamental
39 Factor
40 Expectations
41 Market Behavior
42 Signal
43 Regime Adaptation
44 Portfolio Construction
45 Lifecycle
46 Execution
```

예시 metric:

```text
hit_rate_20d
mean_active_return
median_active_return
information_coefficient
confidence_calibration_error
false_positive_rate
false_negative_rate
loss_avoidance
opportunity_cost
execution_shortfall
sample_count
```

---

## 25. Information Coefficient

42번 score와 미래 수익의 rank correlation을 측정한다.

```text
IC
= SpearmanRankCorr(
    signal_score_t,
    future_active_return_{t+h}
  )
```

horizon별:

```text
IC_5D
IC_20D
IC_60D
```

현재 Universe나 미래 survivorship-filtered Universe를 사용하지 않는다.

---

## 26. Cohort 분석

전체 평균만 보면 중요한 약점을 숨길 수 있다.

cohort:

```text
market regime
sector
industry
market cap bucket
liquidity bucket
volatility bucket
signal confidence bucket
entry rank bucket
holding period bucket
```

예:

```text
Signal 전체 IC = +0.08
RISK_ON IC = +0.15
RISK_OFF IC = -0.09
```

이면 regime robustness 문제가 존재한다.

---

## 27. Learning Feedback Candidate

49번은 직접 모델을 수정하지 않고 다음 구조의 feedback candidate를 생성한다.

```text
feedback_id
source_engine
metric
cohort
observation_window
sample_count
observed_problem
severity
suggested_research_action
confidence
status
```

예:

```text
source_engine = 40 Expectations
problem = 20D false-positive rate elevated
cohort = small-cap / high-dispersion
sample_count = 214
severity = MEDIUM
suggested_action = review dispersion penalty
```

status:

```text
OBSERVED
RESEARCH_REQUIRED
VALIDATION_REQUIRED
GOVERNANCE_REVIEW
CLOSED
```

자동 weight 변경은 금지한다.

---

## 28. Feedback Promotion Flow

```text
49 detects recurring weakness
        ↓
Research / model change
        ↓
new challenger artifact
        ↓
48 Governance validation
        ↓
SHADOW / CANARY
        ↓
ACTIVE
```

따라서:

```text
49 → ACTIVE
```

직접 경로는 존재하지 않는다.

---

## 29. 데이터베이스

핵심 테이블:

```text
outcome_attribution_policies
outcome_attribution_runs
outcome_observations
outcome_decision_lineage
outcome_return_horizons
outcome_components
outcome_counterfactuals
outcome_signal_validations
outcome_regime_attributions
outcome_allocation_attributions
outcome_lifecycle_attributions
outcome_execution_attributions
outcome_no_action_attributions
outcome_engine_scorecards
learning_feedback_candidates
outcome_reason_events
outcome_manifests
```

---

## 30. outcome_attribution_policies

```sql
CREATE TABLE outcome_attribution_policies (
    policy_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    benchmark_policy TEXT NOT NULL,
    neutral_band_1d REAL NOT NULL,
    neutral_band_5d REAL NOT NULL,
    neutral_band_20d REAL NOT NULL,
    neutral_band_60d REAL NOT NULL,
    attribution_tolerance REAL NOT NULL,
    min_cohort_sample INTEGER NOT NULL,
    policy_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## 31. outcome_attribution_runs

```sql
CREATE TABLE outcome_attribution_runs (
    run_id TEXT PRIMARY KEY,
    evaluation_time TEXT NOT NULL,
    observation_cutoff TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT,
    created_at TEXT NOT NULL,
    finalized_at TEXT
);
```

---

## 32. outcome_observations

```sql
CREATE TABLE outcome_observations (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    security_id TEXT,
    decision_time TEXT,
    outcome_time TEXT NOT NULL,
    horizon TEXT NOT NULL,
    gross_return REAL,
    benchmark_return REAL,
    active_return REAL,
    realized_pnl REAL,
    observation_hash TEXT NOT NULL
);
```

---

## 33. outcome_decision_lineage

```sql
CREATE TABLE outcome_decision_lineage (
    lineage_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    fundamental_snapshot_id TEXT,
    factor_snapshot_id TEXT,
    expectation_snapshot_id TEXT,
    market_behavior_snapshot_id TEXT,
    signal_snapshot_id TEXT,
    regime_snapshot_id TEXT,
    portfolio_snapshot_id TEXT,
    lifecycle_snapshot_id TEXT,
    order_id TEXT,
    execution_id TEXT,
    accounting_snapshot_id TEXT,
    lineage_hash TEXT NOT NULL
);
```

---

## 34. outcome_components

```sql
CREATE TABLE outcome_components (
    component_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    component_type TEXT NOT NULL,
    component_value REAL NOT NULL,
    component_unit TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL,
    reason_code TEXT,
    evidence_hash TEXT NOT NULL
);
```

component_type:

```text
MARKET
SECURITY_SELECTION
SIGNAL
REGIME
ALLOCATION
LIFECYCLE
EXECUTION
CASH
EXPLICIT_COST
RESIDUAL
```

---

## 35. outcome_counterfactuals

```sql
CREATE TABLE outcome_counterfactuals (
    counterfactual_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    counterfactual_type TEXT NOT NULL,
    baseline_snapshot_id TEXT,
    hypothetical_return REAL,
    hypothetical_pnl REAL,
    delta_vs_actual REAL,
    method TEXT NOT NULL,
    confidence REAL,
    counterfactual_hash TEXT NOT NULL
);
```

---

## 36. learning_feedback_candidates

```sql
CREATE TABLE learning_feedback_candidates (
    feedback_id TEXT PRIMARY KEY,
    source_engine TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    cohort_key TEXT NOT NULL,
    observation_start TEXT NOT NULL,
    observation_end TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    observed_value REAL,
    reference_value REAL,
    severity TEXT NOT NULL,
    suggested_research_action TEXT,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## 37. Immutable Storage 원칙

Outcome이 새로 확정되면 기존 row를 UPDATE하지 않는다.

```text
1D outcome snapshot
5D outcome snapshot
20D outcome snapshot
60D outcome snapshot
```

각각 별도 observation으로 생성한다.

회계 정정이 발생하면:

```text
new accounting revision
→ new attribution run
```

기존 attribution은 유지한다.

---

## 38. 알고리즘 흐름

```text
1. Observation cutoff 확정
2. Accounting / Reconciliation 데이터 읽기
3. Decision lineage 복원
4. Horizon outcome 생성
5. Benchmark alignment 검증
6. Market vs security-specific return 분해
7. Signal direction validation
8. Regime counterfactual 계산
9. Allocation counterfactual 계산
10. Lifecycle post-action outcome 계산
11. Execution shortfall 계산
12. NO_ACTION / missed opportunity 분석
13. Component reconciliation
14. Engine scorecard 업데이트
15. Learning feedback candidate 생성
16. Manifest / hash 생성
17. FINALIZED
```

---

## 39. 핵심 코드 구조

```text
outcome_attribution/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── accounting.py
│   ├── reconciliation.py
│   ├── signals.py
│   ├── regime.py
│   ├── portfolio.py
│   ├── lifecycle.py
│   ├── execution.py
│   ├── benchmark.py
│   └── market_data.py
│
├── temporal.py
├── lineage.py
├── horizons.py
├── returns.py
├── benchmark.py
├── beta.py
├── decomposition.py
│
├── signal/
│   ├── validation.py
│   ├── confidence.py
│   ├── information_coefficient.py
│   └── confusion_matrix.py
│
├── regime/
│   ├── attribution.py
│   └── counterfactual.py
│
├── allocation/
│   ├── attribution.py
│   ├── baseline.py
│   └── constraints.py
│
├── lifecycle/
│   ├── hold.py
│   ├── add.py
│   ├── reduce.py
│   ├── exit.py
│   └── opportunity_cost.py
│
├── execution/
│   ├── shortfall.py
│   ├── fill_cost.py
│   └── opportunity_cost.py
│
├── no_action.py
├── missed_opportunity.py
├── cohorts.py
├── scorecards.py
├── feedback.py
├── reconciliation.py
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 40. 핵심 모델

```python
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

@dataclass(frozen=True)
class OutcomeObservation:
    observation_id: str
    subject_type: str
    subject_id: str
    decision_time: datetime | None
    outcome_time: datetime
    horizon: str
    gross_return: Decimal | None
    benchmark_return: Decimal | None
    active_return: Decimal | None
    realized_pnl: Decimal | None
    observation_hash: str
```

---

## 41. Attribution Component 모델

```python
@dataclass(frozen=True)
class AttributionComponent:
    observation_id: str
    component_type: str
    value: Decimal
    unit: str
    method: str
    confidence: Decimal | None
    reason_code: str | None
    evidence_hash: str
```

---

## 42. 엔진 의사코드

```python
def run_outcome_attribution(ctx):
    policy = ctx.policy_resolver.resolve(ctx.observation_cutoff)

    accounting = ctx.accounting.load_as_of(ctx.observation_cutoff)
    decisions = ctx.decisions.load_eligible(ctx.observation_cutoff)

    observations = build_horizon_observations(
        decisions=decisions,
        accounting=accounting,
        market_data=ctx.market_data,
        calendar=ctx.calendar,
        cutoff=ctx.observation_cutoff,
    )

    results = []

    for observation in observations:
        lineage = build_decision_lineage(observation, ctx)
        validate_no_future_information(lineage, observation)

        benchmark = resolve_historical_benchmark(lineage, ctx)
        return_components = decompose_market_and_security(
            observation, benchmark, ctx
        )

        signal_result = attribute_signal(observation, lineage, ctx)
        regime_result = attribute_regime(observation, lineage, ctx)
        allocation_result = attribute_allocation(observation, lineage, ctx)
        lifecycle_result = attribute_lifecycle(observation, lineage, ctx)
        execution_result = attribute_execution(observation, lineage, ctx)

        components = reconcile_components(
            observation,
            return_components,
            signal_result,
            regime_result,
            allocation_result,
            lifecycle_result,
            execution_result,
            tolerance=policy.attribution_tolerance,
        )

        results.append(
            finalize_observation_snapshot(
                observation,
                lineage,
                components,
            )
        )

    scorecards = build_engine_scorecards(results, policy)
    feedback = build_learning_feedback_candidates(scorecards, policy)

    return finalize_run(results, scorecards, feedback)
```

---

## 43. Counterfactual 안전 규칙

Counterfactual은 매우 강력하지만 hindsight bias 위험이 크다.

금지:

```text
현재 알려진 재무정보로 과거 후보 재평가
현재 Universe로 과거 ranking 재구성
미래 수익이 높은 종목만 baseline에 포함
현재 정책을 과거에 소급 적용
실제 이후 가격을 이용해 당시 최적 weight 탐색
```

허용:

```text
당시 동일 후보
당시 동일 입력
당시 동일 policy
일부 한 개 decision component만 제거/교체
```

예:

```text
actual = RISK_OFF budget 50%
counterfactual = 동일 당시 정보 + NORMAL budget 100%
```

---

## 44. 주요 Reason Code

```text
OUTCOME_NOT_MATURED
BENCHMARK_OUTCOME_MISSING
ACCOUNTING_SNAPSHOT_MISSING
DECISION_LINEAGE_INCOMPLETE

ATTRIBUTION_RECONCILIATION_FAILED
RESIDUAL_ABOVE_TOLERANCE

SIGNAL_TRUE_POSITIVE
SIGNAL_FALSE_POSITIVE
SIGNAL_TRUE_NEGATIVE
SIGNAL_FALSE_NEGATIVE
SIGNAL_OUTCOME_INCONCLUSIVE

SIGNAL_CONFIDENCE_OVERCONFIDENT
SIGNAL_CONFIDENCE_UNDERCONFIDENT

REGIME_DE_RISK_PROTECTED
REGIME_OPPORTUNITY_COST
REGIME_COUNTERFACTUAL_UNAVAILABLE

ALLOCATION_CONSTRAINT_VALUE_ADDED
ALLOCATION_CONSTRAINT_OPPORTUNITY_COST

HOLD_VALIDATED
ADD_VALUE_ADDED
REDUCE_LOSS_AVOIDED
EXIT_LOSS_AVOIDED
POST_EXIT_OPPORTUNITY_COST

EXECUTION_SHORTFALL
PARTIAL_FILL_OPPORTUNITY_COST
MISSED_FILL_OPPORTUNITY

DEFENSIVE_NO_ACTION_VALIDATED
RISK_GATE_VALIDATED
RISK_GATE_OPPORTUNITY_COST
DATA_GOVERNANCE_PROTECTED
UNIVERSE_OR_SIGNAL_MISSED_OPPORTUNITY

INSUFFICIENT_SCORECARD_SAMPLE
LEARNING_FEEDBACK_CREATED
FUTURE_INFORMATION_GUARD
```

---

## 45. 테스트 계획

### A. 정상 BUY 성공

```text
Signal positive
20D active return +8%
→ TRUE_POSITIVE
```

### B. BUY 실패

```text
Signal positive
20D active return -7%
→ FALSE_POSITIVE
```

### C. Confidence 과신

```text
Confidence bucket 80~90
100 samples
accuracy 55%
→ OVERCONFIDENT
```

### D. RISK_OFF 방어 성공

```text
actual risk budget 50%
market -10%
actual portfolio -4%
normal-risk counterfactual -8%
→ +4% protection
```

### E. RISK_OFF opportunity cost

```text
actual +3%
normal-risk CF +7%
→ -4% opportunity cost
```

### F. Sector cap positive

```text
sector cap으로 대체 종목 편입
대체 종목 outperform
→ constraint value added
```

### G. Sector cap opportunity cost

```text
제외 종목 급등
→ opportunity cost 기록
→ cap 자동 해제 금지
```

### H. EXIT 성공

```text
Exit 이후 20D -15%
→ loss avoided
```

### I. EXIT 후 급등

```text
Exit 이후 20D +20%
→ post-exit opportunity cost
```

### J. Hard Risk exit

```text
강제청산 후 종목 +30%
→ opportunity cost는 기록
→ hard-risk compliance 실패로 판정하지 않음
```

### K. NO_ACTION 방어

```text
NO_CANDIDATE
KOSPI -6%
→ DEFENSIVE_NO_ACTION_VALIDATED
```

### L. Risk-blocked missed opportunity

```text
ELIGIBLE candidate
Risk blocked
20D +25%
→ RISK_GATE_OPPORTUNITY_COST
```

### M. DATA_BLOCKED

```text
데이터 미확정
NO_ACTION
시장 +10%
→ DATA_GOVERNANCE_PROTECTED
→ hindsight로 규칙 위반 처리 금지
```

### N. Partial Fill

```text
100주 주문
40주 체결
60주 미체결
이후 +10%
→ 실제 P&L은 40주
→ 60주 opportunity cost 별도
```

### O. 미래정보 유입

```text
20D outcome이 decision snapshot에 포함
→ BLOCKED
```

### P. Counterfactual hindsight

```text
미래 최고상승주를 baseline에 삽입
→ BLOCKED
```

### Q. Reconciliation

```text
Accounting P&L = 100,000
component sum = 99,990
tolerance = 20
→ PASS
```

### R. Reconciliation 실패

```text
Accounting P&L = 100,000
component sum = 95,000
→ FAILED
```

### S. 표본 부족

```text
cohort sample = 12
minimum = 50
→ feedback candidate 생성 금지
```

### T. 동일 입력 재실행

```text
동일 observation cutoff
동일 snapshots
동일 policy
→ 동일 attribution
→ 동일 scorecard
→ 동일 feedback
→ 동일 hash
```

---

## 46. 통합 테스트 Fixture

고정 fixture:

```text
100 securities
252 trading days
4 regimes
20 BUY
15 HOLD
10 REDUCE
10 EXIT
30 WATCH/REJECT
15 NO_ACTION days
partial fills 포함
transaction costs 포함
corporate action 포함
```

검증:

```text
No future leakage
P&L reconciliation
Benchmark consistency
Signal confusion matrix
Confidence calibration
Regime counterfactual
Allocation effect
Lifecycle outcome
Execution shortfall
NO_ACTION attribution
Deterministic hash
```

---

## 47. 성능 테스트

목표:

```text
10,000 decisions
× 5 horizons
= 50,000 observations
```

초기 목표:

```text
single portfolio daily attribution < 5 sec
50k outcome observations < 60 sec
```

DB index:

```text
(outcome_time)
(subject_type, subject_id)
(security_id, horizon)
(decision_time)
(source_engine, cohort_key)
```

---

## 48. 핵심 불변식

```text
미래 outcome이 과거 decision 입력에 포함 = 0

현재 benchmark의 과거 소급 = 0
현재 Universe의 과거 소급 = 0
현재 policy의 과거 소급 = 0

미래 최고수익 종목을 counterfactual에 포함 = 0

P&L attribution 합계와 회계 P&L 불일치 FINALIZED = 0

결과가 좋았다는 이유로 rule violation 정당화 = 0
결과가 나빴다는 이유로 hard-risk discipline 자동 실패 = 0

NO_ACTION outcome 미평가 = 0
DATA_BLOCKED를 hindsight로 투자판단 실패 처리 = 0

최소표본 미달 cohort feedback 생성 = 0

49번이 production weight 직접 변경 = 0
49번이 ACTIVE artifact 직접 승격 = 0

과거 outcome snapshot 수정 = 0
과거 attribution snapshot 수정 = 0

동일 입력 + 동일 policy + 동일 cutoff
→ 동일 attribution
→ 동일 scorecard
→ 동일 feedback
→ 동일 snapshot hash
```

---

## 49. 구현 순서

```text
1 immutable models / enums
2 DB migrations
3 horizon resolver
4 accounting / benchmark alignment
5 decision lineage builder
6 market/security return decomposition
7 signal validation
8 confidence calibration
9 regime counterfactual
10 allocation attribution
11 lifecycle attribution
12 execution attribution
13 NO_ACTION / missed opportunity
14 reconciliation
15 engine scorecards
16 learning feedback candidates
17 manifest / hashing
18 fixed-fixture integration tests
19 performance tests
20 governance integration
```

---

## 50. ADE 전체 연결

```text
38~41
Evidence / Features
        ↓
42
Signal
        ↓
43
Regime Adaptation
        ↓
44
Capital Allocation
        ↓
45
Trade Lifecycle
        ↓
46
Execution
        ↓
19 / 31
Accounting / Paper Outcome
        ↓
49
Outcome Attribution
"왜 벌었고 왜 잃었는가?"
        ↓
47
Execution Calibration Evidence
        ↓
Research / Challenger
        ↓
48
Governance
"바꿔도 되는가?"
        ↓
Approved future version
```

49번을 통해 ADE는 단순히 거래 결과를 기록하는 시스템에서 벗어나 **의사결정의 질을 사후 검증하고, 실패 패턴을 엔진별로 분해하며, 검증 가능한 개선 근거를 축적하는 폐루프 의사결정 시스템**으로 확장된다.

---

## 51. 다음 확장 후보

49번 이후 자연스러운 다음 엔진은 다음 중 하나다.

```text
50. Strategy Research, Experiment & Walk-Forward Validation Engine
```

역할:

- 49번 feedback을 연구 가설로 변환
- champion/challenger 전략 실험
- walk-forward 검증
- multiple testing / data snooping 통제
- out-of-sample robustness
- 48번 Governance에 promotion evidence 전달

즉:

```text
49
무엇이 반복적으로 잘못되는가?
        ↓
50
그 문제를 고치는 변경이 정말 더 나은가?
        ↓
48
실제로 승격해도 되는가?
```
