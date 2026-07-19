# Signal Generation & Ranking Engine v1

## 1. 목적

Signal Generation & Ranking Engine은 Market Regime & Feature Engine이 만든 시점 정합 특징량을 사용해 종목별 `STRONG_BUY`, `BUY`, `HOLD`, `REDUCE`, `SELL`, `AVOID` 신호를 생성하고, 신호 강도·신뢰도·국면 적합성·유동성·안정성을 종합해 후보 종목을 순위화한다.

이 엔진은 주문을 만들거나 목표 비중을 확정하지 않는다. 최종 매매 가능 여부, 수량, 현금·계좌·집중도 제약은 Risk Engine과 Decision Engine이 결정한다.

핵심 산출물:

- 종목별 component signal과 composite signal
- 신호 방향·강도·신뢰도·유효기간
- 국면 적합성 및 유동성 보정
- 충돌·중복 신호 처리 결과
- 설명 가능한 점수 기여도와 제외 사유
- 전체 종목 순위와 후보군
- 가상투자용 일일 최대 1종목 primary candidate 또는 `NO_ACTION`
- Risk/Decision이 참조하는 immutable `SignalSnapshot`

핵심 원칙은 **point-in-time correctness, deterministic ranking, explainability, conservative gating, online/offline parity, signal stability**다.

---

## 2. 책임 경계

### 담당

- Feature/Regime/Universe/Policy/Portfolio snapshot 조회
- 규칙 기반 및 선택적 모델 기반 신호 계산
- 특징량 정규화와 횡단면 비교
- 국면별 신호 가중치 조정
- 유동성·데이터 품질·거래 상태 필터
- 중복 신호 감쇠와 상충 신호 조정
- 신호 confidence 및 validity 산출
- composite score와 결정론적 rank 계산
- entry/hold/reduce/exit 후보 분리
- signal snapshot 생성·잠금·해시
- Audit lineage와 운영 지표 발행

### 담당하지 않음

- 주문 생성·전송·체결
- 포트폴리오 목표 비중 확정
- 현금·증거금·세금·수수료 계산
- 계좌별 exposure 한도 결정
- 손익·회계 계산
- 시장 데이터 수집 및 feature 계산
- 모델 학습 파이프라인 전체 운영

```text
Feature Engine  = 무엇이 관측되었는가
Signal Engine   = 관측값이 어떤 투자 방향을 시사하는가
Risk Engine     = 그 방향을 받아들여도 안전한가
Decision Engine = 실제로 무엇을 얼마나 할 것인가
Order Engine    = 결정을 어떻게 주문으로 표현할 것인가
```

---

## 3. 핵심 설계 원칙

### 3.1 시점 정합성

```text
feature_snapshot.locked_at <= decision_cutoff
feature_value.available_at <= decision_cutoff
regime_result.available_at <= decision_cutoff
```

당일 종가 기반 신호는 당일 장중 주문에 사용할 수 없다. 장 마감 후 산출 신호는 다음 거래 세션 또는 정책이 허용하는 장후 실행부터 유효하다.

### 3.2 결정론적 순위

```text
SignalSnapshotHash = hash(
  feature_snapshot_id,
  regime_snapshot_id,
  universe_snapshot_id,
  policy_snapshot_id,
  signal_set_version,
  model_version,
  portfolio_context_hash,
  as_of,
  cutoff_at
)
```

동점 처리:

```text
1. composite_score 내림차순
2. confidence 내림차순
3. liquidity_score 내림차순
4. market_cap 내림차순
5. instrument_id 오름차순
```

### 3.3 설명 가능성

```text
composite_score
= trend contribution
+ momentum contribution
+ relative-strength contribution
+ breakout contribution
+ model contribution
+ liquidity bonus
- volatility penalty
- conflict penalty
- turnover penalty
```

각 결과는 특징량 값, 정규화 방식, 가중치, 국면 multiplier, 품질 감점, 제외 사유를 저장한다.

### 3.4 보수적 기본값

- 핵심 feature 결측: `AVOID` 또는 `UNAVAILABLE`
- `UNKNOWN` 국면 + 낮은 confidence: 신규 매수 차단
- 거래정지·상장폐지 예정·정책 제외: 후보 제외
- 저유동성: 후보 제외
- 모델 장애: 승인된 rule fallback 또는 `NO_ACTION`
- rule/model 강한 충돌: `HOLD`로 하향 가능

### 3.5 신호와 실행 분리

```text
BUY signal != BUY order
SELL signal != SELL order
```

미보유 종목의 `SELL`은 공매도 지시가 아니라 `AVOID`다.

### 3.6 Online/Offline 동일성

BACKTEST, PAPER, LIVE는 동일 calculator와 ranking core를 사용한다. Reader, clock, adapter만 다르다.

### 3.7 안정성

- score smoothing
- rank persistence
- entry/exit threshold 분리
- cooldown
- incumbent bonus
- turnover penalty
- replacement margin

급격한 위험 신호는 안정성 규칙보다 우선한다.

---

## 4. 아키텍처

```text
Market Regime & Feature Engine
        │ immutable feature/regime snapshot
        ▼
Signal Generation & Ranking Engine
├─ Request Validator
├─ Universe Resolver
├─ Portfolio Context Resolver
├─ Eligibility Filter
│  ├─ Data Quality Gate
│  ├─ Listing/Trading Status Gate
│  ├─ Liquidity Gate
│  └─ Compliance Exclusion Gate
├─ Signal Definition Registry
├─ Rule Signal Calculators
│  ├─ Trend
│  ├─ Momentum
│  ├─ Relative Strength
│  ├─ Breakout
│  ├─ Mean Reversion
│  ├─ Volume/Liquidity
│  ├─ Volatility
│  └─ Exit/Protection
├─ Model Signal Adapter
├─ Signal Normalizer
├─ Regime Compatibility Adjuster
├─ Conflict & Redundancy Resolver
├─ Confidence Estimator
├─ Stability & Turnover Controller
├─ Composite Scorer
├─ Cross-Sectional Ranker
├─ Candidate Selector
├─ Explanation Builder
├─ Signal Snapshot Builder
├─ Repository
└─ Audit & Metrics Publisher
        │
        ├─ Risk Engine
        ├─ Decision Engine
        ├─ Backtest Engine
        └─ Report Engine
```

---

## 5. 입력과 출력

### 입력

- `FeatureSnapshot`
- `RegimeResult`
- `UniverseSnapshot`
- `PolicySnapshot`
- `PortfolioContext`
- 선택적 `ModelPredictionSnapshot`
- 실행 mode: `BACKTEST`, `PAPER`, `LIVE_BLOCKED`, `LIVE`
- `as_of`, `cutoff_at`

### 출력

```text
SignalSnapshot
├─ component signals
├─ ranked signals
├─ entry/exit/watch candidates
├─ exclusions
├─ explanations
└─ hashes and lineage
```

보유 상태별 action hint:

```text
미보유 + BUY/STRONG_BUY → ENTRY_CANDIDATE
미보유 + HOLD           → WATCHLIST
미보유 + REDUCE/SELL    → AVOID
보유   + STRONG_BUY     → ADD_CANDIDATE
보유   + BUY/HOLD       → HOLD_OR_ADD / HOLD
보유   + REDUCE         → REDUCE_CANDIDATE
보유   + SELL           → EXIT_CANDIDATE
```

Action hint는 Decision이 아니다.

---

## 6. 도메인 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

SignalDirection = Literal[
    "STRONG_BUY", "BUY", "HOLD", "REDUCE", "SELL", "AVOID", "UNAVAILABLE"
]

@dataclass(frozen=True)
class SignalDefinition:
    signal_name: str
    signal_version: str
    category: str
    required_features: tuple[str, ...]
    supported_regimes: tuple[str, ...]
    weight: Decimal
    min_quality: str
    validity_seconds: int
    enabled_modes: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ComponentSignal:
    component_signal_id: str
    instrument_id: str
    signal_name: str
    signal_version: str
    as_of: datetime
    direction: SignalDirection
    raw_score: Decimal
    normalized_score: Decimal
    confidence: Decimal
    validity_until: datetime
    quality_status: str
    evidence: dict[str, Any]

@dataclass(frozen=True)
class RankedSignal:
    instrument_id: str
    direction: SignalDirection
    composite_score: Decimal
    confidence: Decimal
    regime_fit: Decimal
    liquidity_score: Decimal
    stability_score: Decimal
    ranking_score: Decimal
    rank: int | None
    percentile: Decimal | None
    eligible: bool
    action_hint: str
    exclusion_reasons: tuple[str, ...]
    explanation: dict[str, Any]

@dataclass(frozen=True)
class SignalSnapshot:
    signal_snapshot_id: str
    run_id: str
    as_of: datetime
    cutoff_at: datetime
    mode: str
    universe_snapshot_id: str
    feature_snapshot_id: str
    regime_snapshot_id: str
    policy_snapshot_id: str
    signal_set_version: str
    model_version: str | None
    status: Literal["BUILDING", "VALIDATED", "LOCKED", "FAILED", "ABORTED"]
    candidate_count: int
    excluded_count: int
    snapshot_hash: str | None
    created_at: datetime
    locked_at: datetime | None
```

---

## 7. Signal Set v1

### 7.1 Trend

입력: `price_to_sma20`, `sma20_to_sma60`, `sma60_slope_20d`, `trend_strength`, `macd_histogram`.

```text
trend_raw =
  0.30*z(price_to_sma20)
+ 0.25*z(sma20_to_sma60)
+ 0.25*z(sma60_slope_20d)
+ 0.20*z(macd_histogram)
```

### 7.2 Momentum

입력: `return_20d`, `return_60d`, `return_120d`, `rsi_14`, `distance_from_52w_high`.

```text
momentum_raw =
  0.35*rank(return_20d)
+ 0.35*rank(return_60d)
+ 0.20*rank(return_120d)
+ 0.10*high_proximity
- overbought_penalty(rsi_14)
```

### 7.3 Relative Strength

```text
relative_strength =
  0.5*(instrument_return_60d - market_return_60d)
+ 0.3*(instrument_return_20d - sector_return_20d)
+ 0.2*relative_volume_strength
```

### 7.4 Breakout

```text
close > previous_20d_high
volume_ratio_20d >= 1.5
median_traded_value_20d >= policy minimum
close_location_value >= 0.7
```

장대 윗꼬리, 과도한 gap, 낮은 유동성, HIGH_VOL 국면은 감점한다.

### 7.5 Mean Reversion

`SIDEWAY` 또는 일부 `RECOVERY`에서만 활성화한다. 장기 하락 추세에서는 단순 과매도만으로 매수하지 않는다.

### 7.6 Volume/Liquidity Confirmation

거래량, 거래대금, spread, turnover, Amihud illiquidity를 사용해 다른 신호 confidence를 보정한다.

### 7.7 Volatility

realized volatility percentile, ATR/price, downside volatility, gap risk를 사용한다. 과도한 변동성은 entry를 감점하고 exit 신호를 강화한다.

### 7.8 Exit/Protection

- 추세 붕괴
- 모멘텀 반전
- 변동성 급증
- 유동성 악화
- 거래 상태 이상
- signal decay
- time stop 정보

가격 손절과 계좌별 청산 확정은 Risk/Decision 정책에 둔다.

### 7.9 Model Signal

필수 메타데이터:

```text
model_name, model_version, training_cutoff,
feature_schema_hash, prediction_horizon,
calibration_version, approval_status
```

LIVE는 승인된 모델만 허용한다.

---

## 8. Eligibility Filter

기본 조건:

```text
feature_snapshot.status == LOCKED
critical_feature_quality == VALID
price_age <= max_price_age
universe_member == true
listing_status == ACTIVE
trading_status == NORMAL
```

가상투자 v1 유동성 예시:

```text
median_traded_value_20d >= 5,000,000,000 KRW
close_price >= 1,000 KRW
valid_days_60d >= 50
```

제외 코드:

```text
EX_DATA_QUALITY
EX_STALE_PRICE
EX_LOW_LIQUIDITY
EX_TRADING_SUSPENDED
EX_LISTING_STATUS
EX_WARMUP
EX_COMPLIANCE
EX_UNKNOWN_REGIME
EX_POLICY
```

---

## 9. 정규화와 국면 적합성

### 정규화

```text
robust_z = (x - median) / (1.4826 * MAD)
percentile = rank(x) / valid_universe_count
normalized = 2*percentile - 1
```

극단값은 winsorization한다. 표본이 부족하면 `DEGRADED`로 표시하고 confidence를 낮춘다.

### 국면 multiplier 예시

| Signal | BULL | BEAR | SIDEWAY | HIGH_VOL | LIQUIDITY_STRESS | RECOVERY |
|---|---:|---:|---:|---:|---:|---:|
| Trend | 1.20 | 0.40 | 0.70 | 0.50 | 0.00 | 1.00 |
| Momentum | 1.15 | 0.30 | 0.60 | 0.40 | 0.00 | 1.10 |
| Breakout | 1.20 | 0.20 | 0.70 | 0.35 | 0.00 | 1.20 |
| Mean Reversion | 0.50 | 0.20 | 1.20 | 0.50 | 0.00 | 1.00 |
| Relative Strength | 1.00 | 0.80 | 1.00 | 0.80 | 0.20 | 1.10 |

```text
expected_multiplier(signal)
= Σ P(regime=r) * multiplier(signal,r)
```

`LIQUIDITY_STRESS`에서는 신규 진입 weight를 0으로 만들 수 있다.

---

## 10. 충돌·중복 처리

상관이 높은 signal family는 기여도 cap을 적용한다.

```text
family_contribution = clip(sum(contributions), -family_cap, family_cap)
```

충돌 지수:

```text
conflict_index
= 1 - abs(weighted_sum) / sum(abs(weighted_components))
```

confidence 보정:

```text
confidence *= 1 - conflict_penalty*conflict_index
```

rule과 model이 모두 고신뢰 상태에서 반대 방향이면 신규 진입을 `HOLD`로 낮추거나 차단한다.

---

## 11. Confidence와 Composite Score

```text
confidence = clamp(
  0.25*data_quality
+ 0.15*feature_coverage
+ 0.20*component_agreement
+ 0.15*regime_confidence
+ 0.15*stability
+ 0.10*model_reliability
- stale_penalty,
0,1)
```

```text
base_score = Σ(
 normalized_component_score
 * policy_weight
 * regime_multiplier
 * quality_multiplier)
```

```text
composite_score = clamp(
 base_score
 + incumbent_bonus
 + persistence_bonus
 + liquidity_bonus
 - conflict_penalty
 - volatility_penalty
 - turnover_penalty,
-1,1)
```

방향 변환 예시:

```text
score >=  0.70 and confidence >= 0.75 → STRONG_BUY
score >=  0.35 and confidence >= 0.60 → BUY
score >  -0.20                         → HOLD
score >  -0.55                         → REDUCE
else                                  → SELL
```

미보유 종목의 음수 신호는 `AVOID`로 표시한다.

Entry/Exit 비대칭:

```text
entry_threshold = 0.45
hold_threshold  = 0.10
exit_threshold  = -0.45
```

---

## 12. 순위와 후보 선정

```text
ranking_score =
  0.65*composite_score
+ 0.15*confidence
+ 0.10*liquidity_score
+ 0.10*stability_score
```

별도 목록:

- `entry_rank`
- `hold_rank`
- `reduce_rank`
- `exit_rank`
- `watchlist_rank`

가상투자 primary candidate 조건:

```text
rank == 1
eligible == true
direction in {BUY, STRONG_BUY}
confidence >= minimum_entry_confidence
regime permits new entry
signal validity covers next execution window
```

후보가 없으면:

```text
primary_candidate = None
selection_status = NO_ACTION
```

현재 가상투자 정책:

```text
initial_cash              = 10,000,000 KRW
max_new_entries_per_day   = 1
max_weight_per_instrument = 10%
minimum_cash_weight       = 10%
leverage                  = disabled
```

Signal Engine은 후보만 제안하며 실제 수량·금액은 Decision Engine이 계산한다.

우선순위:

```text
HARD_EXIT > SELL > REDUCE > NEW_ENTRY > HOLD
```

---

## 13. 유효기간과 안정성

```text
Daily close signal: 다음 거래일 장 마감까지
Intraday signal: 정책상 5~60분
```

```text
decayed_score = original_score * exp(-lambda*elapsed_seconds)
```

만료 신호는 LIVE Decision 입력으로 사용할 수 없다.

안정성:

```text
smoothed_score_t
= alpha*score_t + (1-alpha)*smoothed_score_(t-1)
```

```text
replace only if:
challenger_score - incumbent_score >= replacement_margin
```

매도 후 재진입 cooldown과 보유 종목 incumbent bonus를 지원한다. Hard exit에는 cooldown을 적용하지 않는다.

---

## 14. 데이터베이스

```sql
CREATE TABLE signal_definition (
  signal_name TEXT NOT NULL,
  signal_version TEXT NOT NULL,
  category TEXT NOT NULL,
  required_features_json TEXT NOT NULL,
  supported_regimes_json TEXT NOT NULL,
  weight NUMERIC NOT NULL,
  validity_seconds INTEGER NOT NULL,
  parameters_json TEXT NOT NULL,
  status TEXT NOT NULL,
  approved_by TEXT,
  approved_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  PRIMARY KEY(signal_name, signal_version)
);

CREATE TABLE signal_snapshot (
  signal_snapshot_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  as_of TIMESTAMP NOT NULL,
  cutoff_at TIMESTAMP NOT NULL,
  mode TEXT NOT NULL,
  universe_snapshot_id TEXT NOT NULL,
  feature_snapshot_id TEXT NOT NULL,
  regime_snapshot_id TEXT NOT NULL,
  policy_snapshot_id TEXT NOT NULL,
  signal_set_version TEXT NOT NULL,
  model_version TEXT,
  portfolio_context_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  excluded_count INTEGER NOT NULL DEFAULT 0,
  snapshot_hash TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL,
  locked_at TIMESTAMP
);

CREATE TABLE component_signal (
  component_signal_id TEXT PRIMARY KEY,
  signal_snapshot_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  signal_name TEXT NOT NULL,
  signal_version TEXT NOT NULL,
  direction TEXT NOT NULL,
  raw_score NUMERIC,
  normalized_score NUMERIC,
  confidence NUMERIC NOT NULL,
  quality_status TEXT NOT NULL,
  validity_until TIMESTAMP NOT NULL,
  evidence_json TEXT NOT NULL,
  component_hash TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE ranked_signal (
  ranked_signal_id TEXT PRIMARY KEY,
  signal_snapshot_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  composite_score NUMERIC NOT NULL,
  confidence NUMERIC NOT NULL,
  regime_fit NUMERIC NOT NULL,
  liquidity_score NUMERIC NOT NULL,
  stability_score NUMERIC NOT NULL,
  ranking_score NUMERIC NOT NULL,
  rank_value INTEGER,
  percentile NUMERIC,
  eligible BOOLEAN NOT NULL,
  action_hint TEXT NOT NULL,
  exclusion_reasons_json TEXT NOT NULL,
  explanation_json TEXT NOT NULL,
  result_hash TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  UNIQUE(signal_snapshot_id, instrument_id)
);

CREATE TABLE signal_candidate (
  signal_snapshot_id TEXT NOT NULL,
  candidate_type TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  candidate_rank INTEGER NOT NULL,
  selection_status TEXT NOT NULL,
  selection_reason TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  PRIMARY KEY(signal_snapshot_id, candidate_type, instrument_id)
);
```

필수 인덱스:

```sql
CREATE INDEX idx_ranked_signal_snapshot_rank
ON ranked_signal(signal_snapshot_id, eligible, rank_value);

CREATE INDEX idx_ranked_signal_instrument_time
ON ranked_signal(instrument_id, created_at DESC);
```

---

## 15. Repository와 서비스 알고리즘

```python
class SignalSnapshotRepository(Protocol):
    def find_by_idempotency_key(self, key: str) -> SignalSnapshot | None: ...
    def create_building(self, snapshot: SignalSnapshot) -> None: ...
    def save_components(self, items: Sequence[ComponentSignal]) -> None: ...
    def save_ranked(self, items: Sequence[RankedSignal]) -> None: ...
    def lock(self, snapshot_id: str, snapshot_hash: str, locked_at: datetime) -> None: ...
    def mark_failed(self, snapshot_id: str, error_code: str) -> None: ...
```

전체 흐름:

```text
1. 요청 검증
2. Policy/Feature/Regime/Universe/Portfolio resolve
3. idempotency 확인
4. BUILDING snapshot 생성
5. point-in-time 검증
6. eligibility filter
7. component signal 계산
8. 정규화와 국면 보정
9. 충돌·중복 해소
10. confidence와 stability 계산
11. composite score와 rank
12. candidate 선택
13. explanation 생성
14. 품질 검증
15. hash 계산 및 LOCKED
16. Audit/metrics 발행
```

```python
def generate_and_rank(request):
    inputs = resolver.resolve(request)
    validate_point_in_time(inputs, request.cutoff_at)

    key = build_idempotency_key(request, inputs)
    existing = repository.find_by_idempotency_key(key)
    if existing and existing.status == "LOCKED":
        return load_result(existing.signal_snapshot_id)

    snapshot = repository.create_building(build_snapshot(request, inputs, key))
    try:
        eligible, exclusions = eligibility_filter.apply(inputs)
        components = calculators.calculate_all(eligible, inputs)
        normalized = normalizer.normalize(components, eligible)
        adjusted = regime_adjuster.apply(normalized, inputs.regime, inputs.policy)
        resolved = conflict_resolver.resolve(adjusted, inputs.policy)
        ranked = scorer.score_and_rank(resolved, inputs)
        candidates = selector.select(ranked, inputs)
        validate_output(ranked, candidates)
        repository.save_components(components)
        repository.save_ranked(ranked)
        snapshot_hash = hash_snapshot(snapshot, components, ranked, candidates)
        repository.lock(snapshot.signal_snapshot_id, snapshot_hash, clock.now())
        audit.publish_success(snapshot, candidates)
        return candidates
    except Exception as exc:
        repository.mark_failed(snapshot.signal_snapshot_id, classify(exc))
        audit.publish_failure(snapshot, exc)
        raise
```

---

## 16. 코드 초안

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class ScoreParts:
    trend: Decimal
    momentum: Decimal
    relative_strength: Decimal
    breakout: Decimal
    mean_reversion: Decimal
    model: Decimal
    liquidity_bonus: Decimal
    volatility_penalty: Decimal
    conflict_penalty: Decimal
    turnover_penalty: Decimal

def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(value, high))

def calculate_composite(parts, weights, regime):
    positive = (
        parts.trend*weights["trend"]*regime["trend"]
        + parts.momentum*weights["momentum"]*regime["momentum"]
        + parts.relative_strength*weights["relative_strength"]
        + parts.breakout*weights["breakout"]*regime["breakout"]
        + parts.mean_reversion*weights["mean_reversion"]*regime["mean_reversion"]
        + parts.model*weights.get("model", Decimal("0"))
        + parts.liquidity_bonus
    )
    penalties = (
        parts.volatility_penalty
        + parts.conflict_penalty
        + parts.turnover_penalty
    )
    return clamp(positive-penalties, Decimal("-1"), Decimal("1"))

def classify_direction(score: Decimal, confidence: Decimal, held: bool) -> str:
    if score >= Decimal("0.70") and confidence >= Decimal("0.75"):
        return "STRONG_BUY"
    if score >= Decimal("0.35") and confidence >= Decimal("0.60"):
        return "BUY"
    if score > Decimal("-0.20"):
        return "HOLD"
    if score > Decimal("-0.55"):
        return "REDUCE" if held else "AVOID"
    return "SELL" if held else "AVOID"
```

결정론적 rank는 composite, confidence, liquidity, market cap, instrument ID 순으로 정렬한다. 난수는 사용하지 않는다.

---

## 17. 정책 예시

```yaml
signal_engine:
  signal_set_version: v1
  minimum_entry_confidence: 0.60
  minimum_valid_universe: 300
  unknown_regime_new_entry: false
  liquidity:
    median_traded_value_20d_min_krw: 5000000000
    close_price_min_krw: 1000
  weights:
    trend: 0.25
    momentum: 0.25
    relative_strength: 0.20
    breakout: 0.15
    mean_reversion: 0.05
    model: 0.10
  thresholds:
    strong_buy: 0.70
    buy: 0.35
    hold_lower: -0.20
    reduce_lower: -0.55
  stability:
    smoothing_alpha: 0.70
    incumbent_bonus: 0.03
    replacement_margin: 0.08
    reentry_cooldown_sessions: 3
  virtual_portfolio:
    max_new_entries_per_day: 1
    max_weight_per_instrument: 0.10
    minimum_cash_weight: 0.10
    leverage_enabled: false
```

---

## 18. 불변식

```text
1. LOCKED FeatureSnapshot 없이 SignalSnapshot 생성 금지
2. cutoff 이후 available_at 데이터 사용 금지
3. LOCKED SignalSnapshot 수정 금지
4. 동일 idempotency key는 동일 snapshot 반환
5. eligible=false 종목은 entry candidate가 될 수 없음
6. rank는 snapshot 내 중복될 수 없음
7. primary candidate는 rank 1과 일치
8. confidence/percentile은 [0,1]
9. composite_score는 [-1,1]
10. 미보유 종목 SELL은 주문 의미가 없음
11. LIQUIDITY_STRESS에서 신규 entry 금지
12. EXPIRED 신호는 LIVE Decision 입력 금지
13. 가상투자 primary entry candidate는 하루 최대 1개
14. 모든 RankedSignal은 explanation과 lineage를 가짐
15. 동일 입력·버전은 동일 snapshot hash 생성
```

---

## 19. Audit와 운영 지표

Audit 이벤트:

```text
SIGNAL_RUN_REQUESTED
SIGNAL_SNAPSHOT_BUILD_STARTED
SIGNAL_INSTRUMENT_EXCLUDED
SIGNAL_COMPONENT_CALCULATED
SIGNAL_MODEL_FALLBACK_USED
SIGNAL_CONFLICT_DETECTED
SIGNAL_RANKING_COMPLETED
SIGNAL_PRIMARY_CANDIDATE_SELECTED
SIGNAL_NO_ACTION_SELECTED
SIGNAL_SNAPSHOT_LOCKED
SIGNAL_SNAPSHOT_FAILED
SIGNAL_EXPIRED_REJECTED
```

운영 지표:

- 계산 지연시간
- universe coverage와 eligibility 통과율
- exclusion reason 분포
- signal/composite/confidence 분포
- conflict index
- 일별 rank turnover와 top-k persistence
- `NO_ACTION` 비율
- model fallback 횟수
- expired signal 거부
- point-in-time violation
- Signal→Decision 채택률
- horizon별 사후 수익률

사후 성과는 현재 snapshot을 수정하지 않고 Performance/Research 계층에서 계산한다.

---

## 20. 실패 처리

- FeatureSnapshot 미잠금: 실행 차단
- Regime 없음: 정책에 따라 `UNKNOWN` 또는 실패
- Universe 불일치: 실패
- 비핵심 calculator 실패: `UNAVAILABLE`, confidence 하향
- 핵심 calculator 실패: snapshot 실패 또는 신규 진입 차단
- model timeout: 승인 fallback 또는 `NO_ACTION`
- DB lock 전 장애: `FAILED`/`ABORTED`
- rank 중복, NaN, 범위 위반, primary candidate 불일치: lock 전 실패
- locked snapshot은 수정하지 않고 신규 snapshot으로 재처리

---

## 21. 테스트 계획

### 단위

- Trend/Momentum/Relative Strength/Breakout/Mean Reversion
- volatility penalty
- robust z-score, winsorization, percentile rank
- regime multiplier
- conflict index와 confidence
- composite 범위와 direction 분류
- decay, cooldown, incumbent bonus, replacement margin
- deterministic tie-breaker

### 시점 정합성

- cutoff 이후 feature 제외
- 당일 종가의 당일 장중 사용 차단
- 정정 데이터 available_at 반영
- historical universe 보존
- model training cutoff 검증
- portfolio context 시점 검증

### Eligibility

- 거래정지·상장폐지·신규상장 warmup
- 거래대금·가격 기준
- 관리종목·compliance blacklist
- 핵심 feature 결측
- UNKNOWN 국면 진입 차단

### DB

- idempotency 중복
- lock 이후 수정 차단
- component/ranked atomicity
- rank uniqueness
- hash 검증
- 재처리 신규 snapshot

### 통합

- Data→Feature→Regime→Signal
- Signal→Risk→Decision
- Scheduler 장 마감 trigger
- Backtest replay/PAPER/LIVE_BLOCKED
- Audit lineage
- Portfolio 보유 상태 action hint
- Report 후보·근거·차단 사유

### 속성 기반

- 입력 순서 변경에도 동일 rank
- 미래 데이터 추가가 과거 snapshot을 변경하지 않음
- score `[−1,1]`, confidence `[0,1]`
- eligible 0개면 `NO_ACTION`
- LIQUIDITY_STRESS entry 0개
- rank는 1부터 연속
- primary candidate 최대 1개

### 실패 주입

- repository/model/policy timeout
- 일부 calculator exception
- DB write 또는 lock 직전 crash
- audit publisher 장애
- clock skew, 중복 trigger, stale portfolio context

### 성능 목표

```text
3,000종목 × 20 component signal 계산 P95 < 10초
ranking P95 < 2초
locked snapshot 단일 종목 조회 P95 < 50ms
10년 일봉 backfill 및 동시 시장 3개 처리
```

대표 테스트:

```python
def test_liquidity_stress_blocks_new_entry(engine, inputs):
    inputs.regime.state = "LIQUIDITY_STRESS"
    result = engine.generate_and_rank(inputs.request)
    assert result.primary_entry_candidate is None
    assert result.selection_status == "NO_ACTION"

def test_deterministic_tie_breaker():
    items = [
        make_ranked("005930", "0.70", "0.80", "0.90"),
        make_ranked("000660", "0.70", "0.80", "0.90"),
    ]
    assert [x.instrument_id for x in rank_signals(items)] == ["000660", "005930"]

def test_future_feature_is_rejected(engine, inputs):
    inputs.feature.available_at = inputs.request.cutoff_at + timedelta(seconds=1)
    with pytest.raises(PointInTimeViolation):
        engine.generate_and_rank(inputs.request)
```

---

## 22. 구현 순서

### Phase 1 — Rule Signal Core

- Registry
- Trend/Momentum/Relative Strength
- Eligibility Filter
- normalization, composite, deterministic rank
- immutable snapshot와 repository

### Phase 2 — Virtual Portfolio Integration

- 보유 상태 action hint
- 하루 최대 1종목 primary candidate
- `NO_ACTION`
- cooldown/turnover penalty
- Signal→Risk→Decision 및 일일 보고서 연계

### Phase 3 — Advanced Signals

- Breakout/Mean Reversion/Exit
- sector relative strength
- family cap/conflict resolver
- smoothing/rank persistence

### Phase 4 — Model Integration

- model registry와 approval
- calibration, rule/model blend
- fallback, drift/성과 모니터링

### Phase 5 — Intraday

- 분봉 신호, expiry/decay
- event trigger, realtime liquidity gate
- low-latency ranking

---

## 23. 완료 기준

- Feature/Regime snapshot 시점 정합성 검증
- Trend/Momentum/Relative Strength 계산
- eligibility와 exclusion reason 저장
- component/composite score 재현 가능
- 국면 보정과 충돌 confidence 적용
- 결정론적 rank와 tie-breaker
- immutable locked snapshot과 hash
- 동일 idempotency 재실행 일치
- BACKTEST/PAPER/LIVE 공통 core
- 가상투자 일일 최대 1종목 또는 `NO_ACTION`
- Risk/Decision이 signal snapshot ID 참조
- Report에 Signal/Risk/Decision 근거 출력
- Feature→Signal→Decision 감사 역추적
- 미래 데이터·만료 신호·저유동성 자동 차단
- 3,000종목 성능 목표 충족

---

## 24. 다음 설계 대상

다음 엔진은 **Portfolio Risk & Exposure Engine v1**로 한다.

Signal 후보와 현재 포트폴리오를 결합하여 종목·섹터·시장·스타일·변동성·유동성·집중도·상관관계 위험을 측정한다. 신규 진입 허용 여부, 최대 허용 비중, 감축 필요성, 현금 하한, 손실 한도, drawdown 보호 모드, 가상투자의 종목당 10%·최소 현금 10%·무레버리지 정책을 구체화한다.
