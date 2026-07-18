# Market Regime & Feature Engine v1

## 1. 목적

Market Regime & Feature Engine은 ADE가 사용하는 시장 데이터를 시점 정합성이 보장된 특징량(feature)으로 변환하고, 시장의 추세·변동성·유동성·시장 폭·상관관계·위험선호 상태를 종합하여 시장 국면(regime)을 판정하는 계층이다.

이 엔진은 종목을 직접 매수하거나 매도하지 않는다. Signal Engine, Risk Engine, Decision Engine이 동일한 시점·동일한 정의·동일한 버전의 특징량과 시장 국면을 사용하도록 표준화한다.

핵심 결과는 다음과 같다.

- 종목·섹터·시장 단위 특징량
- 특징량 품질 상태와 결측 사유
- `BULL`, `BEAR`, `SIDEWAY`, `HIGH_VOL`, `LIQUIDITY_STRESS` 시장 국면
- 국면별 확률과 신뢰도
- Signal/Risk/Decision이 참조할 immutable feature snapshot
- 백테스트와 실시간 실행 간 동일 계산 보장
- 데이터 누수, 미래값 참조, 수정주가 오류 방지

핵심 설계 목표는 **point-in-time correctness, deterministic computation, feature versioning, lineage, online/offline parity, conservative fallback**이다.

---

## 2. 책임 경계

### 담당

- 가격·거래량·호가·지수·시장 폭·섹터·환율·금리 데이터 정규화
- 수익률, 이동평균, 모멘텀, 변동성, 거래대금, 유동성 특징량 계산
- 시장 폭, 상관관계, 분산도, 위험선호 특징량 계산
- 특징량 스키마와 버전 관리
- 특징량 스냅샷 생성 및 잠금
- point-in-time join과 look-ahead bias 방지
- 특징량 품질 검증과 결측 처리
- 시장 국면 점수·확률·상태 계산
- 국면 전환 hysteresis와 최소 지속기간 적용
- Signal/Risk/Decision용 조회 API 제공
- Backtest와 PAPER/LIVE의 동일 계산 경로 제공
- 데이터와 결과의 lineage 기록

### 담당하지 않음

- 종목 최종 순위 결정
- 포트폴리오 목표 비중 산출
- 주문 생성·체결
- 브로커 연동
- 손익·회계 계산
- 뉴스·공시 원문 수집
- 모델 학습 파이프라인 전체 운영

이 엔진은 **현재 시장이 어떤 상태이며 각 자산이 어떤 특징을 보이는지** 설명하고, Signal Engine은 **그 특징에서 어떤 투자 신호를 만들지** 결정한다.

---

## 3. 핵심 설계 원칙

### 3.1 시점 정합성

특징량은 의사결정 시각 이전에 실제로 이용 가능했던 데이터만 사용한다.

```text
feature_as_of <= decision_cutoff
source_available_at <= decision_cutoff
```

거래일 종가 기반 전략은 당일 장중 주문에 당일 종가를 사용할 수 없다. 예를 들어 2026-07-20 종가 특징량은 2026-07-20 장 마감 이후 실행되는 의사결정부터 사용 가능하다.

### 3.2 결정론적 계산

동일한 입력 데이터셋 버전, 정책 버전, feature definition version, 코드 버전을 사용하면 동일한 결과가 생성되어야 한다.

```text
FeatureSnapshotHash = hash(
    dataset_snapshot_id,
    feature_set_version,
    policy_version,
    code_version,
    as_of
)
```

### 3.3 Online/Offline 동일성

BACKTEST와 PAPER/LIVE가 서로 다른 수식을 사용하지 않는다.

```text
Historical Reader ─┐
Realtime Reader ───┼→ Canonical Market Frame → Feature Core
Replay Reader ─────┘
```

### 3.4 Raw·Derived·Decision 분리

- Raw: 원천 시장 데이터
- Normalized: 단위·시간대·기업행동 보정 데이터
- Feature: 수학적 파생값
- Regime: 특징량을 결합한 상태 판정
- Signal: 별도 Signal Engine이 생성

### 3.5 보수적 결측 처리

핵심 특징량이 결측이면 임의 보간으로 거래 가능 상태를 만들지 않는다.

- 비핵심 특징: 정책에 따른 제한적 forward fill 또는 median 대체
- 핵심 특징: `UNAVAILABLE` 또는 `DEGRADED`
- LIVE: 핵심 특징 결측 시 신규 진입 차단 가능
- BACKTEST: 결측 시 해당 시점 또는 종목 제외

### 3.6 국면은 확률과 상태를 함께 제공

단일 label만 저장하지 않는다.

```text
state       = HIGH_VOL
confidence  = 0.82
probability = {
  BULL: 0.08,
  BEAR: 0.10,
  SIDEWAY: 0.18,
  HIGH_VOL: 0.56,
  LIQUIDITY_STRESS: 0.08
}
```

---

## 4. 아키텍처

```text
Data Snapshot & Lineage Engine
        │ immutable dataset snapshot
        ▼
Market Regime & Feature Engine
├─ Input Snapshot Resolver
├─ Point-in-Time Join Service
├─ Canonical Market Frame Builder
├─ Corporate Action Adjuster
├─ Feature Definition Registry
├─ Feature Calculator
│  ├─ Price & Return Features
│  ├─ Trend & Momentum Features
│  ├─ Volatility Features
│  ├─ Volume & Liquidity Features
│  ├─ Breadth Features
│  ├─ Correlation & Dispersion Features
│  └─ Macro & Risk Appetite Features
├─ Feature Quality Validator
├─ Feature Snapshot Builder
├─ Regime Scoring Engine
├─ Regime State Machine
├─ Feature/Regime Repository
└─ Audit & Metrics Publisher
        │
        ├─ Signal Engine
        ├─ Risk Engine
        ├─ Decision Engine
        ├─ Backtest Engine
        └─ Report Engine
```

외부 연동:

```text
Configuration & Policy Engine
 └─ window, threshold, missing policy, regime transition policy

Scheduler & Trigger Engine
 └─ 장중 계산, 장 마감 계산, 재처리, backfill trigger

Audit & Compliance Engine
 └─ feature version, snapshot hash, 수동 재처리, LIVE 품질 위반

Portfolio Accounting & Performance Engine
 └─ 포트폴리오 beta, exposure, regime별 성과 분석 입력
```

---

## 5. 데이터 계층

### 5.1 입력 데이터

```text
Market Index
- KOSPI, KOSDAQ, KOSPI200

Instrument OHLCV
- open, high, low, close, volume, value

Market Microstructure
- bid/ask, spread, depth, turnover

Breadth
- 상승/하락/보합 종목 수
- 신고가/신저가 종목 수
- 이동평균 상회 종목 비율

Cross Asset
- KRW/USD
- 국채 금리
- 변동성 지수 또는 대체 변동성 지표

Reference
- 종목 master
- 섹터 분류
- 거래정지, 관리종목, 상장/폐지일
- 분할, 배당락, 권리락 등 기업행동
```

### 5.2 시간 필드

모든 데이터는 최소 다음 시간을 가진다.

- `event_time`: 시장에서 경제적 사건이 발생한 시각
- `source_time`: 원천 제공자가 기록한 시각
- `available_at`: ADE가 실제 사용 가능해진 시각
- `ingested_at`: ADE 저장 시각

point-in-time join은 `event_time`이 아니라 `available_at` 기준을 포함해야 한다.

---

## 6. 표준 도메인 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class FeatureDefinition:
    feature_name: str
    entity_type: Literal["MARKET", "SECTOR", "INSTRUMENT", "PORTFOLIO"]
    value_type: Literal["DECIMAL", "INTEGER", "BOOLEAN", "CATEGORY"]
    frequency: Literal["TICK", "MINUTE", "DAILY", "WEEKLY"]
    lookback: int
    formula_version: str
    required_inputs: tuple[str, ...]
    missing_policy: str
    warmup_period: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureValue:
    snapshot_id: str
    feature_name: str
    entity_type: str
    entity_id: str
    as_of: datetime
    value_decimal: Decimal | None
    value_text: str | None
    quality_status: Literal["VALID", "DEGRADED", "MISSING", "INVALID"]
    source_dataset_ids: tuple[str, ...]
    definition_version: str
    available_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeResult:
    regime_snapshot_id: str
    market_id: str
    as_of: datetime
    state: Literal[
        "BULL", "BEAR", "SIDEWAY", "HIGH_VOL",
        "LIQUIDITY_STRESS", "RECOVERY", "UNKNOWN"
    ]
    confidence: Decimal
    probabilities: dict[str, Decimal]
    component_scores: dict[str, Decimal]
    previous_state: str | None
    transition_reason: str
    feature_snapshot_id: str
    policy_version: str
    model_version: str
```

---

## 7. Feature Set v1

### 7.1 수익률·가격 특징

- `return_1d`
- `return_5d`
- `return_20d`
- `return_60d`
- `log_return_1d`
- `gap_return`
- `distance_from_52w_high`
- `distance_from_52w_low`

수익률:

```text
R_t(n) = P_t / P_(t-n) - 1
```

### 7.2 추세 특징

- `sma_5`, `sma_20`, `sma_60`, `sma_120`, `sma_200`
- `ema_12`, `ema_26`
- `price_to_sma20`
- `sma20_to_sma60`
- `sma60_slope_20d`
- `trend_strength`
- `macd`, `macd_signal`, `macd_histogram`

예시:

```text
trend_strength = clip(
    0.4 * z(price / sma_60 - 1)
  + 0.3 * z(sma_20 / sma_60 - 1)
  + 0.3 * z(slope(sma_60, 20)),
  -3, 3
)
```

### 7.3 모멘텀 특징

- `momentum_20d`
- `momentum_60d`
- `momentum_120d`
- `momentum_12_1`
- `rsi_14`
- `relative_strength_market_20d`
- `relative_strength_sector_20d`
- `cross_sectional_momentum_rank`

`momentum_12_1`은 최근 1개월을 제외한 장기 모멘텀으로 계산한다.

### 7.4 변동성 특징

- `realized_vol_5d`
- `realized_vol_20d`
- `realized_vol_60d`
- `downside_vol_20d`
- `atr_14`
- `parkinson_vol_20d`
- `volatility_ratio_20_60`
- `max_drawdown_60d`
- `tail_loss_20d`

```text
realized_vol_20d = std(log_return, 20) * sqrt(252)
```

### 7.5 거래량·유동성 특징

- `volume_ratio_5_20`
- `value_traded_20d_avg`
- `turnover_20d`
- `amihud_illiquidity_20d`
- `bid_ask_spread_bps`
- `depth_imbalance`
- `zero_volume_days_20d`
- `liquidity_percentile`

```text
Amihud = mean(abs(return_t) / traded_value_t)
```

분모가 0이거나 거래정지 상태면 `MISSING` 처리한다.

### 7.6 시장 폭 특징

- `advance_decline_ratio`
- `advance_decline_line_change_20d`
- `pct_above_sma20`
- `pct_above_sma60`
- `new_high_low_ratio`
- `up_volume_ratio`
- `breadth_thrust`

```text
advance_decline_ratio = advancing / max(declining, 1)
```

유니버스는 해당 시점에 실제 상장되어 있고 거래 가능한 종목만 포함한다. 현재 구성종목을 과거에 소급 적용하지 않는다.

### 7.7 상관관계·분산도 특징

- `average_pairwise_correlation_20d`
- `cross_sectional_return_dispersion_20d`
- `market_beta_60d`
- `sector_concentration`
- `correlation_spike`

상관관계 급등은 분산효과 약화와 시장 스트레스의 보조 지표로 사용한다.

### 7.8 위험선호·거시 특징

- `krw_usd_return_5d`
- `yield_change_5d`
- `equity_bond_relative_momentum`
- `large_small_relative_strength`
- `kospi_kosdaq_relative_strength`
- `foreign_flow_zscore`
- `institution_flow_zscore`

원천 데이터 이용 가능성이 불안정한 특징은 v1에서 `OPTIONAL`로 표시하며, 결측 시 국면 판정 전체를 실패시키지 않는다.

---

## 8. 특징량 계산 알고리즘

### 8.1 계산 순서

```text
1. dataset snapshot resolve
2. point-in-time cutoff 적용
3. 종목 master·거래상태 결합
4. 기업행동 보정
5. canonical market frame 생성
6. warmup 검증
7. 개별 특징 계산
8. cross-sectional 특징 계산
9. 품질 검증
10. feature snapshot 저장 및 잠금
11. regime 계산
12. lineage·audit 기록
```

### 8.2 의사코드

```python
def build_feature_snapshot(request, repositories, registry, policy):
    datasets = repositories.data.resolve_snapshots(
        market=request.market,
        as_of=request.as_of,
        cutoff=request.cutoff,
        required=registry.required_inputs(request.feature_set_version),
    )

    frame = repositories.data.load_point_in_time_frame(
        snapshots=datasets,
        available_before=request.cutoff,
    )

    frame = apply_instrument_membership(frame, request.as_of)
    frame = apply_corporate_actions(frame, datasets.corporate_actions)

    values = []
    for definition in registry.ordered(request.feature_set_version):
        value = calculate_feature(definition, frame, values, policy)
        values.append(validate_feature(value, definition, policy))

    snapshot = persist_immutable_snapshot(
        values=values,
        inputs=datasets,
        feature_set_version=request.feature_set_version,
        policy_version=policy.version,
        as_of=request.as_of,
    )
    return snapshot
```

### 8.3 Cross-sectional 계산

횡단면 순위와 z-score는 해당 시점의 eligible universe에서만 계산한다.

```text
eligible = listed
        AND not_delisted
        AND not_suspended_by_policy
        AND sufficient_history
        AND valid_price
```

극단값은 정책에 따라 winsorize한다. 원본값은 보존하고 변환값은 별도 특징으로 저장한다.

---

## 9. Feature Quality Model

### 9.1 품질 상태

- `VALID`: 입력·범위·시점·warmup 모두 정상
- `DEGRADED`: 일부 비핵심 입력 대체 또는 지연
- `MISSING`: 계산 불가
- `INVALID`: 미래값, 범위 오류, 비정상 스파이크 등 위반

### 9.2 품질 검사

- source snapshot 잠금 여부
- `available_at <= cutoff`
- 가격 음수·0 오류
- 거래량 음수 오류
- 고가 < 저가 오류
- 비정상 수익률과 기업행동 미반영 여부
- stale price 지속일
- warmup 부족
- 횡단면 표본 수 부족
- 값 범위와 단위 검증
- 동일 snapshot 재계산 hash 일치

### 9.3 품질 게이트

```text
critical_feature_valid_ratio >= 0.98
market_universe_coverage      >= 0.95
breadth_sample_size           >= policy.minimum_breadth_count
future_value_violation_count  = 0
```

LIVE에서 future-value 위반은 CRITICAL이며 즉시 실행을 차단한다.

---

## 10. 시장 국면 모델 v1

### 10.1 국면 정의

#### BULL

- 중장기 추세 양호
- 시장 폭 확산
- 변동성 정상 또는 하락
- 유동성 정상

#### BEAR

- 중장기 추세 하락
- 시장 폭 악화
- drawdown 확대
- 하락 모멘텀 지속

#### SIDEWAY

- 추세 점수 중립
- 방향성 낮음
- 변동성 정상
- 시장 폭 혼조

#### HIGH_VOL

- 실현 변동성 급등
- tail loss 또는 drawdown 확대
- 상관관계 급등 가능

#### LIQUIDITY_STRESS

- 거래대금 감소 또는 spread 확대
- 시장 폭 급락
- 다수 종목 거래 비정상
- 환율·자금흐름 스트레스 동반 가능

#### RECOVERY

- BEAR/HIGH_VOL 이후 추세와 폭이 회복되지만 장기 추세 확인 전 상태

### 10.2 구성 점수

각 점수는 `[-1, 1]`로 정규화한다.

```text
trend_score
breadth_score
volatility_score
liquidity_score
risk_appetite_score
correlation_stress_score
```

예시 규칙:

```text
bull_score =
    0.35 * positive(trend_score)
  + 0.25 * positive(breadth_score)
  + 0.15 * positive(risk_appetite_score)
  + 0.15 * positive(-volatility_score)
  + 0.10 * positive(liquidity_score)

bear_score =
    0.40 * positive(-trend_score)
  + 0.25 * positive(-breadth_score)
  + 0.20 * positive(drawdown_score)
  + 0.15 * positive(-risk_appetite_score)

high_vol_score =
    0.55 * positive(volatility_score)
  + 0.20 * positive(tail_risk_score)
  + 0.15 * positive(correlation_stress_score)
  + 0.10 * positive(drawdown_score)
```

### 10.3 확률 변환

```python
from math import exp


def softmax(scores: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    m = max(scores.values())
    e = {k: exp((v - m) / temperature) for k, v in scores.items()}
    total = sum(e.values())
    return {k: v / total for k, v in e.items()}
```

v1은 설명 가능한 rule-based score를 기본으로 한다. 추후 통계 모델 또는 ML 모델을 추가해도 동일 `RegimeResult` 계약을 사용한다.

---

## 11. 국면 상태 머신

단일 시점 점수만으로 상태를 즉시 변경하면 잦은 전환이 발생한다. 이를 방지하기 위해 hysteresis와 최소 지속기간을 적용한다.

```text
candidate probability >= enter_threshold
AND current probability <= exit_threshold
AND candidate persists for N observations
```

기본 정책 예시:

```yaml
regime_transition:
  enter_threshold: 0.55
  exit_threshold: 0.35
  minimum_confidence: 0.15
  confirmation_periods:
    DAILY: 2
    INTRADAY: 3
  minimum_duration:
    DAILY: 3
  emergency_override:
    HIGH_VOL: 0.80
    LIQUIDITY_STRESS: 0.75
```

HIGH_VOL 또는 LIQUIDITY_STRESS가 emergency threshold를 넘으면 확인기간 없이 즉시 전환할 수 있다.

### 의사코드

```python
def resolve_state(previous, probabilities, policy, history):
    candidate = max(probabilities, key=probabilities.get)
    confidence = probabilities[candidate] - sorted(probabilities.values())[-2]

    if candidate in policy.emergency_override:
        if probabilities[candidate] >= policy.emergency_override[candidate]:
            return candidate, "EMERGENCY_OVERRIDE"

    if confidence < policy.minimum_confidence:
        return previous.state if previous else "UNKNOWN", "LOW_CONFIDENCE"

    if previous and candidate == previous.state:
        return candidate, "STATE_MAINTAINED"

    if not persisted(candidate, history, policy.confirmation_periods):
        return previous.state if previous else "UNKNOWN", "AWAITING_CONFIRMATION"

    if previous and not minimum_duration_met(previous, policy.minimum_duration):
        return previous.state, "MINIMUM_DURATION"

    return candidate, "CONFIRMED_TRANSITION"
```

---

## 12. 데이터베이스 설계

### 12.1 `feature_definition`

```sql
CREATE TABLE feature_definition (
    feature_name          TEXT NOT NULL,
    feature_set_version   TEXT NOT NULL,
    entity_type           TEXT NOT NULL,
    value_type            TEXT NOT NULL,
    frequency             TEXT NOT NULL,
    lookback              INTEGER NOT NULL,
    warmup_period         INTEGER NOT NULL,
    formula_version       TEXT NOT NULL,
    expression_json       TEXT NOT NULL,
    required_inputs_json  TEXT NOT NULL,
    missing_policy        TEXT NOT NULL,
    is_critical           INTEGER NOT NULL,
    status                TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    PRIMARY KEY (feature_name, feature_set_version)
);
```

### 12.2 `feature_snapshot`

```sql
CREATE TABLE feature_snapshot (
    feature_snapshot_id   TEXT PRIMARY KEY,
    market_id             TEXT NOT NULL,
    frequency             TEXT NOT NULL,
    as_of                  TEXT NOT NULL,
    cutoff_at              TEXT NOT NULL,
    feature_set_version    TEXT NOT NULL,
    policy_version         TEXT NOT NULL,
    code_version           TEXT NOT NULL,
    input_manifest_hash    TEXT NOT NULL,
    snapshot_hash          TEXT NOT NULL,
    quality_status         TEXT NOT NULL,
    coverage_ratio         TEXT NOT NULL,
    state                  TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    locked_at              TEXT,
    UNIQUE (market_id, frequency, as_of, feature_set_version, input_manifest_hash)
);
```

### 12.3 `feature_value`

```sql
CREATE TABLE feature_value (
    feature_snapshot_id   TEXT NOT NULL,
    feature_name          TEXT NOT NULL,
    entity_type           TEXT NOT NULL,
    entity_id             TEXT NOT NULL,
    as_of                  TEXT NOT NULL,
    available_at           TEXT NOT NULL,
    value_decimal          TEXT,
    value_text             TEXT,
    quality_status         TEXT NOT NULL,
    quality_reason         TEXT,
    definition_version     TEXT NOT NULL,
    source_refs_json       TEXT NOT NULL,
    metadata_json          TEXT NOT NULL,
    PRIMARY KEY (
        feature_snapshot_id,
        feature_name,
        entity_type,
        entity_id
    ),
    FOREIGN KEY (feature_snapshot_id)
        REFERENCES feature_snapshot(feature_snapshot_id)
);
```

### 12.4 `regime_snapshot`

```sql
CREATE TABLE regime_snapshot (
    regime_snapshot_id    TEXT PRIMARY KEY,
    feature_snapshot_id   TEXT NOT NULL,
    market_id             TEXT NOT NULL,
    as_of                  TEXT NOT NULL,
    state                  TEXT NOT NULL,
    previous_state         TEXT,
    confidence             TEXT NOT NULL,
    probabilities_json     TEXT NOT NULL,
    component_scores_json  TEXT NOT NULL,
    transition_reason      TEXT NOT NULL,
    model_version          TEXT NOT NULL,
    policy_version         TEXT NOT NULL,
    snapshot_hash          TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    locked_at              TEXT NOT NULL,
    FOREIGN KEY (feature_snapshot_id)
        REFERENCES feature_snapshot(feature_snapshot_id)
);
```

### 12.5 `feature_quality_issue`

```sql
CREATE TABLE feature_quality_issue (
    issue_id               TEXT PRIMARY KEY,
    feature_snapshot_id    TEXT NOT NULL,
    severity               TEXT NOT NULL,
    issue_type             TEXT NOT NULL,
    feature_name           TEXT,
    entity_id              TEXT,
    expected_value         TEXT,
    observed_value         TEXT,
    details_json           TEXT NOT NULL,
    detected_at            TEXT NOT NULL,
    resolution_status      TEXT NOT NULL,
    FOREIGN KEY (feature_snapshot_id)
        REFERENCES feature_snapshot(feature_snapshot_id)
);
```

### 12.6 주요 인덱스

```sql
CREATE INDEX idx_feature_value_lookup
ON feature_value(entity_type, entity_id, feature_name, as_of);

CREATE INDEX idx_feature_snapshot_asof
ON feature_snapshot(market_id, frequency, as_of);

CREATE INDEX idx_regime_market_asof
ON regime_snapshot(market_id, as_of);
```

---

## 13. Repository 인터페이스

```python
from typing import Protocol, Iterable
from datetime import datetime


class FeatureRepository(Protocol):
    def save_snapshot(self, snapshot) -> None: ...
    def save_values(self, values: Iterable[FeatureValue]) -> None: ...
    def lock_snapshot(self, feature_snapshot_id: str) -> None: ...
    def get_snapshot(self, feature_snapshot_id: str): ...
    def get_latest_snapshot(
        self,
        market_id: str,
        as_of: datetime,
        feature_set_version: str,
    ): ...
    def query_values(
        self,
        feature_snapshot_id: str,
        entity_ids: list[str],
        feature_names: list[str],
    ) -> list[FeatureValue]: ...


class RegimeRepository(Protocol):
    def save(self, result: RegimeResult) -> None: ...
    def get_latest(self, market_id: str, as_of: datetime) -> RegimeResult | None: ...
    def get_history(self, market_id: str, before: datetime, limit: int): ...
```

---

## 14. 서비스 코드 초안

```python
class MarketRegimeFeatureService:
    def __init__(
        self,
        data_reader,
        feature_repository,
        regime_repository,
        definition_registry,
        policy_resolver,
        lineage_publisher,
        audit_publisher,
    ):
        self.data_reader = data_reader
        self.feature_repository = feature_repository
        self.regime_repository = regime_repository
        self.definition_registry = definition_registry
        self.policy_resolver = policy_resolver
        self.lineage_publisher = lineage_publisher
        self.audit_publisher = audit_publisher

    def execute(self, request):
        policy = self.policy_resolver.resolve(
            policy_snapshot_id=request.policy_snapshot_id,
            engine="MARKET_REGIME_FEATURE",
        )

        existing = self.feature_repository.find_by_idempotency_key(
            request.idempotency_key
        )
        if existing:
            return existing

        snapshot = build_feature_snapshot(
            request=request,
            repositories=self,
            registry=self.definition_registry,
            policy=policy,
        )

        assert snapshot.quality_status in policy.allowed_quality_statuses
        self.feature_repository.lock_snapshot(snapshot.feature_snapshot_id)

        previous = self.regime_repository.get_latest(
            request.market_id, request.as_of
        )
        history = self.regime_repository.get_history(
            request.market_id, request.as_of, limit=policy.history_limit
        )

        scores = calculate_regime_scores(snapshot, policy)
        probabilities = score_to_probabilities(scores, policy.temperature)
        state, reason = resolve_state(previous, probabilities, policy, history)

        result = create_regime_result(
            snapshot=snapshot,
            previous=previous,
            state=state,
            reason=reason,
            probabilities=probabilities,
            scores=scores,
            policy=policy,
        )
        self.regime_repository.save(result)
        self.lineage_publisher.publish(snapshot, result)
        self.audit_publisher.publish("REGIME_CALCULATED", result)
        return result
```

---

## 15. API 계약

### 15.1 Snapshot 생성

```http
POST /v1/features/snapshots
```

```json
{
  "market_id": "KRX",
  "frequency": "DAILY",
  "as_of": "2026-07-20T15:30:00+09:00",
  "cutoff_at": "2026-07-20T16:00:00+09:00",
  "feature_set_version": "kr-equity-daily-v1",
  "policy_snapshot_id": "POLICY-20260720-001",
  "data_snapshot_ids": ["DATA-KRX-20260720-001"],
  "mode": "PAPER",
  "idempotency_key": "KRX:DAILY:2026-07-20:v1"
}
```

### 15.2 종목 특징 조회

```http
GET /v1/features/snapshots/{snapshot_id}/entities/{instrument_id}
```

### 15.3 최신 국면 조회

```http
GET /v1/regimes/latest?market_id=KRX&as_of=2026-07-20T16:00:00%2B09:00
```

모든 응답은 `feature_snapshot_id`, `regime_snapshot_id`, `policy_version`, `data_snapshot_ids`, `snapshot_hash`를 포함한다.

---

## 16. Orchestrator 통합

```text
Scheduler Trigger
  ↓
RunRequest
  ↓
Data Snapshot Resolve
  ↓
Feature Snapshot Build
  ↓
Feature Quality Gate
  ↓
Regime Calculate
  ↓
Signal Engine
  ↓
Risk Engine
  ↓
Decision Engine
```

Run State 예시:

```text
FEATURE_INPUT_RESOLVED
FEATURE_CALCULATING
FEATURE_VALIDATING
FEATURE_SNAPSHOT_LOCKED
REGIME_CALCULATING
REGIME_COMPLETED
```

실패 상태:

```text
FEATURE_INPUT_MISSING
FEATURE_POINT_IN_TIME_VIOLATION
FEATURE_QUALITY_FAILED
REGIME_LOW_CONFIDENCE
REGIME_FAILED
```

`REGIME_LOW_CONFIDENCE`는 반드시 run 실패는 아니다. 정책에 따라 `UNKNOWN` 또는 이전 국면 유지로 진행할 수 있다.

---

## 17. Signal·Risk·Decision 연계 정책

### 17.1 Signal Engine

- BULL: 추세·모멘텀 신호 가중치 상향 가능
- SIDEWAY: mean-reversion 또는 낮은 확신
- BEAR: long 신규 신호 threshold 상향
- HIGH_VOL: 신호 유효기간 단축, 변동성 조정
- LIQUIDITY_STRESS: 저유동 종목 신호 폐기

### 17.2 Risk Engine

- HIGH_VOL: 종목당 최대 비중 축소
- LIQUIDITY_STRESS: 신규 진입 차단 또는 주문 크기 대폭 축소
- BEAR: gross exposure 제한
- UNKNOWN: Preservation Mode 적용

### 17.3 Decision Engine

Decision은 반드시 사용한 `feature_snapshot_id`와 `regime_snapshot_id`를 저장한다.

```python
@dataclass(frozen=True)
class DecisionContext:
    feature_snapshot_id: str
    regime_snapshot_id: str
    regime_state: str
    regime_confidence: Decimal
    policy_snapshot_id: str
```

---

## 18. 가상투자 적용

ADE 일일 가상투자에서 다음 규칙을 사용한다.

```text
초기자금          10,000,000원
최소 현금         10%
종목당 최대 비중  10%
신규 매수         하루 최대 1종목
레버리지          없음
```

Market Regime & Feature Engine 추가 후 후보 평가에 다음 항목을 포함한다.

- 시장 국면과 신뢰도
- 종목 추세·모멘텀·변동성·유동성 특징
- 시장 대비 상대강도
- 횡단면 순위
- 특징량 품질

기본 차단 예시:

```text
regime = LIQUIDITY_STRESS → 신규 매수 NO_ACTION
regime = UNKNOWN and confidence low → 신규 매수 NO_ACTION
feature_quality != VALID → 해당 종목 제외
value_traded_20d_avg below threshold → 해당 종목 제외
realized_vol_20d above limit → Risk 차단
```

본 엔진만 추가된 상태에서는 최종 종목 선택 알고리즘이 완성되지 않았으므로, Signal/Ranking Engine이 구체화되기 전까지 국면과 특징량은 위험 필터와 설명 근거로 우선 사용한다.

---

## 19. 감사·계보

모든 결과는 다음 연결을 유지한다.

```text
Raw Dataset Version
 → Normalized Dataset
 → Feature Definition Version
 → Feature Value
 → Feature Snapshot
 → Regime Snapshot
 → Signal
 → Risk Assessment
 → Decision
```

감사 이벤트:

- `FEATURE_BUILD_STARTED`
- `FEATURE_BUILD_COMPLETED`
- `FEATURE_QUALITY_DEGRADED`
- `FEATURE_POINT_IN_TIME_VIOLATION`
- `FEATURE_SNAPSHOT_LOCKED`
- `REGIME_CALCULATED`
- `REGIME_TRANSITIONED`
- `REGIME_LOW_CONFIDENCE`
- `FEATURE_BACKFILL_REQUESTED`
- `FEATURE_RESTATEMENT_CREATED`

기존 snapshot은 수정하지 않는다. 데이터 정정 후 재계산은 새 snapshot과 새 lineage를 생성한다.

---

## 20. 성능·운영 목표

### Daily v1

- KRX 3,000 종목 기준 일봉 특징 계산 5분 이내
- 핵심 시장 국면 계산 10초 이내
- 단일 종목 특징 조회 p95 100ms 이하
- snapshot 재생 시 hash 100% 일치
- feature coverage 95% 이상

### 운영 지표

- 계산 지연시간
- 특징별 결측률
- universe coverage
- DEGRADED/INVALID 비율
- 국면 전환 빈도
- 국면 평균 지속기간
- snapshot hash mismatch
- future-value violation
- data staleness

---

## 21. 실패 처리

### 입력 데이터 누락

- 핵심 시장 지수 누락: 실행 실패 또는 `UNKNOWN`
- 일부 종목 누락: coverage 계산 후 정책 판단
- breadth 유니버스 부족: breadth 점수 비활성화, confidence 하향

### 계산 장애

- 특징별 독립 계산 단위를 사용하여 비핵심 특징 실패가 전체를 중단하지 않도록 한다.
- 핵심 특징 실패는 quality gate에서 차단한다.
- 동일 idempotency key 재시도는 기존 성공 snapshot을 반환한다.

### DB 장애

- snapshot과 feature values는 하나의 논리적 트랜잭션으로 저장한다.
- lock 전 실패한 snapshot은 `ABORTED` 처리한다.
- lock 후에는 수정 금지다.

### 모델 또는 정책 오류

- 승인되지 않은 feature_set version의 LIVE 사용 금지
- threshold 오류로 국면 전환 과다 발생 시 이전 승인 버전으로 rollback
- rollback도 새 정책 snapshot으로 감사 기록한다.

---

## 22. 테스트 계획

### 22.1 단위 테스트

- 수익률 계산
- SMA/EMA/MACD
- RSI
- realized volatility
- ATR
- Amihud illiquidity
- market breadth
- 횡단면 percentile와 z-score
- winsorization
- score normalization
- softmax probability
- hysteresis 상태 전환
- minimum duration
- emergency override

### 22.2 시점 정합성 테스트

- cutoff 이후 도착 데이터 제외
- 당일 종가를 당일 장중 의사결정에 사용하지 않음
- 수정 데이터의 available_at 반영
- 상장 전 종목 제외
- 폐지 후 종목 제외
- 현재 지수 구성종목을 과거에 소급하지 않음
- 기업행동 발표·적용 시점 구분

### 22.3 데이터 품질 테스트

- 음수 거래량
- high < low
- stale price
- 거래정지
- 분할 미반영 급락
- warmup 부족
- 결측률 threshold
- 표본 수 부족
- 극단값 처리

### 22.4 DB 테스트

- 동일 idempotency key 중복 차단
- locked snapshot 수정 차단
- snapshot과 values atomicity
- hash 일치
- 인덱스 조회 성능
- 재처리 시 새 snapshot 생성

### 22.5 통합 테스트

- Data Snapshot → Feature → Regime → Signal
- Scheduler 장 마감 trigger
- Backtest historical replay
- PAPER 실시간 snapshot
- Audit lineage 완전성
- Risk Engine의 HIGH_VOL 비중 축소
- Decision에 snapshot ID 저장

### 22.6 회귀 테스트

고정된 golden dataset에 대해 다음을 검증한다.

```text
input dataset hash
feature snapshot hash
regime probabilities
final regime state
quality issues
```

feature formula 또는 policy 변경 시 기대 결과 변경을 명시적으로 승인한다.

### 22.7 속성 기반 테스트

- 상수 가격 시 수익률과 변동성은 0
- 가격에 동일 상수를 곱해도 수익률 특징은 불변
- 미래 데이터 추가가 과거 snapshot을 변경하지 않음
- 동일 입력 순서 변경이 결과를 변경하지 않음
- probability 합계는 1
- confidence 범위는 `[0, 1]`

### 22.8 실패 주입 테스트

- 데이터 공급 지연
- DB write 중단
- snapshot lock 전 process crash
- 일부 feature worker timeout
- 잘못된 기업행동 데이터
- clock skew
- 중복 trigger
- 정책 서비스 장애

### 22.9 성능 테스트

- 3,000 종목 × 250일 warmup
- 100개 특징량 일괄 계산
- 10년 backfill
- 동시 시장 3개 처리
- 단일 종목·다중 종목 조회 부하

---

## 23. 대표 테스트 코드

```python
from decimal import Decimal


def test_future_data_is_never_used(feature_service, fake_data):
    fake_data.add(
        event_time="2026-07-20T15:30:00+09:00",
        available_at="2026-07-20T16:10:00+09:00",
        close="100000",
    )

    result = feature_service.execute(make_request(
        as_of="2026-07-20T15:30:00+09:00",
        cutoff="2026-07-20T16:00:00+09:00",
    ))

    assert result.find("close").quality_status == "MISSING"


def test_regime_hysteresis_keeps_previous_state():
    previous = regime("BULL", duration=10)
    probabilities = {
        "BULL": Decimal("0.42"),
        "SIDEWAY": Decimal("0.48"),
        "BEAR": Decimal("0.10"),
    }

    state, reason = resolve_state(
        previous, probabilities, default_policy(), history=[]
    )

    assert state == "BULL"
    assert reason in {"LOW_CONFIDENCE", "AWAITING_CONFIRMATION"}


def test_high_vol_emergency_override():
    probabilities = {
        "BULL": Decimal("0.03"),
        "BEAR": Decimal("0.08"),
        "SIDEWAY": Decimal("0.04"),
        "HIGH_VOL": Decimal("0.85"),
    }

    state, reason = resolve_state(
        regime("SIDEWAY", duration=5),
        probabilities,
        default_policy(),
        history=[],
    )

    assert state == "HIGH_VOL"
    assert reason == "EMERGENCY_OVERRIDE"
```

---

## 24. 보안·권한

- 원천 데이터 credential 저장 금지
- feature definition 변경 권한 분리
- LIVE 활성 feature set은 승인 워크플로 필요
- snapshot lock 해제 API 제공 금지
- 수동 backfill과 restatement는 감사 대상
- 외부 export 시 계좌·사용자 식별정보 제외
- feature 값은 투자전략 지적재산으로 접근 제어 가능

---

## 25. 구현 순서

### Phase 1 — Daily Feature Core

- KRX 일봉 canonical frame
- 수익률·SMA·모멘텀·변동성
- 거래대금·기본 유동성
- feature definition registry
- immutable snapshot
- SQLite/PostgreSQL repository

### Phase 2 — Market Regime v1

- trend/breadth/volatility/liquidity score
- rule-based probability
- hysteresis state machine
- Signal/Risk 연계
- 가상투자 보고서 국면 표시

### Phase 3 — Point-in-Time 강화

- available_at 기반 join
- historical constituent universe
- 기업행동 정정
- backfill/replay
- golden dataset regression

### Phase 4 — Intraday·Advanced

- 분봉·호가 특징
- intraday liquidity stress
- cross-asset 특징
- 통계/ML regime model
- feature store 최적화
- 분산 계산

---

## 26. 완료 기준

다음 조건을 모두 충족하면 v1 설계·구현이 완료된 것으로 본다.

- 동일 snapshot 입력에서 동일 feature hash 생성
- 미래 데이터 참조가 자동 차단됨
- BACKTEST와 PAPER/LIVE 계산 코어가 동일함
- 3,000종목 일봉 특징량 계산 성능 목표 충족
- 핵심 특징 품질 상태와 결측 사유 저장
- feature definition version과 policy version 추적 가능
- BULL/BEAR/SIDEWAY/HIGH_VOL/LIQUIDITY_STRESS 판정 가능
- hysteresis와 emergency transition 테스트 통과
- Signal/Risk/Decision이 동일 snapshot ID 사용
- 데이터 정정 시 기존 snapshot을 수정하지 않고 새 snapshot 생성
- 가상투자 일일 보고서에 국면·특징량·차단 사유 표시 가능
- Audit에서 raw dataset부터 Decision까지 역추적 가능

---

## 27. 다음 설계 대상

다음 엔진은 **Signal Generation & Ranking Engine v1**로 한다.

이 엔진은 Market Regime & Feature Engine이 생성한 특징량을 사용하여 종목별 매수·보유·매도 신호를 계산하고, 규칙 기반 신호와 모델 기반 신호를 결합해 후보 종목을 순위화한다. 신호 강도, 신뢰도, 유효기간, 국면 적합성, 설명 가능성, 중복·상충 신호 처리, 가상투자용 하루 최대 1종목 후보 선정 규칙을 구체화한다.
