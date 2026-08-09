# 41. Market Behavior, Momentum, Trend & Relative Strength Engine v1

## 1. 문서 목적

이 문서는 AI Decision Engine(ADE)의 `Market Behavior, Momentum, Trend & Relative Strength Engine v1` 설계를 정의한다.

이 엔진은 Point-in-Time 시장가격·거래량·벤치마크·기업행동 조정계열을 결합하여 종목별 가격 행동과 시장 상대행동을 표준 Feature로 변환한다.

주요 출력은 다음과 같다.

- Absolute Momentum
- Relative Strength
- Trend State
- Breakout / Breakdown State
- Volatility-Adjusted Momentum
- Volume Confirmation
- Drawdown / Recovery State
- Gap / Shock State
- Cross-Sectional Momentum Rank
- Market Behavior Evidence Manifest

이 엔진은 BUY·SELL·주문을 직접 생성하지 않는다. 출력은 Signal Generation, Market Regime, Risk, Decision, Explainability, Backtest 계층이 소비한다.

핵심 목표는 단순히 `가격이 올랐다/내렸다`를 계산하는 것이 아니라 다음 질문에 재현 가능하게 답하는 것이다.

```text
평가시점 이전에 실제로 확정된 가격만 사용했는가?
기업행동 조정이 미래정보를 포함하지 않았는가?
종목 자체 모멘텀과 시장 대비 상대강도를 분리했는가?
추세와 단기 반등을 구분했는가?
고변동 종목의 큰 수익률을 과대평가하지 않았는가?
거래량이 가격 움직임을 확인하는가?
현재의 Universe·Benchmark 정보를 과거 백테스트에 소급하지 않았는가?
```

---

## 2. 핵심 책임

### 2.1 수행 책임

1. 확정된 일별 OHLCV 및 거래대금 입력 검증
2. RAW 가격과 기업행동 조정계열 분리
3. 거래일 기준 lookback window 생성
4. 단기·중기·장기 절대 모멘텀 계산
5. Benchmark 대비 Relative Strength 계산
6. 이동평균 기반 Trend State 계산
7. 고점·저점 돌파 및 추세 확인 계산
8. 실현변동성·ATR 기반 변동성 조정 모멘텀 계산
9. 거래량·거래대금 확인 Feature 계산
10. Drawdown·Recovery·Distance-from-High 계산
11. Gap·Shock·Abnormal Move 계산
12. Universe 내 횡단면 Momentum Rank 계산
13. 결측·거래정지·신규상장·저유동성 처리
14. Point-in-Time Market Behavior Snapshot 생성
15. 모든 산식·정책·입력 Snapshot hash 및 Evidence 보존

### 2.2 수행하지 않는 책임

- 공식 종가 확정 자체
- Corporate Action 원천 이벤트 판단
- 투자 Universe 최종 선정
- Market Regime 최종 분류
- BUY/SELL 임계값 결정
- 포트폴리오 비중 결정
- 주문가격·수량 결정
- 거래비용 계산

---

## 3. 상위 아키텍처

```text
Market Data Finalization Snapshot
Corporate Actions Adjusted-Series Policy
Instrument Master
Benchmark Snapshot
Trading Calendar
Universe Snapshot
        ↓
Input Contract & Temporal Gate
        ↓
Price Series Builder
   ├─ RAW OHLCV
   ├─ Split/Bonus-adjusted price
   ├─ Total-return-compatible reference
   └─ Suspended / stale-bar handling
        ↓
Return Engine
   ├─ 1D / 5D / 20D / 60D / 120D / 252D
   ├─ skip-period momentum
   └─ log / simple returns
        ↓
Trend Engine
   ├─ moving averages
   ├─ slope
   ├─ price-vs-trend
   └─ trend alignment
        ↓
Relative Strength Engine
   ├─ vs KOSPI/KOSPI200
   ├─ vs sector benchmark
   └─ cross-sectional rank
        ↓
Volatility & Shock Engine
   ├─ realized vol
   ├─ ATR
   ├─ downside vol
   ├─ gap
   └─ abnormal return
        ↓
Volume Confirmation Engine
        ↓
Drawdown / Recovery Engine
        ↓
Quality & Leakage Gate
        ↓
Immutable Market Behavior Snapshot
        ↓
Signal / Regime / Risk / Decision / Explainability
```

---

## 4. 입력 계약

### 4.1 실행 요청

```python
MarketBehaviorRunRequest(
    run_id,
    evaluation_time,
    market_date,
    universe_snapshot_id,
    market_data_snapshot_id,
    corporate_action_snapshot_id,
    benchmark_snapshot_id,
    instrument_master_snapshot_id,
    trading_calendar_snapshot_id,
    behavior_policy_snapshot_id,
)
```

### 4.2 종목별 일별 입력

```text
security_id
listing_id
market_date
open
high
low
close
volume
turnover_value
vwap(optional)
trade_count(optional)
price_status
observed_at
known_at
source_id
revision
```

### 4.3 조정계열 메타데이터

```text
security_id
adjustment_basis
adjustment_factor
factor_effective_date
factor_known_at
corporate_action_event_id
adjusted_series_version
```

### 4.4 Benchmark 입력

```text
benchmark_id
series_type
market_date
close
known_at
benchmark_snapshot_id
```

### 4.5 입력 전제

- 가격은 Market Data Finalization Engine이 승인한 `FINALIZED` 또는 정책상 허용된 값만 사용한다.
- `security_id`는 Instrument Master에서 해결된 canonical ID를 사용한다.
- 거래일은 Trading Calendar 기준으로 계산한다.
- 기업행동 조정은 Corporate Actions Engine이 승인한 Point-in-Time factor만 사용한다.
- Benchmark는 Benchmark Engine이 제공한 동일 거래일 및 동일 평가시점 계열을 사용한다.

---

## 5. 출력 계약

### 5.1 실행 결과

```python
MarketBehaviorRunResult(
    run_id,
    status,
    market_date,
    evaluation_time,
    instrument_count,
    finalized_count,
    degraded_count,
    blocked_count,
    behavior_snapshot_id,
    snapshot_hash,
    reason_codes,
)
```

### 5.2 종목별 결과

```python
InstrumentMarketBehaviorResult(
    security_id,
    status,
    absolute_momentum,
    relative_strength,
    trend_features,
    breakout_features,
    volatility_features,
    volume_features,
    drawdown_features,
    shock_features,
    cross_sectional_features,
    evidence_refs,
    reason_codes,
    result_hash,
)
```

### 5.3 상태

| 상태 | 의미 |
|---|---|
| `FINALIZED` | 필수 가격·벤치마크·기간 데이터가 정상 |
| `DEGRADED` | 일부 보조 Feature 결측이나 짧은 이력 |
| `BLOCKED` | 종가 미확정·미래정보·핵심 계열 충돌 |
| `INSUFFICIENT_HISTORY` | 핵심 lookback에 필요한 거래일 부족 |
| `SUSPENDED` | 거래정지 상태로 신규 가격행동 판단 제한 |
| `NOT_APPLICABLE` | 해당 Feature가 정책상 적용되지 않음 |

---

## 6. 시간 및 Point-in-Time 규칙

평가시점 `T`에서 사용하는 모든 데이터는 다음을 만족해야 한다.

```text
price.known_at <= T
benchmark.known_at <= T
corporate_action.factor_known_at <= T
universe.known_at <= T
policy.known_at <= T
```

### 6.1 거래일 기준 lookback

`20D`는 달력 20일이 아니라 Trading Calendar의 직전 20개 유효 거래일이다.

```text
market_date = 2026-08-07
20D lookback
→ 해당 시장의 이전 20개 거래 세션
```

휴일·주말을 임의 전일 보간하지 않는다.

### 6.2 장중 데이터 사용 금지

일일 종가 기반 Feature 실행에서는:

```text
bar_status != FINALIZED_CLOSE
→ 사용 금지
```

장중 값으로 종가 Feature를 계산하지 않는다.

### 6.3 미래 Corporate Action 사용 금지

평가일 이후 알려진 액면분할·무상증자·분할 정보를 과거 adjusted series에 소급 적용하지 않는다.

```text
adjustment.factor_known_at > evaluation_time
→ factor 사용 금지
```

### 6.4 Snapshot 불변성

과거 Feature Snapshot은 후속 정정이나 Corporate Action 발견으로 UPDATE하지 않는다.

```text
기존 Snapshot 보존
+ 새 revision / replay Snapshot 생성
```

---

## 7. 가격계열 정책

### 7.1 RAW 가격

다음 Feature는 기본적으로 RAW 가격을 사용한다.

```text
당일 gap
intraday range
limit-up/down proximity
실제 주문 가능 가격과의 거리
```

### 7.2 Corporate-Action Adjusted 가격

다음 Feature는 경제적 연속성이 필요한 조정계열을 사용한다.

```text
20D/60D/120D/252D momentum
moving-average trend
52-week high distance
historical volatility
breakout history
```

### 7.3 배당 처리

v1의 가격 모멘텀은 기본적으로 split/bonus-rights 구조왜곡을 제거한 가격계열을 사용한다.

배당 재투자까지 포함하는 Total Return Momentum은 별도 feature로 명시한다.

```text
PRICE_MOMENTUM
TOTAL_RETURN_MOMENTUM
```

둘을 혼합하지 않는다.

---

## 8. 수익률 엔진

### 8.1 Simple Return

```text
R(t, n)
= P_t / P_(t-n) - 1
```

### 8.2 Log Return

변동성 계산용:

```text
r_t = ln(P_t / P_(t-1))
```

### 8.3 기본 Horizon

초기 정책:

```text
1D
5D
20D
60D
120D
252D
```

모든 horizon은 정책 Snapshot으로 관리한다.

### 8.4 Skip-Period Momentum

단기 reversal 영향을 줄이기 위한 장기 momentum:

```text
12M-1M Momentum
= P_(t-20) / P_(t-252) - 1
```

최근 약 1개월을 제외한다.

### 8.5 복합 절대 Momentum

초기 연구용 예:

```text
Absolute Momentum Score Raw
= 0.20 * R20
+ 0.30 * R60
+ 0.30 * R120
+ 0.20 * R252_skip20
```

이 가중치는 Signal threshold가 아니며 `behavior_policy_snapshot`에 저장한다.

---

## 9. Relative Strength Engine

### 9.1 Benchmark 대비 상대수익

단순 초과수익:

```text
Relative Return(n)
= Stock Return(n) - Benchmark Return(n)
```

복리 기준 상대 Wealth:

```text
Relative Wealth(n)
= (1 + Stock Return(n))
  / (1 + Benchmark Return(n))
  - 1
```

기본 출력은 둘 다 보존하되 Signal 계층은 정책상 하나를 선택한다.

### 9.2 다중 Benchmark

가능한 benchmark:

```text
KOSPI
KOSPI200
KOSDAQ
Sector Index
Style / Size Benchmark
```

종목 시장과 benchmark가 불일치하면 reason code를 기록한다.

### 9.3 Relative Strength Composite

초기 예:

```text
RS_raw
= 0.25 * RS20
+ 0.35 * RS60
+ 0.25 * RS120
+ 0.15 * RS252_skip20
```

### 9.4 시장 상승과 상대강도 분리

```text
Stock +8%, Market +10%
→ Absolute Momentum positive
→ Relative Strength negative
```

둘을 동일 Feature로 합치지 않는다.

---

## 10. Trend Engine

### 10.1 이동평균

기본:

```text
MA20
MA60
MA120
MA200
```

가격계열은 조정종가를 사용한다.

### 10.2 Price-vs-MA

```text
distance_to_ma_n
= P_t / MA_n - 1
```

### 10.3 MA 정렬

상승 정렬 예:

```text
P > MA20 > MA60 > MA120 > MA200
```

하락 정렬:

```text
P < MA20 < MA60 < MA120 < MA200
```

### 10.4 이동평균 기울기

단순 차분이 아닌 정규화 기울기:

```text
MA_slope(n, k)
= MA_n(t) / MA_n(t-k) - 1
```

또는 로그가격 선형회귀 기울기를 보조값으로 사용할 수 있다.

### 10.5 Trend State

초기 상태:

```text
STRONG_UPTREND
UPTREND
NEUTRAL
DOWNTREND
STRONG_DOWNTREND
```

예시 규칙:

```text
STRONG_UPTREND
if P > MA20 > MA60 > MA120
and slope60 > 0
and slope120 > 0
```

상태 규칙은 정책 버전으로 고정한다.

### 10.6 추세와 반등 구분

```text
P > MA20
but P < MA60 and MA60 slope < 0
→ SHORT_TERM_REBOUND
```

이를 `UPTREND`로 오분류하지 않는다.

---

## 11. Breakout / Breakdown Engine

### 11.1 N일 고점 돌파

```text
prior_high_n
= max(P_(t-n) ... P_(t-1))

breakout_n
= P_t > prior_high_n
```

현재 종가를 prior high 계산에 포함하지 않는다.

### 11.2 돌파 강도

```text
breakout_distance
= P_t / prior_high_n - 1
```

### 11.3 확인 조건

독립 Feature로 다음을 생성한다.

```text
BREAKOUT_PRICE_ONLY
BREAKOUT_WITH_VOLUME
BREAKOUT_WITH_RELATIVE_STRENGTH
BREAKOUT_WITH_TREND_ALIGNMENT
```

Signal Engine이 어떤 조합을 사용할지는 별도 정책이다.

### 11.4 Breakdown

저점 이탈도 대칭적으로 계산한다.

```text
prior_low_n
= min(P_(t-n) ... P_(t-1))
```

---

## 12. Volatility Engine

### 12.1 Realized Volatility

```text
RV_n
= std(daily log returns over n sessions)
  * sqrt(annualization_factor)
```

연환산 계수는 기본 252이지만 정책 Snapshot에서 관리한다.

### 12.2 Downside Volatility

```text
DownsideVol_n
= std(min(r_t, 0)) * sqrt(252)
```

### 12.3 ATR

True Range:

```text
TR_t = max(
    High_t - Low_t,
    abs(High_t - Close_(t-1)),
    abs(Low_t - Close_(t-1))
)
```

```text
ATR14 = mean(TR over 14 sessions)
ATR_pct = ATR14 / Close_t
```

### 12.4 Volatility-Adjusted Momentum

```text
VAM_n
= Return_n / max(RealizedVol_n, epsilon)
```

높은 raw return이 단지 높은 변동성 때문인지 분리한다.

### 12.5 변동성 급등

```text
vol_shock_ratio
= RV20 / RV120
```

예:

```text
RV20 >> RV120
→ VOLATILITY_REGIME_SHIFT
```

---

## 13. Volume & Turnover Confirmation

### 13.1 상대 거래량

```text
Relative Volume 20
= Volume_t / median(Volume previous 20 sessions)
```

현재 거래량을 기준 median 계산에 포함하지 않는다.

### 13.2 거래대금 확인

가격이 크게 변했지만 거래량만 보는 왜곡을 줄이기 위해 거래대금도 보존한다.

```text
Turnover Ratio
= TurnoverValue_t
  / median(TurnoverValue prior 20)
```

### 13.3 Price-Volume Confirmation

다음 Feature를 분리한다.

```text
UP_MOVE_HIGH_VOLUME
UP_MOVE_LOW_VOLUME
DOWN_MOVE_HIGH_VOLUME
DOWN_MOVE_LOW_VOLUME
```

### 13.4 거래정지 및 0 거래량

```text
volume == 0
and listing_status == ACTIVE
```

이면 자동으로 정상 저유동성으로 간주하지 않는다.

Trading Halt 정보를 확인하여:

```text
TRADING_HALTED
ZERO_VOLUME_UNEXPLAINED
```

를 구분한다.

---

## 14. Drawdown & Recovery Engine

### 14.1 Rolling High

```text
High252_t
= max(P_t ... P_(t-251))
```

### 14.2 Distance from High

```text
DistanceFromHigh252
= P_t / High252_t - 1
```

### 14.3 Current Drawdown

```text
Drawdown_t
= P_t / running_peak_t - 1
```

### 14.4 Maximum Drawdown

```text
MDD_n
= min(drawdown over n-session window)
```

### 14.5 Recovery State

초기 상태:

```text
AT_NEW_HIGH
NEAR_HIGH
NORMAL_RANGE
DEEP_DRAWDOWN
RECOVERY_FROM_DRAWDOWN
```

예:

```text
prior drawdown <= -20%
and current drawdown > -10%
and MA60 slope > 0
→ RECOVERY_FROM_DRAWDOWN
```

반등과 완전 회복을 구분한다.

---

## 15. Gap & Shock Engine

### 15.1 Overnight Gap

```text
Gap_t
= Open_t / Close_(t-1) - 1
```

Corporate Action ex-date로 설명되는 gap은 일반 시장충격으로 분류하지 않는다.

### 15.2 Intraday Range

```text
IntradayRange
= (High_t - Low_t) / Close_(t-1)
```

### 15.3 Abnormal Return

단순 모델:

```text
AbnormalReturn_t
= StockReturn_t - Beta_est * BenchmarkReturn_t
```

Beta history가 부족하면 benchmark-relative return으로 대체하고 `DEGRADED`를 기록한다.

### 15.4 Shock State

```text
POSITIVE_SHOCK
NEGATIVE_SHOCK
GAP_UP_SHOCK
GAP_DOWN_SHOCK
VOLATILITY_SHOCK
NO_SHOCK
```

임계값은 고정 상수가 아니라 정책 Snapshot으로 관리한다.

---

## 16. Cross-Sectional Momentum Rank

### 16.1 비교집단

기본 순서:

```text
동일 시장 + 동일 업종
→ 동일 시장
→ 전체 eligible universe
```

표본이 너무 적으면 상위 그룹으로 확장한다.

### 16.2 Robust 처리

```text
raw momentum
→ winsorization(optional policy)
→ robust z-score
→ percentile rank
```

원천 수익률은 수정하지 않고 별도 정규화 값으로 저장한다.

### 16.3 Percentile

```text
momentum_percentile ∈ [0, 1]
```

1에 가까울수록 비교집단 내 강한 모멘텀이다.

### 16.4 Survivorship Bias 방지

과거 평가에서는 당시 Universe 구성종목만 횡단면에 포함한다.

```text
현재 상장종목 집합
→ 과거 rank 계산에 사용 금지
```

---

## 17. 신규상장 및 짧은 이력 처리

### 17.1 최소 이력

각 Feature별 최소 이력을 별도로 관리한다.

예:

```text
R20      → 21 sessions
MA60     → 60 sessions
R120     → 121 sessions
MA200    → 200 sessions
High252  → 252 sessions
```

### 17.2 Partial Feature

60일 이력만 있는 신규상장주는:

```text
20D Momentum 가능
60D Trend 일부 가능
120D/252D Momentum 불가
```

전체 종목을 차단하지 않고:

```text
DEGRADED
LONG_HORIZON_HISTORY_INSUFFICIENT
```

로 처리할 수 있다.

### 17.3 IPO 첫날

첫 거래일의 급등률을 장기 Momentum으로 해석하지 않는다.

```text
IPO_INITIAL_SESSION
```

Reason Code를 남긴다.

---

## 18. 거래정지·상폐·가격고정 처리

### 18.1 거래정지

거래정지 동안 전일 종가를 반복 삽입하여 가짜 저변동성 계열을 만들지 않는다.

```text
SUSPENDED_BAR
```

로 명시한다.

### 18.2 상장폐지

상폐일 이후 가격을 forward-fill 하지 않는다.

### 18.3 장기간 동일 종가

연속 동일 종가가 비정상적으로 길면:

```text
STALE_PRICE_SERIES
```

를 검사한다.

---

## 19. 데이터 품질 Gate

핵심 검사:

```text
close > 0
high >= max(open, close, low)
low <= min(open, close, high)
volume >= 0
turnover_value >= 0
market_date is valid trading session
known_at <= evaluation_time
no duplicate finalized bar
```

OHLC 관계 위반은:

```text
INVALID_OHLC
```

동일 security/date에 final bar가 2개면:

```text
CONFLICTED_FINAL_BAR
```

로 차단한다.

---

## 20. Feature 정규화 원칙

### 20.1 원천값 보존

다음 값을 모두 보존한다.

```text
raw_value
normalized_value
percentile
normalization_method
peer_group_id
policy_version
```

### 20.2 결측치를 0으로 대체 금지

```text
missing 252D momentum
!= 0% momentum
```

결측과 실제 0은 명확히 분리한다.

### 20.3 방향성

Feature 정의에는 다음 메타데이터를 둔다.

```text
HIGHER_IS_STRONGER
LOWER_IS_STRONGER
NON_MONOTONIC
STATE_ONLY
```

Signal Engine이 방향을 추정하지 않도록 한다.

---

## 21. 데이터베이스 설계

### 21.1 `market_behavior_policies`

```sql
CREATE TABLE market_behavior_policies (
    policy_snapshot_id TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    known_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    policy_hash TEXT NOT NULL
);
```

### 21.2 `market_behavior_runs`

```sql
CREATE TABLE market_behavior_runs (
    run_id TEXT PRIMARY KEY,
    market_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    universe_snapshot_id TEXT NOT NULL,
    market_data_snapshot_id TEXT NOT NULL,
    benchmark_snapshot_id TEXT NOT NULL,
    behavior_policy_snapshot_id TEXT NOT NULL,
    status TEXT NOT NULL,
    instrument_count INTEGER NOT NULL,
    finalized_count INTEGER NOT NULL,
    degraded_count INTEGER NOT NULL,
    blocked_count INTEGER NOT NULL,
    snapshot_hash TEXT,
    created_at TEXT NOT NULL
);
```

### 21.3 `market_behavior_feature_definitions`

```sql
CREATE TABLE market_behavior_feature_definitions (
    feature_code TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    horizon_sessions INTEGER,
    price_basis TEXT NOT NULL,
    direction TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL
);
```

### 21.4 `market_behavior_feature_values`

```sql
CREATE TABLE market_behavior_feature_values (
    run_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    feature_code TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    percentile_value TEXT,
    state_value TEXT,
    status TEXT NOT NULL,
    peer_group_id TEXT,
    evidence_hash TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, security_id, feature_code)
);
```

### 21.5 `market_behavior_reason_events`

```sql
CREATE TABLE market_behavior_reason_events (
    reason_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    security_id TEXT,
    feature_code TEXT,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL
);
```

### 21.6 `market_behavior_snapshots`

```sql
CREATE TABLE market_behavior_snapshots (
    behavior_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    market_date TEXT NOT NULL,
    evaluation_time TEXT NOT NULL,
    instrument_count INTEGER NOT NULL,
    manifest_json TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 21.7 `market_behavior_snapshot_members`

```sql
CREATE TABLE market_behavior_snapshot_members (
    behavior_snapshot_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    instrument_result_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (behavior_snapshot_id, security_id)
);
```

### 21.8 저장 원칙

```text
금액·비율·수익률 → Decimal 문자열 또는 고정정밀도 표현
상태 → Enum
정정 → append-only
Snapshot → immutable
동일 입력 → deterministic hash
```

---

## 22. Feature Definition Registry

Feature 코드는 문자열 관례에 의존하지 않고 Registry에서 관리한다.

예:

```text
MOM_RET_20D
MOM_RET_60D
MOM_12M_SKIP1M
RS_KOSPI_20D
RS_KOSPI_60D
TREND_MA20_DISTANCE
TREND_MA60_SLOPE
TREND_ALIGNMENT
BREAKOUT_20D
VOL_RV20
VOL_ATR14_PCT
VOLUME_REL20
DRAWDOWN_252D
DIST_HIGH_252D
GAP_1D
SHOCK_STATE
MOM_PERCENTILE_MARKET
```

각 정의에는:

```text
formula_version
required_history
price_basis
benchmark_requirement
normalization_method
direction
missing_policy
```

를 저장한다.

---

## 23. 알고리즘 실행 순서

```python
def run_market_behavior(request):
    validate_request(request)

    policy = load_policy(request.behavior_policy_snapshot_id)
    universe = load_universe(request.universe_snapshot_id)
    calendar = load_calendar(request.trading_calendar_snapshot_id)
    benchmark = load_benchmark(request.benchmark_snapshot_id)

    results = []

    for security in universe.members:
        bars = load_finalized_bars(
            security_id=security.security_id,
            end_date=request.market_date,
            required_sessions=policy.max_history_sessions,
        )

        temporal_guard(bars, request.evaluation_time)
        validate_series(bars, calendar)

        adjusted = build_point_in_time_adjusted_series(
            bars=bars,
            corporate_action_snapshot_id=request.corporate_action_snapshot_id,
            evaluation_time=request.evaluation_time,
        )

        features = {}
        features.update(calc_returns(adjusted, policy))
        features.update(calc_trend(adjusted, policy))
        features.update(calc_breakouts(adjusted, policy))
        features.update(calc_volatility(bars, adjusted, policy))
        features.update(calc_volume_features(bars, policy))
        features.update(calc_drawdown(adjusted, policy))
        features.update(calc_shocks(bars, benchmark, policy))
        features.update(calc_relative_strength(adjusted, benchmark, policy))

        quality = resolve_quality(features, bars, policy)
        results.append(build_instrument_result(security, features, quality))

    results = apply_cross_sectional_ranks(
        results,
        universe=universe,
        policy=policy,
    )

    return persist_immutable_snapshot(request, results, policy)
```

---

## 24. 핵심 계산 예제 코드

```python
from decimal import Decimal


def simple_return(current: Decimal, past: Decimal) -> Decimal | None:
    if past <= 0:
        return None
    return current / past - Decimal("1")


def relative_wealth_return(
    stock_return: Decimal,
    benchmark_return: Decimal,
) -> Decimal | None:
    denominator = Decimal("1") + benchmark_return
    if denominator <= 0:
        return None
    return (Decimal("1") + stock_return) / denominator - Decimal("1")
```

이동평균:

```python
def sma(values: list[Decimal], n: int) -> Decimal | None:
    if len(values) < n:
        return None
    window = values[-n:]
    return sum(window, Decimal("0")) / Decimal(n)
```

N일 돌파:

```python
def breakout_distance(closes: list[Decimal], n: int) -> Decimal | None:
    if len(closes) < n + 1:
        return None

    current = closes[-1]
    prior_high = max(closes[-(n + 1):-1])

    if prior_high <= 0:
        return None

    return current / prior_high - Decimal("1")
```

---

## 25. Reason Codes

### 데이터·시점

```text
MISSING_FINAL_CLOSE
CONFLICTED_FINAL_BAR
FUTURE_PRICE_INFORMATION
FUTURE_CORPORATE_ACTION_FACTOR
BENCHMARK_NOT_FINALIZED
BENCHMARK_DATE_MISMATCH
INVALID_TRADING_SESSION
INVALID_OHLC
STALE_PRICE_SERIES
```

### 이력

```text
INSUFFICIENT_HISTORY
LONG_HORIZON_HISTORY_INSUFFICIENT
IPO_INITIAL_SESSION
IPO_SHORT_HISTORY
```

### 거래 상태

```text
TRADING_HALTED
SUSPENDED_BAR
ZERO_VOLUME_UNEXPLAINED
DELISTED_SERIES_END
```

### 계산

```text
NON_POSITIVE_PRICE
RETURN_CALCULATION_BLOCKED
VOLATILITY_HISTORY_INSUFFICIENT
ATR_HISTORY_INSUFFICIENT
RELATIVE_STRENGTH_BENCHMARK_MISSING
BETA_HISTORY_INSUFFICIENT
PEER_GROUP_INSUFFICIENT
```

### 기업행동

```text
CORPORATE_ACTION_ADJUSTMENT_MISSING
CORPORATE_ACTION_ADJUSTMENT_CONFLICTED
EX_DATE_GAP_EXPLAINED
```

### 상태

```text
SHORT_TERM_REBOUND
VOLATILITY_REGIME_SHIFT
BREAKOUT_UNCONFIRMED
BREAKDOWN_UNCONFIRMED
DEEP_DRAWDOWN
RECOVERY_FROM_DRAWDOWN
```

---

## 26. 핵심 불변식

```text
미래 가격 사용 수 = 0
미래 Corporate Action factor 사용 수 = 0
장중 값을 일일 확정종가로 사용한 수 = 0
현재 종목 Universe를 과거 횡단면 rank에 사용한 수 = 0
현재 benchmark 구성/계열을 과거 계산에 소급한 수 = 0
거래정지 기간을 forward-filled 정상 bar로 생성한 수 = 0
결측 Feature를 0으로 대체한 수 = 0
RAW와 adjusted price basis를 동일 feature 안에서 혼합한 수 = 0
breakout prior-high에 현재 종가를 포함한 수 = 0
현재 거래량을 prior-volume 기준치에 포함한 수 = 0
동일 입력·정책·평가시각이면 동일 Snapshot hash
```

---

## 27. 테스트 전략

### 27.1 Unit Test

#### Return

```text
100 → 110
→ +10%

100 → 90
→ -10%

past = 0
→ None + NON_POSITIVE_PRICE
```

#### Relative Strength

```text
Stock +10%
Benchmark +5%
→ arithmetic excess +5%p
→ relative wealth 약 +4.7619%
```

#### Moving Average

```text
1..20 가격
→ MA20 정확성
```

#### Breakout

```text
prior 20D high = 100
current = 105
→ breakout true
→ distance +5%
```

#### ATR

고정 OHLC fixture를 이용해 hand-calculated TR/ATR과 일치해야 한다.

### 27.2 Temporal Test

```text
A. 15:30 종가 확정
평가시각 15:20
→ 해당 종가 사용 금지

B. 액면분할 정보 known_at = T+2일
T 평가
→ 조정 factor 사용 금지

C. 정정 종가 T+1일 수신
기존 Snapshot
→ 불변
새 replay
→ 새 hash
```

### 27.3 Integration Test

```text
A. 정상 KOSPI 제조업 300거래일
→ 20/60/120/252D momentum 생성
→ trend/vol/volume 생성
→ FINALIZED

B. 신규상장 70거래일
→ 20D/60D 일부 생성
→ 120/252D 없음
→ DEGRADED

C. 30일 거래정지 종목
→ 정지구간 forward-fill 금지
→ SUSPENDED

D. 액면분할
→ RAW gap 존재
→ adjusted momentum 연속성 유지

E. 배당락
→ PRICE_MOMENTUM과 TOTAL_RETURN_MOMENTUM 분리

F. KOSPI +3%, 종목 +1%
→ absolute positive
→ relative negative

G. 종목 +5%, 거래량 3배
→ UP_MOVE_HIGH_VOLUME

H. 종목 +5%, 거래량 0.4배
→ UP_MOVE_LOW_VOLUME

I. 현재 종목이 52주 신고가
→ AT_NEW_HIGH / breakout

J. -30% drawdown 후 -8%까지 회복
→ RECOVERY_FROM_DRAWDOWN 조건 검증

K. 동일 입력 재실행
→ 동일 feature/value/result hash
```

### 27.4 Cross-Section Test

```text
Universe 100종목
→ momentum percentile 0~1 범위
→ 동일 값 tie 처리 deterministic
→ security_id 순서가 달라도 동일 rank/hash
```

### 27.5 Failure Injection

```text
DB transaction 중 장애
→ partial final Snapshot 없음

Benchmark fetch 누락
→ absolute features 보존 가능
→ relative-strength feature BLOCKED
→ 정책상 DEGRADED 여부 확인

Corporate Action factor 충돌
→ adjusted-history feature 차단
→ RAW 당일 feature와 분리
```

---

## 28. 고정 통합 테스트 시나리오

```text
A. 삼성형 정상 대형주 300세션
→ 전체 가격 Feature 생성
→ FINALIZED

B. 20일 강한 상승, KOSPI는 더 강한 상승
→ absolute momentum positive
→ relative strength negative

C. 최근 5일 반등, MA60/120 하락
→ SHORT_TERM_REBOUND
→ UPTREND 오분류 금지

D. 60일 신고가 + relative volume 2.5
→ BREAKOUT_WITH_VOLUME

E. 60일 신고가지만 거래량 0.5
→ BREAKOUT_PRICE_ONLY
→ BREAKOUT_UNCONFIRMED 가능

F. RV20 / RV120 급등
→ VOLATILITY_REGIME_SHIFT

G. 액면분할 당일 RAW -50% 형태
→ adjusted momentum 왜곡 0건

H. 미래에 알려진 분할 factor
→ 과거 Snapshot 적용 0건

I. 거래정지 10일
→ 가격 forward-fill 0건

J. 신규상장 40일
→ long horizon Feature 없음
→ DEGRADED

K. Benchmark 종가 미확정
→ RS feature BLOCKED
→ 절대 Momentum 처리 정책 검증

L. 과거 Universe 80종목, 현재 100종목
→ 과거 percentile은 80종목만 사용

M. 동일 입력·정책·평가시각 재실행
→ 동일 Snapshot hash
```

---

## 29. Signal Engine과의 계약

이 엔진의 출력은 `Feature`이지 `Decision`이 아니다.

금지:

```text
MOM_RET_60D > 20%
→ 즉시 BUY
```

허용 흐름:

```text
Market Behavior Features
+ Fundamental Factors
+ Expectations Features
+ Market Regime
+ Risk Features
        ↓
Signal Generation & Ranking
        ↓
Portfolio Risk / Decision
```

예를 들어 Signal Engine은 향후 다음 조합을 정책으로 사용할 수 있다.

```text
중기 momentum positive
+ KOSPI 대비 RS positive
+ MA trend alignment positive
+ volatility shock 없음
+ volume confirmation
```

하지만 임계값과 최종 점수는 이 엔진이 결정하지 않는다.

---

## 30. Market Regime Engine과의 계약

종목 Feature 일부는 시장 전체 수준으로 집계될 수 있다.

예:

```text
KOSPI 종목 중 MA60 상회 비율
20D positive momentum 비율
52주 신고가 종목 비율
신저가 종목 비율
median realized volatility
up-volume / down-volume breadth
```

이 값은 Market Regime Engine의 입력으로 제공할 수 있으나 시장국면 판정 자체는 별도 엔진의 책임이다.

---

## 31. Risk Engine과의 계약

Risk Engine에 다음을 제공한다.

```text
RV20
ATR_pct
DownsideVol
Current Drawdown
Gap Shock
Negative Shock
DistanceFromHigh
Trend State
Liquidity confirmation references
```

Risk Engine은 이를 이용해:

```text
position sizing 축소
entry blocking
stop distance 참고
portfolio concentration adjustment
```

등을 수행할 수 있다.

---

## 32. Explainability 계약

각 Feature는 설명 가능한 Evidence를 제공해야 한다.

예:

```json
{
  "feature_code": "RS_KOSPI_60D",
  "security_id": "...",
  "value": "0.0831",
  "stock_return_60d": "0.1420",
  "benchmark_return_60d": "0.0544",
  "price_basis": "CA_ADJUSTED_PRICE",
  "start_market_date": "...",
  "end_market_date": "...",
  "benchmark_id": "...",
  "formula_version": "rs_relative_wealth_v1",
  "evidence_hash": "..."
}
```

사용자 보고서에는 숫자만이 아니라 다음 형태의 설명이 가능해야 한다.

```text
60거래일 주가 +14.2%
동기간 KOSPI +5.4%
상대강도 +8.3%
MA20 > MA60 > MA120
단, RV20/RV120 1.9배로 변동성 급등
```

---

## 33. Deterministic Hash

종목 결과 hash 입력에는 최소 다음이 포함된다.

```text
security_id
market_date
evaluation_time
input bar ids/revisions
corporate action snapshot id
benchmark snapshot id
universe snapshot id
policy snapshot id
feature definitions + versions
raw feature values
state values
reason codes
```

Canonical JSON serialization 후 SHA-256을 사용한다.

정렬 순서는 명시적으로 고정한다.

---

## 34. 코드 구조

```text
market_behavior/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── feature_registry.py
├── temporal.py
├── calendars.py
├── series.py
├── adjustments.py
├── validation.py
├── returns.py
├── momentum.py
├── relative_strength.py
├── trend.py
├── breakout.py
├── volatility.py
├── atr.py
├── volume.py
├── drawdown.py
├── gaps.py
├── shocks.py
├── breadth.py
├── cross_section.py
├── normalization.py
├── quality.py
├── reason_codes.py
├── evidence.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

테스트:

```text
tests/market_behavior/
├── test_returns.py
├── test_momentum.py
├── test_relative_strength.py
├── test_trend.py
├── test_breakout.py
├── test_volatility.py
├── test_atr.py
├── test_volume.py
├── test_drawdown.py
├── test_gaps.py
├── test_cross_section.py
├── test_point_in_time.py
├── test_corporate_actions.py
├── test_determinism.py
└── test_integration_market_behavior.py
```

---

## 35. 구현 우선순위

### Phase 1 — 불변 모델

```text
FeatureDefinition
FeatureValue
MarketBehaviorPolicy
InstrumentBehaviorResult
MarketBehaviorSnapshot
ReasonEvent
```

### Phase 2 — DB migration

```text
market_behavior_policies
market_behavior_runs
market_behavior_feature_definitions
market_behavior_feature_values
market_behavior_reason_events
market_behavior_snapshots
market_behavior_snapshot_members
```

### Phase 3 — 가격 계열 기반

```text
Trading Calendar window
FINALIZED bar validation
Point-in-Time adjusted series
```

### Phase 4 — 기본 Feature

```text
returns
momentum
moving averages
trend state
relative strength
```

### Phase 5 — 위험·확인 Feature

```text
realized volatility
ATR
volume confirmation
drawdown
breakout
gap/shock
```

### Phase 6 — 횡단면

```text
peer group
robust scaling
percentile ranking
```

### Phase 7 — Evidence / Hash

```text
canonical manifest
deterministic hash
replay verification
```

### Phase 8 — 통합 테스트

```text
300-session fixed fixtures
corporate action fixtures
IPO fixtures
suspension fixtures
benchmark mismatch fixtures
historical universe fixtures
```

---

## 36. PAPER 초기 정책 제안

정책은 코드 상수가 아니라 별도 Snapshot으로 저장한다.

```text
return horizons        = [5, 20, 60, 120, 252]
skip momentum          = 252D excluding latest 20D
moving averages        = [20, 60, 120, 200]
breakout windows       = [20, 60, 120, 252]
realized vol windows   = [20, 60, 120]
ATR window             = 14
relative volume window = 20
high/low window        = 252
annualization factor   = 252
minimum peer count     = 20
```

이 값은 연구 초기값이며 성과가 좋다는 이유만으로 과거 데이터에 맞춰 비공개 변경하지 않는다.

정책 변경 시:

```text
policy_version 증가
새 Snapshot hash
과거 결과 보존
```

---

## 37. 구현 완료 기준

다음 조건을 모두 만족해야 `Market Behavior Engine v1 IMPLEMENTED`로 변경할 수 있다.

```text
[ ] DB migration 완료
[ ] Feature Registry 구현
[ ] FINALIZED bar temporal guard 구현
[ ] Point-in-Time corporate action adjustment 구현
[ ] 5/20/60/120/252D return 구현
[ ] skip-period momentum 구현
[ ] MA trend state 구현
[ ] benchmark relative strength 구현
[ ] breakout/breakdown 구현
[ ] RV/ATR 구현
[ ] volume confirmation 구현
[ ] drawdown/recovery 구현
[ ] gap/shock 구현
[ ] cross-sectional percentile 구현
[ ] reason code 저장 구현
[ ] immutable Snapshot 구현
[ ] deterministic hash 테스트 통과
[ ] 미래정보 leakage 테스트 통과
[ ] corporate action fixture 통과
[ ] IPO/suspension fixture 통과
[ ] benchmark mismatch fixture 통과
[ ] fixed integration test 통과
```

---

## 38. 전체 ADE 내 위치

```text
38 Fundamental Data & Point-in-Time Financials
        ↓
39 Valuation & Cross-Sectional Factors
        ↓
40 Earnings Expectations / Surprise / Revision
        ↓
41 Market Behavior / Momentum / Trend / Relative Strength
        ↓
Feature Integration
        ↓
Signal Generation & Ranking
        ↓
Market Regime + Portfolio Risk
        ↓
Decision & Position Sizing
        ↓
Paper Trading / Execution
```

41번 엔진으로 ADE는 기업의 `기초체력`, `시장 기대`, `실제 가격행동`을 서로 독립된 근거 계층으로 보유하게 된다.

---

## 39. 최종 설계 원칙

```text
가격이 올랐다는 사실과 매수해야 한다는 결론을 분리한다.

절대 Momentum과 시장 대비 Relative Strength를 분리한다.

단기 반등과 중장기 Trend 전환을 분리한다.

RAW 가격과 Corporate-Action Adjusted 가격의 목적을 분리한다.

거래량은 가격신호를 확인하는 독립 Feature로 유지한다.

고변동성 수익률은 위험조정 Feature를 함께 제공한다.

과거 계산에는 당시 이용 가능했던 가격·벤치마크·기업행동·Universe만 사용한다.

결측·거래정지·신규상장을 정상 데이터로 위장하지 않는다.

모든 결과는 설명 가능하고 재현 가능해야 한다.
```

이 원칙을 v1 구현의 기준으로 고정한다.
