# 32. Universe Selection & Eligibility Engine v1

## 1. 목적

Universe Selection & Eligibility Engine은 각 거래일에 ADE가 **평가할 수 있는 종목 집합**을 결정한다.

이 엔진은 종목의 매수·매도 신호를 만들지 않는다. 상장·거래·데이터·유동성·정책 조건을 검증하여 종목을 다음 세 집합으로 분리한다.

- `ELIGIBLE`: Signal Engine에 전달 가능한 종목
- `WATCH_ONLY`: 분석·모니터링은 가능하지만 신규 매수 후보에서는 제외되는 종목
- `EXCLUDED`: 해당 run에서 평가 대상에서 제거되는 종목

Universe가 확정되지 않으면 Signal, Risk, Decision 단계는 실행하지 않는다.

---

## 2. 책임 경계

### 담당

- 시장·상품 유형·통화·거래소 범위 적용
- 상장 상태, 거래정지, 정리매매 등 거래 적격성 검사
- 가격·거래량·시가총액·거래대금 기반 최소 유동성 검사
- OHLCV·기업행동·종목 메타데이터의 완전성 검사
- 신규상장 최소 이력, 가격 상·하한, 정책 제외 목록 적용
- 보유종목과 신규 후보에 서로 다른 적격성 정책 적용
- Universe Snapshot, 제외 사유, 입력 lineage와 hash 저장

### 담당하지 않음

- 수익률·모멘텀·가치·품질 신호 계산
- 종목 순위 결정
- 매수·매도·보유 판단
- 포지션 수량 산정
- 주문 생성·전송
- 거래정지 보유종목의 임의 청산

보유종목이 신규 진입 기준에서 탈락하더라도 자동 매도하지 않는다. 해당 상태는 Portfolio Risk 및 Rebalancing Engine으로 전달한다.

---

## 3. 아키텍처

```text
Instrument Master / Listing Status
Trading Calendar / Session Status
Daily OHLCV / Corporate Actions
Market Cap / Sector / Product Type
Policy Snapshot / Manual Exclusion
Portfolio Snapshot
        ↓
Universe Selection & Eligibility Engine
   ├─ 입력 계약·시점 검증
   ├─ 기본 시장 범위 생성
   ├─ 하드 제외 규칙
   ├─ 데이터 적격성 검사
   ├─ 유동성·가격·이력 검사
   ├─ 보유종목 예외 분리
   ├─ reason code 집계
   └─ deterministic snapshot/hash
        ↓
Eligible Universe → Feature / Signal
Watch-only Universe → Monitoring / Risk
Excluded Universe → Explainability / Audit / Report
```

### 실행 순서

```text
Scheduler
→ Data Snapshot & Lineage
→ Data Quality
→ Universe Selection & Eligibility
→ Market Regime & Feature
→ Signal Generation & Ranking
→ Portfolio Risk
→ Decision
```

---

## 4. 입력 계약

### `UniverseRequest`

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import FrozenSet

@dataclass(frozen=True)
class UniverseRequest:
    run_id: str
    as_of_date: date
    cutoff_at: datetime
    policy_version: str
    policy_hash: str
    instrument_snapshot_id: str
    market_snapshot_id: str
    quality_snapshot_id: str
    portfolio_snapshot_id: str | None
    markets: FrozenSet[str]
    product_types: FrozenSet[str]
```

필수 계약:

- 모든 Snapshot은 동일 `as_of_date`와 허용된 cutoff를 사용한다.
- 정책 hash가 일치하지 않으면 실행을 거부한다.
- 종목 식별자는 내부 `instrument_id`를 기준으로 하며 ticker 재사용에 의존하지 않는다.
- 상장 상태와 가격 데이터의 관측 시점이 미래를 참조해서는 안 된다.

---

## 5. 출력 모델

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Tuple

class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    WATCH_ONLY = "WATCH_ONLY"
    EXCLUDED = "EXCLUDED"

@dataclass(frozen=True)
class EligibilityReason:
    code: str
    severity: str
    observed_value: str | float | int | None
    threshold: str | float | int | None
    evidence_ref: str

@dataclass(frozen=True)
class InstrumentEligibility:
    instrument_id: str
    symbol: str
    market: str
    status: EligibilityStatus
    is_held: bool
    reasons: Tuple[EligibilityReason, ...]
    result_hash: str

@dataclass(frozen=True)
class UniverseSnapshot:
    snapshot_id: str
    run_id: str
    as_of_date: str
    eligible_ids: Tuple[str, ...]
    watch_only_ids: Tuple[str, ...]
    excluded_ids: Tuple[str, ...]
    policy_version: str
    source_hash: str
    result_hash: str
```

---

## 6. 기본 정책 v1

정확한 수치는 Configuration & Policy Engine에서 버전 관리한다. 다음은 PAPER 운용의 초기 기준이다.

| 항목 | 초기 기준 |
|---|---:|
| 시장 | KOSPI, KOSDAQ |
| 상품 유형 | 보통주 우선 |
| 최소 종가 | 1,000원 |
| 최소 상장 이력 | 60 거래일 |
| 20일 중앙 거래대금 | 1,000,000,000원 이상 |
| 최근 가격 이력 | 60 거래일 이상 |
| 최근 20일 유효 OHLCV | 95% 이상 |
| 거래정지 | 신규 후보 제외 |
| 정리매매·상장폐지 진행 | 제외 |
| 관리·투자주의 정책 대상 | 기본 WATCH_ONLY 또는 제외 |
| ETF·ETN·SPAC·우선주 | 별도 Universe 없으면 제외 |
| 수동 금지목록 | 제외 |

이 수치는 전략 성과를 높이기 위한 최적값이 아니라, 데이터와 체결 가능성을 보장하기 위한 초기 운영 통제값이다.

---

## 7. 적격성 규칙

### 7.1 하드 제외

다음 조건은 종합 점수로 상쇄할 수 없다.

```text
UNSUPPORTED_MARKET
UNSUPPORTED_PRODUCT_TYPE
DELISTED
DELISTING_IN_PROGRESS
LIQUIDATION_TRADING
MANUAL_BLOCKLIST
IDENTIFIER_CONFLICT
MISSING_INSTRUMENT_MASTER
FUTURE_DATED_METADATA
```

### 7.2 신규 매수 차단·관찰 유지

```text
TRADING_SUSPENDED
INSUFFICIENT_HISTORY
INSUFFICIENT_LIQUIDITY
PRICE_BELOW_MINIMUM
OHLCV_COMPLETENESS_LOW
CORPORATE_ACTION_UNRESOLVED
QUALITY_STATUS_DEGRADED
SPECIAL_RISK_DESIGNATION
```

보유종목에는 다음 원칙을 적용한다.

- 거래정지 종목은 `WATCH_ONLY`로 유지하고 가격·매도 가능 상태를 Risk에 전달한다.
- 상장폐지 확정 등 하드 제외 상태라도 포트폴리오 원장에서 제거하지 않는다.
- 자동 매도 가능 여부는 Rebalancing과 Order Validation이 결정한다.
- 평가가격이 불확실하면 `VALUATION_UNCERTAIN`을 함께 기록한다.

---

## 8. 결정 알고리즘

```python
def resolve_eligibility(instrument, metrics, policy, is_held):
    reasons = []

    reasons += validate_identity(instrument)
    reasons += validate_market_and_type(instrument, policy)
    reasons += validate_listing_status(instrument)
    reasons += validate_data_quality(metrics, policy)
    reasons += validate_history(metrics, policy)
    reasons += validate_price(metrics, policy)
    reasons += validate_liquidity(metrics, policy)
    reasons += validate_corporate_actions(metrics)
    reasons += validate_policy_lists(instrument, policy)

    if any(r.code in policy.hard_exclusion_codes for r in reasons):
        status = EligibilityStatus.EXCLUDED
    elif reasons:
        status = (
            EligibilityStatus.WATCH_ONLY
            if is_held or policy.keep_degraded_for_monitoring
            else EligibilityStatus.EXCLUDED
        )
    else:
        status = EligibilityStatus.ELIGIBLE

    return build_result(instrument, status, reasons, is_held)
```

### 전체 Universe 생성

```python
def build_universe(request, instruments, metrics_by_id, holdings, policy):
    assert_contract(request, policy)

    results = []
    for instrument in sorted(instruments, key=lambda x: x.instrument_id):
        result = resolve_eligibility(
            instrument=instrument,
            metrics=metrics_by_id.get(instrument.instrument_id),
            policy=policy,
            is_held=instrument.instrument_id in holdings,
        )
        results.append(result)

    snapshot = canonicalize_and_hash(request, results, policy)
    validate_snapshot(snapshot, results)
    return snapshot, tuple(results)
```

---

## 9. 유동성 계산

기본 유동성 지표는 수정주가가 아니라 실제 거래가격과 거래량에서 산출한 거래대금으로 계산한다.

```text
daily_traded_value[t] = close[t] × volume[t]
liquidity_20d = median(daily_traded_value, last 20 valid sessions)
```

중앙값을 사용하는 이유는 단일 급등 거래일이 낮은 평시 유동성을 숨기는 것을 줄이기 위해서다.

추가 확장 지표:

- 20일 평균 거래량
- 20일 거래대금 하위 분위수
- 거래 없는 일수
- 예상 주문금액 / 20일 중앙 거래대금
- 호가 스프레드와 시장충격 추정치

Universe 단계는 최소 유동성만 판정한다. 실제 주문 규모별 시장충격은 Portfolio Risk 및 Order Validation에서 다시 검증한다.

---

## 10. 데이터베이스

### 10.1 `universe_policies`

```sql
CREATE TABLE universe_policies (
    policy_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    market_scope_json TEXT NOT NULL,
    product_scope_json TEXT NOT NULL,
    thresholds_json TEXT NOT NULL,
    hard_exclusion_codes_json TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    policy_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
```

### 10.2 `universe_runs`

```sql
CREATE TABLE universe_runs (
    universe_run_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    as_of_date TEXT NOT NULL,
    cutoff_at TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    instrument_snapshot_id TEXT NOT NULL,
    market_snapshot_id TEXT NOT NULL,
    quality_snapshot_id TEXT NOT NULL,
    portfolio_snapshot_id TEXT,
    status TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    result_hash TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT,
    FOREIGN KEY (policy_id) REFERENCES universe_policies(policy_id)
);
```

### 10.3 `instrument_eligibility_results`

```sql
CREATE TABLE instrument_eligibility_results (
    universe_run_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    eligibility_status TEXT NOT NULL,
    is_held INTEGER NOT NULL,
    reason_count INTEGER NOT NULL,
    result_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (universe_run_id, instrument_id),
    FOREIGN KEY (universe_run_id) REFERENCES universe_runs(universe_run_id)
);
```

### 10.4 `instrument_eligibility_reasons`

```sql
CREATE TABLE instrument_eligibility_reasons (
    universe_run_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    observed_value TEXT,
    threshold_value TEXT,
    evidence_ref TEXT NOT NULL,
    reason_hash TEXT NOT NULL,
    PRIMARY KEY (universe_run_id, instrument_id, sequence_no)
);
```

### 10.5 `universe_snapshots`

```sql
CREATE TABLE universe_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    universe_run_id TEXT NOT NULL UNIQUE,
    eligible_count INTEGER NOT NULL,
    watch_only_count INTEGER NOT NULL,
    excluded_count INTEGER NOT NULL,
    eligible_ids_json TEXT NOT NULL,
    watch_only_ids_json TEXT NOT NULL,
    excluded_ids_json TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
```

### 10.6 `universe_manual_overrides`

```sql
CREATE TABLE universe_manual_overrides (
    override_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    expires_at TEXT,
    approval_ref TEXT NOT NULL,
    override_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
```

수동 override는 하드 안전 규칙을 해제할 수 없다. `FORCE_INCLUDE`는 허용하지 않고, 초기 버전에서는 `EXCLUDE` 또는 `WATCH_ONLY`로의 보수적 변경만 허용한다.

---

## 11. 결정론적 hash

```text
Universe result hash = SHA-256(
    canonical request
  + policy hash
  + sorted instrument master records
  + sorted eligibility metrics
  + sorted reason codes
  + portfolio holding flags
)
```

동일한 입력 Snapshot과 정책은 종목 입력 순서와 관계없이 동일한 결과 hash를 생성해야 한다.

---

## 12. 실패 처리

| 실패 | 처리 |
|---|---|
| 종목 마스터 누락 | 해당 종목 제외, 임계 비율 초과 시 전체 run 실패 |
| 시장 데이터 누락 | 종목 WATCH_ONLY/EXCLUDED, 정책 임계 초과 시 run 실패 |
| 정책 hash 불일치 | 전체 run `REJECTED` |
| 시점 불일치 | 전체 run `REJECTED` |
| 기업행동 미해결 | 신규 진입 차단 |
| 보유종목 데이터 누락 | Risk·Accounting에 `UNKNOWN` 전달, 자동 매도 금지 |
| Universe 0종목 | 성공 가능한 결과이나 Signal 단계는 `NO_CANDIDATE`로 종료 |
| DB 저장 중단 | Snapshot 미발행, 트랜잭션 rollback |

Universe가 비었다는 이유만으로 임의 종목을 추가하지 않는다.

---

## 13. 코드 구조

```text
universe/
├── models.py
├── contracts.py
├── policies.py
├── reason_codes.py
├── identity.py
├── listing.py
├── quality.py
├── liquidity.py
├── history.py
├── corporate_actions.py
├── resolver.py
├── hashing.py
├── repository.py
└── engine.py
```

### Repository 인터페이스

```python
from typing import Protocol

class UniverseRepository(Protocol):
    def reserve_run(self, request: UniverseRequest) -> str: ...
    def save_results(self, universe_run_id: str, results: tuple[InstrumentEligibility, ...]) -> None: ...
    def finalize(self, universe_run_id: str, snapshot: UniverseSnapshot) -> None: ...
    def get_snapshot(self, snapshot_id: str) -> UniverseSnapshot: ...
```

---

## 14. 테스트 계획

### 14.1 단위 테스트

1. 정상 보통주가 `ELIGIBLE`이 되는지 검증
2. 거래정지 신규 종목이 후보에서 제외되는지 검증
3. 거래정지 보유종목이 `WATCH_ONLY`로 유지되는지 검증
4. 정리매매 종목이 하드 제외되는지 검증
5. 60거래일 미만 신규상장이 제외되는지 검증
6. 20일 중앙 거래대금 경계값 검증
7. 가격 1,000원 경계값 검증
8. OHLCV 완전성 95% 경계값 검증
9. ETF·ETN·SPAC·우선주 유형 필터 검증
10. 미해결 기업행동의 신규 진입 차단 검증
11. 수동 제외 override의 유효기간 검증
12. 정책 hash 불일치 거부 검증

### 14.2 속성 테스트

- `ELIGIBLE`, `WATCH_ONLY`, `EXCLUDED`는 상호 배타적이다.
- 모든 입력 종목은 정확히 하나의 상태를 가진다.
- 결과 수 합계는 입력 고유 instrument 수와 같다.
- 하드 제외 reason이 있으면 `ELIGIBLE`이 될 수 없다.
- 입력 순서를 바꿔도 snapshot hash는 같다.
- 정책이나 reason 하나가 달라지면 result hash가 달라진다.
- 미래 시점 메타데이터는 항상 거부된다.
- 보유 여부는 종목을 포트폴리오 원장에서 삭제하지 않는다.

### 14.3 통합 fixture

```text
A. 정상 KOSPI/KOSDAQ 보통주 20개 → 14 ELIGIBLE / 3 WATCH / 3 EXCLUDED
B. 거래정지 보유종목 포함 → 보유 유지, 신규 후보 제외
C. 신규상장 30일 종목 → INSUFFICIENT_HISTORY
D. 거래대금 부족 종목 → INSUFFICIENT_LIQUIDITY
E. OHLCV 결측 급증 → QUALITY_STATUS_DEGRADED
F. 기업행동 미해결 → WATCH_ONLY
G. 전 종목 부적격 → 빈 Universe + Signal NO_CANDIDATE + Decision NO_ACTION
H. 동일 fixture 재실행 → 동일 snapshot hash
```

### 14.4 장애 테스트

- 종목 마스터 중복 identifier
- ticker 변경 및 재사용
- DB finalize 직전 프로세스 중단
- 동일 run 중복 실행
- 가격 snapshot과 상장 상태 날짜 불일치
- 보유종목 메타데이터 완전 누락
- override 만료 직전·직후 경계

---

## 15. 관측성과

주요 metric:

```text
universe.input_count
universe.eligible_count
universe.watch_only_count
universe.excluded_count
universe.exclusion_rate
universe.reason_count{reason_code}
universe.held_watch_only_count
universe.missing_metadata_rate
universe.duration_ms
universe.snapshot_hash_mismatch_count
```

전일 대비 eligible 종목 수가 정책 임계 이상 급변하면 Data Quality 또는 종목 마스터 장애 가능성을 경고한다. 다만 이 엔진이 임의로 전일 Universe를 재사용하지는 않는다.

---

## 16. 핵심 안전 불변식

```text
Universe 미확정 상태에서 Signal 실행 금지
하드 제외 종목의 신규 BUY 생성 금지
거래정지 종목의 가상·실제 매수 금지
빈 Universe에 임의 후보 추가 금지
보유종목 적격성 저하를 포지션 삭제로 처리 금지
미래 시점의 상장·가격·기업행동 정보 사용 금지
수동 override로 하드 안전 규칙 해제 금지
동일 입력·정책은 동일 snapshot hash 생성
```

---

## 17. 구현 우선순위

```text
Eligibility 모델·reason registry
→ 기본 정책 Snapshot
→ listing/product/identity hard filter
→ history/price/liquidity 순수 함수
→ 보유종목 WATCH_ONLY 처리
→ canonical hash
→ SQLite Repository
→ 빈 Universe → NO_CANDIDATE → NO_ACTION 통합 테스트
```

## 18. 완료 기준

- KOSPI/KOSDAQ 고정 fixture에서 적격·관찰·제외 분류가 결정론적으로 재현된다.
- 종목별 모든 제외 사유가 구조화 reason code와 evidence로 저장된다.
- Signal Engine은 오직 final `eligible_ids`만 입력받는다.
- 보유종목의 거래정지·데이터 불확실 상태가 Risk와 Report에 전달된다.
- 빈 Universe가 정상적으로 `NO_CANDIDATE`와 `NO_ACTION`으로 연결된다.
- 동일 입력과 정책에서 snapshot hash가 재실행 간 일치한다.
