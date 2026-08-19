# 51. Strategy Ensemble, Diversification & Meta-Allocation Engine v1

## 1. 목적

Strategy Ensemble, Diversification & Meta-Allocation Engine은 48번 Governance를 통과하여 사용 가능한 여러 전략·알파 모델·정책 조합을 동시에 운용할 때, **전략별 위험예산을 배분하고 전략 간 상관관계·중복 보유·공통 팩터 노출·Regime 민감도·성과 열화 상태를 통합해 메타 포트폴리오를 구성하는 계층**이다.

핵심 질문은 다음과 같다.

```text
전략 A도 좋고
전략 B도 좋고
전략 C도 좋다.

그렇다면 세 전략에 각각 1/3씩 자본을 주면 되는가?

아니다.

A와 B가 사실상 같은 종목을 사고
같은 Momentum 요인에 노출되어 있고
RISK_OFF에서 동시에 무너진다면
전략 이름만 다를 뿐 하나의 위험일 수 있다.
```

51번의 목표는 **개별 전략의 성과를 최대화하는 것**이 아니라, 검증된 전략들의 조합에서 다음을 달성하는 것이다.

- 전략간 독립성 확보
- 공통 위험요인 집중 방지
- 전략별 risk contribution 통제
- Regime별 전략 적합성 반영
- drawdown / drift 발생 전략 자동 축소 후보화
- 전략 자본배분의 turnover 억제
- 종목 레벨 Portfolio Construction과의 중복 제약 방지
- 재현 가능한 Meta-Allocation Snapshot 생성

51번은 **전략을 새로 연구하거나 승인하지 않는다.**

```text
50 Research
→ 전략이 실제로 좋은가?

48 Governance
→ 사용해도 되는가?

51 Meta-Allocation
→ 승인된 전략들에 위험예산을 얼마나 줄 것인가?
```

---

## 2. 책임 경계

### 수행 책임

- ACTIVE / PAPER_ACTIVE / SHADOW 허용 전략 집합 조회
- 전략별 성과·위험·상관관계 Snapshot 정렬
- 전략 수익률 시계열 구성
- 전략 간 correlation / covariance 추정
- 전략별 factor / sector / security overlap 측정
- 전략별 Regime sensitivity 측정
- 전략별 recent health 상태 반영
- 전략 risk budget 산정
- diversification penalty 적용
- concentration cap 적용
- meta-allocation target weight 생성
- 전략별 capital sleeve 생성
- 전략간 자본 경합 해소
- cross-strategy duplicate order netting용 의도 출력
- meta-allocation turnover 제어
- 전략 중단 / 복구 상태 반영
- deterministic allocation 및 snapshot hash 생성
- explainability / reason code 생성

### 수행하지 않는 책임

- 새로운 전략 연구
- 전략 parameter 자동 변경
- Governance 승인 우회
- 종목별 최종 비중 직접 결정
- 실제 주문 생성
- 종목 주문 라우팅
- 거래비용 추정
- 전략 성과를 미래정보로 재작성
- 최근 성과만 보고 전략 자동 폐기

---

## 3. ADE 내 위치

```text
49 Outcome Attribution
        ↓
50 Strategy Research
        ↓
48 Governance
        ↓
Approved Strategy Set
        ↓
┌─────────────────────────────────────────┐
│ 51 Strategy Ensemble & Meta Allocation  │
├─────────────────────────────────────────┤
│ Strategy Eligibility                    │
│ Strategy Health                         │
│ Correlation / Covariance                │
│ Security Overlap                        │
│ Factor / Sector Overlap                 │
│ Regime Compatibility                    │
│ Risk Contribution                       │
│ Diversification Penalty                 │
│ Meta Risk Budget                        │
│ Capital Sleeve Allocation               │
│ Turnover / Hysteresis                    │
│ Cross-Strategy Intent Netting           │
└─────────────────────────────────────────┘
        ↓
Strategy Capital Sleeves
        ↓
42 Signal / 43 Regime / 44 Portfolio Construction
        ↓
Aggregated Portfolio Intent
        ↓
45 Lifecycle / 23 Decision / 46 Execution
```

핵심은 51번이 44번을 대체하지 않는다는 점이다.

```text
51
전략 A에 30%
전략 B에 20%
전략 C에 10%
현금 / 미배분 40%

44
각 전략 sleeve 내부에서
어떤 종목을 얼마만큼 보유할지 결정
```

---

## 4. Strategy 정의

51번에서 Strategy는 단순 문자열 이름이 아니라 immutable artifact를 참조한다.

```text
strategy_id
strategy_version
strategy_artifact_id
governance_binding_id
signal_policy_id
regime_policy_id
portfolio_policy_id
lifecycle_policy_id
execution_policy_id
```

예:

```text
STRATEGY_VALUE_QUALITY_V3
STRATEGY_EARNINGS_REVISION_V2
STRATEGY_MOMENTUM_RS_V4
STRATEGY_DEFENSIVE_LOW_VOL_V1
```

같은 전략 이름이라도 version이 다르면 다른 전략으로 본다.

---

## 5. 전략 Eligibility Gate

51번이 전략을 배분 대상으로 사용하기 전에 다음을 검사한다.

```text
Governance state allowed?
ACTIVE / PAPER_ACTIVE / SHADOW_ALLOWED

Artifact valid at evaluation_time?
Dependencies valid?
Required performance history available?
Required risk history available?
Kill switch inactive?
Critical incident unresolved?
```

기본 상태:

```text
ELIGIBLE
WATCH
DEGRADED
SUSPENDED
BLOCKED
```

하드 차단 예:

```text
GOVERNANCE_NOT_ACTIVE
ARTIFACT_QUARANTINED
DEPENDENCY_INVALID
KILL_SWITCH_ACTIVE
CRITICAL_INCIDENT_OPEN
FUTURE_ARTIFACT_REFERENCE
```

---

## 6. 전략 수익률 시계열

전략간 상관관계를 계산하려면 동일한 시간축의 strategy return series가 필요하다.

기본 수익률은 실제 PAPER / LIVE_SHADOW / LIVE 결과를 우선한다.

```text
realized_strategy_return_t
```

실제 운용기간이 부족하면 Governance가 허용한 replay series를 사용할 수 있다.

하지만 다음을 혼합하면 안 된다.

```text
전략 A = live return
전략 B = 미래정보가 포함된 현재 backtest
```

모든 시계열은 동일한 PIT cutoff와 동일한 benchmark convention을 사용해야 한다.

필수 필드:

```text
strategy_id
trading_date
return
active_return
nav
exposure
source_type
known_at
snapshot_hash
```

---

## 7. Correlation / Covariance

기본 상관계수는 최근 60거래일과 120거래일을 모두 계산한다.

```text
corr_60
corr_120
```

일반 Pearson뿐 아니라 극단 구간의 동조성을 보기 위해 downside correlation도 계산한다.

```text
Downside Corr
= Corr(strategy_i, strategy_j | market_return < 0)
```

초기 정책 예:

```text
corr < 0.30      LOW
0.30~0.60        MODERATE
0.60~0.80        HIGH
>= 0.80          VERY_HIGH
```

단 correlation 한 값만으로 전략을 제거하지 않는다.

---

## 8. Shrinkage Covariance

표본이 짧으면 sample covariance는 불안정하다.

v1 기본은 shrinkage covariance를 사용한다.

```text
Σ_shrunk
= (1 - λ) × Σ_sample
+ λ × Σ_target
```

Target은 diagonal 또는 constant-correlation 구조를 사용할 수 있다.

초기 기본:

```text
Ledoit-Wolf style shrinkage
```

정확한 구현은 정책으로 고정한다.

Reason:

```text
COVARIANCE_SHRINKAGE_APPLIED
```

---

## 9. Security Overlap

전략 수익률 상관계수가 낮더라도 실제 보유종목이 겹칠 수 있다.

예:

```text
Strategy A
Samsung 10%
SK Hynix 10%
NAVER 5%

Strategy B
Samsung 10%
SK Hynix 8%
Hyundai 5%
```

Security overlap은 다음처럼 계산한다.

```text
weighted_overlap(A,B)
= Σ min(|w_A,i|, |w_B,i|)
```

예:

```text
Samsung overlap = 10%
SK Hynix overlap = 8%
Total overlap = 18%
```

초기 경고 기준:

```text
weighted_overlap >= 25%
→ SECURITY_OVERLAP_HIGH
```

---

## 10. Directional Overlap

같은 종목을 반대 방향으로 보유하는 경우 일반 overlap과 의미가 다르다.

```text
same_direction_overlap
opposite_direction_overlap
```

현재 ADE PAPER 정책은 long-only를 기본으로 하므로 v1에서는 same-direction overlap이 핵심이다.

향후 long-short 전략을 추가할 경우 net / gross overlap을 분리한다.

---

## 11. Factor Exposure Overlap

전략명이 달라도 같은 factor에 노출될 수 있다.

표준 factor exposure 예:

```text
Market Beta
Size
Value
Quality
Momentum
Low Volatility
Growth
Earnings Revision
Liquidity
Sector Factors
```

각 전략에 대해:

```text
factor_exposure_vector
```

를 만들고 cosine similarity 또는 normalized dot product를 계산한다.

```text
factor_similarity(A,B)
= cosine(exposure_A, exposure_B)
```

초기 정책:

```text
factor_similarity >= 0.85
→ FACTOR_OVERLAP_HIGH
```

---

## 12. Sector Overlap

전략별 sector weight를 비교한다.

```text
sector_overlap(A,B)
= Σ min(sector_weight_A,s, sector_weight_B,s)
```

예:

```text
A 반도체 40%
B 반도체 50%
→ 최소 40% 공통 sector exposure
```

전략 레벨에서 이를 기록하고, 최종 하드 sector cap은 44번 Portfolio Construction이 집행한다.

즉:

```text
51 = penalty / sleeve allocation
44 = final hard portfolio constraint
```

---

## 13. Regime Compatibility

각 전략은 시장국면별로 성과특성이 다르다.

50번 Research와 49번 Attribution으로부터 다음을 받는다.

```text
RISK_ON score
NORMAL score
RECOVERY score
RISK_OFF score
CRISIS score
```

현재 effective regime을 R이라 하면:

```text
regime_compatibility_i
= strategy_regime_score(i,R)
```

단 최근 결과만 사용해 즉시 바꾸지 않는다.

최소 표본과 Governance 승인된 scorecard만 사용한다.

---

## 14. Strategy Health Score

전략이 역사적으로 좋았더라도 현재 drift가 발생할 수 있다.

Health 구성요소:

```text
Recent active return stability
Drawdown state
Signal hit-rate drift
Confidence calibration drift
Execution quality drift
Turnover drift
Risk limit violations
Incident state
```

초기 예:

```text
Health Score
= 25% Performance Stability
+ 20% Drawdown Health
+ 15% Signal Calibration
+ 15% Risk Discipline
+ 10% Execution Health
+ 10% Turnover Health
+ 5% Operational Health
```

출력:

```text
HEALTHY
WATCH
DEGRADED
CRITICAL
```

CRITICAL은 신규 전략위험 할당을 차단할 수 있다.

---

## 15. Drawdown-aware Budget

전략의 최근 drawdown을 배분에 반영한다.

```text
strategy_drawdown
= current_strategy_nav / peak_strategy_nav - 1
```

예시 정책:

```text
DD > -5%      multiplier 1.00
-5~-10%       multiplier 0.85
-10~-15%      multiplier 0.60
<-15%         multiplier 0.30 or SUSPEND REVIEW
```

단 손실이 났다는 이유만으로 전략을 자동 종료하지 않는다.

```text
Drawdown
+ model evidence deterioration
+ calibration deterioration
```

이 함께 발생하면 더 강하게 축소한다.

---

## 16. Base Strategy Score

각 전략의 기본 meta score는 다음 요소를 결합한다.

```text
MetaScore_i
=
Quality_i
× Robustness_i
× RegimeCompatibility_i
× Health_i
× DiversificationBenefit_i
```

또는 정책에 따라 additive normalized score를 사용할 수 있다.

v1 기본은 해석 가능한 additive 방식이다.

```text
BaseScore_i
=
0.25 × OOS_Quality
+ 0.20 × RiskAdjustedQuality
+ 0.20 × RegimeCompatibility
+ 0.15 × Health
+ 0.10 × ExecutionQuality
+ 0.10 × Stability
```

모든 입력은 0~1로 정규화한다.

---

## 17. Diversification Penalty

전략별 penalty는 다음으로 구성한다.

```text
CorrelationPenalty
SecurityOverlapPenalty
FactorOverlapPenalty
SectorOverlapPenalty
TailCorrelationPenalty
```

예:

```text
DiversificationPenalty_i
= weighted average overlap to already allocated strategies
```

Greedy allocation에서 높은 utility 전략부터 배치하고, 추가되는 전략의 marginal diversification benefit를 계산할 수 있다.

---

## 18. Marginal Strategy Utility

51번의 핵심 개념이다.

```text
MSU_i
=
ExpectedStrategyBenefit_i
- IncrementalPortfolioRisk_i
- OverlapCost_i
- TurnoverCost_i
- InstabilityCost_i
```

초기 normalized 구조:

```text
MSU_i
=
+ 30% BaseScore
+ 15% RegimeCompatibility
+ 15% DiversificationBenefit
- 15% IncrementalVolatility
- 10% TailCorrelationPenalty
- 10% OverlapPenalty
- 5% TurnoverPenalty
```

가중치는 policy snapshot이다.

---

## 19. Meta Risk Budget

51번은 총 전략 위험예산을 입력받는다.

```text
meta_risk_budget
```

이는 43번 Regime Adaptation의 상위 위험예산과 정합되어야 한다.

예:

```text
43 RECOVERY
portfolio risk budget = 70%

51
strategy sleeves 합계 <= 70%
```

51번이 43번보다 더 많은 위험을 생성할 수 없다.

불변식:

```text
Σ strategy_target_budget
<= regime_allowed_budget
```

---

## 20. Strategy Weight Cap

한 전략에 모든 자본이 집중되는 것을 막는다.

초기 PAPER 정책 예:

```text
max_strategy_weight = 35%
max_strategy_family_weight = 50%
```

Strategy Family 예:

```text
Momentum family
Value family
Quality family
Revision family
Defensive family
```

동일 family 전략 3개가 있어도 합계 cap을 적용한다.

---

## 21. Minimum Allocation

너무 작은 전략 sleeve는 의미 없는 복잡성과 turnover를 만든다.

```text
minimum_strategy_weight = 5%
```

계산 결과가 2%라면:

```text
BELOW_MINIMUM_STRATEGY_ALLOCATION
→ 미배분 현금 또는 다른 전략에 재분배
```

단 재분배 후 cap을 다시 검증한다.

---

## 22. Risk Parity Option

v1 기본은 constrained score allocation이지만, 연구용 대안으로 equal risk contribution을 지원한다.

전략 i의 risk contribution:

```text
RC_i
= w_i × (Σw)_i / portfolio_volatility
```

목표:

```text
RC_i ≈ target_risk_budget_i
```

그러나 signal quality와 regime compatibility를 무시한 순수 risk parity를 ACTIVE 기본값으로 사용하지 않는다.

---

## 23. Hierarchical Strategy Clustering

전략간 상관관계를 기반으로 cluster를 구성한다.

```text
Strategy Returns
        ↓
Distance = sqrt(0.5 × (1-corr))
        ↓
Hierarchical Clustering
        ↓
Strategy Clusters
```

예:

```text
Cluster A
Momentum
Revision Momentum
High Beta Growth

Cluster B
Value
Quality Value
Dividend Value

Cluster C
Low Vol
Defensive Quality
```

각 cluster에는 최대 위험예산을 설정할 수 있다.

```text
max_cluster_weight = 45%
```

---

## 24. Tail Correlation

평상시 correlation이 낮아도 위기 때 동시에 무너질 수 있다.

따라서 다음을 별도 계산한다.

```text
corr_all
corr_downside
corr_worst_10pct_market_days
corr_risk_off
corr_crisis
```

특히:

```text
corr_all = 0.30
corr_crisis = 0.90
```

이라면 diversification이 과대평가된 것이다.

Reason:

```text
TAIL_CORRELATION_HIGH
```

---

## 25. Correlation Breakdown Detection

상관관계 자체가 급변하는 것도 위험이다.

```text
corr_20 - corr_120
```

예:

```text
120D corr = 0.25
20D corr  = 0.78
```

이면:

```text
CORRELATION_SPIKE
```

를 발생시킨다.

필요하면 전략 sleeve 신규 확대를 제한한다.

---

## 26. Cross-Strategy Duplicate Intent

전략 A와 B가 동시에 삼성전자 BUY를 낼 수 있다.

51번은 전략별 의도를 보존하면서 netting용 aggregate intent를 생성한다.

```text
Strategy A: Samsung +300,000원
Strategy B: Samsung +500,000원
Strategy C: Samsung -200,000원

Gross Intent
+800,000 BUY
-200,000 SELL

Net Intent
+600,000 BUY
```

하지만 원인 추적을 위해 strategy lineage는 삭제하지 않는다.

---

## 27. Netting과 Attribution 분리

실행은 net order 하나로 할 수 있지만 Attribution은 strategy별이어야 한다.

따라서:

```text
aggregate_order_id
strategy_intent_allocation
```

매핑을 유지한다.

체결 600,000원이 발생하면 정책에 따라 전략 A/B/C의 net contribution에 비례 배분한다.

49번 Outcome Attribution이 이를 다시 전략별로 추적할 수 있어야 한다.

---

## 28. Internal Crossing

향후 LIVE 환경에서 전략 A는 SELL, 전략 B는 BUY할 경우 외부 시장 거래 없이 내부적으로 위험을 이전할 수 있다.

v1에서는 실제 internal crossing을 수행하지 않고 다음만 기록한다.

```text
INTERNAL_CROSS_CANDIDATE
```

실제 실행 여부는 Execution / Compliance 정책의 별도 승인 사항이다.

PAPER 환경에서는 deterministic netting만 지원한다.

---

## 29. Allocation Hysteresis

전략 성과가 하루 좋아졌다고 예산을 크게 늘리지 않는다.

```text
effective_weight
= previous_weight
+ bounded_change
```

초기 예:

```text
max_daily_strategy_weight_change = 5%p
```

또한 감소는 증가보다 빠르게 허용할 수 있다.

```text
max_daily_increase = +5%p
max_daily_decrease = -10%p
```

이는 43번의 FAST DE-RISK / SLOW RE-RISK 원칙과 정합된다.

---

## 30. Strategy Cooldown

CRITICAL 상태로 중단된 전략이 다음날 성과가 좋아졌다고 즉시 복귀하지 않는다.

```text
SUSPENDED
→ RECOVERY_REVIEW
→ WATCH
→ ELIGIBLE
```

초기 예:

```text
minimum_recovery_observations = 10 trading days
```

새 Governance artifact가 승인된 경우 별도 override가 가능하다.

---

## 31. Unallocated Capital

모든 전략을 반드시 채울 필요는 없다.

```text
Total Allowed Budget = 70%
Eligible strategy allocation = 45%

Unallocated = 25%
```

은 현금 / reserve로 남길 수 있다.

Reason:

```text
INSUFFICIENT_DIVERSIFIED_STRATEGIES
META_BUDGET_UNALLOCATED
```

억지로 낮은 품질의 전략에 배분하지 않는다.

---

## 32. Meta-Allocation Objective

v1 기본 목적함수는 완전한 expected-return optimization보다 해석 가능한 constrained utility를 사용한다.

```text
maximize
Σ w_i × MSU_i
- λ_risk × PortfolioRisk
- λ_turnover × StrategyTurnover
- λ_overlap × OverlapPenalty
```

제약:

```text
w_i >= 0
Σw_i <= meta_risk_budget
w_i <= strategy_cap
family_weight <= family_cap
cluster_weight <= cluster_cap
turnover <= limit
blocked_strategy weight = 0
```

---

## 33. Deterministic Solver

v1 운영 기본은 deterministic constrained heuristic이다.

순서:

```text
1 Eligible 전략 필터
2 BaseScore 계산
3 Health / Regime multiplier
4 Pairwise overlap matrix 생성
5 Cluster 생성
6 MSU 계산
7 높은 MSU부터 incremental allocation
8 Strategy cap 적용
9 Family / Cluster cap 적용
10 Tail-correlation penalty 적용
11 Regime budget 적용
12 Turnover / change limiter 적용
13 Minimum allocation 제거
14 잔여 budget 재분배
15 최종 constraint validation
16 Snapshot finalize
```

향후 v2 연구:

```text
Quadratic Programming
Hierarchical Risk Parity
Risk Budgeting
Robust Optimization
CVaR Meta Allocation
```

---

## 34. 데이터베이스

### 34.1 `strategy_ensemble_policies`

```text
policy_id
version
valid_from
valid_to

min_history_days
correlation_window_short
correlation_window_long

max_strategy_weight
max_family_weight
max_cluster_weight
minimum_strategy_weight

max_daily_increase
max_daily_decrease
max_meta_turnover

security_overlap_threshold
factor_overlap_threshold
tail_correlation_threshold

policy_hash
created_at
```

### 34.2 `strategy_registry_snapshots`

```text
snapshot_id
evaluation_time
strategy_id
strategy_version
artifact_id
governance_binding_id
family_id
eligibility_state
known_at
evidence_hash
```

### 34.3 `strategy_performance_snapshots`

```text
snapshot_id
strategy_id
evaluation_time
return_1d
return_20d
return_60d
vol_20d
vol_60d
max_drawdown
active_return
information_ratio
turnover
health_score
source_type
snapshot_hash
```

### 34.4 `strategy_correlation_snapshots`

```text
snapshot_id
evaluation_time
strategy_a
strategy_b
corr_20
corr_60
corr_120
downside_corr
risk_off_corr
crisis_corr
sample_count
quality_state
snapshot_hash
```

### 34.5 `strategy_overlap_snapshots`

```text
snapshot_id
evaluation_time
strategy_a
strategy_b
security_overlap
sector_overlap
factor_similarity
beta_overlap
same_direction_overlap
snapshot_hash
```

### 34.6 `strategy_meta_allocation_runs`

```text
run_id
evaluation_time
portfolio_id
policy_id
regime_snapshot_id
strategy_registry_snapshot_id
status
input_hash
output_hash
created_at
finalized_at
```

### 34.7 `strategy_meta_scores`

```text
run_id
strategy_id
base_score
regime_score
health_score
diversification_score
risk_penalty
overlap_penalty
turnover_penalty
marginal_strategy_utility
reason_codes
```

### 34.8 `strategy_target_allocations`

```text
run_id
strategy_id
previous_weight
raw_target_weight
constraint_adjusted_weight
final_target_weight
target_capital
allocation_state
reason_codes
evidence_hash
```

### 34.9 `strategy_cluster_snapshots`

```text
cluster_snapshot_id
run_id
cluster_id
strategy_id
cluster_method
cluster_distance
cluster_weight
snapshot_hash
```

### 34.10 `cross_strategy_intents`

```text
intent_id
run_id
strategy_id
security_id
direction
notional
quantity_intent
source_portfolio_snapshot_id
known_at
```

### 34.11 `aggregate_strategy_intents`

```text
aggregate_intent_id
run_id
security_id
gross_buy_notional
gross_sell_notional
net_notional
net_direction
intent_count
snapshot_hash
```

### 34.12 `strategy_ensemble_reason_events`

```text
reason_event_id
run_id
strategy_id
reason_code
severity
details_json
created_at
```

### 34.13 `strategy_ensemble_manifests`

```text
manifest_id
run_id
policy_hash
strategy_set_hash
performance_hash
correlation_hash
overlap_hash
regime_hash
previous_allocation_hash
output_hash
```

---

## 35. 주요 상태 Enum

```text
StrategyEligibility
ELIGIBLE
WATCH
DEGRADED
SUSPENDED
BLOCKED

StrategyHealth
HEALTHY
WATCH
DEGRADED
CRITICAL

AllocationState
ALLOCATED
CAPPED
REDUCED
UNALLOCATED
SUSPENDED
BLOCKED

CorrelationState
LOW
MODERATE
HIGH
VERY_HIGH
TAIL_HIGH
SPIKING
```

---

## 36. 주요 Reason Code

```text
STRATEGY_ELIGIBLE
STRATEGY_NOT_GOVERNANCE_APPROVED
STRATEGY_KILL_SWITCH_ACTIVE
STRATEGY_CRITICAL_INCIDENT

INSUFFICIENT_STRATEGY_HISTORY
INSUFFICIENT_CORRELATION_SAMPLE
COVARIANCE_SHRINKAGE_APPLIED

STRATEGY_HEALTH_DEGRADED
STRATEGY_HEALTH_CRITICAL
STRATEGY_DRAWDOWN_PENALTY

CORRELATION_HIGH
TAIL_CORRELATION_HIGH
CORRELATION_SPIKE

SECURITY_OVERLAP_HIGH
SECTOR_OVERLAP_HIGH
FACTOR_OVERLAP_HIGH
STRATEGY_FAMILY_CONCENTRATION
STRATEGY_CLUSTER_CONCENTRATION

REGIME_COMPATIBILITY_LOW
REGIME_BUDGET_LIMIT

STRATEGY_WEIGHT_CAP_BINDING
FAMILY_WEIGHT_CAP_BINDING
CLUSTER_WEIGHT_CAP_BINDING

META_TURNOVER_LIMIT_BINDING
STRATEGY_CHANGE_LIMIT_BINDING
BELOW_MINIMUM_STRATEGY_ALLOCATION

INSUFFICIENT_DIVERSIFIED_STRATEGIES
META_BUDGET_UNALLOCATED

DUPLICATE_SECURITY_INTENT
OPPOSING_STRATEGY_INTENT
INTERNAL_CROSS_CANDIDATE

FUTURE_INFORMATION_GUARD
SNAPSHOT_ALIGNMENT_FAILED
INPUT_HASH_MISMATCH
CONSTRAINT_SET_INFEASIBLE
```

---

## 37. 코드 구조

```text
strategy_ensemble/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── registry.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── governance.py
│   ├── strategy_returns.py
│   ├── outcome_attribution.py
│   ├── research.py
│   ├── regime.py
│   ├── portfolio.py
│   └── execution.py
│
├── temporal.py
├── eligibility.py
├── alignment.py
├── health.py
├── drawdown.py
│
├── covariance.py
├── shrinkage.py
├── correlations.py
├── downside_correlation.py
├── tail_correlation.py
├── correlation_drift.py
│
├── overlaps/
│   ├── securities.py
│   ├── sectors.py
│   ├── factors.py
│   └── directional.py
│
├── clustering.py
├── regime_compatibility.py
├── base_score.py
├── diversification.py
├── marginal_utility.py
├── risk_contribution.py
│
├── allocators/
│   ├── constrained_score.py
│   ├── risk_budget.py
│   └── risk_parity.py
│
├── constraints.py
├── caps.py
├── turnover.py
├── hysteresis.py
├── cooldown.py
├── reallocation.py
│
├── intents.py
├── netting.py
├── attribution_map.py
│
├── reason_codes.py
├── explainability.py
├── manifest.py
├── hashing.py
└── validation.py
```

---

## 38. 핵심 데이터 모델 예시

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class StrategyEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class StrategyMetaInput:
    strategy_id: str
    strategy_version: str
    base_score: Decimal
    regime_compatibility: Decimal
    health_score: Decimal
    volatility: Decimal
    drawdown: Decimal
    previous_weight: Decimal
    eligibility: StrategyEligibility


@dataclass(frozen=True)
class StrategyTargetAllocation:
    strategy_id: str
    raw_weight: Decimal
    final_weight: Decimal
    target_capital: Decimal
    allocation_state: str
    evidence_hash: str
```

불변 모델을 우선 사용한다.

---

## 39. Correlation Matrix 계산

```python
def build_correlation_matrix(return_frame, min_samples: int):
    aligned = align_strategy_returns(return_frame)

    if aligned.sample_count < min_samples:
        raise InsufficientCorrelationSample()

    sample_cov = aligned.returns.cov()
    shrunk_cov = shrink_covariance(sample_cov)
    corr = covariance_to_correlation(shrunk_cov)

    return corr
```

중요한 점은 서로 다른 날짜·다른 cutoff의 수익률을 임의 forward-fill하지 않는 것이다.

---

## 40. Security Overlap 계산

```python
def weighted_security_overlap(weights_a, weights_b):
    securities = set(weights_a) | set(weights_b)

    return sum(
        min(abs(weights_a.get(s, 0)), abs(weights_b.get(s, 0)))
        for s in securities
    )
```

PIT portfolio snapshot만 사용한다.

---

## 41. Meta Score 예시

```python
def calculate_base_score(x, policy):
    return (
        policy.oos_quality_weight * x.oos_quality
        + policy.risk_adjusted_weight * x.risk_adjusted_quality
        + policy.regime_weight * x.regime_compatibility
        + policy.health_weight * x.health_score
        + policy.execution_weight * x.execution_quality
        + policy.stability_weight * x.stability_score
    )
```

결측값을 0으로 대체하지 않는다.

필수 항목이 없으면:

```text
INSUFFICIENT_META_INPUT
```

으로 처리한다.

---

## 42. Marginal Utility 예시

```python
def marginal_strategy_utility(strategy, current_meta_portfolio, policy):
    benefit = strategy.base_score
    regime = strategy.regime_compatibility

    incremental_risk = estimate_incremental_risk(
        current_meta_portfolio,
        strategy,
    )

    overlap = estimate_overlap_penalty(
        current_meta_portfolio,
        strategy,
    )

    turnover = estimate_turnover_penalty(
        current_meta_portfolio,
        strategy,
    )

    return (
        policy.base_weight * benefit
        + policy.regime_weight * regime
        + policy.diversification_weight * strategy.diversification_score
        - policy.risk_weight * incremental_risk
        - policy.overlap_weight * overlap
        - policy.turnover_weight * turnover
    )
```

---

## 43. 기본 Allocation 알고리즘

```python
def allocate_strategies(ctx):
    inputs = validate_point_in_time_inputs(ctx)

    eligible = filter_eligible_strategies(
        inputs.strategy_registry,
        inputs.governance,
    )

    health = evaluate_strategy_health(
        eligible,
        inputs.performance,
        inputs.incidents,
    )

    corr = build_correlation_matrix(
        inputs.strategy_returns,
        min_samples=ctx.policy.min_correlation_samples,
    )

    overlaps = build_overlap_matrices(
        inputs.strategy_positions,
        inputs.factor_exposures,
    )

    clusters = cluster_strategies(corr)

    scored = score_strategies(
        eligible,
        health,
        inputs.regime,
        corr,
        overlaps,
    )

    targets = constrained_incremental_allocation(
        scored,
        total_budget=inputs.regime.meta_risk_budget,
        strategy_cap=ctx.policy.max_strategy_weight,
        family_cap=ctx.policy.max_family_weight,
        cluster_cap=ctx.policy.max_cluster_weight,
    )

    targets = apply_change_limits(
        targets,
        inputs.previous_allocations,
        policy=ctx.policy,
    )

    targets = remove_subminimum_allocations(targets, ctx.policy)
    targets = reallocate_residual_budget(targets, scored, ctx.policy)

    validate_final_constraints(targets, ctx)

    intents = build_strategy_intents(targets, inputs)
    aggregate_intents = deterministic_netting(intents)

    return finalize_meta_snapshot(
        targets=targets,
        clusters=clusters,
        aggregate_intents=aggregate_intents,
    )
```

---

## 44. 전략 Allocation 예시

가정:

```text
Regime = RECOVERY
총 허용 위험예산 = 70%
```

전략:

```text
A Momentum
Base 0.85
Health 0.90
Regime 0.95

B Earnings Revision
Base 0.82
Health 0.88
Regime 0.90

C Value Quality
Base 0.78
Health 0.95
Regime 0.75
```

A와 B correlation이 0.88이고 security overlap도 35%라면:

```text
단순 score 배분
A 30%
B 25%
C 15%

↓ overlap penalty

최종 예시
A 25%
B 15%
C 20%
미배분 10%
```

총 위험자산 60%만 사용하고 10%는 억지로 채우지 않을 수 있다.

---

## 45. Strategy Health 급락 예시

전일:

```text
A 30%
B 20%
C 20%
```

오늘 A:

```text
20D hit rate 급락
Drawdown -12%
Execution shortfall 악화
Health = DEGRADED
```

정책 결과:

```text
A target 15%
```

하지만 하루 감소 limit가 -10%p라면:

```text
실제 effective target = 20%
```

단 CRITICAL / hard-risk이면 change limiter를 우회해 더 빠르게 축소할 수 있다.

---

## 46. Hard Risk Override

다음은 일반 hysteresis보다 우선한다.

```text
Kill Switch
Critical Governance Incident
Artifact Quarantine
Future Information Violation
Invalid Dependency
Severe Risk Breach
```

결과:

```text
strategy target weight = 0
```

필요한 actual liquidation 방식은 45/23/46에 전달한다.

51번이 직접 시장가 청산을 가정하지 않는다.

---

## 47. 전략 수 증가 문제

전략을 많이 추가하면 diversification이 무조건 좋아지는 것이 아니다.

다음 metric을 추적한다.

```text
Effective Number of Strategies
= 1 / Σ w_i^2
```

예:

```text
5개 전략이 있어도
한 전략 70%
나머지 7.5%
→ effective N은 낮음
```

Reason:

```text
LOW_EFFECTIVE_STRATEGY_COUNT
```

---

## 48. Concentration Metrics

다음 메타 집중도도 저장한다.

```text
HHI_strategy
HHI_family
HHI_cluster
Top1 strategy weight
Top3 strategy weight
```

과도한 집중은 신규 위험 확대를 제한한다.

---

## 49. Portfolio-level Exposure Reconciliation

51번의 전략 sleeve를 합치면 44번 최종 포트폴리오 하드제약을 넘을 수 있다.

예:

```text
Strategy A 반도체 40%
Strategy B 반도체 30%
```

51번 sleeve 조합 후 전체 반도체 예상비중이 35%라면 44번 sector cap 30%와 충돌한다.

따라서 51번은 사전 예상 aggregate exposure를 계산해:

```text
EXPECTED_PORTFOLIO_CONSTRAINT_CONFLICT
```

를 만들고 allocation penalty를 적용한다.

최종 하드 차단은 44번이 수행한다.

---

## 50. Feedback 연결

51번 결과는 49번에서 별도 Attribution 대상이다.

```text
Strategy Selection Effect
Meta Allocation Effect
Diversification Effect
Overlap Penalty Effect
Unallocated Cash Effect
Netting Effect
```

예:

```text
A 비중 축소 덕분에 손실 회피
→ META_ALLOCATION_PROTECTED

B 비중 과소 때문에 상승 놓침
→ META_ALLOCATION_OPPORTUNITY_COST
```

하지만 49번 결과가 51번 정책을 직접 변경하지 않는다.

```text
49 → 50 Research → 48 Governance → 51
```

경로를 유지한다.

---

## 51. Snapshot / Hash 원칙

모든 결과는 다음 입력을 hash에 포함한다.

```text
strategy set
strategy versions
governance bindings
performance snapshots
return series cutoff
correlation snapshot
overlap snapshot
factor exposure snapshot
regime snapshot
previous meta allocation
policy version
```

동일 입력이면:

```text
동일 strategy eligibility
동일 correlation matrix
동일 cluster
동일 meta score
동일 target weight
동일 aggregate intent
동일 output hash
```

이어야 한다.

---

## 52. Point-in-Time 규칙

모든 입력은:

```text
input.known_at <= evaluation_time
```

이어야 한다.

특히 금지:

```text
현재 strategy scorecard를 과거에 사용
현재 strategy set을 과거에 사용
현재 Governance ACTIVE binding을 과거에 사용
미래 전략성과로 과거 allocation 변경
미래 correlation로 과거 diversification 계산
```

---

## 53. 결측 처리

다음은 금지한다.

```text
missing correlation = 0
missing overlap = 0
missing health = 1
```

결측은 명시적 상태로 유지한다.

예:

```text
INSUFFICIENT_CORRELATION_SAMPLE
HEALTH_SCORE_UNAVAILABLE
FACTOR_EXPOSURE_UNAVAILABLE
```

정책은 보수적으로 backoff하거나 allocation cap을 낮춘다.

---

## 54. Backoff 정책

새 전략처럼 history가 짧은 경우:

```text
Strategy-specific covariance
→ family covariance proxy
→ market-wide conservative proxy
```

로 backoff할 수 있다.

단:

```text
PROXY_RISK_MODEL_USED
```

를 반드시 기록한다.

새 전략을 무위험처럼 취급하지 않는다.

---

## 55. 테스트 계획

### A. 독립 전략 3개 정상

```text
상관 낮음
Health 정상
Regime 적합
→ 3개 모두 allocation
→ 합계 <= meta budget
```

### B. 전략 A/B 상관 0.92

```text
A/B 모두 성과 우수
→ 둘 다 full allocation 금지
→ diversification penalty
```

### C. 수익률 상관 낮지만 보유종목 40% 중복

```text
→ SECURITY_OVERLAP_HIGH
→ allocation penalty
```

### D. Factor exposure similarity 0.93

```text
→ FACTOR_OVERLAP_HIGH
```

### E. 평상시 corr 0.2 / RISK_OFF corr 0.9

```text
→ TAIL_CORRELATION_HIGH
→ 위험예산 축소
```

### F. 120D corr 0.25 / 20D corr 0.80

```text
→ CORRELATION_SPIKE
```

### G. Strategy Health DEGRADED

```text
→ target weight 감소
→ 일반 increase 금지
```

### H. Strategy Health CRITICAL

```text
→ 신규 allocation 0
→ hard-risk 정책이면 target 0
```

### I. Governance KILL SWITCH

```text
→ strategy target 0
```

### J. 전략 cap 35%

```text
raw allocation 48%
→ 35% cap
```

### K. 동일 family 전략 3개

```text
family total > 50%
→ FAMILY_WEIGHT_CAP_BINDING
```

### L. Cluster weight 60%

```text
max 45%
→ CLUSTER_WEIGHT_CAP_BINDING
```

### M. Regime budget 70%

```text
strategy target 합계 <= 70%
```

### N. Eligible 전략이 2개뿐이고 품질 낮음

```text
→ 억지로 70% 채우지 않음
→ META_BUDGET_UNALLOCATED
```

### O. Strategy allocation 전일 10% → raw 30%

```text
max daily increase +5%p
→ effective 15%
```

### P. Risk 급악화

```text
전일 30%
raw 0%
hard risk
→ 일반 -10%p limiter 우회 가능
```

### Q. Strategy A/B 모두 삼성 BUY

```text
→ aggregate BUY
→ strategy lineage 보존
```

### R. A BUY / B SELL

```text
→ net intent 계산
→ OPPOSING_STRATEGY_INTENT
```

### S. 미래 strategy return 유입

```text
→ BLOCKED
```

### T. 현재 ACTIVE 전략을 과거 replay에 사용

```text
→ BLOCKED
```

### U. missing correlation을 0으로 취급

```text
→ test fail
```

### V. 신규 전략 history 10일

```text
→ independent covariance 금지
→ conservative proxy 또는 allocation 제한
```

### W. 동일 입력 재실행

```text
→ 동일 cluster
→ 동일 meta score
→ 동일 allocation
→ 동일 aggregate intent
→ 동일 hash
```

---

## 56. 통합 테스트

### Scenario 1. Momentum + Revision 과도한 중복

```text
Momentum score 높음
Revision score 높음
두 전략 correlation 0.87
반도체 overlap 42%

→ 두 전략 합산 allocation 제한
→ Value/Defensive 전략에 marginal diversification benefit 증가
```

### Scenario 2. RECOVERY 시장

```text
43 meta risk budget = 70%
Momentum regime score 높음
Value 보통
Defensive 낮음

→ Momentum 확대 가능
→ 단 correlation / overlap cap 유지
→ 총 전략예산 70% 초과 금지
```

### Scenario 3. RISK_OFF 급전환

```text
43 risk budget 70% → 40%
51 기존 전략 합계 65%

→ 전략별 target 축소
→ 위험 악화이므로 빠른 de-risk
→ 44/45/23에 target delta 전달
```

### Scenario 4. 한 전략만 압도적 성과

```text
Strategy A IR 2.0
B/C IR 0.8

A raw 60%
max strategy cap 35%

→ A 35%
→ 잔여를 품질/다각화 기준으로 재배분
```

### Scenario 5. 모든 전략 상관 급등

```text
평균 corr 0.35 → 0.82

→ CORRELATION_SPIKE
→ cluster concentration 상승
→ meta risk budget 전부 사용하지 않을 수 있음
```

---

## 57. 성능 테스트

초기 목표:

```text
전략 수 <= 50
return history <= 5,000 trading days
security universe <= 5,000
```

목표 수행시간 예:

```text
Eligibility / health      < 1s
Correlation / covariance  < 2s
Overlap matrix            < 3s
Clustering                < 2s
Allocation                < 1s
Snapshot finalize         < 1s
```

정확성과 재현성이 속도보다 우선한다.

---

## 58. Property-based Test

자동 생성된 입력에서도 다음이 항상 성립해야 한다.

```text
strategy weight >= 0
blocked strategy weight = 0
Σ strategy weight <= meta budget
strategy cap 초과 = 0
family cap 초과 = 0
cluster cap 초과 = 0
NaN weight = 0
future input usage = 0
```

---

## 59. Replay Test

과거 특정 날짜를 replay한다.

```text
2026-05-15
```

당시:

```text
ACTIVE strategy set
Governance binding
Regime
Performance history
Correlation
Overlap
Policy
```

만 사용해야 한다.

현재 8월에 승인된 전략을 5월 replay에 포함하면 test failure다.

---

## 60. 핵심 불변식

```text
승인되지 않은 전략 allocation > 0 = 0
Kill Switch 전략 allocation > 0 = 0

미래 전략성과 사용 = 0
미래 correlation 사용 = 0
미래 Governance binding 사용 = 0

missing correlation을 0으로 대체 = 0
missing health를 정상으로 대체 = 0

strategy cap 초과 = 0
family cap 초과 = 0
cluster cap 초과 = 0

meta risk budget 초과 = 0

hard blocked 전략 신규위험 = 0

전략 이름만 다른 동일위험 무제한 중복 = 0

aggregate intent 생성 시 strategy lineage 손실 = 0

과거 meta allocation snapshot 수정 = 0

49번 feedback의 직접 policy 변경 = 0
50번 research의 Governance 우회 = 0

동일 입력 + 정책 + 이전 allocation
→ 동일 eligibility
→ 동일 correlation
→ 동일 cluster
→ 동일 meta score
→ 동일 target allocation
→ 동일 aggregate intent
→ 동일 hash
```

---

## 61. 구현 순서

```text
1 Immutable Strategy 모델
2 DB migration
3 Governance strategy resolver
4 Strategy return series / alignment
5 Health score
6 Drawdown state
7 Correlation / shrinkage covariance
8 Downside / tail correlation
9 Security overlap
10 Sector / Factor overlap
11 Strategy clustering
12 Regime compatibility
13 Base score
14 Diversification penalty
15 Marginal Strategy Utility
16 Constrained allocator
17 Strategy / Family / Cluster caps
18 Turnover / hysteresis
19 Unallocated capital 처리
20 Cross-strategy intents
21 Deterministic netting
22 Attribution mapping
23 Manifest / hashing
24 통합 / replay / property test
```

---

## 62. 51번 완료 기준

51번 v1은 다음이 모두 가능할 때 완료된 것으로 본다.

```text
여러 승인 전략을 하나의 Meta Portfolio로 조합

전략간
- return correlation
- tail correlation
- security overlap
- sector overlap
- factor overlap
을 수치화

Regime과 Strategy Health를 반영해
전략별 위험예산을 결정

전략 / family / cluster 집중도를 제한

전략간 동일 종목 주문을 netting하되
원래 전략 lineage를 보존

모든 배분결정을 PIT Snapshot으로 재현

미래정보 없이 과거 Meta Allocation replay 가능
```

---

## 63. 다음 엔진과의 연결

51번 이후에는 개별 전략과 전략 조합까지 통합됐다.

```text
49
결과를 분석한다

50
전략 개선안을 검증한다

48
사용 가능한 전략을 승인한다

51
여러 승인 전략을 어떻게 함께 운용할지 결정한다
```

다음 엔진은 **52. Portfolio-Level Stress Testing, Scenario & Survival Engine**이 적절하다.

51번에서 여러 전략이 조합되더라도 실제 위기에서는 상관관계가 급등할 수 있으므로, 다음 단계에서는 다음 질문을 검증해야 한다.

```text
금리 급등
유가 급등
원화 급락
반도체 -20%
KOSPI -10%
유동성 증발
상관관계 1에 수렴

이 상황에서
ADE 포트폴리오는 얼마나 잃고
어떤 제약이 먼저 깨지며
얼마나 빨리 위험을 줄일 수 있는가?
```
