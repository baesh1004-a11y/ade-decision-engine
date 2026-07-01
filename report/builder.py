from __future__ import annotations

from typing import Any

from report.models import ADEReport, ReportSection


ENGINE_VERSION = "report-engine-v1.0.0"


class ADEReportBuilder:
    """Build unified ADE reports from pipeline, backtest, calibration, and learning outputs."""

    def build(
        self,
        ticker: str,
        pipeline_result: dict[str, Any] | None = None,
        backtest_result: dict[str, Any] | None = None,
        calibration_table: dict[str, Any] | None = None,
        learning_update: dict[str, Any] | None = None,
    ) -> ADEReport:
        sections: list[ReportSection] = []
        if pipeline_result:
            sections.extend(self._pipeline_sections(pipeline_result))
        if backtest_result:
            sections.append(self._backtest_section(backtest_result))
        if calibration_table:
            sections.append(self._calibration_section(calibration_table))
        if learning_update:
            sections.append(self._learning_section(learning_update))

        summary = self._summary(ticker, pipeline_result, backtest_result, calibration_table, learning_update)
        return ADEReport(
            engine_version=ENGINE_VERSION,
            title=f"ADE Decision Report - {ticker}",
            ticker=ticker,
            summary=summary,
            sections=[section.to_dict() for section in sections],
            metadata={
                "section_count": len(sections),
                "has_pipeline": pipeline_result is not None,
                "has_backtest": backtest_result is not None,
                "has_calibration": calibration_table is not None,
                "has_learning": learning_update is not None,
            },
        )

    def _pipeline_sections(self, pipeline_result: dict[str, Any]) -> list[ReportSection]:
        decisions = pipeline_result.get("decisions", pipeline_result)
        candidate = decisions.get("candidate", {}) or {}
        probability = decisions.get("probability", {}) or {}
        risk = decisions.get("risk", {}) or {}
        position = decisions.get("position", {}) or {}
        explanation = decisions.get("explanation", {}) or {}

        sections = [
            ReportSection(
                title="Decision Summary",
                summary="ADE 최종 판단 요약",
                items=[
                    f"Action: {candidate.get('action', 'UNKNOWN')}",
                    f"Score: {candidate.get('score', '-')}",
                    f"Grade: {candidate.get('grade', '-')}",
                    f"Confidence: {self._pct(candidate.get('confidence', 0.0))}",
                ],
                data=candidate,
            ),
            ReportSection(
                title="Probability & Calibration",
                summary="상승확률, 기대수익률, 보정 여부 요약",
                items=[
                    f"Upside Probability: {self._pct(probability.get('upside_probability', 0.0))}",
                    f"Raw Probability: {self._pct(probability.get('raw_upside_probability', probability.get('upside_probability', 0.0)))}",
                    f"Expected Return: {self._pct(probability.get('expected_return', 0.0))}",
                    f"Risk Reward: {probability.get('risk_reward', '-')}",
                    f"Calibration Applied: {probability.get('calibration', {}).get('applied', False)}",
                ],
                data=probability,
            ),
            ReportSection(
                title="Risk & Position",
                summary="리스크와 권장 포지션 요약",
                items=[
                    f"Risk Level: {risk.get('risk_level', 'UNKNOWN')}",
                    f"Trade Allowed: {risk.get('trade_allowed', False)}",
                    f"Recommended Weight: {self._pct(position.get('recommended_weight', 0.0))}",
                    f"Shares: {position.get('shares', '-')}",
                ],
                data={"risk": risk, "position": position},
            ),
        ]
        if explanation:
            sections.append(
                ReportSection(
                    title="Explainable AI",
                    summary=str(explanation.get("summary", "")),
                    items=[
                        f"Evidence Count: {explanation.get('metadata', {}).get('evidence_count', 0)}",
                        f"Warning Count: {explanation.get('metadata', {}).get('warning_count', 0)}",
                    ],
                    data=explanation,
                )
            )
        return sections

    def _backtest_section(self, result: dict[str, Any]) -> ReportSection:
        return ReportSection(
            title="Backtest Performance",
            summary="과거 검증 성과 요약",
            items=[
                f"Period: {result.get('start_date', '')} ~ {result.get('end_date', '')}",
                f"Total Return: {self._pct(result.get('total_return', 0.0))}",
                f"Max Drawdown: {self._pct(result.get('max_drawdown', 0.0))}",
                f"Trade Count: {result.get('trade_count', 0)}",
                f"Win Rate: {self._pct(result.get('win_rate', 0.0))}",
            ],
            data=result,
        )

    def _calibration_section(self, table: dict[str, Any]) -> ReportSection:
        return ReportSection(
            title="Probability Calibration",
            summary="예측확률과 실제 결과 간 보정 상태",
            items=[
                f"Horizon: {table.get('horizon', '-')}",
                f"Sample Count: {table.get('sample_count', 0)}",
                f"Global Bias: {self._pct(table.get('global_bias', 0.0))}",
                f"Brier Score: {table.get('brier_score', '-')}",
                f"Bin Count: {len(table.get('bins', []))}",
            ],
            data=table,
        )

    def _learning_section(self, update: dict[str, Any]) -> ReportSection:
        weights = update.get("weights", [])
        top_weights = sorted(weights, key=lambda item: float(item.get("weight", 1.0)), reverse=True)[:5]
        return ReportSection(
            title="Adaptive Learning v2",
            summary="Rule 성과와 최신 가중치 요약",
            items=[
                f"Sample Count: {update.get('sample_count', 0)}",
                f"Rule Count: {len(weights)}",
                *[f"{item.get('rule_name')}: {item.get('weight')}" for item in top_weights],
            ],
            data=update,
        )

    def _summary(
        self,
        ticker: str,
        pipeline_result: dict[str, Any] | None,
        backtest_result: dict[str, Any] | None,
        calibration_table: dict[str, Any] | None,
        learning_update: dict[str, Any] | None,
    ) -> str:
        if not pipeline_result:
            return f"{ticker} ADE 통합 리포트입니다."
        decisions = pipeline_result.get("decisions", pipeline_result)
        candidate = decisions.get("candidate", {}) or {}
        probability = decisions.get("probability", {}) or {}
        return (
            f"{ticker}의 최종 판단은 {candidate.get('action', 'UNKNOWN')}이며, "
            f"점수는 {candidate.get('score', '-')}점, "
            f"상승확률은 {self._pct(probability.get('upside_probability', 0.0))}입니다."
        )

    def _pct(self, value: Any) -> str:
        try:
            return f"{float(value):.2%}"
        except Exception:
            return "0.00%"
