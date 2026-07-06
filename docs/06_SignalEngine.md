# 06. Signal Engine

## Purpose

Signal Engine은 시장 데이터에서 종목별 매수 후보 신호를 생성한다. 이 엔진은 주문을 실행하지 않으며, 리스크 한도를 최종 판단하지 않는다.

## Current Implementation vs Target Design

현재 저장소에는 `strategy/candidate.py` 기반의 Candidate Decision Engine이 실제 신호 생성 역할을 수행한다.

| 구분 | 현재 구현 | 목표 설계 |
|---|---|---|
| 이름 | Candidate Decision Engine | Signal Engine v1.0 |
| 방식 | 규칙 점수 합산 | 구성요소별 점수 분리 후 가중 합산 |
| 출력 | 후보/관망/중립/거절 | STRONG_BUY/BUY_CANDIDATE/WATCH/IGNORE |
| 구성 | 거래량, 캔들, STO, 이동평균 | Trend, Momentum, Volume, Volatility, Portfolio |
| 상태 | 구현 존재 | 설계 완료, 구현 예정 |

## Current Candidate Algorithm

현재 구현은 다음 조건을 점수화한다.

| 항목 | 조건 | 점수 |
|---|---|---:|
| 거래량 증가 | VOL20_RATIO >= 2 | +15 |
| 거래량 급증 | VOL20_RATIO >= 5 | +10 |
| 거래량 폭증 | VOL20_RATIO >= 10 | +10 |
| 강한 양봉 | IS_BULLISH and BODY_RATIO >= 0.5 | +15 |
| 단기 STO 반등 | STO533_K < 30 and K > D | +15 |
| 중기 STO 저점 | STO1066_K < 40 | +10 |
| 장기 STO 안정 | STO201212_K < 50 | +10 |
| 120일선 위 | Close >= MA120 | +10 |
| 정배열 | MA20 > MA60 > MA120 | +10 |
| 20일선 위 | Close >= MA20 | +5 |

현재 판정 기준:

| 점수 | 현재 판정 |
|---:|---|
| >= 85 | BUY_CANDIDATE |
| 70-84 | WATCHLIST |
| 55-69 | NEUTRAL |
| < 55 | REJECT |

`risk_level == HIGH`이면 높은 점수라도 WATCH 수준으로 제한한다.

## Target Inputs

- price bars
- indicators
- volume data
- volatility metrics
- optional portfolio state

## Target Output

```python
Signal(
    symbol="005930",
    score=72.5,
    action="BUY_CANDIDATE",
    trend_score=80,
    momentum_score=70,
    volume_score=65,
    volatility_score=75,
    portfolio_score=60,
)
```

## Target Architecture

```text
DataHub / Indicators
  ↓
Trend Signal
Momentum Signal
Volume Signal
Volatility Signal
Portfolio Filter
  ↓
SignalScore
  ↓
Risk Engine
```

## Target Score Formula

```python
signal_score = (
    trend_score * 0.30
    + momentum_score * 0.25
    + volume_score * 0.20
    + volatility_score * 0.15
    + portfolio_score * 0.10
)
```

## Target Classification

| Score | Action |
|---:|---|
| >= 80 | STRONG_BUY |
| 65-79 | BUY_CANDIDATE |
| 50-64 | WATCH |
| < 50 | IGNORE |

## Database

| Table | Purpose |
|---|---|
| signal_runs | signal execution history |
| signals | final signal by symbol |
| signal_components | component scores |

## Migration Plan

1. 기존 `strategy/candidate.py`는 유지한다.
2. 신규 `strategy/signal.py`를 추가한다.
3. Trend/Momentum/Volume/Volatility/Portfolio 점수를 분리한다.
4. 기존 `score_latest()`는 호환 래퍼로 유지한다.
5. `tests/test_signal_engine.py`를 추가한다.
6. 파이프라인에서는 Candidate와 Signal 결과를 병행 기록한 뒤 점진적으로 전환한다.

## Test Plan

- current candidate score regression test
- rising trend produces high trend score
- volume surge increases volume score
- overheated momentum is penalized
- excessive volatility is penalized
- insufficient history returns IGNORE
- boundary scores classify correctly at 80, 65, and 50
- HIGH risk level caps candidate outcome
