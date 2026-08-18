# 50. Strategy Research, Experiment & Walk-Forward Validation Engine v1

## 1. 목적

Strategy Research, Experiment & Walk-Forward Validation Engine은 49번 Outcome Attribution이 발견한 반복적 약점과 연구 가설을 **재현 가능한 실험으로 등록하고, Point-in-Time 데이터·시간 순서·거래비용·시장상태를 보존한 상태에서 검증하여 Challenger 후보와 검증 evidence를 생성하는 연구 계층**이다.

핵심 질문은 다음과 같다.

```text
49번이 반복되는 문제를 발견했다.

예:
- Expectations가 high-dispersion 종목에서 false positive가 많다.
- RISK_OFF에서 Momentum weight가 과도하다.
- Exit threshold가 너무 민감해 churn이 발생한다.
- Small-cap에서 예상 execution cost가 낮게 잡힌다.

그렇다면 새로운 규칙이 정말 더 나은가?

단순 과거 전체구간 수익률이 아니라
- 미래정보 없이
- 당시 Universe로
- 당시 정책/비용으로
- Train과 Test를 시간적으로 분리하고
- 여러 가설을 시험한 사실까지 반영하며
- Regime별·Tail Risk별로도 견고한가?
```

50번은 연구 결과를 직접 ACTIVE 정책으로 바꾸지 않는다. 검증을 통과한 결과는 **CHALLENGER_CANDIDATE**로 48번 Governance에 전달한다.

---

## 2. 책임 경계

### 수행 책임

- 연구 가설 등록 및 versioning
- experiment preregistration
- baseline / challenger 정의
- PIT dataset manifest 고정
- train / validation / test 시간 분리
- rolling / expanding walk-forward 실행
- embargo / purge 적용
- 거래비용 및 execution simulation 반영
- benchmark-relative 성과 측정
- risk-adjusted metric 측정
- regime / liquidity / sector cohort 검증
- robustness / sensitivity test
- parameter stability 분석
- multiple-testing 기록 및 보정
- bootstrap confidence interval
- overfitting warning 생성
- baseline vs challenger 비교
- reproducibility hash 생성
- research evidence package 생성
- 48 Governance용 challenger candidate 생성

### 수행하지 않는 책임

- LIVE 정책 직접 변경
- Signal weight 자동 배포
- PAPER/LIVE 주문 생성
- 미래 데이터를 이용한 parameter 선택
- 결과가 좋은 구간만 선택
- 실패한 실험 기록 삭제
- 48번 승인 절차 우회

---

## 3. 상위 아키텍처

```text
49 Outcome Attribution
        ↓
Learning Feedback Candidate
        ↓
Research Hypothesis
        ↓
┌──────────────────────────────────────────┐
│ 50 Strategy Research & Validation        │
├──────────────────────────────────────────┤
│ Hypothesis Registry                      │
│ Experiment Preregistration               │
│ PIT Dataset Resolver                     │
│ Baseline / Challenger Builder            │
│ Temporal Splitter                        │
│ Purge / Embargo Guard                    │
│ Walk-Forward Runner                      │
│ Backtest / Paper Replay Adapter          │
│ Cost / Execution Integration             │
│ Metrics & Attribution                    │
│ Robustness / Sensitivity                 │
│ Multiple-Testing Control                 │
│ Overfitting Diagnostics                  │
│ Champion-Challenger Comparator           │
│ Research Evidence Packager               │
└──────────────────────────────────────────┘
        ↓
CHALLENGER_CANDIDATE
        ↓
48 Model Governance
        ↓
SHADOW / CANARY / ACTIVE
```

50번은 **research plane**에만 존재한다.

---

## 4. 핵심 원칙

### 4.1 가설을 결과보다 먼저 고정한다

실험을 실행하기 전에 다음을 저장한다.

```text
hypothesis
primary_metric
secondary_metrics
risk_metrics
baseline_artifact
challenger_change
train_period
validation_period
test_period
walk_forward_scheme
parameter_search_space
multiple_testing_family
acceptance_criteria
rejection_criteria
```

실행 후 기준을 바꾸면 새로운 experiment version으로 기록한다.

Reason Code:

```text
EXPERIMENT_NOT_PREREGISTERED
POST_HOC_CRITERIA_CHANGE
```

### 4.2 Test 구간은 최종 판정 전까지 parameter 선택에 사용하지 않는다

```text
TRAIN
→ parameter fit / candidate generation

VALIDATION
→ candidate selection / tuning

TEST
→ final untouched evaluation
```

Test 결과를 본 뒤 parameter를 수정하면 기존 Test는 더 이상 진정한 OOS가 아니다.

```text
TEST_TOUCHED_BY_TUNING
→ 새로운 미래 Test window 필요
```

### 4.3 시간 순서를 보존한다

기본 split은 random split이 아니다.

```text
과거 ----------------------------→ 미래

TRAIN | VALIDATION | TEST
```

시계열 전략 연구에서 random shuffle은 금지한다.

### 4.4 PIT 원칙을 연구환경에서도 동일하게 적용한다

각 evaluation time `t`에서 사용할 수 있는 정보는:

```text
known_at <= t
observed_at <= t
policy.valid_from <= t
universe.valid_from <= t
```

조건을 만족해야 한다.

현재 재무제표, 현재 Universe, 현재 종목분류를 과거 실험에 소급 사용하지 않는다.

### 4.5 거래비용 없는 Alpha는 승인 evidence가 아니다

50번의 기본 성과는 net-of-cost 기준이다.

```text
Net Return
= Gross Return
- Explicit Cost
- Slippage
- Impact
```

46번 execution simulation과 34/47번 비용계수를 사용한다.

### 4.6 한 개 지표만 개선되면 충분하지 않다

예:

```text
CAGR +3%p
하지만
Max Drawdown -8%p 악화
Tail loss 악화
Turnover 2배
RISK_OFF 성과 붕괴
```

이면 통과시키지 않는다.

### 4.7 실패한 실험도 보존한다

실패 결과를 삭제하면 research selection bias가 발생한다.

```text
FAILED
REJECTED
INCONCLUSIVE
```

실험도 동일하게 immutable registry에 남긴다.

---

## 5. Experiment 상태 머신

```text
DRAFT
  ↓
PREREGISTERED
  ↓
DATA_READY
  ↓
RUNNING
  ↓
COMPLETED
  ↓
VALIDATED
  ├─ REJECTED
  ├─ INCONCLUSIVE
  └─ CHALLENGER_CANDIDATE
```

오류 상태:

```text
BLOCKED_TEMPORAL_LEAKAGE
BLOCKED_DATA_LINEAGE
BLOCKED_NON_REPRODUCIBLE
BLOCKED_TEST_CONTAMINATION
```

---

## 6. 연구 가설 모델

가설은 최소 다음 형태를 갖는다.

```text
Hypothesis ID
Source Feedback ID
Target Engine
Target Policy / Parameter
Current Behavior
Proposed Change
Expected Mechanism
Primary Metric
Risk Guardrails
Cohorts of Interest
```

예:

```text
HYP-0050-001

source:
49 learning_feedback_candidate

problem:
High dispersion earnings consensus에서
20D false positive가 높음

baseline:
Expectation family score 그대로 사용

challenger:
Dispersion > P80이면
Expectation contribution × 0.7

expected mechanism:
불확실성이 높은 consensus의 과신 감소

primary metric:
20D Information Coefficient

risk guardrail:
Annualized turnover +10% 초과 금지
RISK_OFF MaxDD 악화 금지
```

---

## 7. Experiment Preregistration

실험 실행 전 고정하는 필수값:

```text
experiment_id
hypothesis_id
experiment_version
registered_at
researcher_id

baseline_artifact_id
challenger_spec_hash

universe_policy_id
benchmark_id
cost_model_id
execution_model_id

train_start
train_end
validation_start
validation_end
test_start
test_end

primary_metric
minimum_improvement
risk_guardrails
multiple_test_family_id
```

등록 후 변경은 UPDATE가 아니라 새 version을 만든다.

---

## 8. Dataset Snapshot

실험에 사용한 데이터셋 자체를 manifest로 고정한다.

```text
dataset_snapshot_id
as_of_cutoff
security_universe_hash
market_data_hash
fundamental_hash
factor_hash
expectations_hash
market_behavior_hash
benchmark_hash
corporate_action_hash
calendar_hash
```

동일 experiment를 재실행하면 동일 dataset snapshot을 사용할 수 있어야 한다.

### Dataset 상태

```text
READY
DEGRADED
BLOCKED
```

다음은 BLOCKED다.

```text
FUTURE_INFORMATION_DETECTED
CURRENT_UNIVERSE_BACKFILLED
CORPORATE_ACTION_LOOKAHEAD
BENCHMARK_CONSTITUENT_LOOKAHEAD
DATASET_HASH_MISMATCH
```

---

## 9. Temporal Split

### 9.1 Static Holdout

초기 단순 검증:

```text
Train      2019-01 ~ 2023-12
Validation 2024-01 ~ 2024-12
Test       2025-01 ~ 2026-06
```

### 9.2 Expanding Walk-Forward

```text
Fold 1
Train 2019-2021
Test  2022

Fold 2
Train 2019-2022
Test  2023

Fold 3
Train 2019-2023
Test  2024
```

과거 데이터가 누적되는 모델에 적합하다.

### 9.3 Rolling Walk-Forward

```text
Fold 1
Train 2019-2021
Test  2022

Fold 2
Train 2020-2022
Test  2023

Fold 3
Train 2021-2023
Test  2024
```

시장 구조 변화에 더 민감하다.

v1은 두 방식을 모두 지원하되 기본 연구정책은 **expanding + rolling 교차검증**으로 한다.

---

## 10. Purging과 Embargo

Label horizon이 20D인데 Train 종료 직전 observation의 outcome이 Validation 기간에 걸쳐 있으면 leakage가 생길 수 있다.

따라서 split 경계에서 label horizon만큼 purge한다.

```text
TRAIN observation
whose label_end_time >= validation_start
→ PURGED
```

Embargo도 둔다.

```text
Train End
→ embargo N trading days
→ Validation Start
```

Reason Code:

```text
PURGE_APPLIED
EMBARGO_APPLIED
LABEL_OVERLAP_BLOCKED
```

---

## 11. Baseline과 Challenger

한 실험에서는 가능한 한 변경요소를 최소화한다.

```text
Baseline
= 현재 승인된 artifact

Challenger
= 한정된 정책/알고리즘 변경
```

예:

```text
Baseline:
Expectation weight = 20%

Challenger:
Expectation weight = 15%
Market Behavior = 35%
```

다른 조건은 동일하게 유지한다.

```text
Universe
Data
Cost model
Execution policy
Benchmark
Rebalance policy
```

이렇게 해야 성과 차이를 변경요소에 귀속할 수 있다.

---

## 12. Parameter Search

Parameter search space도 preregistration한다.

예:

```text
expectation_dispersion_penalty
∈ {0.5, 0.6, 0.7, 0.8, 0.9}
```

무제한 연속 탐색은 초기 v1에서 금지한다.

```text
PARAMETER_SEARCH_SPACE_NOT_REGISTERED
SEARCH_SPACE_EXPANDED_POST_HOC
```

를 차단한다.

### Parameter 수 제한

초기 원칙:

```text
한 실험에서 동시에 조정하는 핵심 parameter <= 3
```

복잡도가 과도하면:

```text
EXPERIMENT_COMPLEXITY_HIGH
```

로 별도 검토한다.

---

## 13. Walk-Forward 실행 알고리즘

각 fold에서:

```text
1. Fold cutoff 결정
2. cutoff 이전 PIT 데이터만 resolve
3. Train dataset 생성
4. candidate parameter fit
5. validation 규칙 적용
6. next test window에서 freeze된 parameter 실행
7. 비용/체결 반영
8. metric 저장
9. fold 종료 후 다음 fold로 이동
```

중요:

```text
Fold N test 결과
→ Fold N parameter 변경 금지
```

다음 fold의 Train에 과거가 된 이후에는 사용할 수 있다.

---

## 14. 핵심 성과 Metric

### Return

```text
CAGR
Annualized Return
Total Return
Active Return
Excess Return
```

### Risk

```text
Annualized Volatility
Max Drawdown
Downside Deviation
VaR
CVaR / Expected Shortfall
Worst 1D / 5D / 20D
```

### Risk-adjusted

```text
Sharpe Ratio
Sortino Ratio
Calmar Ratio
Information Ratio
```

### Signal quality

```text
Information Coefficient
Rank IC
Hit Rate
Precision
False Positive Rate
False Negative Rate
Payoff Ratio
```

### Portfolio quality

```text
Turnover
Average Cash
Concentration
Sector Concentration
Beta
Tracking Error
```

### Execution

```text
Implementation Shortfall
Slippage bps
Fill Ratio
Explicit Cost
Implicit Cost
```

---

## 15. Primary Metric과 Guardrail

모든 실험은 primary metric을 하나 고정한다.

예:

```text
Primary:
20D Rank IC

Guardrails:
MaxDD 악화 <= 2%p
Turnover 증가 <= 15%
P95 loss 악화 금지
RISK_OFF 성과 악화 <= 1%p
```

Primary metric이 개선돼도 guardrail 하나라도 critical fail이면 Challenger로 보내지 않는다.

---

## 16. Bootstrap Confidence Interval

성과 차이가 우연인지 판단하기 위해 block bootstrap을 지원한다.

시계열 autocorrelation을 보존하기 위해 iid bootstrap이 아니라 block 기반을 기본으로 한다.

```text
ΔMetric
= Challenger - Baseline
```

예:

```text
Δ 20D Rank IC = +0.028
95% block bootstrap CI
= [+0.006, +0.049]
```

0을 포함하지 않으면 improvement evidence가 강해진다.

반대로:

```text
CI = [-0.008, +0.051]
```

이면:

```text
INCONCLUSIVE_STATISTICAL_EVIDENCE
```

로 처리할 수 있다.

---

## 17. Multiple-Testing Control

많은 전략을 시험하면 우연히 좋아 보이는 전략이 생긴다.

50번은 모든 실험을 `multiple_test_family_id`에 연결한다.

예:

```text
Expectation dispersion 개선 연구
Family EXP_DISP_2026Q3

실험 12개
```

지원 방법:

```text
Benjamini-Hochberg FDR
Holm correction
Bonferroni (보수적 옵션)
```

v1 기본:

```text
FDR <= 10%
```

연구 목적에 따라 정책으로 변경 가능하다.

### 반드시 기록할 값

```text
raw_p_value
adjusted_p_value
number_of_tests
family_id
correction_method
```

실패를 숨기고 성공한 실험만 family에 넣는 것을 금지한다.

---

## 18. Deflated Sharpe / Selection Bias 경고

여러 전략 중 최고 Sharpe를 선택한 경우 일반 Sharpe만 신뢰하지 않는다.

50번은 다음 진단을 지원한다.

```text
Observed Sharpe
Number of Trials
Return Skewness
Return Kurtosis
Sample Length
```

이를 이용해 selection bias warning을 생성한다.

Reason Code:

```text
SHARPE_SELECTION_BIAS_HIGH
MULTIPLE_TRIAL_OVERFITTING_RISK
```

v1에서는 Deflated Sharpe Ratio를 research metric으로 저장하고 hard gate 여부는 policy로 둔다.

---

## 19. Parameter Stability

좋은 parameter가 한 점에서만 작동하면 과적합 가능성이 높다.

예:

```text
threshold 64 → 평범
threshold 65 → 매우 우수
threshold 66 → 붕괴
```

이는 불안정하다.

반대로:

```text
63~68 구간 전체가 baseline보다 개선
```

이면 견고성이 높다.

Parameter sensitivity surface를 생성하고 다음을 계산한다.

```text
local_stability_score
performance_gradient
neighbor_success_ratio
```

Reason Code:

```text
PARAMETER_CLIFF_DETECTED
PARAMETER_STABILITY_LOW
```

---

## 20. Cohort Robustness

전체 평균만 보고 통과시키지 않는다.

최소 cohort:

```text
Regime
RISK_ON
NORMAL
RECOVERY
RISK_OFF
CRISIS

Liquidity
LARGE
MID
SMALL
ILLIQUID

Sector
산업별

Market Cap
MEGA
LARGE
MID
SMALL
```

후보가 전체적으로 개선돼도 특정 critical regime에서 붕괴하면 차단한다.

```text
REGIME_ROBUSTNESS_FAILED
LIQUIDITY_COHORT_FAILED
SECTOR_DEPENDENCY_EXCESSIVE
```

---

## 21. Subperiod Stability

기간 전체 성과를 여러 하위기간으로 나눈다.

```text
Yearly
Quarterly
Pre/Post structural break
Bull / Bear / Sideways
High / Low volatility
```

초기 통과 기준 예:

```text
positive excess performance in >= 60% of eligible subperiods
```

단, 단순 승률이 아니라 primary metric과 risk metric을 함께 본다.

---

## 22. Tail Risk 검증

평균이 좋아도 극단 손실이 커지면 통과시키지 않는다.

```text
P95 loss
P99 loss
Expected Shortfall
Worst Drawdown
Worst Gap Event
Worst Regime Episode
```

다음은 hard reject 후보:

```text
TAIL_RISK_DEGRADED
CRISIS_LOSS_DEGRADED
```

---

## 23. Cost Sensitivity

성과가 거래비용 가정에 너무 민감한지 확인한다.

실험별로:

```text
Base Cost
1.25 × Cost
1.50 × Cost
2.00 × Cost
```

stress를 수행한다.

예:

```text
Base net alpha  +6%
1.5x cost       +1%
2.0x cost       -4%
```

이면:

```text
COST_SENSITIVITY_HIGH
```

로 표시한다.

---

## 24. Execution Sensitivity

46번의 체결가정을 더 보수적으로 바꿔도 전략이 유지되는지 평가한다.

```text
fill probability -10%p
slippage +5bps
market impact +25%
next-open gap stress
partial-fill stress
```

체결을 낙관적으로 가정해야만 수익이 나는 전략은 승격하지 않는다.

---

## 25. Universe Robustness

특정 소수 종목이 전체 성과를 만든 것인지 확인한다.

```text
Top 1 contributor 제거
Top 5 contributors 제거
Sector-neutral subset
Large-cap only
Ex-top-decile winners
```

결과가 급격히 붕괴하면:

```text
PERFORMANCE_CONCENTRATED_IN_FEW_NAMES
```

를 기록한다.

---

## 26. Benchmark 비교

기본 Benchmark는 실험 목적에 따라 고정한다.

예:

```text
KOSPI
KODEX 200
Universe Equal Weight
Sector Benchmark
Current Champion
```

가장 중요한 비교는:

```text
Challenger vs Current Champion
```

이다.

시장 상승 덕분에 둘 다 수익이 난 것을 Challenger 개선으로 오해하지 않는다.

---

## 27. Challenger Acceptance Scorecard

최종 판정은 다차원 scorecard로 수행한다.

예시 PAPER 정책:

```text
Primary Metric Improvement    PASS required
OOS Improvement               PASS required
Risk Guardrails               PASS required
Tail Risk                     PASS required
Regime Robustness             PASS required
Cost Robustness               PASS required
Parameter Stability           PASS required
Reproducibility               PASS required
Multiple Testing              PASS required
Operational Compatibility     PASS required
```

모든 critical 항목을 통과해야:

```text
CHALLENGER_CANDIDATE
```

가 된다.

---

## 28. 판정 상태

```text
PASS
FAIL
WARN
INCONCLUSIVE
NOT_APPLICABLE
```

최종:

```text
REJECTED
INCONCLUSIVE
CHALLENGER_CANDIDATE
```

`WARN`이 존재해도 policy가 허용하면 후보가 될 수 있지만 모든 warning을 evidence package에 포함한다.

---

## 29. 데이터베이스

### 29.1 `research_hypotheses`

```text
hypothesis_id PK
source_feedback_id
created_at
target_engine
target_artifact_type
problem_statement
proposed_change
expected_mechanism
status
hypothesis_hash
```

### 29.2 `research_experiments`

```text
experiment_id PK
hypothesis_id
experiment_version
registered_at
baseline_artifact_id
challenger_spec_hash
primary_metric
multiple_test_family_id
status
```

### 29.3 `research_experiment_policies`

```text
policy_id PK
policy_version
walk_forward_type
purge_days
embargo_days
min_folds
min_oos_observations
fdr_threshold
parameter_count_cap
policy_hash
```

### 29.4 `research_dataset_snapshots`

```text
dataset_snapshot_id PK
experiment_id
as_of_cutoff
universe_hash
market_data_hash
fundamental_hash
factor_hash
expectations_hash
behavior_hash
benchmark_hash
corporate_action_hash
calendar_hash
dataset_hash
status
```

### 29.5 `research_temporal_splits`

```text
split_id PK
experiment_id
fold_no
train_start
train_end
validation_start
validation_end
test_start
test_end
purge_days
embargo_days
split_hash
```

### 29.6 `research_parameter_candidates`

```text
candidate_id PK
experiment_id
fold_no
parameter_json
parameter_hash
selected_on
selection_metric
state
```

### 29.7 `research_backtest_runs`

```text
run_id PK
experiment_id
fold_no
candidate_id
baseline_or_challenger
started_at
completed_at
status
input_hash
output_hash
```

### 29.8 `research_run_metrics`

```text
run_id
metric_name
metric_value
sample_count
cohort_type
cohort_value
horizon
PRIMARY KEY (...)
```

### 29.9 `research_statistical_tests`

```text
stat_test_id PK
experiment_id
metric_name
raw_p_value
adjusted_p_value
correction_method
multiple_test_family_id
confidence_interval_low
confidence_interval_high
state
```

### 29.10 `research_robustness_results`

```text
robustness_id PK
experiment_id
test_type
scenario
baseline_value
challenger_value
result_state
reason_code
```

### 29.11 `research_challenger_candidates`

```text
challenger_id PK
experiment_id
target_engine
artifact_spec_hash
comparison_summary_hash
risk_summary_hash
status
created_at
```

### 29.12 `research_reason_events`

```text
reason_event_id PK
experiment_id
run_id
reason_code
severity
evidence_json
created_at
```

### 29.13 `research_manifests`

```text
manifest_id PK
experiment_id
hypothesis_hash
policy_hash
dataset_hash
code_hash
baseline_hash
challenger_hash
result_hash
manifest_hash
```

---

## 30. 주요 인덱스

```text
research_experiments(hypothesis_id, experiment_version)
research_temporal_splits(experiment_id, fold_no)
research_parameter_candidates(experiment_id, fold_no)
research_backtest_runs(experiment_id, fold_no, baseline_or_challenger)
research_run_metrics(run_id, metric_name)
research_statistical_tests(multiple_test_family_id, metric_name)
research_reason_events(experiment_id, reason_code)
research_challenger_candidates(target_engine, status)
```

---

## 31. 코드 구조

```text
strategy_research/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── feedback.py
│   ├── governance.py
│   ├── market_data.py
│   ├── fundamentals.py
│   ├── factors.py
│   ├── expectations.py
│   ├── market_behavior.py
│   ├── signal.py
│   ├── regime.py
│   ├── portfolio.py
│   ├── lifecycle.py
│   ├── cost.py
│   └── execution.py
│
├── hypotheses.py
├── preregistration.py
├── datasets.py
├── point_in_time.py
├── lineage.py
│
├── temporal/
│   ├── splitter.py
│   ├── walk_forward.py
│   ├── purge.py
│   └── embargo.py
│
├── candidates.py
├── parameter_search.py
├── baseline.py
├── challenger.py
├── runner.py
├── replay.py
│
├── metrics/
│   ├── returns.py
│   ├── risk.py
│   ├── signal.py
│   ├── portfolio.py
│   └── execution.py
│
├── statistics/
│   ├── bootstrap.py
│   ├── multiple_testing.py
│   ├── deflated_sharpe.py
│   └── confidence_intervals.py
│
├── robustness/
│   ├── regimes.py
│   ├── cohorts.py
│   ├── subperiods.py
│   ├── parameters.py
│   ├── costs.py
│   ├── execution.py
│   └── universe.py
│
├── scorecard.py
├── acceptance.py
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 32. 핵심 데이터 계약

```python
@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    hypothesis_id: str
    version: int
    baseline_artifact_id: str
    challenger_spec_hash: str
    primary_metric: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    multiple_test_family_id: str
    policy_hash: str


@dataclass(frozen=True)
class FoldResult:
    experiment_id: str
    fold_no: int
    baseline_metrics: dict[str, float]
    challenger_metrics: dict[str, float]
    selected_parameter_hash: str
    dataset_hash: str
    result_hash: str
```

---

## 33. Walk-Forward 의사코드

```python
def run_experiment(spec: ExperimentSpec):
    assert_preregistered(spec)

    dataset = resolve_point_in_time_dataset(spec)
    validate_dataset_lineage(dataset)

    splits = build_walk_forward_splits(spec, dataset.calendar)

    fold_results = []

    for fold in splits:
        train = dataset.slice(fold.train)
        valid = dataset.slice(fold.validation)
        test = dataset.slice(fold.test)

        train = purge_overlapping_labels(train, fold.validation.start)
        valid = apply_embargo(valid, fold)

        candidates = fit_or_generate_candidates(train, spec)

        selected = select_on_validation(
            candidates=candidates,
            validation=valid,
            primary_metric=spec.primary_metric,
        )

        freeze(selected)

        baseline_result = replay_strategy(
            artifact=spec.baseline_artifact_id,
            dataset=test,
        )

        challenger_result = replay_strategy(
            artifact=selected,
            dataset=test,
        )

        fold_results.append(
            compare_fold(
                baseline_result,
                challenger_result,
            )
        )

    stats = aggregate_oos_results(fold_results)
    robustness = run_robustness_suite(spec, fold_results)
    multiple_testing = evaluate_multiple_testing(spec, stats)

    decision = build_acceptance_scorecard(
        stats=stats,
        robustness=robustness,
        multiple_testing=multiple_testing,
    )

    return finalize_research_manifest(spec, decision)
```

---

## 34. Acceptance 알고리즘

```python
def accept_challenger(result, policy):
    if result.temporal_leakage:
        return "REJECTED"

    if not result.reproducible:
        return "REJECTED"

    if result.primary_metric_delta < policy.min_primary_improvement:
        return "REJECTED"

    if result.oos_folds_passed < policy.min_oos_folds:
        return "REJECTED"

    if result.tail_risk_degraded:
        return "REJECTED"

    if result.critical_regime_failed:
        return "REJECTED"

    if result.cost_robustness_failed:
        return "REJECTED"

    if result.parameter_stability_low:
        return "REJECTED"

    if result.adjusted_p_value > policy.fdr_threshold:
        return "INCONCLUSIVE"

    return "CHALLENGER_CANDIDATE"
```

---

## 35. Reason Code

```text
EXPERIMENT_NOT_PREREGISTERED
POST_HOC_CRITERIA_CHANGE
TEST_TOUCHED_BY_TUNING

FUTURE_INFORMATION_DETECTED
CURRENT_UNIVERSE_BACKFILLED
CORPORATE_ACTION_LOOKAHEAD
BENCHMARK_CONSTITUENT_LOOKAHEAD
DATASET_HASH_MISMATCH

PURGE_APPLIED
EMBARGO_APPLIED
LABEL_OVERLAP_BLOCKED

PARAMETER_SEARCH_SPACE_NOT_REGISTERED
SEARCH_SPACE_EXPANDED_POST_HOC
EXPERIMENT_COMPLEXITY_HIGH

PRIMARY_METRIC_NOT_IMPROVED
OOS_IMPROVEMENT_CONFIRMED
OOS_IMPROVEMENT_INSUFFICIENT

INCONCLUSIVE_STATISTICAL_EVIDENCE
MULTIPLE_TESTING_ADJUSTMENT_APPLIED
MULTIPLE_TRIAL_OVERFITTING_RISK
SHARPE_SELECTION_BIAS_HIGH

PARAMETER_CLIFF_DETECTED
PARAMETER_STABILITY_LOW

REGIME_ROBUSTNESS_FAILED
LIQUIDITY_COHORT_FAILED
SECTOR_DEPENDENCY_EXCESSIVE
SUBPERIOD_STABILITY_LOW

TAIL_RISK_DEGRADED
CRISIS_LOSS_DEGRADED

COST_SENSITIVITY_HIGH
EXECUTION_SENSITIVITY_HIGH
PERFORMANCE_CONCENTRATED_IN_FEW_NAMES

REPRODUCIBILITY_FAILED
CHALLENGER_CANDIDATE_CREATED
```

---

## 36. 테스트 계획

### A. 정상 Walk-Forward

```text
3 folds
모든 fold에서 PIT 데이터 정상
Challenger OOS 개선
Risk guardrail 통과
→ CHALLENGER_CANDIDATE
```

### B. 미래 재무정보 유입

```text
2024 evaluation
2025 known_at fundamental 사용
→ FUTURE_INFORMATION_DETECTED
→ experiment BLOCKED
```

### C. 현재 Universe의 과거 사용

```text
2026 Universe를 2022 backtest에 사용
→ CURRENT_UNIVERSE_BACKFILLED
→ BLOCKED
```

### D. Label overlap

```text
20D forward label
Train 마지막 observation label이 Validation까지 침범
→ purge
```

### E. Test tuning

```text
Test 결과 확인 후 threshold 65 → 67 변경
→ TEST_TOUCHED_BY_TUNING
→ 기존 Test 무효
```

### F. Primary 개선 / Tail 악화

```text
CAGR +4%p
MaxDD -7%p 악화
→ TAIL_RISK_DEGRADED
→ REJECTED
```

### G. 전체 개선 / RISK_OFF 붕괴

```text
전체 Sharpe +0.3
RISK_OFF return -8%p 악화
→ REGIME_ROBUSTNESS_FAILED
```

### H. 거래비용 민감

```text
Base cost에서는 +5% alpha
1.5x cost에서 0
2x cost에서 -5%
→ COST_SENSITIVITY_HIGH
```

### I. Parameter cliff

```text
64: IR 0.2
65: IR 1.4
66: IR 0.1
→ PARAMETER_CLIFF_DETECTED
```

### J. Multiple testing

```text
20개 실험 중 raw p < .05 3개
FDR 보정 후 1개만 통과
→ 보정된 1개만 후보 가능
```

### K. 실패 실험 삭제 시도

```text
REJECTED experiment
→ immutable
→ delete/update 차단
```

### L. 동일 입력 재실행

```text
동일 hypothesis
동일 preregistration
동일 dataset snapshot
동일 code
→ 동일 fold 결과
→ 동일 scorecard
→ 동일 manifest hash
```

### M. Cost model 소급

```text
현재 47 calibrated parameter를
2023 experiment 전 기간에 소급 사용
→ 당시 valid_from 위반
→ BLOCKED
```

### N. Challenger 단일변경 원칙

```text
Signal weight + Exit + Cost model을 동시에 변경
→ EXPERIMENT_COMPLEXITY_HIGH
→ manual review
```

### O. 소수 종목 집중

```text
성과의 80%가 상위 3종목에서 발생
상위종목 제거 시 alpha 소멸
→ PERFORMANCE_CONCENTRATED_IN_FEW_NAMES
```

---

## 37. 통합 테스트

### 49 → 50

```text
49 Feedback:
Expectation high-dispersion false positive
        ↓
50 Hypothesis 생성
        ↓
Experiment preregister
        ↓
Walk-forward
```

### 50 → 48

```text
50 scorecard PASS
        ↓
CHALLENGER_CANDIDATE
        ↓
48 Governance validation
        ↓
SHADOW / CANARY / ACTIVE 여부 결정
```

### 47 / 46 연계

```text
각 과거 시점에 유효한
Cost / Execution parameter만 사용
```

### 42 / 43 / 44 / 45 연계

변경하려는 엔진 이외의 artifact는 baseline과 challenger에서 동일해야 한다.

---

## 38. 핵심 불변식

```text
Preregistration 없는 최종 실험 = 0

미래정보 사용 = 0
현재 Universe 과거 소급 = 0
현재 정책 과거 소급 = 0

Train / Validation / Test overlap = 0
label overlap 미처리 = 0

Test 데이터 기반 parameter tuning = 0

등록되지 않은 parameter search = 0

거래비용 없는 final acceptance = 0
execution 없는 final acceptance = 0

critical tail risk 악화 Challenger = 0
critical regime 실패 Challenger = 0

multiple-testing family에서
실패 실험 누락 = 0

실패한 연구결과 삭제 = 0
과거 experiment snapshot 수정 = 0

50번의 ACTIVE 직접 변경 = 0
50번의 Governance 우회 = 0

동일 입력 + policy + dataset + code
→ 동일 fold results
→ 동일 acceptance decision
→ 동일 manifest hash
```

---

## 39. 초기 PAPER 권장 정책

```text
minimum_oos_folds              = 3
minimum_oos_observations       = 250 trading days equivalent
minimum_primary_improvement    = policy-specific
max_parameter_count            = 3
fdr_threshold                  = 0.10
max_turnover_increase          = 15%
max_drawdown_degradation       = 2%p
critical_regime_degradation    = 1%p
cost_stress_multiplier         = [1.0, 1.25, 1.5, 2.0]
execution_slippage_stress      = +5 bps
parameter_neighbor_radius      = policy-specific
```

이 값은 코드 상수가 아니라 versioned experiment policy로 관리한다.

---

## 40. 구현 순서

```text
1 Immutable models / enums
2 DB migration
3 Hypothesis registry
4 Experiment preregistration
5 PIT dataset manifest
6 Temporal split / purge / embargo
7 Baseline replay adapter
8 Challenger parameter runner
9 Walk-forward executor
10 Return / risk / signal metrics
11 Bootstrap confidence interval
12 Multiple-testing control
13 Cohort / regime robustness
14 Cost / execution stress
15 Parameter stability
16 Acceptance scorecard
17 Challenger evidence package
18 48 Governance contract
19 Determinism / hash tests
20 Full integration tests
```

---

## 41. ADE에서의 의미

50번이 추가되면 ADE의 개선 루프는 다음처럼 닫힌다.

```text
실제 판단
    ↓
실제 결과
    ↓
49 Attribution
"어디에서 반복적으로 문제가 생겼는가?"
    ↓
50 Research / Walk-Forward
"바꾸면 정말 OOS에서도 좋아지는가?"
    ↓
48 Governance
"그 개선안을 실제로 써도 되는가?"
    ↓
SHADOW / CANARY / ACTIVE
    ↓
새 결과
    ↓
다시 49
```

핵심 철학은 다음과 같다.

```text
Backtest가 좋아 보이는 전략을 만드는 것이 목표가 아니다.

미래정보 없이,
비용을 포함하고,
다른 시장국면에서도 견디며,
많은 시도 중 우연히 나온 결과를 걸러내고,
재현 가능한 개선만 다음 단계로 보내는 것이 목표다.
```

50번은 ADE를 단순한 자동매매 시스템이 아니라 **실험·검증·통제된 학습을 수행하는 의사결정 연구 플랫폼**으로 확장하는 핵심 research governance 계층이다.
