# 35. Market Data Finalization & Freshness Engine v1

## 1. 목적

Market Data Finalization & Freshness Engine은 한국 주식시장 장 마감 후 ADE가 사용하는 가격·거래량·지수·종목 상태 데이터가 **실제로 해당 거래일의 확정 데이터인지**, **충분히 최신인지**, **서로 시간적으로 일치하는지**를 검증하고 불변 Snapshot으로 확정한다.

이 엔진은 Signal, Risk, Decision을 만들지 않는다. 하위 엔진이 신뢰할 수 있는 `FINALIZED_MARKET_SNAPSHOT`을 제공하거나, 데이터가 불완전할 때 실행을 차단·지연·격리하는 통제 계층이다.

핵심 질문은 다음과 같다.

```text
오늘이 한국거래소 거래일인가?
장 마감 이후 데이터인가?
종가·거래량·지수 값이 해당 거래일에 귀속되는가?
공급원 간 값이 허용 오차 내에서 일치하는가?
정정 가능성이 남은 잠정 데이터인가?
Universe 전체가 동일 cut-off 시점으로 정렬되었는가?
이 Snapshot을 과거에 동일하게 재현할 수 있는가?
```

---

## 2. 책임 경계

### 수행하는 일

- KRX 거래일과 시장 세션 판정
- 장 마감 후 데이터 도착 상태 추적
- 종목별 OHLCV·거래대금·시가총액·거래상태 최신성 검증
- KOSPI·KOSDAQ·KODEX 200 등 벤치마크 데이터 최신성 검증
- 공급원 간 종가·거래량 대사
- 데이터 cut-off 시각과 `known_at` 확정
- 잠정·확정·정정 상태 관리
- 종목별 결측·지연·불일치 사유 기록
- 실행 가능 여부와 신뢰 등급 산출
- canonical snapshot hash 생성

### 수행하지 않는 일

- 종목 적격성 결정
- Feature 계산
- Signal 점수 생성
- 매수·매도·보유 판단
- 가상체결 또는 실주문
- 기업행동의 경제적 효과 계산
- 잘못된 값을 임의 보정하거나 추정 종가로 대체

책임 연결은 다음과 같다.

```text
Raw Market Data Sources
        ↓
Market Data Finalization & Freshness Engine
        ↓
FINALIZED / DEGRADED / BLOCKED Snapshot
        ↓
Data Quality
        ↓
Universe Selection
        ↓
Feature / Signal / Risk / Decision
```

---

## 3. 입력 계약

```python
@dataclass(frozen=True)
class MarketFinalizationRequest:
    run_id: str
    market_date: date
    evaluation_time: datetime
    timezone: str
    markets: tuple[str, ...]
    benchmark_ids: tuple[str, ...]
    universe_snapshot_id: str | None
    policy_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
```

주요 입력:

- 거래 캘린더와 임시휴장 정보
- 종목 마스터와 상장·거래상태
- 종목별 일봉 OHLCV
- 종목별 거래대금·시가총액
- 시장지수·벤치마크 종가
- 데이터 공급원 수신 시각
- 공급원별 원본 payload hash
- 기업행동·가격정정 통지
- 버전이 고정된 Finalization Policy

모든 시각은 저장 시 UTC를 사용하고, 세션 판정은 `Asia/Seoul` 기준으로 수행한다.

---

## 4. 출력 계약

```python
class FinalizationStatus(str, Enum):
    FINALIZED = "FINALIZED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    NOT_TRADING_DAY = "NOT_TRADING_DAY"

@dataclass(frozen=True)
class FinalizedMarketSnapshot:
    snapshot_id: str
    run_id: str
    market_date: date
    status: FinalizationStatus
    finalized_at: datetime
    cutoff_time: datetime
    expected_instrument_count: int
    finalized_instrument_count: int
    degraded_instrument_count: int
    blocked_instrument_count: int
    benchmark_status: str
    source_manifest_hash: str
    policy_hash: str
    snapshot_hash: str
```

종목별 출력:

```python
@dataclass(frozen=True)
class InstrumentFinalizationResult:
    instrument_id: str
    market_date: date
    status: str
    official_close: Decimal | None
    volume: int | None
    trading_value: Decimal | None
    observed_at: datetime | None
    source_count: int
    confidence: str
    reason_codes: tuple[str, ...]
    evidence_hash: str
```

하위 엔진은 `snapshot_id`, `market_date`, `cutoff_time`, `snapshot_hash`를 반드시 입력 lineage에 포함해야 한다.

---

## 5. 상태 모델

### Snapshot 상태

| 상태 | 의미 | 후속 처리 |
|---|---|---|
| `FINALIZED` | 필수 데이터와 벤치마크가 정책을 충족 | 정상 실행 |
| `DEGRADED` | 일부 비핵심 종목이 지연·불일치 | 해당 종목 제외 또는 WATCH_ONLY |
| `BLOCKED` | 지수·핵심 데이터·완전성 기준 미달 | Signal/Decision 실행 금지 |
| `NOT_TRADING_DAY` | 거래일이 아님 | 시장 평가 없이 정상 종료 |

### 종목 상태

```text
PENDING
→ RECEIVED
→ VALIDATED
→ RECONCILED
→ FINALIZED

예외:
PENDING → MISSING
RECEIVED → STALE
VALIDATED → CONFLICTED
RECONCILED → DEGRADED
```

종목 상태를 Snapshot 상태와 혼동하지 않는다. 일부 종목이 `DEGRADED`여도 전체 Snapshot은 정책상 `DEGRADED`로 실행 가능할 수 있다.

---

## 6. 초기 정책

초기 PAPER 정책 예시:

| 항목 | 기준 |
|---|---:|
| 정규장 종료 | 15:30 KST |
| 최초 평가 가능 시각 | 15:40 KST |
| 정상 수신 마감 | 16:10 KST |
| 최종 재시도 마감 | 17:00 KST |
| OHLCV 완전성 | Universe의 99.0% 이상 |
| 공식 종가 존재 | 필수 |
| 거래량 존재 | 필수 |
| 벤치마크 종가 | 필수 |
| 공급원 종가 차이 | 1 tick 또는 5 bps 이하 |
| 공급원 거래량 차이 | 0.1% 이하 |
| 미래 timestamp | 허용 안 함 |
| market_date 불일치 | 허용 안 함 |

정책 값은 코드 상수가 아니라 다음 메타데이터를 가진 불변 Snapshot으로 저장한다.

```text
policy_id
version
known_at
effective_from
effective_to
approved_by
policy_hash
```

---

## 7. 아키텍처

```text
KRX Calendar / KRX Market Data
KIS / Broker / Licensed Vendor
Internal Cache / DataHub
Corporate Action Notices
              ↓
Session Resolver
   ├─ 거래일 확인
   ├─ 조기종료·임시휴장 확인
   └─ 장 종료 cut-off 계산
              ↓
Arrival Tracker
   ├─ 공급원별 수신 상태
   ├─ expected universe 계산
   └─ 지연·누락 탐지
              ↓
Freshness Validator
   ├─ market_date 검증
   ├─ observed_at 검증
   ├─ stale/future timestamp 검사
   └─ 종가·거래량 필수 필드 검사
              ↓
Cross-Source Reconciler
   ├─ 가격 tick 허용오차
   ├─ 거래량 허용오차
   ├─ 거래정지·무거래 구분
   └─ 정정 revision 연결
              ↓
Finalization Resolver
   ├─ 종목 상태 확정
   ├─ 전체 완전성 계산
   ├─ 벤치마크 Gate
   └─ FINALIZED/DEGRADED/BLOCKED
              ↓
Immutable Snapshot + Evidence Manifest
              ↓
Data Quality / Universe / Feature / Signal
```

---

## 8. 데이터베이스

### 8.1 `market_finalization_policies`

```sql
CREATE TABLE market_finalization_policies (
    policy_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    timezone TEXT NOT NULL,
    first_evaluation_delay_minutes INTEGER NOT NULL,
    normal_deadline_minutes INTEGER NOT NULL,
    hard_deadline_minutes INTEGER NOT NULL,
    minimum_completeness_ratio TEXT NOT NULL,
    close_tolerance_bps TEXT NOT NULL,
    volume_tolerance_ratio TEXT NOT NULL,
    known_at TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    approved_by TEXT NOT NULL,
    policy_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
```

### 8.2 `market_sessions`

```sql
CREATE TABLE market_sessions (
    session_id TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    market_date TEXT NOT NULL,
    session_type TEXT NOT NULL,
    open_at TEXT,
    close_at TEXT,
    is_trading_day INTEGER NOT NULL,
    source_ref TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    known_at TEXT NOT NULL,
    UNIQUE(market, market_date)
);
```

### 8.3 `market_data_arrivals`

```sql
CREATE TABLE market_data_arrivals (
    arrival_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    market_date TEXT NOT NULL,
    data_type TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    revision_no INTEGER NOT NULL DEFAULT 1,
    supersedes_arrival_id TEXT,
    UNIQUE(source_id, instrument_id, market_date, data_type, revision_no)
);
```

### 8.4 `market_finalization_runs`

```sql
CREATE TABLE market_finalization_runs (
    run_id TEXT PRIMARY KEY,
    market_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    status TEXT NOT NULL,
    expected_count INTEGER NOT NULL,
    finalized_count INTEGER NOT NULL,
    degraded_count INTEGER NOT NULL,
    blocked_count INTEGER NOT NULL,
    completeness_ratio TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    source_manifest_hash TEXT NOT NULL,
    snapshot_hash TEXT,
    started_at TEXT NOT NULL,
    finalized_at TEXT,
    failure_code TEXT
);
```

### 8.5 `instrument_finalization_results`

```sql
CREATE TABLE instrument_finalization_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    market_date TEXT NOT NULL,
    status TEXT NOT NULL,
    official_close TEXT,
    volume INTEGER,
    trading_value TEXT,
    observed_at TEXT,
    confidence TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    UNIQUE(run_id, instrument_id)
);
```

### 8.6 `market_finalization_reasons`

```sql
CREATE TABLE market_finalization_reasons (
    reason_id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    observed_value TEXT,
    threshold_value TEXT,
    evidence_ref TEXT NOT NULL,
    reason_hash TEXT NOT NULL
);
```

### 8.7 `market_snapshot_manifests`

```sql
CREATE TABLE market_snapshot_manifests (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    market_date TEXT NOT NULL,
    cutoff_time TEXT NOT NULL,
    status TEXT NOT NULL,
    source_manifest_json TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
```

모든 정정은 기존 행을 수정하는 대신 revision과 `supersedes_*` 연결을 사용한다.

---

## 9. 핵심 알고리즘

### 9.1 세션 판정

```python
def resolve_market_session(calendar, market_date, evaluation_time):
    session = calendar.get(market_date)

    if session is None or not session.is_trading_day:
        return NOT_TRADING_DAY

    if evaluation_time < session.close_at:
        return BLOCKED_PRE_CLOSE

    return SESSION_CLOSED
```

캘린더 데이터가 없으면 주말 여부만으로 거래일을 추정하지 않고 `BLOCKED_CALENDAR_UNKNOWN`으로 처리한다.

### 9.2 종목 신선도 검사

```python
def validate_freshness(row, market_date, cutoff_time):
    reasons = []

    if row is None:
        reasons.append("MISSING_DAILY_BAR")
        return reasons

    if row.market_date != market_date:
        reasons.append("MARKET_DATE_MISMATCH")

    if row.observed_at > cutoff_time:
        reasons.append("FUTURE_TIMESTAMP")

    if row.close is None or row.close <= 0:
        reasons.append("INVALID_OFFICIAL_CLOSE")

    if row.volume is None or row.volume < 0:
        reasons.append("INVALID_VOLUME")

    return reasons
```

거래정지 또는 무거래 종목에서 거래량 0은 정상일 수 있으므로 종목 상태 데이터와 함께 판정한다.

### 9.3 공급원 대사

```python
def reconcile_close(primary, secondary, tick_size, policy):
    absolute_diff = abs(primary.close - secondary.close)
    bps_diff = absolute_diff / primary.close * Decimal("10000")

    if absolute_diff <= tick_size:
        return MATCHED

    if bps_diff <= policy.close_tolerance_bps:
        return MATCHED_WITH_TOLERANCE

    return CONFLICTED_CLOSE
```

공급원 값이 충돌하면 우선순위만으로 값을 덮어쓰지 않는다. 원천별 근거를 보존하고 `CONFLICTED`로 격리한다.

### 9.4 완전성 계산

```text
completeness_ratio
= finalized_instrument_count
÷ expected_instrument_count
```

`expected_instrument_count`는 실행 이후 도착한 종목 수가 아니라, 거래일 시작 전 확정된 종목 마스터·Universe 기준으로 계산한다. 그래야 누락 종목이 분모에서 사라지는 오류를 막을 수 있다.

### 9.5 전체 상태 결정

```python
def resolve_snapshot_status(metrics, policy):
    if not metrics.is_trading_day:
        return NOT_TRADING_DAY

    if not metrics.benchmark_finalized:
        return BLOCKED

    if metrics.critical_conflict_count > 0:
        return BLOCKED

    if metrics.completeness_ratio < policy.minimum_completeness_ratio:
        return BLOCKED

    if metrics.degraded_count > 0:
        return DEGRADED

    return FINALIZED
```

### 9.6 재시도와 마감

```text
15:40 최초 평가
→ 미도착 종목 존재
→ PENDING 상태 유지
→ 정책 간격으로 재수집
→ 16:10 정상 마감
→ 기준 충족 시 FINALIZED/DEGRADED
→ 기준 미달 시 재시도
→ 17:00 hard deadline
→ BLOCKED 확정
```

동일 `market_date + policy_hash + source_manifest_hash` 조합의 재실행은 동일 Snapshot hash를 생성해야 한다.

---

## 10. Reason Code

```text
NOT_TRADING_DAY
BLOCKED_CALENDAR_UNKNOWN
BLOCKED_PRE_CLOSE
MISSING_DAILY_BAR
MISSING_BENCHMARK_CLOSE
MARKET_DATE_MISMATCH
STALE_OBSERVATION
FUTURE_TIMESTAMP
INVALID_OFFICIAL_CLOSE
INVALID_VOLUME
MISSING_TRADING_VALUE
CONFLICTED_CLOSE
CONFLICTED_VOLUME
TRADING_STATUS_MISMATCH
SOURCE_REVISION_PENDING
COMPLETENESS_BELOW_THRESHOLD
DEGRADED_PARTIAL_UNIVERSE
FINALIZED_WITH_TOLERANCE
FINALIZED_ALL_REQUIRED_DATA
```

Reason은 다음 구조로 저장한다.

```text
reason_code
+ severity
+ observed_value
+ threshold_value
+ evidence_ref
+ source_hash
+ reason_hash
```

---

## 11. 코드 구조

```text
market_finalization/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── calendar.py
├── sessions.py
├── arrivals.py
├── freshness.py
├── reconciliation.py
├── completeness.py
├── benchmarks.py
├── resolver.py
├── reason_codes.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

### Engine 골격

```python
class MarketDataFinalizationEngine:
    def __init__(
        self,
        calendar,
        source_gateway,
        reconciler,
        repository,
        hasher,
    ):
        self.calendar = calendar
        self.source_gateway = source_gateway
        self.reconciler = reconciler
        self.repository = repository
        self.hasher = hasher

    def run(self, request, policy):
        session = self.calendar.resolve(
            request.market_date,
            request.evaluation_time,
        )

        if not session.is_trading_day:
            return self.repository.finalize_non_trading_day(request, session)

        expected = self.source_gateway.load_expected_instruments(
            request.market_date
        )
        observations = self.source_gateway.load_daily_observations(
            request.market_date,
            request.source_snapshot_ids,
        )

        results = [
            self.reconciler.finalize_instrument(
                instrument_id=instrument_id,
                observations=observations.get(instrument_id, ()),
                session=session,
                policy=policy,
            )
            for instrument_id in expected
        ]

        benchmark_result = self.reconciler.finalize_benchmarks(
            request.benchmark_ids,
            observations,
            session,
            policy,
        )

        status = resolve_snapshot_status(
            summarize(results, benchmark_result),
            policy,
        )

        snapshot_hash = self.hasher.hash_snapshot(
            request=request,
            policy=policy,
            session=session,
            results=results,
            benchmark_result=benchmark_result,
            status=status,
        )

        return self.repository.commit_atomically(
            request,
            session,
            results,
            benchmark_result,
            status,
            snapshot_hash,
        )
```

---

## 12. 실패와 복구

### 공급원 장애

```text
Primary source failure
→ Secondary source 조회
→ 단일 원천 허용 정책 확인
→ 허용 시 DEGRADED
→ 핵심 필드 검증 불가 시 BLOCKED
```

### 부분 저장 실패

Run, 종목 결과, reason, manifest는 하나의 DB 트랜잭션으로 저장한다. 중간 실패 시 final Snapshot을 발행하지 않는다.

### 정정 데이터 도착

```text
기존 Snapshot v1
→ 공급원 정정 수신
→ arrival revision 2 추가
→ 신규 reconciliation run
→ Snapshot v2 생성
→ v1 보존
→ 이후 실행만 v2 참조
```

이미 생성된 과거 의사결정을 자동 덮어쓰지 않는다. 재평가가 필요하면 별도의 `REPLAY` run을 생성한다.

---

## 13. 핵심 안전 불변식

```text
장 마감 전 일봉 Snapshot FINALIZED 금지

거래일 캘린더 미확인 상태에서 거래일 추정 금지

market_date가 다른 데이터를 같은 Snapshot에 혼합 금지

미래 timestamp 데이터 사용 금지

벤치마크 종가 누락 시 성과 보고 FINALIZED 금지

종가 누락 종목에 전일 종가 자동 대입 금지

공급원 충돌 값을 임의 평균하여 확정 금지

expected universe에서 누락 종목을 분모에서 제거 금지

BLOCKED Snapshot으로 Signal·Decision 실행 금지

동일 입력·정책·원천 manifest는 동일 snapshot hash 생성

정정은 append-only revision으로 관리
```

---

## 14. 테스트 계획

### 14.1 단위 테스트

- 정상 거래일 세션 종료 판정
- 주말·공휴일 `NOT_TRADING_DAY`
- 임시휴장 `NOT_TRADING_DAY`
- 장 마감 전 `BLOCKED_PRE_CLOSE`
- market_date 불일치 탐지
- 미래 timestamp 탐지
- 종가 0·음수·None 거부
- 거래정지 종목의 거래량 0 허용
- 가격 1 tick 차이 허용
- 가격 허용오차 초과 충돌
- 완전성 비율 Decimal 계산
- canonical hash 입력 순서 독립성

### 14.2 통합 시나리오

```text
A. 정상 거래일, 전 종목·벤치마크 수신
→ FINALIZED

B. 장 마감 전 실행
→ BLOCKED_PRE_CLOSE
→ 하위 엔진 호출 0건

C. Universe 1,000종목 중 3종목 지연
→ completeness 99.7%
→ DEGRADED
→ 3종목만 신규 후보 제외

D. Universe 1,000종목 중 25종목 누락
→ completeness 97.5%
→ BLOCKED

E. KOSPI 종가 누락
→ MISSING_BENCHMARK_CLOSE
→ BLOCKED

F. 삼성전자 공급원 종가 불일치
→ CONFLICTED_CLOSE
→ 해당 종목 DEGRADED 또는 Snapshot BLOCKED

G. 휴장일 실행
→ NOT_TRADING_DAY
→ Signal·Paper fill 0건
→ 정상 종료 기록

H. 정정 데이터 도착
→ revision 증가
→ 기존 Snapshot 보존
→ 신규 snapshot hash 생성

I. 동일 입력 재실행
→ 동일 결과·동일 hash

J. DB 저장 중 장애
→ final manifest 0건
→ 재실행 가능
```

### 14.3 속성 테스트

```text
0 <= completeness_ratio <= 1

finalized_count + degraded_count + blocked_count
= expected_count

FINALIZED이면 benchmark_status = FINALIZED

BLOCKED이면 downstream_execution_count = 0

모든 finalized 종목의 market_date = request.market_date

모든 observed_at <= cutoff_time

동일 snapshot_hash에 서로 다른 manifest 존재 불가
```

### 14.4 시간 경계 테스트

- 15:29:59 실행
- 15:30:00 실행
- 15:39:59 실행
- 15:40:00 최초 평가
- 16:10:00 정상 마감
- 17:00:00 hard deadline
- 조기폐장일 close time 변경
- KST/UTC 변환과 DST 비적용 확인

---

## 15. 관측성과 운영 지표

```text
finalization_latency_seconds
source_arrival_latency_seconds
instrument_missing_count
instrument_conflict_count
benchmark_missing_count
completeness_ratio
revision_count
blocked_run_count
finalized_with_tolerance_count
```

경보 예시:

```text
완전성 < 99%
→ WARNING

벤치마크 누락
→ CRITICAL

동일 종목 공급원 충돌 반복
→ DATA_SOURCE_DEGRADED

17:00까지 미확정
→ RUN_BLOCKED + 운영자 알림
```

---

## 16. 다른 엔진과의 계약

### Data Quality Engine

- 이 엔진: 데이터가 해당 거래일의 확정·최신 데이터인지 검증
- Data Quality: 값의 논리적·통계적 품질을 검증

### Universe Selection Engine

- `FINALIZED` 종목만 정상 적격성 평가
- `DEGRADED` 종목은 정책에 따라 `WATCH_ONLY` 또는 `EXCLUDED`
- `BLOCKED` Snapshot이면 Universe 실행 금지

### Corporate Actions Engine

- 기업행동 정정과 가격 정정 revision을 source manifest에 포함
- 조정가격을 공식 RAW 종가로 사용하지 않음

### Paper Trading Engine

- 가상체결은 `FINALIZED` RAW 공식 종가만 사용
- 종가 미확정 시 fill 0건
- `NO_ACTION`과 `BLOCKED_DATA`를 구분

### Explainability Engine

보고서에는 다음을 증거로 포함한다.

```text
market_snapshot_id
market_date
cutoff_time
finalization_status
completeness_ratio
benchmark_status
snapshot_hash
차단·저하 reason codes
```

---

## 17. 구현 우선순위

```text
1. 불변 Session·Observation·Result 모델
2. SQLite migration
3. KRX 거래 캘린더 resolver
4. market_date·timestamp·필수필드 순수 검증 함수
5. 가격·거래량 cross-source reconciler
6. completeness와 benchmark gate
7. FINALIZED/DEGRADED/BLOCKED resolver
8. canonical manifest hash
9. atomic repository
10. Data Quality·Universe downstream guard
11. 장 마감 시간 경계 fixture
12. 정정 revision과 REPLAY 통합 테스트
```

---

## 18. 완료 기준

다음 조건을 모두 충족하면 v1 구현 완료로 판단한다.

- 한국거래소 거래일과 장 종료 시각을 결정론적으로 판정
- 종목별 데이터 최신성·귀속일·필수 필드를 검증
- 공급원 간 종가·거래량 대사 가능
- 벤치마크와 Universe 완전성 Gate 작동
- `FINALIZED`, `DEGRADED`, `BLOCKED`, `NOT_TRADING_DAY` 구분
- BLOCKED 시 하위 Signal/Decision 호출 0건
- Snapshot과 evidence manifest를 원자적으로 저장
- 동일 입력의 hash 재현성 보장
- 정정 데이터를 append-only revision으로 처리
- 고정 fixture 통합 테스트 통과

이 엔진을 통해 ADE 일일 종목 평가는 단순히 “데이터가 존재한다”는 조건이 아니라, **장 마감 후 해당 거래일의 확정 데이터가 충분한 완전성과 시간 정합성을 갖췄다**는 증거를 기반으로 실행된다.
