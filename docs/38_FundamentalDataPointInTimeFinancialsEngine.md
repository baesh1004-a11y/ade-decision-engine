# 38. Fundamental Data & Point-in-Time Financials Engine v1

## 1. 문서 목적

본 문서는 ADE가 기업의 재무제표, 실적발표, 재무비율, 컨센서스 및 정정공시를 평가시점 기준으로 안전하게 사용할 수 있도록 하는 `Fundamental Data & Point-in-Time Financials Engine`의 아키텍처, 데이터베이스, 알고리즘, 코드 구조 및 테스트 계획을 정의한다.

이 엔진의 최우선 목표는 다음 두 가지다.

1. 평가시점에 실제로 알 수 있었던 재무정보만 사용한다.
2. 원천 수치, 정규화 수치, 파생 지표, 투자 신호를 서로 분리한다.

본 문서는 설계 완료 기준이며 실행 코드와 운영 검증은 별도 단계다.

---

## 2. 책임 범위

### 2.1 수행 책임

- DART, KRX, 기업 IR, 허가된 데이터 공급업체의 재무 데이터 수집
- 연결/별도, 연간/분기, 잠정/확정, 감사/비감사 구분
- 공시 접수시각과 ADE 인지시각 관리
- 정정공시와 재작성 재무제표의 revision 관리
- 계정과목 표준화 및 원천 taxonomy 보존
- 누적 분기값을 단일 분기값으로 변환
- TTM, 성장률, 마진, 수익성, 레버리지, 현금흐름 지표 계산
- 주당 지표 계산 시 point-in-time 주식수 적용
- 데이터 품질, 완전성, 일관성 및 시점 적합성 판정
- 불변 Fundamental Snapshot 및 evidence hash 생성
- Feature, Signal, Risk, Explainability 계층에 표준 계약 제공

### 2.2 수행하지 않는 책임

- BUY, SELL, HOLD 또는 NO_ACTION 결정 생성
- 목표가격 산출
- 종목 순위 확정
- 주문 생성 또는 체결
- 임의 결측치 보간
- 정정 전 재무제표 삭제
- 현재 시점의 최신 재무정보를 과거 백테스트에 소급 적용

---

## 3. 해결하려는 핵심 오류

```text
2026년 정정공시
→ 2025년 당시 실행에 소급 적용
→ 미래정보 누수

연결 재무제표와 별도 재무제표 혼합
→ 매출·이익·부채 이중 비교 오류

반기 누적 영업이익
→ 2분기 단일 영업이익으로 오인

잠정실적과 확정실적
→ 동일 레코드로 덮어쓰기

주식분할 이후 현재 주식수
→ 과거 EPS 계산에 사용

결측 재무수치
→ 0으로 자동 대입

회계기준 또는 통화 변경
→ 연속 성장률로 단순 연결

공급원 간 수치 불일치
→ 평균값으로 임의 확정
```

---

## 4. 핵심 개념 모델

### 4.1 시점 차원

모든 관측값은 최소 다음 시점을 구분한다.

| 필드 | 의미 |
|---|---|
| `period_start` | 재무기간 시작일 |
| `period_end` | 재무기간 종료일 |
| `filed_at` | 공식 공시 접수시각 |
| `published_at` | 원천이 공개한 시각 |
| `known_at` | ADE가 해당 정보를 사용할 수 있게 된 시각 |
| `recorded_at` | ADE 저장 시각 |
| `effective_from` | 해당 revision이 유효한 시점 |
| `superseded_at` | 후속 revision으로 대체된 시점 |

평가시점 `T`에서는 다음 조건을 만족하는 값만 사용할 수 있다.

```text
known_at <= T
and effective_from <= T
and (superseded_at is null or T < superseded_at)
```

### 4.2 재무제표 범위

| 차원 | 예시 |
|---|---|
| `statement_scope` | CONSOLIDATED, SEPARATE |
| `statement_type` | INCOME, BALANCE_SHEET, CASH_FLOW, EQUITY |
| `period_type` | ANNUAL, QUARTER, HALF_YEAR, NINE_MONTH, TTM |
| `value_basis` | INSTANT, DURATION, CUMULATIVE_YTD, DISCRETE_QUARTER |
| `filing_status` | PRELIMINARY, FILED, AUDITED, RESTATED |
| `accounting_standard` | K-IFRS, IFRS, LOCAL_GAAP |
| `currency` | KRW, USD 등 |

서로 다른 범위의 수치를 명시적 변환 없이 비교하거나 합산하지 않는다.

---

## 5. 상태 모델

### 5.1 Snapshot 상태

| 상태 | 의미 | 후속 처리 |
|---|---|---|
| `FINALIZED` | 필수 수치와 시점 검증 완료 | 전체 Feature 사용 가능 |
| `DEGRADED` | 일부 비핵심 수치 누락 또는 단일 원천 | 제한적 Feature 사용 |
| `CONFLICTED` | 핵심 수치가 원천 간 불일치 | 관련 Feature 차단 |
| `INCOMPLETE` | 필수 재무제표 또는 기간 부족 | 신규 Fundamental Signal 차단 |
| `STALE` | 정책상 허용된 최신성 초과 | 감점 또는 차단 |
| `NOT_APPLICABLE` | 금융업 등 일반 지표 미적용 | 업종별 모델 사용 |
| `BLOCKED` | 미래정보, 식별 오류, 통화/범위 혼합 | 후속 사용 금지 |

### 5.2 개별 관측값 상태

```text
RECEIVED
→ NORMALIZED
→ RECONCILED
→ VALIDATED
→ FINALIZED

예외:
MISSING
DUPLICATE
CONFLICTED
RESTATED
UNRESOLVED_ACCOUNT
FUTURE_KNOWN_AT
```

---

## 6. 아키텍처

```text
DART / KRX / Corporate IR / Licensed Vendor
                    ↓
Raw Filing & Observation Ingestion
   ├─ 원문 metadata
   ├─ 원천 account code
   ├─ 원천 값·단위·통화
   └─ receipt/publish timestamp
                    ↓
Instrument & Issuer Resolution
   ├─ issuer_id
   ├─ security_id
   └─ listing_id
                    ↓
Taxonomy Normalization
   ├─ 원천 계정과목 보존
   ├─ canonical account mapping
   ├─ 단위·부호 정규화
   └─ 연결/별도 범위 검증
                    ↓
Revision & Reconciliation
   ├─ 잠정→확정
   ├─ 감사→정정
   ├─ 공급원 대사
   └─ 충돌 격리
                    ↓
Period Transformer
   ├─ 누적→단일분기
   ├─ TTM
   ├─ 비교기간 정렬
   └─ 회계연도 변경 처리
                    ↓
Fundamental Metric Calculator
   ├─ 성장성
   ├─ 수익성
   ├─ 안정성
   ├─ 현금흐름
   ├─ 자본효율
   └─ 주당 지표
                    ↓
Point-in-Time Snapshot Builder
   ├─ raw evidence refs
   ├─ normalized values
   ├─ derived metrics
   ├─ quality state
   └─ canonical hash
                    ↓
Feature / Signal / Risk / Explainability / Backtest
```

---

## 7. 입력 계약

### 7.1 `RawFundamentalObservation`

```python
@dataclass(frozen=True)
class RawFundamentalObservation:
    source_id: str
    issuer_external_id: str
    filing_id: str
    statement_scope: str
    statement_type: str
    account_code: str
    account_name: str
    period_start: date | None
    period_end: date
    value: Decimal | None
    unit: str
    currency: str
    filed_at: datetime
    published_at: datetime | None
    known_at: datetime
    revision: int
    raw_hash: str
```

### 7.2 필수 입력

- 평가시각
- issuer/security identity snapshot
- 거래 캘린더
- 재무 원천 데이터
- taxonomy mapping version
- fundamental policy snapshot
- corporate action share-count snapshot
- 필요 시 FX snapshot

---

## 8. 출력 계약

### 8.1 `FundamentalSnapshot`

```python
@dataclass(frozen=True)
class FundamentalSnapshot:
    snapshot_id: str
    issuer_id: str
    security_id: str | None
    evaluation_time: datetime
    statement_scope: str
    currency: str
    policy_version: str
    taxonomy_version: str
    status: str
    source_filing_ids: tuple[str, ...]
    observation_hash: str
    metric_hash: str
    snapshot_hash: str
```

### 8.2 `FundamentalMetric`

```python
@dataclass(frozen=True)
class FundamentalMetric:
    metric_code: str
    period_end: date
    period_type: str
    value: Decimal | None
    unit: str
    quality_status: str
    source_observation_ids: tuple[str, ...]
    formula_version: str
    reason_codes: tuple[str, ...]
```

---

## 9. 데이터베이스 설계

### 9.1 핵심 테이블

- `fundamental_sources`
- `fundamental_filings`
- `fundamental_raw_observations`
- `fundamental_account_mappings`
- `fundamental_normalized_observations`
- `fundamental_revisions`
- `fundamental_reconciliation_results`
- `fundamental_metric_definitions`
- `fundamental_metric_values`
- `fundamental_snapshots`
- `fundamental_snapshot_members`
- `fundamental_reason_events`
- `fundamental_runs`

### 9.2 `fundamental_filings`

```sql
CREATE TABLE fundamental_filings (
    filing_id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_filing_key TEXT NOT NULL,
    report_type TEXT NOT NULL,
    statement_scope TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    filing_status TEXT NOT NULL,
    accounting_standard TEXT NOT NULL,
    filed_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    supersedes_filing_id TEXT,
    raw_document_hash TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(source_id, source_filing_key, revision)
);
```

### 9.3 `fundamental_raw_observations`

```sql
CREATE TABLE fundamental_raw_observations (
    observation_id TEXT PRIMARY KEY,
    filing_id TEXT NOT NULL,
    statement_type TEXT NOT NULL,
    source_account_code TEXT NOT NULL,
    source_account_name TEXT NOT NULL,
    value_text TEXT,
    unit TEXT NOT NULL,
    currency TEXT NOT NULL,
    value_basis TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(filing_id) REFERENCES fundamental_filings(filing_id)
);
```

### 9.4 `fundamental_normalized_observations`

```sql
CREATE TABLE fundamental_normalized_observations (
    normalized_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    canonical_account_code TEXT NOT NULL,
    normalized_value_text TEXT,
    normalized_unit TEXT NOT NULL,
    normalized_currency TEXT NOT NULL,
    sign_policy TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    normalization_hash TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES fundamental_raw_observations(observation_id)
);
```

### 9.5 `fundamental_metric_values`

```sql
CREATE TABLE fundamental_metric_values (
    metric_value_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    period_end TEXT NOT NULL,
    period_type TEXT NOT NULL,
    value_text TEXT,
    unit TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    metric_hash TEXT NOT NULL,
    UNIQUE(snapshot_id, metric_code, period_end, period_type),
    FOREIGN KEY(snapshot_id) REFERENCES fundamental_snapshots(snapshot_id)
);
```

### 9.6 저장 원칙

- 금액과 비율은 `Decimal` 문자열로 저장한다.
- 원천 관측값은 수정하지 않는다.
- 정정은 새 filing revision으로 추가한다.
- normalized 값과 derived metric을 분리한다.
- snapshot 확정은 모든 member 저장 이후 원자적으로 수행한다.
- 동일 입력, 정책, 평가시각은 동일 hash를 생성한다.

---

## 10. 계정과목 정규화

### 10.1 Canonical account 예시

```text
REVENUE
COST_OF_REVENUE
GROSS_PROFIT
OPERATING_PROFIT
NET_INCOME_PARENT
TOTAL_ASSETS
TOTAL_LIABILITIES
TOTAL_EQUITY
CASH_AND_EQUIVALENTS
INTEREST_BEARING_DEBT
OPERATING_CASH_FLOW
CAPEX
FREE_CASH_FLOW
SHARES_OUTSTANDING
WEIGHTED_AVERAGE_SHARES
```

### 10.2 매핑 원칙

```text
원천 account code
+ 원천 account name
+ statement type
+ statement scope
+ accounting standard
+ 업종
        ↓
Canonical account code
```

종목명 또는 한글 계정명만으로 자동 매핑하지 않는다. 동일 명칭이라도 현금흐름표와 손익계산서에서 의미가 다를 수 있다.

### 10.3 매핑 신뢰도

| 상태 | 조건 |
|---|---|
| `EXACT` | 공식 taxonomy code 일치 |
| `RULE_MATCHED` | 승인된 deterministic rule |
| `REVIEWED` | 수동 검토 후 승인 |
| `AMBIGUOUS` | 복수 후보 |
| `UNRESOLVED` | 매핑 실패 |

`AMBIGUOUS`와 `UNRESOLVED` 값은 핵심 파생지표 계산에 사용하지 않는다.

---

## 11. 기간 변환 알고리즘

### 11.1 누적값에서 단일 분기값 계산

K-IFRS 분기·반기 보고서의 손익 및 현금흐름은 누적값일 수 있다.

```text
Q1 discrete = Q1 cumulative
Q2 discrete = H1 cumulative - Q1 cumulative
Q3 discrete = 9M cumulative - H1 cumulative
Q4 discrete = FY cumulative - 9M cumulative
```

필수 전제:

- 동일 회계연도
- 동일 연결/별도 범위
- 동일 통화
- 동일 회계기준
- 비교 대상 revision이 평가시점에 이용 가능

하나라도 충족하지 않으면 `DISCRETE_PERIOD_UNAVAILABLE`로 처리한다.

### 11.2 TTM 계산

```text
TTM_t = Q_t + Q_(t-1) + Q_(t-2) + Q_(t-3)
```

또는 누적 데이터가 안정적인 경우:

```text
TTM_t = Latest FY + Current YTD - Prior-Year YTD
```

두 방식의 결과가 허용오차를 초과하면 `TTM_RECONCILIATION_FAILED`로 처리한다.

### 11.3 재무상태표

재무상태표는 기간 누적값이 아니라 특정 시점의 잔액이므로 차감해 단일 분기값을 만들지 않는다.

---

## 12. 파생 지표 알고리즘

### 12.1 성장성

```text
Revenue Growth YoY
= Revenue_t / Revenue_(t-4Q) - 1

Operating Profit Growth YoY
= OperatingProfit_t / OperatingProfit_(t-4Q) - 1
```

기준값이 0 이하인 경우 단순 성장률은 왜곡될 수 있으므로 다음 상태를 기록한다.

```text
BASE_ZERO
BASE_NEGATIVE
SIGN_CHANGE
```

### 12.2 수익성

```text
Gross Margin = Gross Profit / Revenue
Operating Margin = Operating Profit / Revenue
Net Margin = Net Income Parent / Revenue
ROA = TTM Net Income / Average Total Assets
ROE = TTM Net Income Parent / Average Parent Equity
```

평균 자산과 평균 자본은 기초·기말 잔액을 사용한다. 기초 잔액이 없으면 정책에 따라 `DEGRADED` 처리하며 기말값을 임의 대체하지 않는다.

### 12.3 안정성

```text
Debt Ratio = Total Liabilities / Total Equity
Net Debt = Interest-Bearing Debt - Cash and Equivalents
Net Debt to EBITDA = Net Debt / TTM EBITDA
Current Ratio = Current Assets / Current Liabilities
Interest Coverage = TTM Operating Profit / TTM Interest Expense
```

분모가 0 이하이면 수치 대신 명시적 상태를 반환한다.

### 12.4 현금흐름

```text
Free Cash Flow = Operating Cash Flow - Capex
Cash Conversion = Operating Cash Flow / Net Income
FCF Margin = Free Cash Flow / Revenue
```

CAPEX 부호 정책은 원천별로 다를 수 있으므로 canonical sign policy를 적용한다.

### 12.5 주당 지표

```text
EPS = Net Income Available to Common / Weighted Average Shares
BPS = Common Equity / Period-End Shares
FCF per Share = TTM FCF / Weighted Average Shares
```

주식수는 Corporate Actions Engine이 제공하는 평가시점 기준 share snapshot을 사용한다. 현재 주식수를 과거 기간에 소급 적용하지 않는다.

---

## 13. 정정공시와 revision 처리

```text
잠정실적 revision 1
        ↓
확정 사업보고서 revision 2
        ↓
감사 후 정정공시 revision 3
```

각 revision은 append-only로 저장한다.

과거 평가를 재현할 때는 당시 `known_at` 기준 revision을 사용한다. 최신 정정치를 이용한 분석은 별도의 `REPLAY_LATEST_RESTATED` 모드에서 수행하며 원래 의사결정 기록을 덮어쓰지 않는다.

### 13.1 정정 영향 분류

| 등급 | 예시 | 처리 |
|---|---|---|
| `IMMATERIAL` | 표시 단위·주석 정정 | snapshot revision만 추가 |
| `MATERIAL_METRIC_CHANGE` | 매출·이익 수정 | 관련 metric 재계산 |
| `SIGN_FLIP` | 이익→손실 | 모니터링 경보 |
| `IDENTITY_CHANGE` | 연결 범위·사업부 변경 | 자동 연결 차단 |

---

## 14. 공급원 대사

초기 신뢰도 우선순위:

```text
DART 공식 공시 원문
> KRX 공식 실적 정보
> 기업 IR 공식 발표
> 허가된 재무 데이터 공급업체
```

그러나 우선순위만으로 자동 확정하지 않고 핵심 필드를 비교한다.

### 14.1 핵심 대사 필드

- 매출액
- 영업이익
- 지배주주순이익
- 총자산
- 총부채
- 총자본
- 영업현금흐름
- 회계기간
- 연결/별도 범위
- 통화와 단위

허용오차를 초과하는 경우:

```text
CONFLICTED_CORE_FINANCIAL
→ 해당 account와 파생 metric 차단
→ 임의 평균 금지
→ evidence bundle 생성
```

---

## 15. 데이터 품질 점수

```text
quality_score =
    completeness_weight
  + reconciliation_weight
  + freshness_weight
  + taxonomy_weight
  + audit_status_weight
```

초기 정책 예시:

| 항목 | 기준 |
|---|---:|
| 핵심 계정 완전성 | 95% 이상 |
| 공급원 핵심 수치 차이 | 0.1% 또는 정책 절대오차 이하 |
| 미해결 핵심 계정 | 0개 |
| 미래 known_at | 0건 |
| 연결/별도 혼합 | 0건 |
| 통화 혼합 | 0건 |

점수는 투자 Signal이 아니라 데이터 사용 가능성 판단에만 사용한다.

---

## 16. 업종별 처리

일반 제조업 지표를 모든 업종에 강제 적용하지 않는다.

### 16.1 금융업

- 매출 대신 영업수익/이자수익 구조
- 일반 부채비율 대신 BIS, CET1, NPL 등 별도 모델
- 영업현금흐름 비교 제한

### 16.2 보험업

- 보험계약부채
- CSM
- 지급여력비율

### 16.3 지주회사·리츠

- NAV 또는 FFO 기반 별도 지표
- 연결 중복과 자회사 가치 반영 주의

업종별 metric profile이 없으면 `NOT_APPLICABLE_GENERAL_MODEL`로 처리하며 잘못된 일반 지표를 만들지 않는다.

---

## 17. Reason Code

```text
FUNDAMENTAL_FINALIZED
FUNDAMENTAL_DEGRADED
MISSING_CORE_STATEMENT
MISSING_CORE_ACCOUNT
STALE_FUNDAMENTAL_DATA
FUTURE_FILING_INFORMATION
SCOPE_MISMATCH
CURRENCY_MISMATCH
ACCOUNTING_STANDARD_CHANGED
FISCAL_YEAR_CHANGED
UNRESOLVED_ACCOUNT_MAPPING
AMBIGUOUS_ACCOUNT_MAPPING
CONFLICTED_CORE_FINANCIAL
DUPLICATE_OBSERVATION
DISCRETE_PERIOD_UNAVAILABLE
TTM_INSUFFICIENT_HISTORY
TTM_RECONCILIATION_FAILED
BASE_ZERO
BASE_NEGATIVE
SIGN_CHANGE
DIVISION_BY_ZERO
SHARE_COUNT_UNAVAILABLE
RESTATEMENT_DETECTED
MATERIAL_RESTATEMENT
NOT_APPLICABLE_GENERAL_MODEL
FX_SNAPSHOT_MISSING
```

각 Reason에는 다음 증거를 포함한다.

```text
reason_code
severity
observed_value
expected_or_threshold
source_filing_id
evidence_ref
formula_version
reason_hash
```

---

## 18. 결정론적 Snapshot hash

Snapshot hash 입력:

```text
issuer_id
security_id
evaluation_time
statement_scope
currency
selected filing revisions
normalized observation hashes
metric formula versions
policy version
taxonomy version
share-count snapshot hash
FX snapshot hash
sorted reason hashes
```

Canonical JSON 직렬화 후 SHA-256을 사용한다.

입력 순서가 달라도 동일한 경제적 데이터라면 동일 hash가 생성되어야 한다.

---

## 19. 코드 구조

```text
fundamentals/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── adapters/
│   ├── dart.py
│   ├── krx.py
│   ├── corporate_ir.py
│   └── vendor.py
├── ingestion.py
├── identity.py
├── taxonomy.py
├── normalization.py
├── revisions.py
├── reconciliation.py
├── periods.py
├── discrete_quarters.py
├── ttm.py
├── metrics/
│   ├── growth.py
│   ├── profitability.py
│   ├── leverage.py
│   ├── cashflow.py
│   ├── efficiency.py
│   └── per_share.py
├── industry_profiles.py
├── quality.py
├── point_in_time.py
├── reason_codes.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

---

## 20. 엔진 처리 의사코드

```python
def build_fundamental_snapshot(request, repository, policy):
    filings = repository.load_filings(
        issuer_id=request.issuer_id,
        period_end_lte=request.evaluation_time.date(),
    )

    visible = [
        f for f in filings
        if f.known_at <= request.evaluation_time
    ]

    selected = select_point_in_time_revisions(visible)
    observations = load_raw_observations(selected)
    normalized = normalize_accounts(
        observations,
        taxonomy_version=policy.taxonomy_version,
    )

    reconciliation = reconcile_core_values(normalized, policy)
    if reconciliation.has_blocking_conflict:
        return blocked_snapshot(
            reason="CONFLICTED_CORE_FINANCIAL"
        )

    periods = derive_discrete_and_ttm_periods(normalized, policy)
    metrics = calculate_metrics(
        periods=periods,
        share_snapshot=request.share_snapshot,
        industry_profile=request.industry_profile,
        policy=policy,
    )

    quality = evaluate_quality(
        selected,
        normalized,
        metrics,
        reconciliation,
        policy,
    )

    snapshot = assemble_snapshot(
        request=request,
        filings=selected,
        observations=normalized,
        metrics=metrics,
        quality=quality,
        policy=policy,
    )

    repository.save_atomically(snapshot)
    return snapshot
```

---

## 21. 핵심 안전 불변식

```text
known_at > evaluation_time인 filing 사용 수 = 0

연결·별도 재무제표 혼합 수 = 0

서로 다른 통화의 직접 합산 수 = 0

미해결 핵심 계정으로 계산한 metric 수 = 0

정정공시로 기존 filing 삭제·수정 수 = 0

누적 손익 값을 단일 분기로 직접 사용 수 = 0

재무상태표 잔액을 분기 차감한 수 = 0

현재 주식수를 과거 EPS에 소급 적용 수 = 0

CONFLICTED 핵심 수치의 파생 metric 수 = 0

동일 입력·정책·평가시각의 snapshot hash는 동일
```

---

## 22. 테스트 계획

### 22.1 단위 테스트

- 날짜와 `known_at` 경계값
- Decimal 단위 변환
- 부호 정규화
- account mapping exact/rule/ambiguous
- 누적→단일분기 변환
- TTM 두 방식 대사
- 분모 0/음수 처리
- 성장률 sign change 처리
- 연결/별도 범위 guard
- 통화 혼합 guard
- canonical hash 순서 독립성

### 22.2 고정 통합 시나리오

```text
A. 정상 제조업 5개 분기
→ 단일분기·TTM 생성
→ FINALIZED

B. 반기 누적 영업이익
→ Q2 = H1 - Q1
→ 원 누적값 보존

C. 3분기 누적 현금흐름
→ Q3 discrete 변환
→ FCF 계산

D. 잠정실적 후 확정공시
→ revision 2 추가
→ 과거 평가에서는 revision 1 유지

E. 다음 달 정정공시
→ 최신 replay에서는 revision 3
→ 기존 의사결정 snapshot 불변

F. 연결 매출과 별도 영업이익 혼합 요청
→ SCOPE_MISMATCH
→ metric 생성 0건

G. DART와 Vendor 영업이익 불일치
→ CONFLICTED_CORE_FINANCIAL
→ 관련 Signal 입력 차단

H. 현재 주식수만 존재
→ 과거 EPS 계산 금지
→ SHARE_COUNT_UNAVAILABLE

I. 금융업 종목에 일반 제조업 지표 요청
→ NOT_APPLICABLE_GENERAL_MODEL

J. 평가시각 이후 발표된 실적
→ FUTURE_FILING_INFORMATION
→ 사용 0건

K. 회계연도 변경
→ 비교기간 자동 연결 금지
→ DEGRADED 또는 BLOCKED

L. 동일 입력 재실행
→ 동일 metric과 snapshot hash

M. DB 저장 중 장애
→ final snapshot manifest 생성 금지
→ 재실행 시 중복 없음
```

### 22.3 속성 테스트

```text
Q1 + Q2 + Q3 + Q4 = FY
허용오차 이내

모든 finalized metric의 evidence 수 >= 1

모든 metric formula_version은 비어 있지 않음

모든 normalized observation은 원천 observation을 참조

RESTATED filing은 supersedes 관계를 가짐

BLOCKED snapshot은 downstream usable=false
```

### 22.4 회귀 테스트

- 삼성전자와 같은 12월 결산 제조업 fixture
- 3월 또는 6월 결산법인 fixture
- 적자→흑자 전환 fixture
- 대규모 분할 후 EPS fixture
- 합병 또는 연결범위 변경 fixture
- 금융업 별도 profile fixture

---

## 23. 다른 엔진과의 연결

```text
Instrument Master
→ issuer/security/listing 식별

Corporate Actions
→ point-in-time 주식수와 분할 계수

Market Data Finalization
→ 시가총액·가격 기반 배수 계산 시 공식 종가

Data Snapshot & Lineage
→ filing, metric, policy evidence 고정

Feature Engine
→ 성장성·수익성·현금흐름 Feature 수신

Signal Engine
→ Fundamental score 입력

Portfolio Risk
→ 레버리지·유동성·재무건전성 위험 입력

Explainability
→ 사용 수치·기간·공시·formula 근거 출력

Backtest
→ 당시 알려진 재무정보만 사용
```

### 23.1 Feature 계층 전달 예시

```json
{
  "issuer_id": "issuer-001",
  "evaluation_time": "2026-08-06T16:30:00+09:00",
  "snapshot_hash": "sha256:...",
  "metrics": {
    "revenue_growth_yoy": "0.1240",
    "operating_margin_ttm": "0.1835",
    "roe_ttm": "0.1472",
    "net_debt_to_ebitda": "0.81",
    "fcf_margin_ttm": "0.0960"
  },
  "status": "FINALIZED"
}
```

---

## 24. 초기 정책 제안

| 항목 | 초기값 |
|---|---:|
| 최소 분기 이력 | 5개 분기 |
| TTM 최소 단일분기 | 4개 |
| 핵심 계정 완전성 | 95% |
| 핵심 원천 대사 허용오차 | 0.1% |
| Decimal 정밀도 | 28자리 |
| 자동 account mapping 최소 신뢰도 | 0.98 |
| 정정 수치 material threshold | 1% 또는 정책 절대금액 |
| 재무 최신성 경고 | 업종·보고주기별 정책 |
| 미래 known_at 허용 | 0건 |

정책값은 코드 상수가 아니라 `known_at`, `effective_from`, `effective_to`, 승인자 및 hash를 가진 Policy Snapshot으로 관리한다.

---

## 25. 구현 우선순위

```text
불변 Filing·Observation·Metric 모델
→ SQLite migration
→ DART 원천 adapter fixture
→ issuer identity adapter
→ canonical account taxonomy v1
→ Decimal 단위·부호 정규화
→ point-in-time revision selector
→ 누적→단일분기 변환
→ TTM 계산기
→ 성장성·수익성·안정성·현금흐름 metric
→ share-count 연동 EPS/BPS
→ 공급원 대사와 conflict guard
→ quality resolver
→ canonical snapshot hash
→ Feature Engine adapter
→ 미래정보 차단 백테스트
```

---

## 26. 완료 기준

다음 조건을 모두 만족하면 v1 구현 완료로 본다.

1. 5개 분기 고정 fixture에서 단일분기 및 TTM이 정확히 계산된다.
2. 잠정·확정·정정공시가 append-only revision으로 보존된다.
3. 과거 평가시점에서 미래 filing이 단 한 건도 사용되지 않는다.
4. 연결/별도, 통화, 회계기준 혼합이 차단된다.
5. 핵심 수치 충돌 시 파생 metric이 생성되지 않는다.
6. Corporate Actions의 point-in-time 주식수로 EPS가 계산된다.
7. 동일 입력과 정책으로 동일 snapshot hash가 생성된다.
8. Snapshot에서 원천 filing까지 evidence 추적이 가능하다.
9. Feature·Signal 계층이 raw 공시값을 직접 참조하지 않는다.
10. 통합 테스트에서 `FINALIZED`, `DEGRADED`, `CONFLICTED`, `BLOCKED`가 모두 검증된다.

---

## 27. 요약

`Fundamental Data & Point-in-Time Financials Engine v1`은 ADE의 가치·품질·성장·재무위험 판단에 필요한 재무정보의 기준 계층이다. 이 엔진은 최신 수치를 제공하는 것보다 **당시 알 수 있었던 정확한 수치와 그 근거를 재현 가능하게 제공하는 것**을 우선한다.

핵심 원칙은 다음과 같다.

```text
원천과 파생값을 분리한다.

공시기간과 인지시각을 분리한다.

잠정·확정·정정을 덮어쓰지 않는다.

누적값과 단일분기값을 혼합하지 않는다.

연결·별도와 통화를 혼합하지 않는다.

미래 재무정보를 과거 의사결정에 사용하지 않는다.

모든 metric은 formula version과 evidence를 가진다.
```
