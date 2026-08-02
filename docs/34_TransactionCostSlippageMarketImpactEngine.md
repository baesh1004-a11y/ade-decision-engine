# 34. Transaction Cost, Slippage & Market Impact Engine v1

## 1. 목적

Transaction Cost, Slippage & Market Impact Engine은 주문 또는 가상체결에 수반되는 명시적·암묵적 거래비용을 시점 정합성이 있는 정책과 시장 데이터에 따라 결정론적으로 추정하고, 사전 비용 예상치와 사후 실현 비용을 분리하여 제공한다.

핵심 목적은 다음 오류를 방지하는 것이다.

- 수수료·거래세를 누락해 백테스트와 PAPER 성과가 과대평가되는 오류
- 모든 주문이 종가 또는 중간가격에 무충격 체결된다고 가정하는 오류
- 저유동성 종목에 대규모 주문을 허용하면서 시장충격을 무시하는 오류
- 매수·매도, 시장·지정가, 장중·종가 주문의 비용 구조를 동일하게 처리하는 오류
- 현재의 세율·수수료 정책을 과거 거래일에 소급 적용하는 오류
- 예상 비용과 실제 체결 비용을 혼합하여 모델 보정과 성과 귀속이 왜곡되는 오류

본 엔진은 투자 신호나 BUY/SELL 판단을 생성하지 않는다. Decision, Risk, Order, Backtest, Paper Trading, Portfolio Accounting에 비용 추정치·제약 위반·사후 비용 분석 결과를 제공한다.

---

## 2. 책임 경계

### 2.1 수행 책임

1. 브로커 수수료, 거래세, 유관기관 비용 정책의 버전 관리
2. Bid-Ask spread, 주문 크기, 거래대금, 변동성에 기반한 슬리피지 추정
3. 주문 참여율과 시장충격 추정
4. 주문 유형·방향·세션별 비용 모델 선택
5. 사전 예상 비용과 사후 실현 비용 분리
6. 비용 한도 초과 주문의 축소 또는 차단 요청
7. 비용 모델 입력·출력·정책·데이터 lineage와 hash 생성
8. PAPER·BACKTEST·LIVE_SHADOW 간 동일 계약 제공
9. 모델 오차와 비용 드리프트 측정

### 2.2 수행하지 않는 책임

- 투자 후보 선정
- 최종 주문 방향 결정
- 실제 브로커 주문 제출
- 미체결 주문 취소·정정
- 포트폴리오 현금 원장 확정
- 세법상 개인별 최종 납세액 계산
- 호가 데이터가 없을 때 근거 없는 정밀 추정

---

## 3. 상위 아키텍처

```text
Fee / Tax Policy
Broker Schedule
Market Quote / OHLCV / ADV
OrderIntent / Decision Approval
Execution Fill Evidence
             ↓
Transaction Cost Engine
   ├─ Policy Resolver
   ├─ Explicit Cost Calculator
   ├─ Spread Estimator
   ├─ Slippage Estimator
   ├─ Market Impact Model
   ├─ Participation Guard
   ├─ Cost Budget Resolver
   ├─ Post-trade Cost Analyzer
   └─ Evidence / Hash Publisher
             ↓
Pre-trade Cost Estimate
Cost-adjusted Quantity Limit
BLOCK / REDUCE / APPROVE
Post-trade Realized Cost
             ↓
Risk / Decision / Order Validation
Backtest / Paper Trading
Portfolio Accounting / Monitoring
Explainability / Report / Audit
```

---

## 4. 핵심 입력 계약

```python
@dataclass(frozen=True)
class CostEstimateRequest:
    run_id: str
    portfolio_id: str
    instrument_id: str
    side: str                 # BUY | SELL
    order_type: str           # MARKET | LIMIT | MOC | LOC
    quantity: int
    reference_price: Decimal
    limit_price: Decimal | None
    evaluation_time: datetime
    market_session: str
    policy_snapshot_id: str
    quote_snapshot_id: str | None
    liquidity_snapshot_id: str
    decision_id: str
    risk_approval_id: str
```

필수 시장 입력:

- 공식 또는 검증된 기준가격
- 최근 호가 스프레드 또는 대체 추정치
- 최근 20일 중앙 거래대금
- 최근 20일 중앙 거래량
- 당일 또는 최근 변동성
- 주문 금액과 예상 시장 참여율
- 가격 단위와 최소 호가단위

입력 데이터가 불완전한 경우 신뢰도를 명시적으로 낮추고 `ESTIMATE_DEGRADED` 또는 `COST_UNKNOWN_BLOCK`을 반환한다.

---

## 5. 출력 계약

```python
@dataclass(frozen=True)
class CostEstimate:
    estimate_id: str
    status: str               # APPROVED | REDUCED | BLOCKED | DEGRADED
    currency: str
    gross_notional: Decimal
    commission: Decimal
    exchange_fees: Decimal
    transaction_tax: Decimal
    estimated_half_spread: Decimal
    estimated_slippage: Decimal
    estimated_market_impact: Decimal
    total_estimated_cost: Decimal
    total_cost_bps: Decimal
    participation_rate: Decimal
    approved_quantity: int
    reason_codes: tuple[str, ...]
    model_version: str
    policy_hash: str
    input_hash: str
    result_hash: str
```

사후 분석 출력:

```python
@dataclass(frozen=True)
class RealizedCostAnalysis:
    fill_group_id: str
    arrival_price: Decimal
    volume_weighted_fill_price: Decimal
    explicit_cost: Decimal
    implementation_shortfall: Decimal
    realized_slippage_bps: Decimal
    realized_total_cost_bps: Decimal
    estimate_error_bps: Decimal
    analysis_status: str
```

---

## 6. 비용 구성요소

### 6.1 명시적 비용

```text
explicit_cost
= commission
+ exchange_fees
+ transaction_tax
+ 기타 정책상 확정 비용
```

정책은 `effective_from`, `effective_to`, `known_at`을 가진다. 과거 재현 시 다음을 강제한다.

```text
policy.known_at <= evaluation_time
policy.effective_from <= trade_date
policy.effective_to is null or trade_date <= policy.effective_to
```

### 6.2 스프레드 비용

호가가 존재하면:

```text
mid = (best_bid + best_ask) / 2
half_spread_bps = ((best_ask - best_bid) / 2) / mid × 10,000
```

매수는 ask 방향, 매도는 bid 방향으로 비용을 적용한다.

호가가 없으면 종목별 가격대·유동성 군집에 따른 보수적 대체 모델을 사용하되 `SPREAD_PROXY_USED`를 기록한다.

### 6.3 기본 슬리피지

초기 결정론적 모델:

```text
base_slippage_bps
= spread_component
+ volatility_coefficient × intraday_volatility_bps
+ urgency_coefficient × urgency_score
```

모든 계수는 정책 Snapshot에 저장하며 코드 상수로 숨기지 않는다.

### 6.4 시장 참여율

```text
order_value = quantity × reference_price
participation_rate = order_value / median_daily_trading_value_20d
```

정책 예시:

```text
participation_rate <= 0.5%   → 정상
0.5% < rate <= 2.0%          → 비용 증가·수량 축소 가능
2.0% < rate <= 5.0%          → HIGH_IMPACT
rate > 5.0%                  → 기본 BLOCK
```

수치는 정책화하며 전략별로 변경 가능하되 과거 run에는 소급하지 않는다.

### 6.5 시장충격

초기 square-root 모델:

```text
impact_bps
= impact_coefficient
× daily_volatility_bps
× sqrt(order_value / median_daily_trading_value_20d)
```

다음 조건에서는 계산을 차단한다.

- 거래대금이 0 또는 누락
- 기준가격이 0 이하
- 주문수량이 음수
- 변동성 값이 비정상
- 종목 거래정지

### 6.6 총 예상 비용

```text
total_estimated_cost
= explicit_cost
+ spread_cost
+ slippage_cost
+ market_impact_cost
```

```text
total_cost_bps
= total_estimated_cost / gross_notional × 10,000
```

---

## 7. 비용 예산과 주문 축소

Decision이 승인한 주문이라도 비용 예산을 초과하면 그대로 통과시키지 않는다.

```text
입력 승인수량
    ↓
예상 비용 계산
    ↓
비용 bps <= soft_limit
    → APPROVED

soft_limit < 비용 bps <= hard_limit
    → 수량 이분탐색
    → REDUCED

비용 bps > hard_limit 또는 입력 불확실
    → BLOCKED
```

수량 축소 알고리즘:

```python
def find_max_affordable_quantity(request, policy, market):
    lo = 0
    hi = request.quantity
    best = 0

    while lo <= hi:
        mid = (lo + hi) // 2
        estimate = estimate_cost(request.with_quantity(mid), policy, market)

        if estimate.total_cost_bps <= policy.hard_cost_limit_bps:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    return best
```

허용수량이 0주이면 `BLOCKED_COST_BUDGET`을 반환한다. 이를 임의의 `NO_ACTION`으로 변환하지 않는다.

---

## 8. 주문 유형별 처리

### MARKET

- spread와 시장충격을 모두 적용
- 긴급도 계수를 높게 적용
- 저유동성 종목은 보수적으로 차단

### LIMIT

- 지정가가 시장성 있는 경우 MARKET과 유사하게 평가
- 비시장성 지정가는 체결확률과 adverse selection을 별도 기록
- 미체결 위험은 비용이 0이라는 의미가 아님

### MOC / 종가 가상체결

- 공식 종가를 체결 기준가격으로 사용
- 당일 종가 경매 참여율 또는 거래대금 대비 주문비중 적용
- 호가 데이터가 없더라도 무비용 체결을 가정하지 않음

### PAPER / BACKTEST

- 실제 주문은 생성하지 않음
- RAW 가격에 추정 비용을 별도 원장 이벤트로 반영
- 조정주가를 체결가격으로 사용하지 않음

---

## 9. 사후 비용 분석

실제 또는 가상 fill 이후 다음을 계산한다.

```text
arrival_price = 주문 의사결정 확정 시점의 검증된 기준가격
VWAP_fill = Σ(fill_price × fill_qty) / Σ(fill_qty)
```

매수:

```text
implementation_shortfall
= (VWAP_fill - arrival_price) × quantity + explicit_cost
```

매도:

```text
implementation_shortfall
= (arrival_price - VWAP_fill) × quantity + explicit_cost
```

예상 오차:

```text
estimate_error_bps
= realized_total_cost_bps - estimated_total_cost_bps
```

이 결과는 Strategy Monitoring에 전달되어 모델 편향과 드리프트를 탐지한다.

---

## 10. 데이터베이스 설계

### 10.1 `transaction_cost_policies`

- `policy_id` PK
- `version`
- `market`
- `account_mode`
- `effective_from`
- `effective_to`
- `known_at`
- `soft_cost_limit_bps`
- `hard_cost_limit_bps`
- `max_participation_rate`
- `parameters_json`
- `policy_hash`
- `created_at`

### 10.2 `broker_fee_schedules`

- `schedule_id` PK
- `broker_id`
- `account_type`
- `market`
- `effective_from`
- `effective_to`
- `commission_rule_json`
- `minimum_fee`
- `source_ref`
- `schedule_hash`

### 10.3 `transaction_tax_schedules`

- `tax_schedule_id` PK
- `market`
- `instrument_type`
- `side`
- `effective_from`
- `effective_to`
- `rate`
- `source_ref`
- `schedule_hash`

### 10.4 `cost_estimate_runs`

- `estimate_run_id` PK
- `run_id`
- `request_id`
- `status`
- `model_version`
- `policy_snapshot_id`
- `market_snapshot_id`
- `started_at`
- `completed_at`
- `input_hash`
- `result_hash`

### 10.5 `cost_estimates`

- `estimate_id` PK
- `estimate_run_id` FK
- `instrument_id`
- `side`
- `requested_quantity`
- `approved_quantity`
- `gross_notional`
- `commission`
- `exchange_fees`
- `transaction_tax`
- `spread_cost`
- `slippage_cost`
- `market_impact_cost`
- `total_estimated_cost`
- `total_cost_bps`
- `participation_rate`
- `status`

### 10.6 `cost_estimate_reasons`

- `estimate_id` FK
- `sequence_no`
- `reason_code`
- `severity`
- `observed_value`
- `threshold_value`
- `evidence_ref`
- `reason_hash`

### 10.7 `realized_cost_analyses`

- `analysis_id` PK
- `estimate_id` FK
- `fill_group_id`
- `arrival_price`
- `vwap_fill_price`
- `explicit_cost`
- `implementation_shortfall`
- `realized_slippage_bps`
- `realized_total_cost_bps`
- `estimate_error_bps`
- `analysis_status`
- `analysis_hash`

### 10.8 `cost_model_calibrations`

- `calibration_id` PK
- `model_version`
- `universe_segment`
- `window_start`
- `window_end`
- `sample_count`
- `parameters_json`
- `validation_metrics_json`
- `approval_status`
- `artifact_hash`

모든 금액과 비율은 `Decimal` 또는 고정소수점 문자열로 저장한다.

---

## 11. Reason Code

```text
COST_APPROVED
COST_REDUCED_TO_BUDGET
BLOCKED_COST_BUDGET
BLOCKED_PARTICIPATION_LIMIT
BLOCKED_INVALID_PRICE
BLOCKED_MISSING_LIQUIDITY
BLOCKED_TRADING_HALT
ESTIMATE_DEGRADED
SPREAD_PROXY_USED
VOLATILITY_PROXY_USED
HIGH_MARKET_IMPACT
HIGH_EXPLICIT_COST
POLICY_NOT_EFFECTIVE
POLICY_SNAPSHOT_MISMATCH
POST_TRADE_COST_OUTLIER
MODEL_UNDERESTIMATION
MODEL_OVERESTIMATION
```

Reason은 자연어만 저장하지 않고 관측값, 임계값, 증거 참조를 함께 저장한다.

---

## 12. 코드 구조

```text
transaction_costs/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── explicit_costs.py
├── spread.py
├── slippage.py
├── market_impact.py
├── participation.py
├── sizing.py
├── post_trade.py
├── calibration.py
├── reason_codes.py
├── hashing.py
├── repository.py
└── engine.py
```

핵심 오케스트레이션:

```python
class TransactionCostEngine:
    def estimate(self, request: CostEstimateRequest) -> CostEstimate:
        policy = self.policy_resolver.resolve(request)
        market = self.market_loader.load(request)
        self.validator.validate(request, policy, market)

        explicit = self.explicit_costs.calculate(request, policy)
        spread = self.spread_model.estimate(request, market, policy)
        slippage = self.slippage_model.estimate(request, market, policy)
        impact = self.impact_model.estimate(request, market, policy)

        result = self.budget_resolver.resolve(
            request=request,
            explicit=explicit,
            spread=spread,
            slippage=slippage,
            impact=impact,
            policy=policy,
        )

        return self.repository.save(result)
```

---

## 13. 핵심 불변식

```text
total_estimated_cost >= 0

approved_quantity <= requested_quantity

BLOCKED 상태의 approved_quantity = 0

explicit_cost = commission + exchange_fees + transaction_tax

모든 비용 구성요소의 합 = total_estimated_cost

참여율이 hard limit를 초과하면 APPROVED 금지

정책 유효기간 밖 세율·수수료 사용 금지

PAPER와 BACKTEST에서 비용 원장 이벤트 누락 금지

예상 비용과 실현 비용 레코드 혼합 금지

조정주가를 체결 기준가격으로 사용 금지

동일 request_id의 final estimate는 하나

입력·정책·모델이 동일하면 result_hash 동일
```

---

## 14. 테스트 계획

### 14.1 단위 테스트

1. 매수 수수료 계산
2. 매도 수수료와 거래세 계산
3. 최소 수수료 적용
4. bid-ask half spread 계산
5. 참여율 계산
6. square-root impact 단조 증가 검증
7. 비용 bps 계산
8. 이분탐색 기반 최대 허용수량 계산
9. 과거 거래일 정책 선택
10. Decimal 반올림과 원단위 정합성

### 14.2 고정 통합 시나리오

```text
A. 고유동성 대형주 소액 MARKET BUY
→ APPROVED
→ 비용 구성요소와 합계 검증

B. 저유동성 종목 대규모 BUY
→ 참여율 초과
→ REDUCED 또는 BLOCKED

C. PAPER 종가 매수
→ RAW 종가 사용
→ 비용 원장 별도 반영
→ 총자산 감소 정확성 검증

D. 과거 거래일 매도
→ 해당 거래일의 세율 정책 적용
→ 현재 정책 소급 사용 금지

E. 호가 누락·OHLCV 정상
→ SPREAD_PROXY_USED
→ DEGRADED 상태

F. 거래대금 누락
→ BLOCKED_MISSING_LIQUIDITY
→ 승인수량 0

G. 동일 요청 재실행
→ 동일 estimate_id 또는 멱등 결과
→ 동일 result_hash

H. 실제 fill이 예상보다 불리
→ 양의 estimate_error_bps
→ POST_TRADE_COST_OUTLIER 조건 평가
```

### 14.3 속성 테스트

- 주문수량 증가 시 시장충격이 감소하지 않는다.
- 동일 시장조건에서 참여율 증가 시 총비용 bps가 감소하지 않는다.
- 승인수량은 요청수량을 초과하지 않는다.
- 비용 한도가 낮아질수록 승인수량은 증가하지 않는다.
- 입력 순서를 바꿔도 canonical hash는 동일하다.
- 거래세가 매도 전용 정책이면 매수 거래세는 0이다.
- 총비용은 각 구성요소 합과 정확히 일치한다.

### 14.4 장애 테스트

- 정책 Snapshot 누락
- 잘못된 가격 단위
- 거래량 0
- 음수 수량
- 중복 request
- DB 저장 중 트랜잭션 중단
- 사후 fill 일부 누락
- 모델 버전 artifact checksum 불일치

### 14.5 통합 경로 테스트

```text
Decision approved quantity
→ Transaction Cost estimate
→ 비용 초과 수량 축소
→ Order Validation
→ PAPER Fill
→ Cost Ledger
→ Portfolio Accounting
→ Explainability
→ Daily Report
```

---

## 15. 구현 우선순위

1. 불변 Request·Estimate·Policy 모델
2. SQLite migration
3. Decimal 기반 명시적 비용 계산기
4. 참여율·spread·square-root impact 순수 함수
5. 비용 예산 resolver와 수량 이분탐색
6. canonical hash와 멱등 저장
7. PAPER Trading 비용 원장 adapter
8. Order Validation 사전 비용 adapter
9. 사후 implementation shortfall 분석
10. 고정 대형주·저유동성 fixture 통합 테스트
11. Strategy Monitoring 비용 드리프트 adapter
12. 승인된 calibration artifact 관리

---

## 16. 완료 기준

다음 조건을 만족하면 v1 구현 완료로 본다.

- 명시적 비용 정책이 거래일 기준으로 정확히 선택된다.
- 모든 PAPER·BACKTEST 체결에 비용이 반영된다.
- 참여율과 시장충격에 따라 수량 축소 또는 차단이 결정론적으로 수행된다.
- 비용 구성요소 합계와 총비용이 정확히 일치한다.
- 동일 입력은 동일 hash를 생성한다.
- 사전 예상 비용과 사후 실현 비용이 분리 저장된다.
- 비용 차단·축소 사유가 Explainability와 Report에 전달된다.
- 고정 통합 fixture와 속성 테스트가 통과한다.
