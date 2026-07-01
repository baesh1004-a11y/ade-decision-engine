from __future__ import annotations

from typing import Any

from calibration.models import ProbabilityObservation


class CalibrationCollector:
    """Collect probability predictions and realized outcomes from backtest trades."""

    def collect_from_backtest(self, result: dict[str, Any], horizon: str = "20d") -> list[ProbabilityObservation]:
        observations: list[ProbabilityObservation] = []
        for trade in result.get("trades", []):
            metadata = trade.get("metadata", {}) or {}
            candidate = metadata.get("candidate", {}) or {}
            probability_adjustment = candidate.get("probability_adjustment", {}) or {}
            predicted = probability_adjustment.get("upside_probability")
            if predicted is None:
                continue
            realized_return = float(trade.get("gross_return", 0.0))
            observations.append(
                ProbabilityObservation(
                    ticker=str(trade.get("ticker", result.get("ticker", "UNKNOWN"))),
                    prediction_date=str(trade.get("entry_date", "")),
                    horizon=horizon,
                    predicted_probability=float(predicted),
                    actual_outcome=1 if realized_return > 0 else 0,
                    expected_return=float(probability_adjustment.get("expected_return", 0.0)),
                    realized_return=realized_return,
                    metadata={
                        "entry_price": trade.get("entry_price"),
                        "exit_price": trade.get("exit_price"),
                        "holding_days": trade.get("holding_days"),
                        "recommendation": probability_adjustment.get("recommendation"),
                    },
                )
            )
        return observations

    def collect_from_pairs(self, predictions: list[dict[str, Any]], actuals: list[dict[str, Any]]) -> list[ProbabilityObservation]:
        actual_by_key = {
            (str(item["ticker"]), str(item["prediction_date"]), str(item.get("horizon", "20d"))): item
            for item in actuals
        }
        observations: list[ProbabilityObservation] = []
        for pred in predictions:
            key = (str(pred["ticker"]), str(pred["prediction_date"]), str(pred.get("horizon", "20d")))
            actual = actual_by_key.get(key)
            if not actual:
                continue
            realized_return = float(actual.get("realized_return", 0.0))
            observations.append(
                ProbabilityObservation(
                    ticker=key[0],
                    prediction_date=key[1],
                    horizon=key[2],
                    predicted_probability=float(pred["predicted_probability"]),
                    actual_outcome=int(actual.get("actual_outcome", 1 if realized_return > 0 else 0)),
                    expected_return=float(pred.get("expected_return", 0.0)),
                    realized_return=realized_return,
                    metadata={"prediction": pred, "actual": actual},
                )
            )
        return observations
