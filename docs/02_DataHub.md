# 02. DataHub Engine

## Purpose

DataHub Engine은 ADE의 시장 데이터 신뢰 계층이다. CSV, Yahoo, KIS 등 여러 소스에서 가격 데이터를 가져와 동일한 `PriceBar` 구조로 정규화하고 저장한다.

## Inputs

- CSV OHLCV data
- Yahoo price data
- KIS price data
- symbol, market, date range

## Outputs

- normalized `PriceBar`
- persisted `price_bars`
- DataFrame for downstream engines

## Architecture

```text
CSV / Yahoo / KIS
  ↓
Downloader / Adapter
  ↓
PriceBar Normalizer
  ↓
price_bars Repository
  ↓
Data Quality Engine
```

## Database: price_bars

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | row id |
| symbol | TEXT | ticker or stock code |
| market | TEXT | KR/US/etc |
| date | DATE | trading date |
| open | REAL | open price |
| high | REAL | high price |
| low | REAL | low price |
| close | REAL | close price |
| volume | INTEGER | volume |
| source | TEXT | csv/yahoo/kis |
| created_at | DATETIME | inserted time |

## Key Rules

- DataHub does not make trading decisions.
- DataHub only collects, normalizes, and stores data.
- Any data used by Signal Engine must pass Data Quality validation.

## Reference API

```python
hub.sync_csv(path, symbol="005930", market="KR")
hub.sync_yahoo("AAPL", start="2024-01-01", end="2026-07-01")
hub.sync_kis("005930", start="20240101", end="20260701")
hub.load_prices("005930")
```
