# 10. Execution Monitor

## Purpose

Execution Monitor는 Order Engine이 생성한 주문의 상태를 추적하고, 체결/부분체결/미체결/거부/취소/오류를 표준화한다.

이 엔진은 새로운 매수/매도 판단을 생성하지 않는다. 역할은 주문 이후의 실행 상태를 감시하고, Portfolio State Engine과 Report Engine이 사용할 수 있는 체결 이벤트를 만드는 것이다.

## Responsibility Boundary

| 포함 | 제외 |
|---|---|
| 주문 상태 조회 | 신규 투자 판단 |
| 체결/미체결 상태 표준화 | 주문 생성 |
| 부분체결 누적 계산 | 포지션 크기 결정 |
| 주문 실패 원인 분류 | 리스크 한도 결정 |
| 체결 이벤트 저장 | 실계좌 주문 전송 |
| 포트폴리오 갱신 이벤트 발행 | 백테스트 성과 평가 |

## Inputs

```python
ExecutionMonitorInput(
    order_id="ORD-20260708-000001",
    broker_order_id="KIS-123456789",
    symbol="005930",
    side="BUY",
    requested_quantity=10,
    requested_price=72000,
    order_type="LIMIT",
    submitted_at="2026-07-08T09:01:00+09:00",
    mode="DRY_RUN",
)
```

## Outputs

```python
ExecutionStatus(
    order_id="ORD-20260708-000001",
    broker_order_id="KIS-123456789",
    symbol="005930",
    status="PARTIALLY_FILLED",
    requested_quantity=10,
    filled_quantity=4,
    remaining_quantity=6,
    average_fill_price=71950,
    last_event="FILL",
    last_event_at="2026-07-08T09:02:15+09:00",
    reject_reason=None,
)
```

## Architecture

```text
Order Engine
  ↓
Submitted Order
  ↓
Execution Monitor
  ├─ Order Status Poller
  ├─ Fill Event Normalizer
  ├─ Partial Fill Aggregator
  ├─ Failure Classifier
  └─ Execution Journal
  ↓
Portfolio State Engine
Report Engine
```

## Execution State Model

| 상태 | 의미 | 다음 상태 |
|---|---|---|
| CREATED | 주문 객체 생성 | SUBMITTED, REJECTED |
| SUBMITTED | 브로커 또는 모의 엔진에 접수 | PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED |
| PARTIALLY_FILLED | 일부 수량 체결 | FILLED, CANCELLED, EXPIRED |
| FILLED | 전체 수량 체결 | FINAL |
| CANCELLED | 사용자가 취소 또는 시스템 취소 | FINAL |
| REJECTED | 주문 접수 거부 | FINAL |
| EXPIRED | 지정 시간 내 미체결 | FINAL |
| ERROR | 조회/연동/데이터 오류 | RETRY, MANUAL_REVIEW |

## Failure Classification

| 분류 | 예시 | 처리 |
|---|---|---|
| INSUFFICIENT_CASH | 현금 부족 | REJECTED 기록, 재주문 금지 |
| PRICE_LIMIT | 상하한가 또는 호가 제한 | REJECTED 또는 EXPIRED |
| MARKET_CLOSED | 장외 시간 | EXPIRED 또는 대기 |
| SYMBOL_INVALID | 종목 코드 오류 | REJECTED, 수동 확인 |
| API_ERROR | KIS/API 응답 실패 | ERROR, 재조회 |
| NETWORK_ERROR | 통신 장애 | ERROR, 재시도 |
| UNKNOWN | 분류 불가 | MANUAL_REVIEW |

## Database

### execution_runs

| Column | Type | Description |
|---|---|---|
| id | integer | execution monitor run id |
| started_at | datetime | run start time |
| finished_at | datetime | run finish time |
| mode | text | DRY_RUN/PAPER/LIVE_BLOCKED/LIVE |
| status | text | SUCCESS/PARTIAL/FAILED |
| note | text | optional note |

### order_executions

| Column | Type | Description |
|---|---|---|
| id | integer | primary key |
| order_id | text | internal order id |
| broker_order_id | text | broker order id |
| symbol | text | stock symbol |
| side | text | BUY/SELL |
| order_type | text | MARKET/LIMIT |
| requested_quantity | integer | requested quantity |
| requested_price | numeric | requested price |
| filled_quantity | integer | cumulative filled quantity |
| remaining_quantity | integer | unfilled quantity |
| average_fill_price | numeric | weighted average fill price |
| status | text | current execution status |
| reject_reason | text | normalized rejection reason |
| created_at | datetime | order creation time |
| updated_at | datetime | last update time |

### execution_events

| Column | Type | Description |
|---|---|---|
| id | integer | primary key |
| order_id | text | internal order id |
| event_type | text | SUBMIT/FILL/PARTIAL_FILL/CANCEL/REJECT/EXPIRE/ERROR |
| event_time | datetime | event time |
| event_quantity | integer | event fill quantity |
| event_price | numeric | event fill price |
| raw_payload | json | raw broker/mock response |
| normalized_payload | json | normalized event data |

## Algorithm

```python
def monitor_order(order):
    execution = load_or_create_execution(order)

    raw_status = fetch_order_status(order)
    event = normalize_execution_event(raw_status)

    execution = apply_event(execution, event)
    execution.status = classify_status(execution)
    execution.reject_reason = classify_failure(event)

    save_execution(execution)
    save_execution_event(event)

    if execution.status in FINAL_STATES:
        publish_portfolio_update(execution)
        publish_report_event(execution)

    return execution
```

## Partial Fill Aggregation

```python
average_fill_price = (
    previous_average_price * previous_filled_quantity
    + new_fill_price * new_fill_quantity
) / (previous_filled_quantity + new_fill_quantity)
```

```python
filled_quantity = previous_filled_quantity + new_fill_quantity
remaining_quantity = requested_quantity - filled_quantity
```

## Operating Modes

| Mode | Behavior |
|---|---|
| DRY_RUN | 주문 전송 없이 가상 체결 이벤트 생성 |
| PAPER | 모의 주문 엔진 또는 샌드박스 응답 추적 |
| LIVE_BLOCKED | 실계좌 주문과 체결 조회 모두 차단 |
| LIVE | 명시적 검증 후에만 실계좌 체결 조회 허용 |

## Safety Rules

1. `LIVE_BLOCKED`에서는 실계좌 API를 호출하지 않는다.
2. 주문 상태 조회와 주문 전송을 분리한다.
3. 같은 체결 이벤트는 중복 반영하지 않는다.
4. 체결 수량은 요청 수량을 초과할 수 없다.
5. 평균 체결가는 체결 이벤트 기준으로만 계산한다.
6. 오류 상태는 자동 재주문으로 이어지지 않는다.
7. 모든 원본 응답은 감사 추적을 위해 저장한다.

## Code Plan

```text
execution/
  __init__.py
  monitor.py          # ExecutionMonitor main service
  models.py           # ExecutionMonitorInput, ExecutionStatus, ExecutionEvent
  repository.py       # persistence layer
  normalizer.py       # broker/mock response normalization
  classifier.py       # status and failure classification
  simulator.py        # DRY_RUN/PAPER fill simulator

tests/
  test_execution_monitor.py
  test_execution_normalizer.py
  test_execution_partial_fill.py
```

## Test Plan

- submitted order becomes FILLED when full quantity is executed
- partial fills accumulate quantity correctly
- weighted average fill price is calculated correctly
- duplicate fill event is ignored
- rejected order records normalized reject reason
- expired order does not update portfolio as filled
- execution quantity cannot exceed requested quantity
- LIVE_BLOCKED mode does not call broker API
- API error becomes ERROR and does not trigger reorder
- final execution event publishes portfolio/report update

## Acceptance Criteria

- 주문 1건의 전체 생명주기를 CREATED부터 FINAL 상태까지 추적할 수 있다.
- 체결/부분체결/거부/취소/만료/오류가 표준 상태로 저장된다.
- 체결 이벤트는 Portfolio State와 Report Engine에 전달 가능한 형태로 출력된다.
- 실계좌 주문 또는 조회는 명시적 안전 검증 전까지 차단된다.
