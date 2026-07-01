from __future__ import annotations

from calibration.models import CalibrationBin, CalibrationTable, ProbabilityObservation


ENGINE_VERSION = "probability-calibration-v1.0.0"


class ProbabilityCalibrator:
    """Bin-based probability calibration.

    v1.0 groups predicted probabilities into fixed-width bins and compares
    predicted probability with observed outcome frequency.
    """

    def __init__(self, bin_size: float = 0.1, min_samples_per_bin: int = 1) -> None:
        if bin_size <= 0 or bin_size > 1:
            raise ValueError("bin_size must be between 0 and 1")
        if min_samples_per_bin <= 0:
            raise ValueError("min_samples_per_bin must be greater than zero")
        self.bin_size = bin_size
        self.min_samples_per_bin = min_samples_per_bin

    def fit(self, observations: list[ProbabilityObservation | dict], horizon: str = "20d") -> CalibrationTable:
        normalized = [self._normalize(item) for item in observations]
        scoped = [item for item in normalized if item.horizon == horizon]
        if not scoped:
            raise ValueError("Calibration requires at least one observation")

        bins: list[CalibrationBin] = []
        start = 0.0
        while start < 1.0:
            end = round(min(1.0, start + self.bin_size), 10)
            members = [
                item
                for item in scoped
                if item.predicted_probability >= start and (item.predicted_probability < end or end == 1.0)
            ]
            if len(members) >= self.min_samples_per_bin:
                avg_pred = sum(item.predicted_probability for item in members) / len(members)
                observed = sum(item.actual_outcome for item in members) / len(members)
                bins.append(
                    CalibrationBin(
                        bin_start=round(start, 4),
                        bin_end=round(end, 4),
                        sample_count=len(members),
                        avg_predicted_probability=round(avg_pred, 4),
                        observed_probability=round(observed, 4),
                        bias=round(avg_pred - observed, 4),
                    )
                )
            start = end

        avg_pred_all = sum(item.predicted_probability for item in scoped) / len(scoped)
        observed_all = sum(item.actual_outcome for item in scoped) / len(scoped)
        brier = sum((item.predicted_probability - item.actual_outcome) ** 2 for item in scoped) / len(scoped)
        reasons = [
            f"Collected {len(scoped)} observations for {horizon}",
            f"Global predicted probability is {avg_pred_all:.2%}",
            f"Global observed probability is {observed_all:.2%}",
        ]
        if avg_pred_all - observed_all > 0.05:
            reasons.append("Model is over-confident globally")
        elif observed_all - avg_pred_all > 0.05:
            reasons.append("Model is under-confident globally")
        else:
            reasons.append("Global calibration is acceptable")

        return CalibrationTable(
            engine_version=ENGINE_VERSION,
            horizon=horizon,
            sample_count=len(scoped),
            bins=[item.to_dict() for item in bins],
            global_bias=round(avg_pred_all - observed_all, 4),
            brier_score=round(brier, 4),
            reasons=reasons,
        )

    def _normalize(self, item: ProbabilityObservation | dict) -> ProbabilityObservation:
        if isinstance(item, ProbabilityObservation):
            return item
        return ProbabilityObservation(
            ticker=str(item["ticker"]),
            prediction_date=str(item["prediction_date"]),
            horizon=str(item.get("horizon", "20d")),
            predicted_probability=float(item["predicted_probability"]),
            actual_outcome=int(item["actual_outcome"]),
            expected_return=float(item.get("expected_return", 0.0)),
            realized_return=float(item.get("realized_return", 0.0)),
            metadata=item.get("metadata", {}),
        )
