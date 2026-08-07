# 39. Valuation & Cross-Sectional Factor Engine v1

## 1. 문서 목적

이 문서는 AI Decision Engine(ADE)의 `Valuation & Cross-Sectional Factor Engine v1` 설계를 정의한다.

이 엔진은 Point-in-Time 재무정보, 가격, 주식수, 기업행동, 업종 분류를 결합하여 종목별 가치·품질·성장·안정성·현금흐름 팩터를 계산하고, 동일 업종 또는 비교가능 집단 내에서 횡단면 점수와 순위를 생성한다.

이 엔진은 최종 BUY·SELL·주문을 생성하지 않는다. 출력은 Feature 및 Signal Generation Engine이 소비하는 근거 데이터이다.

---

## 2. 핵심 책임

### 2.1 수행 책임

1. 평가시점에 이용 가능했던 재무 Snapshot 선택
2. 평가시점의 RAW 가격 및 주식수 선택
3. 시가총액·기업가치 계산
4. 가치·품질·성장·재무안정성·현금흐름 팩터 계산
5. 업종별 적용 가능 지표 분리
6. 극단값 처리와 결측치 상태 기록
7. 업종·시장·규모 그룹 내 횡단면 정규화
8. 복합 Factor Score 생성
9. Point-in-Time Factor Snapshot과 evidence hash 생성
10. Feature·Signal·Explainability 계층에 표준 계약 제공

### 2.2 수행하지 않는 책임

- 투자 후보 Universe 생성
- 최종 Signal 임계값 결정
- 포트폴리오 비중 결정
- 주문가격·수량 결정
- 기업행동 자체 계산
- 재무 원천 계정 정규화
- 시장가격 확정

---

## 3. 설계 목표

```text
Point-in-Time Fundamental Snapshot
+ RAW / Adjusted Market Snapshot
+ Share Count Snapshot
+ Industry Classification Snapshot
        ↓
Valuation & Cross-Sectional Factor Engine
        ↓
Raw Factors
Normalized Factors
Composite Scores
Factor Evidence Manifest
        ↓
Feature Engine
Signal Generation & Ranking
Risk Engine
Explainability
Backtest
```

핵심 목표는 다음과 같다.

```text
미래 실적정보 사용 금지
현재 주식수를 과거 가치평가에 사용 금지
업종별 부적합 지표 강제 적용 금지
적자기업 PER 왜곡 방지
음수 기업가치·분모 0 처리 명시
극단값을 임의 삭제하지 않고 정책 기반 처리
현재 횡단면 통계를 과거 백테스트에 소급 사용 금지
동일 입력·정책·시각이면 동일 Factor Snapshot hash
```

---

## 4. 입력 계약

### 4.1 필수 입력

```python
FactorRunRequest(
    run_id,
    evaluation_time,
    market_date,
    universe_snapshot_id,
    fundamental_snapshot_id,
    market_snapshot_id,
    share_count_snapshot_id,
    industry_snapshot_id,
    factor_policy_snapshot_id,
)
```

### 4.2 종목별 입력

```text
security_id
listing_id
market
industry_code
industry_profile
raw_close
shares_outstanding
free_float_shares(optional)
market_cap(optional precomputed)
cash_and_equivalents
interest_bearing_debt
minority_interest
preferred_equity
revenue_ttm
operating_income_ttm
net_income_common_ttm
ebitda_ttm
operating_cashflow_ttm
capex_ttm
free_cashflow_ttm
total_assets
average_total_assets
common_equity
average_common_equity
gross_profit_ttm
current_assets
current_liabilities
filing_known_at
price_observed_at
```

### 4.3 입력 전제

- Fundamental Data Engine의 `FINALIZED` 또는 정책상 허용된 `DEGRADED` Snapshot
- Market Data Finalization Engine의 확정 가격
- Corporate Actions Engine의 시점별 주식수
- Instrument Master의 canonical `security_id`
- Universe Selection Engine의 평가 대상 종목 집합

---

## 5. 출력 계약

### 5.1 실행 결과

```python
FactorRunResult(
    run_id,
    status,
    market_date,
    evaluation_time,
    instrument_count,
    finalized_count,
    degraded_count,
    blocked_count,
    factor_snapshot_id,
    snapshot_hash,
    reason_codes,
)
```

### 5.2 종목별 결과

```python
InstrumentFactorResult(
    security_id,
    status,
    raw_factors,
    normalized_factors,
    composite_scores,
    peer_group_id,
    evidence_refs,
    reason_codes,
    result_hash,
)
```

### 5.3 상태

| 상태 | 의미 |
|---|---|
| `FINALIZED` | 필수 지표와 횡단면 점수가 정상 생성됨 |
| `DEGRADED` | 일부 지표 결측이나 비핵심 이상이 있으나 제한적 사용 가능 |
| `BLOCKED` | 핵심 시점정보·가격·주식수·재무정보가 없어 사용 금지 |
| `NOT_APPLICABLE` | 업종 특성상 일반 모델 적용 대상이 아님 |
| `INSUFFICIENT_PEERS` | 비교집단 표본이 부족하여 횡단면 점수 생성 불가 |

---

## 6. 아키텍처

```text
Fundamental Snapshot ───────┐
Market Price Snapshot ──────┤
Share Count Snapshot ───────┤
Industry Classification ────┤
Universe Snapshot ──────────┘
              ↓
Input Contract Validator
              ↓
Point-in-Time Join
   ├─ known_at 검사
   ├─ market_date 검사
   ├─ security_id 검사
   └─ snapshot hash 검사
              ↓
Capital Structure Calculator
   ├─ market capitalization
   ├─ net debt
   └─ enterprise value
              ↓
Raw Factor Calculators
   ├─ valuation
   ├─ quality
   ├─ growth
   ├─ leverage
   ├─ cash flow
   └─ efficiency
              ↓
Applicability & Quality Gate
              ↓
Cross-Sectional Processor
   ├─ peer grouping
   ├─ winsorization
   ├─ robust scaling
   ├─ percentile ranking
   └─ direction alignment
              ↓
Composite Score Builder
              ↓
Immutable Factor Snapshot
              ↓
Feature / Signal / Risk / Explainability
```

---

## 7. 시점 정합성

평가시점 `T`에서 사용하는 모든 입력은 다음 조건을 충족해야 한다.

```text
fundamental.known_at <= T
price.observed_at <= T
share_count.known_at <= T
industry_classification.known_at <= T
policy.known_at <= T
```

재무 기간 종료일이 과거라는 이유만으로 사용할 수 있는 것은 아니다.

예:

```text
2026-03-31 분기 종료
2026-05-15 공시
2026-04-30 평가
→ 해당 분기 실적 사용 금지
```

횡단면 통계 또한 평가시점 당시 Universe와 당시 이용 가능한 데이터로 다시 계산한다.

```text
현재 종목 집합의 평균·표준편차
→ 과거 백테스트에 사용 금지
```

---

## 8. 자본구조 계산

### 8.1 시가총액

```text
Market Capitalization
= RAW Close × Shares Outstanding
```

주식수는 평가시점의 Corporate Actions Snapshot을 사용한다.

```text
현재 발행주식수 × 과거 가격
→ 금지
```

### 8.2 순차입금

```text
Net Debt
= Interest-Bearing Debt
- Cash and Cash Equivalents
```

### 8.3 기업가치

```text
Enterprise Value
= Market Capitalization
+ Interest-Bearing Debt
+ Preferred Equity
+ Minority Interest
- Cash and Cash Equivalents
```

기업가치가 0 이하인 경우 EV 기반 배수를 일반적인 방식으로 해석하지 않는다.

```text
NON_POSITIVE_ENTERPRISE_VALUE
```

---

## 9. 가치 팩터

### 9.1 Earnings Yield

```text
Earnings Yield
= Net Income Common TTM / Market Capitalization
```

PER 대신 수익률 방향으로 통일하면 다른 팩터와 결합하기 쉽다.

순이익이 음수인 경우 값은 음수로 유지하되 일반 PER 순위와 혼합하지 않는다.

### 9.2 Book-to-Market

```text
Book-to-Market
= Common Equity / Market Capitalization
```

자본총계가 음수이면 다음 상태를 기록한다.

```text
NEGATIVE_COMMON_EQUITY
```

### 9.3 Sales Yield

```text
Sales Yield
= Revenue TTM / Market Capitalization
```

### 9.4 Free-Cash-Flow Yield

```text
FCF Yield
= Free Cash Flow TTM / Market Capitalization
```

### 9.5 EBIT / EV

```text
EBIT Yield
= Operating Income TTM / Enterprise Value
```

### 9.6 EBITDA / EV

```text
EBITDA Yield
= EBITDA TTM / Enterprise Value
```

분모가 0 이하이면 생성하지 않는다.

---

## 10. 품질 팩터

### 10.1 ROE

```text
ROE
= Net Income Common TTM / Average Common Equity
```

평균 자본이 0 이하이면 일반 ROE 비교를 차단한다.

### 10.2 ROA

```text
ROA
= Net Income TTM / Average Total Assets
```

### 10.3 Operating Margin

```text
Operating Margin
= Operating Income TTM / Revenue TTM
```

### 10.4 Gross Profitability

```text
Gross Profitability
= Gross Profit TTM / Average Total Assets
```

### 10.5 Cash Conversion

```text
Cash Conversion
= Operating Cash Flow TTM / Net Income TTM
```

순이익이 0 또는 음수이면 일반 비율 대신 상태를 기록한다.

### 10.6 Accruals

초기 단순 모델:

```text
Total Accruals
= Net Income TTM - Operating Cash Flow TTM

Accrual Ratio
= Total Accruals / Average Total Assets
```

낮은 Accrual Ratio를 높은 품질로 해석한다.

---

## 11. 성장 팩터

### 11.1 매출 성장

```text
Revenue Growth YoY
= Revenue TTM / Revenue TTM Previous Year - 1
```

### 11.2 영업이익 성장

```text
Operating Income Growth YoY
= Operating Income TTM / Prior Operating Income TTM - 1
```

기준값이 0 또는 음수이면 일반 성장률 순위에 바로 포함하지 않는다.

```text
BASE_ZERO
BASE_NEGATIVE
SIGN_CHANGE
```

### 11.3 FCF 성장

```text
FCF Growth YoY
= FCF TTM / Prior FCF TTM - 1
```

### 11.4 성장 안정성

최근 8개 분기 또는 정책 지정 기간이 있을 때:

```text
Growth Stability
= - standard_deviation(quarterly_growth_rates)
```

변동성이 낮을수록 높은 점수 방향으로 변환한다.

---

## 12. 안정성 및 레버리지 팩터

### 12.1 Debt-to-Equity

```text
Debt to Equity
= Total Liabilities / Common Equity
```

Common Equity가 0 이하이면 계산하지 않는다.

### 12.2 Net Debt / EBITDA

```text
Net Debt to EBITDA
= Net Debt / EBITDA TTM
```

EBITDA가 0 이하이면 일반 레버리지 비교에서 제외한다.

### 12.3 Interest Coverage

```text
Interest Coverage
= Operating Income TTM / Interest Expense TTM
```

이자비용이 0이면 무한대 값을 저장하지 않고 상한 상태를 사용한다.

### 12.4 Current Ratio

```text
Current Ratio
= Current Assets / Current Liabilities
```

업종별 적용 가능 여부를 확인한다.

---

## 13. 업종별 적용 모델

### 13.1 일반 제조·서비스업

사용 가능:

```text
Earnings Yield
Book-to-Market
FCF Yield
EBIT/EV
ROE
ROA
Margins
Accruals
Growth
Net Debt/EBITDA
```

### 13.2 은행

일반 EV·EBITDA 모델을 적용하지 않는다.

초기 허용 지표:

```text
Book-to-Market
ROE
ROA
Earnings Yield
자본적정성 지표가 있을 경우 별도 확장
```

### 13.3 보험

```text
Book-to-Market
ROE
Earnings Yield
CSM·지급여력 관련 전용 지표는 별도 버전
```

### 13.4 증권

```text
Book-to-Market
ROE
Earnings Yield
순차입금/EBITDA 일반 적용 금지
```

### 13.5 리츠

일반 순이익·PER보다 다음 지표를 우선한다.

```text
FFO Yield
NAV Discount
Distribution Yield
Debt Ratio
```

전용 데이터가 없으면:

```text
NOT_APPLICABLE_REIT_MODEL
```

---

## 14. 비교집단 구성

기본 peer group 우선순위:

```text
시장 + 세부업종
→ 시장 + 중분류 업종
→ 전체 시장 + 중분류 업종
→ 전체 시장
```

정책 예시:

| 항목 | 기본값 |
|---|---:|
| 최소 비교종목 수 | 20 |
| 권장 비교종목 수 | 40 |
| 최대 업종 상향 단계 | 3 |
| 신규상장 최소 재무 이력 | 4분기 |

비교집단이 최소 표본 수보다 작으면 무리하게 전체시장 점수를 만들지 않고 `INSUFFICIENT_PEERS`를 반환할 수 있다.

---

## 15. 극단값 처리

### 15.1 원칙

- 원천값 삭제 금지
- raw value 보존
- normalized value에만 정책 적용
- 처리 전후 값을 모두 기록

### 15.2 Winsorization

기본 정책 예시:

```text
lower percentile = 1%
upper percentile = 99%
```

표본이 작으면 percentile 방식 대신 Median Absolute Deviation를 사용할 수 있다.

### 15.3 Robust Z-Score

```text
robust_z
= (x - median) / (1.4826 × MAD)
```

MAD가 0이면:

```text
ZERO_CROSS_SECTIONAL_DISPERSION
```

### 15.4 Percentile Rank

```text
percentile_rank ∈ [0, 1]
```

높을수록 좋은 팩터와 낮을수록 좋은 팩터의 방향을 통일한다.

```text
높을수록 좋음:
Earnings Yield, FCF Yield, ROE, Margin, Growth

낮을수록 좋음:
Accrual Ratio, Debt Ratio, Net Debt/EBITDA
```

---

## 16. 결측치 처리

결측치를 0으로 대체하지 않는다.

| 상태 | 처리 |
|---|---|
| 원천 계정 없음 | `MISSING_SOURCE_ACCOUNT` |
| 분모 0 | `ZERO_DENOMINATOR` |
| 분모 음수 | 지표별 별도 상태 |
| 업종 부적합 | `NOT_APPLICABLE` |
| 시점 불일치 | `POINT_IN_TIME_MISMATCH` |
| 재무 이력 부족 | `INSUFFICIENT_HISTORY` |

복합점수는 최소 가용 팩터 수를 충족할 때만 생성한다.

```text
available_factor_count >= policy.minimum_factor_count
```

그렇지 않으면 `COMPOSITE_NOT_AVAILABLE`이다.

---

## 17. 복합 점수

### 17.1 하위 점수

```text
Value Score
Quality Score
Growth Score
Financial Strength Score
Cash Flow Score
```

### 17.2 기본 가중치 예시

```text
Value              30%
Quality            30%
Growth             20%
Financial Strength 10%
Cash Flow          10%
```

가중치는 코드 상수가 아니라 승인된 `factor_policy_snapshot`에 저장한다.

### 17.3 가중 평균

```text
Composite Score
= Σ(normalized_factor_i × effective_weight_i)
  / Σ(effective_weight_i)
```

결측 팩터가 있을 때 가중치를 자동 재배분할지 여부는 정책으로 통제한다.

기본 정책:

```text
핵심 팩터 결측
→ 복합점수 차단

비핵심 팩터 결측
→ 허용 범위 내에서 가중치 재정규화
→ DEGRADED 표시
```

### 17.4 점수 안정화

단일 날짜 점수 급변을 추적하기 위해:

```text
score_change
= current_composite_score - previous_score
```

재무 정정, 가격 급변, 비교집단 변경을 구분하여 reason event로 기록한다.

---

## 18. 데이터베이스 설계

### 18.1 `factor_policies`

```sql
CREATE TABLE factor_policies (
    policy_id TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL,
    known_at TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    minimum_peer_count INTEGER NOT NULL,
    winsor_lower TEXT,
    winsor_upper TEXT,
    scaling_method TEXT NOT NULL,
    composite_weights_json TEXT NOT NULL,
    policy_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
```

### 18.2 `factor_definitions`

```sql
CREATE TABLE factor_definitions (
    factor_definition_id TEXT PRIMARY KEY,
    factor_code TEXT NOT NULL,
    factor_version TEXT NOT NULL,
    category TEXT NOT NULL,
    direction TEXT NOT NULL,
    formula_text TEXT NOT NULL,
    applicability_profile TEXT NOT NULL,
    required_inputs_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL UNIQUE,
    UNIQUE(factor_code, factor_version)
);
```

### 18.3 `factor_runs`

```sql
CREATE TABLE factor_runs (
    run_id TEXT PRIMARY KEY,
    market_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    universe_snapshot_id TEXT NOT NULL,
    fundamental_snapshot_id TEXT NOT NULL,
    market_snapshot_id TEXT NOT NULL,
    share_count_snapshot_id TEXT NOT NULL,
    industry_snapshot_id TEXT NOT NULL,
    factor_policy_id TEXT NOT NULL,
    status TEXT NOT NULL,
    instrument_count INTEGER NOT NULL,
    finalized_count INTEGER NOT NULL,
    degraded_count INTEGER NOT NULL,
    blocked_count INTEGER NOT NULL,
    snapshot_hash TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
```

### 18.4 `raw_factor_values`

```sql
CREATE TABLE raw_factor_values (
    raw_factor_value_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    factor_definition_id TEXT NOT NULL,
    raw_value TEXT,
    numerator_value TEXT,
    denominator_value TEXT,
    status TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, security_id, factor_definition_id)
);
```

### 18.5 `peer_groups`

```sql
CREATE TABLE peer_groups (
    peer_group_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    market_code TEXT,
    industry_code TEXT,
    grouping_level TEXT NOT NULL,
    member_count INTEGER NOT NULL,
    group_hash TEXT NOT NULL UNIQUE
);
```

### 18.6 `normalized_factor_values`

```sql
CREATE TABLE normalized_factor_values (
    normalized_factor_value_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    factor_definition_id TEXT NOT NULL,
    peer_group_id TEXT NOT NULL,
    winsorized_value TEXT,
    z_score TEXT,
    percentile_rank TEXT,
    aligned_score TEXT,
    status TEXT NOT NULL,
    normalization_hash TEXT NOT NULL,
    UNIQUE(run_id, security_id, factor_definition_id)
);
```

### 18.7 `factor_composite_scores`

```sql
CREATE TABLE factor_composite_scores (
    composite_score_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    score_type TEXT NOT NULL,
    score_value TEXT,
    available_factor_count INTEGER NOT NULL,
    expected_factor_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    score_hash TEXT NOT NULL,
    UNIQUE(run_id, security_id, score_type)
);
```

### 18.8 `factor_reason_events`

```sql
CREATE TABLE factor_reason_events (
    reason_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT,
    factor_code TEXT,
    reason_code TEXT NOT NULL,
    observed_value TEXT,
    threshold_value TEXT,
    evidence_ref TEXT,
    created_at TEXT NOT NULL
);
```

### 18.9 `factor_snapshot_manifests`

```sql
CREATE TABLE factor_snapshot_manifests (
    factor_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    market_date TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    input_manifest_hash TEXT NOT NULL,
    member_manifest_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL UNIQUE,
    finalized_at TEXT NOT NULL
);
```

---

## 19. 주요 알고리즘

### 19.1 Point-in-Time Join

```python
def select_visible_record(records, evaluation_time):
    visible = [
        r for r in records
        if r.known_at <= evaluation_time
        and r.valid_from <= evaluation_time
        and (r.valid_to is None or evaluation_time < r.valid_to)
    ]
    return select_latest_revision(visible)
```

### 19.2 안전한 비율 계산

```python
def safe_ratio(numerator, denominator, policy):
    if numerator is None or denominator is None:
        return Missing("MISSING_INPUT")
    if denominator == 0:
        return Missing("ZERO_DENOMINATOR")
    if not policy.allow_negative_denominator and denominator < 0:
        return Missing("NEGATIVE_DENOMINATOR")
    return Decimal(numerator) / Decimal(denominator)
```

### 19.3 Robust Normalization

```python
def robust_normalize(values):
    median = decimal_median(values)
    mad = decimal_median([abs(v - median) for v in values])

    if mad == 0:
        return ZeroDispersionResult()

    scale = Decimal("1.4826") * mad
    return [(v - median) / scale for v in values]
```

### 19.4 방향 정렬

```python
def align_direction(percentile_rank, direction):
    if direction == "HIGHER_IS_BETTER":
        return percentile_rank
    if direction == "LOWER_IS_BETTER":
        return Decimal("1") - percentile_rank
    raise UnsupportedDirection(direction)
```

### 19.5 복합점수

```python
def build_composite_score(factors, weights, policy):
    available = [f for f in factors if f.is_usable]

    if any(f.is_core and not f.is_usable for f in factors):
        return Blocked("MISSING_CORE_FACTOR")

    if len(available) < policy.minimum_factor_count:
        return Blocked("INSUFFICIENT_FACTOR_COVERAGE")

    effective_weights = renormalize_weights(available, weights)
    score = sum(
        f.aligned_score * effective_weights[f.factor_code]
        for f in available
    )
    return Finalized(score)
```

---

## 20. 결정론과 Hash

### 20.1 정렬 규칙

Hash 생성 전 다음 순서로 정렬한다.

```text
security_id
factor_code
factor_version
peer_group_id
```

### 20.2 Decimal 직렬화

- 지수표기 금지
- trailing zero 정책 통일
- locale 구분자 금지
- NaN·Infinity 저장 금지

### 20.3 Snapshot Hash

```text
snapshot_hash
= SHA256(
    policy_hash
    + input_manifest_hash
    + sorted_member_hashes
  )
```

---

## 21. Reason Code

```text
MISSING_MARKET_PRICE
MISSING_SHARE_COUNT
MISSING_FUNDAMENTAL_SNAPSHOT
MISSING_SOURCE_ACCOUNT
POINT_IN_TIME_MISMATCH
FUTURE_FINANCIAL_INFORMATION
FUTURE_SHARE_COUNT_INFORMATION
ZERO_DENOMINATOR
NEGATIVE_DENOMINATOR
NEGATIVE_COMMON_EQUITY
NON_POSITIVE_ENTERPRISE_VALUE
NEGATIVE_EBITDA
BASE_ZERO
BASE_NEGATIVE
SIGN_CHANGE
INSUFFICIENT_HISTORY
INSUFFICIENT_PEERS
ZERO_CROSS_SECTIONAL_DISPERSION
OUTLIER_WINSORIZED
PEER_GROUP_ESCALATED
INDUSTRY_MODEL_NOT_APPLICABLE
NOT_APPLICABLE_REIT_MODEL
MISSING_CORE_FACTOR
INSUFFICIENT_FACTOR_COVERAGE
COMPOSITE_NOT_AVAILABLE
FACTOR_DEGRADED
FACTOR_FINALIZED
```

---

## 22. 코드 구조

```text
factors/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── definitions.py
├── point_in_time.py
├── joins.py
├── capital_structure.py
├── calculators/
│   ├── valuation.py
│   ├── quality.py
│   ├── growth.py
│   ├── leverage.py
│   ├── cashflow.py
│   └── efficiency.py
├── applicability/
│   ├── general.py
│   ├── banks.py
│   ├── insurance.py
│   ├── securities.py
│   └── reits.py
├── peer_groups.py
├── outliers.py
├── normalization.py
├── ranking.py
├── composites.py
├── reason_codes.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

---

## 23. API 예시

```python
class ValuationFactorEngine:
    def run(self, request: FactorRunRequest) -> FactorRunResult:
        inputs = self.input_loader.load(request)
        self.contract_validator.validate(inputs)

        joined = self.point_in_time_joiner.join(inputs)
        raw_results = self.raw_factor_calculator.calculate(joined)
        applicable = self.applicability_gate.apply(raw_results)

        peer_groups = self.peer_group_builder.build(applicable)
        normalized = self.normalizer.normalize(applicable, peer_groups)
        composites = self.composite_builder.build(normalized)

        manifest = self.manifest_builder.build(
            request=request,
            raw_results=raw_results,
            normalized=normalized,
            composites=composites,
        )

        return self.repository.commit_atomically(
            request,
            raw_results,
            normalized,
            composites,
            manifest,
        )
```

---

## 24. 테스트 전략

### 24.1 단위 테스트

#### 가치 팩터

```text
정상 시가총액 계산
정상 기업가치 계산
현금이 부채보다 큰 순현금 기업
기업가치 0 이하
적자기업 Earnings Yield
음수 자본 Book-to-Market
FCF 음수
```

#### 품질 팩터

```text
정상 ROE·ROA
평균자본 0
영업이익률 음수
Accrual Ratio 방향성
영업현금흐름과 순이익 부호 차이
```

#### 성장 팩터

```text
정상 YoY 성장
기준값 0
기준값 음수
적자→흑자 전환
흑자→적자 전환
분기 이력 부족
```

#### 정규화

```text
Robust Z-Score
MAD 0
1%·99% winsorization
동점 percentile rank
높을수록 좋은 방향
낮을수록 좋은 방향
입력 순서 변경 불변성
```

### 24.2 데이터베이스 테스트

```text
동일 run/security/factor 중복 저장 차단
실패 시 manifest 미생성
원자적 commit
정정 재무정보의 새 run 생성
기존 factor snapshot 불변
Decimal 왕복 정확성
```

### 24.3 통합 테스트 시나리오

#### A. 정상 제조업 50종목

```text
가격·주식수·재무정보 정상
→ 가치·품질·성장 팩터 생성
→ 업종 peer group 생성
→ FINALIZED
```

#### B. 적자기업

```text
순이익 음수
→ PER 생성 금지
→ Earnings Yield 음수 보존
→ 다른 팩터로 제한적 평가
→ DEGRADED 또는 FINALIZED 정책 판정
```

#### C. 음수 자본 기업

```text
Common Equity < 0
→ Book-to-Market·ROE 차단
→ NEGATIVE_COMMON_EQUITY
```

#### D. 순현금 기업

```text
Cash > Debt
→ Net Debt 음수 허용
→ Enterprise Value 정상 계산
```

#### E. EV 0 이하

```text
Enterprise Value <= 0
→ EBIT/EV·EBITDA/EV 생성 금지
→ NON_POSITIVE_ENTERPRISE_VALUE
```

#### F. 금융업

```text
은행 종목
→ 일반 EV/EBITDA·Current Ratio 적용 금지
→ 은행 프로필 팩터만 생성
```

#### G. 비교집단 부족

```text
세부업종 8종목
→ 중분류로 상향
→ 25종목 확보
→ PEER_GROUP_ESCALATED
```

#### H. 비교집단 최종 부족

```text
전체 허용 집단 12종목
→ INSUFFICIENT_PEERS
→ 횡단면 복합점수 생성 금지
```

#### I. 미래정보 누수

```text
평가시각 이후 공시된 실적
→ 사용 수 0
→ FUTURE_FINANCIAL_INFORMATION
```

#### J. 기업행동 전후

```text
액면분할
→ 과거 평가에는 당시 주식수 사용
→ 시가총액 연속성 확인
```

#### K. 재무 정정공시

```text
정정 전 run
→ 기존 factor snapshot 유지
정정 후 replay
→ 새 snapshot hash 생성
```

#### L. 동일 입력 재실행

```text
동일 입력·정책·평가시각
→ 동일 raw factor
→ 동일 peer group
→ 동일 composite score
→ 동일 snapshot hash
```

---

## 25. 속성 기반 테스트

```text
Market Cap >= 0

Shares Outstanding > 0인 경우
Market Cap = Price × Shares

모든 percentile rank는 0 이상 1 이하

모든 aligned score는 0 이상 1 이하

BLOCKED 종목의 composite score는 null

미래 known_at 입력 사용 수 = 0

동일 peer group 내 동일 값은 동일 rank 정책 적용

입력 순서를 바꿔도 snapshot hash 동일

원천 raw factor는 winsorization으로 변경되지 않음

복합점수의 유효 가중치 합 = 1
```

---

## 26. 성능 테스트

초기 목표:

| 항목 | 목표 |
|---|---:|
| 종목 수 | 3,000 |
| 팩터 수 | 30 |
| 전체 계산 | 10초 이내 |
| Snapshot 저장 | 5초 이내 |
| 메모리 | 1GB 이내 |

최적화 우선순위:

1. Point-in-Time 입력 사전 조회
2. Decimal 계산 배치화
3. peer group별 단일 정렬
4. factor definition 캐시
5. hash canonical serialization 스트리밍

정확성을 희생하는 float 변환은 기본 허용하지 않는다.

---

## 27. 관측성과 운영지표

```text
factor_run_duration_seconds
factor_instrument_count
factor_finalized_count
factor_degraded_count
factor_blocked_count
factor_missing_rate_by_code
factor_peer_group_size
factor_outlier_rate
factor_composite_coverage_rate
factor_snapshot_hash_mismatch_count
future_information_block_count
```

경보 예시:

```text
핵심 팩터 결측률 > 10%
복합점수 커버리지 < 80%
전일 대비 중간값 급변
특정 업종 전체 BLOCKED
동일 입력 hash 불일치
```

---

## 28. 다른 엔진과의 연결

### Fundamental Data Engine

```text
정규화된 Point-in-Time 재무 수치 제공
```

### Corporate Actions Engine

```text
평가시점 주식수·분할·병합 정보 제공
```

### Market Data Finalization Engine

```text
확정 RAW 가격 제공
```

### Instrument Master

```text
security_id와 업종 식별 연결
```

### Universe Selection Engine

```text
계산 대상 종목 집합 제공
```

### Feature Engine

```text
raw factor·normalized factor·composite score 소비
```

### Signal Generation Engine

```text
가치·품질·성장 점수를 기술적 신호와 결합
```

### Explainability Engine

```text
점수 구성요소, 비교집단, 원천 evidence 제공
```

### Backtest Engine

```text
평가 당시 횡단면 점수 재현
```

---

## 29. 안전 불변식

```text
현재 재무정보의 과거 사용 금지

현재 주식수의 과거 사용 금지

RAW 가격과 조정가격의 목적 혼합 금지

적자기업에 양수 PER 순위 부여 금지

기업가치 0 이하인 종목의 EV 배수 생성 금지

업종 부적합 지표 생성 금지

결측치를 0으로 대체 금지

원천값 winsorization 금지

비교집단 최소 표본 미달 시 허위 정규화 금지

복합점수 산식·가중치·정책 hash 기록

동일 입력·정책·평가시각이면 동일 결과
```

---

## 30. 구현 우선순위

```text
1. FactorDefinition·RawFactorValue 불변 모델
2. SQLite migration
3. Capital Structure 계산기
4. 안전한 Decimal ratio 함수
5. 가치 팩터 계산기
6. 품질·성장·레버리지 계산기
7. 업종 applicability profile
8. peer group builder
9. winsorization·robust scaling·percentile rank
10. composite score builder
11. Point-in-Time join guard
12. canonical hash·manifest
13. Fundamental·Market·Corporate Actions adapter
14. 50종목 고정 fixture 통합 테스트
15. 미래정보·정정공시·기업행동 replay 테스트
```

---

## 31. 완료 기준

다음 조건이 충족되면 v1 구현 완료로 본다.

```text
모든 필수 테이블 migration 존재

핵심 팩터 순수 함수 구현

업종별 applicability guard 구현

Point-in-Time 입력 선택 구현

횡단면 peer group·정규화 구현

복합점수와 reason code 구현

Snapshot hash 결정론 검증

고정 fixture 단위·통합 테스트 통과

미래정보 사용 0건 검증

Feature Engine용 JSON 계약 출력 확인
```

---

## 32. 최종 요약

Valuation & Cross-Sectional Factor Engine은 Fundamental Data Engine이 제공한 재무 원천값을 직접 투자결정으로 연결하지 않고, 시점 정합성과 업종 적합성을 보장한 가치·품질·성장·안정성 팩터로 변환한다.

이 엔진의 핵심은 단순한 PER·PBR 계산이 아니다.

```text
Point-in-Time 재무정보
+ 당시 가격
+ 당시 주식수
+ 업종별 적용 가능성
+ 당시 비교집단
+ 결정론적 정규화
+ 증거와 hash
```

를 결합하여 백테스트와 PAPER·실운영에서 동일하게 재현 가능한 횡단면 Factor Snapshot을 만드는 것이 핵심이다.
