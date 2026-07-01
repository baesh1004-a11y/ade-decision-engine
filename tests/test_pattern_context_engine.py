import pandas as pd

from pattern.context import PatternContextEngine, evaluate_pattern_context


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
                "MA20": close - 1.0,
                "MA60": close - 3.0,
                "MA120": close - 5.0,
                "VOL20_RATIO": 1.5,
            }
        )
    return pd.DataFrame(data)


def test_pattern_context_returns_combined_similarity():
    decision = PatternContextEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(
        _market_data(),
        ticker="NVDA",
        market_regime="BULL",
        vix=18,
    )

    assert decision.engine_version == "pattern-context-v1.0.0"
    assert decision.ticker == "NVDA"
    assert 0 <= decision.context_similarity <= 1
    assert 0 <= decision.combined_similarity <= 1
    assert "return_20d" in decision.expected_returns
    assert "pattern" in decision.to_dict()


def test_bear_high_vix_reduces_context_similarity():
    bull = PatternContextEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(
        _market_data(), market_regime="BULL", vix=15
    )
    bear = PatternContextEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(
        _market_data(), market_regime="BEAR", vix=40
    )

    assert bear.context_similarity < bull.context_similarity


def test_evaluate_pattern_context_backward_compatible_dict():
    result = evaluate_pattern_context(
        _market_data(),
        ticker="NVDA",
        market_regime="SIDEWAY",
        vix=22,
        window=20,
        top_k=3,
        horizons=(5, 10),
    )

    assert isinstance(result, dict)
    assert "combined_similarity" in result
    assert "current_context" in result


def test_insufficient_rows_raise_value_error():
    try:
        PatternContextEngine(window=20, top_k=5, horizons=(5, 10, 20)).evaluate(_market_data(rows=30))
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
