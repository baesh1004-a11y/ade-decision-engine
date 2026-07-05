# ADE Recommendation Engine v1

## Purpose

Recommendation Engine v1 ranks a multi-market stock universe and produces explainable Top-N buy candidates.

Target universe:

```text
Korea: KOSPI/KOSDAQ selected large-cap universe
US: S&P500/NASDAQ100 selected universe
```

The first implementation is data-source agnostic: it can rank any symbol when given OHLCV-style price data.

## Files

```text
recommendation/__init__.py
recommendation/models.py
recommendation/engine.py
tests/test_recommendation_engine.py
```

## Score Components

```text
Trend       20
Volume      15
Momentum    20
Volatility  10
Pattern     15
Risk        10
Confidence  10
Total      100
```

## Output Actions

```text
STRONG_BUY_CANDIDATE
BUY_CANDIDATE
WATCHLIST
REJECT
```

## Example

```python
import pandas as pd

from recommendation.engine import RecommendationEngine
from recommendation.models import RecommendationInput

items = [
    RecommendationInput(
        market="us",
        ticker="NVDA",
        name="NVIDIA",
        market_data=pd.read_csv("data/NVDA.csv"),
    ),
]

report = RecommendationEngine().rank(items, top_n=10)
print(report.to_dict())
```

## Next Step

Recommendation Engine v1 is the ranking core. Next modules should add:

```text
1. Universe loader: KR top 200 + US top 200
2. DataHub batch price loading
3. Daily Top 10 report
4. FastAPI endpoint /recommendations
5. KIS paper-trading connection for selected symbols
```
