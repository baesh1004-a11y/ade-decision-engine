import pandas as pd

from pattern.matching import PatternMatchingEngine, evaluate_pattern_match
from pattern.vector import PatternVectorizer, vectorize_latest


def _market_data(rows: int = 120) -> pd.DataFrame:
    data = []
    for i in range(rows):
        cycle = i % 20
        close = 100 + cycle * 0.5 + i * 0.05
        data.append(
            {
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + cycle * 10_000,
            }
        )
    return pd.DataFrame(data)


def test_vectorizer_creates_fixed_length_vector():
    df = _market_data()
    vector = PatternVectorizer(window=20).transform_latest(df, ticker="NVDA")

    assert vector.vector_version == "pattern-vector-v1.0.0"
    assert vector.ticker == "NVDA"
    assert vector.window == 20
    assert len(vector.values) == 20 * 6


def test_vectorize_latest_backward_compatible_dict():
    result = vectorize_latest(_market_data(), ticker="NVDA", window=20)

    assert isinstance(result, dict)
    assert result["ticker"] == "NVDA"
    assert "values" in result


def test_pattern_matching_returns_top_matches_and_expected_returns():
    df = _market_data()
    decision = PatternMatchingEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(df, ticker="NVDA")

    assert decision.engine_version == "pattern-matching-v1.0.0"
    assert decision.ticker == "NVDA"
    assert decision.match_count == 5
    assert len(decision.matches) == 5
    assert "return_20d" in decision.expected_returns
    assert "win_rate_20d" in decision.win_rates


def test_matches_are_sorted_by_similarity():
    df = _market_data()
    decision = PatternMatchingEngine(window=20, top_k=5, horizons=(5, 10)).evaluate(df, ticker="NVDA")
    similarities = [match["similarity"] for match in decision.matches]

    assert similarities == sorted(similarities, reverse=True)


def test_evaluate_pattern_match_backward_compatible_dict():
    result = evaluate_pattern_match(_market_data(), ticker="NVDA", window=20, top_k=3, horizons=(5, 10))

    assert isinstance(result, dict)
    assert result["match_count"] == 3
    assert "expected_returns" in result


def test_low_similarity_or_negative_expectation_can_flag_risk():
    df = _market_data()
    df.loc[df.index[-20:], "Close"] = [200 + i * 5 for i in range(20)]

    decision = PatternMatchingEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(df, ticker="NVDA")

    assert isinstance(decision.risk_flags, list)


def test_not_enough_rows_raises_value_error():
    try:
        PatternMatchingEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(_market_data(rows=30))
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_missing_required_columns_raises_value_error():
    df = _market_data().drop(columns=["Volume"])

    try:
        PatternMatchingEngine(window=20).evaluate(df)
    except ValueError as exc:
        assert "Volume" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
