# 64. Market Universe Investability, Capacity & PIT Snapshot Engine v1

## 1. 목적

Engine 64는 Engine 32 `Universe Selection & Eligibility`가 만든 **평가 가능 종목 집합**을 입력으로 받아, 각 종목이 현재 시점에 실제 신규 위험을 받을 수 있는지와 어느 정도까지 수용 가능한지를 Point-in-Time(PIT) 기준으로 확정한다.

Engine 32의 질문은 `이 종목을 평가해도 되는가?`이고, Engine 64의 질문은 `평가 가능한 이 종목을 지금 실제 포트폴리오 후보로 사용할 수 있는가?`이다.

따라서 다음을 명확히 분리한다.

```text
32 Eligibility
ELIGIBLE / WATCH_ONLY / EXCLUDED
        ↓
64 Investability
INVESTABLE / LIMITED / NON_INVESTABLE
        ↓
63 PIT Feature Store
        ↓
38~42 Signal Pipeline
```

Engine 64는 Signal, Alpha, Confidence, Ranking을 만들지 않는다. 투자 가능성·유동성·거래상태·이벤트·용량·데이터 신뢰도를 기준으로 **오늘의 실제 Investable Universe Snapshot**을 만든다.

---

## 2. 책임 경계

### 담당

- Engine 32 ELIGIBLE 결과를 PIT 기준으로 재검증
- 실제 거래 가능 세션·정지·정리매매·가격제한 상태 반영
- 신규상장·재상장·합병·분할·권리락 등 이벤트 기반 제한
- 최근 거래대금·ADV·free-float·turnover 기반 investability 계산
- 포트폴리오 규모 대비 거래 가능 capacity 산출
- 시장 충격/유동성 스트레스 기반 capacity haircut
- 종목별 `INVESTABLE`, `LIMITED`, `NON_INVESTABLE` 결정
- Engine 63이 사용할 PIT Universe Snapshot freeze
- 제외/제한 사유와 evidence lineage 저장

### 담당하지 않음

- Fundamental/Valuation/Expectations/Behavior feature 계산
- Signal score 및 후보 순위 계산
- 포트폴리오 목표비중 결정
- 주문 수량 산정
- 주문 전송 또는 체결
- 보유종목 자동청산

---

## 3. 아키텍처

```text
36 Instrument Master
35 Market Data Finalization
32 Universe Eligibility
33 Corporate Actions
37 Benchmark / Constituents
61 Configuration Snapshot
62 Semantic Contracts
Current Portfolio NAV
Liquidity / ADV / Free Float
Trading Calendar / Session State
        ↓
┌────────────────────────────────────────┐
│ 64 Investability & Capacity Engine    │
├────────────────────────────────────────┤
│ Input / Temporal Validation           │
│ Eligibility Bridge                    │
│ Tradability Resolver                  │
│ Event-Risk Resolver                   │
│ Liquidity Metrics                     │
│ Capacity Estimation                   │
│ Stress Haircut                        │
│ New-Listing / Corporate-Action Rules  │
│ Investability State Machine           │
│ Universe Completeness Validation      │
│ PIT Snapshot Freeze                   │
└────────────────────────────────────────┘
        ↓
PIT Investable Universe Snapshot
        ↓
63 Feature Store
        ↓
38~42 Signal / Ranking
```

핵심 원칙:

```text
ELIGIBLE != INVESTABLE

INVESTABLE != BUY

Investability는 Alpha 이전의 실행가능성 Gate다.
```

---

## 4. 입력 계약

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

@dataclass(frozen=True)
class InvestabilityRequest:
    run_id: str
    portfolio_id: str
    market: str
    evaluation_time: datetime
    decision_cutoff: datetime

    eligibility_snapshot_id: str
    instrument_snapshot_id: str
    market_snapshot_id: str
    corporate_action_snapshot_id: str
    configuration_snapshot_id: str
    semantic_contract_snapshot_id: str

    portfolio_nav: Decimal
```

필수 조건:

```text
source.known_at <= decision_cutoff
source.materialized_at <= decision_cutoff
Engine32 snapshot.state == FINALIZED
Market snapshot.state == FINALIZED
Configuration snapshot == frozen run binding
```

조건을 만족하지 않으면 다음 상태를 허용하지 않는다.

```text
INVESTABLE
```

---

## 5. 출력 상태

```python
from enum import StrEnum

class InvestabilityState(StrEnum):
    INVESTABLE = "INVESTABLE"
    LIMITED = "LIMITED"
    NON_INVESTABLE = "NON_INVESTABLE"
```

의미:

| 상태 | 의미 |
|---|---|
| `INVESTABLE` | Feature/Signal 후보로 정상 사용 가능 |
| `LIMITED` | 분석 가능하지만 신규 위험에 용량/이벤트 제한 존재 |
| `NON_INVESTABLE` | 신규 후보 경로 사용 금지 |

보유종목은 `NON_INVESTABLE`이라도 Portfolio 원장에서 제거하지 않는다. Lifecycle/Risk/Execution 계층에서 별도로 처리한다.

---

## 6. 종목별 출력 모델

```python
@dataclass(frozen=True)
class InvestabilityResult:
    security_id: str
    state: InvestabilityState

    is_tradable: bool
    is_new_entry_allowed: bool

    adv20_krw: Decimal | None
    median_turnover20_krw: Decimal | None
    free_float_market_cap_krw: Decimal | None

    normal_capacity_krw: Decimal | None
    stressed_capacity_krw: Decimal | None
    portfolio_capacity_weight: Decimal | None

    liquidity_score: float | None
    capacity_score: float | None
    event_risk_score: float | None
    overall_investability_score: float | None

    reasons: tuple[str, ...]
    evidence_hash: str
    result_hash: str
```

---

## 7. Engine 32와의 연결 규칙

```text
32 = EXCLUDED
→ 64 = NON_INVESTABLE

32 = WATCH_ONLY
→ 신규 진입 기본 NON_INVESTABLE
→ 보유종목은 별도 monitoring lineage 유지

32 = ELIGIBLE
→ 64 세부 investability 검사 수행
```

64는 32의 하드 제외를 완화할 수 없다.

```text
64 override direction = MORE_CONSERVATIVE_ONLY
```

---

## 8. Tradability Gate

신규 위험 경로에서 다음은 Hard Block이다.

```text
TRADING_SUSPENDED
LIQUIDATION_TRADING
DELISTING_IN_PROGRESS
MARKET_SESSION_INVALID
NO_EXECUTABLE_MARKET
IDENTITY_UNRESOLVED
CRITICAL_MARKET_DATA_MISSING
UNRESOLVED_CORPORATE_ACTION
```

다음은 기본 `LIMITED` 또는 정책상 block이다.

```text
PRICE_LIMIT_LOCK_RISK
ABNORMAL_SPREAD
EXTREME_GAP
RECENT_RELISTING
RECENT_TRADING_RESUMPTION
SPECIAL_MARKET_DESIGNATION
```

---

## 9. 신규상장 / 재상장 정책

상장 직후 종목은 데이터가 적고 가격발견이 불안정하다.

초기 PAPER 정책 예:

```text
IPO age < 20 trading days
→ NON_INVESTABLE

20 <= age < 60 trading days
→ LIMITED

age >= 60 trading days
→ 일반 규칙 적용
```

재상장, 인적분할 후 신규 listing, 합병 후 재거래도 별도 age clock을 둘 수 있다.

```text
listing_age
continuous_price_history_age
post_event_age
```

을 구분한다.

---

## 10. Corporate Action Event Window

다음 이벤트 전후에는 정상 가격·수량 계열의 연속성이 깨질 수 있다.

```text
STOCK_SPLIT
REVERSE_SPLIT
RIGHTS_ISSUE
BONUS_ISSUE
MERGER
SPINOFF
DEMERGER
RELISTING
TRADING_RESUMPTION
```

정책 예:

```text
corporate_action_unresolved
→ NON_INVESTABLE

resolved but post-event history < 5 sessions
→ LIMITED
```

Engine 33의 adjusted-price lineage가 정상임을 확인한 후에만 `INVESTABLE` 복귀를 허용한다.

---

## 11. Liquidity Metrics

최소 지표:

```text
ADV20_KRW
ADV60_KRW
MEDIAN_TURNOVER20_KRW
TURNOVER_RATE20
ZERO_VOLUME_DAYS20
VALID_BAR_RATIO20
FREE_FLOAT_MARKET_CAP
```

단일 일자의 거래대금 급증에 의해 저유동성 종목이 정상 종목처럼 보이지 않도록 `median turnover`와 `ADV`를 함께 사용한다.

---

## 12. 정상 거래 Capacity

기본 daily notional capacity:

```text
capacity_adv
= ADV20 × max_adv_participation
```

예:

```text
ADV20 = 50억원
max_adv_participation = 1%

capacity_adv = 5천만원
```

Free-float cap도 동시에 적용한다.

```text
capacity_float
= free_float_market_cap × max_free_float_position
```

최종 정상 capacity:

```text
normal_capacity
= min(capacity_adv, capacity_float)
```

정확한 비율은 Engine 61 Configuration에서 관리한다.

---

## 13. 포트폴리오 대비 Capacity

가상 NAV가 10,000,000원이고 종목당 최대비중이 10%라면 이론적 종목 목표금액은 1,000,000원이다.

하지만 시장 capacity가 600,000원이라면:

```text
policy single-name cap = 10%
market capacity cap = 6%

실제 investability capacity = 6%
```

따라서:

```text
portfolio_capacity_weight
= min(
    normal_capacity / NAV,
    single_name_policy_cap
)
```

64는 목표 비중을 결정하지 않지만 44/54가 사용할 상한을 제공한다.

---

## 14. Stress Capacity

평상시 거래대금만 보면 위기 때 capacity를 과대평가할 수 있다.

```text
stressed_adv
= ADV20 × liquidity_stress_multiplier
```

예:

```text
NORMAL       1.00
ELEVATED     0.70
HIGH_VOL     0.50
RISK_OFF     0.35
CRISIS       0.20
```

최종:

```text
stressed_capacity
= min(
    stressed_adv × max_adv_participation,
    capacity_float
)
```

43/52의 Regime/Stress 결과를 사용할 수 있지만 미래 시나리오 결과를 현재 실제 capacity로 오인하지 않는다. `operational stress capacity`와 `scenario analysis capacity`를 별도 namespace로 유지한다.

---

## 15. Investability Score

Hard Gate가 없는 경우에만 보조 score를 계산한다.

초기 구조:

```text
Investability Score
=
35% Liquidity
25% Capacity
15% Trading Continuity
10% Data Quality
10% Event Stability
 5% Free-Float Quality
```

예시 상태:

```text
score >= 75
→ INVESTABLE

50 <= score < 75
→ LIMITED

score < 50
→ NON_INVESTABLE
```

단 Hard Block은 점수로 상쇄할 수 없다.

```text
Hard Block > Score
```

---

## 16. 왜 점수만 사용하지 않는가

다음 종목이 있다고 가정한다.

```text
Liquidity Score 95
Capacity Score 95
Data Score 100

BUT
TRADING_SUSPENDED
```

평균점수는 높지만 실제 매수는 불가능하다.

따라서:

```text
Hard Gate
→ State 결정

Soft Metrics
→ INVESTABLE/LIMITED 세부 결정
```

순서로 처리한다.

---

## 17. Price / Spread Abnormality

다음은 execution risk를 높인다.

```text
close_price too low
spread_bps extreme
intraday gap extreme
price-limit proximity
zero-volume bars
```

64는 예상수익이 높은지를 평가하지 않고 `정상적인 진입·청산이 가능한 구조인지`만 평가한다.

---

## 18. PIT Universe Snapshot

Engine 63은 current market listing을 직접 조회하지 않고 반드시 64의 snapshot을 입력으로 받는다.

```python
@dataclass(frozen=True)
class InvestableUniverseSnapshot:
    snapshot_id: str
    run_id: str
    market: str
    evaluation_time: datetime
    decision_cutoff: datetime

    source_eligibility_snapshot_id: str
    configuration_snapshot_id: str

    investable_count: int
    limited_count: int
    non_investable_count: int

    universe_hash: str
    snapshot_hash: str
```

Snapshot은 append-only다.

---

## 19. Historical Replay

2024년 Feature를 만들 때 2026년 현재 Investable Universe를 사용할 수 없다.

```text
Historical Feature Date
        ↓
Historical Engine32 Eligibility Snapshot
        ↓
Historical Engine64 Investability Snapshot
        ↓
Historical Engine63 Feature Snapshot
```

공식 replay에서 현재 universe를 과거에 소급하면:

```text
CURRENT_INVESTABILITY_IN_HISTORICAL_REPLAY
→ BLOCKED
```

이다.

---

## 20. Survivorship Bias

현재 상장폐지된 종목도 당시에는 investable했을 수 있다.

```text
현재 listing 상태
!= 과거 investability 상태
```

따라서 historical snapshot에는 delisted security도 당시 조건에 따라 포함한다.

---

## 21. 데이터베이스

핵심 테이블:

```text
investability_policies
investability_runs

investability_input_members
investability_results
investability_metric_values

investability_capacity_results
investability_event_states
investability_tradability_states

investable_universe_snapshots
investable_universe_members

investability_reason_events
investability_manifests
```

### `investability_runs`

```text
run_id
portfolio_id
market
evaluation_time
decision_cutoff

eligibility_snapshot_id
market_snapshot_id
corporate_action_snapshot_id
configuration_snapshot_id
semantic_contract_snapshot_id

status
input_hash
output_hash
created_at
finalized_at
```

### `investability_results`

```text
run_id
security_id

engine32_status
investability_state
is_tradable
is_new_entry_allowed

overall_score
liquidity_score
capacity_score
event_score

normal_capacity_krw
stressed_capacity_krw
portfolio_capacity_weight

primary_reason_code
result_hash
```

### `investable_universe_members`

```text
snapshot_id
security_id
state
capacity_weight
rank_eligible
feature_eligible
reason_codes
member_hash
```

`rank_eligible`과 `feature_eligible`을 분리한다. `LIMITED` 종목은 Feature 계산은 허용하면서 Signal 후보 ranking에서는 제외하는 정책이 가능하다.

---

## 22. 상태 결정 알고리즘

```python
def evaluate_investability(ctx, instrument):
    e32 = ctx.eligibility[instrument.security_id]

    if e32.status == "EXCLUDED":
        return non_investable("ENGINE32_EXCLUDED")

    if e32.status == "WATCH_ONLY":
        return non_investable("ENGINE32_WATCH_ONLY")

    validate_temporal_integrity(ctx, instrument)

    tradability = evaluate_tradability(ctx, instrument)
    if tradability.hard_block:
        return non_investable(*tradability.reasons)

    event_state = evaluate_event_risk(ctx, instrument)
    if event_state.hard_block:
        return non_investable(*event_state.reasons)

    liquidity = compute_liquidity_metrics(ctx, instrument)
    capacity = compute_capacity(ctx, instrument, liquidity)
    data_quality = evaluate_data_quality(ctx, instrument)

    score = calculate_investability_score(
        liquidity=liquidity,
        capacity=capacity,
        event_state=event_state,
        data_quality=data_quality,
    )

    if score < ctx.policy.non_investable_score:
        state = "NON_INVESTABLE"
    elif score < ctx.policy.investable_score:
        state = "LIMITED"
    else:
        state = "INVESTABLE"

    return finalize_result(
        instrument=instrument,
        state=state,
        capacity=capacity,
        score=score,
    )
```

---

## 23. Capacity 알고리즘

```python
def compute_capacity(ctx, instrument, liquidity):
    adv_capacity = (
        liquidity.adv20_krw
        * ctx.policy.max_adv_participation
    )

    float_capacity = (
        instrument.free_float_market_cap_krw
        * ctx.policy.max_free_float_position
    )

    normal = min(adv_capacity, float_capacity)

    stressed_adv = (
        liquidity.adv20_krw
        * ctx.liquidity_stress_multiplier
    )

    stressed = min(
        stressed_adv * ctx.policy.max_adv_participation,
        float_capacity,
    )

    weight = min(
        stressed / ctx.portfolio_nav,
        ctx.policy.single_name_cap,
    )

    return CapacityResult(
        normal_capacity_krw=normal,
        stressed_capacity_krw=stressed,
        portfolio_capacity_weight=weight,
    )
```

---

## 24. Snapshot 생성 알고리즘

```python
def build_investable_universe(ctx):
    validate_frozen_inputs(ctx)

    results = []

    for security_id in sorted(ctx.eligibility.security_ids):
        result = evaluate_investability(
            ctx,
            ctx.instruments[security_id],
        )
        results.append(result)

    validate_universe_completeness(results)

    return finalize_immutable_snapshot(
        run_id=ctx.run_id,
        results=results,
        source_snapshot_id=ctx.eligibility_snapshot_id,
    )
```

정렬과 tie policy를 고정하여 동일 입력의 hash가 항상 같아야 한다.

---

## 25. 코드 구조

```text
investability/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── eligibility.py
│   ├── instrument_master.py
│   ├── market_data.py
│   ├── corporate_actions.py
│   ├── regime.py
│   ├── stress.py
│   └── portfolio.py
│
├── temporal.py
├── tradability.py
├── listing_age.py
├── event_risk.py
├── data_quality.py
│
├── liquidity/
│   ├── adv.py
│   ├── turnover.py
│   ├── free_float.py
│   └── continuity.py
│
├── capacity/
│   ├── normal.py
│   ├── stress.py
│   └── portfolio_weight.py
│
├── scoring.py
├── state_machine.py
├── completeness.py
├── snapshots.py
├── replay.py
├── survivorship.py
│
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 26. 주요 Reason Codes

```text
ENGINE32_EXCLUDED
ENGINE32_WATCH_ONLY

TRADING_SUSPENDED
LIQUIDATION_TRADING
DELISTING_IN_PROGRESS
NO_EXECUTABLE_MARKET

IPO_TOO_RECENT
IPO_HISTORY_LIMITED
RECENT_RELISTING
RECENT_TRADING_RESUMPTION

CORPORATE_ACTION_UNRESOLVED
POST_CORPORATE_ACTION_LIMITED

ADV_INSUFFICIENT
TURNOVER_INSUFFICIENT
FREE_FLOAT_INSUFFICIENT
TRADING_CONTINUITY_LOW

NORMAL_CAPACITY_LOW
STRESSED_CAPACITY_LOW
PORTFOLIO_CAPACITY_BINDING

ABNORMAL_SPREAD
EXTREME_GAP
PRICE_LIMIT_LOCK_RISK

CRITICAL_MARKET_DATA_MISSING
DATA_QUALITY_DEGRADED

INVESTABLE
INVESTABILITY_LIMITED
NON_INVESTABLE

CURRENT_INVESTABILITY_IN_HISTORICAL_REPLAY
SURVIVORSHIP_BIAS_GUARD
FUTURE_INFORMATION_GUARD
```

---

## 27. 테스트 계획

### Unit Tests

```text
A. Engine32 EXCLUDED
→ 64 NON_INVESTABLE

B. Engine32 WATCH_ONLY
→ 신규진입 NON_INVESTABLE

C. 거래정지
→ NON_INVESTABLE

D. IPO 10일
→ NON_INVESTABLE

E. IPO 35일
→ LIMITED

F. IPO 80일 + 정상 유동성
→ 일반 investability 평가

G. ADV20 50억원, participation 1%
→ ADV capacity 5천만원

H. Free float capacity가 ADV capacity보다 작음
→ 더 작은 값 binding

I. RISK_OFF liquidity multiplier 0.35
→ stressed capacity 감소

J. NAV 1천만원 / stressed capacity 60만원
→ portfolio capacity <= 6%

K. unresolved split
→ NON_INVESTABLE

L. split resolved + history 부족
→ LIMITED
```

### PIT / Bias Tests

```text
M. 2024 snapshot에 2026 investability 사용
→ BLOCK

N. 현재 delisted 종목이 2024 당시 정상 상장
→ 2024 snapshot 포함 가능

O. decision cutoff 이후 거래정지 정보
→ 기존 snapshot 소급 수정 금지

P. 미래 corporate action을 과거 investability에 사용
→ BLOCK
```

### Integration Tests

```text
Q. 32 ELIGIBLE 1,800종목
→ 64 INVESTABLE 1,200 / LIMITED 300 / NON 300
→ 합계 정확히 1,800

R. 64 snapshot 일부 누락
→ FINALIZED 금지

S. 64 INVESTABLE만 rank_eligible
→ 63 cross-sectional universe와 정확히 일치

T. LIMITED는 feature_eligible=True, rank_eligible=False 정책
→ 63 feature 계산 가능 / 42 candidate 제외

U. 동일 Input + Policy + cutoff
→ 동일 member states
→ 동일 capacity
→ 동일 snapshot hash
```

### Failure Injection

```text
Market data snapshot stale
Corporate action feed missing
Free-float missing
ADV history missing
Engine32 hash mismatch
Configuration hash mismatch
Clock skew
Duplicate security ID
```

Critical 입력의 상태를 모르면 `INVESTABLE`로 추정하지 않는다.

```text
UNKNOWN != INVESTABLE
```

---

## 28. 핵심 불변식

```text
32 EXCLUDED → 64 INVESTABLE = 0
32 WATCH_ONLY → 신규 risk allowed = 0

거래정지 → 신규 BUY capacity > 0 = 0
상장폐지 진행 → 신규 BUY capacity > 0 = 0

Unresolved Corporate Action → INVESTABLE = 0

미래 거래상태 사용 = 0
미래 Corporate Action 사용 = 0
현재 Universe 과거 소급 = 0
Survivorship Bias = 0

Unknown Critical State → INVESTABLE = 0

stressed_capacity > normal_capacity = 0
portfolio_capacity_weight > single_name_cap = 0

Historical Snapshot mutation = 0

Same inputs
+ Same policy
+ Same cutoff
→ Same member state
→ Same capacity
→ Same universe hash
```

---

## 29. Engine 63과의 계약

63은 자체적으로 상장종목 목록을 만들지 않는다.

```text
64 INVESTABLE
→ Feature + Ranking 대상

64 LIMITED
→ 정책에 따라 Feature 계산은 가능
→ 신규 Candidate Ranking은 기본 제외

64 NON_INVESTABLE
→ 신규 Candidate Feature Serving 차단
```

기본 계약:

```python
FeatureMaterializationRequest(
    investable_universe_snapshot_id=..., 
    feature_set_id=...,
    evaluation_time=...,
)
```

이를 통해 `현재 종목목록을 직접 조회하는 Feature Store`를 금지한다.

---

## 30. 32 → 64 → 63 → 42의 의미

```text
32 Universe Eligibility
"평가해도 되는 종목인가?"
        ↓
64 Investability
"지금 실제 신규 위험을 받을 수 있는 종목인가?"
        ↓
63 PIT Feature Store
"그 종목의 당시 Feature는 무엇인가?"
        ↓
42 Signal Integration
"그중 실제로 무엇이 좋은 후보인가?"
```

이 구조가 완성되면 ADE는 더 이상 소수 대형주를 사람이 먼저 고른 뒤 분석하지 않는다.

```text
KRX 전체 상장종목
→ 32 평가가능 Universe
→ 64 실제 Investable Universe
→ 63 전체 PIT Feature
→ 42 Cross-sectional Alpha / Confidence / Ranking
→ 54 Risk Governor
→ 44 Portfolio Construction
→ BUY / NO_ACTION
```

즉 Engine 64는 **종목 발굴 파이프라인의 실행가능성 경계**다.

---

## 31. 구현 우선순위

### Phase 1 — Tradability

```text
32 snapshot ingestion
Trading suspension
Listing status
Product type
Corporate action unresolved
```

### Phase 2 — Liquidity

```text
ADV20
Median turnover20
Valid trading days
Free-float market cap
```

### Phase 3 — Capacity

```text
ADV participation cap
Free-float cap
Portfolio NAV-relative capacity
```

### Phase 4 — Event windows

```text
IPO
Relisting
Split/Merger/Spin-off
Trading resume
```

### Phase 5 — PIT Snapshot

```text
Investable Universe Snapshot
63 Feature Store integration
Historical replay tests
```

최소 구현으로 Phase 1~3만 완료해도 KOSPI/KOSDAQ 전체 종목 중 실제 feature/ranking에 넣을 종목 집합을 자동 확정할 수 있다.

---

## 32. 완료 기준

Engine 64 v1은 다음이 만족될 때 완료로 본다.

```text
1. Engine32 FINALIZED snapshot을 입력으로 사용
2. 전체 member에 investability state 100% 부여
3. Hard Tradability Gate 구현
4. ADV/free-float 기반 Capacity 구현
5. PIT cutoff 준수
6. Historical survivorship test 통과
7. Immutable Universe Snapshot 생성
8. Engine63가 snapshot_id로만 universe를 소비
9. 동일 입력 deterministic hash 검증
10. NON_INVESTABLE 종목이 Candidate path에 유입되는 사례 0건
```
