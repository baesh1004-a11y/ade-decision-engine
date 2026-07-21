# 22. Portfolio Risk & Exposure Engine v1

## 1. 목적

Portfolio Risk & Exposure Engine은 Signal Generation & Ranking Engine이 만든 후보가 현재 포트폴리오의 위험 한도 안에서 실제로 진입 가능한지 판단한다.

이 엔진은 종목을 추천하지 않으며 주문을 전송하지 않는다. 현재 포트폴리오와 후보 주문을 결합해 예상 포트폴리오를 계산하고, 승인 가능 금액과 차단 사유를 Decision Engine에 전달한다.

## 2. 책임 경계

### 담당

- 종목별 최대 비중 검증
- 총 익스포저와 현금 하한 검증
- 섹터 및 상관 군집 집중도 검증
- 변동성·유동성 기반 주문 한도 계산
- 일일 손실 및 누적 낙폭에 따른 위험 예산 축소
- 시장 국면별 위험 계수 적용
- 후보 주문의 승인·축소·차단
- Risk Snapshot과 평가 근거 저장

### 담당하지 않음

- 종목 후보 생성 또는 순위 결정
- BUY/HOLD/SELL 최종 행동 결정
- 주문 유형·가격 결정
- 브로커 주문 전송
- 체결 상태 추적
- 손익 회계 처리

## 3. 아키텍처

```text
Signal Candidate
      +
Portfolio State
      +
Market Regime / Feature Snapshot
      +
Risk Policy Snapshot
      ↓
Portfolio Risk & Exposure Engine
  ├─ Input Validator
  ├─ Current Exposure Calculator
  ├─ Proposed Portfolio Simulator
  ├─ Hard Limit Guard
  ├─ Volatility Budgeter
  ├─ Liquidity Capacity Calculator
  ├─ Drawdown Guard
  ├─ Regime Risk Multiplier
  └─ Explanation Builder
      ↓
RiskAssessment
      ↓
Decision & Position Sizing Engine
```

## 4. 입력 모델

```python
@dataclass(frozen=True)
class CandidateOrder:
    symbol: str
    side: str
    requested_amount: float
    requested_quantity: int
    reference_price: float
    sector: str | None
    correlation_cluster: str | None
    signal_score: float
    signal_confidence: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: float
    total_equity: float
    total_market_value: float
    daily_pnl_pct: float
    drawdown_pct: float
    positions: tuple[dict, ...]


@dataclass(frozen=True)
class MarketRiskContext:
    regime: str
    regime_confidence: float
    volatility_pct: float
    avg_daily_traded_value: float
    feature_quality: str


@dataclass(frozen=True)
class RiskPolicy:
    max_position_pct: float = 0.10
    min_cash_pct: float = 0.10
    max_total_exposure_pct: float = 0.90
    max_sector_pct: float = 0.30
    max_cluster_pct: float = 0.25
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    max_order_adv_pct: float = 0.01
    max_volatility_pct: float = 0.08
    max_new_entries_per_day: int = 1
    allow_leverage: bool = False
```

## 5. 출력 모델

```python
@dataclass(frozen=True)
class RiskAssessment:
    symbol: str
    status: str
    requested_amount: float
    approved_amount: float
    approved_quantity: int
    risk_score: float
    projected_position_pct: float
    projected_cash_pct: float
    projected_total_exposure_pct: float
    projected_sector_pct: float
    projected_cluster_pct: float
    hard_blocks: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    snapshot_id: str
```

### 상태

| 상태 | 의미 |
|---|---|
| APPROVED | 요청 금액 전부 승인 |
| APPROVED_REDUCED | 일부 금액만 승인 |
| BLOCKED | 신규 주문 차단 |
| FORCE_REDUCE | 기존 포지션 일부 축소 필요 |
| FORCE_EXIT | 기존 포지션 전량 청산 필요 |
| DEGRADED | 품질 저하 상태에서 보수적 결과 반환 |

## 6. 기본 위험 정책

| 항목 | 기본값 | 설명 |
|---|---:|---|
| 종목당 최대 비중 | 10% | 단일 종목 집중 제한 |
| 최소 현금 비중 | 10% | 주문 후에도 유지 |
| 총 익스포저 | 90% | 레버리지 없이 보유 가능 한도 |
| 섹터 최대 비중 | 30% | 동일 섹터 집중 제한 |
| 상관 군집 최대 비중 | 25% | 유사 위험자산 집중 제한 |
| 일일 최대 손실 | 2% | 초과 시 신규 매수 차단 |
| 최대 낙폭 기준 | 10% | 위험 예산 축소 또는 신규 매수 차단 |
| 주문/ADV 비율 | 1% | 일평균 거래대금 대비 주문 한도 |
| 최대 허용 변동성 | 8% | 초과 시 차단 |
| 하루 신규 진입 | 1종목 | 가상투자 정책 |

## 7. 하드 차단 규칙

다음 조건은 점수와 무관하게 주문을 차단한다.

- 가격이 0 이하이거나 수량이 음수
- 현금 또는 총자산이 음수
- 레버리지 발생
- 거래정지 또는 가격 미형성
- Feature Snapshot 품질이 `INVALID`
- `LIQUIDITY_STRESS` 국면에서 신규 매수
- 일일 손실 한도 초과
- 종목 비중, 섹터 비중, 상관 군집 비중 초과
- 총 익스포저 90% 초과
- 주문 후 현금 비중 10% 미만
- 변동성 상한 초과
- 거래대금 하한 미달
- 하루 신규 진입 수 초과

## 8. 핵심 알고리즘

### 8.1 현재 익스포저 계산

```python
position_pct = current_position_value / total_equity
cash_pct = cash / total_equity
total_exposure_pct = total_market_value / total_equity
sector_pct = sector_market_value / total_equity
cluster_pct = cluster_market_value / total_equity
```

### 8.2 최대 주문 가능 금액

```python
position_capacity = (
    total_equity * policy.max_position_pct
    - current_position_value
)

cash_capacity = (
    cash
    - total_equity * policy.min_cash_pct
)

exposure_capacity = (
    total_equity * policy.max_total_exposure_pct
    - total_market_value
)

sector_capacity = (
    total_equity * policy.max_sector_pct
    - sector_market_value
)

cluster_capacity = (
    total_equity * policy.max_cluster_pct
    - cluster_market_value
)

liquidity_capacity = (
    avg_daily_traded_value * policy.max_order_adv_pct
)

max_allowed_amount = max(
    0,
    min(
        requested_amount,
        position_capacity,
        cash_capacity,
        exposure_capacity,
        sector_capacity,
        cluster_capacity,
        liquidity_capacity,
    ),
)
```

### 8.3 시장 국면별 위험 계수

| 국면 | 신규 위험 예산 계수 |
|---|---:|
| BULL | 1.00 |
| RECOVERY | 0.80 |
| SIDEWAY | 0.70 |
| BEAR | 0.40 |
| HIGH_VOL | 0.30 |
| LIQUIDITY_STRESS | 0.00 |
| UNKNOWN | 0.25 |

```python
regime_adjusted_amount = max_allowed_amount * regime_multiplier
```

국면 신뢰도가 낮거나 특징량 품질이 `DEGRADED`이면 추가 감액한다.

### 8.4 변동성 기반 포지션 조정

```python
volatility_multiplier = min(
    1.0,
    target_volatility_pct / max(observed_volatility_pct, 1e-9),
)

volatility_adjusted_amount = (
    regime_adjusted_amount * volatility_multiplier
)
```

### 8.5 낙폭 기반 위험 축소

```python
if daily_pnl_pct <= -policy.max_daily_loss_pct:
    block("DAILY_LOSS_LIMIT")

if drawdown_pct <= -policy.max_drawdown_pct:
    drawdown_multiplier = 0.0
elif drawdown_pct <= -0.07:
    drawdown_multiplier = 0.25
elif drawdown_pct <= -0.04:
    drawdown_multiplier = 0.50
else:
    drawdown_multiplier = 1.0
```

### 8.6 승인 수량 계산

```python
approved_quantity = int(
    final_allowed_amount // reference_price
)
approved_amount = approved_quantity * reference_price
```

소수점 주식은 v1에서 지원하지 않는다.

### 8.7 상태 판정

```python
if hard_blocks:
    status = "BLOCKED"
elif approved_amount <= 0:
    status = "BLOCKED"
elif approved_amount < requested_amount:
    status = "APPROVED_REDUCED"
else:
    status = "APPROVED"
```

## 9. 위험 점수

```python
risk_score = (
    position_risk * 0.20
    + total_exposure_risk * 0.20
    + sector_risk * 0.15
    + cluster_risk * 0.10
    + volatility_risk * 0.15
    + liquidity_risk * 0.10
    + drawdown_risk * 0.10
)
```

- 점수 범위: 0~100
- 하드 차단은 점수와 별개로 우선 적용
- 점수는 설명과 비교를 위한 보조값이며 승인 여부를 단독 결정하지 않음

## 10. 데이터베이스

### `risk_policy`

| 컬럼 | 설명 |
|---|---|
| policy_id | 정책 ID |
| version | 정책 버전 |
| status | DRAFT/APPROVED/ACTIVE/RETIRED |
| mode | BACKTEST/PAPER/LIVE_BLOCKED/LIVE |
| policy_json | 한도 설정 |
| approved_by | 승인자 |
| created_at | 생성 시각 |

### `risk_snapshot`

| 컬럼 | 설명 |
|---|---|
| snapshot_id | 불변 스냅샷 ID |
| run_id | 실행 ID |
| policy_id | 정책 ID |
| portfolio_snapshot_id | 포트폴리오 스냅샷 |
| market_snapshot_id | 시장/특징량 스냅샷 |
| created_at | 생성 시각 |
| snapshot_hash | 무결성 해시 |

### `risk_assessment`

| 컬럼 | 설명 |
|---|---|
| assessment_id | 평가 ID |
| snapshot_id | 위험 스냅샷 ID |
| symbol | 종목 코드 |
| status | 평가 상태 |
| requested_amount | 요청 금액 |
| approved_amount | 승인 금액 |
| approved_quantity | 승인 수량 |
| risk_score | 위험 점수 |
| projected_exposure_json | 예상 익스포저 |
| created_at | 생성 시각 |

### `risk_reason`

| 컬럼 | 설명 |
|---|---|
| reason_id | 사유 ID |
| assessment_id | 평가 ID |
| reason_type | HARD_BLOCK/WARNING/INFO |
| reason_code | 표준 사유 코드 |
| message | 설명 |
| actual_value | 실제 값 |
| limit_value | 한도 값 |

### `exposure_snapshot`

| 컬럼 | 설명 |
|---|---|
| exposure_id | 익스포저 ID |
| snapshot_id | 위험 스냅샷 ID |
| exposure_type | SYMBOL/SECTOR/CLUSTER/TOTAL/CASH |
| exposure_key | 종목·섹터·군집 키 |
| current_pct | 현재 비중 |
| projected_pct | 주문 후 예상 비중 |

## 11. 표준 사유 코드

```text
INVALID_INPUT
NEGATIVE_CASH
LEVERAGE_NOT_ALLOWED
MARKET_DATA_INVALID
TRADING_SUSPENDED
LIQUIDITY_STRESS
DAILY_LOSS_LIMIT
MAX_DRAWDOWN_LIMIT
POSITION_LIMIT
CASH_BUFFER_LIMIT
TOTAL_EXPOSURE_LIMIT
SECTOR_LIMIT
CORRELATION_CLUSTER_LIMIT
VOLATILITY_LIMIT
LIQUIDITY_LIMIT
NEW_ENTRY_LIMIT
REGIME_REDUCED
VOLATILITY_REDUCED
REQUESTED_AMOUNT_REDUCED
```

## 12. 코드 구조

```text
risk/
  __init__.py
  engine.py
  models.py
  policy.py
  exposure.py
  limits.py
  scoring.py
  reasons.py
  repository.py

 tests/
  test_portfolio_risk_engine.py
  test_risk_limits.py
  test_risk_regime.py
  test_risk_liquidity.py
  test_risk_properties.py
```

## 13. 참조 코드

```python
class PortfolioRiskEngine:
    def __init__(self, policy_repository, risk_repository):
        self.policy_repository = policy_repository
        self.risk_repository = risk_repository

    def assess(self, candidate, portfolio, market, policy):
        validate_inputs(candidate, portfolio, market, policy)

        current = calculate_current_exposure(
            portfolio=portfolio,
            candidate=candidate,
        )

        hard_blocks = evaluate_hard_blocks(
            candidate=candidate,
            portfolio=portfolio,
            market=market,
            policy=policy,
            current=current,
        )

        if hard_blocks:
            return self._blocked(candidate, hard_blocks)

        capacities = calculate_capacities(
            candidate=candidate,
            portfolio=portfolio,
            market=market,
            policy=policy,
            current=current,
        )

        allowed = min(capacities.values())
        allowed *= regime_multiplier(market)
        allowed *= volatility_multiplier(market, policy)
        allowed *= drawdown_multiplier(portfolio, policy)

        quantity = max(0, int(allowed // candidate.reference_price))
        approved_amount = quantity * candidate.reference_price

        projected = simulate_projected_exposure(
            candidate=candidate,
            portfolio=portfolio,
            approved_amount=approved_amount,
        )

        assert_projected_limits(projected, policy)

        result = build_assessment(
            candidate=candidate,
            approved_amount=approved_amount,
            approved_quantity=quantity,
            projected=projected,
            capacities=capacities,
        )
        self.risk_repository.save(result)
        return result
```

## 14. 불변식

```text
승인 금액 ≤ 요청 금액
승인 수량 ≥ 0
BLOCKED이면 승인 금액 = 0
BLOCKED이면 승인 수량 = 0
주문 후 현금 비중 ≥ 최소 현금 비중
주문 후 종목 비중 ≤ 종목 한도
주문 후 섹터 비중 ≤ 섹터 한도
주문 후 상관 군집 비중 ≤ 군집 한도
주문 후 총 익스포저 ≤ 총 익스포저 한도
동일 정책·스냅샷·입력은 동일 결과 생성
위험 평가 결과는 원본 정책과 스냅샷을 참조
```

## 15. 테스트 계획

### 단위 테스트

- 정상 후보는 전액 승인
- 종목 비중 한도 초과 시 금액 축소
- 현금 10% 하한 미달 시 금액 축소 또는 차단
- 총 익스포저 90% 초과 차단
- 섹터 30% 초과 차단
- 상관 군집 25% 초과 차단
- 일일 손실 2% 초과 시 신규 매수 차단
- 최대 낙폭 도달 시 신규 매수 차단
- 변동성 상승 시 승인 금액 감소
- 저유동성 종목 승인 금액 감소 또는 차단
- `LIQUIDITY_STRESS`에서 신규 매수 차단
- `UNKNOWN` 국면에서 보수적 감액
- 승인 금액의 정수 수량 절삭

### DB 테스트

- Risk Snapshot은 생성 후 변경 불가
- Assessment와 Reason이 원자적으로 저장
- snapshot hash 재계산 일치
- 정책 버전과 결과 연결 보존
- 중복 assessment ID 차단

### 통합 테스트

- Signal 후보 → Risk 평가 → Decision 입력 생성
- Portfolio Accounting 스냅샷과 평가 결과 일치
- Market Regime 결과가 위험 계수에 반영
- Orchestrator run ID와 Risk Snapshot 연결
- Report Engine에서 차단 사유 조회 가능
- BACKTEST/PAPER 경로에서 동일 입력은 동일 결과

### 속성 기반 테스트

무작위 포트폴리오와 후보 주문을 생성해 다음을 검증한다.

- 승인 결과가 어떤 하드 한도도 위반하지 않음
- 승인 금액이 요청 금액을 초과하지 않음
- 자산과 현금이 증가해도 capacity가 비정상적으로 감소하지 않음
- 한도를 더 엄격하게 변경하면 승인 금액이 증가하지 않음
- 변동성이 증가하면 승인 금액이 증가하지 않음

### 실패 주입 테스트

- Portfolio Snapshot 누락
- Market Snapshot 누락
- 정책 저장소 오류
- DB 트랜잭션 실패
- NaN/Infinity 입력
- 비정상 가격 또는 거래대금
- 동일 실행 중 중복 평가

### 성능 테스트

- 3,000종목 위험 평가 배치
- 100개 보유 포지션과 3,000개 후보 조합
- 1회 배치 평가 목표 5초 이내
- 메모리 사용량과 DB 쓰기량 측정

## 16. 수용 기준

Portfolio Risk & Exposure Engine v1은 다음 조건을 충족하면 구현 완료로 본다.

1. 후보 주문에 대해 승인·축소·차단 결과를 반환한다.
2. 승인 후 예상 포트폴리오가 모든 하드 한도를 준수한다.
3. 종목·섹터·상관 군집·총 익스포저를 함께 평가한다.
4. 변동성·유동성·시장 국면·낙폭이 승인 금액에 반영된다.
5. Risk Snapshot과 모든 사유가 감사 가능하게 저장된다.
6. BACKTEST와 PAPER에서 동일한 계산 코어를 사용한다.
7. 속성 기반 테스트에서 하드 한도 위반이 발생하지 않는다.

## 17. 다음 설계 대상

다음 엔진은 **Decision & Position Sizing Engine v1**이다.

이 엔진은 Signal Ranking과 RiskAssessment를 결합하여 `BUY`, `HOLD`, `REDUCE`, `SELL`, `REJECT`, `NO_ACTION`을 확정하고, 하루 최대 1종목·종목당 최대 10% 정책 안에서 목표 수량과 주문 의도를 생성한다.
