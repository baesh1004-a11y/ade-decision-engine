from __future__ import annotations

from dataclasses import dataclass

from jp_radar.engine import JPRadarEngine


@dataclass(frozen=True)
class ValidationContext:
    """One combined market-and-sector environment result for validation."""

    market_signal: str = "HOLD"
    sector_signal: str = "HOLD"


NEUTRAL_VALIDATION_CONTEXT = ValidationContext()


class EnvironmentAdvisor:
    """Analyze the overall market and the selected stock's supported sector together."""

    def __init__(self, radar_engine: JPRadarEngine | None = None) -> None:
        self.radar_engine = radar_engine or JPRadarEngine()
        self._cache: dict[str, object | None] = {}

    def analyze(self, recommendation: object) -> ValidationContext:
        market_code = str(getattr(recommendation, "market", "kr")).lower()
        ticker = str(getattr(recommendation, "ticker", ""))
        name = str(getattr(recommendation, "name", "") or "")

        market_signal = self._signal(self._market_sector(market_code, ticker))
        sector_code = self._sector_code(name)
        sector_signal = self._signal(sector_code) if sector_code else "HOLD"

        return ValidationContext(
            market_signal=market_signal,
            sector_signal=sector_signal,
        )

    def _signal(self, sector_code: str) -> str:
        if sector_code not in self._cache:
            try:
                self._cache[sector_code] = self.radar_engine.analyze(sector_code, refresh=False)
            except Exception:
                self._cache[sector_code] = None
        result = self._cache[sector_code]
        return str(getattr(result, "combined_signal", "HOLD") if result else "HOLD")

    @staticmethod
    def _market_sector(market_code: str, ticker: str) -> str:
        if market_code in {"us", "usa", "nasdaq", "nyse"}:
            return "nasdaq30"
        if ticker.endswith(".KQ"):
            return "kosdaq50"
        return "kospi50"

    @staticmethod
    def _sector_code(name: str) -> str | None:
        if any(keyword in name for keyword in ("조선", "해양", "중공업")):
            return "ship"
        if any(keyword in name for keyword in ("바이오", "제약", "셀트리온", "에이비엘", "알테오젠")):
            return "bio"
        return None
