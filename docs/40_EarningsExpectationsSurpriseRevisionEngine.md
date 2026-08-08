# 40. Earnings Expectations, Surprise & Revision Engine v1

## 1. 문서 목적

이 문서는 AI Decision Engine(ADE)의 `Earnings Expectations, Surprise & Revision Engine v1` 설계를 정의한다.

이 엔진은 평가시점에 실제로 이용 가능했던 시장 기대치(analyst consensus / estimate), 기업의 실제 실적(actual), 추정치 변경 이력(revision)을 결합하여 다음을 생성한다.

- Point-in-Time Consensus Snapshot
- Earnings Surprise
- Revenue / Operating Income / EPS Surprise
- Estimate Revision Momentum
- Revision Breadth
- Estimate Dispersion
- Guidance Surprise / Guidance Revision
- Post-Earnings Evidence Manifest

이 엔진은 BUY·SELL·주문을 직접 생성하지 않는다. 출력은 Feature, Signal, Risk, Explainability, Backtest 계층이 소비한다.

핵심 목표는 단순히 `실적이 좋다/나쁘다`를 판단하는 것이 아니라, 다음 질문에 재현 가능하게 답하는 것이다.

```text
그 실적은 시장이 당시 기대했던 값보다 얼마나 좋았는가?
기대치 자체가 발표 전 수주 동안 상향 또는 하향되고 있었는가?
애널리스트 간 의견이 얼마나 일치했는가?
실적발표 시각 이전에 알려진 추정치만 사용했는가?
발표 후 수정된 컨센서스를 과거 surprise 계산에 섞지 않았는가?
```

---

## 2. 핵심 책임

### 2.1 수행 책임

1. 공급원별 애널리스트 추정치 수집 및 정규화
2. 회계기간·발표 이벤트·종목 식별 정합성 검증
3. `known_at` 기반 Point-in-Time 추정치 선택
4. 실적 발표 직전 Consensus Snapshot 동결
5. actual 실적과 consensus 비교
6. 매출·영업이익·순이익·EPS 등 surprise 계산
7. 추정치 상향·하향 revision 추세 계산
8. revision breadth 및 analyst participation 계산
9. dispersion / uncertainty 계산
10. 신규 추정치 유입과 기존 추정치 수정 구분
11. guidance 대비 consensus 변화 추적
12. 공급원 충돌·stale estimate·표본 부족 차단
13. immutable snapshot / evidence hash 생성
14. Feature·Signal·Risk·Explainability 계층에 표준 계약 제공

### 2.2 수행하지 않는 책임

- 기업 재무 원천공시 해석 자체
- 종목 Universe 선정
- 시장가격 확정
- 최종 Signal 임계값 결정
- 포트폴리오 비중 결정
- 주문가격·수량 결정
- 투자자문 문구 생성

---

## 3. 설계 목표

```text
Broker / Vendor Estimates
Corporate Guidance
Fundamental Actuals
Instrument Master
Trading Calendar
        ↓
Estimate Ingestion & Normalization
        ↓
Point-in-Time Estimate Ledger
        ↓
Pre-Event Consensus Freezer
        ↓
Actual-vs-Consensus Surprise
        ↓
Revision / Breadth / Dispersion
        ↓
Quality & Leakage Gate
        ↓
Immutable Expectations Snapshot
        ↓
Feature / Signal / Risk / Explainability / Backtest
```

핵심 안전 목표:

```text
실적 발표 이후 수정된 추정치를 발표 직전 consensus로 사용 금지
미래 known_at 정보 사용 금지
현재 컨센서스를 과거 백테스트에 소급 사용 금지
기간이 다른 추정치와 actual 비교 금지
연결·별도 범위 혼합 금지
통화·단위 혼합 금지
애널리스트 1명 값을 consensus로 위장 금지
표본이 너무 적은 surprise 점수의 과신 금지
negative denominator에서 일반 surprise % 왜곡 금지
동일 입력·정책·평가시각이면 동일 Snapshot hash
```

---

## 4. 입력 계약

### 4.1 실행 요청

```python
ExpectationRunRequest(
    run_id,
    evaluation_time,
    market_date,
    universe_snapshot_id,
    instrument_master_snapshot_id,
    fundamental_snapshot_id,
    estimate_policy_snapshot_id,
    event_calendar_snapshot_id,
    market_snapshot_id=None,
)
```

### 4.2 추정치 원천 입력

```text
estimate_id
source_id
analyst_id(optional hashed/pseudonymous)
broker_id(optional)
security_id / vendor_symbol
metric_code
fiscal_period_type
fiscal_year
fiscal_quarter
period_start
period_end
scope              # CONSOLIDATED / SEPARATE
currency
unit
estimate_value
estimate_type      # POINT / LOW / HIGH
published_at
known_at
recorded_at
revision
supersedes_estimate_id
```

### 4.3 actual 입력

Fundamental Data & Point-in-Time Financials Engine의 확정 값을 사용한다.

```text
security_id
metric_code
period_start
period_end
scope
currency
unit
actual_value
filing_id
published_at
known_at
revision
fundamental_snapshot_id
```

### 4.4 Event 입력

```text
event_id
security_id
event_type            # EARNINGS_RELEASE / GUIDANCE / PRELIMINARY / RESTATEMENT
scheduled_at(optional)
announced_at(optional)
actual_release_at
known_at
fiscal_period_end
source_id
```

---

## 5. 출력 계약

### 5.1 실행 결과

```python
ExpectationRunResult(
    run_id,
    status,
    market_date,
    evaluation_time,
    instrument_count,
    finalized_count,
    degraded_count,
    blocked_count,
    expectations_snapshot_id,
    snapshot_hash,
    reason_codes,
)
```

### 5.2 종목별 결과

```python
InstrumentExpectationResult(
    security_id,
    status,
    fiscal_period,
    event_id,
    consensus_snapshot_id,
    metric_results,
    revision_features,
    dispersion_features,
    guidance_features,
    evidence_refs,
    reason_codes,
    result_hash,
)
```

### 5.3 Metric 결과

```python
ExpectationMetricResult(
    metric_code,
    consensus_value,
    consensus_method,
    analyst_count,
    actual_value,
    surprise_absolute,
    surprise_pct,
    standardized_surprise,
    dispersion,
    status,
    reason_codes,
)
```

### 5.4 상태

| 상태 | 의미 |
|---|---|
| `FINALIZED` | 기대치와 actual의 시점·기간·범위가 정상 정합 |
| `DEGRADED` | 표본 부족·일부 공급원 누락 등으로 제한적 사용 |
| `BLOCKED` | 미래정보·기간 충돌·핵심 actual/consensus 부재 |
| `NO_CONSENSUS` | 최소 참여자 수 미달 |
| `NOT_APPLICABLE` | 해당 종목/업종/지표에 적용하지 않음 |

---

## 6. 핵심 시간 모델

이 엔진의 가장 중요한 설계는 `발표 시점 이전의 기대치`를 고정하는 것이다.

### 6.1 시간 필드

```text
estimate.published_at
estimate.known_at
estimate.recorded_at
estimate.superseded_at
actual.published_at
actual.known_at
event.actual_release_at
run.evaluation_time
```

### 6.2 Pre-Event Cutoff

실적 surprise를 계산할 때 사용할 추정치는 기본적으로 다음 조건을 만족해야 한다.

```text
estimate.known_at <= event.actual_release_at - cutoff_buffer
```

초기 PAPER 정책 예:

```text
cutoff_buffer = 5 minutes
```

데이터 공급원의 timestamp granularity가 일 단위라면 더 보수적인 정책을 사용한다.

```text
일 단위 추정치 공급원
→ 실적 발표일 당일 업데이트를 pre-event consensus에 포함하지 않음
```

### 6.3 평가시점 조건

어떤 시점 `T`에서 사용할 정보는:

```text
known_at <= T
```

를 반드시 만족해야 한다.

### 6.4 발표 이후 데이터 소급 금지

예:

```text
09:00 consensus = 영업이익 1조원
15:30 기업 실적발표 = 1.2조원
16:00 vendor가 consensus를 1.18조원으로 수정

Surprise 계산:
1.2조 / 1.0조 - 1 = +20%

금지:
1.2조 / 1.18조 - 1 = +1.69%
```

16:00 수정값은 향후 분기 추정치 revision 분석에는 사용할 수 있지만, 방금 발표된 분기의 pre-event consensus를 다시 쓰는 데 사용할 수 없다.

---

## 7. 기간 매핑

### 7.1 Fiscal Period Key

모든 estimate와 actual은 다음 canonical key로 결합한다.

```text
security_id
metric_code
period_start
period_end
fiscal_year
fiscal_quarter
scope
currency
```

### 7.2 금지 사례

```text
2026 Q2 actual
vs
2026 FY estimate
→ 비교 금지

연결 영업이익 actual
vs
별도 영업이익 consensus
→ 비교 금지

KRW actual
vs
USD estimate
→ 통화 정규화 정책 없으면 비교 금지
```

### 7.3 회계연도 변경

12월 결산법인이 아닌 기업이나 회계연도 변경 기업은 calendar year를 fiscal year로 추정하지 않는다.

Instrument Master / Fundamental Engine의 회계기간 메타데이터를 사용한다.

---

## 8. Consensus 생성

### 8.1 기본 Consensus

초기 정책은 `median`을 기본값으로 한다.

```text
consensus = median(latest estimate per analyst before cutoff)
```

평균보다 median을 기본값으로 선택하는 이유:

- 극단값에 덜 민감
- 소수의 비정상 추정치 영향 제한
- outlier 제거 규칙 의존성 감소

### 8.2 Analyst별 최신 추정치 선택

같은 애널리스트가 여러 번 수정한 경우 cutoff 이전의 최신 revision 하나만 사용한다.

```python
latest = max(
    estimates,
    key=lambda x: (x.known_at, x.revision, x.estimate_id)
)
```

### 8.3 최소 참여자 수

초기 정책 예:

| 항목 | 기준 |
|---|---:|
| 최소 analyst/broker 수 | 3 |
| 권장 analyst/broker 수 | 5 |
| 강한 신뢰도 | 10 이상 |

3명 미만이면:

```text
NO_CONSENSUS
```

로 처리한다.

단일 추정치는 `single_estimate`로 보존할 수 있으나 consensus feature로 사용하지 않는다.

### 8.4 중복 추정치 제거

동일 리서치가 여러 vendor를 통해 중복 수신될 수 있으므로:

```text
analyst_id + broker_id + metric + period + published_at + value
```

기반 fingerprint를 사용한다.

동일 fingerprint는 consensus 표본 수에서 1건으로 계산한다.

---

## 9. Surprise 계산

### 9.1 Absolute Surprise

```text
surprise_absolute = actual - consensus
```

### 9.2 Percentage Surprise

일반적인 경우:

```text
surprise_pct
= (actual - consensus) / abs(consensus)
```

단, 분모가 0에 가깝거나 이익의 부호가 달라질 때는 일반 백분율 점수를 제한한다.

### 9.3 분모 보호

```text
if abs(consensus) < epsilon:
    surprise_pct = None
    reason = CONSENSUS_NEAR_ZERO
```

`epsilon`은 metric·단위별 정책으로 관리한다.

### 9.4 이익 부호 전환

예:

```text
Consensus = -100억원
Actual = +50억원
```

단순 surprise_pct는 경제적 의미를 왜곡할 수 있으므로:

```text
SIGN_FLIP_POSITIVE
```

을 별도 feature로 생성한다.

반대의 경우:

```text
Consensus = +100억원
Actual = -50억원
→ SIGN_FLIP_NEGATIVE
```

### 9.5 Standardized Surprise

과거 surprise의 종목별 또는 업종별 분포가 충분할 경우:

```text
standardized_surprise
= (current_surprise - historical_median)
  / (1.4826 × historical_MAD)
```

history가 부족하면 cross-sectional robust scaling을 보조 방식으로 사용한다.

절대금액 surprise를 종목 간 직접 비교하지 않는다.

---

## 10. EPS Surprise 특수 처리

EPS는 다음 사항을 반드시 일치시켜야 한다.

```text
basic vs diluted
reported vs adjusted
common-share attributable income
weighted average shares
corporate action adjustment basis
```

Vendor가 `adjusted EPS`를 제공하더라도 DART reported EPS와 동일한 metric으로 취급하지 않는다.

```text
EPS_REPORTED
EPS_ADJUSTED_VENDOR
```

를 별도 metric으로 관리한다.

액면분할·무상증자 등으로 과거 EPS가 조정되는 경우 Corporate Actions Engine의 revision 및 기준일을 추적한다.

---

## 11. Revision Momentum

Surprise는 발표 순간의 정보이고, revision은 발표 전후 기대치 방향을 나타낸다.

### 11.1 Revision Horizon

초기 정책:

```text
7 calendar days
30 calendar days
60 calendar days
90 calendar days
```

### 11.2 Consensus Revision Rate

```text
revision_rate_30d
= consensus_now / consensus_30d_ago - 1
```

분모가 0 또는 부호 전환이면 일반 비율 대신 상태 feature를 사용한다.

### 11.3 Absolute Revision

```text
revision_absolute_30d
= consensus_now - consensus_30d_ago
```

### 11.4 Revision Breadth

기간 내 최신 추정치를 기준으로:

```text
up = 상향한 analyst 수
down = 하향한 analyst 수
unchanged = 변경 없음

revision_breadth
= (up - down) / (up + down + unchanged)
```

범위:

```text
-1 <= revision_breadth <= +1
```

### 11.5 Revision Intensity

```text
revision_intensity
= (up + down) / active_analyst_count
```

breadth가 +1이어도 수정한 사람이 1명뿐인 경우 과대평가하지 않기 위해 intensity를 함께 사용한다.

### 11.6 New Coverage vs Revision

신규 애널리스트의 첫 추정치는 기존 추정치의 상향/하향 revision으로 계산하지 않는다.

```text
NEW_COVERAGE
```

로 분리한다.

---

## 12. Dispersion & Uncertainty

시장 기대치의 불확실성을 측정한다.

### 12.1 Robust Dispersion

```text
dispersion_mad
= 1.4826 × MAD(analyst estimates)
```

### 12.2 Relative Dispersion

```text
relative_dispersion
= dispersion_mad / abs(consensus)
```

분모가 작으면 계산하지 않는다.

### 12.3 Interquartile Range

```text
IQR = Q75 - Q25
```

### 12.4 의미

```text
높은 surprise + 낮은 dispersion
→ 비교적 명확한 기대치 상회

높은 surprise + 매우 높은 dispersion
→ 시장 기대 자체가 불확실했음
```

Signal Engine은 surprise 단독이 아니라 dispersion과 함께 사용할 수 있다.

---

## 13. Guidance 처리

기업이 공식 가이던스를 제공하는 경우 별도 ledger로 관리한다.

### 13.1 Guidance 필드

```text
guidance_metric
guidance_period
guidance_low
guidance_mid
guidance_high
currency
scope
published_at
known_at
```

### 13.2 Guidance Surprise

```text
guidance_mid_vs_consensus
= guidance_mid / consensus_next_period - 1
```

단, guidance가 범위일 경우 midpoint만 사용한 계산은 반드시 다음 메타데이터를 기록한다.

```text
MIDPOINT_DERIVED
```

### 13.3 Guidance Revision

기존 기업 가이던스 대비:

```text
RAISED_GUIDANCE
MAINTAINED_GUIDANCE
LOWERED_GUIDANCE
WITHDRAWN_GUIDANCE
```

를 구분한다.

---

## 14. Preliminary vs Final Actual

한국 기업은 잠정실적 후 정식 분기보고서를 제출할 수 있다.

### 14.1 원칙

```text
잠정실적 공개 시점
→ 당시 surprise 계산 가능

후속 확정공시
→ 새로운 actual revision 생성
→ 기존 surprise Snapshot은 수정하지 않음
```

### 14.2 Replay

후속 정정 공시를 기준으로 경제적 분석을 다시 하고 싶다면:

```text
run_mode = REPLAY_WITH_LATEST_ACTUAL
```

을 명시하며 원래 의사결정 당시 결과와 분리한다.

---

## 15. 공급원 우선순위와 충돌

### 15.1 Actual 우선순위

```text
DART / KRX 공식 공시
> 기업 공식 IR
> 허가된 데이터 공급업체
```

### 15.2 Estimate 우선순위

추정치는 공식값이 아니므로 단순 provider 우선순위만으로 정답을 결정하지 않는다.

각 vendor는 별도 observation으로 보존한다.

### 15.3 Provider Consensus와 ADE Consensus

Vendor가 이미 consensus를 제공하는 경우:

```text
VENDOR_CONSENSUS
```

ADE가 개별 estimate에서 자체 집계한 경우:

```text
ADE_REBUILT_CONSENSUS
```

로 구분한다.

둘이 크게 다르면:

```text
CONFLICTED_CONSENSUS
```

을 기록한다.

### 15.4 자동 평균 금지

두 vendor consensus가 충돌한다고 둘을 평균내어 새로운 consensus를 만들지 않는다.

---

## 16. Staleness

오래된 추정치는 현재 기대치를 잘 반영하지 못할 수 있다.

### 16.1 Analyst Estimate Age

```text
estimate_age_days
= cutoff_date - estimate_known_date
```

### 16.2 초기 정책 예

| 기간 | 상태 |
|---|---|
| 0~30일 | FRESH |
| 31~60일 | AGING |
| 61~90일 | STALE_WARNING |
| 90일 초과 | STALE_EXCLUDE |

정확한 기준은 정책 Snapshot으로 관리한다.

### 16.3 Weighted Consensus 금지 기본값

v1에서는 stale한 추정치에 임의 가중치를 주는 방식보다:

```text
정책 기준 초과 → 제외
```

를 기본으로 한다.

가중 consensus는 향후 별도 정책 버전에서 도입한다.

---

## 17. 데이터베이스 설계

### 17.1 `estimate_sources`

```sql
CREATE TABLE estimate_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    license_class TEXT,
    timezone TEXT,
    created_at TEXT NOT NULL
);
```

### 17.2 `analyst_entities`

실명 저장이 라이선스·개인정보 측면에서 불필요한 경우 pseudonymous ID를 사용한다.

```sql
CREATE TABLE analyst_entities (
    analyst_id TEXT PRIMARY KEY,
    broker_id TEXT,
    external_hash TEXT,
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT NOT NULL
);
```

### 17.3 `earnings_estimate_observations`

```sql
CREATE TABLE earnings_estimate_observations (
    estimate_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    analyst_id TEXT,
    broker_id TEXT,
    security_id TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    scope TEXT NOT NULL,
    currency TEXT,
    unit TEXT,
    estimate_value TEXT NOT NULL,
    published_at TEXT,
    known_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    supersedes_estimate_id TEXT,
    fingerprint TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
```

### 17.4 `earnings_events`

```sql
CREATE TABLE earnings_events (
    event_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    fiscal_period_end TEXT NOT NULL,
    scheduled_at TEXT,
    actual_release_at TEXT,
    known_at TEXT NOT NULL,
    source_id TEXT NOT NULL,
    event_hash TEXT NOT NULL
);
```

### 17.5 `consensus_snapshots`

```sql
CREATE TABLE consensus_snapshots (
    consensus_snapshot_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    event_id TEXT,
    metric_code TEXT NOT NULL,
    period_end TEXT NOT NULL,
    cutoff_at TEXT NOT NULL,
    consensus_method TEXT NOT NULL,
    consensus_value TEXT,
    analyst_count INTEGER NOT NULL,
    included_count INTEGER NOT NULL,
    excluded_stale_count INTEGER NOT NULL,
    dispersion_value TEXT,
    status TEXT NOT NULL,
    policy_snapshot_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 17.6 `consensus_snapshot_members`

```sql
CREATE TABLE consensus_snapshot_members (
    consensus_snapshot_id TEXT NOT NULL,
    estimate_id TEXT NOT NULL,
    analyst_id TEXT,
    estimate_value TEXT NOT NULL,
    estimate_age_days INTEGER,
    inclusion_status TEXT NOT NULL,
    exclusion_reason TEXT,
    member_hash TEXT NOT NULL,
    PRIMARY KEY (consensus_snapshot_id, estimate_id)
);
```

### 17.7 `earnings_surprise_results`

```sql
CREATE TABLE earnings_surprise_results (
    surprise_result_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    consensus_snapshot_id TEXT NOT NULL,
    fundamental_snapshot_id TEXT NOT NULL,
    consensus_value TEXT,
    actual_value TEXT,
    surprise_absolute TEXT,
    surprise_pct TEXT,
    standardized_surprise TEXT,
    status TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 17.8 `estimate_revision_features`

```sql
CREATE TABLE estimate_revision_features (
    revision_feature_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    period_end TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    consensus_start TEXT,
    consensus_end TEXT,
    revision_absolute TEXT,
    revision_rate TEXT,
    up_count INTEGER,
    down_count INTEGER,
    unchanged_count INTEGER,
    new_coverage_count INTEGER,
    revision_breadth TEXT,
    revision_intensity TEXT,
    status TEXT NOT NULL,
    feature_hash TEXT NOT NULL
);
```

### 17.9 `expectation_reason_events`

```sql
CREATE TABLE expectation_reason_events (
    reason_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT,
    metric_code TEXT,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    evidence_json TEXT,
    created_at TEXT NOT NULL
);
```

### 17.10 `expectation_snapshot_manifests`

```sql
CREATE TABLE expectation_snapshot_manifests (
    expectations_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    policy_snapshot_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## 18. DB 제약조건

논리적 제약:

```text
known_at <= recorded_at 허용 여부는 source latency 정책에 따름
actual_release_at 이후의 estimate는 pre-event snapshot member 금지
동일 analyst + metric + period + cutoff에는 최신 revision 1개만 포함
동일 fingerprint 중복 count 금지
Decimal 값을 FLOAT로 저장 금지
기존 observation UPDATE 금지
revision은 append-only
```

권장 index:

```sql
CREATE INDEX idx_estimate_lookup
ON earnings_estimate_observations (
    security_id,
    metric_code,
    period_end,
    known_at
);

CREATE INDEX idx_event_lookup
ON earnings_events (
    security_id,
    fiscal_period_end,
    actual_release_at
);
```

---

## 19. 정책 Snapshot

예:

```python
EstimatePolicy(
    version="v1",
    consensus_method="MEDIAN",
    min_contributors=3,
    recommended_contributors=5,
    strong_contributors=10,
    stale_warning_days=60,
    stale_exclude_days=90,
    pre_event_cutoff_buffer_minutes=5,
    dedupe_enabled=True,
    use_adjusted_eps=False,
    allow_vendor_consensus=True,
    allow_rebuilt_consensus=True,
    denominator_epsilon_policy="METRIC_SPECIFIC",
)
```

정책은 코드 상수가 아니라 다음 필드를 가진 immutable snapshot으로 관리한다.

```text
policy_snapshot_id
version
valid_from
valid_to
known_at
approved_by
payload_json
payload_hash
```

---

## 20. 핵심 알고리즘 1 — Estimate Revision 선택

```python
def select_latest_estimate_per_analyst(
    observations,
    cutoff_at,
    stale_exclude_days,
):
    eligible = []

    for row in observations:
        if row.known_at > cutoff_at:
            continue

        age_days = (cutoff_at.date() - row.known_at.date()).days
        if age_days > stale_exclude_days:
            continue

        eligible.append(row)

    grouped = group_by_analyst_or_broker(eligible)

    selected = []
    for _, rows in grouped.items():
        latest = max(
            rows,
            key=lambda x: (x.known_at, x.revision, x.estimate_id),
        )
        selected.append(latest)

    return deduplicate_by_fingerprint(selected)
```

---

## 21. 핵심 알고리즘 2 — Consensus Builder

```python
from decimal import Decimal
from statistics import median


def build_consensus(selected, policy):
    if len(selected) < policy.min_contributors:
        return ConsensusResult(
            status="NO_CONSENSUS",
            value=None,
            count=len(selected),
        )

    values = [Decimal(x.estimate_value) for x in selected]

    if policy.consensus_method == "MEDIAN":
        value = Decimal(str(median(values)))
    elif policy.consensus_method == "MEAN":
        value = sum(values) / Decimal(len(values))
    else:
        raise UnsupportedConsensusMethod()

    dispersion = robust_mad(values)

    return ConsensusResult(
        status="FINALIZED",
        value=value,
        count=len(values),
        dispersion=dispersion,
    )
```

---

## 22. 핵심 알고리즘 3 — Surprise

```python
def calculate_surprise(actual, consensus, epsilon):
    absolute = actual - consensus

    if abs(consensus) <= epsilon:
        return {
            "absolute": absolute,
            "pct": None,
            "sign_flip": classify_sign_flip(actual, consensus),
            "reason": "CONSENSUS_NEAR_ZERO",
        }

    pct = absolute / abs(consensus)

    return {
        "absolute": absolute,
        "pct": pct,
        "sign_flip": classify_sign_flip(actual, consensus),
        "reason": None,
    }
```

---

## 23. 핵심 알고리즘 4 — Revision Breadth

```python
def revision_breadth(changes):
    up = sum(1 for x in changes if x > 0)
    down = sum(1 for x in changes if x < 0)
    unchanged = sum(1 for x in changes if x == 0)

    total = up + down + unchanged
    if total == 0:
        return None

    breadth = (up - down) / total
    intensity = (up + down) / total

    return breadth, intensity
```

신규 커버리지는 `changes`에 포함하지 않는다.

---

## 24. 핵심 알고리즘 5 — Point-in-Time Revision Momentum

평가시점 `T`에서 30일 revision을 계산하려면:

```text
Consensus(T)
vs
Consensus(T - 30일)
```

두 consensus 모두 각각 해당 시점까지 알려진 정보만 사용해 재구축해야 한다.

금지:

```text
현재 analyst 집합을 과거 T-30일 consensus에 그대로 적용
```

당시 활성 커버리지와 당시 공개된 revision만 사용한다.

---

## 25. 핵심 알고리즘 6 — Event Freeze

```python
def freeze_pre_event_consensus(event, estimates, policy):
    cutoff_at = event.actual_release_at - policy.cutoff_buffer

    eligible = [
        e for e in estimates
        if e.known_at <= cutoff_at
    ]

    selected = select_latest_estimate_per_analyst(
        eligible,
        cutoff_at,
        policy.stale_exclude_days,
    )

    return build_consensus(selected, policy)
```

`actual_release_at` 자체가 불확실하면:

```text
EVENT_RELEASE_TIME_UNCERTAIN
```

으로 처리하며, 당일 추정치를 보수적으로 제외한다.

---

## 26. 품질 Gate

### 26.1 FINALIZED 조건

```text
instrument identity resolved
period mapping exact
scope exact
currency/unit normalized
actual is point-in-time valid
consensus contributors >= minimum
no post-event estimates included
no critical provider conflict
policy snapshot available
```

### 26.2 DEGRADED 조건 예

```text
contributors = 3~4
stale_warning 비중 높음
secondary metric 일부 누락
dispersion history 부족
```

### 26.3 BLOCKED 조건 예

```text
future information detected
period mismatch
scope mismatch
actual conflict
release time unknown + same-day estimates contamination risk
consensus members below minimum
```

---

## 27. Reason Code

```text
NO_CONSENSUS
INSUFFICIENT_CONTRIBUTORS
STALE_ESTIMATE
STALE_ESTIMATE_EXCLUDED
DUPLICATE_ESTIMATE
NEW_COVERAGE
FUTURE_ESTIMATE_INFORMATION
POST_EVENT_ESTIMATE_EXCLUDED
EVENT_RELEASE_TIME_UNKNOWN
EVENT_RELEASE_TIME_UNCERTAIN
PERIOD_MISMATCH
FISCAL_YEAR_MISMATCH
SCOPE_MISMATCH
CURRENCY_MISMATCH
UNIT_MISMATCH
METRIC_DEFINITION_MISMATCH
ACTUAL_NOT_FINALIZED
ACTUAL_CONFLICTED
CONSENSUS_CONFLICTED
CONSENSUS_NEAR_ZERO
SIGN_FLIP_POSITIVE
SIGN_FLIP_NEGATIVE
DISPERSION_NOT_ENOUGH_MEMBERS
REVISION_HISTORY_INSUFFICIENT
GUIDANCE_NOT_AVAILABLE
GUIDANCE_WITHDRAWN
RESTATEMENT_AFTER_DECISION
FUTURE_INFORMATION_GUARD
SNAPSHOT_HASH_MISMATCH
```

---

## 28. Feature 출력

Feature Engine에 전달할 수 있는 예:

```text
earnings_surprise_revenue_pct
earnings_surprise_operating_income_pct
earnings_surprise_net_income_pct
earnings_surprise_eps_pct
standardized_surprise_operating_income
standardized_surprise_eps
revision_7d
revision_30d
revision_60d
revision_breadth_30d
revision_intensity_30d
estimate_dispersion
relative_dispersion
analyst_count
fresh_analyst_count
guidance_vs_consensus
sign_flip_positive
sign_flip_negative
```

Feature마다 다음 메타데이터를 함께 전달한다.

```text
feature_version
known_at
as_of
period_end
consensus_snapshot_id
fundamental_snapshot_id
policy_snapshot_id
evidence_hash
quality_status
```

---

## 29. Signal Engine 연계 원칙

이 엔진은 다음과 같은 점수를 직접 BUY로 변환하지 않는다.

예:

```text
강한 positive surprise
+ 30일 revision 상향
+ 낮은 dispersion
```

은 긍정적인 Feature Bundle일 수 있으나,

```text
가격 gap 과열
극단적 시장 변동성
유동성 부족
포트폴리오 집중도 제한
```

등으로 최종 매수는 차단될 수 있다.

즉:

```text
Expectations Engine
→ evidence-producing analytical layer

Signal / Risk / Decision
→ action-producing layer
```

로 책임을 분리한다.

---

## 30. Risk Engine 연계

Risk에 전달할 수 있는 경고:

```text
HIGH_ESTIMATE_DISPERSION
LOW_ANALYST_COVERAGE
POST_EARNINGS_GAP_RISK
NEGATIVE_SIGN_FLIP
GUIDANCE_WITHDRAWAL
CONSENSUS_DATA_CONFLICT
```

특히 analyst count가 적고 dispersion이 높은 종목은 surprise 절대값이 크더라도 신뢰도를 낮춘다.

---

## 31. Explainability 연계

예시 evidence:

```text
삼성전자 2026 Q2 영업이익
Pre-event consensus: 10.2조원
Contributors: 18
Actual: 11.0조원
Surprise: +7.84%
30d consensus revision: +5.1%
Revision breadth: +0.61
Dispersion: LOW
Consensus cutoff: 2026-xx-xx 15:25 KST
```

Explainability Engine은 다음을 반드시 보여줄 수 있어야 한다.

```text
어떤 추정치가 포함됐는가
어떤 추정치가 stale로 제외됐는가
cutoff는 언제였는가
actual은 어느 공시 revision인가
산식 버전은 무엇인가
```

---

## 32. Backtest Leakage Guard

가장 중요한 검증 대상이다.

### 금지 1

```text
현재 consensus history API가 반환하는 정리된 과거값을
그대로 과거 시점 consensus로 간주
```

Vendor가 과거 데이터를 사후 수정했을 가능성이 있기 때문이다.

### 금지 2

```text
실적 발표 후 consensus revision을
발표 직전 기대치 계산에 포함
```

### 금지 3

```text
후속 정정 actual을
원래 발표시점 surprise에 자동 소급
```

### 필요 저장

```text
raw estimate observation
known_at
revision
pre-event frozen snapshot
actual revision
policy hash
```

---

## 33. Hashing

Canonical snapshot payload 예:

```json
{
  "security_id": "...",
  "metric_code": "OPERATING_INCOME",
  "period_end": "2026-06-30",
  "cutoff_at": "...",
  "consensus_method": "MEDIAN",
  "members": [
    ["estimate_id_1", "value_1"],
    ["estimate_id_2", "value_2"]
  ],
  "policy_snapshot_id": "..."
}
```

정렬 규칙:

```text
member는 estimate_id 기준 정렬
Decimal은 canonical string
시간은 UTC offset-aware ISO-8601
null과 missing을 구분
```

그 후 SHA-256으로 hash를 생성한다.

---

## 34. Atomic Persistence

실행 흐름:

```text
BEGIN TRANSACTION
  run 생성
  consensus snapshot 저장
  members 저장
  surprise results 저장
  revision features 저장
  reason events 저장
  manifest 저장
COMMIT
```

중간 실패 시:

```text
ROLLBACK
final manifest 없음
```

부분적으로 저장된 `FINALIZED` 상태를 허용하지 않는다.

---

## 35. 코드 구조

```text
expectations/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── adapters/
│   ├── vendor_consensus.py
│   ├── broker_estimates.py
│   ├── corporate_guidance.py
│   └── fundamental_actuals.py
├── normalization.py
├── fiscal_periods.py
├── identity.py
├── deduplication.py
├── temporal.py
├── staleness.py
├── consensus.py
├── dispersion.py
├── surprise.py
├── revisions.py
├── breadth.py
├── guidance.py
├── event_freeze.py
├── quality.py
├── reason_codes.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

---

## 36. 핵심 Python 모델

```python
@dataclass(frozen=True)
class EstimateObservation:
    estimate_id: str
    source_id: str
    analyst_id: str | None
    broker_id: str | None
    security_id: str
    metric_code: str
    period_end: date
    scope: str
    currency: str | None
    unit: str | None
    value: Decimal
    known_at: datetime
    revision: int
    fingerprint: str


@dataclass(frozen=True)
class ConsensusSnapshot:
    consensus_snapshot_id: str
    security_id: str
    metric_code: str
    period_end: date
    cutoff_at: datetime
    value: Decimal | None
    method: str
    contributor_count: int
    dispersion: Decimal | None
    status: str
    snapshot_hash: str
```

---

## 37. Engine Orchestration

```python
class EarningsExpectationsEngine:
    def run(self, request: ExpectationRunRequest) -> ExpectationRunResult:
        policy = self.policy_repo.get_snapshot(
            request.estimate_policy_snapshot_id
        )

        universe = self.universe_repo.load(
            request.universe_snapshot_id
        )

        results = []

        for security_id in universe.security_ids:
            events = self.event_repo.get_relevant_events(
                security_id=security_id,
                evaluation_time=request.evaluation_time,
            )

            result = self.evaluate_security(
                security_id,
                events,
                request,
                policy,
            )
            results.append(result)

        return self.persist_atomic(request, policy, results)
```

---

## 38. 단위 테스트 계획

### 38.1 Consensus

```text
3개 추정치 median 정상
4개 추정치 median 정상
1개 추정치 → NO_CONSENSUS
2개 추정치 → NO_CONSENSUS
중복 fingerprint 제거
동일 analyst 최신 revision만 선택
```

### 38.2 Time

```text
cutoff 이전 estimate 포함
cutoff 이후 estimate 제외
발표 후 estimate 제외
future known_at 제외
일 단위 timestamp 공급원 보수적 처리
```

### 38.3 Surprise

```text
positive surprise
negative surprise
consensus=0
consensus near zero
negative→positive sign flip
positive→negative sign flip
```

### 38.4 Revision

```text
전원 상향 → breadth +1
전원 하향 → breadth -1
절반 상향/절반 하향 → 0
변경 없음 포함
신규 coverage는 breadth에서 제외
```

### 38.5 Dispersion

```text
동일 추정치 → dispersion 0
outlier 포함 robust MAD
표본 부족 → NOT_ENOUGH_MEMBERS
```

---

## 39. 통합 테스트 시나리오

### A. 정상 실적 상회

```text
5명 analyst
pre-event consensus 영업이익 1조원
actual 1.1조원
→ FINALIZED
→ surprise +10%
```

### B. 발표 직후 consensus 수정

```text
15:30 actual 공개
15:35 vendor consensus 수정
→ 15:35 수정값 pre-event snapshot 사용 0건
```

### C. 표본 부족

```text
analyst 2명
→ NO_CONSENSUS
→ surprise feature 생성 금지
```

### D. stale estimate 다수

```text
5명 중 3명이 120일 전 추정
→ stale 3명 제외
→ 유효 2명
→ NO_CONSENSUS
```

### E. 적자 예상 → 흑자 actual

```text
consensus -100억원
actual +50억원
→ SIGN_FLIP_POSITIVE
→ 일반 surprise %의 해석 제한
```

### F. 연결·별도 불일치

```text
연결 actual
별도 consensus
→ SCOPE_MISMATCH
→ BLOCKED
```

### G. 분기 불일치

```text
Q2 actual
FY consensus
→ PERIOD_MISMATCH
```

### H. 잠정실적 후 확정실적

```text
잠정 actual revision 1
정식 공시 revision 2
→ 기존 surprise snapshot 유지
→ replay에서 새 결과 생성 가능
```

### I. 추정치 중복 공급

```text
동일 analyst report가 vendor A/B에서 수신
→ fingerprint 중복 제거
→ contributor count 1명
```

### J. 30일 revision momentum

```text
30일 전 consensus 100
현재 110
→ +10%
```

### K. 현재정보 과거 백테스트 유입

```text
평가시점 이후 known_at 추정치
→ FUTURE_INFORMATION_GUARD
→ 사용 0건
```

### L. 동일 입력 재실행

```text
동일 raw observations
동일 policy
동일 evaluation_time
→ 동일 consensus hash
→ 동일 surprise result hash
```

### M. DB 저장 중 장애

```text
members 저장 후 오류
→ 전체 rollback
→ final manifest 없음
```

---

## 40. Property-Based 테스트

검증할 불변식:

```text
surprise_absolute == actual - consensus
revision_breadth ∈ [-1, +1]
revision_intensity ∈ [0, 1]
contributor_count >= included_count
post-event estimate count in pre-event snapshot == 0
future known_at usage count == 0
duplicate fingerprint included count <= 1
동일 canonical payload → 동일 hash
```

랜덤 Decimal 값과 timestamp permutation으로 테스트한다.

---

## 41. Determinism 테스트

동일 입력을 다음 순서로 섞어서 넣어도 결과가 같아야 한다.

```text
estimate ingestion order randomization
member order randomization
provider order randomization
DB query order randomization
```

최종 hash는 동일해야 한다.

---

## 42. 장애 테스트

```text
Vendor API timeout
부분 응답
동일 estimate 중복 수신
timezone 누락
잘못된 fiscal period
잘못된 currency
actual release timestamp 누락
DB deadlock
process restart
```

핵심 원칙:

```text
데이터가 불확실하면 추정하지 않는다.
BLOCKED 또는 DEGRADED로 명시한다.
```

---

## 43. 성능 목표

초기 PAPER 환경 기준 목표:

```text
Universe 3,000 종목
Active estimate observations 1,000,000 이하
일일 incremental processing 우선
```

권장 최적화:

```text
security_id + metric + period + known_at index
incremental revision calculation
immutable snapshot cache
precomputed latest-per-analyst pointer
```

정확성과 재현성이 성능보다 우선한다.

---

## 44. 관측성

수집할 metric:

```text
estimate_rows_ingested
estimate_rows_deduplicated
future_rows_blocked
post_event_rows_blocked
stale_rows_excluded
consensus_built_count
no_consensus_count
surprise_finalized_count
period_mismatch_count
scope_mismatch_count
average_contributor_count
median_dispersion
snapshot_hash_conflict_count
```

중대한 alert:

```text
future_rows_blocked > 0
post_event_rows_in_frozen_snapshot > 0
snapshot_hash_conflict_count > 0
```

---

## 45. 보안 및 라이선스

애널리스트 추정치는 데이터 라이선스 제약이 클 수 있다.

따라서:

```text
source_license_class 저장
원문 report 저장 여부 정책화
개인 analyst 실명 최소화
외부 출력에 raw licensed estimates 노출 제한
hash / aggregate feature 중심 저장 가능
```

라이선스가 없는 데이터를 웹에서 임의 스크래핑하여 production feature에 포함하지 않는다.

---

## 46. v1 제외 범위

v1에서는 다음을 구현하지 않는다.

```text
NLP 기반 리서치 보고서 톤 분석
목표주가 consensus
추천등급 Buy/Hold/Sell consensus
options-implied earnings move
실적발표 conference call 음성 분석
LLM 기반 guidance extraction
```

이 기능들은 추후 별도 엔진으로 분리한다.

---

## 47. 다른 엔진과 연결

```text
Instrument Master
→ security_id / fiscal identity

Fundamental PIT Engine
→ actual earnings

Corporate Actions Engine
→ EPS / share basis 정합성

Market Data Finalization
→ post-earnings 가격 반응 계산의 확정 가격

Valuation & Cross-Sectional Factor Engine
→ 실적 및 기대치 변화의 가치 팩터 연계

Feature Engine
→ surprise / revision / dispersion feature 소비

Signal Engine
→ earnings momentum signal 구성

Risk Engine
→ high dispersion / low coverage / gap risk 반영

Explainability Engine
→ consensus cutoff 및 evidence 표시

Backtest
→ point-in-time estimate history 사용
```

---

## 48. 구현 우선순위

```text
1. EstimateObservation / ConsensusSnapshot 불변 모델
2. SQLite migration
3. 고정 fixture 기반 vendor adapter
4. fiscal period canonicalizer
5. point-in-time selector
6. analyst별 latest revision selector
7. fingerprint deduplication
8. stale estimate exclusion
9. median consensus builder
10. dispersion calculator
11. actual-vs-consensus surprise
12. sign-flip guard
13. 7/30/60/90일 revision momentum
14. revision breadth / intensity
15. event freeze
16. immutable snapshot hash
17. Feature Engine adapter
18. leakage regression suite
19. 50종목 × 8분기 fixture 통합 테스트
20. PAPER daily pipeline 연결
```

---

## 49. 완료 기준 (Definition of Done)

v1 설계 및 구현 완료 조건:

```text
[ ] 미래 estimate 사용 0건
[ ] post-event estimate의 pre-event snapshot 포함 0건
[ ] 동일 analyst 중복 count 0건
[ ] 기간·scope 혼합 0건
[ ] contributor minimum enforcement 100%
[ ] stale exclusion 정책 재현 가능
[ ] surprise Decimal 계산 재현 가능
[ ] revision breadth 범위 위반 0건
[ ] 정정 actual이 기존 snapshot을 덮어쓰는 경우 0건
[ ] 동일 입력 재실행 hash 100% 일치
[ ] DB partial finalization 0건
[ ] Feature/Explainability evidence 추적 가능
```

---

## 50. 최종 설계 요약

`Earnings Expectations, Surprise & Revision Engine v1`의 핵심은 다음 한 문장으로 정의한다.

> **ADE는 실제 실적 그 자체가 아니라, 그 시점에 시장이 알고 있던 기대치와 비교하여 surprise를 측정하고, 그 기대치가 어떻게 변해왔는지까지 Point-in-Time으로 보존한다.**

따라서 이 엔진은 다음 오류를 구조적으로 차단한다.

```text
사후 수정 consensus를 과거 surprise에 사용
현재 consensus를 과거 백테스트에 사용
실적 발표 후 추정치를 발표 전 기대치로 사용
적은 analyst 표본을 강한 consensus로 오인
연결/별도 및 분기/연간 추정치를 혼합
적자↔흑자 전환을 단순 퍼센트 surprise로 왜곡
```

이 엔진의 출력은 다음 단계의 Signal Generation이 `실적 모멘텀`, `기대치 상향`, `불확실성 감소`를 서로 분리하여 사용할 수 있게 한다.
