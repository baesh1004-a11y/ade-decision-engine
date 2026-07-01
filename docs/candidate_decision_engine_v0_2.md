# ADE Candidate Decision Engine v0.2

## 1. Purpose

Candidate Decision Engine은 ADE의 첫 번째 핵심 엔진이다. 목적은 한국/미국 주식의 일봉 OHLCV 데이터와 기술지표를 입력받아 현재 시점이 매수 후보인지, 관찰 대상인지, 제외 대상인지 판단하는 것이다.

이 엔진은 최종 자동매매 모델이 아니라, 사람이 검토할 수 있는 설명 가능한 1차 후보 선별 엔진이다.

## 2. Architecture

```text
OHLCV Collector
    ↓
Indicator Pipeline
    - MA20 / MA60 / MA120
    - VOL20_RATIO
    - Candle body structure
    - STO 5-3-3 / 10-6-6 / 20-12-12
    ↓
Candidate Decision Engine
    - Rule scoring
    - Risk flags
    - Grade mapping
    - Action mapping
    - Confidence score
    ↓
Decision Output
    - CLI report
    - Backtest signal table
    - candidate_decisions DB table
```

## 3. Input Data

Required raw fields:

| Field | Meaning |
|---|---|
| Date | Trading date |
| Open | Open price |
| High | High price |
| Low | Low price |
| Close | Close price |
| Volume | Trading volume |

Required indicator fields:

| Field | Meaning |
|---|---|
| MA20 | 20-day moving average |
| MA60 | 60-day moving average |
| MA120 | 120-day moving average |
| VOL20_RATIO | Current volume / 20-day average volume |
| BODY_RATIO | Candle body / full candle range |
| IS_BULLISH | Close > Open |
| STO533_K / STO533_D | Short stochastic |
| STO1066_K / STO1066_D | Medium stochastic |
| STO201212_K / STO201212_D | Long stochastic |

## 4. Algorithm

### 4.1 Score Rules

| Rule | Condition | Points |
|---|---:|---:|
| Volume expansion 2x | VOL20_RATIO >= 2 | 15 |
| Volume expansion 5x | VOL20_RATIO >= 5 | 10 |
| Volume expansion 10x | VOL20_RATIO >= 10 | 10 |
| Bullish body | IS_BULLISH and BODY_RATIO >= 0.5 | 15 |
| STO short rebound | STO533_K < 30 and STO533_K > STO533_D | 15 |
| STO medium low zone | STO1066_K < 40 | 10 |
| STO long not overheated | STO201212_K < 50 | 10 |
| Above MA120 | Close >= MA120 | 10 |
| Moving average alignment | MA20 > MA60 > MA120 | 10 |
| Above MA20 | Close >= MA20 | 5 |

Maximum score is capped at 100.

### 4.2 Grade Mapping

| Score | Grade |
|---:|---|
| 85–100 | A |
| 70–84 | B |
| 55–69 | C |
| 40–54 | D |
| 0–39 | F |

### 4.3 Risk Gates

Risk flags:

| Flag | Condition |
|---|---|
| Close below MA120 | Close < MA120 |
| Abnormal volume spike | VOL20_RATIO >= 15 |
| Short stochastic overheated | STO533_K >= 85 |
| Strong bearish candle body | not IS_BULLISH and BODY_RATIO >= 0.5 |

Risk level:

| Risk Level | Rule |
|---|---|
| HIGH | Strong bearish candle body or abnormal volume spike |
| MEDIUM | Any other risk flag exists |
| LOW | No risk flag |

Action mapping:

| Condition | Action |
|---|---|
| Risk level HIGH | WATCH |
| Score >= 85 | BUY_CANDIDATE |
| Score >= 70 | WATCHLIST |
| Score >= 55 | NEUTRAL |
| Else | REJECT |

### 4.4 Confidence

Confidence is not a price-rise probability. It is an evidence-density score.

```text
confidence = score / 100 - risk_penalty
risk_penalty:
  LOW    = 0.00
  MEDIUM = 0.15
  HIGH   = 0.35
```

The value is clipped to the range 0.0–1.0.

## 5. Database Design

Core table: `candidate_decisions`

```sql
CREATE TABLE IF NOT EXISTS candidate_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    score INTEGER NOT NULL,
    grade TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    close REAL NOT NULL,
    risk_level TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market, ticker, trade_date, engine_version)
);
```

Design principle:

- `engine_version` is mandatory so future rule changes can be compared.
- `risk_flags` and `reasons` are stored as serialized text in SQLite v0.2.
- PostgreSQL migration can later convert these to JSONB.

## 6. Code Files

| File | Role |
|---|---|
| `strategy/candidate.py` | Candidate decision engine |
| `indicators/pipeline.py` | Indicator input generator |
| `backtest/engine.py` | Historical validation and future returns |
| `backtest/report.py` | Text report formatter |
| `database/schema.sql` | SQLite-first schema |
| `tests/test_candidate_engine.py` | Unit tests |

## 7. Test Plan

### 7.1 Unit Tests

| Test | Purpose |
|---|---|
| structured decision test | Verifies score, grade, action, risk level, rule hits |
| backward compatibility test | Ensures `score_latest()` still returns dict payload |
| high-risk gate test | Ensures bearish/abnormal volume forces WATCH |
| empty dataframe test | Ensures invalid input raises ValueError |

Run:

```bash
pytest tests/test_candidate_engine.py
```

### 7.2 Integration Tests

Run Korean default ticker:

```bash
python main.py
```

Run US default ticker:

```bash
python main.py --market us --ticker NVDA
```

Expected output sections:

```text
Latest Candidate Decision
Backtest Summary
```

### 7.3 Backtest Validation

Minimum acceptance criteria:

| Metric | Target |
|---|---:|
| Signals | > 10 over 10 years |
| 20D win rate | > 50% preferred |
| Avg 20D return | Positive preferred |
| Avg MDD | Should be lower than average return magnitude |
| Profit factor | > 1.0 preferred |

## 8. Next Engine Candidate

The next engine should be Pattern Similarity Engine:

```text
current chart vector
    ↓
historical vector library
    ↓
similarity search
    ↓
future return distribution
    ↓
probability of up / sideways / down
```

This will convert ADE from a rule-based screener into a probabilistic decision engine.
