from __future__ import annotations

import numpy as np
import pandas as pd

from replay_target.integrated import IntegratedWatchConfig, ReplayTargetIntegratedService


def _ohlcv(start: str, periods: int, phase: float = 0.0) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    x = np.linspace(0.0, 10.0, periods)
    close = 100.0 + np.sin(x + phase) * 12.0 + x * 1.5
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close - 0.8,
            "High": close + 1.6,
            "Low": close - 1.7,
            "Close": close,
            "Volume": np.full(periods, 100000.0),
        }
    )


def test_integrated_watch_with_manual_anchor_produces_target_and_path() -> None:
    current = _ohlcv("2026-01-02", 190, phase=0.2)
    reference = _ohlcv("2011-01-03", 280, phase=0.2)
    service = ReplayTargetIntegratedService()
    cfg = IntegratedWatchConfig(
        current_anchor_date="2026-08-25",
        reference_anchor_date="2011-10-03",
        reference_target_date="2011-12-14",
    )

    result = service.evaluate_frames(current, reference, config=cfg)

    assert result.resolved_current_anchor_date is not None
    assert result.resolved_reference_anchor_date is not None
    assert result.target is not None
    assert result.target.target_score is not None
    assert result.path is not None
    assert result.path.path_score is not None


def test_integrated_watch_auto_calibrates_reference_anchor_inside_window() -> None:
    current = _ohlcv("2026-01-02", 190, phase=0.4)
    reference = _ohlcv("2011-01-03", 280, phase=0.4)
    service = ReplayTargetIntegratedService()
    cfg = IntegratedWatchConfig(
        current_anchor_date="2026-08-25",
        reference_window_start="2011-09-01",
        reference_window_end="2011-12-31",
        reference_anchor_date=None,
        reference_target_date="2011-12-30",
    )

    result = service.evaluate_frames(current, reference, config=cfg)

    assert result.resolved_reference_anchor_date is not None
    resolved = pd.Timestamp(result.resolved_reference_anchor_date)
    assert pd.Timestamp("2011-09-01") <= resolved <= pd.Timestamp("2011-12-31")
    assert result.anchor_similarity is not None
