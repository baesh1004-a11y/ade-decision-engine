# Paper Trading & Portfolio Continuity Engine v1

## 1. 목적

이 엔진은 ADE의 일일 종목평가 결과를 실제 주문 없이 가상 포트폴리오에 연속 반영한다. 전일 포트폴리오를 다음 거래일로 이어받고, 공식 가격·가상 체결·수수료·세금·기업행동·벤치마크를 동일한 규칙으로 처리하여 재현 가능한 PAPER 운용 원장을 만든다.

이 엔진은 새로운 Signal, Risk 또는 Decision을 생성하지 않는다. 확정된 Decision/Exit/OrderIntent를 모의 체결하고 포트폴리오 상태를 전이시키는 실행·회계 경계다.

## 2. 책임 경계

### 수행

- 전일 PAPER 포트폴리오 스냅샷 로딩
- 거래일·시장 세션 확인
- Decision과 OrderIntent 계약 검증
- 종가 또는 정책 지정 가격을 이용한 결정론적 가상 체결
- 현금, 포지션, 평균단가, 실현·미실현 손익 갱신
- 레버리지 없음, 최소 현금, 종목당 비중, 하루 신규 1종목 제약 재검증
- NO_ACTION/HOLD도 불변 일일 기록으로 저장
- 수수료·세금·슬리피지 정책 적용
- 기업행동과 종목코드 변경 반영
- KOSPI/KODEX 200 벤치마크 기준가와 상대성과 연결
- 다음 거래일의 기준 PortfolioSnapshot 발행

### 수행하지 않음

- 후보 종목 탐색
- Signal 점수 산출
- Risk 승인 또는 hard block 변경
- 매수·매도 행동 생성
- 실브로커 호출
- 공식 종가가 없는 상태에서 임의 가격 추정
- 이전 일자의 확정 원장 덮어쓰기

## 3. 기본 운용 정책

```text
initial_cash_krw        = 10_000_000
leverage_allowed        = false
minimum_cash_ratio      = 0.10
maximum_symbol_weight   = 0.10
maximum_new_entries_day = 1
fractional_shares       = false
base_currency           = KRW
fill_policy              = OFFICIAL_CLOSE
no_candidate_action      = NO_ACTION
```

정책은 `policy_version`과 hash로 스냅샷에 고정한다. 정책 변경은 과거 원장에 소급 적용하지 않는다.

## 4. 아키텍처

```text
Scheduler / Trading Calendar
            +
Validated Decision / Exit Proposal / OrderIntent
            +
Official Close Price Snapshot
            +
Previous Paper Portfolio Snapshot
            ↓
Paper Trading & Portfolio Continuity Engine
   ├─ Session Guard
   ├─ Input Lineage Guard
   ├─ Constraint Pre-check
   ├─ Deterministic Fill Simulator
   ├─ Cost / Tax Calculator
   ├─ Position & Cash Ledger Writer
   ├─ Corporate Action Adjuster
   ├─ Benchmark Tracker
   ├─ Daily Return Calculator
   └─ Continuity Snapshot Publisher
            ↓
Portfolio Accounting & Performance
Report / Explainability / Monitoring / Audit
```

## 5. 입력 계약

### PaperRunRequest

```python
@dataclass(frozen=True)
class PaperRunRequest:
    run_id: str
    portfolio_id: str
    trade_date: date
    market: str
    previous_snapshot_id: str
    decision_snapshot_id: str
    order_intent_ids: tuple[str, ...]
    price_snapshot_id: str
    benchmark_snapshot_id: str
    policy_snapshot_id: str
```

필수 검증:

1. `trade_date`가 한국거래소 거래일이어야 한다.
2. 모든 입력이 동일 run 또는 명시적으로 연결된 lineage에 속해야 한다.
3. 가격 스냅샷은 장 마감 확정 상태여야 한다.
4. 이전 스냅샷은 동일 portfolio의 직전 확정 거래일이어야 한다.
5. Decision/OrderIntent가 만료되지 않았고 Risk 승인 범위를 초과하지 않아야 한다.

## 6. 출력 계약

### PaperRunResult

```python
@dataclass(frozen=True)
class PaperRunResult:
    paper_run_id: str
    status: str
    trade_date: date
    action: str
    fills: tuple["PaperFill", ...]
    ending_snapshot_id: str
    daily_return: Decimal
    cumulative_return: Decimal
    benchmark_daily_return: Decimal
    excess_return: Decimal
    evidence_hash: str
    reason_codes: tuple[str, ...]
```

상태:

- `COMPLETED`
- `NO_ACTION_RECORDED`
- `BLOCKED_MISSING_PRICE`
- `BLOCKED_LINEAGE_MISMATCH`
- `BLOCKED_CONSTRAINT_VIOLATION`
- `MANUAL_REVIEW`

## 7. 데이터베이스

### 7.1 paper_portfolios

```sql
CREATE TABLE paper_portfolios (
    portfolio_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_currency TEXT NOT NULL DEFAULT 'KRW',
    initial_cash_krw INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    policy_version TEXT NOT NULL
);
```

### 7.2 paper_runs

```sql
CREATE TABLE paper_runs (
    paper_run_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    run_id TEXT NOT NULL,
    previous_snapshot_id TEXT,
    decision_snapshot_id TEXT NOT NULL,
    price_snapshot_id TEXT NOT NULL,
    benchmark_snapshot_id TEXT NOT NULL,
    policy_snapshot_id TEXT NOT NULL,
    status TEXT NOT NULL,
    action TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(portfolio_id, trade_date),
    FOREIGN KEY(portfolio_id) REFERENCES paper_portfolios(portfolio_id)
);
```

### 7.3 paper_orders / paper_fills

```sql
CREATE TABLE paper_orders (
    paper_order_id TEXT PRIMARY KEY,
    paper_run_id TEXT NOT NULL,
    order_intent_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    requested_qty INTEGER NOT NULL,
    approved_qty INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason_code TEXT,
    UNIQUE(paper_run_id, order_intent_id)
);

CREATE TABLE paper_fills (
    paper_fill_id TEXT PRIMARY KEY,
    paper_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    fill_price_krw INTEGER NOT NULL,
    fill_qty INTEGER NOT NULL,
    gross_amount_krw INTEGER NOT NULL,
    fee_krw INTEGER NOT NULL,
    tax_krw INTEGER NOT NULL,
    slippage_krw INTEGER NOT NULL,
    net_cash_effect_krw INTEGER NOT NULL,
    price_source TEXT NOT NULL,
    price_asof TEXT NOT NULL,
    fill_hash TEXT NOT NULL,
    UNIQUE(paper_order_id, fill_hash)
);
```

### 7.4 paper_cash_ledger / paper_position_ledger

모든 변경은 append-only event로 기록한다.

```sql
CREATE TABLE paper_cash_ledger (
    cash_event_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    paper_run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    amount_krw INTEGER NOT NULL,
    balance_after_krw INTEGER NOT NULL,
    source_ref TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_position_ledger (
    position_event_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    paper_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    quantity_delta INTEGER NOT NULL,
    quantity_after INTEGER NOT NULL,
    average_cost_after_krw INTEGER NOT NULL,
    realized_pnl_krw INTEGER NOT NULL,
    source_ref TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 7.5 paper_portfolio_snapshots

```sql
CREATE TABLE paper_portfolio_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    cash_krw INTEGER NOT NULL,
    market_value_krw INTEGER NOT NULL,
    total_equity_krw INTEGER NOT NULL,
    daily_pnl_krw INTEGER NOT NULL,
    cumulative_pnl_krw INTEGER NOT NULL,
    daily_return TEXT NOT NULL,
    cumulative_return TEXT NOT NULL,
    cash_ratio TEXT NOT NULL,
    benchmark_level TEXT NOT NULL,
    benchmark_cumulative_return TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    is_final INTEGER NOT NULL DEFAULT 0,
    UNIQUE(portfolio_id, trade_date)
);
```

추가 테이블:

- `paper_positions`
- `paper_daily_metrics`
- `paper_benchmark_observations`
- `paper_corporate_actions`
- `paper_adjustment_events`

## 8. 핵심 알고리즘

### 8.1 일일 실행 순서

```text
1. 거래일 확인
2. 직전 final snapshot 로딩
3. 입력 lineage와 hash 검증
4. 기업행동 선반영
5. Exit/SELL/REDUCE를 먼저 시뮬레이션
6. 매도 후 현금·포지션 임시 상태 계산
7. 신규 BUY 후보를 Decision 우선순위로 정렬
8. 하루 신규 1종목 제한 적용
9. 종목당 10%, 최소 현금 10%, 레버리지 금지 검증
10. 공식 종가와 비용 정책으로 가상 체결
11. ledger event 원자적 저장
12. 종가 평가와 일간·누적 수익률 계산
13. 벤치마크 상대성과 계산
14. final snapshot과 evidence hash 발행
```

### 8.2 매수 가능 수량

```python
max_symbol_value = floor(total_equity_before * max_symbol_weight)
cash_buffer = ceil(total_equity_before * minimum_cash_ratio)
spendable_cash = max(0, cash_before - cash_buffer)
risk_cap = min(decision.approved_amount, max_symbol_value, spendable_cash)
unit_cost = close_price + estimated_fee_per_share + slippage_per_share
quantity = min(decision.approved_qty, floor(risk_cap / unit_cost))
```

수량이 0이면 `NO_ACTION`이 아니라 기존 BUY 요청에 대한 `BLOCKED_CONSTRAINT_VIOLATION`으로 기록한다.

### 8.3 매도 손익

```python
realized_pnl = (fill_price - average_cost) * fill_qty - fee - tax - slippage
new_qty = old_qty - fill_qty
new_average_cost = 0 if new_qty == 0 else old_average_cost
```

매도 수량은 보유수량과 매도가능수량을 초과할 수 없다.

### 8.4 수익률

```text
daily_return = (ending_equity - beginning_equity - external_cash_flow)
               / beginning_equity

cumulative_return = ending_equity / initial_cash - 1

benchmark_daily_return = benchmark_close_t / benchmark_close_t-1 - 1
excess_return = daily_return - benchmark_daily_return
```

외부 입출금은 기본 정책상 금지한다. 허용할 경우 별도 cash-flow event로 분리한다.

### 8.5 NO_ACTION 연속성

유효 후보가 없거나 모든 후보가 Risk에서 차단된 날에도 `paper_runs`, `paper_daily_metrics`, `paper_portfolio_snapshots`를 생성한다. 보유 포지션은 당일 종가로 평가하고 현금은 그대로 유지한다.

## 9. 기업행동

우선 지원:

- 현금배당
- 주식분할·병합
- 무상증자
- 종목코드 변경
- 상장폐지·거래정지

기업행동은 원본 fill을 수정하지 않고 `paper_adjustment_events`를 추가한다. 데이터가 불완전하면 자동 추정하지 않고 `MANUAL_REVIEW`로 격리한다.

## 10. 코드 구조

```text
paper_trading/
├── models.py
├── contracts.py
├── calendar.py
├── pricing.py
├── constraints.py
├── fills.py
├── costs.py
├── corporate_actions.py
├── ledger.py
├── performance.py
├── benchmark.py
├── hashing.py
├── repository.py
└── engine.py
```

### 최소 엔진 골격

```python
class PaperTradingEngine:
    def run(self, request: PaperRunRequest) -> PaperRunResult:
        previous = self.repository.get_final_snapshot(
            request.portfolio_id, request.previous_snapshot_id
        )
        self.contracts.validate(request, previous)
        prices = self.pricing.load_final_prices(request.price_snapshot_id)
        working = self.corporate_actions.apply(previous, request.trade_date)

        intents = self.repository.get_validated_intents(request.order_intent_ids)
        exits, entries = self.constraints.partition_and_validate(intents, working, prices)
        fills = self.fills.simulate(exits + entries, working, prices)
        ending = self.ledger.apply_atomically(request, working, fills)
        metrics = self.performance.calculate(previous, ending, request.benchmark_snapshot_id)
        return self.repository.finalize(request, fills, ending, metrics)
```

## 11. 안전 불변식

```text
ending_cash >= 0
cash_ratio >= 10% after every BUY
symbol_weight <= 10% after execution
new_symbols_bought_per_day <= 1
fill_qty <= approved_qty
sell_fill_qty <= sellable_qty
same order_intent_id is filled at most once per paper run
same portfolio/date has exactly one final snapshot
NO_ACTION creates zero fills
unfinalized price snapshot creates zero fills
past final ledger events are never updated or deleted
```

## 12. 테스트 계획

### 단위 테스트

- 종목당 10% 한도로 매수수량 축소
- 최소 현금 10% 보존
- 하루 두 번째 신규 종목 차단
- 기존 보유 종목 추가매수와 신규 종목 구분
- 보유수량 초과 매도 거부
- 수수료·세금·슬리피지 반영
- 평균단가와 실현손익 계산
- NO_ACTION 스냅샷 생성
- 벤치마크 일간·누적 수익률 계산
- 공식 종가 누락 시 zero fill

### 통합 fixture

A. 초기 1천만원 → 삼성전자 3주 매수

B. 다음 거래일 HOLD → 종가 평가만 수행

C. 유효 후보 없음 → NO_ACTION, 현금·포지션 연속 유지

D. 손절선 이탈 → FORCE_EXIT 전량 매도

E. 급락장 → 신규 BUY 전면 차단, 현금 100% 유지

F. 두 BUY 후보 → 상위 1종목만 체결

G. 매수 후 현금 9% 예상 → 수량 축소 또는 차단

H. 종목 비중 10% 초과 예상 → 수량 축소

### 속성 테스트

- 모든 BUY 이후 현금비중은 최소 기준 이상
- 모든 snapshot의 총자산은 현금 + 포지션 평가액과 일치
- ledger event 합계는 snapshot 잔액과 일치
- 동일 입력을 재실행하면 동일 fill/snapshot hash
- 입력 순서를 바꿔도 canonical 결과는 동일
- 한 입력 hash가 달라지면 evidence hash도 달라짐
- 거래일 사이 누락 snapshot이 있으면 자동 연결하지 않고 차단

### 장애 테스트

- DB 트랜잭션 중단 시 fill과 ledger가 부분 저장되지 않음
- 중복 run 요청은 기존 final 결과를 반환하거나 명시적으로 거부
- 가격 데이터 지연·정정 시 final 전에는 재계산 가능, final 후에는 adjustment event만 허용
- 기업행동 데이터 충돌 시 MANUAL_REVIEW

## 13. 구현 우선순위

```text
1. 불변 모델과 SQLite migration
2. PortfolioSnapshot repository
3. 제약 계산 순수 함수
4. 종가 기반 Deterministic Fill Simulator
5. Cash/Position append-only ledger
6. 일간·누적·벤치마크 성과 계산
7. NO_ACTION/HOLD/BUY/FORCE_EXIT fixture
8. corporate action 최소 지원
9. Report Engine JSON adapter
10. Strategy Monitoring용 PAPER metric adapter
```

## 14. 완료 기준

- 10개 연속 거래일 fixture가 전일 상태를 정확히 이어간다.
- 재실행 시 금액·수량·수익률·hash가 동일하다.
- 정책 위반 체결이 0건이다.
- NO_ACTION 날도 완전한 일일 보고 자료가 생성된다.
- Portfolio Accounting, Explainability, Report, Monitoring이 동일 snapshot ID를 참조한다.
- 실브로커 호출 수가 항상 0이다.
