from __future__ import annotations

from typing import Any

from report.builder import ADEReportBuilder
from report.renderer import ReportRenderer


class ReportEngine:
    """Unified ADE Report Engine."""

    def __init__(self) -> None:
        self.builder = ADEReportBuilder()
        self.renderer = ReportRenderer()

    def build_report(
        self,
        ticker: str,
        pipeline_result: dict[str, Any] | None = None,
        backtest_result: dict[str, Any] | None = None,
        calibration_table: dict[str, Any] | None = None,
        learning_update: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.builder.build(
            ticker=ticker,
            pipeline_result=pipeline_result,
            backtest_result=backtest_result,
            calibration_table=calibration_table,
            learning_update=learning_update,
        ).to_dict()

    def markdown(self, report: dict[str, Any]) -> str:
        return self.renderer.to_markdown(report)

    def json(self, report: dict[str, Any]) -> str:
        return self.renderer.to_json(report)
