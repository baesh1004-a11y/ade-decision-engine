# 23. Decision & Position Sizing Engine v1

## 1. 목적

Decision & Position Sizing Engine은 Signal Generation & Ranking Engine의 후보와 Portfolio Risk & Exposure Engine의 승인 결과를 결합해 최종 행동, 목표 금액, 주문 수량, 주문 의도를 확정한다.

이 엔진은 종목을 새로 발굴하지 않고, Risk Engine의 하드 차단을 무시하지 않으며, 브로커 주문을 직접 전송하지 않는다.

## 2. 책임 경계

### 담당

- BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION 최종 행동 결정
- 보유 여부와 기존 포지션 상태를 반영한 진입·추가매수·축소·청산 판단
- Risk 승인 금액 안에서 목표 금액과 정수 수량 계산
- 하루 신규 진입 최대 1종목 정책 적용
- 최소 주문 금액, 최소 수량, 가격 단위 검증
- 신호·리스크·포트폴리오 적합도를 결합한 confidence 계산
- 결정 근거, 차단 사유, 정책 버전 기록
- 불변 Decision Snapshot 생성

### 담당하지 않음

- 특징량 계산 또는 시장 국면 분류
- 종목 순위 산출
- 위험 한도 변경
- 주문 유형별 브로커 세부 파라미터 확정
- 주문 전송과 체결 추적
- 회계 원장과 손익 계산

## 3. 아키텍처

```text
Ranked Signal Candidate
        +
RiskAssessment
        +
Portfolio Snapshot
        +
Decision Policy Snapshot
        +
Market / Feature Snapshot
        ↓
Decision & Position Sizing Engine
   ├─ Input Contract Validator
   ├─ Position State Resolver
   ├─ Exit / Protection Gate
   ├─ Risk Gate
   ├─ Entry Gate
   ├─ Position Size Calculator
   ├─ Quantity / Lot Rounding
   ├─ Confidence Calculator
   ├─ Daily Entry Selector
   └─ Explanation Builder
        ↓
DecisionResult / OrderIntent
        ↓
Order Engine
```

## 4. 입력 모델

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedSignal:
    symbol: str
    rank: int
    action: str
    score: float
    confidence: float
    reference_price: float
    valid_until: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RiskAssessment:
    symbol: str
    status: str
    approved_amount: float
    approved_quantity: int
    risk_score: float
    hard_blocks: tuple[str, ...]
    warnings: tuple[str, ...]
    snapshot_id: str


@dataclass(frozen=True)
class PositionState:
    symbol: str
    quantity: int
    market_value: float
    weight: float
    avg_price: float
    unrealized_pnl_pct: float
    holding_days: int


@dataclass(frozen=True)
class DecisionContext:
    run_id: str
    as_of: str
    mode: str
    portfolio_equity: float
    cash: float
    new_entries_today: int
    market_regime: str
    feature_quality: str
```

## 5. 정책 모델

```python
@dataclass(frozen=True)
class DecisionPolicy:
    strong_buy_threshold: float = 80.0
    buy_threshold: float = 65.0
    watch_threshold: float = 50.0
    sell_threshold: float = 35.0
    min_confidence_to_buy: float = 0.65
    min_order_amount: float = 100_000.0
    max_new_entries_per_day: int = 1
    stop_loss_pct: float = -0.07
    reduce_loss_pct: float = -0.04
    take_profit_pct: float = 0.12
    trailing_stop_pct: float = 0.06
    max_position_pct: float = 0.10
    allow_scale_in: bool = True
    max_scale_in_count: int = 2
```

## 6. 출력 모델

```python
@dataclass(frozen=True)
class DecisionResult:
    decision_id: str
    run_id: str
    symbol: str
    decision: str
    confidence: float
    target_amount: float
    target_quantity: int
    order_side: str | None
    order_intent: str | None
    signal_score: float
    risk_score: float
    source_signal_snapshot_id: str
    source_risk_snapshot_id: str
    policy_snapshot_id: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    decision_hash: str
```

### 최종 결정 값

| 결정 | 의미 |
|---|---|
| BUY | 신규 매수 또는 승인된 추가매수 |
| HOLD | 보유 유지 또는 관망 |
| REDUCE | 일부 수량 축소 |
| SELL | 전량 청산 |
| REJECT | 신호가 있으나 위험 또는 정책 조건 미충족 |
| NO_ACTION | 유효한 주문 행동이 없음 |

### 주문 의도

| Order Intent | 의미 |
|---|---|
| OPEN | 신규 포지션 진입 |
| ADD | 기존 포지션 추가매수 |
| REDUCE | 일부 축소 |
| CLOSE | 전량 청산 |
| NONE | 주문 없음 |

## 7. 규칙 우선순위

결정은 아래 순서를 고정한다.

1. 입력·시점·스냅샷 유효성 검사
2. 보유 포지션의 강제 청산·보호 규칙
3. Risk Engine의 `FORCE_EXIT` 또는 `FORCE_REDUCE`
4. Risk Engine 하드 차단
5. 보유 포지션의 일반 SELL/REDUCE 규칙
6. 신규 진입 가능 횟수 검사
7. STRONG_BUY/BUY 진입 규칙
8. HOLD/NO_ACTION 규칙

상위 규칙이 성립하면 하위 규칙은 평가하지 않는다.

## 8. 핵심 알고리즘

### 8.1 입력 계약 검증

다음 조건은 계산 전에 차단한다.

- Signal과 Risk의 종목 코드 불일치
- Signal 또는 Risk Snapshot이 현재 run과 불일치
- 신호 만료
- 가격 0 이하
- 정책 스냅샷 누락
- Feature 품질 `INVALID`
- Risk 상태 또는 결정 값이 허용 enum에 없음

### 8.2 보유 포지션 보호 규칙

```python
if risk.status == "FORCE_EXIT":
    return SELL

if position.quantity > 0 and position.unrealized_pnl_pct <= policy.stop_loss_pct:
    return SELL

if risk.status == "FORCE_REDUCE":
    return REDUCE

if position.quantity > 0 and position.unrealized_pnl_pct <= policy.reduce_loss_pct:
    if signal.score < policy.watch_threshold:
        return REDUCE

if position.quantity > 0 and position.unrealized_pnl_pct >= policy.take_profit_pct:
    if signal.score < policy.buy_threshold:
        return REDUCE
```

Trailing stop은 별도 최고가 상태가 제공될 때 적용한다.

```python
trailing_drawdown = current_price / highest_price_since_entry - 1
if trailing_drawdown <= -policy.trailing_stop_pct:
    return SELL
```

### 8.3 Risk Gate

```python
if risk.status == "BLOCKED" or risk.hard_blocks:
    decision = "REJECT" if signal.score >= policy.buy_threshold else "NO_ACTION"
```

Risk가 승인한 금액과 수량은 절대 상향하지 않는다.

### 8.4 진입 조건

신규 진입은 다음을 모두 충족해야 한다.

- `signal.action`이 `STRONG_BUY` 또는 `BUY`
- signal score가 `buy_threshold` 이상
- signal confidence가 `min_confidence_to_buy` 이상
- Risk 상태가 `APPROVED` 또는 `APPROVED_REDUCED`
- 승인 수량 1주 이상
- 하루 신규 진입 수가 정책 한도 미만
- Feature 품질이 `VALID` 또는 허용된 `DEGRADED`
- 시장 국면이 `LIQUIDITY_STRESS`가 아님

### 8.5 목표 금액 계산

```python
signal_strength = min(1.0, max(0.0, (signal.score - 50.0) / 50.0))
confidence_factor = min(1.0, max(0.0, signal.confidence))
regime_factor = {
    "BULL": 1.00,
    "RECOVERY": 0.85,
    "SIDEWAY": 0.70,
    "BEAR": 0.50,
    "HIGH_VOL": 0.40,
    "UNKNOWN": 0.30,
    "LIQUIDITY_STRESS": 0.00,
}[context.market_regime]

raw_target = (
    context.portfolio_equity
    * policy.max_position_pct
    * signal_strength
    * confidence_factor
    * regime_factor
)

target_amount = min(raw_target, risk.approved_amount)
```

기존 보유 종목의 추가매수는 현재 시장가치만큼 차감한다.

```python
incremental_target = max(0.0, target_amount - position.market_value)
```

### 8.6 수량 계산

```python
quantity_by_amount = int(target_amount // signal.reference_price)
quantity = min(quantity_by_amount, risk.approved_quantity)
approved_amount = quantity * signal.reference_price
```

다음 조건이면 주문을 만들지 않는다.

- `quantity < 1`
- `approved_amount < min_order_amount`
- 매수 후 목표 비중이 현재 비중보다 증가하지 않음

### 8.7 축소·청산 수량

```python
if decision == "SELL":
    target_quantity = position.quantity

elif decision == "REDUCE":
    reduce_ratio = 0.50
    if risk.status == "FORCE_REDUCE":
        reduce_ratio = 0.50
    elif position.unrealized_pnl_pct <= policy.reduce_loss_pct:
        reduce_ratio = 0.33
    elif position.unrealized_pnl_pct >= policy.take_profit_pct:
        reduce_ratio = 0.50

    target_quantity = max(1, int(position.quantity * reduce_ratio))
```

### 8.8 Confidence 계산

```python
signal_quality = signal.score / 100.0
risk_quality = 1.0 - risk.risk_score / 100.0
portfolio_fit = 1.0 - min(1.0, position.weight / policy.max_position_pct)
regime_fit = regime_factor

confidence = (
    signal_quality * 0.45
    + signal.confidence * 0.20
    + risk_quality * 0.20
    + portfolio_fit * 0.10
    + regime_fit * 0.05
)
```

하드 차단, 만료 신호, 품질 불량 상태에서는 confidence와 무관하게 주문을 만들지 않는다.

### 8.9 하루 1종목 선정

복수 후보는 순위 순으로 평가하며, 최초로 BUY 조건을 통과한 1종목만 신규 진입한다.

```text
ranked candidates
→ 기존 보유 종목의 SELL/REDUCE 먼저 처리
→ 신규 후보를 rank 오름차순으로 평가
→ 첫 APPROVED BUY 확정
→ 이후 신규 후보는 DAILY_ENTRY_LIMIT로 NO_ACTION
```

매도·축소는 신규 진입 횟수에 포함하지 않는다.

## 9. 의사결정 매트릭스

| 포지션 | Signal | Risk | 결과 |
|---|---|---|---|
| 없음 | STRONG_BUY/BUY | APPROVED | BUY |
| 없음 | STRONG_BUY/BUY | APPROVED_REDUCED | 축소된 BUY |
| 없음 | BUY 이상 | BLOCKED | REJECT |
| 없음 | WATCH 이하 | 무관 | NO_ACTION |
| 보유 | SELL/AVOID | 승인 불필요 | SELL 또는 REDUCE |
| 보유 | HOLD | 정상 | HOLD |
| 보유 | BUY | APPROVED | ADD 또는 HOLD |
| 보유 | 무관 | FORCE_REDUCE | REDUCE |
| 보유 | 무관 | FORCE_EXIT | SELL |

## 10. 데이터베이스

### `decision_policy`

| 컬럼 | 설명 |
|---|---|
| policy_id | 정책 ID |
| version | 정책 버전 |
| mode | BACKTEST/PAPER/LIVE_BLOCKED/LIVE |
| status | DRAFT/APPROVED/ACTIVE/RETIRED |
| policy_json | threshold와 sizing 설정 |
| approved_by | 승인자 |
| created_at | 생성 시각 |

### `decision_snapshot`

| 컬럼 | 설명 |
|---|---|
| snapshot_id | 불변 스냅샷 ID |
| run_id | 실행 ID |
| policy_snapshot_id | 정책 스냅샷 |
| signal_snapshot_id | Signal 원천 |
| risk_snapshot_id | Risk 원천 |
| portfolio_snapshot_id | 포트폴리오 원천 |
| market_snapshot_id | 시장 원천 |
| snapshot_hash | 무결성 해시 |
| created_at | 생성 시각 |

### `decision_result`

| 컬럼 | 설명 |
|---|---|
| decision_id | 결정 ID |
| snapshot_id | Decision Snapshot |
| symbol | 종목 코드 |
| rank | 후보 순위 |
| decision | 최종 행동 |
| order_intent | OPEN/ADD/REDUCE/CLOSE/NONE |
| target_amount | 목표 금액 |
| target_quantity | 목표 수량 |
| confidence | 최종 confidence |
| signal_score | 원천 Signal 점수 |
| risk_score | 원천 Risk 점수 |
| reason_json | 판단 근거 |
| warning_json | 경고 |
| decision_hash | 결과 해시 |
| created_at | 생성 시각 |

### `decision_event`

| 컬럼 | 설명 |
|---|---|
| event_id | 이벤트 ID |
| decision_id | 결정 ID |
| event_type | CREATED/VALIDATED/REJECTED/SELECTED/EXPIRED |
| payload_json | 이벤트 상세 |
| created_at | 생성 시각 |

## 11. 표준 사유 코드

### BUY/ADD

- `SIGNAL_THRESHOLD_MET`
- `SIGNAL_CONFIDENCE_MET`
- `RISK_APPROVED`
- `RISK_AMOUNT_REDUCED`
- `TOP_RANKED_CANDIDATE`
- `POSITION_CAPACITY_AVAILABLE`

### HOLD/NO_ACTION

- `SIGNAL_WATCH_ONLY`
- `INSUFFICIENT_CONFIDENCE`
- `MIN_ORDER_NOT_MET`
- `NO_INCREMENTAL_CAPACITY`
- `DAILY_ENTRY_LIMIT`
- `SIGNAL_EXPIRED`

### REJECT

- `RISK_HARD_BLOCK`
- `INVALID_FEATURE_QUALITY`
- `SNAPSHOT_MISMATCH`
- `LIQUIDITY_STRESS`
- `INVALID_PRICE`

### REDUCE/SELL

- `STOP_LOSS_TRIGGERED`
- `TRAILING_STOP_TRIGGERED`
- `TAKE_PROFIT_PROTECTION`
- `WEAKENING_SIGNAL`
- `RISK_FORCE_REDUCE`
- `RISK_FORCE_EXIT`

## 12. 참조 코드

```python
class DecisionPositionSizingEngine:
    def decide(
        self,
        signal: RankedSignal,
        risk: RiskAssessment,
        position: PositionState,
        context: DecisionContext,
        policy: DecisionPolicy,
    ) -> DecisionResult:
        self._validate_contract(signal, risk, context)

        protection = self._evaluate_protection(signal, risk, position, policy)
        if protection is not None:
            return protection

        if risk.status == "BLOCKED" or risk.hard_blocks:
            return self._reject_or_no_action(signal, risk, context, policy)

        if position.quantity > 0:
            existing = self._evaluate_existing_position(signal, risk, position, context, policy)
            if existing is not None:
                return existing

        if context.new_entries_today >= policy.max_new_entries_per_day:
            return self._no_action("DAILY_ENTRY_LIMIT")

        if not self._entry_signal_valid(signal, policy):
            return self._no_action("SIGNAL_THRESHOLD_NOT_MET")

        target_amount = self._calculate_target_amount(signal, risk, position, context, policy)
        quantity = min(
            int(target_amount // signal.reference_price),
            risk.approved_quantity,
        )
        amount = quantity * signal.reference_price

        if quantity < 1 or amount < policy.min_order_amount:
            return self._no_action("MIN_ORDER_NOT_MET")

        return self._buy_result(
            signal=signal,
            risk=risk,
            position=position,
            context=context,
            policy=policy,
            amount=amount,
            quantity=quantity,
        )
```

## 13. 불변식

- Decision의 매수 금액은 Risk 승인 금액을 초과할 수 없다.
- Decision의 매수 수량은 Risk 승인 수량을 초과할 수 없다.
- Risk 하드 차단이 있으면 BUY/ADD가 나올 수 없다.
- SELL 수량은 보유 수량을 초과할 수 없다.
- 신규 진입은 하루 최대 1종목이다.
- `NO_ACTION`, `HOLD`, `REJECT`는 주문 수량이 0이다.
- 동일 입력 스냅샷과 정책은 동일한 결과와 해시를 생성한다.
- 만료되거나 서로 다른 run의 스냅샷은 결합할 수 없다.
- Decision 결과는 원천 Signal, Risk, Portfolio, Policy Snapshot을 모두 참조한다.

## 14. 테스트 계획

### 단위 테스트

- 강한 신호와 Risk 승인 시 BUY
- 승인 금액이 축소되면 BUY 수량도 축소
- Risk 하드 차단 시 REJECT
- WATCH 신호는 NO_ACTION
- 보유 종목의 stop loss는 SELL
- take profit 이후 신호 약화 시 REDUCE
- FORCE_REDUCE와 FORCE_EXIT 우선 적용
- 신호 confidence 미달 시 NO_ACTION
- 최소 주문 금액 미달 시 NO_ACTION
- 수량은 정수 단위로 절삭
- Risk 승인 금액과 수량을 초과하지 않음
- 하루 신규 진입 한도 적용

### 계약 테스트

- Signal/Risk symbol 불일치 차단
- run ID 또는 snapshot ID 불일치 차단
- 만료 신호 차단
- 누락 정책 스냅샷 차단
- 잘못된 enum 차단

### 통합 테스트

- Feature → Signal → Risk → Decision 전체 fixture 실행
- 복수 후보 중 상위 1종목만 BUY
- 보유 포지션 SELL과 신규 BUY가 같은 날 함께 처리됨
- Decision 결과가 Order Engine 입력 계약과 일치
- Report Engine이 이유 코드와 confidence를 표시
- Audit Engine이 원천 스냅샷 계보를 검증

### 속성 기반 테스트

무작위 포트폴리오와 후보를 생성해 다음을 검증한다.

- BUY 금액과 수량은 항상 Risk 승인 이하
- SELL 수량은 항상 보유 수량 이하
- 하드 차단 상태에서 BUY가 절대 생성되지 않음
- 하루 신규 BUY 수가 정책 한도를 초과하지 않음
- 동일 입력은 동일 결정 생성

### 실패 주입 테스트

- Risk Repository 조회 실패
- 정책 스냅샷 조회 실패
- 가격 NaN/0/음수
- Signal 만료 경계 시각
- DB 저장 실패 시 Order Engine 호출 금지
- hash 생성 실패 시 결정 확정 금지

### 회귀 테스트

- 기존 `strategy/candidate.py` 점수 결과를 Signal adapter로 입력
- 기존 Risk Engine 결과를 새 RiskAssessment로 매핑
- 기존 Position/Entry/Exit 결정과 새 엔진 결과 비교
- 동일 fixture에서 정책 변경 전후 결과 차이 기록

## 15. 코드 구조 계획

```text
decision/
  __init__.py
  engine.py
  models.py
  policy.py
  sizing.py
  protection.py
  selector.py
  explanation.py
  repository.py

core/
  decision_adapter.py

tests/
  test_decision_engine.py
  test_position_sizing.py
  test_decision_protection.py
  test_decision_contract.py
  test_daily_entry_selector.py
  test_decision_integration.py
```

## 16. 구현 순서

1. 입력·출력 dataclass와 enum 구현
2. 순수 함수 기반 수량·금액 계산기 구현
3. Risk Gate와 보호 규칙 구현
4. 하루 신규 진입 selector 구현
5. SQLite Repository와 snapshot hash 구현
6. 기존 Candidate/Risk/Position/Entry/Exit adapter 작성
7. 고정 CSV fixture 통합 테스트
8. Order Engine에 `OrderIntent` 연결
9. Report/Audit 계보 검증

## 17. 완료 기준

- Signal, Risk, Portfolio, Policy 입력으로 결정론적 DecisionResult 생성
- Risk 하드 차단을 우회할 수 없음
- 목표 금액과 수량이 모든 Risk 승인 한도 이내
- 보유 포지션의 SELL/REDUCE 보호 규칙 동작
- 하루 최대 1종목 신규 진입 보장
- Decision Snapshot과 원천 계보 저장
- 단위·계약·통합·속성 기반 테스트 통과
- Order Engine이 결과를 변형하지 않고 주문 요청으로 변환 가능

## 18. 다음 설계 대상

다음은 **Order Validation & Routing Engine v2**를 설계한다. 기존 Order Engine v1을 확장해 시장별 호가 단위, 주문 유효시간, 중복·재전송·승인 만료, 브로커 라우팅, 불확실 전송 결과의 `VERIFY_REQUIRED` 상태를 통합한다.
