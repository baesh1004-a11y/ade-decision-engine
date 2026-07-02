# ADE KIS Open API Integration v1

## Purpose

KIS Open API is ADE's first production-grade broker/data adapter.

It gives ADE two missing capabilities:

```text
1. Eye  = current/ historical market data
2. Hand = account, balance, order, execution status
```

DataHub v1 already supports CSV and Yahoo Finance. KIS v1 adds the Korean broker path while keeping the same ADE price model.

## Current ADE Fit

Existing DataHub stores normalized OHLCV in `price_bars`.

```text
CSV / Yahoo / KIS
        ↓
PriceBar normalization
        ↓
price_bars SQLite table
        ↓
DataFrame
        ↓
ADEPipeline
```

KIS should not directly change the decision engines. It should only feed data and broker state into ADE.

## Official Reference

KIS Developers describes the Open API portal, REST usage, token issuance with account App Key/App Secret, WebSocket real-time reception, API application, GitHub sample code, and test bed. The portal also exposes notices, including API service maintenance and call-limit notices. See the KIS Developers portal for the latest endpoint and TR-ID details before live use.

## v1 Scope

```text
Data Adapter
- OAuth token issuance
- Korean domestic stock current price
- Korean domestic stock daily OHLCV
- PriceBar normalization

Broker Adapter
- Cash lookup
- Position lookup
- Dry-run order object
- Paper-trading order path
- Live-order hard block by default
```

## Out of Scope for v1

```text
- real live order execution
- overseas stocks through KIS
- WebSocket streaming
- order correction/cancel
- partial-fill reconciliation
- tax/fee reconciliation
- multi-account operation
```

## New Files

```text
broker/__init__.py
broker/base.py
broker/kis.py
datahub/kis.py
tests/test_kis_price_adapter.py
docs/kis_openapi_integration.md
```

## Environment Variables

Secrets must never be committed to GitHub.

Use `.env` or a server secret manager.

```bash
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
KIS_ACCOUNT_PRODUCT_CODE=01
KIS_ENV=paper
```

## Architecture

```text
                    ADEPipeline
                         ▲
                         │ DecisionContext
                         │
DataHub ◀──── price_bars SQLite
  ▲
  │
  ├─ CSV loader
  ├─ Yahoo downloader
  └─ KISPriceDownloader
        ├─ token
        ├─ quote
        └─ daily chart

Broker Layer
  └─ KISBrokerAdapter
        ├─ token
        ├─ cash
        ├─ positions
        ├─ dry-run order
        └─ paper order
```

## Database Impact

No new table is required for KIS price history because `price_bars` already has the needed shape.

Current table:

```text
price_bars
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
```

KIS rows should be stored as:

```text
market = kr
source = kis
```

Future order/execution storage should use separate tables:

```text
broker_orders
broker_executions
broker_positions_snapshot
```

These are intentionally not added in v1 because live trading is not enabled yet.

## Algorithm

### Price Sync

```text
Input: ticker, start, end
1. Load KIS credentials from env
2. Request OAuth access token
3. Call daily OHLCV endpoint
4. Convert KIS compact date YYYYMMDD to YYYY-MM-DD
5. Convert string numeric values to float
6. Create PriceBar records
7. Upsert into price_bars
8. Run ADEPipeline with retrieved DataFrame
```

### Broker State Sync

```text
Input: account
1. Load KIS credentials from env
2. Request OAuth access token
3. Request balance/position data
4. Normalize holdings to BrokerPosition
5. Map holdings into DecisionContext.holdings
6. Map cash into DecisionContext.cash
```

### Order Guard

```text
ADE signal
    ↓
Risk Engine
    ↓
Position Sizing
    ↓
BrokerOrder
    ↓
If dry_run=True: no broker call
If paper=True: paper order only
If live=True: blocked in v1
```

## Code Usage

### KIS Daily Price Download

```python
from datahub.kis import KISPriceDownloader

kis = KISPriceDownloader(
    app_key="...",
    app_secret="...",
    environment="paper",
)
records = kis.download_daily_bars("005930", start="20240101", end="20260701")
```

### Broker Adapter

```python
from broker.base import BrokerConfig, BrokerOrder
from broker.kis import KISBrokerAdapter

config = BrokerConfig(
    app_key="...",
    app_secret="...",
    account_no="...",
    account_product_code="01",
    environment="paper",
)

broker = KISBrokerAdapter(config)
cash = broker.get_cash()
positions = broker.get_positions()

result = broker.place_order(
    BrokerOrder(
        market="kr",
        ticker="005930",
        side="BUY",
        quantity=1,
        dry_run=True,
    )
)
```

## Test Plan

```text
Unit Tests
- KIS daily rows normalize to PriceBar
- KIS compact date conversion
- KIS numeric string conversion
- OAuth token is cached
- dry-run order never calls broker endpoint

Integration Tests, paper only
- token issuance succeeds
- quote request succeeds
- daily chart request succeeds
- balance request succeeds
- dry-run decision path succeeds
- paper order succeeds only after explicit manual approval

Safety Tests
- live order blocked in v1
- invalid quantity rejected
- invalid order type rejected
- non-KR order rejected by domestic KIS adapter
```

## Next Implementation Step

Update `datahub/service.py` to expose:

```python
DataHub.sync_kis("005930", start="20240101", end="20260701")
```

Then add a paper-trading execution runner:

```text
scripts/run_kis_paper_decision.py
```

That script should:

```text
1. fetch KIS prices
2. save to DataHub
3. run ADEPipeline
4. produce BUY/WATCH/REJECT
5. create BrokerOrder only if paper mode is explicit
```
