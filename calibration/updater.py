from __future__ import annotations

from typing import Any


class ProbabilityUpdater:
    """Apply a calibration table to probability decisions."""

    def apply(self, probability: dict[str, Any], calibration_table: dict[str, Any]) -> dict[str, Any]:
        adjusted = dict(probability)
        original = float(adjusted.get("upside_probability", 0.0))
        calibrated = self._calibrated_probability(original, calibration_table)
        adjusted["raw_upside_probability"] = round(original, 4)
        adjusted["upside_probability"] = round(calibrated, 4)
        adjusted["downside_probability"] = round(max(0.0, min(1.0, 1.0 - calibrated)), 4)
        adjusted["calibration"] = {
            "engine_version": calibration_table.get("engine_version"),
            "horizon": calibration_table.get("horizon"),
            "global_bias": calibration_table.get("global_bias"),
            "brier_score": calibration_table.get("brier_score"),
            "applied": True,
        }
        adjusted["recommendation"] = self._recommendation(
            adjusted["upside_probability"],
            float(adjusted.get("expected_return", 0.0)),
            float(adjusted.get("risk_reward", 0.0)),
            float(adjusted.get("confidence", 0.0)),
        )
        reasons = list(adjusted.get("reasons", []))
        reasons.append(f"Probability calibrated from {original:.2%} to {calibrated:.2%}")
        adjusted["reasons"] = reasons
        return adjusted

    def _calibrated_probability(self, probability: float, calibration_table: dict[str, Any]) -> float:
        bins = calibration_table.get("bins", [])
        for item in bins:
            start = float(item["bin_start"])
            end = float(item["bin_end"])
            if probability >= start and (probability < end or end == 1.0):
                return max(0.0, min(1.0, float(item["observed_probability"])))
        global_bias = float(calibration_table.get("global_bias", 0.0))
        return max(0.0, min(1.0, probability - global_bias))

    def _recommendation(self, upside_probability: float, expected_return: float, risk_reward: float, confidence: float) -> str:
        if expected_return < 0 or upside_probability < 0.45:
            return "AVOID"
        if upside_probability >= 0.70 and expected_return >= 0.05 and risk_reward >= 2.0 and confidence >= 0.75:
            return "STRONG_BUY"
        if upside_probability >= 0.60 and expected_return > 0 and risk_reward >= 1.2 and confidence >= 0.65:
            return "BUY"
        if upside_probability >= 0.52 and expected_return > 0:
            return "WATCH"
        return "AVOID"
