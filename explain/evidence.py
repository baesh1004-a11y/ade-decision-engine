from __future__ import annotations

from typing import Any

from explain.models import EvidenceItem


class EvidenceEngine:
    """Extract explainable evidence from ADE decision outputs."""

    def collect(self, decisions: dict[str, Any]) -> tuple[list[EvidenceItem], list[str]]:
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        self._pattern_evidence(decisions, evidence, warnings)
        self._probability_evidence(decisions, evidence, warnings)
        self._candidate_evidence(decisions, evidence, warnings)
        self._risk_evidence(decisions, evidence, warnings)
        self._position_evidence(decisions, evidence, warnings)
        self._entry_exit_evidence(decisions, evidence, warnings)
        return evidence, warnings

    def _pattern_evidence(self, decisions: dict[str, Any], evidence: list[EvidenceItem], warnings: list[str]) -> None:
        pattern = decisions.get("pattern", {}) or {}
        pattern_context = decisions.get("pattern_context", {}) or {}
        memory = decisions.get("pattern_memory", {}) or {}
        if memory:
            evidence.append(
                EvidenceItem(
                    category="Pattern Memory",
                    label="Memory Records",
                    value=str(memory.get("records", 0)),
                    impact="supportive" if int(memory.get("records", 0)) > 0 else "weak",
                    weight=0.10,
                )
            )
        if pattern:
            evidence.append(
                EvidenceItem(
                    category="Pattern",
                    label="Match Count",
                    value=str(pattern.get("match_count", 0)),
                    impact="supportive" if int(pattern.get("match_count", 0)) >= 5 else "weak",
                    weight=0.15,
                )
            )
            evidence.append(
                EvidenceItem(
                    category="Pattern",
                    label="Average Similarity",
                    value=self._pct(pattern.get("avg_similarity", 0.0)),
                    impact="supportive" if float(pattern.get("avg_similarity", 0.0)) >= 0.70 else "weak",
                    weight=0.20,
                )
            )
            for flag in pattern.get("risk_flags", []) or []:
                warnings.append(f"Pattern: {flag}")
        if pattern_context:
            evidence.append(
                EvidenceItem(
                    category="Context",
                    label="Combined Similarity",
                    value=self._pct(pattern_context.get("combined_similarity", 0.0)),
                    impact="supportive" if float(pattern_context.get("combined_similarity", 0.0)) >= 0.70 else "weak",
                    weight=0.20,
                )
            )
            for flag in pattern_context.get("risk_flags", []) or []:
                warnings.append(f"Pattern Context: {flag}")

    def _probability_evidence(self, decisions: dict[str, Any], evidence: list[EvidenceItem], warnings: list[str]) -> None:
        probability = decisions.get("probability", {}) or {}
        if not probability:
            return
        evidence.append(
            EvidenceItem(
                category="Probability",
                label="Upside Probability",
                value=self._pct(probability.get("upside_probability", 0.0)),
                impact="supportive" if float(probability.get("upside_probability", 0.0)) >= 0.60 else "weak",
                weight=0.25,
            )
        )
        if probability.get("raw_upside_probability") is not None:
            evidence.append(
                EvidenceItem(
                    category="Calibration",
                    label="Raw → Calibrated",
                    value=f"{self._pct(probability.get('raw_upside_probability'))} → {self._pct(probability.get('upside_probability'))}",
                    impact="calibrated",
                    weight=0.15,
                )
            )
        evidence.append(
            EvidenceItem(
                category="Probability",
                label="Expected Return",
                value=self._pct(probability.get("expected_return", 0.0)),
                impact="supportive" if float(probability.get("expected_return", 0.0)) > 0 else "negative",
                weight=0.20,
            )
        )
        evidence.append(
            EvidenceItem(
                category="Probability",
                label="Risk Reward",
                value=str(probability.get("risk_reward", 0.0)),
                impact="supportive" if float(probability.get("risk_reward", 0.0)) >= 1.2 else "weak",
                weight=0.15,
            )
        )
        for flag in probability.get("risk_flags", []) or []:
            warnings.append(f"Probability: {flag}")

    def _candidate_evidence(self, decisions: dict[str, Any], evidence: list[EvidenceItem], warnings: list[str]) -> None:
        candidate = decisions.get("candidate", {}) or {}
        if not candidate:
            return
        evidence.append(
            EvidenceItem(
                category="Candidate",
                label="Score / Grade",
                value=f"{candidate.get('score', 0)} / {candidate.get('grade', '-')}",
                impact="supportive" if int(candidate.get("score", 0)) >= 70 else "weak",
                weight=0.25,
            )
        )
        evidence.append(
            EvidenceItem(
                category="Candidate",
                label="Action",
                value=str(candidate.get("action", "UNKNOWN")),
                impact="supportive" if str(candidate.get("action", "")).upper() in {"BUY_CANDIDATE", "WATCHLIST"} else "neutral",
                weight=0.15,
            )
        )
        for flag in candidate.get("risk_flags", []) or []:
            warnings.append(f"Candidate: {flag}")

    def _risk_evidence(self, decisions: dict[str, Any], evidence: list[EvidenceItem], warnings: list[str]) -> None:
        risk = decisions.get("risk", {}) or {}
        if not risk:
            return
        evidence.append(
            EvidenceItem(
                category="Risk",
                label="Risk Level",
                value=str(risk.get("risk_level", "UNKNOWN")),
                impact="supportive" if str(risk.get("risk_level", "")).upper() in {"LOW", "NORMAL"} else "negative",
                weight=0.25,
            )
        )
        evidence.append(
            EvidenceItem(
                category="Risk",
                label="Trade Allowed",
                value=str(risk.get("trade_allowed", False)),
                impact="supportive" if bool(risk.get("trade_allowed", False)) else "negative",
                weight=0.30,
            )
        )
        for flag in risk.get("risk_flags", []) or []:
            warnings.append(f"Risk: {flag}")

    def _position_evidence(self, decisions: dict[str, Any], evidence: list[EvidenceItem], warnings: list[str]) -> None:
        position = decisions.get("position", {}) or {}
        if not position:
            return
        evidence.append(
            EvidenceItem(
                category="Position",
                label="Recommended Weight",
                value=self._pct(position.get("recommended_weight", 0.0)),
                impact="supportive" if float(position.get("recommended_weight", 0.0)) > 0 else "weak",
                weight=0.15,
            )
        )
        if position.get("risk_capped"):
            warnings.append("Position: size was capped by Risk Engine")

    def _entry_exit_evidence(self, decisions: dict[str, Any], evidence: list[EvidenceItem], warnings: list[str]) -> None:
        entry = decisions.get("entry", {}) or {}
        if entry:
            evidence.append(
                EvidenceItem(
                    category="Entry",
                    label="Entry Action",
                    value=str(entry.get("action", "UNKNOWN")),
                    impact="supportive" if str(entry.get("action", "")).upper() not in {"WAIT", "AVOID"} else "weak",
                    weight=0.10,
                )
            )
            for flag in entry.get("risk_flags", []) or []:
                warnings.append(f"Entry: {flag}")
        exit_decision = decisions.get("exit", {}) or {}
        if exit_decision:
            evidence.append(
                EvidenceItem(
                    category="Exit",
                    label="Exit Action",
                    value=str(exit_decision.get("action", "UNKNOWN")),
                    impact="neutral",
                    weight=0.10,
                )
            )

    def _pct(self, value: Any) -> str:
        try:
            return f"{float(value):.2%}"
        except Exception:
            return "0.00%"
