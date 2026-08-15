# 47. Execution Calibration & Transaction Cost Model Learning Engine v1

## 1. 목적

Execution Calibration & Transaction Cost Model Learning Engine은 34번 Transaction Cost, Slippage & Market Impact Engine과 46번 Execution Simulation Engine이 사전에 예측한 **비용, 슬리피지, 체결률, 체결지연, 부분체결 확률**을 실제 PAPER/LIVE_SHADOW/실체결 관측값과 비교하고, 예측오차를 통계적으로 보정하여 다음 실행 모델 파라미터를 생성하는 계층이다.

이 엔진의 목적은 수익률을 직접 최적화하는 것이 아니다. 핵심 목표는 다음과 같다.

1. 예상 거래비용과 실제 실행비용의 체계적 편향 제거
2. Fill probability와 실제 fill ratio의 calibration 개선
3. 종목 유동성·주문 크기·세션·변동성·시장국면별 오차 분해
4. 34번/46번 모델 파라미터의 안전한 재추정
5. 학습 구간과 평가 구간의 완전 분리
6. 미래정보 유입, 과적합, 데이터 스누핑 방지
7. 모델 변경 전후의 재현 가능한 champion/challenger 비교
8. 승인되지 않은 자동 정책 변경 방지

본 엔진은 BUY/SELL 신호, 목표비중, 주문 방향을 결정하지 않는다.

---

## 2. 책임 경계

### 수행 책임

- 예측 execution snapshot과 realized execution outcome 정합
- predicted vs realized residual 계산
- calibration cohort 생성
- feature bin별 편향/분산 측정
- cost/slippage/fill 모델 파라미터 후보 학습
- walk-forward validation
- champion/challenger 비교
- promotion eligibility 판정
- drift 탐지
- 정책 snapshot과 학습 lineage 저장

### 수행하지 않는 책임

- 종목 선택
- 포트폴리오 비중 결정
- 실제 주문 전송
- 실체결 복구
- 회계 P&L 확정
- 자동 production 배포

정책 승격은 별도 governance 승인 이후에만 가능하다.

---

## 3. 상위 아키텍처

```text
34 Transaction Cost / Slippage / Impact
        ↓ predicted cost
46 Execution Simulation
        ↓ predicted fill / price / latency
25 Execution Reconciliation
        ↓ realized fills
19 Portfolio Accounting
        ↓ realized explicit costs

        ┌────────────────────────────────────┐
        │ 47 Execution Calibration Engine    │
        ├────────────────────────────────────┤
        │ Prediction/Outcome Join            │
        │ Residual Decomposition             │
        │ Cohort Builder                     │
        │ Calibration Metrics                │
        │ Drift Detection                    │
        │ Parameter Estimation               │
        │ Walk-Forward Validation            │
        │ Champion / Challenger              │
        │ Promotion Gate                     │
        │ Evidence / Hash                    │
        └────────────────────────────────────┘
                ↓
     Approved Calibration Snapshot
                ↓
34 / 46 model parameter policy
```

---

## 4. 핵심 원칙

### 4.1 예측 당시 정보와 사후 결과를 분리한다

모델 입력은 반드시 주문 승인 시점 이전 또는 실행 시점에 이용 가능했던 정보만 사용한다.

```text
feature.known_at <= prediction_time
```

실현 체결은 target label일 뿐, 같은 표본의 prediction feature에 들어갈 수 없다.

### 4.2 학습과 평가를 시간순으로 분리한다

랜덤 train/test split을 기본으로 사용하지 않는다.

```text
TRAIN      VALIDATION       TEST
past  →      later      →  newest
```

v1 기본은 expanding 또는 rolling walk-forward 방식이다.

### 4.3 자동 실전 승격 금지

```text
TRAINED
→ VALIDATED
→ CHALLENGER
→ APPROVED
→ ACTIVE
```

학습 완료만으로 ACTIVE가 될 수 없다.

---

## 5. 입력 계약

```python
@dataclass(frozen=True)
class ExecutionCalibrationRequest:
    calibration_run_id: str
    as_of_time: datetime
    training_start: datetime
    training_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime | None
    test_end: datetime | None

    cost_model_version: str
    execution_model_version: str
    calibration_policy_id: str
    source_environment: str  # PAPER | LIVE_SHADOW | LIVE
```

관측 단위는 기본적으로 `order_id`와 `fill_id`이다.

필수 입력:

- predicted explicit cost
- predicted implicit cost
- predicted impact bps
- predicted slippage bps
- predicted fill probability
- predicted fill ratio
- predicted time-to-fill
- arrival price
- requested quantity / notional
- realized fill quantity
- realized fill VWAP
- realized explicit costs
- realized slippage
- realized implementation shortfall
- ADV20 / spread / volatility
- order participation rate
- order type / side / session
- market regime
- instrument / sector / liquidity bucket

---

## 6. 핵심 Label 정의

### 6.1 Slippage residual

BUY 기준:

```text
realized_slippage_bps
= (fill_vwap - arrival_price)
  / arrival_price * 10,000
```

SELL 기준은 부호를 정규화하여 **양수일수록 비용이 큰 방향**으로 통일한다.

```text
slippage_residual
= realized_slippage_bps
  - predicted_slippage_bps
```

### 6.2 Cost residual

```text
cost_residual_bps
= realized_total_cost_bps
  - predicted_total_cost_bps
```

### 6.3 Fill calibration error

```text
fill_error
= realized_fill_ratio
  - predicted_fill_ratio
```

binary fill probability 모델은 Brier score와 calibration curve를 사용한다.

### 6.4 Time-to-fill error

```text
latency_error
= realized_time_to_fill_seconds
  - predicted_time_to_fill_seconds
```

---

## 7. Calibration Cohort

전체 주문을 한 번에 학습하지 않고 최소 다음 cohort로 분해한다.

```text
SIDE
BUY / SELL

ORDER TYPE
MARKET / LIMIT / MOC / LOC

LIQUIDITY
MEGA / LARGE / MID / SMALL / ILLIQUID

PARTICIPATION
<0.1%
0.1~0.5%
0.5~1%
1~3%
>3%

VOLATILITY
LOW / NORMAL / HIGH / EXTREME

SPREAD
TIGHT / NORMAL / WIDE

SESSION
OPEN / MORNING / MIDDAY / AFTERNOON / CLOSE

REGIME
RISK_ON / NORMAL / RECOVERY / RISK_OFF / CRISIS
```

표본이 부족한 cohort는 상위 bucket으로 backoff한다.

```text
security
→ industry
→ liquidity bucket
→ market-wide
```

Reason code:

```text
INSUFFICIENT_CALIBRATION_SAMPLE
CALIBRATION_BACKOFF_APPLIED
```

---

## 8. v1 모델 구조

v1은 복잡한 ML보다 해석 가능하고 안정적인 계층형 calibration을 기본으로 한다.

### 8.1 Slippage model

```text
predicted_slippage_bps
= base_spread_component
+ participation_component
+ volatility_component
+ regime_component
+ session_component
```

예시 형태:

```text
slippage_bps
= β0
+ β1 * spread_bps
+ β2 * sqrt(participation_rate)
+ β3 * realized_volatility
+ β4 * open_dummy
+ β5 * close_dummy
+ β6 * stressed_regime_dummy
```

계수는 robust regression 또는 Huber regression을 기본으로 한다.

### 8.2 Market impact

초기 함수:

```text
impact_bps
= η * volatility
  * sqrt(order_notional / ADV20)
```

Calibration은 η를 liquidity/regime cohort별로 추정한다.

### 8.3 Fill ratio model

지정가 주문의 경우:

```text
fill_ratio_hat
= f(
    price_aggressiveness,
    spread,
    volume_capacity,
    participation,
    volatility,
    time_remaining
  )
```

v1에서는 isotonic calibration 또는 monotonic bin mapping을 기본으로 하여 확률 순서를 보존한다.

---

## 9. 손실함수와 평가 지표

### Cost / Slippage

```text
MAE_bps
MedianAE_bps
RMSE_bps
Bias_bps
P90_abs_error
P95_abs_error
```

비용 모델은 평균오차만 작고 tail error가 큰 모델을 승격하지 않는다.

### Fill Probability

```text
Brier Score
Log Loss
Expected Calibration Error (ECE)
Calibration Slope
Calibration Intercept
```

### Fill Ratio

```text
MAE_fill_ratio
RMSE_fill_ratio
Bias_fill_ratio
```

### Latency

```text
Median Absolute Error
P90 latency error
```

---

## 10. Drift Detection

모델이 과거에는 맞았지만 최근 시장구조 변화로 틀릴 수 있으므로 drift를 독립적으로 관리한다.

감시 대상:

- residual mean drift
- residual variance drift
- spread distribution shift
- participation distribution shift
- volatility regime shift
- fill ratio shift

v1 기본 탐지:

```text
rolling_20d_bias
rolling_60d_bias
PSI
KS distance
```

예시:

```text
abs(rolling_20d_cost_bias) > 5 bps
AND
sample_count >= 100
→ CALIBRATION_DRIFT_WARNING
```

강한 drift:

```text
MODEL_RECALIBRATION_REQUIRED
```

---

## 11. 데이터 누수 방지

다음은 금지한다.

```text
오늘 실현 체결정보를 오늘 주문 예측에 사용
미래 spread/volume을 과거 주문 feature로 사용
전체기간 정규화 통계를 과거 fold에 사용
테스트기간 결과를 parameter selection에 사용
현재 ACTIVE 모델로 과거 predicted snapshot 덮어쓰기
```

모든 fold는 당시 이용 가능한 데이터만 사용한다.

---

## 12. Champion / Challenger

현재 ACTIVE 모델을 `CHAMPION`, 새 모델을 `CHALLENGER`로 정의한다.

Challenger 승격 기본 조건:

```text
1. validation MAE 개선
2. validation bias 악화 없음
3. P95 error 악화 없음
4. fill calibration 악화 없음
5. 최소 표본수 충족
6. 최소 관측기간 충족
7. stressed regime 성능 허용범위
8. deterministic replay 통과
```

예:

```text
MAE improvement >= 5%
P95 degradation <= 2%
abs(bias) <= approved_limit
```

단, 특정 정상장에서만 좋아지고 RISK_OFF에서 크게 악화되면 승격하지 않는다.

```text
REGIME_ROBUSTNESS_FAILED
```

---

## 13. Promotion State Machine

```text
DRAFT
  ↓
TRAINED
  ↓
VALIDATED
  ↓
CHALLENGER
  ↓
APPROVAL_PENDING
  ↓
APPROVED
  ↓
ACTIVE
  ↓
SUPERSEDED
```

실패 상태:

```text
REJECTED
ROLLED_BACK
QUARANTINED
```

47번 엔진은 기본적으로 `APPROVAL_PENDING`까지만 자동 생성할 수 있다.

---

## 14. 파라미터 안정화

새 추정치를 그대로 적용하지 않고 shrinkage를 사용한다.

```text
new_effective_parameter
= (1 - λ) * current_parameter
+ λ * estimated_parameter
```

초기 PAPER 정책:

```text
λ <= 0.25 per calibration cycle
```

즉 한 번의 calibration으로 계수가 4배 변하는 등의 급격한 정책변경을 막는다.

추가 제한:

```text
max_parameter_change_pct
max_absolute_parameter_change
```

Reason code:

```text
PARAMETER_CHANGE_LIMIT_APPLIED
```

---

## 15. 데이터베이스

주요 테이블:

```text
execution_calibration_policies
execution_calibration_runs
execution_calibration_observations
execution_calibration_cohorts
execution_calibration_metrics
execution_model_parameters
execution_model_candidates
execution_model_promotions
execution_model_drift_events
execution_calibration_reason_events
execution_calibration_manifests
```

### execution_calibration_runs

```text
run_id
as_of_time
training_start
training_end
validation_start
validation_end
test_start
test_end
source_environment
champion_version
policy_version
policy_hash
status
input_hash
result_hash
created_at
finalized_at
```

### execution_calibration_observations

```text
observation_id
run_id
order_id
fill_id
instrument_id
prediction_time
realization_time
predicted_slippage_bps
realized_slippage_bps
predicted_cost_bps
realized_cost_bps
predicted_fill_probability
predicted_fill_ratio
realized_fill_ratio
predicted_latency_seconds
realized_latency_seconds
liquidity_bucket
volatility_bucket
regime
feature_snapshot_hash
```

### execution_model_parameters

```text
parameter_snapshot_id
model_family
model_version
cohort_key
parameter_name
parameter_value
training_window
known_at
approved_at
status
parameter_hash
```

---

## 16. 코드 구조

```text
execution_calibration/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── transaction_cost.py
│   ├── execution_simulation.py
│   ├── reconciliation.py
│   ├── accounting.py
│   └── market_data.py
│
├── joins.py
├── labels.py
├── cohorts.py
├── residuals.py
├── metrics.py
├── drift.py
├── temporal_split.py
├── walk_forward.py
│
├── models/
│   ├── slippage.py
│   ├── impact.py
│   ├── fill_probability.py
│   └── latency.py
│
├── shrinkage.py
├── stability.py
├── champion_challenger.py
├── promotion.py
├── rollback.py
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 17. 핵심 알고리즘 의사코드

```python
def calibrate_execution_model(ctx):
    observations = load_point_in_time_observations(ctx)

    joined = join_predictions_to_realized_outcomes(observations)
    joined = reject_temporal_leakage(joined)

    train, validation, test = temporal_split(joined, ctx.policy)

    cohorts = build_cohorts(train)

    challenger = fit_models(
        train=train,
        cohorts=cohorts,
        robust=True,
        monotonic_fill_model=True,
    )

    validation_metrics = evaluate(challenger, validation)
    champion_metrics = evaluate(ctx.current_champion, validation)

    drift = detect_drift(joined, ctx.policy)

    promotion = compare_champion_challenger(
        champion_metrics,
        validation_metrics,
        drift,
        ctx.policy,
    )

    stabilized_parameters = apply_shrinkage_and_change_limits(
        current=ctx.current_champion.parameters,
        estimated=challenger.parameters,
        policy=ctx.policy,
    )

    return finalize_calibration_snapshot(
        metrics=validation_metrics,
        parameters=stabilized_parameters,
        promotion_state=promotion,
    )
```

---

## 18. Explainability 출력

각 calibration 결과는 최소 다음을 설명할 수 있어야 한다.

```text
기존 예상 슬리피지: 12.0 bps
최근 실제 평균:     16.8 bps
편향:              +4.8 bps

주요 원인:
- OPEN session +2.1 bps
- HIGH volatility +1.7 bps
- 1% 이상 participation +1.0 bps

새 추정 계수: +18%
실제 적용 계수: +4.5%
(shrinkage λ=0.25)
```

즉 “모델이 바뀌었다”가 아니라 **왜 바뀌었고 얼마나 제한해서 반영했는지** 설명해야 한다.

---

## 19. 주요 Reason Code

```text
CALIBRATION_SAMPLE_READY
INSUFFICIENT_CALIBRATION_SAMPLE
CALIBRATION_BACKOFF_APPLIED

POSITIVE_COST_BIAS
NEGATIVE_COST_BIAS
FILL_PROBABILITY_MISCALIBRATED
LATENCY_MODEL_BIAS

CALIBRATION_DRIFT_WARNING
MODEL_RECALIBRATION_REQUIRED

TEMPORAL_LEAKAGE_BLOCKED
FUTURE_MARKET_DATA_BLOCKED
TRAIN_TEST_OVERLAP_BLOCKED

CHALLENGER_IMPROVED
CHALLENGER_NO_IMPROVEMENT
TAIL_ERROR_DEGRADED
REGIME_ROBUSTNESS_FAILED

PARAMETER_CHANGE_LIMIT_APPLIED
SHRINKAGE_APPLIED

PROMOTION_ELIGIBLE
PROMOTION_REJECTED
APPROVAL_REQUIRED
MODEL_ROLLBACK_REQUIRED
```

---

## 20. 테스트 계획

```text
A. 예측 10 bps / 실제 평균 15 bps
→ +5 bps positive bias 검출

B. BUY/SELL 부호
→ 비용 방향으로 정규화 후 동일 해석

C. predicted fill probability 0.8
   실제 fill 빈도 0.5
→ miscalibration 검출

D. 표본 10건뿐인 개별종목
→ 종목 전용 계수 생성 금지
→ liquidity cohort backoff

E. 학습기간 이후 데이터가 train에 포함
→ TEMPORAL_LEAKAGE_BLOCKED

F. validation과 train 기간 중첩
→ 실행 BLOCKED

G. Challenger MAE -10% 개선
   P95 +15% 악화
→ 승격 거절

H. Normal regime 개선
   Risk-Off 대폭 악화
→ REGIME_ROBUSTNESS_FAILED

I. 추정 impact coefficient +80%
   max cycle change 20%
→ 실제 새 policy는 +20% 이내

J. residual 20일 bias 급증
→ CALIBRATION_DRIFT_WARNING

K. drift 지속 + 최소 표본 충족
→ MODEL_RECALIBRATION_REQUIRED

L. PAPER 데이터와 LIVE_SHADOW 혼합
→ environment tag 보존
→ 정책상 허용되지 않으면 분리

M. 동일 데이터·정책 재실행
→ 동일 metrics
→ 동일 parameters
→ 동일 hash

N. ACTIVE 모델 변경 후 과거 predicted snapshot
→ 과거 값 불변

O. 미래 realized fill을 prediction feature로 사용
→ 사용 0건
```

---

## 21. 핵심 불변식

```text
미래 시장데이터의 학습 feature 사용 = 0
미래 realized fill의 prediction feature 사용 = 0
Train/Test 시간 중첩 = 0
Validation 결과를 Train feature로 사용 = 0

최소 표본 미달 cohort의 독립 파라미터 생성 = 0
승인 없는 ACTIVE 승격 = 0
한 cycle 정책변경 한도 초과 = 0

현재 모델로 과거 predicted snapshot 덮어쓰기 = 0
과거 calibration snapshot UPDATE/DELETE = 0

Challenger가 평균만 개선하고 tail risk 크게 악화된 상태에서 승격 = 0
RISK_OFF 성능 검증 없이 production 승격 = 0

동일 입력 + 동일 정책 + 동일 champion
→ 동일 candidate parameter
→ 동일 metrics
→ 동일 promotion decision
→ 동일 snapshot hash
```

---

## 22. 34·46번과의 최종 연결

```text
34
예상 비용 / impact
        ↓
46
예상 체결 / fill / slippage
        ↓
실제 PAPER / LIVE_SHADOW 결과
        ↓
47
예측오차 측정
        ↓
cohort별 calibration
        ↓
walk-forward 검증
        ↓
champion vs challenger
        ↓
승인된 parameter snapshot
        ↓
34 / 46 다음 버전
```

47번의 존재로 ADE는 실행모델을 고정된 상수가 아니라 **실제 시장 미시구조 변화에 맞추어 검증·학습되는 모델**로 운영할 수 있다. 다만 학습과 배포 사이에 명확한 승인 경계를 유지하여 자동 과적합과 정책 폭주를 차단한다.

---

## 23. 구현 순서

```text
1. immutable observation model
2. DB migration
3. prediction-realization join
4. residual calculators
5. cohort builder
6. temporal split / walk-forward
7. calibration metrics
8. robust slippage model
9. impact coefficient calibration
10. fill probability calibration
11. drift detector
12. champion/challenger evaluator
13. shrinkage/change limiter
14. promotion state machine
15. manifests / hashes
16. fixed-fixture integration tests
```
