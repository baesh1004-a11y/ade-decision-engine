# 46. Execution Simulation, Fill Probability & Execution Quality Engine v1

## 1. 목적

Execution Simulation, Fill Probability & Execution Quality Engine은 ADE가 생성한 주문 의도를 PAPER/BACKTEST/SHADOW 환경에서 실제 시장 체결에 가까운 방식으로 시뮬레이션하고, 주문별 체결확률·부분체결·평균체결가·체결지연·미체결·실행품질을 결정론적으로 산출한다.

34번 Transaction Cost, Slippage & Market Impact Engine이 **거래비용의 크기**를 추정한다면, 46번 엔진은 **주문이 언제, 얼마나, 어떤 가격에 체결되는가**를 담당한다.

본 엔진의 핵심 목표는 다음 오류를 방지하는 것이다.

- 모든 주문이 100% 즉시 체결된다고 가정하는 오류
- 지정가 주문이 단순히 당일 저가/고가를 통과했다는 이유만으로 전량 체결됐다고 가정하는 오류
- 장 마감 후 생성된 주문을 같은 날 종가에 체결하는 look-ahead 오류
- 거래정지·상하한가·호가 공백에서 허위 체결을 생성하는 오류
- 부분체결과 잔량 취소를 무시하는 오류
- 주문 체결가격과 비용 모델의 기준가격을 혼합하는 오류
- 백테스트와 PAPER에서 서로 다른 체결 규칙을 사용해 재현성이 깨지는 오류

본 엔진은 투자 방향이나 종목선택을 생성하지 않는다. 주문승인 이후의 실행상태만 모델링한다.

---

## 2. 책임 경계

### 2.1 수행 책임

1. 실행 가능 세션과 최초 허용 체결시점 결정
2. 주문 유형별 체결 규칙 적용
3. 시장가·지정가·MOC·LOC 주문의 체결 시뮬레이션
4. 주문가격과 시장가격 관계에 따른 fill probability 산출
5. 부분체결·잔량·취소·만료 상태 생성
6. 유동성·거래량·스프레드·변동성 기반 최대 체결수량 제한
7. 34번 엔진의 비용/시장충격 모델과 결합한 체결가격 조정
8. 주문별 arrival price, VWAP fill price, implementation shortfall 계산
9. PAPER/BACKTEST/SHADOW 공통 실행 계약 제공
10. 실행 결과와 입력 lineage/hash 보존

### 2.2 수행하지 않는 책임

- BUY/SELL 방향 결정
- 목표비중 결정
- 브로커에 실제 주문 제출
- 실계좌 체결 정합성 복구
- 거래비용 정책 자체의 계산
- 포트폴리오 회계 원장 확정

실주문 전송은 24번 Order Validation & Routing, 실체결 정합성은 25번 Execution Reconciliation & Recovery가 담당한다.

---

## 3. 상위 아키텍처

```text
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
24 Order Validation / Routing
        ↓
┌───────────────────────────────────────┐
│ 46 Execution Simulation Engine        │
├───────────────────────────────────────┤
│ Execution-Time Guard                  │
│ Session Resolver                      │
│ Order-Type Simulator                  │
│ Fill Probability Model                │
│ Volume / Liquidity Capacity           │
│ Partial Fill Allocator                │
│ Price Formation                       │
│ Cost / Impact Integration (34)        │
│ Execution Quality Analyzer            │
│ Evidence / Hash Publisher             │
└───────────────────────────────────────┘
        ↓
Simulated Fill Events
        ↓
31 Paper Trading Continuity
19 Portfolio Accounting
30 Explainability
12 Reporting
```

---

## 4. 핵심 원칙: Decision Time과 Execution Time 분리

장 마감 후 EOD 전략의 핵심 불변식은 다음이다.

```text
decision_time < first_allowed_execution_time
```

예:

```text
2026-08-14 15:40  EOD 데이터 확정
2026-08-14 16:00  Signal/Decision 생성
2026-08-18 09:00  다음 거래일 최초 체결 가능
```

따라서 장 마감 후 생성된 BUY를 8월 14일 종가로 체결하는 것은 금지한다.

```text
SAME_BAR_EXECUTION_AFTER_DECISION = 0
```

---

## 5. 입력 계약

```python
@dataclass(frozen=True)
class ExecutionSimulationRequest:
    execution_run_id: str
    order_id: str
    portfolio_id: str
    instrument_id: str

    side: str                  # BUY | SELL
    order_type: str            # MARKET | LIMIT | MOC | LOC
    time_in_force: str         # DAY | IOC | FOK
    quantity: int
    limit_price: Decimal | None

    decision_time: datetime
    approved_time: datetime
    earliest_execution_time: datetime

    market_snapshot_id: str
    liquidity_snapshot_id: str
    cost_estimate_id: str | None
    policy_snapshot_id: str
```

필수 시장 입력:

- 거래 캘린더
- 거래정지 여부
- 상하한가 상태
- 체결 가능한 가격계열
- 세션별 OHLCV 또는 intraday bars
- best bid/ask가 있으면 해당 quote
- 거래량/거래대금
- 20일 ADV/median volume
- 최소 호가단위
- 변동성

---

## 6. 출력 계약

```python
@dataclass(frozen=True)
class SimulatedExecutionResult:
    execution_id: str
    order_id: str
    status: str
    requested_quantity: int
    filled_quantity: int
    remaining_quantity: int

    arrival_price: Decimal | None
    average_fill_price: Decimal | None
    gross_notional: Decimal

    estimated_cost: Decimal
    implementation_shortfall: Decimal | None
    realized_slippage_bps: Decimal | None

    first_fill_time: datetime | None
    last_fill_time: datetime | None
    fill_ratio: Decimal

    reason_codes: tuple[str, ...]
    policy_version: str
    input_hash: str
    result_hash: str
```

`status`:

```text
FILLED
PARTIALLY_FILLED
NOT_FILLED
CANCELLED
EXPIRED
BLOCKED
```

---

## 7. Order State Machine

```text
CREATED
   ↓
APPROVED
   ↓
WAITING_FOR_SESSION
   ↓
ACTIVE
   ├─→ FILLED
   ├─→ PARTIALLY_FILLED
   │      ↓
   │   ACTIVE / EXPIRED / CANCELLED
   ├─→ NOT_FILLED
   └─→ BLOCKED
```

모든 상태전이는 append-only event로 저장한다.

---

## 8. 시장가 주문 시뮬레이션

시장가 주문은 `earliest_execution_time` 이후 첫 유효 거래구간에서 체결 대상으로 간주한다.

### 8.1 기본 기준가격

intraday quote 존재 시:

```text
BUY  → best_ask 또는 executable ask ladder
SELL → best_bid 또는 executable bid ladder
```

quote가 없고 다음 거래일 일봉만 존재하는 EOD 백테스트에서는 기본값을 다음처럼 둔다.

```text
reference = next_session_open
```

그리고 34번의 spread/slippage/impact 비용을 방향성 있게 적용한다.

```text
BUY_fill_price
= reference × (1 + execution_cost_bps / 10,000)

SELL_fill_price
= reference × (1 - execution_cost_bps / 10,000)
```

단, 거래세·수수료 같은 명시적 비용은 가격에 중복 반영하지 않고 별도 cash cost로 유지한다.

---

## 9. 지정가 주문 시뮬레이션

단순 규칙:

```text
BUY LIMIT
market_price <= limit_price
→ 체결 가능

SELL LIMIT
market_price >= limit_price
→ 체결 가능
```

그러나 `당일 저가 <= 매수 지정가`만으로 전량체결을 확정하지 않는다.

체결가능성은 다음 요소를 사용한다.

```text
price_cross_depth
available_volume
order_participation
spread
volatility
session_location
```

초기 결정론적 fill score:

```text
fill_score
= price_cross_score
× liquidity_score
× participation_score
× session_score
```

결과:

```text
fill_score >= 0.80 → 최대 허용수량까지 체결
0.50~0.80          → 부분체결
0.20~0.50          → 보수적 소량 체결
< 0.20              → NOT_FILLED
```

정책 임계치는 policy snapshot으로 관리한다.

---

## 10. 가격 관통 정도

BUY LIMIT 예:

```text
limit = 100,000
bar_low = 98,000
bar_vwap_proxy = 99,200
```

지정가가 단순히 저가에 닿은 경우보다 VWAP 근처 또는 그 위로 충분히 관통된 경우 fill probability를 높인다.

```text
cross_depth
= max(0, limit_price - market_reference)
  / max(tick_size, intrabar_range)
```

SELL은 반대 방향으로 계산한다.

---

## 11. Volume Capacity

한 주문이 해당 구간 거래량을 과도하게 소비할 수 없다.

```text
max_fill_quantity
= floor(bar_volume × max_bar_participation)
```

초기 PAPER 정책 예:

```text
max_bar_participation = 5%
max_daily_participation = 1% of ADV20
```

최종 허용수량:

```text
fillable_qty
= min(
    remaining_qty,
    bar_capacity,
    daily_capacity,
    liquidity_cap_from_engine_34
)
```

---

## 12. 부분체결

예:

```text
주문수량 100주
첫 bar 허용 30주
두 번째 bar 허용 25주
세 번째 bar 허용 20주
```

결과:

```text
filled = 75
remaining = 25
status = PARTIALLY_FILLED
```

DAY 주문이면 장 종료 시 잔량을 `EXPIRED`로 전환한다.

IOC:

```text
첫 실행기회에서 가능한 수량만 체결
잔량 즉시 CANCELLED
```

FOK:

```text
전량 즉시 체결 가능하지 않으면 0주 체결
```

---

## 13. Fill Event

한 주문은 여러 체결 이벤트를 가질 수 있다.

```python
@dataclass(frozen=True)
class SimulatedFillEvent:
    fill_id: str
    order_id: str
    execution_id: str
    fill_time: datetime
    quantity: int
    raw_market_price: Decimal
    fill_price: Decimal
    explicit_cost: Decimal
    implicit_cost: Decimal
    market_impact_bps: Decimal
    liquidity_used: Decimal
    market_snapshot_id: str
```

평균체결가:

```text
VWAP_fill
= Σ(fill_price × fill_qty)
  / Σ(fill_qty)
```

---

## 14. Gap 처리

전일 장마감 후 BUY 결정 후 다음날 +8% gap-up이 발생하면 전일 종가로 체결하지 않는다.

```text
Decision reference = previous close
Execution reference = next open
```

따라서 gap은 실제 실행손익에 반영된다.

```text
GAP_AFTER_DECISION_CAPTURED
```

반대로 SELL도 gap-down을 그대로 반영한다.

---

## 15. 상하한가 / 거래정지

### 거래정지

```text
TRADING_HALT
→ fill_quantity = 0
→ status = BLOCKED
```

### 매수 주문 + 상한가 잠김

매도호가/체결가능 유동성이 없으면:

```text
LIMIT_UP_NO_LIQUIDITY
→ NOT_FILLED
```

### 매도 주문 + 하한가 잠김

매수호가가 없으면:

```text
LIMIT_DOWN_NO_LIQUIDITY
→ NOT_FILLED
```

일봉의 종가만 보고 강제로 체결하지 않는다.

---

## 16. MOC / LOC

MOC는 해당 시장과 데이터가 종가 auction을 충분히 표현할 때만 정밀 시뮬레이션한다.

그렇지 않으면:

```text
MOC_PROXY_MODE
```

로 표시하고 확정 종가 + 정책상 auction slippage proxy를 사용한다.

LOC는 종가가 limit 조건을 충족하고 auction liquidity가 충분한 경우에만 체결한다.

---

## 17. Execution Quality

주문 체결 후 다음 지표를 계산한다.

### Arrival Slippage

```text
BUY:
(fill_vwap - arrival_price) / arrival_price × 10,000

SELL:
(arrival_price - fill_vwap) / arrival_price × 10,000
```

### Implementation Shortfall

BUY 기준:

```text
implementation_shortfall
= filled_qty × (fill_price - decision_reference_price)
+ explicit_cost
+ opportunity_cost_of_unfilled_qty
```

SELL은 방향을 반대로 계산한다.

### Fill Ratio

```text
fill_ratio = filled_quantity / requested_quantity
```

### Time to Fill

```text
time_to_first_fill
time_to_complete_fill
```

---

## 18. 미체결 Opportunity Cost

부분체결 또는 미체결이 항상 비용 0을 의미하지 않는다.

예:

```text
BUY 100주 주문
40주만 체결
이후 가격 +10% 상승
```

60주의 미체결에는 opportunity cost가 존재한다.

```text
opportunity_cost
= unfilled_qty
× adverse_price_move
```

이는 실제 현금비용과 분리하여 분석용으로만 저장한다.

---

## 19. 34번 엔진과의 관계

```text
34 Cost Engine
→ spread/slippage/impact estimate
→ cost budget / liquidity cap

46 Execution Engine
→ 언제 체결?
→ 몇 주 체결?
→ 어떤 가격 체결?
→ 부분체결 여부?
→ 실행품질은?
```

46번은 34번 비용을 호출하거나 참조할 수 있지만, 명시적 비용을 중복 계산하지 않는다.

---

## 20. PAPER / BACKTEST / SHADOW 모드

### BACKTEST

```text
historical bars only
future bar 사용 금지
deterministic fill simulation
```

### PAPER

```text
실시간 또는 지연 시세
가상 주문
실제 브로커 제출 없음
```

### LIVE_SHADOW

```text
실제 주문/체결 이벤트를 관찰
46번 예상체결과 실제체결 비교
모델 보정 데이터 생성
```

동일 입력 snapshot과 정책이면 BACKTEST/PAPER에서 동일한 결정론적 결과를 낼 수 있어야 한다.

---

## 21. 데이터베이스

주요 테이블:

```text
execution_simulation_policies
execution_simulation_runs
simulated_orders
simulated_order_state_events
simulated_fill_events
execution_quality_results
execution_reason_events
execution_snapshot_manifests
```

### execution_simulation_policies

```text
policy_id
version
effective_from
effective_to
known_at

market_order_reference_mode
max_bar_participation
max_daily_participation
limit_fill_threshold_full
limit_fill_threshold_partial
partial_fill_fraction

allow_moc_proxy
allow_quote_proxy

created_at
policy_hash
```

### execution_simulation_runs

```text
run_id
evaluation_time
mode
policy_id
market_snapshot_id
status
input_hash
output_hash
created_at
finalized_at
```

### simulated_orders

```text
execution_id
order_id
instrument_id
side
order_type
time_in_force
requested_qty
filled_qty
remaining_qty
status
arrival_price
average_fill_price
first_fill_time
last_fill_time
result_hash
```

### simulated_fill_events

```text
fill_id
execution_id
sequence_no
fill_time
quantity
raw_market_price
fill_price
explicit_cost
implicit_cost
impact_bps
market_snapshot_id
fill_hash
```

### execution_quality_results

```text
execution_id
decision_reference_price
arrival_price
fill_vwap
arrival_slippage_bps
implementation_shortfall
opportunity_cost
fill_ratio
time_to_first_fill_ms
time_to_complete_fill_ms
quality_status
```

---

## 22. Index / Constraint 권장

```sql
CREATE UNIQUE INDEX uq_sim_fill_sequence
ON simulated_fill_events(execution_id, sequence_no);

CREATE INDEX ix_sim_order_status
ON simulated_orders(status, instrument_id);

CREATE INDEX ix_execution_run_time
ON execution_simulation_runs(evaluation_time, mode);
```

불변식:

```text
filled_qty + remaining_qty = requested_qty
filled_qty >= 0
remaining_qty >= 0
fill_event.quantity > 0
Σ fill_event.quantity = simulated_orders.filled_qty
```

---

## 23. 코드 구조

```text
execution_simulation/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── orders.py
│   ├── market_data.py
│   ├── trading_calendar.py
│   ├── liquidity.py
│   └── transaction_cost.py
│
├── temporal.py
├── sessions.py
├── market_state.py
├── capacity.py
├── fill_probability.py
├── partial_fill.py
├── price_formation.py
│
├── simulators/
│   ├── market.py
│   ├── limit.py
│   ├── moc.py
│   └── loc.py
│
├── time_in_force.py
├── state_machine.py
├── quality.py
├── opportunity_cost.py
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 24. 핵심 알고리즘

```python
def simulate_execution(ctx):
    order = validate_order(ctx.order)
    policy = resolve_policy(ctx.policy_snapshot_id)

    assert order.decision_time < order.earliest_execution_time

    market = load_market_after(
        instrument_id=order.instrument_id,
        start=order.earliest_execution_time,
    )

    if market.is_trading_halted:
        return blocked("TRADING_HALT")

    cost_model = load_cost_estimate(order.cost_estimate_id)

    state = ExecutionState(order=order)

    for bar in eligible_bars(market, order, policy):
        if state.remaining_qty == 0:
            break

        if not is_price_executable(order, bar):
            continue

        probability = compute_fill_score(order, bar, policy)
        capacity = compute_fill_capacity(order, bar, policy, cost_model)

        fill_qty = allocate_fill_quantity(
            remaining=state.remaining_qty,
            score=probability,
            capacity=capacity,
            tif=order.time_in_force,
        )

        if fill_qty <= 0:
            continue

        raw_price = executable_reference_price(order, bar)
        fill_price = apply_implicit_execution_cost(
            side=order.side,
            price=raw_price,
            cost_model=cost_model,
            quantity=fill_qty,
        )

        state.add_fill(
            time=bar.time,
            quantity=fill_qty,
            raw_price=raw_price,
            fill_price=fill_price,
        )

        if order.time_in_force == "IOC":
            break

    state = apply_time_in_force_completion(state, order, market)
    quality = analyze_execution_quality(state, order, market)

    validate_execution_invariants(state)
    return finalize_execution_snapshot(state, quality)
```

---

## 25. 결정론적 Fill Probability

v1은 난수 기반 Monte Carlo를 기본으로 사용하지 않는다.

이유:

```text
동일 입력 → 동일 결과
백테스트 재현성
설명가능성
정책 비교 용이성
```

초기 score 예:

```text
price_cross_score     40%
liquidity_score       25%
participation_score   20%
session_score         15%
```

향후 v2에서 확률모델/ML을 도입하더라도 seed와 model snapshot을 고정해야 한다.

---

## 26. Reason Codes

```text
EXECUTION_TIME_NOT_REACHED
SAME_BAR_EXECUTION_BLOCKED
TRADING_HALT
LIMIT_UP_NO_LIQUIDITY
LIMIT_DOWN_NO_LIQUIDITY
MARKET_DATA_MISSING
QUOTE_DATA_MISSING
QUOTE_PROXY_USED
MOC_PROXY_MODE

PRICE_NOT_CROSSED
LOW_FILL_PROBABILITY
LIQUIDITY_CAP_BINDING
BAR_PARTICIPATION_CAP
DAILY_PARTICIPATION_CAP

PARTIAL_FILL
IOC_REMAINDER_CANCELLED
FOK_NOT_FILLED
DAY_ORDER_EXPIRED

GAP_AFTER_DECISION_CAPTURED
EXECUTION_COST_APPLIED

EXECUTION_QUALITY_GOOD
EXECUTION_QUALITY_DEGRADED
HIGH_IMPLEMENTATION_SHORTFALL
HIGH_OPPORTUNITY_COST

FUTURE_BAR_GUARD
INPUT_SNAPSHOT_MISMATCH
POLICY_SNAPSHOT_MISMATCH
```

---

## 27. 테스트 계획

### A. EOD BUY의 다음 거래일 체결

```text
금요일 16:00 Decision
월요일 휴장
화요일 09:00 Open
→ 화요일 이전 체결 0건
```

### B. Same-bar look-ahead 차단

```text
15:40 종가 확정 후 Decision
→ 당일 15:30 종가 체결 금지
```

### C. Market BUY gap-up

```text
전일 close 100
다음날 open 108
→ 100 체결 금지
→ 108 + implicit cost 기준
```

### D. Market SELL gap-down

```text
전일 close 100
다음날 open 92
→ 92 기반 체결
```

### E. BUY LIMIT 미도달

```text
limit 100
bar low 101
→ NOT_FILLED
```

### F. BUY LIMIT 경미 접촉

```text
limit 100
bar low 99.9
거래량 매우 적음
→ 전량체결 금지
→ partial 또는 not filled
```

### G. 충분한 관통 + 충분한 거래량

```text
limit 100
bar VWAP 98.5
volume 충분
→ 높은 fill ratio
```

### H. 거래량 제한

```text
order 10,000주
bar capacity 500주
→ 한 bar 최대 500주
```

### I. DAY 부분체결

```text
1,000주 주문
장중 700주 체결
→ 300주 EXPIRED
```

### J. IOC

```text
500주 주문
즉시 가능 120주
→ 120주 fill
→ 380주 CANCELLED
```

### K. FOK

```text
500주 전량 즉시 불가능
→ fill 0
```

### L. 거래정지

```text
halted = true
→ fill 0
```

### M. 상한가 잠김 BUY

```text
매도 유동성 0
→ fill 0
```

### N. 하한가 잠김 SELL

```text
매수 유동성 0
→ fill 0
```

### O. 비용 중복 방지

```text
34번 commission = 1,000원
→ 46번 fill price에 commission을 가격슬리피지로 중복 반영 금지
```

### P. Fill 합계 정합성

```text
fill events 합계 = filled_quantity
```

### Q. 미래 bar 사용 차단

```text
execution_time 이후 데이터만 사용
과거 decision 계산에 미래 fill 정보 유입 0건
```

### R. 동일 입력 재실행

```text
동일 order + market snapshot + policy
→ 동일 fill events
→ 동일 average price
→ 동일 result hash
```

### S. Corporate Action

```text
액면분할 후 실제 execution price는 raw tradable price 사용
adjusted historical price로 주문 체결 금지
```

### T. Opportunity Cost

```text
100주 BUY
40주 fill
60주 unfilled
이후 가격 급등
→ opportunity_cost > 0
```

---

## 28. 통합 테스트

```text
42 ELIGIBLE Candidate
→ 44 target 8%
→ 45 ENTER
→ 23 BUY 8주
→ 24 APPROVED
→ 46 PARTIAL_FILL 5주
→ 31 paper portfolio에는 5주만 반영
→ 19 cash ledger에는 실제 simulated fill cost만 반영
```

절대로 승인수량 8주 전체를 보유수량으로 기록하지 않는다.

또한:

```text
46 NOT_FILLED
→ 포트폴리오 position 생성 금지
```

---

## 29. 핵심 불변식

```text
미래 bar 사용 = 0
Decision 이전 fill = 0
장마감 후 Decision의 same-close fill = 0

거래정지 상태 fill = 0
체결가능 유동성 없는 상하한가 fill = 0

filled_qty > requested_qty = 0
음수 fill quantity = 0
fill event 합계 불일치 = 0

명시적 비용 중복 반영 = 0
adjusted price를 실제 체결가격으로 사용 = 0

NOT_FILLED 주문의 position 생성 = 0
PARTIAL_FILL 주문의 전체수량 position 반영 = 0

동일 입력 + 동일 정책
→ 동일 fill sequence
→ 동일 average_fill_price
→ 동일 quality result
→ 동일 hash
```

---

## 30. 구현 순서

```text
1. Immutable execution models/enums
2. DB migration
3. Trading calendar / session resolver
4. Temporal guard
5. Market order simulator
6. Limit order executable check
7. Volume capacity
8. Partial fill allocator
9. Time-in-force
10. 34 Cost Engine integration
11. Execution quality metrics
12. Reason codes / evidence / hashing
13. Unit tests
14. E2E Paper Trading integration test
15. LIVE_SHADOW calibration dataset
```

---

## 31. ADE 전체에서의 위치

```text
34 Transaction Cost Engine
"이 주문의 비용은 얼마나 드는가?"

44 Portfolio Construction
"얼마나 보유해야 하는가?"

45 Trade Lifecycle
"진입/보유/축소/청산 중 무엇을 해야 하는가?"

23 Decision / Sizing
"몇 주를 주문할 것인가?"

24 Order Validation
"이 주문을 제출해도 되는가?"

46 Execution Simulation
"실제로 몇 주가 언제 어떤 가격에 체결되는가?"

25 Execution Reconciliation
"실체결과 내부 상태가 일치하는가?"

19 Portfolio Accounting
"체결 이후 NAV와 손익은 얼마인가?"
```

46번 엔진이 추가됨으로써 ADE 백테스트와 모의투자는 더 이상 `신호 발생 → 종가 전량체결`이라는 비현실적 가정을 사용하지 않고, 주문의 실행 가능성·부분체결·gap·유동성·미체결 비용까지 재현 가능한 방식으로 모델링할 수 있다.
