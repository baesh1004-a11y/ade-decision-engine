# 33. Corporate Actions & Adjusted Pricing Engine v1

## 1. 목적

Corporate Actions & Adjusted Pricing Engine은 배당, 액면분할, 주식병합, 무상증자, 유상증자, 권리락, 합병, 분할, 종목코드 변경, 상장폐지와 같은 기업행동을 시점 정합성이 있는 불변 이벤트로 관리하고, 가격계열·포지션·현금·성과·신호에 필요한 조정 결과를 결정론적으로 제공한다.

이 엔진의 핵심 목적은 다음 오류를 방지하는 것이다.

- 액면분할 이후 수익률이 급락한 것으로 잘못 계산되는 오류
- 배당을 누락해 총수익률과 벤치마크 대비 성과가 왜곡되는 오류
- 권리락·무상증자·합병을 일반 가격변동으로 오인해 Signal이 생성되는 오류
- 보유수량과 평균단가가 기업행동 전후로 불일치하는 오류
- 발표일 이후 정보를 기준일 이전 백테스트에 사용하는 미래정보 누수
- 공급업체별 조정주가를 혼합해 Feature·Risk·Accounting 결과가 달라지는 오류

본 엔진은 투자 판단을 생성하지 않는다. 기업행동 사실과 조정계수, 적용 가능한 가격·수량·현금 이벤트를 생성하여 DataHub, Feature, Signal, Portfolio Accounting, Paper Trading, Backtest, Risk, Explainability에 전달한다.

---

## 2. 책임 경계

### 2.1 수행 책임

1. 공급업체 원천 기업행동 수집 및 정규화
2. 동일 이벤트 중복 제거와 충돌 탐지
3. 발표일, 기준일, 권리락일, 지급일, 효력일 분리 관리
4. 가격조정계수와 수량조정계수 계산
5. 가격수익률용 `PRICE_RETURN` 계열과 총수익률용 `TOTAL_RETURN` 계열 분리
6. 보유 포지션의 수량·원가·현금배당 조정 이벤트 생성
7. 정정·취소 기업행동의 append-only revision 관리
8. 이벤트별 lineage, source hash, canonical result hash 생성
9. 불확실 이벤트의 격리와 downstream block/watch 상태 발행

### 2.2 수행하지 않는 책임

- BUY/SELL/HOLD/NO_ACTION 판단 생성
- 기업행동을 이유로 자동 매도
- 세법상 개인별 실제 원천징수 세액 확정
- 브로커 주문 제출
- 공급업체 원본 데이터 삭제 또는 과거 확정 이벤트 덮어쓰기
- 근거 없는 조정계수 추정

---

## 3. 상위 아키텍처

```text
Exchange / DART / KRX / Vendor Feeds
                ↓
Corporate Action Ingestion
   ├─ Source Adapter
   ├─ Raw Event Store
   ├─ Schema Normalizer
   └─ Identity Resolver
                ↓
Event Reconciliation
   ├─ Duplicate Resolver
   ├─ Conflict Detector
   ├─ Revision Chain
   └─ Confidence Resolver
                ↓
Adjustment Calculator
   ├─ Price Factor
   ├─ Quantity Factor
   ├─ Cash Entitlement
   ├─ Cost-basis Allocation
   └─ Fractional-share Handling
                ↓
Immutable Corporate Action Snapshot
   ├─ PRICE_RETURN series contract
   ├─ TOTAL_RETURN series contract
   ├─ Position Adjustment Events
   ├─ Cash Ledger Events
   └─ Evidence / Hash
                ↓
DataHub / Feature / Signal / Risk
Backtest / Paper Trading / Accounting
Explainability / Report / Audit
```

### 3.1 처리 단계

```text
INGESTED
→ NORMALIZED
→ RECONCILING
→ CONFIRMED | CONFLICTED | INCOMPLETE
→ FACTOR_CALCULATED
→ READY
→ APPLIED
→ REVISED | CANCELLED
```

`CONFLICTED`, `INCOMPLETE`, `CANCELLED` 상태는 자동 적용하지 않는다.

---

## 4. 핵심 도메인 모델

### 4.1 CorporateActionType

```python
from enum import StrEnum

class CorporateActionType(StrEnum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    STOCK_SPLIT = "STOCK_SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    BONUS_ISSUE = "BONUS_ISSUE"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    SPIN_OFF = "SPIN_OFF"
    MERGER = "MERGER"
    DEMERGER = "DEMERGER"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    DELISTING = "DELISTING"
    CAPITAL_REDUCTION = "CAPITAL_REDUCTION"
```

### 4.2 EventStatus

```python
class EventStatus(StrEnum):
    INGESTED = "INGESTED"
    NORMALIZED = "NORMALIZED"
    CONFIRMED = "CONFIRMED"
    CONFLICTED = "CONFLICTED"
    INCOMPLETE = "INCOMPLETE"
    READY = "READY"
    APPLIED = "APPLIED"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"
```

### 4.3 날짜 의미

| 필드 | 의미 |
|---|---|
| `announced_at` | 시장에 최초 공개된 시각 |
| `record_date` | 권리 보유 기준일 |
| `ex_date` | 권리가 가격에서 분리되는 거래일 |
| `effective_date` | 수량·종목 변환 효력일 |
| `payment_date` | 현금 또는 주식 지급일 |
| `known_at` | ADE가 해당 사실을 알 수 있었던 시각 |

백테스트와 재현 실행에서는 반드시 `known_at <= evaluation_time`인 이벤트만 사용할 수 있다.

### 4.4 CorporateActionEvent

```python
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

@dataclass(frozen=True)
class CorporateActionEvent:
    event_id: str
    instrument_id: str
    action_type: CorporateActionType
    status: EventStatus
    announced_at: datetime | None
    known_at: datetime
    record_date: date | None
    ex_date: date | None
    effective_date: date | None
    payment_date: date | None
    cash_per_share: Decimal | None
    old_shares: Decimal | None
    new_shares: Decimal | None
    subscription_price: Decimal | None
    source_id: str
    source_event_key: str
    source_hash: str
    revision_no: int
```

### 4.5 AdjustmentFactor

```python
@dataclass(frozen=True)
class AdjustmentFactor:
    instrument_id: str
    effective_date: date
    price_factor: Decimal
    quantity_factor: Decimal
    cash_component_per_old_share: Decimal
    factor_method: str
    event_ids: tuple[str, ...]
    status: str
    result_hash: str
```

원칙:

```text
adjusted_historical_price = raw_historical_price × cumulative_price_factor
adjusted_quantity         = raw_quantity × cumulative_quantity_factor
```

조정 방향은 저장소 전체에서 하나의 convention으로 고정한다.

---

## 5. 데이터베이스 설계

SQLite 기준 최소 스키마이며 운영 DB에서도 동일한 논리 모델을 유지한다.

### 5.1 `corporate_action_sources`

```sql
CREATE TABLE corporate_action_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_priority INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
```

### 5.2 `corporate_action_raw_events`

```sql
CREATE TABLE corporate_action_raw_events (
    raw_event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_event_key TEXT NOT NULL,
    instrument_raw_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(source_id, source_event_key, payload_hash)
);
```

### 5.3 `corporate_actions`

```sql
CREATE TABLE corporate_actions (
    event_id TEXT PRIMARY KEY,
    canonical_event_key TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    announced_at TEXT,
    known_at TEXT NOT NULL,
    record_date TEXT,
    ex_date TEXT,
    effective_date TEXT,
    payment_date TEXT,
    cash_per_share TEXT,
    old_shares TEXT,
    new_shares TEXT,
    subscription_price TEXT,
    revision_no INTEGER NOT NULL,
    supersedes_event_id TEXT,
    source_confidence TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(canonical_event_key, revision_no)
);
```

### 5.4 `corporate_action_source_links`

```sql
CREATE TABLE corporate_action_source_links (
    event_id TEXT NOT NULL,
    raw_event_id TEXT NOT NULL,
    source_role TEXT NOT NULL,
    PRIMARY KEY(event_id, raw_event_id)
);
```

### 5.5 `adjustment_factors`

```sql
CREATE TABLE adjustment_factors (
    factor_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    price_factor TEXT NOT NULL,
    quantity_factor TEXT NOT NULL,
    cash_component_per_old_share TEXT NOT NULL,
    factor_method TEXT NOT NULL,
    status TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(instrument_id, effective_date, result_hash)
);
```

### 5.6 `adjustment_factor_events`

```sql
CREATE TABLE adjustment_factor_events (
    factor_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    PRIMARY KEY(factor_id, event_id)
);
```

### 5.7 `position_adjustment_events`

```sql
CREATE TABLE position_adjustment_events (
    adjustment_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    old_quantity TEXT NOT NULL,
    new_quantity TEXT NOT NULL,
    old_cost_basis TEXT NOT NULL,
    new_cost_basis TEXT NOT NULL,
    fractional_quantity TEXT NOT NULL,
    cash_in_lieu TEXT NOT NULL,
    status TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    UNIQUE(portfolio_id, event_id)
);
```

### 5.8 `cash_entitlement_events`

```sql
CREATE TABLE cash_entitlement_events (
    entitlement_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    record_date TEXT,
    payment_date TEXT NOT NULL,
    eligible_quantity TEXT NOT NULL,
    gross_cash TEXT NOT NULL,
    withholding_tax TEXT NOT NULL,
    net_cash TEXT NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    UNIQUE(portfolio_id, event_id)
);
```

### 5.9 `corporate_action_runs`

```sql
CREATE TABLE corporate_action_runs (
    run_id TEXT PRIMARY KEY,
    as_of_time TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    conflict_count INTEGER NOT NULL,
    output_snapshot_hash TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
```

모든 금액·비율은 binary float가 아니라 decimal 문자열 또는 고정소수점 숫자로 저장한다.

---

## 6. 기업행동별 계산 알고리즘

### 6.1 액면분할

기존 1주가 신규 `r`주로 변환되는 경우:

```text
quantity_factor = r
price_factor    = 1 / r
new_quantity    = old_quantity × r
new_unit_cost   = old_unit_cost / r
position_cost_basis total은 불변
```

예: 1주 → 5주 분할

```text
100주 × 50,000원
→ 500주 × 10,000원
총 원가 5,000,000원 유지
```

### 6.2 주식병합

기존 `r`주가 신규 1주로 변환되는 경우:

```text
quantity_factor = 1 / r
price_factor    = r
```

정수주 미만 잔여분은 임의 반올림하지 않고 `fractional_quantity`로 격리한다. 정책에 따라 현금대체금이 확정될 때 별도 cash-in-lieu 이벤트를 기록한다.

### 6.3 현금배당

가격수익률 계열은 배당을 현금으로 보지 않으며 총수익률 계열은 지급 또는 재투자 가정에 따라 반영한다.

```text
gross_cash = eligible_quantity × cash_per_share
net_cash   = gross_cash - withholding_tax
```

PAPER 기본 정책:

- 권리수량은 record-date entitlement snapshot으로 고정
- 지급일에 현금원장 반영
- 세율이 확정되지 않으면 gross와 `TAX_PENDING`을 분리
- 배당을 매수 Signal로 변환하지 않음

### 6.4 주식배당·무상증자

```text
quantity_factor = 1 + new_shares_per_old_share
price_factor    = 1 / quantity_factor
```

총 원가는 유지하고 단위 원가는 희석한다.

### 6.5 유상증자·권리락

권리 가치와 청약 여부가 필요하므로 자동 단일계수 적용을 제한한다.

```text
THEORETICAL_EX_RIGHTS_PRICE =
    (old_shares × cum_rights_price + new_shares × subscription_price)
    / (old_shares + new_shares)
```

다음 중 하나라도 없으면 `INCOMPLETE` 처리한다.

- 구주 대비 신주 비율
- 발행가
- 권리락일
- 권리 행사 정책

PAPER v1 기본은 권리 자체를 자동 행사하지 않는다. 향후 Rights Exercise Policy가 승인된 경우에만 별도 Decision이 아닌 corporate-action entitlement 처리로 반영한다.

### 6.6 합병·분할

합병·인적분할은 단일 가격계수로 환원하지 않고 자산배분 이벤트로 처리한다.

```text
old instrument
→ successor instrument(s)
→ exchange ratio
→ allocated cost basis
→ residual cash
```

원가배분 근거가 없으면 `MANUAL_REVIEW_REQUIRED`로 격리한다.

### 6.7 종목코드 변경

경제적 자산이 동일하고 식별자만 변경된 경우:

- position_id와 economic lineage 유지
- instrument_id mapping event 생성
- 과거 데이터를 새 코드로 덮어쓰지 않음
- symbol alias 기간을 명시

### 6.8 상장폐지

상장폐지는 Universe에서 신규진입을 차단하지만 보유 포지션을 자동 삭제하지 않는다.

```text
DELISTING_NOTICE
→ Universe EXCLUDED
→ Position remains
→ Risk / Rebalancing / Report escalation
→ final settlement evidence가 있을 때만 원장 조정
```

---

## 7. 조정주가 계열 계약

엔진은 목적별 계열을 명시적으로 구분한다.

| 계열 | 사용 목적 | 배당 반영 | 분할 반영 |
|---|---|---:|---:|
| `RAW` | 체결·공식 종가·감사 | 아니오 | 아니오 |
| `SPLIT_ADJUSTED` | 기술적 Feature | 아니오 | 예 |
| `PRICE_RETURN` | 순수 가격수익률 | 아니오 | 예 |
| `TOTAL_RETURN_GROSS` | 세전 총수익률 | 예 | 예 |
| `TOTAL_RETURN_NET` | 정책 세율 반영 총수익률 | 예 | 예 |

안전 규칙:

```text
Order/Paper Fill price는 RAW 공식 가격만 사용
Feature는 policy가 지정한 adjusted series만 사용
Accounting은 RAW 가격 + 별도 cash/quantity ledger 사용
Backtest 결과에는 사용한 series_type과 factor_snapshot_hash 기록
서로 다른 series_type을 한 수익률 구간에서 혼합 금지
```

---

## 8. 이벤트 대사 및 충돌 해결

### 8.1 canonical key

```text
instrument_id
+ action_type
+ effective/ex date
+ 핵심 비율 또는 금액
```

### 8.2 source priority

초기 정책 예:

```text
KRX confirmed filing
> DART official disclosure
> broker corporate-action notice
> licensed vendor
> public market-data feed
```

우선순위만으로 자동 확정하지 않고 핵심 필드 일치 여부를 함께 본다.

### 8.3 conflict algorithm

```python
def reconcile(events, policy):
    grouped = group_by_canonical_candidate(events)
    results = []

    for group in grouped:
        if exact_core_fields_match(group):
            results.append(confirm(merge_evidence(group)))
            continue

        authoritative = highest_priority_confirmed(group, policy)
        if authoritative and no_material_conflict(authoritative, group):
            results.append(confirm_with_warnings(authoritative, group))
        else:
            results.append(mark_conflicted(group))

    return results
```

핵심 필드 충돌 예:

- 분할 비율 상이
- 배당금 상이
- 권리락일 상이
- 효력일 상이
- successor instrument 상이

이 경우 downstream 자동 적용은 0건이어야 한다.

---

## 9. 일일 실행 알고리즘

```text
1. as_of_time과 거래일 세션 확정
2. as_of_time 이전에 known 상태인 raw event만 로딩
3. instrument identity 해석
4. schema 정규화
5. canonical 후보 그룹 생성
6. 중복 제거·source evidence 결합
7. 핵심 필드 충돌 검사
8. CONFIRMED 이벤트만 factor 계산
9. factor chain의 연속성·양수성 검사
10. 가격계열별 adjustment snapshot 생성
11. 보유 포트폴리오의 entitlement snapshot 생성
12. effective/payment date 도달 이벤트 적용 제안 생성
13. Accounting/Paper Trading에 append-only ledger event 전달
14. DataHub/Feature에 series contract와 factor hash 전달
15. Explainability/Audit에 evidence bundle 전달
16. output snapshot hash 저장
```

### 9.1 결정론적 factor chain

```python
from decimal import Decimal

ONE = Decimal("1")

def cumulative_factor(factors):
    price = ONE
    qty = ONE
    for factor in sorted(factors, key=lambda x: (x.effective_date, x.factor_id)):
        if factor.status != "READY":
            continue
        price *= factor.price_factor
        qty *= factor.quantity_factor
    return price, qty
```

정렬 기준과 Decimal precision은 policy version에 고정한다.

---

## 10. 코드 구조

```text
corporate_actions/
├── models.py
├── enums.py
├── contracts.py
├── adapters/
│   ├── krx.py
│   ├── dart.py
│   ├── broker.py
│   └── vendor.py
├── normalization.py
├── identity.py
├── deduplication.py
├── reconciliation.py
├── calculators/
│   ├── split.py
│   ├── dividend.py
│   ├── rights.py
│   ├── merger.py
│   └── spin_off.py
├── factors.py
├── entitlements.py
├── position_adjustments.py
├── series.py
├── hashing.py
├── repository.py
└── engine.py
```

### 10.1 서비스 인터페이스

```python
from typing import Protocol

class CorporateActionRepository(Protocol):
    def load_raw_events(self, as_of_time): ...
    def save_normalized_events(self, events): ...
    def save_factors(self, factors): ...
    def save_snapshot(self, snapshot): ...

class CorporateActionsEngine:
    def run(self, request: "CorporateActionRunRequest") -> "CorporateActionRunResult":
        ...
```

### 10.2 입력 계약

```python
@dataclass(frozen=True)
class CorporateActionRunRequest:
    run_id: str
    as_of_time: datetime
    policy_version: str
    instrument_master_snapshot_hash: str
    market_data_snapshot_hash: str
    portfolio_snapshot_hash: str | None
```

### 10.3 출력 계약

```python
@dataclass(frozen=True)
class CorporateActionRunResult:
    status: str
    confirmed_events: tuple[CorporateActionEvent, ...]
    conflicted_event_ids: tuple[str, ...]
    factors: tuple[AdjustmentFactor, ...]
    position_adjustments: tuple[str, ...]
    cash_entitlements: tuple[str, ...]
    output_snapshot_hash: str
```

---

## 11. 오류 처리

| 오류 | 처리 |
|---|---|
| 종목 식별 실패 | `UNRESOLVED_IDENTITY`, 자동 적용 차단 |
| source 핵심필드 충돌 | `CONFLICTED`, 수동 검토 |
| 음수·0 조정계수 | `INVALID_FACTOR`, 전체 chain 차단 |
| ex-date 누락 | 적용 불가, `INCOMPLETE` |
| 미래 known_at 이벤트 | 입력에서 제외 |
| 과거 확정 이벤트 정정 | 기존 row 수정 금지, 새 revision 추가 |
| 동일 event 중복 적용 | `(portfolio_id,event_id)` unique로 차단 |
| 현금 지급액 불명 | entitlement 생성 가능, cash posting 대기 |
| 합병 원가배분 불명 | `MANUAL_REVIEW_REQUIRED` |

Fail-safe 원칙:

```text
기업행동 데이터가 불확실하면
가격·수량·현금을 추정해 적용하지 않는다.

Feature는 해당 종목을 WATCH_ONLY 또는 제외할 수 있고,
보유 포지션은 원장에서 유지한 채 Risk와 Report로 전달한다.
```

---

## 12. 테스트 계획

### 12.1 단위 테스트

1. 1:5 액면분할의 가격·수량·원가 불변성
2. 5:1 병합과 fractional share 격리
3. 현금배당 gross/net cash 계산
4. 무상증자 quantity factor 계산
5. 권리락 이론가격 계산
6. cumulative factor 정렬 독립성
7. canonical hash의 입력 순서 독립성
8. known_at 미래정보 차단
9. conflict 상태에서 factor 0건
10. revision chain 불변성

### 12.2 고정 통합 시나리오

```text
A. 삼성형 50:1 액면분할 fixture
   → 과거 가격 조정
   → 현재 RAW 가격 불변
   → 보유수량 50배
   → 총 원가 불변

B. 현금배당 fixture
   → record-date entitlement 고정
   → payment-date cash ledger 반영
   → PRICE_RETURN과 TOTAL_RETURN 차이 확인

C. 공급업체 2곳의 동일 분할 이벤트
   → 단일 canonical event
   → evidence 2개
   → 중복 적용 0건

D. 분할비율 충돌
   → CONFLICTED
   → factor/position adjustment 0건

E. 발표 정정
   → revision_no 증가
   → 과거 이벤트 보존
   → 새 snapshot hash

F. 종목코드 변경
   → economic lineage 유지
   → position 삭제 없음

G. 합병 원가배분 근거 누락
   → MANUAL_REVIEW_REQUIRED
   → 자동 원장 조정 0건

H. 전체 corporate-action 없음
   → empty confirmed set
   → 정상 final snapshot 생성
```

### 12.3 속성 기반 테스트

```text
split 후 total cost basis == split 전 total cost basis

price_factor > 0
quantity_factor > 0

동일 portfolio/event의 적용 횟수 <= 1

CONFLICTED event의 ledger event 수 == 0

known_at > as_of_time인 event의 사용 횟수 == 0

입력 순서 변경 후 output hash 동일

RAW order price는 adjusted factor의 영향을 받지 않음

PRICE_RETURN과 TOTAL_RETURN은 배당 없는 구간에서 동일
```

### 12.4 회귀 테스트

- 액면분할일에 -80% 손실 Signal이 생성되지 않음
- 배당락을 비정상 급락으로 오인하지 않음
- 조정주가로 가상체결하지 않음
- 배당이 두 번 현금원장에 반영되지 않음
- 기업행동 정정이 과거 final ledger를 덮어쓰지 않음

### 12.5 장애·복구 테스트

- factor 저장 직후 DB 중단
- event 저장과 ledger 적용 사이 중단
- 중복 run 재시도
- source feed 지연 도착
- 지급일 정정
- instrument mapping 변경

재실행은 idempotency key와 unique constraint로 동일 결과를 한 번만 반영해야 한다.

---

## 13. 감사·설명 요구사항

모든 적용 결과는 다음을 설명할 수 있어야 한다.

```text
어떤 기업행동이 있었는가?
어느 시점에 ADE가 알 수 있었는가?
어떤 원천이 이를 뒷받침하는가?
가격·수량·현금이 어떻게 변했는가?
어떤 정책과 계산식을 사용했는가?
왜 자동 적용 또는 차단되었는가?
```

Evidence Bundle 최소 항목:

- 원천 payload hash
- canonical event hash
- instrument master snapshot hash
- policy version/hash
- factor method/version
- Decimal precision/rounding rule
- portfolio entitlement snapshot hash
- output result hash

---

## 14. 핵심 안전 불변식

```text
기업행동 엔진은 투자 판단이나 주문을 생성하지 않는다.

RAW 공식 가격과 adjusted 가격을 혼합하지 않는다.

Order와 PAPER Fill은 adjusted 가격을 사용하지 않는다.

미래 known_at 정보는 과거 평가에 사용할 수 없다.

CONFLICTED/INCOMPLETE 이벤트는 자동 적용하지 않는다.

조정계수는 항상 양수여야 한다.

분할·병합 후 총 원가는 정책상 동일해야 한다.

동일 portfolio/event는 최대 한 번만 적용한다.

정정은 append-only revision으로 기록한다.

보유종목의 기업행동 불확실성을 포지션 삭제로 처리하지 않는다.

배당 현금은 entitlement와 payment를 분리해 기록한다.

동일 입력·정책은 동일한 canonical snapshot hash를 생성한다.
```

---

## 15. 구현 우선순위

```text
1. 불변 Event/Factor/Entitlement 모델
2. SQLite migration
3. Decimal 기반 split/dividend 순수 계산기
4. source event canonicalization과 중복 제거
5. conflict resolver
6. factor chain과 adjusted-series contract
7. position/cash append-only adjustment adapter
8. known_at temporal guard
9. canonical hashing
10. 분할·배당·충돌·정정 고정 fixture
11. DataHub/Feature/Paper Trading/Accounting adapter
12. 20거래일 연속 기업행동 포함 통합 테스트
```

## 16. 완료 기준

다음 조건을 모두 만족하면 v1 최소 구현 완료로 간주한다.

- 분할과 현금배당 fixture가 결정론적으로 통과
- 미래정보 누수 테스트 통과
- conflict 이벤트 자동 적용 0건
- 동일 이벤트 중복 원장 반영 0건
- RAW/PRICE_RETURN/TOTAL_RETURN 계열 분리 검증
- Paper Trading·Accounting 포트폴리오 연속성 유지
- 동일 입력 재실행 시 동일 output hash
- 실브로커 주문 호출 0건
