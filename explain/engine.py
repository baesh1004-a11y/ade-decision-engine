from __future__ import annotations

from typing import Any

from explain.evidence import EvidenceEngine
from explain.models import ExplanationReport
from explain.narrative import NarrativeEngine


ENGINE_VERSION = "explainable-ai-v1.0.0"


class ExplainableAIEngine:
    """Generate explainable decision reports from ADE pipeline outputs."""

    def __init__(self) -> None:
        self.evidence_engine = EvidenceEngine()
        self.narrative_engine = NarrativeEngine()

    def explain(self, ticker: str, decisions: dict[str, Any]) -> ExplanationReport:
        candidate = decisions.get("candidate", {}) or {}
        decision = str(candidate.get("action", "UNKNOWN"))
        confidence = float(candidate.get("confidence", 0.0))
        evidence, warnings = self.evidence_engine.collect(decisions)
        summary = self.narrative_engine.summarize(ticker, decision, confidence, evidence, warnings)
        narrative = self.narrative_engine.narrative(ticker, decision, confidence, evidence, warnings)
        return ExplanationReport(
            engine_version=ENGINE_VERSION,
            ticker=ticker,
            decision=decision,
            confidence=round(confidence, 4),
            summary=summary,
            evidence=[item.to_dict() for item in evidence],
            warnings=warnings,
            narrative=narrative,
            metadata={
                "evidence_count": len(evidence),
                "warning_count": len(warnings),
            },
        )


def explain_decision(ticker: str, decisions: dict[str, Any]) -> dict[str, Any]:
    return ExplainableAIEngine().explain(ticker, decisions).to_dict()
