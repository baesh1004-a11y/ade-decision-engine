# 42. Signal Integration, Confidence & Candidate Ranking Engine v2

## 1. 문서 목적

이 문서는 AI Decision Engine(ADE)의 `Signal Integration, Confidence & Candidate Ranking Engine v2` 설계를 정의한다.

이 엔진은 38~41번 엔진에서 생성된 Point-in-Time Feature를 하나의 종목별 투자 신호로 통합하되, 단순 가중평균이 아니라 다음을 동시에 관리한다.

- Fundamental quality
- Valuation / cross-sectional factor
- Earnings expectations / surprise / revision
- Market behavior / momentum / trend / relative strength
- Market regime compatibility
- Data quality / freshness / coverage
- Signal agreement / conflict
- Confidence
- Candidate ranking
- Candidate eligibility for downstream Risk / Decision

이 엔진의 핵심 책임은 `좋아 보이는 종목`을 고르는 것이 아니라, 평가시점에 사용 가능한 증거만으로 다음 질문에 결정론적으로 답하는 것이다.

```text
이 종목의 투자 가설은 어떤 Feature family가 지지하는가?
각 Feature가 동일한 방향을 가리키는가?
좋은 점수가 단 하나의 극단값에 의해 만들어진 것은 아닌가?
데이터가 충분하고 최신인가?
현재 시장 국면에서 이 신호를 믿어도 되는가?
신호 강도와 신뢰도를 분리했는가?
동일 Universe에서 상대 순위는 몇 위인가?
Risk Engine으로 넘길 후보인가, 아니면 차단해야 하는가?
```

본 엔진은 최종 BUY/SELL, 포지션 비중, 주문 수량을 결정하지 않는다.

출력은 `Portfolio Risk & Exposure Engine`, `Decision & Position Sizing Engine`, `Explainability Engine`, `Paper Trading`, `Backtest`가 소비한다.

---

## 2. 기존 21번 Signal Engine과의 관계

ADE Roadmap에는 기존 `21. Signal Generation & Ranking Engine` 설계가 존재한다.

42번은 이를 삭제하지 않고 v2 통합 사양으로 확장한다.

```text
21 Signal Generation & Ranking Engine
        ↓
legacy contract / early design
        ↓
42 Signal Integration, Confidence & Candidate Ranking Engine v2
        ↓
38~41 Feature family를 실제로 통합하는 canonical signal contract
```

마이그레이션 원칙:

1. 21번의 기존 외부 인터페이스는 adapter로 유지한다.
2. 신규 Signal 계산은 42번 canonical model을 사용한다.
3. 기존 Candidate 구현은 `LegacyCandidateAdapter`를 통해 매핑한다.
4. 동일한 개념의 중복 점수 계산을 금지한다.
5. 42번 검증 완료 후 Roadmap에서 21번을 `legacy/superseded`로 표시한다.

---

## 3. 책임 범위

### 3.1 수행 책임

1. Feature family별 입력 계약 검증
2. Point-in-Time / known_at 검증
3. Feature direction 정렬
4. Feature scale 표준화
5. Feature family score 생성
6. 결측·비적용 Feature 처리
7. Signal family 간 동의/충돌 측정
8. Market Regime compatibility 계산
9. Data quality / freshness / coverage confidence 계산
10. Composite Alpha Score 생성
11. Confidence Score 생성
12. Signal Strength와 Confidence 분리
13. Cross-sectional ranking
14. Candidate eligibility 판정
15. 신규매수 후보 shortlist 생성
16. Reason Code 및 Evidence Manifest 생성
17. 동일 입력 재실행의 결정론성 보장

### 3.2 수행하지 않는 책임

- 원천 시장데이터 수집
- 종가 확정
- 재무제표 계산
- 기업가치 산식 계산
- Consensus 생성
- Momentum / trend 원천 Feature 계산
- Market Regime 자체 생성
- Portfolio concentration 계산
- 최종 매수/매도 승인
- Position sizing
- 주문 생성
- 체결 처리

---

## 4. 상위 아키텍처

```text
38 Fundamental PIT Financials
        ↓
39 Valuation & Cross-Sectional Factors
        ↓
40 Expectations / Surprise / Revisions
        ↓
41 Market Behavior / Momentum / Trend / RS
        ↓
Market Regime Snapshot
Universe Snapshot
Data Quality Snapshot
Policy Snapshot
        ↓
┌────────────────────────────────────────────┐
│ Signal Input Contract & Temporal Gate      │
└────────────────────────────────────────────┘
        ↓
Feature Alignment
   ├─ direction
   ├─ scale
   ├─ applicability
   ├─ freshness
   └─ confidence metadata
        ↓
Family Scoring
   ├─ Fundamental
   ├─ Value/Quality/Growth
   ├─ Expectations
   └─ Market Behavior
        ↓
Agreement / Conflict Engine
        ↓
Regime Compatibility Engine
        ↓
Data Confidence Engine
        ↓
Composite Alpha Engine
        ↓
Signal Confidence Engine
        ↓
Cross-Sectional Rank
        ↓
Candidate Eligibility Gate
        ↓
Immutable Signal Snapshot
        ↓
Risk → Decision → Paper Trading / Backtest
```

---

## 5. 핵심 설계 원칙

### 5.1 Alpha와 Confidence를 분리한다

높은 점수와 높은 신뢰도는 같은 개념이 아니다.

```text
Alpha Score
= 방향성과 기대수익 잠재력

Confidence Score
= 입력 품질, 데이터 커버리지, 신호 합의도, 안정성
```

예:

```text
종목 A
Alpha = 90
Confidence = 42
→ 강한 신호이나 불확실성 큼

종목 B
Alpha = 78
Confidence = 88
→ 신호는 조금 약하지만 훨씬 안정적
```

Risk/Decision은 두 값을 모두 받아야 한다.

### 5.2 단일 Feature가 전체 신호를 지배하지 못하게 한다

한 개 Feature의 극단값 때문에 Composite가 폭발하지 않도록 다음 장치를 둔다.

- family-level aggregation
- per-feature clipping
- family weight cap
- contribution cap
- evidence concentration check

### 5.3 결측을 0점으로 처리하지 않는다

결측은 중립이 아니다.

```text
MISSING
NOT_APPLICABLE
STALE
BLOCKED
CONFLICTED
```

을 분리한다.

### 5.4 미래정보 사용을 금지한다

모든 입력 Feature는 다음을 만족해야 한다.

```text
feature.known_at <= evaluation_time
feature.snapshot_time <= evaluation_time
policy.known_at <= evaluation_time
universe.known_at <= evaluation_time
regime.known_at <= evaluation_time
```

### 5.5 Ranking Universe를 고정한다

현재 Universe를 과거 신호 순위 계산에 사용하지 않는다.

Cross-sectional rank는 반드시 동일 실행의 `universe_snapshot_id` 안에서 계산한다.

---

## 6. 입력 계약

### 6.1 실행 요청

```python
SignalIntegrationRunRequest(
    run_id: str,
    evaluation_time: datetime,
    market_date: date,
    universe_snapshot_id: str,
    fundamental_snapshot_id: str | None,
    factor_snapshot_id: str | None,
    expectations_snapshot_id: str | None,
    market_behavior_snapshot_id: str | None,
    regime_snapshot_id: str,
    data_quality_snapshot_id: str,
    signal_policy_snapshot_id: str,
)
```

### 6.2 Feature 입력 공통 계약

```python
SignalFeatureObservation(
    security_id: str,
    feature_id: str,
    family: FeatureFamily,
    raw_value: Decimal | None,
    normalized_value: Decimal | None,
    direction: FeatureDirection,
    status: FeatureStatus,
    confidence: Decimal | None,
    valid_from: datetime,
    valid_to: datetime | None,
    known_at: datetime,
    source_snapshot_id: str,
    evidence_hash: str,
)
```

### 6.3 Feature Family

```text
FUNDAMENTAL
VALUATION
QUALITY
GROWTH
FINANCIAL_STRENGTH
CASHFLOW
EXPECTATIONS
SURPRISE
REVISION
MOMENTUM
RELATIVE_STRENGTH
TREND
VOLATILITY
VOLUME_CONFIRMATION
DRAWDOWN_RECOVERY
```

정책상 이들을 4개 상위 family로 묶는다.

```text
BUSINESS_QUALITY
VALUATION_FACTOR
EXPECTATIONS
MARKET_BEHAVIOR
```

---

## 7. 출력 계약

### 7.1 실행 결과

```python
SignalIntegrationRunResult(
    run_id: str,
    status: RunStatus,
    market_date: date,
    evaluation_time: datetime,
    universe_count: int,
    scored_count: int,
    degraded_count: int,
    blocked_count: int,
    candidate_count: int,
    signal_snapshot_id: str,
    snapshot_hash: str,
    reason_codes: tuple[str, ...],
)
```

### 7.2 종목별 Signal 결과

```python
SecuritySignalResult(
    security_id: str,
    alpha_score: Decimal | None,
    confidence_score: Decimal | None,
    risk_adjusted_signal_score: Decimal | None,
    family_scores: dict[str, Decimal | None],
    agreement_score: Decimal | None,
    regime_compatibility_score: Decimal | None,
    data_confidence_score: Decimal | None,
    cross_sectional_percentile: Decimal | None,
    rank: int | None,
    signal_state: SignalState,
    candidate_state: CandidateState,
    reason_codes: tuple[str, ...],
    evidence_hash: str,
)
```

### 7.3 Signal State

```text
STRONG_POSITIVE
POSITIVE
NEUTRAL
NEGATIVE
STRONG_NEGATIVE
DEGRADED
BLOCKED
NOT_EVALUATED
```

### 7.4 Candidate State

```text
ELIGIBLE
WATCH
REJECTED_SIGNAL
REJECTED_CONFIDENCE
REJECTED_REGIME
REJECTED_DATA
REJECTED_CONFLICT
```

`ELIGIBLE`은 매수 승인이 아니다.

이는 다음 Risk / Decision 계층으로 전달 가능한 후보라는 의미다.

---

## 8. Feature Registry

모든 Feature는 registry에 정의한다.

```python
FeatureDefinition(
    feature_id,
    family,
    preferred_direction,
    required,
    minimum_history,
    freshness_limit,
    normalization_method,
    clipping_policy,
    default_weight,
    applicable_industries,
    version,
)
```

예시:

```text
VAL_EARNINGS_YIELD
VAL_FCF_YIELD
QUAL_ROE
QUAL_CASH_CONVERSION
GROWTH_REVENUE_YOY
EXPECT_SURPRISE_OP
EXPECT_REVISION_30D
EXPECT_REVISION_BREADTH
MOM_RET_20D
MOM_RET_60D
MOM_12M_SKIP1M
RS_KOSPI_60D
TREND_ALIGNMENT
VOL_RV20
VOLUME_REL20
DRAWDOWN_252D
```

---

## 9. 방향 정렬

모든 normalized Feature는 최종적으로 `높을수록 긍정적`인 방향으로 정렬한다.

### 9.1 Positive direction

예:

```text
ROE 증가
FCF Yield 증가
Revision Breadth 증가
Relative Strength 증가
Trend Alignment 증가
```

### 9.2 Negative direction

예:

```text
Debt-to-Equity 증가
Accrual Ratio 증가
Realized Volatility 증가
Drawdown 심화
```

변환:

```text
aligned_score = -normalized_value
```

또는 percentile인 경우:

```text
aligned_percentile = 1 - percentile
```

### 9.3 Non-monotonic Feature

일부 Feature는 높을수록 무조건 좋지 않다.

예:

```text
매우 낮은 변동성 → 안정적
적당한 변동성 → 정상
극단적 변동성 → 위험
```

이 경우 piecewise 정책을 사용한다.

```text
feature_transform = PIECEWISE
```

산식 버전은 반드시 기록한다.

---

## 10. Family Score

상위 4개 Family를 기본으로 사용한다.

### 10.1 Business Quality

입력 예:

- ROE
- ROA
- 영업이익률
- FCF margin
- cash conversion
- leverage
- earnings stability

### 10.2 Valuation Factor

입력 예:

- Earnings Yield
- FCF Yield
- Book-to-Market
- EBIT/EV
- sector-relative valuation percentile

### 10.3 Expectations

입력 예:

- Earnings Surprise
- Revision 30D
- Revision 60D
- Revision Breadth
- Estimate Dispersion
- sign flip

### 10.4 Market Behavior

입력 예:

- 20D / 60D momentum
- 12M-1M momentum
- Relative Strength
- Trend alignment
- breakout
- volume confirmation
- drawdown / recovery
- volatility penalty

---

## 11. Family 내부 집계

기본은 weighted robust mean이다.

```text
family_score
= sum(valid aligned feature score × weight)
  / sum(valid weight)
```

단 다음 조건을 적용한다.

1. Feature contribution cap
2. 최소 required feature coverage
3. stale feature 제외
4. conflicted feature 제외
5. NOT_APPLICABLE은 분모에서 제외
6. missing required feature는 family degrade 또는 block

초기 정책 예:

```text
minimum_family_coverage = 0.60
minimum_required_coverage = 1.00
max_single_feature_contribution = 0.35
```

정확한 값은 Policy Snapshot으로 관리한다.

---

## 12. Composite Alpha Score

초기 PAPER 정책 예:

```text
Business Quality   25%
Valuation Factor   25%
Expectations       20%
Market Behavior    30%
```

계산:

```text
raw_alpha
= 0.25 × business_quality
+ 0.25 × valuation
+ 0.20 × expectations
+ 0.30 × market_behavior
```

가중치는 코드 상수가 아니라 `signal_policy_snapshot`에서 읽는다.

### 12.1 Family missing 처리

핵심 family가 누락되면 기본적으로 자동 재가중하지 않는다.

```text
Expectations 없음
→ 종목 자체가 analyst coverage가 없는 경우
→ 정책에 따라 NOT_APPLICABLE 가능

Market Behavior 없음
→ 신규상장 또는 데이터 부족
→ 후보 진입 차단 가능
```

재가중이 허용되는 경우에도 반드시:

```text
WEIGHTS_RENORMALIZED
```

Reason Code를 기록한다.

---

## 13. Signal Agreement Engine

Composite가 높더라도 family 간 방향이 충돌하면 신뢰도를 낮춘다.

예:

```text
Business Quality +0.8
Valuation       +0.7
Expectations    -0.8
Market Behavior -0.6
```

단순 평균은 중립 근처가 될 수 있으나 중요한 정보는 `강한 충돌`이다.

### 13.1 Agreement 계산

Family score를 -1~+1로 정규화했다고 가정한다.

```text
agreement
= 1 - weighted_dispersion(family_scores)
```

보조 지표:

```text
positive_family_count
negative_family_count
family_sign_consensus
family_score_dispersion
```

### 13.2 Conflict 상태

```text
LOW_CONFLICT
MODERATE_CONFLICT
HIGH_CONFLICT
```

예:

```text
Quality + Value positive
Expectations + Market Behavior negative
→ HIGH_CONFLICT 가능
```

HIGH_CONFLICT 종목은 Alpha가 높아도 Candidate를 WATCH로 낮출 수 있다.

---

## 14. Regime Compatibility

Signal은 Market Regime과 독립적으로 평가하되, 후보 진입 전에 compatibility를 계산한다.

예:

```text
RISK_ON + strong momentum
→ compatibility 높음

RISK_OFF + high beta breakout
→ compatibility 낮음

HIGH_VOLATILITY + falling knife rebound
→ compatibility 매우 낮음
```

Regime compatibility는 Alpha 자체를 역사적으로 덮어쓰지 않는다.

즉:

```text
Alpha Score = 종목 자체 투자 신호
Regime Compatibility = 현재 환경 적합성
```

분리 저장한다.

초기 상태:

```text
FAVORABLE
NEUTRAL
UNFAVORABLE
BLOCKING
UNKNOWN
```

---

## 15. Data Confidence Engine

Confidence는 다음 5개 축으로 계산한다.

```text
Coverage
Freshness
Source Quality
Feature Stability
Agreement
```

예시 정책:

```text
Coverage          25%
Freshness         20%
Source Quality    20%
Feature Stability 15%
Agreement         20%
```

### 15.1 Coverage

```text
coverage
= valid expected feature weight
  / total applicable feature weight
```

### 15.2 Freshness

Feature family별 freshness 기준을 다르게 둔다.

예:

```text
Market Behavior → 당일 FINALIZED 종가 필수
Fundamental     → 최신 공식 공시 기준
Expectations    → analyst estimate staleness 정책 적용
```

### 15.3 Source Quality

공식 원천과 파생 vendor 간 신뢰도 정책을 적용한다.

### 15.4 Stability

최근 실행 간 점수가 비정상적으로 급변하면 confidence를 낮춘다.

단 실제 실적발표나 기업행동처럼 설명 가능한 이벤트는 별도 처리한다.

---

## 16. Confidence Score

```text
confidence_score
= weighted_mean(
    coverage,
    freshness,
    source_quality,
    stability,
    agreement
  )
```

범위:

```text
0 ~ 100
```

초기 해석 예:

```text
85~100 HIGH
70~84  MEDIUM_HIGH
55~69  MEDIUM
40~54  LOW
0~39   VERY_LOW
```

임계값은 정책화한다.

---

## 17. Risk-Adjusted Signal Score

이 값은 Portfolio Risk Score가 아니다.

Signal 단계에서 데이터 및 신호 불확실성을 반영한 보조 점수다.

```text
risk_adjusted_signal_score
= alpha_score
× confidence_multiplier
× regime_multiplier
```

예시:

```text
confidence_multiplier = confidence / 100
```

Regime multiplier는 정책상 좁은 범위로 제한한다.

예:

```text
FAVORABLE   1.05
NEUTRAL     1.00
UNFAVORABLE 0.85
BLOCKING    candidate blocked
```

Regime가 강하다고 Alpha를 과도하게 증폭시키지 않는다.

---

## 18. Cross-Sectional Ranking

Ranking 대상은 동일 `universe_snapshot_id`의 유효 종목만 포함한다.

### 18.1 기본 순위키

```text
1. candidate eligibility
2. risk_adjusted_signal_score DESC
3. confidence_score DESC
4. alpha_score DESC
5. security_id ASC
```

마지막 security_id 정렬은 동일 점수에서 결정론적 결과를 보장하기 위한 tie-breaker다.

### 18.2 Percentile

```text
percentile
= rank position within eligible universe
```

전체 Universe가 아니라 업종·시장별 보조 percentile도 저장할 수 있다.

```text
market_percentile
sector_percentile
industry_percentile
```

---

## 19. Candidate Eligibility Gate

후보가 다음 Risk Engine으로 넘어가기 위한 Gate다.

초기 PAPER 예시:

```text
alpha_score >= 65
confidence_score >= 60
risk_adjusted_signal_score >= 55
regime != BLOCKING
conflict != HIGH_CONFLICT
market_behavior family available
no hard data-quality block
```

이 값들은 모두 정책 Snapshot으로 관리한다.

### 19.1 Candidate 상태 규칙

```text
hard data error
→ REJECTED_DATA

confidence below floor
→ REJECTED_CONFIDENCE

alpha below floor
→ REJECTED_SIGNAL

regime blocking
→ REJECTED_REGIME

high family conflict
→ REJECTED_CONFLICT

모두 통과
→ ELIGIBLE
```

---

## 20. 하루 신규매수 최대 1종목과의 관계

본 엔진은 하루 1종목 제한을 직접 집행하지 않는다.

42번은 후보를 정렬해서 전달한다.

```text
Candidate Rank 1
Candidate Rank 2
Candidate Rank 3
...
        ↓
Portfolio Risk
        ↓
Decision & Position Sizing
        ↓
하루 신규매수 최대 1종목 정책 적용
```

Rank 1이 Risk Gate에서 차단되면 Decision Engine은 정책상 Rank 2를 평가할 수 있다.

이를 위해 후보별 모든 Reason / Evidence를 보존한다.

---

## 21. NO_CANDIDATE와 NO_ACTION

둘을 구분한다.

```text
NO_CANDIDATE
= Signal 단계에서 유효 후보가 0개

NO_ACTION
= 최종 Decision 단계에서 실행할 행동이 없음
```

예:

```text
Signal 후보 3개
→ Risk에서 모두 차단
→ Decision = NO_ACTION

Signal 자체 후보 0개
→ Signal = NO_CANDIDATE
→ Decision = NO_ACTION
```

Explainability에서 두 경우를 명확히 분리해야 한다.

---

## 22. 데이터베이스 설계

### 22.1 signal_policies

```sql
CREATE TABLE signal_policies (
    policy_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    known_at TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 22.2 signal_runs

```sql
CREATE TABLE signal_runs (
    run_id TEXT PRIMARY KEY,
    market_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    universe_snapshot_id TEXT NOT NULL,
    signal_policy_snapshot_id TEXT NOT NULL,
    regime_snapshot_id TEXT NOT NULL,
    status TEXT NOT NULL,
    universe_count INTEGER NOT NULL,
    scored_count INTEGER NOT NULL,
    candidate_count INTEGER NOT NULL,
    snapshot_hash TEXT,
    created_at TEXT NOT NULL
);
```

### 22.3 signal_feature_inputs

```sql
CREATE TABLE signal_feature_inputs (
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    family TEXT NOT NULL,
    aligned_value TEXT,
    status TEXT NOT NULL,
    known_at TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, security_id, feature_id)
);
```

### 22.4 signal_family_scores

```sql
CREATE TABLE signal_family_scores (
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    family TEXT NOT NULL,
    family_score TEXT,
    coverage TEXT,
    confidence TEXT,
    status TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, security_id, family)
);
```

### 22.5 signal_security_scores

```sql
CREATE TABLE signal_security_scores (
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    alpha_score TEXT,
    confidence_score TEXT,
    agreement_score TEXT,
    regime_compatibility_score TEXT,
    data_confidence_score TEXT,
    risk_adjusted_signal_score TEXT,
    signal_state TEXT NOT NULL,
    candidate_state TEXT NOT NULL,
    rank INTEGER,
    percentile TEXT,
    evidence_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, security_id)
);
```

### 22.6 signal_reason_events

```sql
CREATE TABLE signal_reason_events (
    reason_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);
```

### 22.7 signal_snapshot_manifests

```sql
CREATE TABLE signal_snapshot_manifests (
    signal_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    input_manifest_hash TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    canonical_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## 23. 저장 원칙

1. Decimal을 float로 저장하지 않는다.
2. 점수는 Decimal 문자열 또는 fixed-point로 저장한다.
3. 입력 Feature를 Signal 테이블에서 수정하지 않는다.
4. 동일 run_id 재실행은 멱등성을 보장한다.
5. final snapshot은 입력/정책/출력 hash를 가진다.
6. 정정된 upstream snapshot은 새 run으로 계산한다.
7. 과거 signal snapshot을 덮어쓰지 않는다.

---

## 24. 알고리즘 상세

### 24.1 전체 처리

```python
def run_signal_integration(req, repos, policy):
    universe = repos.universe.load(req.universe_snapshot_id)
    regime = repos.regime.load(req.regime_snapshot_id)
    features = repos.features.load_all(req)

    validate_temporal_contract(req, universe, regime, features)

    results = []
    for security_id in universe.security_ids:
        observations = features.for_security(security_id)
        aligned = align_features(observations, policy)
        family_scores = score_families(aligned, policy)
        agreement = calculate_agreement(family_scores, policy)
        data_confidence = calculate_data_confidence(
            observations,
            family_scores,
            agreement,
            req.evaluation_time,
            policy,
        )
        regime_score = calculate_regime_compatibility(
            family_scores,
            regime,
            policy,
        )
        alpha = calculate_alpha(family_scores, policy)
        confidence = calculate_confidence(
            data_confidence,
            agreement,
            policy,
        )
        adjusted = calculate_adjusted_signal(
            alpha,
            confidence,
            regime_score,
            policy,
        )
        candidate = resolve_candidate_state(
            alpha,
            confidence,
            adjusted,
            agreement,
            regime,
            observations,
            policy,
        )
        results.append(build_security_result(...))

    ranked = rank_candidates(results, universe, policy)
    return persist_immutable_snapshot(req, ranked, policy)
```

---

## 25. Family Score pseudocode

```python
def score_family(features, family_policy):
    applicable = [f for f in features if f.status != "NOT_APPLICABLE"]

    hard_block = [f for f in applicable if f.status in {"CONFLICTED", "BLOCKED"} and f.required]
    if hard_block:
        return FamilyScore.blocked("REQUIRED_FEATURE_BLOCKED")

    valid = [f for f in applicable if f.status == "VALID"]

    required_total = sum(f.weight for f in applicable if f.required)
    required_valid = sum(f.weight for f in valid if f.required)

    if required_total > 0 and required_valid < required_total:
        return FamilyScore.blocked("REQUIRED_FEATURE_MISSING")

    total_weight = sum(f.weight for f in applicable)
    valid_weight = sum(f.weight for f in valid)
    coverage = valid_weight / total_weight if total_weight else Decimal("0")

    if coverage < family_policy.minimum_coverage:
        return FamilyScore.degraded_or_blocked(coverage)

    contributions = []
    for f in valid:
        c = clip_contribution(f.aligned_value * f.weight, family_policy)
        contributions.append(c)

    score = sum(contributions) / valid_weight
    return FamilyScore.finalized(score=score, coverage=coverage)
```

---

## 26. Alpha pseudocode

```python
def calculate_alpha(family_scores, policy):
    required = policy.required_families

    if any(family_scores[f].status == "BLOCKED" for f in required):
        return None

    valid = {
        family: result
        for family, result in family_scores.items()
        if result.status in {"FINALIZED", "DEGRADED"}
    }

    weights = resolve_family_weights(valid, policy)

    return sum(
        valid[f].score * weights[f]
        for f in valid
    )
```

---

## 27. Ranking pseudocode

```python
def rank_candidates(results, policy):
    eligible = [r for r in results if r.candidate_state == "ELIGIBLE"]

    eligible.sort(
        key=lambda r: (
            -r.risk_adjusted_signal_score,
            -r.confidence_score,
            -r.alpha_score,
            r.security_id,
        )
    )

    for i, row in enumerate(eligible, start=1):
        row.rank = i
        row.percentile = percentile_from_rank(i, len(eligible))

    return results
```

---

## 28. 하드 차단 조건

다음은 초기 하드 블록 예시다.

```text
FUTURE_INFORMATION_DETECTED
UNIVERSE_SNAPSHOT_MISMATCH
MARKET_DATA_NOT_FINALIZED
REQUIRED_MARKET_BEHAVIOR_MISSING
IDENTITY_CONFLICTED
CORE_FEATURE_CONFLICTED
POLICY_NOT_EFFECTIVE
REGIME_SNAPSHOT_FUTURE
SIGNAL_INPUT_HASH_MISMATCH
```

하드 블록은 점수 감점으로 해결하지 않는다.

즉:

```text
데이터 오류 -30점
```

같은 방식은 금지한다.

오류는 `BLOCKED`로 처리한다.

---

## 29. Soft Penalty

정상 데이터이지만 불확실한 경우에만 soft penalty를 사용한다.

예:

```text
낮은 analyst coverage
높은 estimate dispersion
경미한 feature staleness
family conflict
시장 regime unfavorable
```

이 경우 Alpha는 보존하고 Confidence 또는 Adjusted Signal을 낮춘다.

---

## 30. 주요 Reason Code

```text
FUTURE_INFORMATION_DETECTED
POLICY_NOT_EFFECTIVE
UNIVERSE_SNAPSHOT_MISMATCH
REGIME_SNAPSHOT_MISMATCH
MARKET_DATA_NOT_FINALIZED

REQUIRED_FEATURE_MISSING
REQUIRED_FEATURE_BLOCKED
FEATURE_STALE
FEATURE_CONFLICTED
FEATURE_NOT_APPLICABLE
FEATURE_COVERAGE_LOW

FAMILY_SCORE_BLOCKED
FAMILY_SCORE_DEGRADED
FAMILY_HIGH_DISPERSION
FAMILY_CONFLICT_HIGH

ALPHA_BELOW_THRESHOLD
CONFIDENCE_BELOW_THRESHOLD
REGIME_UNFAVORABLE
REGIME_BLOCKING

WEIGHTS_RENORMALIZED
SINGLE_FEATURE_CONCENTRATION
EVIDENCE_CONCENTRATION_HIGH

NO_CANDIDATE
CANDIDATE_ELIGIBLE
CANDIDATE_WATCH

SNAPSHOT_HASH_MISMATCH
NON_DETERMINISTIC_RESULT
```

---

## 31. Explainability 계약

각 후보는 최소 다음 설명 정보를 제공해야 한다.

```python
SignalExplanationPayload(
    security_id,
    alpha_score,
    confidence_score,
    adjusted_signal_score,
    top_positive_contributors,
    top_negative_contributors,
    family_scores,
    conflict_state,
    regime_state,
    candidate_state,
    blocking_reasons,
    evidence_hash,
)
```

예:

```text
삼성전자
Alpha 78
Confidence 84

Positive
+ Revision Breadth
+ 60D Relative Strength
+ Earnings Yield

Negative
- RV20 상승
- 단기 valuation premium

Decision context
= Signal ELIGIBLE
= 최종 BUY 여부는 Risk/Decision에서 결정
```

---

## 32. 코드 구조

```text
signal_integration/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── registry.py
├── adapters/
│   ├── fundamentals.py
│   ├── factors.py
│   ├── expectations.py
│   ├── market_behavior.py
│   ├── regime.py
│   └── legacy_candidate.py
├── temporal.py
├── alignment.py
├── applicability.py
├── coverage.py
├── family_scoring.py
├── contributions.py
├── agreement.py
├── conflicts.py
├── regime_compatibility.py
├── confidence.py
├── alpha.py
├── adjusted_signal.py
├── candidate_gate.py
├── ranking.py
├── reason_codes.py
├── explainability.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

---

## 33. 모델 예시

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class CandidateState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    WATCH = "WATCH"
    REJECTED_SIGNAL = "REJECTED_SIGNAL"
    REJECTED_CONFIDENCE = "REJECTED_CONFIDENCE"
    REJECTED_REGIME = "REJECTED_REGIME"
    REJECTED_DATA = "REJECTED_DATA"
    REJECTED_CONFLICT = "REJECTED_CONFLICT"


@dataclass(frozen=True)
class FamilyScore:
    family: str
    score: Decimal | None
    coverage: Decimal
    confidence: Decimal
    status: str
    evidence_hash: str


@dataclass(frozen=True)
class SecuritySignal:
    security_id: str
    alpha_score: Decimal | None
    confidence_score: Decimal | None
    adjusted_signal_score: Decimal | None
    agreement_score: Decimal | None
    regime_compatibility_score: Decimal | None
    rank: int | None
    candidate_state: CandidateState
    reason_codes: tuple[str, ...]
    evidence_hash: str
```

---

## 34. 정책 모델 예시

```python
@dataclass(frozen=True)
class SignalPolicy:
    version: str
    family_weights: dict[str, Decimal]
    min_family_coverage: Decimal
    min_alpha: Decimal
    min_confidence: Decimal
    min_adjusted_signal: Decimal
    max_single_feature_contribution: Decimal
    block_on_high_conflict: bool
    require_market_behavior: bool
```

정책 validation:

```text
family_weights sum = 1.0
all thresholds in valid range
known_at <= evaluation_time
policy status = APPROVED
```

---

## 35. 테스트 전략

테스트를 5계층으로 분리한다.

```text
Unit
Property
Temporal leakage
Integration
Golden fixture / deterministic replay
```

---

## 36. Unit Test

### A. 방향 정렬

```text
Debt-to-Equity z = +2
preferred direction = LOWER_IS_BETTER
→ aligned score 음수
```

### B. Feature contribution cap

```text
단일 Feature 극단값
→ family contribution cap 적용
→ 전체 점수 지배 금지
```

### C. 결측값

```text
missing feature
→ 0으로 대체하지 않음
```

### D. NOT_APPLICABLE

```text
은행에 EV/EBITDA N/A
→ coverage 분모에서 제외
```

### E. required missing

```text
required market behavior feature 없음
→ family BLOCKED
```

---

## 37. Temporal Leakage Test

### F. 미래 실적공시

```text
평가시각 이후 known_at
→ 사용 0건
```

### G. 실적발표 후 수정 Consensus

```text
pre-event signal replay
→ post-event estimate 사용 0건
```

### H. 현재 Universe로 과거 rank

```text
현재 Universe snapshot 전달
+ 과거 evaluation_time
→ UNIVERSE_SNAPSHOT_MISMATCH
```

### I. 미래 Regime

```text
regime.known_at > evaluation_time
→ BLOCKED
```

---

## 38. Integration Test

### J. 강한 전방위 신호

```text
Quality +0.8
Valuation +0.7
Expectations +0.9
Market Behavior +0.8
Confidence inputs 정상
Regime FAVORABLE
→ STRONG_POSITIVE
→ ELIGIBLE
→ 상위 rank
```

### K. Fundamental 강함, Market Behavior 약함

```text
Quality +0.8
Valuation +0.7
Expectations +0.2
Market Behavior -0.8
→ conflict 증가
→ WATCH 또는 REJECTED_CONFLICT
```

### L. Alpha 높고 Confidence 낮음

```text
Alpha 85
Confidence 40
→ REJECTED_CONFIDENCE
```

### M. Alpha 중간, Confidence 높음

```text
Alpha 62
Confidence 90
min alpha 65
→ REJECTED_SIGNAL
```

### N. Regime BLOCKING

```text
Alpha 90
Confidence 95
Regime BLOCKING
→ REJECTED_REGIME
```

### O. 후보 0개

```text
모든 종목 threshold 미달
→ NO_CANDIDATE
```

---

## 39. Ranking Test

### P. 동일 점수 tie

```text
A adjusted 75, confidence 80, alpha 80
B adjusted 75, confidence 80, alpha 80
security_id A < B
→ A rank 1
→ deterministic
```

### Q. Confidence tie-break

```text
A adjusted 80, confidence 70
B adjusted 80, confidence 90
→ B 우선
```

### R. 업종별 percentile

```text
시장 rank와 sector rank 별도 생성
→ 서로 덮어쓰지 않음
```

---

## 40. Deterministic Replay Test

### S. 동일 입력

```text
동일 evaluation_time
동일 Universe
동일 Feature snapshot
동일 Regime
동일 Policy
→ 동일 score
→ 동일 rank
→ 동일 reason
→ 동일 canonical hash
```

### T. 입력 1개 수정

```text
upstream revision 변경
→ 새 input hash
→ 새 signal snapshot hash
→ 과거 snapshot 불변
```

---

## 41. 장애 / 복구 테스트

### U. DB 저장 중 실패

```text
family score 저장 후 장애
→ final manifest 생성 금지
→ run FAILED
→ 재실행 가능
```

### V. 중복 run

```text
동일 idempotency key 재호출
→ 중복 signal snapshot 생성 금지
```

### W. hash mismatch

```text
입력 artifact hash와 manifest 불일치
→ SNAPSHOT_HASH_MISMATCH
→ BLOCKED
```

---

## 42. Property Test

다음 속성을 자동 검증한다.

```text
0 <= confidence <= 100
0 <= percentile <= 100
rank >= 1 for eligible candidates
blocked candidate has no actionable rank
future known_at usage count = 0
missing feature substituted with zero count = 0
single feature contribution > cap count = 0
same inputs produce different hash count = 0
```

---

## 43. 성능 목표

PAPER v1 기준 목표:

```text
Universe 3,000 securities
Feature inputs <= 100 per security
single daily EOD run
```

목표 처리:

```text
feature alignment O(N×F)
family scoring O(N×F)
ranking O(N log N)
```

성능 최적화보다 재현성과 감사 가능성을 우선한다.

---

## 44. 감사 / Evidence Manifest

최종 Snapshot은 최소 다음 hash를 포함한다.

```text
universe_snapshot_hash
fundamental_snapshot_hash
factor_snapshot_hash
expectations_snapshot_hash
market_behavior_snapshot_hash
regime_snapshot_hash
data_quality_snapshot_hash
policy_hash
feature_registry_hash
output_hash
canonical_signal_snapshot_hash
```

종목별로:

```text
top positive contributions
top negative contributions
family score provenance
confidence components
candidate gate outcome
reason codes
```

을 추적 가능해야 한다.

---

## 45. 핵심 불변식

```text
미래정보 사용 수 = 0

현재 Universe의 과거 ranking 사용 수 = 0

결측 Feature를 0으로 대체한 수 = 0

NOT_APPLICABLE을 negative signal로 처리한 수 = 0

hard data error를 soft penalty로 처리한 수 = 0

단일 Feature가 contribution cap을 넘은 수 = 0

BLOCKED 종목이 ELIGIBLE로 전달된 수 = 0

Regime BLOCKING 종목이 ELIGIBLE로 전달된 수 = 0

동일 입력·정책·평가시각에서 rank 변경 수 = 0

과거 Signal Snapshot 수정·삭제 수 = 0
```

---

## 46. 기존 ADE 모의투자 정책과 연결

현재 PAPER 운용 제약:

```text
초기자금 10,000,000원
레버리지 없음
최소 현금 10%
종목당 최대 비중 10%
하루 신규 매수 최대 1종목
유효 후보 없으면 NO_ACTION
```

42번은 이 중 `유효 후보`의 정의를 표준화한다.

```text
Universe 통과
+ Signal threshold 통과
+ Confidence threshold 통과
+ Regime blocking 없음
+ Data hard block 없음
        ↓
Candidate ELIGIBLE
        ↓
Portfolio Risk
        ↓
Decision & Position Sizing
        ↓
최대 1개 신규매수
```

따라서 42번 도입 후 일일 ADE 보고서의 Signal 점수는 임의 숫자가 아니라 이 엔진의 Snapshot에서 직접 읽어야 한다.

---

## 47. 일일 보고서 출력 계약

Report Engine이 사용할 필드:

```text
market_date
signal_engine_version
signal_policy_version
security_id
security_name
alpha_score
confidence_score
adjusted_signal_score
rank
candidate_state
regime_compatibility
positive_reasons
negative_reasons
blocking_reasons
signal_snapshot_hash
```

보고서에서는 최소 다음을 분리한다.

```text
Signal
Risk
Decision
```

Signal이 강하다고 Risk 또는 Decision을 생략하지 않는다.

---

## 48. 구현 우선순위

### Phase 1 — Pure domain model

1. enums
2. immutable models
3. policy validation
4. Feature Registry
5. reason registry

### Phase 2 — Core scoring

6. alignment
7. applicability
8. coverage
9. family scoring
10. contribution caps
11. alpha

### Phase 3 — Confidence

12. agreement
13. freshness
14. source quality
15. stability
16. confidence score

### Phase 4 — Context / ranking

17. regime compatibility
18. adjusted signal
19. candidate gate
20. deterministic ranking

### Phase 5 — Persistence / reproducibility

21. SQLite migration
22. repository
23. manifest
24. hashing
25. idempotency

### Phase 6 — Integration

26. 38 adapter
27. 39 adapter
28. 40 adapter
29. 41 adapter
30. Market Regime adapter
31. legacy 21 adapter
32. Risk / Decision output adapter

---

## 49. 최소 구현 파일

```text
signal_integration/models.py
signal_integration/enums.py
signal_integration/policies.py
signal_integration/registry.py
signal_integration/alignment.py
signal_integration/family_scoring.py
signal_integration/agreement.py
signal_integration/confidence.py
signal_integration/alpha.py
signal_integration/regime_compatibility.py
signal_integration/candidate_gate.py
signal_integration/ranking.py
signal_integration/reason_codes.py
signal_integration/hashing.py
signal_integration/repository.py
signal_integration/engine.py
```

---

## 50. 최소 테스트 파일

```text
tests/signal_integration/test_alignment.py
tests/signal_integration/test_family_scoring.py
tests/signal_integration/test_contribution_caps.py
tests/signal_integration/test_agreement.py
tests/signal_integration/test_confidence.py
tests/signal_integration/test_alpha.py
tests/signal_integration/test_regime.py
tests/signal_integration/test_candidate_gate.py
tests/signal_integration/test_ranking.py
tests/signal_integration/test_temporal_leakage.py
tests/signal_integration/test_hashing.py
tests/integration/test_signal_pipeline_38_42.py
```

---

## 51. Golden Fixture

최소 50종목 고정 fixture를 만든다.

구성:

```text
10 strong positive
10 positive but low confidence
10 conflicting
10 neutral
10 negative / blocked
```

각 종목에 대해 다음이 고정되어야 한다.

```text
expected family score
expected alpha
expected confidence
expected candidate state
expected rank range
expected reason codes
expected hash
```

---

## 52. PAPER 10거래일 통합 테스트

```text
Day 1 strong candidate A
Day 2 candidate B but A already held
Day 3 no candidate
Day 4 regime risk-off
Day 5 earnings surprise event
Day 6 revision reversal
Day 7 market shock
Day 8 recovery
Day 9 candidate conflict
Day 10 stable risk-on
```

검증:

```text
Signal Snapshot continuity
Candidate ranking continuity
Risk / Decision separation
NO_CANDIDATE vs NO_ACTION
하루 신규 1종목 정책
Portfolio state continuity
Explainability evidence continuity
```

---

## 53. Acceptance Criteria

v1 구현 완료 조건:

```text
[ ] 38~41 adapter 연결
[ ] Feature Registry versioning
[ ] Point-in-Time leakage guard
[ ] Family score 구현
[ ] contribution cap 구현
[ ] Alpha / Confidence 분리 구현
[ ] Agreement / Conflict 구현
[ ] Regime compatibility 구현
[ ] Candidate Gate 구현
[ ] deterministic ranking 구현
[ ] SQLite persistence
[ ] immutable manifest / hash
[ ] 50종목 golden fixture 통과
[ ] 10거래일 PAPER integration 통과
[ ] 동일 입력 replay hash 일치
[ ] 미래정보 사용 0건 확인
```

---

## 54. 최종 설계 결론

42번 엔진은 ADE에서 처음으로 다음 네 질문을 한 곳에서 통합한다.

```text
기업이 좋은가?             → Fundamental / Quality
가격이 매력적인가?         → Valuation / Factors
시장 기대가 좋아지는가?    → Expectations / Revisions
실제 가격이 확인해 주는가?  → Market Behavior
```

그 결과를 단순한 하나의 숫자로 압축하지 않고:

```text
Alpha
Confidence
Agreement
Regime Compatibility
Candidate State
Rank
Evidence
```

로 분리해 다음 Risk / Decision 계층에 전달한다.

핵심 설계 원칙은 다음 한 문장으로 요약한다.

> **강한 신호와 믿을 수 있는 신호는 다르며, ADE는 둘을 분리해서 평가한 뒤에만 후보를 만든다.**
