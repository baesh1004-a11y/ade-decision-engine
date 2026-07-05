import pandas as pd

from recommendation.engine import RecommendationEngine
from recommendation.models import RecommendationInput


def _data(rows: int = 140, start: float = 100.0, step: float = 0.5, volume_boost: float = 2.0):
    records = []
    for i in range(rows):
        close = start + i * step
        volume = 1_000_000
        if i == rows - 1:
            volume = int(volume * volume_boost)
        records.append({"Close": close, "Volume": volume})
    return pd.DataFrame(records)


def test_recommendation_engine_scores_single_symbol():
    engine = RecommendationEngine()
    item = RecommendationInput(market="us", ticker="NVDA", name="NVIDIA", market_data=_data())

    result = engine.score(item)

    assert result.ticker == "NVDA"
    assert result.final_score >= 70
    assert result.grade in {"A+", "A", "B", "C", "D"}
    assert result.action in {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE", "WATCHLIST", "REJECT"}
    assert "trend" in result.components
    assert result.reasons


def test_recommendation_engine_ranks_top_candidates():
    engine = RecommendationEngine()
    universe = [
        RecommendationInput("us", "NVDA", "NVIDIA", _data(step=0.8, volume_boost=2.5)),
        RecommendationInput("us", "AAPL", "Apple", _data(step=0.2, volume_boost=1.0)),
        RecommendationInput("kr", "005930", "Samsung Electronics", _data(step=-0.1, volume_boost=0.7)),
    ]

    report = engine.rank(universe, top_n=2)

    assert report.total_universe == 3
    assert report.selected_count == 2
    assert report.recommendations[0].final_score >= report.recommendations[1].final_score
    assert report.recommendations[0].ticker == "NVDA"


def test_recommendation_engine_rejects_short_data():
    engine = RecommendationEngine()
    item = RecommendationInput("us", "BAD", "Bad Data", _data(rows=10))

    try:
        engine.score(item)
    except ValueError as exc:
        assert "at least 30 rows" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
