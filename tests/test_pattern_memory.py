import pandas as pd

from pattern.memory import PatternMemoryBuilder, PatternMemoryRepository, build_pattern_memory
from pattern.memory_matching import PatternMemoryMatchingEngine
from pattern.vector import PatternVectorizer


def _market_data(rows: int = 120) -> pd.DataFrame:
    data = []
    for i in range(rows):
        cycle = i % 20
        close = 100 + cycle * 0.5 + i * 0.05
        data.append(
            {
                "Date": f"2024-01-{(i % 28) + 1:02d}",
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + cycle * 10_000,
            }
        )
    return pd.DataFrame(data)


def test_pattern_memory_builder_creates_records():
    records = PatternMemoryBuilder(window=20, horizons=(5, 10, 20)).build_records(
        _market_data(),
        market="us",
        ticker="NVDA",
    )

    assert len(records) > 0
    assert records[0].market == "us"
    assert records[0].ticker == "NVDA"
    assert "return_20d" in records[0].forward_returns
    assert len(records[0].vector) == 20 * 6


def test_repository_upsert_and_count():
    repo = PatternMemoryRepository()
    records = PatternMemoryBuilder(window=20, horizons=(5, 10, 20)).build_records(_market_data(), "us", "NVDA")

    count = repo.bulk_upsert(records[:5])

    assert count == 5
    assert repo.count() == 5
    repo.close()


def test_repository_search_returns_top_matches():
    df = _market_data()
    repo = PatternMemoryRepository()
    build_pattern_memory(df, "us", "NVDA", repo, window=20, horizons=(5, 10, 20))
    query = PatternVectorizer(window=20).transform_latest(df, ticker="NVDA")

    matches = repo.search(query.values, top_k=5, market="us")

    assert len(matches) == 5
    similarities = [match.similarity for match in matches]
    assert similarities == sorted(similarities, reverse=True)
    repo.close()


def test_memory_matching_engine_returns_decision():
    df = _market_data()
    repo = PatternMemoryRepository()
    build_pattern_memory(df, "us", "NVDA", repo, window=20, horizons=(5, 10, 20))

    decision = PatternMemoryMatchingEngine(repo, window=20, top_k=5, horizons=(5, 10, 20)).evaluate(
        df,
        market="us",
        ticker="NVDA",
    )

    assert decision.engine_version == "pattern-memory-matching-v1.0.0"
    assert decision.match_count == 5
    assert "return_20d" in decision.expected_returns
    assert "win_rate_20d" in decision.win_rates
    repo.close()


def test_memory_builder_requires_enough_rows():
    try:
        PatternMemoryBuilder(window=20, horizons=(5, 10, 20)).build_records(_market_data(rows=30), "us", "NVDA")
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
