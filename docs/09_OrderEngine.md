# 09. Order Engine

## Purpose

Order Engine은 Decision Engine의 최종 판단을 실제 주문 요청 객체로 변환하고, 주문 전 검증을 수행하며, 승인된 주문만 브로커 연동 계층으로 전달한다.

이 엔진은 투자 판단을 새로 만들지 않는다. 또한 실계좌 주문 실행은 명시적 안전 검증 전까지 차단한다.

## Scope

### Responsibilities

- Decision 결과를 표준 주문 객체로 변환
- 주문 가능 여부 사전 검증
- 수량, 가격, 주문 유형, 계좌, 종목 코드 검증
- 중복 주문 및 과도 주문 방지
- 모의 주문 또는 실주문 전송 요청 생성
- 주문 요청/응답 이력 저장
- Execution Monitor로 추적 가능한 주문 ID 전달

### Non-Responsibilities

- 매수/매도 여부 판단
- 포지션 크기 산정
- 리스크 한도 최종 판단
- 체결 여부 판단
- 손익 계산
- 리포트 생성

## Inputs

```python
Decision(
    symbol="005930",
    action="BUY",
    confidence=0.78,
    reason="signal_score>=65 and risk_level=LOW",
    target_quantity=10,
    target_price=72000,
    order_type="LIMIT",
    time_in_force="DAY",
)
```

Additional inputs:

- portfolio state
- risk approval result
- broker account configuration
- market session state
- latest price snapshot
- open orders
- trading mode: `DRY_RUN`, `PAPER`, `LIVE_BLOCKED`, `LIVE`

## Outputs

```python
OrderRequest(
    order_id="ORD-20260707-000001",
    symbol="005930",
    side="BUY",
    quantity=10,
    order_type="LIMIT",
    limit_price=72000,
    time_in_force="DAY",
    trading_mode="PAPER",
    status="READY_TO_SEND",
    source_decision_id="DEC-20260707-000001",
)
```

Possible output statuses:

| Status | Meaning |
|---|---|
| REJECTED_BY_ORDER_ENGINE | 주문 생성 전 검증 실패 |
| READY_TO_SEND | 브로커 전송 가능 |
| DRY_RUN_RECORDED | 실제 전송 없이 기록 완료 |
| PAPER_SUBMITTED | 모의 주문 전송 완료 |
| LIVE_BLOCKED | 실계좌 주문 안전 차단 |
| LIVE_SUBMITTED | 실계좌 주문 전송 완료 |
| SEND_FAILED | 브로커 전송 실패 |

## Architecture

```text
Decision Engine
  ↓
Order Intent Parser
  ↓
Order Validator
  ↓
Duplicate / Exposure Guard
  ↓
Order Builder
  ↓
Trading Mode Gate
  ├─ DRY_RUN → Record only
  ├─ PAPER → Paper broker adapter
  ├─ LIVE_BLOCKED → Block and record
  └─ LIVE → Broker adapter
  ↓
Order Log
  ↓
Execution Monitor
```

## Order Validation Rules

| Rule | Description | Failure Status |
|---|---|---|
| action_allowed | BUY/SELL/REDUCE only creates orders | REJECTED_BY_ORDER_ENGINE |
| quantity_positive | quantity > 0 | REJECTED_BY_ORDER_ENGINE |
| price_valid | limit order must have valid limit_price | REJECTED_BY_ORDER_ENGINE |
| symbol_valid | symbol exists and matches market format | REJECTED_BY_ORDER_ENGINE |
| market_open | market session allows order submission | REJECTED_BY_ORDER_ENGINE |
| risk_approved | Risk Engine approved the decision | REJECTED_BY_ORDER_ENGINE |
| cash_available | buy order does not exceed available cash | REJECTED_BY_ORDER_ENGINE |
| position_available | sell order does not exceed available holdings | REJECTED_BY_ORDER_ENGINE |
| duplicate_check | same symbol/side order is not already open | REJECTED_BY_ORDER_ENGINE |
| live_safety | live trading is explicitly enabled | LIVE_BLOCKED |

## Trading Modes

| Mode | Behavior |
|---|---|
| DRY_RUN | 주문 객체만 생성하고 DB에 기록한다. 브로커 전송 없음 |
| PAPER | 모의투자 또는 가상 브로커에 전송한다 |
| LIVE_BLOCKED | 실계좌 주문 요청을 차단하고 차단 로그를 남긴다 |
| LIVE | 명시적 안전 검증 후에만 실계좌 브로커로 전송한다 |

Default mode must be `LIVE_BLOCKED` or `DRY_RUN`. Production `LIVE` mode is forbidden until safety review is completed.

## Database

### `order_requests`

| Column | Type | Description |
|---|---|---|
| id | text | internal order request id |
| decision_id | text | source decision id |
| symbol | text | stock code |
| side | text | BUY/SELL |
| quantity | integer | order quantity |
| order_type | text | MARKET/LIMIT |
| limit_price | numeric | limit price, nullable for market orders |
| time_in_force | text | DAY/IOC/FOK |
| trading_mode | text | DRY_RUN/PAPER/LIVE_BLOCKED/LIVE |
| status | text | order request status |
| reason | text | rejection/block/send reason |
| created_at | datetime | request creation timestamp |
| updated_at | datetime | last update timestamp |

### `order_events`

| Column | Type | Description |
|---|---|---|
| id | text | event id |
| order_request_id | text | related order request id |
| event_type | text | CREATED/VALIDATED/BLOCKED/SUBMITTED/FAILED |
| message | text | event detail |
| raw_payload | json | broker request/response payload |
| created_at | datetime | event timestamp |

### `broker_order_refs`

| Column | Type | Description |
|---|---|---|
| id | text | internal id |
| order_request_id | text | related order request id |
| broker | text | broker name, e.g. KIS |
| broker_order_id | text | external order id |
| broker_status | text | broker-side status |
| created_at | datetime | timestamp |

## Algorithm

```python
def create_order(decision, portfolio, risk_result, market, open_orders, config):
    if decision.action not in {"BUY", "SELL", "REDUCE"}:
        return reject("action does not require order")

    validation = validate_order_inputs(
        decision=decision,
        portfolio=portfolio,
        risk_result=risk_result,
        market=market,
        open_orders=open_orders,
    )
    if not validation.ok:
        return reject(validation.reason)

    order = build_order_request(decision, config.trading_mode)

    if config.trading_mode == "DRY_RUN":
        record_order(order, status="DRY_RUN_RECORDED")
        return order

    if config.trading_mode == "LIVE_BLOCKED":
        record_order(order, status="LIVE_BLOCKED")
        return order

    response = broker_adapter.submit(order)
    return map_broker_response(order, response)
```

## Safety Principles

- LIVE trading must never be the default mode.
- Order Engine must persist rejected and blocked orders for auditability.
- Every submitted order must reference a source Decision ID.
- Every submitted order must be traceable by Execution Monitor.
- Duplicate orders must be blocked unless explicitly approved.
- Order Engine must not silently modify Decision intent except for validation failure.

## Interface Draft

```python
@dataclass
class OrderRequest:
    order_id: str
    source_decision_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: float | None
    time_in_force: Literal["DAY", "IOC", "FOK"]
    trading_mode: Literal["DRY_RUN", "PAPER", "LIVE_BLOCKED", "LIVE"]
    status: str
    reason: str | None = None
```

## Test Plan

- HOLD/NO_ACTION decision does not create an order
- BUY decision creates BUY order request
- SELL/REDUCE decision creates SELL order request
- zero or negative quantity is rejected
- limit order without limit price is rejected
- buy order exceeding available cash is rejected
- sell order exceeding holdings is rejected
- duplicate open order is rejected
- LIVE_BLOCKED mode blocks real order submission
- DRY_RUN mode records order without broker call
- PAPER mode calls paper broker adapter
- broker failure maps to SEND_FAILED
- every order stores source decision id

## Implementation Plan

1. Add `order/order.py` or `core/order_engine.py`.
2. Define `OrderRequest`, `OrderResult`, and `OrderEvent` dataclasses.
3. Add validation helpers independent from broker API.
4. Add `DryRunBrokerAdapter` and `PaperBrokerAdapter` first.
5. Keep `KISBrokerAdapter` behind `LIVE_BLOCKED` safety gate.
6. Add unit tests for validation and trading mode gate.
7. Connect Order Engine after Decision Engine only after smoke test passes.

## Current Status

| Area | Status |
|---|---|
| Architecture | 설계 완료 |
| Database | 설계 완료 |
| Algorithm | 설계 완료 |
| Code | 미구현 |
| Tests | 계획 완료 |
| Execution | 미확인 |
