# 43. Market Regime Adaptation & Dynamic Signal Weighting Engine v1

## 1. 문서 목적

이 문서는 AI Decision Engine(ADE)의 `Market Regime Adaptation & Dynamic Signal Weighting Engine v1` 설계를 정의한다.

20번 Market Regime & Feature Engine은 시장 상태를 관측·분류하고, 42번 Signal Integration Engine은 종목별 Fundamental/Valuation/Expectations/Market Behavior를 Alpha·Confidence·Candidate로 통합한다. 43번 엔진은 이 둘 사이의 정책 계층으로서 다음 질문에 답한다.

```text
현재 시장 국면에서 어떤 Signal Family를 더 신뢰해야 하는가?
어떤 신호는 감쇠해야 하는가?
시장 국면이 나빠질수록 Candidate 통과 기준을 얼마나 강화해야 하는가?
국면 변화가 너무 잦을 때 가중치가 흔들리지 않도록 어떻게 안정화할 것인가?
위기 국면에서 신규매수를 완전히 차단할 것인가, 비중만 줄일 것인가?
동일한 시장 데이터와 정책으로 항상 동일한 가중치가 생성되는가?
```

본 엔진은 종목의 BUY/SELL을 직접 결정하지 않는다. 또한 시장 국면 자체를 새로 분류하지 않는다.

출력은 42번 Signal Integration, 22번 Portfolio Risk & Exposure, 23번 Decision & Position Sizing, 30번 Explainability, 31번 Paper Trading, Backtest가 소비한다.

---

## 2. 기존 엔진과의 책임 경계

### 2.1 20번과의 관계

```text
20 Market Regime & Feature Engine
→ 시장 상태를 관측하고 Regime Snapshot 생성

43 Market Regime Adaptation Engine
→ Regime Snapshot을 정책 파라미터로 변환

42 Signal Integration Engine
→ 변환된 동적 가중치와 임계치를 이용해 종목별 신호 통합
```

43번은 20번의 분류 결과를 수정하지 않는다.

### 2.2 42번과의 관계

42번의 기본 Signal Family는 다음과 같다.

- Business Quality
- Valuation
- Expectations
- Market Behavior

43번은 이 family들의 기본 가중치를 현재 Regime에 맞게 조정한다.

예:

```text
NORMAL / RISK_ON
Quality      25%
Valuation    25%
Expectations 20%
Behavior     30%

HIGH_VOLATILITY
Quality      30%
Valuation    20%
Expectations 15%
Behavior     35%

CRISIS
신규 진입 차단
```

단, 위 숫자는 초기 PAPER 정책 예시일 뿐이며 코드 상수가 아니다.

### 2.3 22/23번과의 관계

43번은 다음과 같은 위험예산 배율을 출력할 수 있다.

```text
risk_budget_multiplier
position_size_multiplier
new_entry_cap
candidate_threshold_delta
```

그러나 실제 종목별 위험 계산과 최종 수량 결정은 각각 22번과 23번의 책임이다.

---

## 3. 설계 목표

1. Regime별 Signal Family 가중치 조정
2. Regime별 Candidate 최소 Alpha/Confidence/Adjusted Signal 임계치 조정
3. 신규 진입 허용/제한/차단 상태 생성
4. Risk Budget / Position Size 배율 생성
5. Regime 전환 시 hysteresis 및 confirmation 적용
6. 급격한 가중치 변화 제한
7. Regime Confidence 반영
8. 충돌하는 Regime 증거 처리
9. Point-in-Time 정책 재현성 확보
10. Backtest와 Paper Trading에서 동일 규칙 사용
11. 정책 버전·입력 Snapshot·출력 hash 감사 가능성 확보
12. 미래정보 및 현재 Regime의 과거 소급 사용 차단

---

## 4. 비목표

본 엔진은 다음을 수행하지 않는다.

- 가격 데이터 수집
- 변동성 직접 계산
- KOSPI 추세 직접 계산
- 시장 Regime 원천 분류
- 종목별 Factor 계산
- 종목별 Alpha 계산
- 포트폴리오 VaR 계산
- 종목별 포지션 비중 확정
- 주문 생성
- 거래 실행
- 사후 수익률을 보고 Regime을 재작성

---

## 5. 상위 아키텍처

```text
Market Data Finalization
        ↓
20 Market Regime & Feature Engine
        ↓
Immutable Regime Snapshot
   ├─ primary_regime
   ├─ secondary_regime
   ├─ volatility_state
   ├─ trend_state
   ├─ breadth_state
   ├─ liquidity_state
   ├─ stress_state
   ├─ regime_confidence
   └─ evidence_hash
        ↓
43 Regime Adaptation Engine
   ├─ Input Contract Gate
   ├─ Transition/Hysteresis Resolver
   ├─ Policy Profile Selector
   ├─ Weight Adaptation
   ├─ Threshold Adaptation
   ├─ Risk Budget Multipliers
   ├─ Change-Rate Limiter
   ├─ Safety Override
   └─ Manifest / Hash
        ↓
Regime Adaptation Snapshot
        ├─────────────→ 42 Signal Integration
        ├─────────────→ 22 Portfolio Risk
        ├─────────────→ 23 Decision / Sizing
        └─────────────→ 30 Explainability
```

---

## 6. Regime 상태 모델

v1은 20번 엔진이 최소 다음 canonical state를 제공한다고 가정한다.

### 6.1 Primary Regime

```text
RISK_ON
NORMAL
LATE_CYCLE
RISK_OFF
CRISIS
RECOVERY
UNKNOWN
```

### 6.2 Volatility State

```text
LOW
NORMAL
HIGH
EXTREME
UNKNOWN
```

### 6.3 Trend State

```text
STRONG_UP
UP
SIDEWAYS
DOWN
STRONG_DOWN
UNKNOWN
```

### 6.4 Market Breadth State

```text
BROAD
NEUTRAL
NARROW
CAPITULATION
UNKNOWN
```

### 6.5 Liquidity / Stress State

```text
NORMAL
TIGHTENING
STRESSED
DISLOCATED
UNKNOWN
```

Regime classification schema가 20번에서 바뀌면 adapter를 통해 43번 canonical state로 변환한다.

---

## 7. 입력 계약

```python
@dataclass(frozen=True)
class RegimeSnapshotInput:
    snapshot_id: str
    evaluation_time: datetime
    primary_regime: str
    volatility_state: str
    trend_state: str
    breadth_state: str
    liquidity_state: str
    stress_state: str
    regime_confidence: Decimal
    known_at: datetime
    evidence_hash: str
```

필수 검증:

```text
known_at <= evaluation_time
0 <= regime_confidence <= 1
snapshot_id not null
evidence_hash not null
policy.known_at <= evaluation_time
```

위반 시 adaptation을 생성하지 않는다.

---

## 8. 출력 계약

```python
@dataclass(frozen=True)
class RegimeAdaptationSnapshot:
    adaptation_id: str
    evaluation_time: datetime
    source_regime_snapshot_id: str
    effective_regime: str
    transition_state: str
    signal_family_weights: Mapping[str, Decimal]
    alpha_threshold: Decimal
    confidence_threshold: Decimal
    adjusted_signal_threshold: Decimal
    risk_budget_multiplier: Decimal
    position_size_multiplier: Decimal
    new_entry_mode: str
    max_new_entries_multiplier: Decimal
    confidence_multiplier: Decimal
    policy_version: str
    reason_codes: tuple[str, ...]
    evidence_hash: str
    snapshot_hash: str
```

`new_entry_mode`는 다음 중 하나이다.

```text
NORMAL
TIGHTENED
LIMITED
BLOCKED
```

---

## 9. 기본 정책 프로필

정책은 Configuration & Policy Engine의 불변 Snapshot으로 관리한다.

초기 PAPER 정책 예:

| Effective Regime | Quality | Valuation | Expectations | Behavior | Alpha Min | Confidence Min | Adj Signal Min | Risk Budget | Position Size | Entry Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| RISK_ON | 0.20 | 0.20 | 0.20 | 0.40 | 62 | 58 | 52 | 1.00 | 1.00 | NORMAL |
| NORMAL | 0.25 | 0.25 | 0.20 | 0.30 | 65 | 60 | 55 | 1.00 | 1.00 | NORMAL |
| LATE_CYCLE | 0.30 | 0.25 | 0.15 | 0.30 | 68 | 65 | 58 | 0.85 | 0.85 | TIGHTENED |
| RECOVERY | 0.25 | 0.20 | 0.20 | 0.35 | 70 | 65 | 60 | 0.70 | 0.70 | LIMITED |
| RISK_OFF | 0.35 | 0.20 | 0.10 | 0.35 | 75 | 70 | 65 | 0.50 | 0.50 | LIMITED |
| CRISIS | - | - | - | - | - | - | - | 0.00 | 0.00 | BLOCKED |

이 표는 v1 초기값이며 검증과 승격 절차 없이 LIVE 정책으로 사용해서는 안 된다.

---

## 10. 핵심 알고리즘

### 10.1 정책 프로필 선택

```python
def select_profile(effective_regime: str, policy: Policy) -> RegimeProfile:
    profile = policy.profiles.get(effective_regime)
    if profile is None:
        raise PolicyError("REGIME_PROFILE_NOT_FOUND")
    return profile
```

UNKNOWN을 NORMAL로 자동 대체하지 않는다.

```text
UNKNOWN
→ 신규 진입 TIGHTENED 또는 BLOCKED
→ 정책에 명시된 fallback만 허용
```

### 10.2 Signal Weight Adaptation

기본 가중치 `w_base`와 Regime target `w_regime`이 있을 때 즉시 교체하지 않고 전환 비율 `lambda`를 사용한다.

```text
w_target = regime profile weight

w_effective
= (1 - lambda) × w_previous
+ lambda × w_target
```

`lambda`는 Regime confidence와 transition maturity에 의해 결정된다.

예:

```text
lambda
= base_transition_rate
× regime_confidence
× confirmation_factor
```

각 family weight는 다음 불변식을 만족해야 한다.

```text
0 <= weight <= family_weight_cap
sum(weights) = 1 within tolerance
```

### 10.3 Regime Confidence 반영

낮은 신뢰도의 Regime에서 과도하게 가중치를 바꾸지 않는다.

```text
regime_confidence < 0.50
→ previous stable profile 유지 우선
→ REGIME_CONFIDENCE_LOW

0.50 <= confidence < 0.70
→ partial adaptation

confidence >= 0.70
→ normal adaptation 허용
```

단, crisis safety override는 confidence와 무관하게 적용될 수 있다. 예를 들어 공식 시장중단, 데이터 dislocation, extreme stress hard trigger가 별도 정책으로 들어온 경우다.

### 10.4 Hysteresis

Regime이 하루마다 RISK_ON ↔ NORMAL ↔ RISK_OFF로 흔들리는 것을 막는다.

진입과 해제 임계치를 다르게 둔다.

```text
RISK_OFF 진입
stress_score >= 0.70 for N confirmations

RISK_OFF 해제
stress_score <= 0.45 for M confirmations
```

N과 M은 정책 값이다.

### 10.5 Confirmation Window

일반 Regime 전환은 연속 거래일 또는 연속 확정 Snapshot 확인이 필요하다.

초기 PAPER 예:

```text
NORMAL → RISK_OFF : 2 confirmations
RISK_OFF → NORMAL : 3 confirmations
RISK_OFF → CRISIS : hard trigger 즉시 가능
CRISIS → RECOVERY : 3 confirmations
RECOVERY → NORMAL : 5 confirmations
```

미래 거래일을 미리 사용하지 않는다.

### 10.6 Threshold Adaptation

42번 Candidate Gate의 기준을 동적으로 조정한다.

```text
alpha_min_effective
= alpha_min_base + alpha_delta_regime

confidence_min_effective
= confidence_min_base + confidence_delta_regime

adjusted_signal_min_effective
= adjusted_signal_min_base + signal_delta_regime
```

예:

```text
NORMAL
Alpha >= 65
Confidence >= 60
Adj Signal >= 55

RISK_OFF
Alpha >= 75
Confidence >= 70
Adj Signal >= 65
```

### 10.7 Risk Budget Multiplier

```text
risk_budget_effective
= base_risk_budget × regime_multiplier
```

단, 43번은 실제 종목 Risk Budget을 할당하지 않고 배율만 제공한다.

초기 예:

```text
RISK_ON  1.00
NORMAL   1.00
LATE     0.85
RECOVERY 0.70
RISK_OFF 0.50
CRISIS   0.00
```

### 10.8 Position Size Multiplier

23번 Decision Engine이 계산한 기본 목표금액에 다음 배율을 전달한다.

```text
regime_adjusted_target
= base_target × position_size_multiplier
```

그 이후 종목 최대비중, 현금 최소비중 등 포트폴리오 제약은 23번이 다시 검증한다.

### 10.9 신규 진입 모드

```text
NORMAL
→ 기존 신규 진입 정책 그대로

TIGHTENED
→ Alpha/Confidence 임계치 강화

LIMITED
→ 임계치 강화 + Risk Budget 축소

BLOCKED
→ 신규 BUY 후보 downstream 전달 금지
```

보유종목의 매도/축소 판단은 BLOCKED 상태에서도 계속 작동해야 한다.

즉:

```text
CRISIS
new BUY = BLOCKED
SELL / REDUCE / FORCE_EXIT = allowed
```

### 10.10 Change-Rate Limiter

하루 사이 Signal family weight가 지나치게 크게 변하는 것을 막는다.

```text
abs(w_t - w_t-1) <= max_daily_weight_change
```

초기 예: family당 10%p.

Risk Budget의 변화도 제한할 수 있으나 위험 악화 방향은 즉시 적용을 허용한다.

```text
risk budget increase
→ ramp-up 제한

risk budget decrease
→ 즉시 적용 가능
```

이를 비대칭 change limiter로 정의한다.

### 10.11 Recovery Asymmetry

위기 진입보다 위험 해제가 느려야 한다.

```text
Risk deterioration
→ fast de-risk

Risk normalization
→ slow re-risk
```

예:

```text
NORMAL → RISK_OFF
risk budget 1.0 → 0.5 즉시 가능

RISK_OFF → RECOVERY → NORMAL
0.5 → 0.7 → 0.8 → 0.9 → 1.0
점진적 회복
```

---

## 11. Regime Conflict Resolution

20번에서 다음처럼 충돌할 수 있다.

```text
Trend = STRONG_UP
Volatility = EXTREME
Breadth = NARROW
Liquidity = STRESSED
```

이 경우 단일 낙관 Regime으로 덮지 않는다.

v1 우선순위:

```text
Hard Stress / Market Dislocation
> Volatility
> Liquidity
> Trend
> Breadth
```

안전 방향 충돌 시 보수적인 정책을 선택한다.

예:

```text
primary = RISK_ON
volatility = EXTREME
liquidity = STRESSED

→ effective regime = RISK_OFF-like safety profile
→ reason = REGIME_CONFLICT_CONSERVATIVE_OVERRIDE
```

---

## 12. Safety Override

다음 상태는 일반 smoothing/hysteresis를 우회할 수 있다.

```text
MARKET_HALT
OFFICIAL_EXCHANGE_DISRUPTION
EXTREME_VOLATILITY_HARD_TRIGGER
LIQUIDITY_DISLOCATION
BENCHMARK_DATA_CONFLICT
REGIME_INPUT_CONFLICTED
POLICY_NOT_APPROVED
```

Safety override 결과 예:

```text
new_entry_mode = BLOCKED
risk_budget_multiplier = 0
position_size_multiplier = 0 for new positions
```

기존 보유자산의 청산 기능은 유지한다.

---

## 13. Point-in-Time 규칙

평가시점 `T`에서 사용 가능한 모든 입력은 다음을 만족해야 한다.

```text
regime_snapshot.known_at <= T
policy_snapshot.known_at <= T
previous_adaptation.known_at <= T
market_calendar.known_at <= T
```

과거 백테스트에서 오늘의 Regime이나 오늘 승인된 정책을 소급 사용하면 안 된다.

```text
current regime → historical decision
금지

latest policy → historical decision
금지
```

정책 수정은 append-only revision으로 관리한다.

---

## 14. 데이터베이스 설계

### 14.1 `regime_adaptation_policies`

```sql
CREATE TABLE regime_adaptation_policies (
    policy_id TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL,
    known_at TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    policy_hash TEXT NOT NULL
);
```

### 14.2 `regime_adaptation_profiles`

```sql
CREATE TABLE regime_adaptation_profiles (
    policy_id TEXT NOT NULL,
    regime_code TEXT NOT NULL,
    quality_weight TEXT,
    valuation_weight TEXT,
    expectations_weight TEXT,
    behavior_weight TEXT,
    alpha_threshold TEXT,
    confidence_threshold TEXT,
    adjusted_signal_threshold TEXT,
    risk_budget_multiplier TEXT NOT NULL,
    position_size_multiplier TEXT NOT NULL,
    new_entry_mode TEXT NOT NULL,
    PRIMARY KEY (policy_id, regime_code)
);
```

### 14.3 `regime_transition_rules`

```sql
CREATE TABLE regime_transition_rules (
    policy_id TEXT NOT NULL,
    from_regime TEXT NOT NULL,
    to_regime TEXT NOT NULL,
    required_confirmations INTEGER NOT NULL,
    entry_threshold TEXT,
    exit_threshold TEXT,
    hard_trigger INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (policy_id, from_regime, to_regime)
);
```

### 14.4 `regime_adaptation_runs`

```sql
CREATE TABLE regime_adaptation_runs (
    run_id TEXT PRIMARY KEY,
    evaluation_time TEXT NOT NULL,
    regime_snapshot_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    previous_adaptation_id TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    input_hash TEXT NOT NULL,
    output_hash TEXT
);
```

### 14.5 `regime_adaptation_snapshots`

```sql
CREATE TABLE regime_adaptation_snapshots (
    adaptation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    source_regime_snapshot_id TEXT NOT NULL,
    effective_regime TEXT NOT NULL,
    transition_state TEXT NOT NULL,
    alpha_threshold TEXT,
    confidence_threshold TEXT,
    adjusted_signal_threshold TEXT,
    risk_budget_multiplier TEXT NOT NULL,
    position_size_multiplier TEXT NOT NULL,
    new_entry_mode TEXT NOT NULL,
    regime_confidence TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 14.6 `regime_adaptation_weights`

```sql
CREATE TABLE regime_adaptation_weights (
    adaptation_id TEXT NOT NULL,
    family_code TEXT NOT NULL,
    base_weight TEXT NOT NULL,
    target_weight TEXT NOT NULL,
    effective_weight TEXT NOT NULL,
    change_limited INTEGER NOT NULL,
    PRIMARY KEY (adaptation_id, family_code)
);
```

### 14.7 `regime_adaptation_reason_events`

```sql
CREATE TABLE regime_adaptation_reason_events (
    event_id TEXT PRIMARY KEY,
    adaptation_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## 15. 데이터 저장 원칙

1. Decimal은 float로 저장하지 않는다.
2. 정책과 Snapshot은 append-only다.
3. 이전 Adaptation Snapshot을 UPDATE하지 않는다.
4. 모든 결과는 source regime snapshot id를 가진다.
5. 모든 결과는 policy version/hash를 가진다.
6. family weight의 합은 허용오차 내 1이어야 한다.
7. BLOCKED 모드에서 신규 진입용 weight가 존재하더라도 BUY 후보 전달은 금지한다.
8. 동일 입력·정책·이전 상태는 동일 snapshot_hash를 생성해야 한다.

---

## 16. 상태 전이 모델

```text
STABLE
TRANSITION_PENDING
TRANSITION_CONFIRMED
SAFETY_OVERRIDE
RECOVERY_RAMP
BLOCKED
```

예:

```text
NORMAL
↓ stress 증가 1회
TRANSITION_PENDING
↓ 2회 연속 확인
TRANSITION_CONFIRMED → RISK_OFF

RISK_OFF
↓ 개선 1~2회
TRANSITION_PENDING
↓ 3회 확인
RECOVERY
↓ 점진적 risk ramp
RECOVERY_RAMP
↓ 기준 충족
NORMAL
```

---

## 17. 주요 Reason Code

```text
REGIME_SNAPSHOT_MISSING
REGIME_SNAPSHOT_STALE
REGIME_INPUT_CONFLICTED
REGIME_UNKNOWN
REGIME_CONFIDENCE_LOW
REGIME_PROFILE_NOT_FOUND
POLICY_NOT_APPROVED
POLICY_NOT_EFFECTIVE
FUTURE_REGIME_INFORMATION
FUTURE_POLICY_INFORMATION
TRANSITION_CONFIRMATION_PENDING
TRANSITION_CONFIRMED
HYSTERESIS_HOLD
WEIGHT_CHANGE_LIMITED
RISK_BUDGET_REDUCED
RISK_BUDGET_RECOVERY_RAMP
ENTRY_THRESHOLD_TIGHTENED
NEW_ENTRY_LIMITED
NEW_ENTRY_BLOCKED
REGIME_CONFLICT_CONSERVATIVE_OVERRIDE
CRISIS_SAFETY_OVERRIDE
WEIGHT_SUM_INVALID
NEGATIVE_WEIGHT_INVALID
SNAPSHOT_HASH_MISMATCH
```

---

## 18. 코드 구조

```text
regime_adaptation/
├── __init__.py
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── adapters/
│   └── market_regime.py
├── temporal.py
├── validation.py
├── profiles.py
├── transitions.py
├── hysteresis.py
├── confidence.py
├── conflicts.py
├── weights.py
├── thresholds.py
├── risk_budget.py
├── entry_mode.py
├── change_limiter.py
├── safety_override.py
├── recovery.py
├── reason_codes.py
├── explainability.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

---

## 19. 핵심 모델 예시

```python
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Mapping

@dataclass(frozen=True)
class AdaptationProfile:
    regime: str
    family_weights: Mapping[str, Decimal]
    alpha_threshold: Decimal
    confidence_threshold: Decimal
    adjusted_signal_threshold: Decimal
    risk_budget_multiplier: Decimal
    position_size_multiplier: Decimal
    new_entry_mode: str

@dataclass(frozen=True)
class AdaptationResult:
    effective_regime: str
    transition_state: str
    effective_weights: Mapping[str, Decimal]
    alpha_threshold: Decimal
    confidence_threshold: Decimal
    adjusted_signal_threshold: Decimal
    risk_budget_multiplier: Decimal
    position_size_multiplier: Decimal
    new_entry_mode: str
    reason_codes: tuple[str, ...]
```

---

## 20. Weight 계산 예시 코드

```python
from decimal import Decimal

ONE = Decimal("1")


def blend_weights(previous, target, lam, cap):
    result = {}
    for family in target:
        prev = previous[family]
        tgt = target[family]
        blended = (ONE - lam) * prev + lam * tgt
        if blended > cap:
            blended = cap
        if blended < Decimal("0"):
            raise ValueError("NEGATIVE_WEIGHT_INVALID")
        result[family] = blended

    total = sum(result.values(), Decimal("0"))
    if total <= 0:
        raise ValueError("WEIGHT_SUM_INVALID")

    return {
        family: value / total
        for family, value in result.items()
    }
```

---

## 21. Transition Resolver 예시 코드

```python
def resolve_transition(
    previous_regime,
    observed_regime,
    confirmation_count,
    rule,
    hard_trigger=False,
):
    if hard_trigger:
        return observed_regime, "SAFETY_OVERRIDE"

    if observed_regime == previous_regime:
        return previous_regime, "STABLE"

    if confirmation_count < rule.required_confirmations:
        return previous_regime, "TRANSITION_PENDING"

    return observed_regime, "TRANSITION_CONFIRMED"
```

---

## 22. Engine 의사코드

```python
def run_regime_adaptation(request):
    regime = load_regime_snapshot(request.regime_snapshot_id)
    policy = load_effective_policy(request.evaluation_time)
    previous = load_previous_adaptation(request.evaluation_time)

    validate_temporal_contract(regime, policy, request.evaluation_time)

    safety = evaluate_safety_override(regime, policy)

    if safety.block_new_entries:
        result = build_blocked_result(regime, policy, safety)
        return persist_atomic(result)

    effective_regime, transition_state = resolve_regime_transition(
        regime,
        previous,
        policy,
    )

    profile = select_profile(effective_regime, policy)

    lam = compute_transition_lambda(
        regime_confidence=regime.regime_confidence,
        transition_state=transition_state,
        policy=policy,
    )

    weights = adapt_weights(
        previous_weights=previous.signal_family_weights,
        target_weights=profile.signal_family_weights,
        lam=lam,
        policy=policy,
    )

    thresholds = adapt_thresholds(profile, policy)
    risk_budget = adapt_risk_budget(profile, previous, policy)
    entry_mode = resolve_entry_mode(profile, regime, policy)

    result = build_snapshot(
        regime=regime,
        effective_regime=effective_regime,
        transition_state=transition_state,
        weights=weights,
        thresholds=thresholds,
        risk_budget=risk_budget,
        entry_mode=entry_mode,
        policy=policy,
    )

    validate_output_invariants(result)
    return persist_atomic(result)
```

---

## 23. 42번 Signal Engine 연동 계약

42번은 더 이상 자체적으로 Regime weight를 추정하지 않는다.

```python
@dataclass(frozen=True)
class SignalRegimePolicyInput:
    adaptation_id: str
    family_weights: Mapping[str, Decimal]
    alpha_threshold: Decimal
    confidence_threshold: Decimal
    adjusted_signal_threshold: Decimal
    new_entry_mode: str
    known_at: datetime
    snapshot_hash: str
```

42번의 Candidate Gate는 다음과 같이 변경된다.

```text
if new_entry_mode == BLOCKED:
    candidate_state = REJECTED_REGIME

else:
    alpha >= effective_alpha_threshold
    confidence >= effective_confidence_threshold
    adjusted_signal >= effective_signal_threshold
```

---

## 24. 22/23번 연동 계약

22번 Risk Engine 입력:

```text
risk_budget_multiplier
stress reason codes
effective_regime
```

23번 Decision Engine 입력:

```text
position_size_multiplier
new_entry_mode
max_new_entries_multiplier
```

예를 들어 사용자의 PAPER 정책이 하루 신규매수 최대 1종목이면:

```text
NORMAL
1 × 1.0 → 최대 1종목

LIMITED
1 × 0.5 → 정책 resolver에서 0 또는 1로 명시적 처리

BLOCKED
→ 0종목
```

소수 종목수를 암묵적 반올림하지 않고 정책에 `floor/ceil/explicit` 규칙을 둔다.

---

## 25. Explainability 출력

43번은 다음 설명 데이터를 제공해야 한다.

```json
{
  "effective_regime": "RISK_OFF",
  "transition_state": "TRANSITION_CONFIRMED",
  "regime_confidence": "0.82",
  "weight_changes": {
    "quality": "+0.10",
    "valuation": "-0.05",
    "expectations": "-0.10",
    "behavior": "+0.05"
  },
  "alpha_threshold": "75",
  "confidence_threshold": "70",
  "risk_budget_multiplier": "0.50",
  "new_entry_mode": "LIMITED",
  "reason_codes": [
    "ENTRY_THRESHOLD_TIGHTENED",
    "RISK_BUDGET_REDUCED"
  ]
}
```

이 설명은 30번 Explainability Engine의 증거 Bundle에 포함된다.

---

## 26. 단위 테스트 계획

### A. NORMAL 정상 경로

```text
입력: NORMAL, confidence 0.9
결과:
- NORMAL profile 선택
- weight 합 = 1
- entry mode NORMAL
- risk budget 1.0
```

### B. RISK_OFF 전환 미확정

```text
전일 NORMAL
오늘 observed RISK_OFF
confirmation 1/2
→ effective NORMAL 유지
→ TRANSITION_PENDING
→ HYSTERESIS_HOLD
```

### C. RISK_OFF 전환 확정

```text
confirmation 2/2
→ effective RISK_OFF
→ threshold 강화
→ risk budget 0.5
```

### D. CRISIS hard trigger

```text
전일 NORMAL
오늘 hard crisis trigger
→ confirmation 대기 없음
→ CRISIS
→ NEW_ENTRY_BLOCKED
→ risk budget 0
```

### E. 낮은 Regime confidence

```text
observed RISK_ON
confidence 0.42
→ 즉시 공격적 weight 확대 금지
→ REGIME_CONFIDENCE_LOW
```

### F. 회복 구간

```text
RISK_OFF → RECOVERY
risk budget 0.5 → 0.7
다음날 NORMAL observed라도
→ 즉시 1.0 금지
→ RECOVERY_RAMP
```

### G. Weight cap

```text
Behavior target 0.70
family cap 0.45
→ 0.45 이하
→ 나머지 family 재정규화
```

### H. Weight sum 오류

```text
정책 weight 합 1.20
→ WEIGHT_SUM_INVALID
→ Snapshot FINALIZED 금지
```

### I. 미래 Regime 정보

```text
regime.known_at > evaluation_time
→ FUTURE_REGIME_INFORMATION
→ 사용 0건
```

### J. 미래 정책

```text
policy.known_at > evaluation_time
→ FUTURE_POLICY_INFORMATION
→ 정책 사용 0건
```

### K. Regime conflict

```text
primary RISK_ON
volatility EXTREME
liquidity STRESSED
→ conservative override
→ 공격적 profile 금지
```

### L. 동일 입력 재실행

```text
동일 regime snapshot
동일 policy
동일 previous adaptation
동일 evaluation_time
→ 동일 output
→ 동일 snapshot hash
```

---

## 27. 통합 테스트 계획

### Integration 1: 20 → 43

고정 Market Regime fixture를 입력하여 profile과 transition 결과를 검증한다.

### Integration 2: 43 → 42

같은 종목 Feature라도 Regime이 바뀔 때 Candidate 결과가 달라지는지 검증한다.

```text
종목 Alpha 70 / Confidence 68 / Adj 62

NORMAL
→ ELIGIBLE 가능

RISK_OFF
→ threshold 미달
→ REJECTED_REGIME 또는 REJECTED_SIGNAL
```

### Integration 3: 43 → 22 → 23

```text
NORMAL target 1,000,000원

RISK_OFF multiplier 0.5
→ regime-adjusted base 500,000원
→ 이후 포트폴리오 제한 재검증
```

### Integration 4: CRISIS

```text
유효 Candidate 10개 존재
→ 43 new_entry_mode BLOCKED
→ 신규 BUY 0건
→ SELL/REDUCE는 정상 동작
```

### Integration 5: Paper Trading 연속 20거래일

```text
NORMAL 5일
→ RISK_OFF 4일
→ CRISIS 2일
→ RECOVERY 4일
→ NORMAL 5일
```

검증:

- state transition 결정론성
- 신규매수 차단 정확성
- risk ramp 정확성
- 이전 portfolio continuity 유지
- 미래정보 사용 0건

---

## 28. Property-Based Test

다음 불변식을 property test로 검증한다.

```text
모든 비차단 Snapshot에서 sum(weights) ≈ 1
모든 weight >= 0
risk_budget_multiplier >= 0
position_size_multiplier >= 0
BLOCKED이면 신규매수 허용 수 = 0
미래정보 사용 수 = 0
동일 입력 hash → 동일 출력 hash
위험 악화 시 risk budget 증가 금지
회복 첫날 risk budget 즉시 1.0 복귀 금지
```

---

## 29. Failure Injection Test

1. DB commit 직전 장애
2. Policy 읽기 중 장애
3. 이전 Snapshot 누락
4. Regime Snapshot hash 불일치
5. malformed Decimal
6. 중복 adaptation run
7. 부분 저장 후 재실행

기대 결과:

```text
불완전 FINALIZED Snapshot = 0
중복 logical Snapshot = 0
재실행 가능
감사 reason event 보존
```

---

## 30. Backtest 안전 규칙

Backtest는 반드시 당시 알려진 Regime과 당시 승인된 정책만 사용한다.

금지:

```text
오늘의 위기 분류를 과거에 소급
현재 조정된 policy를 과거에 소급
사후 수익률을 이용해 Regime label 수정
미래 거래일 confirmation을 현재 transition에 사용
```

특히 Regime model 자체의 historical labels가 사후 수정될 수 있으므로 `known_at` revision ledger가 필요하다.

---

## 31. 성능 평가 지표

43번 자체의 우수성을 단순 수익률만으로 평가하지 않는다.

검증 지표:

```text
Turnover caused by weight adaptation
Regime transition frequency
False transition rate
Average risk budget by regime
Max one-day risk-budget increase
Time-to-de-risk
Time-to-re-risk
Candidate count by regime
Drawdown containment
Missed upside during recovery
Signal family contribution stability
```

전략 승격은 27번 Strategy Validation Engine이 결정한다.

---

## 32. 초기 PAPER 정책 권고

초기 운영에서는 동적 적응을 공격적으로 사용하지 않는다.

권고:

```text
1. Regime은 5~7개 canonical state로 제한
2. family weight 일일 변화 10%p 이하
3. 위험 악화는 빠르게 반영
4. 위험 완화는 최소 3거래일 확인
5. CRISIS에서 신규매수 0
6. UNKNOWN에서 공격적 신규매수 금지
7. Confidence 낮은 Regime은 이전 stable profile 우선
8. 모든 weight/threshold 변화 Reason Code 기록
```

---

## 33. 구현 우선순위

```text
1. immutable models / enums
2. SQLite migration
3. canonical regime adapter
4. policy profile loader
5. temporal gate
6. transition resolver
7. hysteresis / confirmation
8. conflict resolver
9. weight blender
10. weight cap / normalization
11. dynamic thresholds
12. risk budget multiplier
13. entry mode resolver
14. asymmetric change limiter
15. recovery ramp
16. safety override
17. snapshot hash / manifest
18. repository atomic write
19. 20→43 fixture integration
20. 43→42 fixture integration
21. 43→22→23 integration
22. 20거래일 Paper Trading test
```

---

## 34. 핵심 안전 불변식

```text
미래 Regime 정보 사용 = 0
미래 정책 사용 = 0
현재 Regime의 과거 백테스트 소급 = 0
현재 정책의 과거 소급 = 0
음수 Signal weight = 0
weight 합계 오류 FINALIZED = 0
CRISIS 신규 BUY 전달 = 0
UNKNOWN을 자동 RISK_ON 변환 = 0
위험 악화 시 risk budget 증가 = 0
회복 첫날 full risk 복귀 = 0
동일 입력·정책·이전 상태에서 결과 변경 = 0
과거 Adaptation Snapshot 수정/삭제 = 0
```

---

## 35. ADE 전체에서의 위치

```text
38 Fundamental PIT
        ↓
39 Valuation / Factors
        ↓
40 Expectations
        ↓
41 Market Behavior
        ↓
20 Market Regime
        ↓
43 Regime Adaptation
   ├─ Dynamic Family Weights
   ├─ Dynamic Candidate Thresholds
   ├─ Risk Budget Multiplier
   └─ New Entry Mode
        ↓
42 Signal Integration
        ↓
22 Portfolio Risk
        ↓
23 Decision / Position Sizing
        ↓
24 Order Validation
        ↓
31 Paper Trading / Live Execution
```

43번의 핵심 철학은 다음 한 문장으로 요약된다.

> 시장 국면은 미래수익률을 맞히기 위한 별도 매매신호가 아니라, 이미 존재하는 투자 신호를 얼마나 신뢰하고 얼마나 위험을 허용할지 조절하는 안전 정책 계층이다.
