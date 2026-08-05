# 37. Benchmark & Index Constituents Engine v1

## 1. 목적

Benchmark & Index Constituents Engine은 ADE가 사용하는 벤치마크 지수와 지수 구성종목 정보를 **시점 정합성(point-in-time)** 있게 관리하고, 포트폴리오 성과·상대강도·시장국면·Universe 평가에 동일한 기준 Snapshot을 제공한다.

이 엔진의 핵심 목적은 다음 오류를 차단하는 것이다.

- 현재의 KOSPI 200 구성종목을 과거 백테스트에 사용해 발생하는 생존편향
- 리밸런싱 발표일과 실제 편입 효력일을 혼동하는 오류
- 가격지수와 총수익지수를 혼합하는 오류
- KOSPI, KOSPI 200, KODEX 200을 동일한 벤치마크로 취급하는 오류
- 지수 종가가 누락된 날 전일 종가를 자동 대입하는 오류
- 구성종목 변경 정정을 과거 Snapshot에 덮어쓰는 오류
- ETF 추적오차를 지수 자체의 성과로 오인하는 오류

본 엔진은 투자 Signal이나 주문을 생성하지 않는다. 지수 정의, 구성종목, 가중치, 가격계열, 벤치마크 수익률 및 관련 증거를 표준화해 후속 엔진에 전달한다.

---

## 2. 책임 범위

### 2.1 수행 책임

1. 벤치마크 정의 및 식별
2. 지수 가격·총수익 계열 수집과 정규화
3. 지수 구성종목과 가중치의 유효기간 관리
4. 정기·수시 변경 이벤트 관리
5. 발표시각·효력일·ADE 인지시각 분리
6. 구성종목 Snapshot 생성
7. 벤치마크 수익률 계산
8. 포트폴리오 상대성과 계산에 필요한 기준 데이터 제공
9. 공급원 간 지수 값·구성종목 대사
10. 생존편향·미래정보 누수 차단
11. 모든 결과의 Manifest 및 canonical hash 생성

### 2.2 수행하지 않는 책임

- 종목 BUY·SELL 판단
- 포트폴리오 목표 비중 산출
- 주문 또는 체결 생성
- 지수 추종전략 리밸런싱 주문 생성
- ETF의 실제 NAV 또는 괴리율 산출 책임
- 개별 종목 가격 조정
- 기업행동 원장 반영

---

## 3. 벤치마크 유형

ADE는 다음 유형을 명시적으로 구분한다.

| 유형 | 예시 | 용도 |
|---|---|---|
| Broad Market Index | KOSPI, KOSDAQ | 시장 전체 방향·시장국면 |
| Tradable Large-cap Index | KOSPI 200 | 대형주 전략 상대성과 |
| Sector Index | 반도체, 자동차 등 | 섹터 상대강도·노출 분석 |
| Total Return Index | KOSPI 200 TR | 배당 포함 장기 성과 비교 |
| ETF Proxy | KODEX 200 | 실제 거래 가능한 대체 벤치마크 |
| Cash Benchmark | 0% 또는 정책금리 기반 | 현금성 전략 비교 |

`KOSPI 200`과 `KODEX 200`은 동일하지 않다.

```text
KOSPI 200
→ 지수 자체

KODEX 200
→ 거래 가능한 ETF
→ 운용보수, 추적오차, 괴리율, 배당 처리의 영향 존재
```

따라서 각 벤치마크는 `benchmark_type`과 `series_type`을 함께 기록한다.

---

## 4. 가격계열 계약

| series_type | 의미 | 배당 반영 | 주요 사용처 |
|---|---|---:|---|
| PRICE_INDEX | 가격지수 | 아니오 | 시장국면, 단기 상대성과 |
| GROSS_TOTAL_RETURN | 세전 총수익지수 | 예 | 장기 전략 성과 |
| NET_TOTAL_RETURN | 정책 세율 반영 총수익 | 예 | 세후 비교 |
| ETF_CLOSE | ETF 공식 종가 | ETF 정책에 따름 | 거래가능 프록시 |
| ETF_NAV | ETF 순자산가치 | ETF 정책에 따름 | 추적오차 분석 |

포트폴리오 성과 보고서에는 어떤 계열을 사용했는지 반드시 명시한다.

```text
benchmark_id
benchmark_version
series_type
market_date
observation_id
snapshot_hash
```

가격지수와 총수익지수의 수익률을 한 누적성과 곡선에서 혼합하지 않는다.

---

## 5. 상태 모델

### 5.1 벤치마크 관측 상태

| 상태 | 의미 |
|---|---|
| PENDING | 데이터 수신 대기 |
| RECEIVED | 원천 데이터 수신 |
| VALIDATED | 형식·날짜·값 검증 완료 |
| RECONCILED | 공급원 간 대사 완료 |
| FINALIZED | 후속 엔진 사용 가능 |
| DEGRADED | 보조정보 일부 부족 |
| CONFLICTED | 핵심 값 충돌 |
| MISSING | 필수 관측치 없음 |
| RETIRED | 더 이상 사용하지 않는 벤치마크 |

### 5.2 구성종목 Snapshot 상태

| 상태 | 의미 |
|---|---|
| DRAFT | 변경안 수신, 아직 효력 없음 |
| ANNOUNCED | 공식 발표됨 |
| EFFECTIVE | 해당 거래일에 적용 |
| SUPERSEDED | 후속 revision으로 대체 |
| CONFLICTED | 구성·가중치 충돌 |
| INCOMPLETE | 필수 종목 또는 가중치 누락 |

---

## 6. 시간 정합성

다음 시각을 분리한다.

| 필드 | 의미 |
|---|---|
| announced_at | 지수 변경이 공식 발표된 시각 |
| known_at | ADE가 해당 정보를 이용 가능해진 시각 |
| effective_from | 변경이 실제 지수에 반영되는 시점 |
| effective_to | 해당 구성의 종료 시점 |
| recorded_at | ADE 저장소 기록 시각 |
| revised_at | 정정 공시 또는 수정 시각 |

과거 평가시점 `T`에는 다음 조건을 만족하는 데이터만 사용한다.

```text
known_at <= T
and effective_from <= T < effective_to
and revision is the latest revision known at T
```

발표는 되었지만 아직 효력이 발생하지 않은 편입종목은 해당 거래일 구성종목으로 사용하지 않는다.

---

## 7. 아키텍처

```text
KRX / Index Provider / ETF Provider / Market Data Vendor
                        ↓
Benchmark Definition Ingestion
   ├─ 지수 식별자
   ├─ 산출 방식
   ├─ 통화
   ├─ 기준시점
   └─ 가격·총수익 계열 구분
                        ↓
Constituent Event Ingestion
   ├─ 정기변경
   ├─ 수시편입·편출
   ├─ 가중치 변경
   └─ 정정·취소
                        ↓
Identity Resolution
   ├─ security_id
   ├─ listing_id
   └─ 유효 종목코드 매핑
                        ↓
Reconciliation & Validation
   ├─ 공급원 간 지수값 비교
   ├─ 구성종목 집합 비교
   ├─ 가중치 합계 검사
   ├─ 유효기간 중복 검사
   └─ 미래정보 검사
                        ↓
Point-in-Time Snapshot Builder
   ├─ Benchmark Observation Snapshot
   ├─ Constituent Snapshot
   ├─ Weight Snapshot
   └─ Evidence Manifest
                        ↓
Return Calculator
   ├─ 일간 수익률
   ├─ 누적 수익률
   ├─ 초과수익률
   ├─ Tracking Difference
   └─ 상대 Drawdown
                        ↓
Portfolio Accounting / Market Regime / Universe
Signal Ranking / Risk / Backtest / Report
```

---

## 8. 입력 계약

### 8.1 BenchmarkDefinitionInput

```python
@dataclass(frozen=True)
class BenchmarkDefinitionInput:
    external_id: str
    name: str
    benchmark_type: str
    series_type: str
    currency: str
    provider: str
    known_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    source_ref: str
```

### 8.2 BenchmarkObservationInput

```python
@dataclass(frozen=True)
class BenchmarkObservationInput:
    benchmark_id: UUID
    market_date: date
    value: Decimal
    observed_at: datetime
    received_at: datetime
    source_id: UUID
    source_revision: str
    raw_hash: str
```

### 8.3 ConstituentEventInput

```python
@dataclass(frozen=True)
class ConstituentEventInput:
    benchmark_id: UUID
    event_type: str
    announced_at: datetime
    known_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    external_security_id: str
    raw_weight: Decimal | None
    source_id: UUID
    source_ref: str
    revision: int
```

---

## 9. 출력 계약

### 9.1 BenchmarkSnapshot

```python
@dataclass(frozen=True)
class BenchmarkSnapshot:
    snapshot_id: UUID
    benchmark_id: UUID
    benchmark_version: str
    market_date: date
    series_type: str
    official_value: Decimal
    daily_return: Decimal | None
    status: str
    observation_ids: tuple[UUID, ...]
    policy_hash: str
    snapshot_hash: str
    finalized_at: datetime
```

### 9.2 ConstituentSnapshot

```python
@dataclass(frozen=True)
class ConstituentSnapshot:
    snapshot_id: UUID
    benchmark_id: UUID
    as_of: datetime
    status: str
    constituent_count: int
    weight_sum: Decimal | None
    members: tuple["ConstituentMember", ...]
    evidence_ids: tuple[UUID, ...]
    snapshot_hash: str
```

### 9.3 RelativePerformanceResult

```python
@dataclass(frozen=True)
class RelativePerformanceResult:
    portfolio_id: UUID
    benchmark_id: UUID
    start_date: date
    end_date: date
    portfolio_return: Decimal
    benchmark_return: Decimal
    excess_return: Decimal
    tracking_error: Decimal | None
    information_ratio: Decimal | None
    status: str
    evidence_hash: str
```

---

## 10. 데이터베이스 설계

### 10.1 benchmark_definitions

```sql
CREATE TABLE benchmark_definitions (
    benchmark_id TEXT PRIMARY KEY,
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    benchmark_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    currency TEXT NOT NULL,
    calculation_method TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    known_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    source_ref TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    UNIQUE(external_id, provider, valid_from, revision)
);
```

### 10.2 benchmark_series

```sql
CREATE TABLE benchmark_series (
    series_id TEXT PRIMARY KEY,
    benchmark_id TEXT NOT NULL,
    series_type TEXT NOT NULL,
    base_date TEXT,
    base_value TEXT,
    currency TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    known_at TEXT NOT NULL,
    series_hash TEXT NOT NULL,
    FOREIGN KEY (benchmark_id) REFERENCES benchmark_definitions(benchmark_id)
);
```

### 10.3 benchmark_observations

```sql
CREATE TABLE benchmark_observations (
    observation_id TEXT PRIMARY KEY,
    series_id TEXT NOT NULL,
    market_date TEXT NOT NULL,
    value TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    supersedes_observation_id TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(series_id, market_date, source_id, source_revision),
    FOREIGN KEY (series_id) REFERENCES benchmark_series(series_id)
);
```

### 10.4 benchmark_constituent_events

```sql
CREATE TABLE benchmark_constituent_events (
    event_id TEXT PRIMARY KEY,
    benchmark_id TEXT NOT NULL,
    listing_id TEXT,
    security_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    announced_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    raw_weight TEXT,
    normalized_weight TEXT,
    source_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    revision INTEGER NOT NULL,
    supersedes_event_id TEXT,
    status TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    FOREIGN KEY (benchmark_id) REFERENCES benchmark_definitions(benchmark_id)
);
```

### 10.5 benchmark_constituent_snapshots

```sql
CREATE TABLE benchmark_constituent_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    benchmark_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    status TEXT NOT NULL,
    constituent_count INTEGER NOT NULL,
    weight_sum TEXT,
    policy_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    finalized_at TEXT,
    UNIQUE(benchmark_id, as_of, snapshot_hash)
);
```

### 10.6 benchmark_constituent_members

```sql
CREATE TABLE benchmark_constituent_members (
    snapshot_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    listing_id TEXT,
    weight TEXT,
    rank INTEGER,
    source_event_id TEXT NOT NULL,
    member_hash TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, security_id),
    FOREIGN KEY (snapshot_id)
        REFERENCES benchmark_constituent_snapshots(snapshot_id)
);
```

### 10.7 benchmark_runs

```sql
CREATE TABLE benchmark_runs (
    run_id TEXT PRIMARY KEY,
    market_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    input_manifest_hash TEXT NOT NULL,
    output_manifest_hash TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    failure_code TEXT
);
```

### 10.8 benchmark_reason_events

```sql
CREATE TABLE benchmark_reason_events (
    reason_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    benchmark_id TEXT,
    security_id TEXT,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    observed_value TEXT,
    expected_value TEXT,
    source_ref TEXT,
    reason_hash TEXT NOT NULL
);
```

---

## 11. 핵심 알고리즘

### 11.1 벤치마크 선택

전략 또는 포트폴리오 정책에 따라 벤치마크를 결정한다.

```python
def select_benchmark(portfolio, policy, available):
    candidates = [
        b for b in available
        if b.currency == portfolio.currency
        and b.status == "ACTIVE"
        and b.series_type == policy.required_series_type
    ]

    exact = [
        b for b in candidates
        if b.benchmark_type == policy.preferred_benchmark_type
    ]

    if len(exact) == 1:
        return exact[0]

    if len(exact) > 1:
        raise BenchmarkAmbiguousError()

    if policy.allow_fallback:
        return resolve_policy_fallback(candidates, policy)

    raise BenchmarkMissingError()
```

벤치마크가 없을 때 임의로 KOSPI를 선택하지 않는다.

### 11.2 일간 수익률

```text
R_t = Index_t / Index_(t-1) - 1
```

전 거래일은 KRX 거래 캘린더를 사용해 결정한다. 달력상 전일을 사용하지 않는다.

```python
def daily_return(current, previous):
    if current <= 0 or previous <= 0:
        raise InvalidBenchmarkValue()
    return (current / previous) - Decimal("1")
```

### 11.3 기간 누적 수익률

```text
Cumulative Return
= Product(1 + R_t) - 1
```

가격지수와 총수익지수는 기간 중 전환하지 않는다.

### 11.4 초과수익률

```text
Excess Return_t
= Portfolio Return_t - Benchmark Return_t
```

누적 초과수익률은 단순히 일간 초과수익률을 합산하지 않고 각각의 누적가치를 계산한 뒤 비교한다.

```text
Portfolio Wealth_t = Product(1 + Rp_t)
Benchmark Wealth_t = Product(1 + Rb_t)
Relative Wealth_t  = Portfolio Wealth_t / Benchmark Wealth_t
```

### 11.5 Tracking Error

```text
Tracking Error
= std(Rp_t - Rb_t) × sqrt(연환산 계수)
```

한국 주식 일간 데이터의 기본 연환산 계수는 정책상 252로 둘 수 있으나 코드 상수가 아니라 정책 Snapshot으로 관리한다.

### 11.6 Information Ratio

```text
Information Ratio
= annualized excess return / tracking error
```

관측치가 정책상 최소 개수보다 적거나 tracking error가 0이면 `NOT_ENOUGH_HISTORY`로 반환한다.

### 11.7 구성종목 Snapshot 생성

```python
def build_constituent_snapshot(events, evaluation_time, policy):
    visible = [
        e for e in events
        if e.known_at <= evaluation_time
        and e.effective_from <= evaluation_time
        and (e.effective_to is None or evaluation_time < e.effective_to)
    ]

    latest = latest_revision_per_security(visible)

    if has_core_conflict(latest):
        return conflicted_snapshot(latest)

    members = apply_add_remove_events(latest)
    members = resolve_canonical_identity(members)

    validate_no_duplicate_security(members)
    validate_weights(members, policy)

    return finalize_snapshot(members, policy)
```

### 11.8 가중치 검사

가중치 제공 지수는 다음 조건을 검사한다.

```text
모든 weight >= 0
중복 security_id 없음
weight_sum은 정책 허용오차 내 1.0 또는 100.0
```

가중치가 제공되지 않는 지수는 임의 동일가중치로 변환하지 않는다. `WEIGHTS_NOT_PROVIDED` 상태로 저장한다.

### 11.9 편입·편출 이벤트

```text
ADD
REMOVE
WEIGHT_CHANGE
RECLASSIFY
REBALANCE
CORRECTION
CANCEL
```

정정은 기존 이벤트를 수정하지 않고 새 revision과 `supersedes_event_id`를 생성한다.

### 11.10 ETF Proxy 추적차이

```text
Tracking Difference_t
= ETF Return_t - Index Return_t
```

ETF 종가를 사용하는 경우 분배금과 NAV 기준 여부를 명시한다. 가격지수와 ETF 총수익을 직접 비교하지 않는다.

---

## 12. 공급원 대사

### 12.1 지수값 대사

```text
공급원 A 값
공급원 B 값
        ↓
절대차이 또는 상대차이 허용범위 이내
        ↓
RECONCILED
```

허용범위를 초과하면 평균을 사용하지 않는다.

```text
CONFLICTED_BENCHMARK_VALUE
→ 수익률 계산 금지
→ 상대성과 보고 차단
```

### 12.2 구성종목 대사

두 원천의 구성종목 집합을 비교한다.

```text
missing_in_source_a
missing_in_source_b
weight_mismatch_count
identity_unresolved_count
```

핵심 구성종목이 충돌하면 `CONFLICTED_CONSTITUENTS`로 처리한다.

---

## 13. Reason Code

```text
BENCHMARK_FINALIZED
BENCHMARK_DEGRADED
MISSING_BENCHMARK_DEFINITION
MISSING_BENCHMARK_CLOSE
INVALID_BENCHMARK_VALUE
BENCHMARK_DATE_MISMATCH
FUTURE_BENCHMARK_DATA
CONFLICTED_BENCHMARK_VALUE
MISSING_PREVIOUS_TRADING_DAY_VALUE
SERIES_TYPE_MISMATCH
BENCHMARK_AMBIGUOUS
CONSTITUENT_SNAPSHOT_FINALIZED
CONFLICTED_CONSTITUENTS
INCOMPLETE_CONSTITUENT_SET
DUPLICATE_CONSTITUENT
UNRESOLVED_CONSTITUENT_IDENTITY
INVALID_WEIGHT
WEIGHT_SUM_OUT_OF_TOLERANCE
WEIGHTS_NOT_PROVIDED
FUTURE_CONSTITUENT_EVENT
ANNOUNCED_NOT_EFFECTIVE
REVISION_SUPERSEDED
SURVIVORSHIP_BIAS_GUARD
ETF_PROXY_USED
TRACKING_ERROR_NOT_ENOUGH_HISTORY
```

각 사유에는 다음 증거를 기록한다.

```text
reason_code
severity
observed_value
expected_value
threshold
source_ref
reason_hash
```

---

## 14. 코드 구조

```text
benchmarking/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── definitions.py
├── observations.py
├── calendars.py
├── reconciliation.py
├── constituents.py
├── weights.py
├── point_in_time.py
├── returns.py
├── relative_performance.py
├── tracking.py
├── etf_proxy.py
├── reason_codes.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

### 14.1 Engine 골격

```python
class BenchmarkIndexConstituentsEngine:
    def run(self, request: BenchmarkRunRequest) -> BenchmarkRunResult:
        policy = self.policy_repository.load_snapshot(
            request.policy_version,
            request.evaluation_time,
        )

        definition = self.definition_resolver.resolve(
            request.benchmark_selector,
            request.evaluation_time,
        )

        observation = self.observation_resolver.finalize(
            definition=definition,
            market_date=request.market_date,
            evaluation_time=request.evaluation_time,
            policy=policy,
        )

        constituents = self.constituent_builder.build(
            benchmark_id=definition.benchmark_id,
            evaluation_time=request.evaluation_time,
            policy=policy,
        )

        snapshot = self.snapshot_factory.create(
            definition=definition,
            observation=observation,
            constituents=constituents,
            policy=policy,
        )

        self.repository.save_atomically(snapshot)
        return BenchmarkRunResult.from_snapshot(snapshot)
```

---

## 15. 핵심 불변식

```text
동일 benchmark/series/market_date의 final observation은 1개

FINALIZED benchmark value > 0

일간 수익률 계산에는 연속된 거래일의 동일 series_type만 사용

가격지수와 총수익지수 혼합 금지

known_at이 평가시각보다 늦은 이벤트 사용 금지

발표됐지만 미효력인 구성 변경 사용 금지

동일 constituent snapshot 내 security_id 중복 금지

가중치 제공 지수의 weight는 음수 금지

가중치 합계가 허용오차를 벗어나면 FINALIZED 금지

CONFLICTED benchmark로 상대성과 계산 금지

CONFLICTED constituent snapshot을 Universe 기준으로 사용 금지

현재 구성종목을 과거 시점에 소급 사용 금지

정정은 append-only revision으로 관리

동일 입력·정책·평가시각이면 동일 canonical hash
```

---

## 16. 실패 처리

| 실패 | 처리 |
|---|---|
| 벤치마크 정의 없음 | `BLOCKED_BENCHMARK_DEFINITION` |
| 당일 지수 종가 누락 | `BLOCKED_BENCHMARK_VALUE` |
| 이전 거래일 값 누락 | 일간 수익률만 차단, Snapshot은 정책에 따라 DEGRADED |
| 공급원 값 충돌 | `CONFLICTED`, 평균 사용 금지 |
| 구성종목 일부 누락 | 임계치 이내 DEGRADED, 초과 시 BLOCKED |
| 식별 불가 종목 존재 | 해당 종목 격리, 비율에 따라 DEGRADED/BLOCKED |
| 가중치 합계 불일치 | `WEIGHT_SUM_OUT_OF_TOLERANCE` |
| 미래 이벤트 탐지 | 이벤트 제외 + 감사 이벤트 기록 |
| 저장 중 장애 | final manifest 생성 금지, 재실행 가능 |

`NO_ACTION`과 벤치마크 장애를 구분한다.

```text
정상 데이터로 평가했지만 후보 없음
→ NO_ACTION

벤치마크 데이터가 없어 상대성과 계산 불가
→ BLOCKED_BENCHMARK 또는 REPORT_DEGRADED
```

---

## 17. 테스트 계획

### 17.1 단위 테스트

1. 동일 series_type 일간 수익률 계산
2. 가격지수·총수익지수 혼합 차단
3. KRX 거래일 기준 이전 관측치 선택
4. 평가시각 이후 known_at 이벤트 제외
5. 발표 후 효력 전 구성 변경 제외
6. 중복 구성종목 탐지
7. 가중치 합계 허용오차 검사
8. 음수 가중치 차단
9. revision 우선순위 결정
10. canonical hash 결정론 검증

### 17.2 고정 통합 시나리오

```text
A. KOSPI 공식 종가 정상 수신
→ FINALIZED
→ 일간 수익률 계산

B. KOSPI 200 가격지수와 TR지수 동시 수신
→ 별도 series 유지
→ 혼합 계산 0건

C. 6월 정기변경 발표 후 효력 전 평가
→ 기존 구성 유지
→ ANNOUNCED_NOT_EFFECTIVE

D. 효력일 장 마감 평가
→ 신규 구성 Snapshot 생성
→ 기존 Snapshot 보존

E. 현재 구성종목으로 2년 전 백테스트 요청
→ point-in-time Snapshot 사용
→ SURVIVORSHIP_BIAS_GUARD 통과

F. 공급원별 지수 종가 충돌
→ CONFLICTED_BENCHMARK_VALUE
→ 상대성과 계산 0건

G. 구성종목 200개 중 1개 식별 실패
→ 정책 임계치 내 DEGRADED
→ 실패 종목 evidence 기록

H. 가중치 합계 98.7%
→ WEIGHT_SUM_OUT_OF_TOLERANCE
→ FINALIZED 금지

I. KODEX 200을 프록시로 사용
→ ETF_PROXY_USED
→ 지수와 ETF 수익률 별도 저장

J. 정정 공시 도착
→ revision 증가
→ 이전 Snapshot 불변
→ 새 snapshot hash 생성

K. 동일 입력 재실행
→ 동일 결과와 동일 hash

L. DB 저장 중 장애
→ final manifest 없음
→ 원자적 재실행 가능
```

### 17.3 속성 테스트

```text
모든 FINALIZED value > 0

동일 입력 순서를 바꿔도 snapshot hash 동일

known_at > evaluation_time 이벤트 사용 수 = 0

동일 snapshot 내 security_id 중복 수 = 0

가격지수와 총수익지수 혼합 계산 수 = 0

CONFLICTED observation으로 생성된 상대성과 수 = 0

revision 정정 후 과거 레코드 수정 수 = 0
```

### 17.4 회귀 테스트

- KOSPI/KOSDAQ/KOSPI 200 고정 20거래일 fixture
- 정기변경 전후 10거래일 구성종목 fixture
- KODEX 200 종가·분배금·NAV fixture
- 종목코드 변경과 구성종목 이벤트 결합 fixture
- 10거래일 PAPER 포트폴리오와 상대성과 fixture

---

## 18. 다른 엔진과의 계약

### Instrument Master & Security Identity Resolution Engine

```text
외부 구성종목 코드
→ security_id / listing_id로 변환
```

식별 실패 종목을 종목명만으로 강제 결합하지 않는다.

### Market Data Finalization & Freshness Engine

```text
벤치마크 종가 FINALIZED
→ 일일 보고서 상대성과 계산 허용
```

### Universe Selection & Eligibility Engine

지수 구성종목 Universe 전략은 point-in-time constituent snapshot만 사용한다.

### Corporate Actions & Adjusted Pricing Engine

지수 총수익계열과 개별 종목 조정주가를 혼합하지 않는다.

### Portfolio Accounting & Performance Engine

```text
Portfolio daily return
+ Benchmark daily return
→ Excess return / Tracking error / Relative wealth
```

### Backtest Engine

과거 구성종목 Snapshot과 당시 알려진 revision만 사용해 생존편향을 차단한다.

### Paper Trading & Portfolio Continuity Engine

매일 동일 benchmark series를 이어서 사용하며, 벤치마크 변경 시 명시적 전환 이벤트를 생성한다.

### Report Engine

보고서에 다음을 반드시 포함한다.

```text
benchmark name
benchmark version
series type
market date
benchmark return
portfolio excess return
snapshot hash
DEGRADED/BLOCKED reason
```

---

## 19. 구현 우선순위

```text
불변 BenchmarkDefinition·Series·Observation 모델
→ SQLite migration
→ KRX 거래일 기반 수익률 계산
→ 동일 series_type guard
→ point-in-time constituent event 모델
→ Instrument Master identity adapter
→ 구성종목 Snapshot builder
→ 가중치 validator
→ 공급원 대사
→ canonical hash와 Manifest
→ Portfolio Accounting 상대성과 adapter
→ Backtest 생존편향 방지 fixture
→ PAPER 10거래일 통합 테스트
```

---

## 20. 완료 기준

다음 조건을 모두 만족하면 v1 구현 완료로 간주한다.

1. KOSPI·KOSPI 200·KODEX 200 정의와 계열을 분리 저장할 수 있다.
2. 동일 series_type의 일간·누적 수익률을 결정론적으로 계산한다.
3. 특정 과거 시점의 구성종목 Snapshot을 재현할 수 있다.
4. 발표일과 효력일을 구분한다.
5. 미래 known_at 데이터를 과거 실행에서 차단한다.
6. 구성종목과 가중치 충돌을 자동 평균·보정하지 않는다.
7. 현재 구성종목을 과거 백테스트에 소급 사용하지 않는다.
8. 상대성과 결과에 benchmark version과 snapshot hash가 남는다.
9. 정정은 append-only revision으로 보존된다.
10. 고정 fixture에서 동일 입력은 동일 결과 hash를 생성한다.

---

## 21. 설계 결론

Benchmark & Index Constituents Engine은 단순히 KOSPI 종가 한 개를 저장하는 모듈이 아니다. ADE의 시장국면, 상대강도, Universe, 백테스트, PAPER 성과 및 일일 보고서가 모두 동일한 벤치마크 정의와 동일한 시점의 구성종목을 사용하도록 강제하는 기준 계층이다.

이 엔진이 없으면 ADE는 현재의 지수 구성종목을 과거에 소급 적용하거나, 가격지수와 총수익지수를 혼합하거나, ETF 프록시의 추적오차를 지수 성과로 오인할 수 있다. 따라서 v1의 최우선 통제는 **point-in-time constituent snapshot, series-type separation, append-only revision, survivorship-bias guard**이다.
