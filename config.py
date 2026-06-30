"""Global configuration for ADE."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketConfig:
    korea_start: str = "20200101"
    korea_end: str = "20261231"
    usa_period: str = "10y"
    usa_interval: str = "1d"


@dataclass(frozen=True)
class IndicatorConfig:
    ma_periods: tuple[int, ...] = (5, 20, 60, 120, 240)
    volume_window: int = 20
    stochastic_settings: tuple[tuple[int, int, int], ...] = (
        (5, 3, 3),
        (10, 6, 6),
        (20, 12, 12),
    )


MARKET = MarketConfig()
INDICATOR = IndicatorConfig()
