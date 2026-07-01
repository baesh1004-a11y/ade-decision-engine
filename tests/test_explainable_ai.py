from explain.engine import ExplainableAIEngine, explain_decision
from explain.formatter import ExplanationFormatter


def _decisions():
    return {
        "pattern_memory": {"records": 100, "backend": "sqlite"},
        "pattern": {
            "engine_version": "pattern-memory-matching-v1.0.0",
            "match_count": 10,
            "avg_similarity": 0.82,
            "risk_flags": [],
        },
        "pattern_context": {
            "combined_similarity": 0.79,
            "risk_flags": [],
        },
        "probability": {
            "upside_probability": 0.64,
            "raw_upside_probability": 0.72,
            "expected_return": 0.04,
            "risk_reward": 1.8,
            "risk_flags": [],
        },
        "candidate": {
            "score": 78,
            "grade": "B",
            "action": "WATCHLIST",
            "confidence": 0.72,
            "risk_flags": [],
        },
        "risk": {
            "risk_level": "LOW",
            "trade_allowed": True,
            "risk_flags": [],
        },
        "position": {
            "recommended_weight": 0.08,
        },
        "entry": {
            "action": "BUY_NOW",
            "risk_flags": [],
        },
    }


def test_explainable_ai_generates_report():
    report = ExplainableAIEngine().explain("NVDA", _decisions())

    assert report.engine_version == "explainable-ai-v1.0.0"
    assert report.ticker == "NVDA"
    assert report.decision == "WATCHLIST"
    assert report.confidence == 0.72
    assert len(report.evidence) > 0
    assert "NVDA" in report.summary
    assert "핵심 근거" in report.narrative


def test_explain_decision_helper_returns_dict():
    report = explain_decision("NVDA", _decisions())

    assert isinstance(report, dict)
    assert report["ticker"] == "NVDA"
    assert "evidence" in report


def test_formatter_outputs_json_and_markdown():
    report = ExplainableAIEngine().explain("NVDA", _decisions()).to_dict()
    formatter = ExplanationFormatter()

    json_text = formatter.to_json(report)
    markdown = formatter.to_markdown(report)

    assert "NVDA" in json_text
    assert "ADE 설명 리포트" in markdown
    assert "근거" in markdown
