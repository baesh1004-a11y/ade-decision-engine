from __future__ import annotations

from dataclasses import dataclass

from jp_radar.engine import JPRadarEngine


@dataclass(frozen=True)
class ValidationContext:
    """One combined market, sector and stock-risk advice result."""

    market_signal: str = "HOLD"
    sector_signal: str = "HOLD"
    risk_score: float = 100.0


NEUTRAL_VALIDATION_CONTEXT = ValidationContext()


class EnvironmentAdvisor:
    """Analyze market, sector and selected-stock risk as one user-requested advice step."""

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
        risk_score = self._risk_score(recommendation)

        return ValidationContext(
            market_signal=market_signal,
            sector_signal=sector_signal,
            risk_score=risk_score,
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
    def _risk_score(item: object) -> float:
        prediction = getattr(item, "prediction", None)
        if prediction is not None:
            mdd = float(getattr(prediction, "expected_mdd_7d", 0.0) or 0.0)
            stop = float(getattr(prediction, "stop_return", 0.0) or 0.0)
        else:
            mdd = float(getattr(item, "matched_max_drawdown", 0.0) or 0.0)
            stop = 0.0
        penalty = abs(min(0.0, mdd)) * 4.0 + abs(min(0.0, stop)) * 2.0
        return max(0.0, min(100.0, 100.0 - penalty))

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
