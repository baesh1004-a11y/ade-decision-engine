# Portfolio Accounting & Performance Engine v1

## 1. 목적

Portfolio Accounting & Performance Engine은 ADE가 생성한 주문·체결·현금흐름을 일관된 회계 규칙으로 기록하고, 계좌·포트폴리오·전략별 포지션, 손익, 수익률, 벤치마크 대비 성과를 계산하는 계층이다.

이 엔진은 종목을 선택하거나 주문을 생성하지 않는다. Execution Engine이 확정한 체결과 외부 현금흐름을 회계 이벤트로 받아 다음 결과를 제공한다.

- 현금 및 결제 예정 현금
- 종목별 보유 수량과 가용 수량
- 평균 취득단가와 세금 원가
- 실현·미실현 손익
- 수수료, 세금, 이자, 배당
- 순자산가치(NAV)와 총자산가치(GAV)
- 일간·누적·기간 수익률
- 벤치마크 대비 초과수익률
- 회전율, 최대낙폭, 변동성, Sharpe 등 성과 지표
- 가상투자, PAPER, BACKTEST, LIVE 모드 간 동일한 회계 결과

핵심 설계 목표는 **원장 우선(ledger-first), 이벤트 재생 가능, 결정론적 계산, 이중 계산 검증, 과거 수정 금지**다.

---

## 2. 책임 경계

### 담당

- 체결, 입출금, 배당, 수수료, 세금, 이자, 분할·병합 등 회계 이벤트 기록
- 복식부기 원장 생성
- 계좌·포트폴리오·전략·종목별 포지션 계산
- 평균단가와 lot 기반 원가 계산
- 실현·미실현 손익 계산
- T+N 결제 예정 현금 및 수량 관리
- 시장가치, GAV, NAV 계산
- 수익률과 벤치마크 성과 계산
- 회계 일 마감과 불변 스냅샷 생성
- 체결 원장, 현금 원장, 포지션 스냅샷 간 대사
- 가상투자 일일 성과 상태 저장
- Audit & Compliance용 증거와 계산 근거 제공

### 담당하지 않음

- Signal, Risk, Decision 생성
- 주문 가격·수량 결정
- 주문 전송과 체결 여부 판단
- 시장 데이터 품질 평가
- 브로커 원장 자체의 수정
- 기업행동 원천 데이터 수집
- 세법 해석이나 세무 신고
- 투자 성과에 대한 설명문 작성

Portfolio Accounting은 **무엇을 보유하고 얼마를 벌거나 잃었는지** 계산하며, Decision Engine은 **무엇을 보유해야 하는지** 결정한다.

---

## 3. 핵심 설계 원칙

### 3.1 체결이 회계의 유일한 거래 입력

주문 생성, 주문 접수, 부분 체결 대기 상태는 포지션을 변경하지 않는다. 포지션과 현금은 `FILL_CONFIRMED` 이벤트에서만 변경한다.

```text
Decision → Order → Broker ACK → Fill Confirmed
                                  ↓
                         Accounting Event
                                  ↓
                   Journal Entry / Position
```

### 3.2 Append-only 원장

기존 분개는 수정하거나 삭제하지 않는다. 오류 정정은 반대 분개와 교정 분개를 추가한다.

```text
원 분개 J-100
→ REVERSAL J-101
→ CORRECTION J-102
```

### 3.3 원장과 파생 상태 분리

- 원장: 회계 사실의 영구 기록
- 포지션: 원장을 집계한 현재 상태
- 스냅샷: 특정 시점의 계산 결과
- 성과 지표: 스냅샷과 현금흐름에서 계산한 파생 결과

포지션 테이블이 손상되어도 원장 이벤트를 재생하여 복구할 수 있어야 한다.

### 3.4 모드 간 동일한 계산 코어

```text
BACKTEST Fill Simulator ─┐
PAPER Broker Adapter ────┼→ Canonical Fill → Accounting Core
LIVE Broker Adapter ─────┘
```

입력 체결의 원천만 다르고 회계 알고리즘은 동일하다.

### 3.5 통화와 소수 정밀도

- 금액은 부동소수점 `float`를 사용하지 않는다.
- Python에서는 `Decimal`을 사용한다.
- DB에는 통화별 최소 단위 정수 또는 고정 소수 문자열을 저장한다.
- 수량 정밀도는 자산 유형별 `quantity_scale`을 따른다.
- 반올림 규칙은 정책 버전에 포함한다.

---

## 4. 아키텍처

```text
Order & Execution Engine
        │ CanonicalFill
        ▼
Portfolio Accounting & Performance Engine
├─ Event Intake & Idempotency Guard
├─ Accounting Policy Resolver
├─ Journal Builder
├─ Settlement Ledger
├─ Position Lot Engine
├─ Corporate Action Processor
├─ Valuation Service
├─ NAV Calculator
├─ Return Calculator
├─ Benchmark Calculator
├─ Performance Analytics
├─ Reconciliation Service
├─ Daily Close Coordinator
└─ Accounting Repository
        │
        ├─ Accounting Event Store
        ├─ Double-entry Journal
        ├─ Position Lots
        ├─ Cash & Settlement Balances
        ├─ Valuation Snapshots
        └─ Performance Series
```

외부 연동:

```text
Configuration & Policy Engine
 └─ 원가법, 수수료, 세금, 반올림, 기준통화, 마감 정책

Data Snapshot & Lineage Engine
 └─ 평가가격 snapshot_id, FX snapshot_id, benchmark dataset_version

Scheduler & Trigger Engine
 └─ 장 마감 평가, 결제 처리, 배당 반영, 일일 성과 산출

Audit & Compliance Engine
 └─ 수동 조정, 원장 정정, 마감 재개방, 대사 불일치 감사

Report Engine
 └─ 포트폴리오 현황, 손익, 수익률, 벤치마크 비교
```

---

## 5. 회계 범위와 계층

### 5.1 계층 모델

```text
Legal Account
  └─ Portfolio
       └─ Strategy Book
            └─ Instrument Position
                 └─ Tax/Cost Lot
```

- `account_id`: 실제 또는 가상 계좌
- `portfolio_id`: 운용 목적별 자산 집합
- `strategy_id`: 전략 성과 귀속 단위
- `instrument_id`: 거래 대상
- `lot_id`: 취득 원가와 잔여 수량 추적 단위

### 5.2 가상투자 기본 계좌

ADE 일일 가상투자는 별도 계좌로 관리한다.

```text
account_id      = SIM-ADE-KR-001
portfolio_id    = ADE-DAILY-VIRTUAL
base_currency   = KRW
initial_capital = 10,000,000 KRW
leverage        = disabled
minimum_cash    = 10%
max_weight      = 10% per instrument
```

최소 현금과 최대 비중은 Risk/Decision 단계의 제약이다. Accounting Engine은 이를 변경하지 않고 실제 결과가 제약을 위반했는지 계산하여 Compliance Engine에 전달한다.

---

## 6. 표준 입력 모델

```python
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class CanonicalFill:
    fill_id: str
    order_id: str
    decision_id: str
    account_id: str
    portfolio_id: str
    strategy_id: str
    instrument_id: str
    market: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    price: Decimal
    trade_currency: str
    fee: Decimal
    tax: Decimal
    executed_at: datetime
    trade_date: date
    settlement_date: date
    broker_execution_id: str
    source_mode: Literal["BACKTEST", "PAPER", "LIVE"]
    correlation_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CashFlowEvent:
    cashflow_id: str
    account_id: str
    portfolio_id: str
    event_type: Literal[
        "DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST",
        "FEE", "TAX", "WITHHOLDING_TAX", "ADJUSTMENT"
    ]
    amount: Decimal
    currency: str
    effective_date: date
    occurred_at: datetime
    external_reference: str | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class ValuationPrice:
    instrument_id: str
    price: Decimal
    currency: str
    price_type: Literal["CLOSE", "OFFICIAL_CLOSE", "MID", "LAST", "MODEL"]
    as_of: datetime
    snapshot_id: str
    quality_status: str
```

필수 입력 검증:

- `quantity > 0`
- `price >= 0`
- `fee >= 0`, `tax >= 0`
- 동일 `fill_id`는 한 번만 처리
- 동일 `broker_execution_id` 중복 차단
- 매도 수량은 정책상 short 허용 여부 검증
- 거래일과 결제일의 시장 달력 일관성 검증
- 통화와 instrument master의 거래통화 일치 검증
- LIVE/PAPER 입력은 Execution Engine의 확정 상태만 허용

---

## 7. 회계 이벤트 모델

```text
FILL_CONFIRMED
CASH_DEPOSITED
CASH_WITHDRAWN
DIVIDEND_DECLARED
DIVIDEND_RECEIVED
INTEREST_ACCRUED
INTEREST_RECEIVED
FEE_CHARGED
TAX_WITHHELD
SETTLEMENT_COMPLETED
STOCK_SPLIT_APPLIED
REVERSE_SPLIT_APPLIED
SPINOFF_APPLIED
MERGER_APPLIED
POSITION_TRANSFERRED
JOURNAL_REVERSED
MANUAL_ADJUSTMENT
DAILY_CLOSE_COMPLETED
```

모든 이벤트는 다음 공통 필드를 가진다.

```python
@dataclass(frozen=True)
class AccountingEvent:
    event_id: str
    event_type: str
    account_id: str
    portfolio_id: str
    strategy_id: str | None
    instrument_id: str | None
    effective_at: datetime
    recorded_at: datetime
    source_type: str
    source_id: str
    idempotency_key: str
    policy_version: str
    payload: dict[str, Any]
    correlation_id: str
```

`effective_at`은 경제적 효력 시각, `recorded_at`은 시스템 기록 시각이다. 과거 이벤트가 늦게 도착하면 두 값이 다를 수 있다.

---

## 8. 복식부기 계정과목

### 8.1 최소 계정과목

| 코드 | 계정 | 유형 |
|---|---|---|
| `ASSET_CASH_AVAILABLE` | 가용 현금 | 자산 |
| `ASSET_CASH_RECEIVABLE` | 미수금 | 자산 |
| `LIAB_CASH_PAYABLE` | 미지급금 | 부채 |
| `ASSET_SECURITY_COST` | 유가증권 취득원가 | 자산 |
| `ASSET_SECURITY_MTM` | 유가증권 평가조정 | 자산 |
| `INCOME_REALIZED_PNL` | 실현손익 | 수익/비용 |
| `INCOME_UNREALIZED_PNL` | 미실현손익 | 수익/비용 |
| `INCOME_DIVIDEND` | 배당수익 | 수익 |
| `INCOME_INTEREST` | 이자수익 | 수익 |
| `EXPENSE_FEE` | 수수료 | 비용 |
| `EXPENSE_TAX` | 거래세·원천세 | 비용 |
| `EQUITY_CONTRIBUTION` | 외부 납입자본 | 자본 |
| `EQUITY_WITHDRAWAL` | 외부 인출 | 자본 |
| `SUSPENSE_RECONCILIATION` | 대사 임시계정 | 임시 |

### 8.2 매수 체결 예시

100주 × 10,000원, 수수료 1,000원, 결제 T+2:

```text
거래일
차변  ASSET_SECURITY_COST       1,000,000
차변  EXPENSE_FEE                   1,000
대변  LIAB_CASH_PAYABLE          1,001,000

결제일
차변  LIAB_CASH_PAYABLE          1,001,000
대변  ASSET_CASH_AVAILABLE       1,001,000
```

### 8.3 매도 체결 예시

보유원가 1,000,000원인 100주를 1,100,000원에 매도, 수수료·세금 4,000원:

```text
거래일
차변  ASSET_CASH_RECEIVABLE      1,096,000
차변  EXPENSE_FEE/TAX                4,000
대변  ASSET_SECURITY_COST        1,000,000
대변  INCOME_REALIZED_PNL          100,000

결제일
차변  ASSET_CASH_AVAILABLE       1,096,000
대변  ASSET_CASH_RECEIVABLE      1,096,000
```

분개는 통화별로 차변 합계와 대변 합계가 일치해야 한다.

---

## 9. 데이터베이스 설계

SQLite v1 기준이며 PostgreSQL 이전을 고려한다.

### 9.1 `ade_accounting_events`

```sql
CREATE TABLE IF NOT EXISTS ade_accounting_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    strategy_id TEXT,
    instrument_id TEXT,
    effective_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    policy_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    reversed_by_event_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (reversed_by_event_id)
        REFERENCES ade_accounting_events(event_id)
);

CREATE INDEX IF NOT EXISTS ix_accounting_events_account_effective
ON ade_accounting_events(account_id, effective_at);

CREATE INDEX IF NOT EXISTS ix_accounting_events_source
ON ade_accounting_events(source_type, source_id);
```

### 9.2 `ade_journal_entries`

```sql
CREATE TABLE IF NOT EXISTS ade_journal_entries (
    journal_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    strategy_id TEXT,
    instrument_id TEXT,
    ledger_account TEXT NOT NULL,
    debit_amount TEXT NOT NULL DEFAULT '0',
    credit_amount TEXT NOT NULL DEFAULT '0',
    currency TEXT NOT NULL,
    quantity TEXT,
    effective_at TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (event_id)
        REFERENCES ade_accounting_events(event_id),
    CHECK (debit_amount <> '0' OR credit_amount <> '0'),
    UNIQUE (event_id, sequence_no)
);

CREATE INDEX IF NOT EXISTS ix_journal_account_ledger_time
ON ade_journal_entries(account_id, ledger_account, effective_at);

CREATE INDEX IF NOT EXISTS ix_journal_instrument_time
ON ade_journal_entries(account_id, instrument_id, effective_at);
```

### 9.3 `ade_position_lots`

```sql
CREATE TABLE IF NOT EXISTS ade_position_lots (
    lot_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    opened_fill_id TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    original_quantity TEXT NOT NULL,
    remaining_quantity TEXT NOT NULL,
    unit_cost TEXT NOT NULL,
    total_cost TEXT NOT NULL,
    currency TEXT NOT NULL,
    cost_method TEXT NOT NULL,
    status TEXT NOT NULL,
    closed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    CHECK (status IN ('OPEN','PARTIALLY_CLOSED','CLOSED')),
    UNIQUE (account_id, opened_fill_id, lot_id)
);

CREATE INDEX IF NOT EXISTS ix_position_lots_open
ON ade_position_lots(account_id, portfolio_id, instrument_id, status, opened_at);
```

### 9.4 `ade_cash_balances`

```sql
CREATE TABLE IF NOT EXISTS ade_cash_balances (
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    available_amount TEXT NOT NULL,
    receivable_amount TEXT NOT NULL,
    payable_amount TEXT NOT NULL,
    reserved_amount TEXT NOT NULL,
    as_of TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, portfolio_id, currency)
);
```

### 9.5 `ade_settlement_obligations`

```sql
CREATE TABLE IF NOT EXISTS ade_settlement_obligations (
    settlement_id TEXT PRIMARY KEY,
    fill_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    cash_amount TEXT NOT NULL,
    cash_currency TEXT NOT NULL,
    quantity TEXT NOT NULL,
    direction TEXT NOT NULL,
    status TEXT NOT NULL,
    settled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (direction IN ('PAY','RECEIVE')),
    CHECK (status IN ('PENDING','SETTLED','FAILED','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS ix_settlement_due
ON ade_settlement_obligations(status, settlement_date);
```

### 9.6 `ade_position_snapshots`

```sql
CREATE TABLE IF NOT EXISTS ade_position_snapshots (
    snapshot_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    quantity TEXT NOT NULL,
    available_quantity TEXT NOT NULL,
    average_cost TEXT NOT NULL,
    cost_value TEXT NOT NULL,
    market_price TEXT NOT NULL,
    market_value TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    realized_pnl_to_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    valuation_price_snapshot_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, strategy_id, instrument_id)
);
```

### 9.7 `ade_portfolio_valuations`

```sql
CREATE TABLE IF NOT EXISTS ade_portfolio_valuations (
    valuation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    valuation_date TEXT NOT NULL,
    as_of TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    cash_value TEXT NOT NULL,
    security_market_value TEXT NOT NULL,
    receivable_value TEXT NOT NULL,
    payable_value TEXT NOT NULL,
    accrued_income TEXT NOT NULL,
    gav TEXT NOT NULL,
    nav TEXT NOT NULL,
    external_flow TEXT NOT NULL,
    fee_total TEXT NOT NULL,
    tax_total TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    price_snapshot_id TEXT NOT NULL,
    fx_snapshot_id TEXT,
    calculation_version TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (account_id, portfolio_id, valuation_date, calculation_version),
    CHECK (status IN ('PRELIMINARY','FINAL','RESTATED'))
);
```

### 9.8 `ade_performance_series`

```sql
CREATE TABLE IF NOT EXISTS ade_performance_series (
    performance_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    frequency TEXT NOT NULL,
    return_method TEXT NOT NULL,
    portfolio_return TEXT NOT NULL,
    cumulative_return TEXT NOT NULL,
    benchmark_id TEXT,
    benchmark_return TEXT,
    excess_return TEXT,
    nav_start TEXT NOT NULL,
    nav_end TEXT NOT NULL,
    net_external_flow TEXT NOT NULL,
    volatility TEXT,
    sharpe_ratio TEXT,
    max_drawdown TEXT,
    turnover TEXT,
    calculation_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (account_id, portfolio_id, period_end, frequency, calculation_version)
);
```

### 9.9 `ade_reconciliation_results`

```sql
CREATE TABLE IF NOT EXISTS ade_reconciliation_results (
    reconciliation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    business_date TEXT NOT NULL,
    reconciliation_type TEXT NOT NULL,
    internal_value TEXT NOT NULL,
    external_value TEXT NOT NULL,
    difference_value TEXT NOT NULL,
    tolerance_value TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    CHECK (status IN ('MATCHED','WARNING','BREAK','RESOLVED'))
);
```

---

## 10. 상태 모델

### 10.1 회계 이벤트

```text
RECEIVED → VALIDATED → POSTED
                   ├→ REJECTED
                   └→ QUARANTINED

POSTED → REVERSED
```

### 10.2 일일 평가

```text
NOT_STARTED → PRICE_LOCKED → CALCULATED → RECONCILED → FINAL
                                   ├→ FAILED
                                   └→ RESTATEMENT_REQUIRED
```

`FINAL` 평가를 변경하지 않는다. 정정 데이터나 늦은 체결이 발생하면 새로운 계산 버전으로 `RESTATED` 결과를 생성한다.

---

## 11. 원가 계산 정책

지원 방식:

- `WEIGHTED_AVERAGE`: 이동평균법
- `FIFO`: 선입선출
- `LIFO`: 후입선출, 일반 운용 성과용 선택 사항
- `SPECIFIC_LOT`: 지정 lot, 운영자 또는 주문 메타데이터 필요

v1 기본값:

```text
KR equity virtual/PAPER = WEIGHTED_AVERAGE
BACKTEST                = WEIGHTED_AVERAGE
LIVE tax reporting      = external broker statement authoritative
```

### 11.1 이동평균 매수

기존 수량 `Q0`, 기존 원가 `C0`, 신규 수량 `Q1`, 신규 총원가 `C1`:

```text
new_quantity = Q0 + Q1
new_cost     = C0 + C1
average_cost = new_cost / new_quantity
```

매수 수수료를 원가에 포함할지 비용 처리할지는 정책으로 고정한다. 성과 분석 기본값은 수수료를 비용으로 별도 인식하고, 세무 원가는 별도 필드로 관리한다.

### 11.2 이동평균 매도

매도 수량 `Qs`, 평균원가 `Pavg`, 매도가 `Ps`:

```text
released_cost = Qs × Pavg
sale_proceeds = Qs × Ps
realized_pnl  = sale_proceeds - released_cost - fee - tax
```

### 11.3 부분 체결

각 fill은 독립 이벤트로 처리한다. 동일 주문의 여러 체결은 주문 단위가 아니라 fill 단위로 순서대로 원장에 반영한다.

---

## 12. 핵심 알고리즘

### 12.1 체결 처리

```text
CanonicalFill 수신
→ idempotency_key 및 broker_execution_id 중복 검사
→ instrument/account/policy 검증
→ 회계 이벤트 INSERT
→ 원가 정책 조회
→ lot 잠금 또는 현재 집계 상태 잠금
→ 매수/매도 분개 생성
→ lot 생성 또는 소진
→ settlement obligation 생성
→ 현금·포지션 파생 상태 갱신
→ 분개 차변/대변 균형 검증
→ Audit 이벤트 기록
→ COMMIT
```

모든 단계는 하나의 DB 트랜잭션에서 처리한다.

### 12.2 매도 lot 소진

```python
from decimal import Decimal


def allocate_sell_fifo(lots: list[dict], sell_quantity: Decimal) -> list[dict]:
    remaining = sell_quantity
    allocations: list[dict] = []

    for lot in sorted(lots, key=lambda row: row["opened_at"]):
        if remaining <= 0:
            break

        available = Decimal(lot["remaining_quantity"])
        used = min(available, remaining)
        allocations.append({
            "lot_id": lot["lot_id"],
            "quantity": used,
            "unit_cost": Decimal(lot["unit_cost"]),
            "released_cost": used * Decimal(lot["unit_cost"]),
        })
        remaining -= used

    if remaining != 0:
        raise InsufficientPosition(
            f"sell quantity exceeds available position: {remaining}"
        )

    return allocations
```

### 12.3 일일 평가

```text
평가 대상 계좌 확정
→ Data Snapshot에서 공식 종가·FX 잠금
→ 미결제 현금·수량 반영
→ 종목별 시장가치 계산
→ 실현·미실현 손익 계산
→ GAV/NAV 계산
→ 외부 현금흐름 분리
→ 일간 수익률 계산
→ 벤치마크 수익률 계산
→ 위험·성과 지표 갱신
→ 내부 원장 및 외부 브로커 대사
→ FINAL 또는 PRELIMINARY 저장
```

### 12.4 NAV 계산

```text
GAV = 현금 + 유가증권 시장가치 + 미수금 + 미수수익
NAV = GAV - 미지급금 - 비용충당 - 세금충당
```

v1에서 공매도와 파생상품은 제외한다. 이후 확장 시 margin, collateral, derivative MTM을 별도 계정으로 추가한다.

---

## 13. 수익률 계산

### 13.1 단순 일간 수익률

외부 현금흐름이 장 마감 후 발생한다고 가정할 때:

```text
R_t = (NAV_t - NAV_{t-1} - Flow_t) / NAV_{t-1}
```

현금흐름의 시점이 장중이면 Modified Dietz 또는 하위 기간 분할을 사용한다.

### 13.2 Time-Weighted Return

외부 입출금 직전·직후로 기간을 분리한다.

```text
TWR = ∏(1 + subperiod_return_i) - 1
```

운용 의사결정의 순수 성과 비교에는 TWR을 기본값으로 사용한다.

### 13.3 Money-Weighted Return

투자자의 실제 자금 경험을 평가할 때 XIRR을 선택적으로 제공한다. 일일 자동 보고서의 주 성과 지표로는 사용하지 않는다.

### 13.4 누적 수익률

```text
cumulative_return_t = ∏(1 + daily_return_i) - 1
```

초기 NAV가 0이거나 데이터가 불완전한 날은 계산하지 않고 상태를 `NOT_AVAILABLE`로 저장한다.

### 13.5 벤치마크

한국 주식 가상 포트폴리오 기본 벤치마크:

1. 1순위: KOSPI Total Return 지수
2. 사용 불가 시: KOSPI 가격지수
3. 거래 가능한 대체 비교: KODEX 200 수정주가

벤치마크 기준은 보고 기간 중 변경하지 않는다. 변경 시 새 성과 시리즈를 생성한다.

```text
excess_return_t = portfolio_return_t - benchmark_return_t
active_wealth_t = ∏(1 + portfolio_return) / ∏(1 + benchmark_return) - 1
```

---

## 14. 성과 지표

v1 필수 지표:

- 일간 수익률
- 누적 수익률
- 벤치마크 누적 수익률
- 누적 초과수익률
- 실현손익
- 미실현손익
- 총 수수료와 세금
- 투자 비중과 현금 비중
- 회전율
- 최대낙폭
- 변동성
- 승률
- 평균 이익·평균 손실
- Profit Factor

충분한 관측치가 있을 때 제공:

```text
annualized_volatility = std(daily_return) × sqrt(252)
sharpe_ratio = mean(excess_daily_return) / std(daily_return) × sqrt(252)
max_drawdown = min(NAV_t / rolling_max_NAV_t - 1)
turnover = min(total_buys, total_sells) / average_NAV
profit_factor = gross_profit / abs(gross_loss)
```

30개 미만 일간 관측치의 Sharpe·변동성은 `INSUFFICIENT_HISTORY`로 표시한다.

---

## 15. 수수료·세금·배당

### 15.1 비용 정책

비용 계산은 Configuration & Policy Engine의 버전 정책을 사용한다.

```python
@dataclass(frozen=True)
class FeeTaxPolicy:
    policy_version: str
    market: str
    asset_class: str
    buy_fee_rate: Decimal
    sell_fee_rate: Decimal
    sell_tax_rate: Decimal
    minimum_fee: Decimal
    rounding_scale: int
    rounding_mode: str
```

실제 LIVE/PAPER 체결은 브로커가 제공한 확정 수수료·세금을 우선한다. 제공되지 않은 경우에만 정책 추정값을 사용하고 `ESTIMATED`를 표시한다.

### 15.2 배당

```text
배당 기준일/권리 확정
→ DIVIDEND_DECLARED
→ 미수배당 인식
→ 지급일 DIVIDEND_RECEIVED
→ 원천세 인식
→ 가용 현금 증가
```

백테스트에서는 수정주가를 사용하는 경우 배당을 별도로 더하지 않도록 데이터 정책으로 중복을 차단한다.

### 15.3 기업행동

v1 필수:

- 주식 분할
- 주식 병합
- 현금 배당

v2 예정:

- 무상증자
- 유상증자 권리
- 합병
- 분할·스핀오프
- 상장폐지 현금청산

---

## 16. 참조 코드

```python
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol


ZERO = Decimal("0")


class DuplicateAccountingEvent(ValueError):
    pass


class InsufficientPosition(ValueError):
    pass


class UnbalancedJournal(ValueError):
    pass


@dataclass(frozen=True)
class JournalLine:
    ledger_account: str
    debit: Decimal
    credit: Decimal
    currency: str
    instrument_id: str | None = None
    quantity: Decimal | None = None


@dataclass(frozen=True)
class PositionState:
    quantity: Decimal
    total_cost: Decimal
    average_cost: Decimal
    realized_pnl: Decimal


class AccountingRepository(Protocol):
    def has_idempotency_key(self, key: str) -> bool: ...
    def load_position_for_update(
        self, account_id: str, portfolio_id: str, instrument_id: str
    ) -> PositionState: ...
    def save_event(self, event: AccountingEvent) -> None: ...
    def save_journal(self, event_id: str, lines: list[JournalLine]) -> None: ...
    def save_position(self, key: tuple[str, str, str], state: PositionState) -> None: ...
    def create_settlement(self, fill: CanonicalFill, net_cash: Decimal) -> None: ...


def money(value: Decimal, scale: int = 0) -> Decimal:
    quantum = Decimal(1).scaleb(-scale)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def assert_balanced(lines: list[JournalLine]) -> None:
    by_currency: dict[str, tuple[Decimal, Decimal]] = {}
    for line in lines:
        debit, credit = by_currency.get(line.currency, (ZERO, ZERO))
        by_currency[line.currency] = (debit + line.debit, credit + line.credit)

    for currency, (debit, credit) in by_currency.items():
        if debit != credit:
            raise UnbalancedJournal(
                f"journal is not balanced for {currency}: {debit} != {credit}"
            )


class PortfolioAccountingService:
    def __init__(self, repository: AccountingRepository):
        self.repository = repository

    def post_fill(self, fill: CanonicalFill, policy_version: str) -> PositionState:
        key = f"fill:{fill.source_mode}:{fill.broker_execution_id}"
        if self.repository.has_idempotency_key(key):
            raise DuplicateAccountingEvent(key)

        current = self.repository.load_position_for_update(
            fill.account_id, fill.portfolio_id, fill.instrument_id
        )

        gross = money(fill.quantity * fill.price)
        total_costs = fill.fee + fill.tax

        if fill.side == "BUY":
            new_quantity = current.quantity + fill.quantity
            new_total_cost = current.total_cost + gross
            new_average = (
                new_total_cost / new_quantity if new_quantity != ZERO else ZERO
            )
            next_state = PositionState(
                quantity=new_quantity,
                total_cost=new_total_cost,
                average_cost=new_average,
                realized_pnl=current.realized_pnl - total_costs,
            )
            journal = build_buy_journal(fill, gross)
            net_cash = gross + total_costs
        else:
            if current.quantity < fill.quantity:
                raise InsufficientPosition(fill.instrument_id)
            released_cost = fill.quantity * current.average_cost
            realized = gross - released_cost - total_costs
            remaining_quantity = current.quantity - fill.quantity
            remaining_cost = current.total_cost - released_cost
            next_state = PositionState(
                quantity=remaining_quantity,
                total_cost=remaining_cost,
                average_cost=(
                    remaining_cost / remaining_quantity
                    if remaining_quantity != ZERO else ZERO
                ),
                realized_pnl=current.realized_pnl + realized,
            )
            journal = build_sell_journal(fill, gross, released_cost)
            net_cash = gross - total_costs

        assert_balanced(journal)
        event = to_accounting_event(fill, key, policy_version)
        self.repository.save_event(event)
        self.repository.save_journal(event.event_id, journal)
        self.repository.save_position(
            (fill.account_id, fill.portfolio_id, fill.instrument_id),
            next_state,
        )
        self.repository.create_settlement(fill, net_cash)
        return next_state
```

실제 구현에서는 `post_fill` 전체를 `BEGIN IMMEDIATE` 또는 PostgreSQL row lock 트랜잭션으로 감싼다.

---

## 17. API / Repository 인터페이스

```python
class PortfolioAccountingRepository(Protocol):
    def post_fill(self, fill: CanonicalFill) -> str: ...
    def post_cashflow(self, cashflow: CashFlowEvent) -> str: ...
    def reverse_event(self, event_id: str, reason: str, requested_by: str) -> str: ...
    def settle_due(self, business_date: date) -> list[str]: ...
    def get_cash_balance(self, account_id: str, currency: str) -> dict: ...
    def get_positions(self, account_id: str, as_of: datetime | None = None) -> list[dict]: ...
    def calculate_valuation(
        self, account_id: str, valuation_date: date, price_snapshot_id: str
    ) -> str: ...
    def finalize_daily_close(self, account_id: str, valuation_date: date) -> str: ...
    def get_performance(
        self, account_id: str, start: date, end: date, frequency: str
    ) -> list[dict]: ...
    def replay_account(self, account_id: str, through: datetime | None = None) -> str: ...
```

권장 애플리케이션 API:

```text
POST /accounting/fills
POST /accounting/cashflows
POST /accounting/events/{id}/reversal
POST /accounting/settlements/run
POST /accounting/valuations
POST /accounting/daily-close
GET  /accounts/{id}/cash
GET  /accounts/{id}/positions
GET  /accounts/{id}/performance
GET  /accounts/{id}/reconciliation
```

---

## 18. 동시성·멱등성·장애 처리

### 18.1 멱등성

```text
fill idempotency key = source_mode + broker_execution_id
cashflow key         = source_system + external_reference + event_type
valuation key        = account + date + price_snapshot + calculation_version
```

중복 입력은 성공으로 간주하되 기존 결과 ID를 반환할 수 있다. payload가 다른 동일 키는 CRITICAL 충돌이다.

### 18.2 동시성

동일 계좌·종목 체결은 순차 처리한다.

- SQLite: `BEGIN IMMEDIATE` + 짧은 트랜잭션
- PostgreSQL: `SELECT ... FOR UPDATE`
- 이벤트 순서: `executed_at`, broker sequence, received sequence

순서가 뒤바뀐 체결은 격리 후 재정렬하거나 계좌를 재생한다.

### 18.3 장애 복구

- 이벤트 저장 전 실패: 재시도 가능
- 이벤트 저장 후 분개 실패: 동일 트랜잭션 롤백
- 분개 후 포지션 갱신 실패: 동일 트랜잭션 롤백
- 평가 중 실패: `PRELIMINARY` 또는 `FAILED`, 이전 FINAL 유지
- 대사 실패: 주문을 자동 수정하지 않고 Compliance 사건 생성

---

## 19. 대사(Reconciliation)

### 19.1 내부 대사

매일 확인:

```text
원장 현금 합계 = cash balance
원장 수량 합계 = position lots 잔여 수량
lot 총원가      = position total cost
차변 합계       = 대변 합계
NAV 구성요소 합 = 저장된 NAV
```

### 19.2 외부 대사

LIVE/PAPER 브로커 제공값과 비교:

- 가용 현금
- 미수·미지급금
- 종목별 보유 수량
- 평균단가
- 당일 체결 건수와 총수량
- 수수료와 세금

허용 오차:

```text
quantity tolerance = 0
KRW cash tolerance = 1 KRW
price tolerance    = policy-defined
fee/tax tolerance  = broker-specific
```

수량 불일치 또는 큰 현금 차이는 `BREAK`이며 LIVE 신규 주문 차단 후보가 된다.

---

## 20. 일일 가상투자 보고 연계

장 마감 후 Scheduler가 다음 파이프라인을 실행한다.

```text
MARKET_CLOSE + 20m
→ 공식 종가 snapshot 잠금
→ 미처리 가상 체결 반영
→ 포지션·현금 평가
→ 일간 수익률 계산
→ KOSPI/KODEX 200 벤치마크 계산
→ 제약 위반 확인
→ Report Engine 입력 생성
```

일일 보고용 출력:

```python
@dataclass(frozen=True)
class DailyPortfolioReportInput:
    valuation_date: date
    account_id: str
    starting_nav: Decimal
    ending_nav: Decimal
    cash: Decimal
    invested_value: Decimal
    daily_return: Decimal
    cumulative_return: Decimal
    benchmark_daily_return: Decimal | None
    benchmark_cumulative_return: Decimal | None
    excess_return: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    taxes: Decimal
    positions: list[dict]
    trades: list[dict]
    accounting_status: str
    reconciliation_status: str
```

신규 매수 후보가 없어 `NO_ACTION`인 날에도 평가와 수익률 계산은 수행한다.

---

## 21. 감사·컴플라이언스 통제

필수 통제:

| ID | 통제 |
|---|---|
| `PA-001` | 중복 fill 회계 반영 차단 |
| `PA-002` | 차변·대변 불균형 분개 차단 |
| `PA-003` | 보유수량 초과 매도 차단 |
| `PA-004` | 음수 가격·수량 입력 차단 |
| `PA-005` | 승인되지 않은 수동 조정 차단 |
| `PA-006` | FINAL 일 마감 직접 수정 차단 |
| `PA-007` | 평가가격 snapshot 미잠금 시 FINAL 차단 |
| `PA-008` | 내부 원장과 브로커 수량 불일치 탐지 |
| `PA-009` | 현금 제약·종목 비중 위반 탐지 |
| `PA-010` | 수정주가와 현금배당 중복 반영 차단 |
| `PA-011` | 정책 버전 없는 계산 차단 |
| `PA-012` | float 기반 금액 계산 사용 금지 |

수동 조정은 요청자와 승인자를 분리하고 사유, 증빙, 만료 여부를 기록한다.

---

## 22. 테스트 계획

### 22.1 단위 테스트

#### 체결·원가

- 최초 매수 후 수량·평균단가
- 여러 가격 매수 후 이동평균
- 전량 매도 후 수량과 원가 0
- 부분 매도 후 잔여 원가
- FIFO 여러 lot 소진
- 수수료·세금 포함 실현손익
- 부분 체결 순차 반영
- 동일 fill 중복 처리
- 보유수량 초과 매도

#### 분개

- 모든 이벤트의 차변·대변 균형
- 통화별 독립 균형
- 매수·매도·배당·입출금 분개
- reversal과 correction 분개
- 0 금액 및 반올림 경계값

#### 수익률

- 외부 현금흐름 없는 일간 수익률
- 입금·출금 포함 수익률
- TWR 하위 기간 연결
- 누적 수익률 기하 연결
- NAV 0 처리
- 최대낙폭
- 벤치마크 초과수익률

### 22.2 DB 테스트

- idempotency unique constraint
- journal event FK
- 트랜잭션 중간 실패 롤백
- 동일 종목 동시 체결 직렬화
- FINAL 평가 유일성
- 이벤트 replay 결과와 저장 포지션 일치
- reversal 참조 무결성

### 22.3 통합 테스트

```text
Decision → Order → Partial Fill × 3
→ Accounting Events × 3
→ Position 1개 집계
→ Settlement T+2
→ Daily Valuation
→ Performance
→ Report
```

검증 항목:

- Execution fill 합계와 회계 수량 일치
- Report 수익률과 Performance Series 일치
- Run State Store artifact hash 연결
- Data Snapshot 가격과 valuation snapshot 연결
- Audit event와 source fill 추적 가능

### 22.4 가상투자 시나리오 테스트

초기자금 10,000,000원:

1. 1일차 1종목 900,000원 매수
2. 2일차 가격 +5%, NO_ACTION
3. 3일차 추가 매수
4. 4일차 절반 매도
5. 5일차 배당 수령
6. 6일차 전량 매도

검증:

- 현금 비중
- 종목당 최대 비중
- 일간·누적 수익률
- 실현·미실현 손익 이동
- 수수료·세금 누계
- 벤치마크 대비 성과

### 22.5 기업행동 테스트

- 2:1 분할 후 수량 2배, 단가 절반, 총원가 유지
- 1:5 병합의 단주 처리
- 배당 기준일 보유 수량 기준 미수배당
- 수정주가 데이터 사용 시 배당 중복 방지

### 22.6 실패 주입 테스트

- 이벤트 INSERT 후 강제 예외
- journal 2번째 line 저장 중 실패
- 평가가격 일부 누락
- FX rate 누락
- 결제일 처리 worker 중단
- 늦은 체결 도착
- 브로커 대사 API 일시 실패
- 원장 해시 불일치

### 22.7 속성 기반 테스트

항상 성립해야 하는 불변식:

```text
모든 journal: debit == credit
short 비허용 계좌: quantity >= 0
전량 매도 후: remaining_cost == 0
분할 전후: total_cost 불변
외부 현금흐름 제외 NAV 변화 = 총손익
replay(position) == stored_position
```

### 22.8 성능 테스트

v1 목표:

- 단일 fill 회계 처리 p95 < 50ms(SQLite local)
- 10만 fill replay < 60초
- 1,000종목 일일 평가 < 10초
- 일간 성과 5년 재계산 < 5초
- 대사 1,000종목 < 5초

성능 최적화 전에 정확성·재현성·감사성을 우선한다.

---

## 23. 운영 지표

- accounting_events_posted_total
- accounting_events_rejected_total
- duplicate_fill_total
- unbalanced_journal_total
- position_replay_mismatch_total
- settlement_pending_total
- settlement_failed_total
- valuation_duration_ms
- valuation_missing_price_total
- reconciliation_break_total
- daily_close_failed_total
- restatement_total
- nav_age_seconds

경보 기준 예:

```text
unbalanced_journal_total > 0         → CRITICAL
position_replay_mismatch_total > 0   → CRITICAL
reconciliation_break_total > 0       → HIGH
valuation_missing_price_total > 0    → HIGH
nav_age_seconds > policy threshold   → WARNING/HIGH
```

---

## 24. 보안과 데이터 보존

- 계좌 인증정보와 API 키는 저장하지 않는다.
- 브로커 계좌번호는 토큰화 또는 마스킹한다.
- 수동 조정 API는 강한 인증과 승인 워크플로를 요구한다.
- 회계 이벤트와 journal은 append-only 권한으로 분리한다.
- 원장 export에는 개인정보와 계좌 식별자를 최소화한다.
- 정책에 따라 원장·감사 기록을 장기 보존한다.
- 백업 복원 후 원장 해시와 replay 결과를 검증한다.

---

## 25. 구현 순서

### Phase 1 — 가상투자·백테스트 최소 기능

- CanonicalFill 입력
- 이동평균 원가
- 현금·포지션 원장
- 실현·미실현 손익
- 일일 NAV
- 일간·누적 수익률
- 가상투자 보고 입력

### Phase 2 — PAPER 안정화

- T+N 결제
- 브로커 수수료·세금
- 외부 대사
- 배당
- 이벤트 replay
- FINAL 일 마감

### Phase 3 — LIVE 준비

- 복식부기 journal 강화
- 승인된 reversal/correction
- 다중 통화
- 기업행동 확장
- 고가용성 DB
- 계좌별 순차 처리
- 강제 대사 차단 정책

### Phase 4 — 고급 성과 분석

- 전략별 성과 귀속
- 요인 및 섹터 기여도
- 거래비용 분석
- 슬리피지 분석
- XIRR
- 세후 수익률

---

## 26. 완료 기준

다음 조건을 모두 충족하면 v1 설계·구현이 완료된 것으로 본다.

- 동일 체결 스트림 재생 시 동일 포지션·현금·손익 생성
- 모든 회계 이벤트가 균형 분개 생성
- 부분 체결과 중복 체결에 안전
- 이동평균 원가와 실현손익 테스트 통과
- 일간 NAV와 누적 TWR 계산 검증
- 벤치마크 대비 성과 계산 가능
- 가상투자 초기자금 1,000만원 상태를 연속 보존
- NO_ACTION 날짜도 성과 시계열 유지
- 내부 원장 대사와 브로커 대사 결과 저장
- FINAL 평가 수정 없이 restatement 가능
- Audit & Compliance에서 원천 Decision·Order·Fill까지 역추적 가능

---

## 27. 다음 설계 대상

다음 엔진은 **Market Regime & Feature Engine v1**로 한다.

이 엔진은 시장 데이터에서 추세, 변동성, 유동성, 거래대금, 시장 폭, 상관관계, 위험선호 상태를 계산하고, `BULL`, `BEAR`, `SIDEWAY`, `HIGH_VOL`, `LIQUIDITY_STRESS`와 같은 시장 국면을 결정한다. Signal·Risk·Decision Engine이 동일한 특징량과 국면 정보를 사용하도록 데이터 누수 방지, feature versioning, 시점 정합성, 학습·실행 일관성을 설계한다.
