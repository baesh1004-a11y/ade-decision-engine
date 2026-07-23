# 24. Order Validation & Routing Engine v2

## 1. 목적

Order Validation & Routing Engine v2는 Decision & Position Sizing Engine이 만든 `OrderIntent`를 주문 전송 직전에 다시 검증하고, 실행 모드·시장·계좌·상품에 적합한 브로커 어댑터와 주문 경로를 선택하는 실행 경계 계층이다.

이 엔진은 새로운 투자 판단이나 포지션 크기를 만들지 않는다. Decision과 Risk가 승인한 의도를 보존하면서, 주문 시점의 최신 계좌·시장·가격·미체결 상태를 기준으로 전송 가능 여부를 확정한다.

## 2. v1 대비 확장 범위

| 영역 | Order Engine v1 | Validation & Routing v2 |
|---|---|---|
| 주문 생성 | 기본 주문 객체 생성 | 불변 OrderIntent → 실행 OrderRequest 변환 |
| 검증 | 수량·가격·현금·보유량 | 최신 시세·승인 만료·예약금·호가단위·시장세션·상품 규칙 |
| 중복 방지 | 종목/방향 단순 비교 | idempotency key, fingerprint, unresolved order reservation |
| 라우팅 | 단일 broker adapter | 시장·계좌·모드·상품별 Route Policy |
| 가격 보호 | 기본 limit 검증 | stale price, price band, slippage budget, collar |
| 장애 처리 | SEND_FAILED | VERIFY_REQUIRED, retry classification, circuit breaker |
| 승인 | 암묵적 | approval token, TTL, 정책·데이터 snapshot 일치 |
| 감사 | 주문 이벤트 | 검증 결과·라우팅 이유·원본 응답·재조회 증거 |

## 3. 책임 경계

### 담당

- `OrderIntent` 계약 검증
- Decision, Risk, Policy, Data Snapshot의 run/snapshot 정합성 확인
- 승인 토큰과 주문 승인 만료시간 검증
- 최신 시세와 기준 시세의 신선도·가격 괴리 검증
- 현금, 예약금, 미체결 주문, 매도 가능 수량 재검증
- KRX 호가단위, 최소 주문수량, 주문유형, 시장 세션 검증
- 동일 주문의 중복 전송 방지와 멱등성 보장
- DRY_RUN, PAPER, LIVE_BLOCKED, LIVE 모드 게이트
- 시장·계좌·상품에 맞는 브로커 Route 선택
- 전송 전 주문 fingerprint와 reservation 생성
- 브로커 응답의 표준 상태 변환
- 불확실 전송 결과를 `VERIFY_REQUIRED`로 격리
- Execution Monitor가 추적 가능한 broker reference 전달

### 담당하지 않음

- 매수·매도 판단 생성
- 목표 금액·수량 확대
- Risk 하드 차단 우회
- 체결 여부 확정
- 실현·미실현 손익 계산
- 자동 재주문 판단
- 전략 파라미터 변경

## 4. 전체 아키텍처

```text
Decision & Position Sizing Engine
        ↓
Immutable OrderIntent
        ↓
Order Contract Validator
        ├─ run/snapshot consistency
        ├─ decision/risk approval
        ├─ approval token / TTL
        └─ quantity and amount bounds
        ↓
Pre-Trade Revalidation
        ├─ latest quote and freshness
        ├─ cash / reservation / holdings
        ├─ open orders / duplicate guard
        ├─ market session / halt
        └─ tick size / order type rules
        ↓
Price Protection
        ├─ limit price normalization
        ├─ price collar
        ├─ slippage budget
        └─ stale-price block
        ↓
Route Policy Engine
        ├─ DRY_RUN adapter
        ├─ PAPER adapter
        ├─ LIVE_BLOCKED sink
        └─ LIVE broker adapter
        ↓
Submission Coordinator
        ├─ idempotency reservation
        ├─ broker request
        ├─ response normalization
        └─ ambiguous response isolation
        ↓
Order Journal / Execution Monitor / Audit Engine
```

## 5. 입력 모델

```python
@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    run_id: str
    decision_id: str
    risk_snapshot_id: str
    policy_snapshot_id: str
    data_snapshot_id: str
    account_id: str
    market: str
    symbol: str
    action: str
    side: str
    target_quantity: int
    target_amount: int
    reference_price: float
    order_type: str
    time_in_force: str
    created_at: datetime
    expires_at: datetime
    approval_token: str | None
    reason_codes: tuple[str, ...]
```

추가 실행 입력:

- current portfolio/account snapshot
- broker buying power and sellable quantity
- latest quote and quote timestamp
- market calendar/session state
- open and unresolved orders
- policy snapshot
- routing configuration
- trading mode

## 6. 출력 모델

```python
@dataclass(frozen=True)
class RoutedOrderResult:
    order_request_id: str
    intent_id: str
    route_id: str
    broker: str
    account_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    limit_price: float | None
    status: str
    broker_order_id: str | None
    idempotency_key: str
    validation_codes: tuple[str, ...]
    route_reason: str
    created_at: datetime
```

상태:

| 상태 | 의미 |
|---|---|
| REJECTED_CONTRACT | 입력 계약·snapshot 불일치 |
| REJECTED_PRETRADE | 현금·보유량·세션·상품 규칙 위반 |
| REJECTED_PRICE | 가격 신선도·괴리·collar 위반 |
| DUPLICATE_BLOCKED | 동일 또는 실질적으로 동일한 미해결 주문 존재 |
| APPROVAL_EXPIRED | 승인 TTL 만료 |
| LIVE_BLOCKED | LIVE 주문 안전 게이트 차단 |
| DRY_RUN_RECORDED | 전송 없이 기록 완료 |
| PAPER_SUBMITTED | 모의 주문 전송 완료 |
| LIVE_SUBMITTED | 실주문 접수 확인 |
| VERIFY_REQUIRED | 전송 여부가 불확실하여 재주문 금지·조회 필요 |
| SEND_FAILED | 전송되지 않았음이 확인된 실패 |

## 7. 핵심 불변식

```text
전송 수량 ≤ Decision 목표 수량
전송 수량 ≤ Risk 승인 수량
전송 금액 ≤ Risk 승인 금액
OrderIntent의 run_id와 모든 snapshot run_id는 동일
만료된 승인으로 주문 생성 금지
동일 idempotency key는 최대 1회만 브로커 전송
VERIFY_REQUIRED 상태는 자동 재전송 금지
LIVE_BLOCKED에서는 브로커 submit 호출 0회
매도 수량 ≤ 최신 매도 가능 수량
매수 후 예상 현금은 정책 하한 이상
브로커 응답이 불확실하면 실패로 단정하지 않음
```

## 8. 검증 단계

### 8.1 계약 검증

1. 필수 식별자 존재
2. `BUY`, `SELL`, `REDUCE`만 주문 생성 가능
3. 수량·금액·가격이 양수
4. Decision과 Risk 결과가 동일 run에 속함
5. Risk 상태가 `APPROVED` 또는 `APPROVED_REDUCED`
6. Intent 수량·금액이 Risk 승인 범위 이하
7. Policy/Data snapshot이 잠김 상태
8. 승인 토큰 서명·주체·계좌·intent 일치
9. `expires_at` 이전

### 8.2 주문 전 재검증

매수:

```text
available_cash
= broker_buying_power
- unresolved_buy_reservations
- fees_and_tax_buffer
```

```text
estimated_order_cost
= normalized_price × quantity
+ expected_fee
+ expected_tax
```

`estimated_order_cost > available_cash`이면 차단한다.

매도:

```text
available_sell_quantity
= broker_sellable_quantity
- unresolved_sell_reservations
```

`quantity > available_sell_quantity`이면 차단한다.

공통:

- 거래일·세션 허용 여부
- 종목 상장·거래정지·관리 상태
- 주문유형 지원 여부
- 일일 신규 진입 한도
- 동일 종목·방향의 미해결 주문
- 계좌·시장·통화 일치

## 9. 가격 보호 알고리즘

### 9.1 시세 신선도

```python
quote_age = now - latest_quote.as_of
if quote_age > policy.max_quote_age:
    reject("STALE_QUOTE")
```

예시 기본값:

| 모드 | 최대 시세 지연 |
|---|---:|
| DRY_RUN | 15분 |
| PAPER | 60초 |
| LIVE_BLOCKED | 60초 |
| LIVE | 10초 |

### 9.2 가격 괴리

```python
reference_gap = abs(latest_price - intent.reference_price) / intent.reference_price
if reference_gap > policy.max_reference_gap_pct:
    reject("REFERENCE_PRICE_DRIFT")
```

### 9.3 Price Collar

매수 상한:

```text
max_buy_price = latest_ask × (1 + buy_collar_pct)
```

매도 하한:

```text
min_sell_price = latest_bid × (1 - sell_collar_pct)
```

Limit 가격이 collar 밖이면 정책에 따라 `REJECT` 또는 보수 방향으로만 정규화한다. 엔진은 더 공격적인 가격으로 임의 변경하지 않는다.

### 9.4 호가단위 정규화

- 매수 지정가는 허용 호가단위로 내림 또는 정책 지정 방식 적용
- 매도 지정가는 허용 호가단위로 올림 또는 정책 지정 방식 적용
- 정규화 후 예상 금액과 Risk 한도를 다시 검증

## 10. 중복·멱등성 설계

### Order Fingerprint

```text
fingerprint = SHA256(
    account_id
    + market
    + symbol
    + side
    + quantity
    + normalized_price
    + order_type
    + source_decision_id
    + policy_snapshot_id
)
```

### Idempotency Key

```text
idempotency_key = SHA256(intent_id + route_id + attempt_group)
```

차단 조건:

- 동일 idempotency key의 `RESERVED`, `SUBMITTING`, `SUBMITTED`, `VERIFY_REQUIRED` 존재
- 동일 fingerprint의 미해결 주문 존재
- 동일 Decision에서 이미 주문 생성

`SEND_FAILED`라도 브로커 미접수 사실이 확정된 경우에만 새로운 attempt를 허용한다.

## 11. 라우팅 정책

```python
@dataclass(frozen=True)
class RouteRule:
    route_id: str
    mode: str
    market: str
    account_type: str
    product_type: str
    broker: str
    priority: int
    enabled: bool
```

선택 순서:

1. mode 일치
2. market 일치
3. account/product 지원
4. enabled 상태
5. broker circuit breaker 정상
6. 정책 승인 상태
7. priority가 가장 높은 route

라우팅 결과가 없으면 `REJECTED_PRETRADE: NO_ELIGIBLE_ROUTE`이다.

## 12. 브로커 전송 및 불확실 응답

```python
def submit_routed_order(intent, context, repository, router):
    contract = validate_contract(intent, context)
    if not contract.ok:
        return reject_contract(contract.codes)

    pretrade = revalidate_pretrade(intent, context)
    if not pretrade.ok:
        return reject_pretrade(pretrade.codes)

    protected = protect_price(intent, context.quote, context.policy)
    route = router.select(intent, context)
    key = build_idempotency_key(intent, route)

    with repository.reserve_submission(key, intent, route) as reservation:
        if context.mode == "DRY_RUN":
            return repository.complete_dry_run(reservation, protected)
        if context.mode == "LIVE_BLOCKED":
            return repository.block_live(reservation, protected)

        try:
            raw = route.adapter.submit(protected)
        except DefiniteNotSentError as exc:
            return repository.mark_send_failed(reservation, exc)
        except (TimeoutError, ConnectionError) as exc:
            return repository.mark_verify_required(reservation, exc)

        normalized = normalize_broker_response(raw)
        if normalized.accepted:
            return repository.mark_submitted(reservation, normalized)
        if normalized.definite_reject:
            return repository.mark_rejected(reservation, normalized)
        return repository.mark_verify_required(reservation, normalized)
```

`VERIFY_REQUIRED` 처리:

1. 자동 재전송 금지
2. broker order query 또는 execution inquiry 수행
3. 주문 존재 확인 시 `SUBMITTED` 전환
4. 미존재가 확정되면 `SEND_FAILED_CONFIRMED`
5. 끝까지 불명확하면 수동 검토

## 13. 데이터베이스

### 13.1 `order_intents`

| 컬럼 | 설명 |
|---|---|
| intent_id PK | 불변 주문 의도 ID |
| run_id | 실행 ID |
| decision_id | 원천 Decision |
| risk_snapshot_id | Risk 근거 |
| policy_snapshot_id | 정책 근거 |
| data_snapshot_id | 데이터 근거 |
| account_id, market, symbol | 주문 대상 |
| side, target_quantity, target_amount | 승인된 의도 |
| reference_price | 판단 기준 가격 |
| order_type, time_in_force | 주문 속성 |
| approval_token_hash | 승인 증거 |
| created_at, expires_at | 생성·만료 |
| payload_hash | 불변성 해시 |

### 13.2 `order_validations`

| 컬럼 | 설명 |
|---|---|
| validation_id PK | 검증 ID |
| intent_id FK | 주문 의도 |
| validation_stage | CONTRACT/PRETRADE/PRICE/ROUTE |
| result | PASS/FAIL/WARN |
| reason_code | 표준 코드 |
| observed_value | 관측값 |
| limit_value | 정책값 |
| evidence_json | 검증 증거 |
| created_at | 시각 |

### 13.3 `order_routes`

| 컬럼 | 설명 |
|---|---|
| route_id PK | 라우트 ID |
| mode, market | 적용 범위 |
| account_type, product_type | 계좌·상품 |
| broker | 브로커 |
| priority | 우선순위 |
| enabled | 활성 상태 |
| config_json | 비민감 라우트 설정 |
| policy_version | 정책 버전 |

### 13.4 `order_submissions`

| 컬럼 | 설명 |
|---|---|
| submission_id PK | 전송 ID |
| order_request_id | 내부 주문 ID |
| intent_id FK | 주문 의도 |
| route_id FK | 사용 경로 |
| idempotency_key UNIQUE | 멱등성 키 |
| fingerprint | 실질 중복 비교값 |
| status | RESERVED/SUBMITTING/SUBMITTED/VERIFY_REQUIRED/SEND_FAILED |
| broker_order_id | 외부 주문번호 |
| requested_at, responded_at | 전송 시각 |
| request_hash, response_hash | 무결성 |
| error_class, error_message | 오류 |

### 13.5 `order_reservations`

| 컬럼 | 설명 |
|---|---|
| reservation_id PK | 예약 ID |
| account_id, symbol, side | 예약 대상 |
| reserved_cash | 매수 예약금 |
| reserved_quantity | 매도 예약수량 |
| submission_id FK | 전송 ID |
| status | ACTIVE/RELEASED/CONSUMED |
| expires_at | 복구용 만료 |

### 13.6 `broker_route_health`

| 컬럼 | 설명 |
|---|---|
| route_id PK | 라우트 |
| state | CLOSED/OPEN/HALF_OPEN |
| failure_count | 연속 실패 |
| opened_at | 차단 시각 |
| next_probe_at | 시험 요청 시각 |
| last_error | 최근 오류 |

## 14. 표준 사유 코드

| 코드 | 의미 |
|---|---|
| CROSS_RUN_SNAPSHOT | 서로 다른 run의 결과 결합 |
| RISK_NOT_APPROVED | Risk 승인 없음 |
| RISK_BOUND_EXCEEDED | 수량·금액이 Risk 승인 초과 |
| APPROVAL_REQUIRED | 승인 토큰 없음 |
| APPROVAL_EXPIRED | 승인 만료 |
| STALE_QUOTE | 최신 시세 지연 |
| REFERENCE_PRICE_DRIFT | 판단 가격과 최신 가격 괴리 |
| PRICE_COLLAR_VIOLATION | 가격 보호범위 초과 |
| INSUFFICIENT_BUYING_POWER | 매수 가능금액 부족 |
| INSUFFICIENT_SELLABLE_QTY | 매도 가능수량 부족 |
| UNRESOLVED_RESERVATION | 기존 미해결 주문 예약 존재 |
| DUPLICATE_ORDER | 동일 주문 존재 |
| MARKET_CLOSED | 세션 비허용 |
| SYMBOL_HALTED | 거래정지 |
| UNSUPPORTED_ORDER_TYPE | 주문유형 미지원 |
| NO_ELIGIBLE_ROUTE | 사용 가능한 라우트 없음 |
| BROKER_CIRCUIT_OPEN | 브로커 경로 차단 |
| LIVE_MODE_BLOCKED | 실계좌 안전 차단 |
| AMBIGUOUS_BROKER_RESPONSE | 접수 여부 불확실 |

## 15. 코드 구조

```text
order/
├── __init__.py
├── models.py              # OrderIntent, RoutedOrderResult
├── contract.py            # snapshot, approval, risk bounds
├── pretrade.py            # cash, holdings, reservations, session
├── pricing.py             # freshness, collar, tick normalization
├── fingerprint.py         # fingerprint and idempotency
├── router.py              # RouteRule, route selection
├── coordinator.py         # submission transaction coordinator
├── normalizer.py          # broker response mapping
├── repository.py          # protocol and persistence
├── dry_run.py             # DryRun adapter
├── paper.py               # Paper adapter
└── kis_adapter.py         # protected live adapter

tests/
├── test_order_contract.py
├── test_order_pretrade.py
├── test_order_pricing.py
├── test_order_idempotency.py
├── test_order_routing.py
├── test_order_submission.py
├── test_order_verify_required.py
└── test_order_integration.py
```

## 16. 테스트 계획

### 단위 테스트

- HOLD/NO_ACTION은 주문을 만들지 않는다.
- BUY/SELL/REDUCE Intent가 올바른 방향으로 변환된다.
- cross-run snapshot은 차단된다.
- Risk 승인 수량·금액 초과는 차단된다.
- 승인 토큰 누락·불일치·만료는 차단된다.
- stale quote와 reference price drift를 탐지한다.
- price collar 밖 지정가를 차단한다.
- KRX 호가단위 정규화 후 금액을 재검증한다.
- 예약금을 포함한 매수 가능금액을 계산한다.
- 예약수량을 포함한 매도 가능수량을 계산한다.
- 동일 fingerprint와 idempotency key를 차단한다.
- route priority와 circuit breaker를 반영한다.

### 데이터베이스 테스트

- idempotency key UNIQUE 제약이 경쟁 요청을 차단한다.
- reservation 생성과 submission RESERVED 기록이 원자적이다.
- 실패 시 reservation rollback 또는 명시적 RELEASE가 수행된다.
- 감사 이벤트와 validation evidence가 누락 없이 저장된다.
- 민감정보가 raw payload에 저장되지 않는다.

### 통합 테스트

- Decision → Risk → OrderIntent → DRY_RUN 전체 경로
- PAPER adapter의 제출과 Execution Monitor 전달
- LIVE_BLOCKED에서 브로커 호출 0회
- 동일 요청 동시 20개 중 브로커 호출 1회
- 부분 체결 주문이 unresolved reservation을 유지
- 주문 취소·거부·만료 시 reservation 해제
- 서로 다른 종목의 주문은 독립 처리

### 장애 주입 테스트

- submit 직전 DB 장애
- broker timeout
- broker accepted 후 응답 유실
- broker 5xx와 명확한 reject 응답
- order query 장애
- circuit breaker OPEN 전환
- process crash 후 RESERVED/SUBMITTING 복구

### 속성 기반 테스트

무작위 계좌·보유·시세·주문 조합에서 다음을 검증한다.

```text
전송 수량은 승인 수량을 초과하지 않는다.
매수 후 현금은 음수가 되지 않는다.
매도 후 보유수량은 음수가 되지 않는다.
동일 멱등성 키의 submit 호출은 최대 1회다.
VERIFY_REQUIRED는 자동 재전송되지 않는다.
```

### 성능 목표

- 단일 주문 검증 p95 < 50ms, 외부 API 제외
- 라우트 선택 p95 < 5ms
- SQLite 기준 초당 100건 reservation 경쟁 처리 검증
- 10,000개 미해결 주문에서 종목·계좌 중복 조회 p95 < 30ms

## 17. 안전 정책

1. 기본 모드는 `DRY_RUN` 또는 `LIVE_BLOCKED`이다.
2. `LIVE`는 승인된 Policy Snapshot과 명시적 계좌 허용 목록이 모두 있어야 한다.
3. Risk 하드 차단은 어떠한 route도 우회할 수 없다.
4. 주문 가격·수량을 더 공격적으로 확대하지 않는다.
5. 불확실 응답은 실패가 아니라 `VERIFY_REQUIRED`이다.
6. `VERIFY_REQUIRED` 상태에서 재주문을 만들지 않는다.
7. 모든 주문은 Decision, Risk, Policy, Data Snapshot으로 역추적 가능해야 한다.
8. API 키·토큰·계좌 인증정보는 DB와 감사 payload에 저장하지 않는다.

## 18. 구현 순서

1. `OrderIntent`, `OrderValidationResult`, `RoutedOrderResult` 모델
2. 순수 함수 기반 contract/pretrade/pricing validator
3. SQLite migration과 Repository
4. idempotency reservation transaction
5. DryRun/Paper adapter
6. route policy와 circuit breaker
7. ambiguous response → VERIFY_REQUIRED 처리
8. Execution Monitor 연계
9. KIS adapter는 LIVE_BLOCKED 뒤에 연결
10. fixture 기반 전체 통합 테스트

## 19. 완료 기준

- 동일 OrderIntent가 중복 전송되지 않는다.
- 주문 직전 최신 현금·보유·시세·미체결 상태를 재검증한다.
- Decision/Risk 승인값을 초과하는 주문이 생성되지 않는다.
- DRY_RUN/PAPER/LIVE_BLOCKED 경로가 모두 테스트된다.
- 불확실 브로커 응답을 안전하게 격리하고 조회로 해소한다.
- 모든 주문 결과가 Execution Monitor와 Audit Engine에 전달된다.
- 고정 fixture 통합 테스트에서 결정부터 주문 journal까지 재현 가능하다.

## 20. 다음 설계 대상

**Execution Reconciliation & Recovery Engine v2**

브로커 주문·체결 조회와 내부 Order/Execution/Portfolio 원장을 대사하고, 유실·중복·지연·부분체결·불확실 전송 결과를 안전하게 복구하는 계층을 구체화한다.
