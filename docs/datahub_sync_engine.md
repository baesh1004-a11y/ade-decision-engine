# ADE DataHub Sync Engine v1

## Purpose

DataHub Sync Engine v1 is ADE's normalized market-data backbone.

It turns multiple raw data sources into one trusted price stream for:

```text
Candidate Engine
Decision Engine
Exit Engine
Risk Engine
Backtest Engine
Report Engine
```

The first design objective is not speed. It is repeatability, auditability, and data quality.

## Architecture

```text
CSV / Yahoo / KIS / Future Crypto
          │
          ▼
Source Adapter
          │
          ▼
PriceBar Normalization
          │
          ▼
SQLite price_bars
          │
          ├── fetch_dataframe()
          │
          ├── validate_prices()
          │
          └── ADEPipeline
```

## Engine Boundary

DataHub Sync Engine must do:

```text
- ingest raw OHLCV
- normalize field names
- normalize dates
- normalize numeric values
- upsert deterministic PriceBar records
- return source/date sync metadata
- validate ADE usability
```

DataHub Sync Engine must not do:

```text
- buy/sell decisioning
- position sizing
- order placement
- portfolio allocation
- discretionary interpretation
```

This separation keeps DataHub as ADE's source-of-truth layer, not another decision engine.

## Current Database

The existing table remains the canonical v1 schema:

```text
price_bars
- id
- market
- ticker
- trade_date
- open
- high
- low
- close
- volume
- adjusted_close
- source
- created_at

Unique key:
- market
- ticker
- trade_date
- source
```

The unique key is important because the same ticker/date may be imported repeatedly. Re-imports should update the same row, not duplicate it.

## Source Rules

```text
CSV        source=csv or dataframe
Yahoo      source=yahoo
KIS        source=kis
Future     source=exchange-specific adapter name
```

Market codes:

```text
us = United States listed equities/ETFs
kr = Korean listed equities/ETFs
crypto = crypto assets
```

## Public API

### CSV/DataFrame

```python
hub = DataHub(db_path="ade.db")
hub.import_dataframe(df, market="us", ticker="NVDA")
hub.import_csv("nvda.csv", market="us", ticker="NVDA")
```

### Yahoo

```python
hub.sync_yahoo("NVDA", market="us", start="2024-01-01", end="2026-07-01")
```

### KIS

```python
hub.sync_kis("005930", start="20240101", end="20260701")
```

KIS dates stay compact at the adapter boundary because KIS uses `YYYYMMDD`. The adapter converts them to `YYYY-MM-DD` before storage.

### Quality Check

```python
report = hub.validate_prices(market="kr", ticker="005930", source="kis")

if report.is_usable:
    df = hub.get_prices(market="kr", ticker="005930", source="kis")
```

## Data Quality Algorithm

```text
Input: normalized OHLCV dataframe

1. Check required columns
   - Date, Open, High, Low, Close, Volume

2. Check dataset is not empty

3. Parse dates
   - reject invalid dates
   - sort dates
   - compute start/end

4. Detect duplicate trade dates

5. Check minimum history length
   - warning if below 60 rows

6. Convert numeric OHLCV fields
   - reject excessive missing numeric values

7. Validate OHLC consistency
   - open/high/low/close > 0
   - high >= open/close/low
   - low <= open/close/high

8. Validate volume
   - reject negative volume

9. Detect large date gaps
   - warning if calendar gap >= 10 days

10. Return DataQualityReport
```

## Quality Severity

```text
ERROR
- Missing required columns
- Empty dataset
- Invalid dates
- Duplicate dates
- Missing numeric values above threshold
- Impossible OHLC ranges
- Negative volume

WARNING
- Short history
- Large date gap
```

`is_usable` is false only when at least one ERROR exists.

## Why This Matters

ADE indicators and signals are only as good as the input data.

Bad input creates false confidence:

```text
wrong OHLCV
   ↓
wrong MA/RSI/MACD/ATR
   ↓
wrong candidate score
   ↓
wrong buy/sell decision
```

So DataHub quality checks are now part of the decision safety layer.

## v1 Code Added

```text
datahub/quality.py
- DataQualityIssue
- DataQualityReport
- PriceDataQualityValidator

datahub/service.py
- sync_kis()
- validate_prices()
- KIS env fallback

tests/test_datahub_quality.py
- valid data acceptance
- invalid OHLC rejection
- short-history warning
- DataHub validate_prices integration
- KIS sync injected downloader test
```

## Test Plan

```text
Unit Tests
- validator accepts valid data
- validator rejects missing columns
- validator rejects invalid dates
- validator rejects duplicate dates
- validator rejects impossible OHLC ranges
- validator rejects negative volume
- validator warns on short history
- validator warns on large date gaps

Integration Tests
- import_dataframe -> validate_prices
- sync_kis with injected downloader -> get_prices
- sync_yahoo -> validate_prices, network-enabled/manual only

Safety Tests
- KIS sync without env raises clear ValueError
- live broker order still blocked in broker layer
- invalid raw data never enters ADEPipeline without explicit override
```

## Next Engine to Design

The next recommended engine is:

```text
Portfolio State Engine v1
```

Purpose:

```text
cash + holdings + pending orders + market prices
        ↓
trusted account state snapshot
        ↓
DecisionContext / ExitDecisionEngine / RiskEngine
```

This should come before full auto-trading because ADE needs a reliable account-state model before it can size or execute orders safely.
