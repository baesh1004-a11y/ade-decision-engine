from __future__ import annotations

from explain.models import EvidenceItem


class NarrativeEngine:
    """Generate human-readable explanations from evidence items."""

    def summarize(self, ticker: str, decision: str, confidence: float, evidence: list[EvidenceItem], warnings: list[str]) -> str:
        decision_text = self._decision_text(decision)
        main = self._top_supporting_evidence(evidence)
        warning_text = " 단, " + "; ".join(warnings[:3]) + "에 유의해야 합니다." if warnings else ""
        return f"{ticker}는 {decision_text}. 주요 근거는 {main}입니다.{warning_text} 신뢰도는 {confidence:.2%}입니다."

    def narrative(self, ticker: str, decision: str, confidence: float, evidence: list[EvidenceItem], warnings: list[str]) -> str:
        lines = [
            f"# ADE Decision Explanation: {ticker}",
            "",
            f"최종 판단: {decision}",
            f"신뢰도: {confidence:.2%}",
            "",
            "## 핵심 근거",
        ]
        for item in sorted(evidence, key=lambda x: x.weight, reverse=True)[:8]:
            lines.append(f"- [{item.category}] {item.label}: {item.value} ({item.impact})")
        if warnings:
            lines.extend(["", "## 주의사항"])
            for warning in warnings[:8]:
                lines.append(f"- {warning}")
        return "\n".join(lines)

    def _top_supporting_evidence(self, evidence: list[EvidenceItem]) -> str:
        supportive = [item for item in evidence if item.impact in {"supportive", "calibrated"}]
        selected = sorted(supportive, key=lambda x: x.weight, reverse=True)[:3]
        if not selected:
            return "충분한 긍정 근거가 제한적"
        return ", ".join(f"{item.label} {item.value}" for item in selected)

    def _decision_text(self, decision: str) -> str:
        mapping = {
            "BUY_CANDIDATE": "매수 후보로 판단됩니다",
            "WATCHLIST": "관심종목으로 관찰할 만합니다",
            "NEUTRAL": "중립으로 판단됩니다",
            "REJECT": "매수 후보에서 제외됩니다",
            "WATCH": "관찰이 필요합니다",
        }
        return mapping.get(decision, f"{decision}로 판단됩니다")
