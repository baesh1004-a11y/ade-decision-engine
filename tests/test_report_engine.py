from report.engine import ReportEngine


def _pipeline_result():
    return {
        "ticker": "NVDA",
        "decisions": {
            "candidate": {
                "action": "WATCHLIST",
                "score": 78,
                "grade": "B",
                "confidence": 0.72,
            },
            "probability": {
                "upside_probability": 0.64,
                "raw_upside_probability": 0.72,
                "expected_return": 0.04,
                "risk_reward": 1.8,
                "calibration": {"applied": True},
            },
            "risk": {
                "risk_level": "LOW",
                "trade_allowed": True,
            },
            "position": {
                "recommended_weight": 0.08,
                "shares": 100,
            },
            "explanation": {
                "summary": "NVDA는 관심종목으로 관찰할 만합니다.",
                "metadata": {"evidence_count": 8, "warning_count": 1},
            },
        },
    }


def _backtest_result():
    return {
        "ticker": "NVDA",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "total_return": 0.18,
        "max_drawdown": -0.08,
        "trade_count": 12,
        "win_rate": 0.67,
    }


def _calibration_table():
    return {
        "horizon": "20d",
        "sample_count": 100,
        "global_bias": 0.05,
        "brier_score": 0.21,
        "bins": [{"bin_start": 0.6, "bin_end": 0.7}],
    }


def _learning_update():
    return {
        "sample_count": 50,
        "weights": [
            {"rule_name": "probability", "weight": 1.2},
            {"rule_name": "pattern", "weight": 1.1},
        ],
    }


def test_report_engine_builds_unified_report():
    engine = ReportEngine()
    report = engine.build_report(
        ticker="NVDA",
        pipeline_result=_pipeline_result(),
        backtest_result=_backtest_result(),
        calibration_table=_calibration_table(),
        learning_update=_learning_update(),
    )

    assert report["engine_version"] == "report-engine-v1.0.0"
    assert report["ticker"] == "NVDA"
    assert report["metadata"]["section_count"] >= 6
    assert report["metadata"]["has_backtest"] is True
    assert report["metadata"]["has_calibration"] is True
    assert report["metadata"]["has_learning"] is True


def test_report_renderer_outputs_markdown_and_json():
    engine = ReportEngine()
    report = engine.build_report(ticker="NVDA", pipeline_result=_pipeline_result())

    markdown = engine.markdown(report)
    json_text = engine.json(report)

    assert "# ADE Decision Report - NVDA" in markdown
    assert "Decision Summary" in markdown
    assert "NVDA" in json_text
    assert "sections" in json_text
