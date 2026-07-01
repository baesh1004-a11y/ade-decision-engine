# ADE DataHub v1

## Purpose

DataHub is the market data layer for ADE.

It ingests historical price data from:

```text
CSV
Yahoo Finance
Future: KIS / KRX / FRED
```

and stores normalized OHLCV data into SQLite.

## Core Files

```text
datahub/models.py
datahub/loaders.py
datahub/yahoo.py
datahub/repository.py
datahub/service.py
database/migrations/005_add_datahub_price_bars.sql
tests/test_datahub.py
```

## Data Model

Required OHLCV format:

```text
Date
Open
High
Low
Close
Volume
Adj Close optional
```

Stored as:

```text
price_bars
```

## Example: Import CSV

```python
from datahub.service import DataHub

hub = DataHub("ade.db")
sync = hub.import_csv("data/NVDA.csv", market="us", ticker="NVDA")
df = hub.get_prices(market="us", ticker="NVDA")
hub.close()
```

## Example: Yahoo Finance

Install dependency:

```bash
pip install yfinance
```

Run:

```python
from datahub.service import DataHub

hub = DataHub("ade.db")
hub.sync_yahoo("NVDA", market="us", start="2020-01-01")
df = hub.get_prices("us", "NVDA")
hub.close()
```

## ADE Pipeline Usage

```python
from core.context import DecisionContext
from core.pipeline import ADEPipeline
from datahub.service import DataHub

hub = DataHub("ade.db")
df = hub.get_prices("us", "NVDA")

context = DecisionContext(
    market="us",
    ticker="NVDA",
    market_data=df,
    account_balance=100_000_000,
    cash=50_000_000,
)

result = ADEPipeline().run(context)
```

## Tests

```bash
pytest tests/test_datahub.py
```

## Next Step

Add broker/data adapters:

```text
KIS Open API
KRX daily data
FRED macro data
Financial statements
```
