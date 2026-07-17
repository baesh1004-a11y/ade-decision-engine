from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from jp_radar.engine import JPRadarEngine
from meta_score.models import MetaScoreBreakdown, MetaScoreResult


SIGNAL_SCORE = {
    "STRONG BUY": 100.0,
    "BUY": 90.0,
    "WATCH BUY": 75.0,
    "HOLD": 60.0,
    "WATCH SELL": 35.0,
    "SELL": 15.0,
    "STRONG SELL": 0.0,
}


class MetaScoreEngine:
    """Recommendation validation layer without a second composite score.

    The pattern similarity produced by Daily Center remains the only ranking
    score. Market, sector and risk are independent validation gates and never
    recalculate or dilute that score.
    """

    def __init__(self) -> None:
        self.radar_engine = JPRadarEngine()
        self._radar_cache: dict[str, object] = {}

    def score(self, recommendations: Iterable[object]) -> list[MetaScoreResult]:
        results: list[MetaScoreResult] = []
        for item in recommendations:
            market_code = str(getattr(item, "market", "kr")).lower()
            pattern_score = self._clamp(float(getattr(item, "final_similarity", 0.0) or 0.0))
            risk_score = self._risk_score(item)

            market_sector = self._market_sector(market_code, str(getattr(item, "ticker", "")))
            market_radar = self._radar(market_sector)
            market_signal = getattr(market_radar, "combined_signal", "HOLD") if market_radar else "HOLD"
            market_score = SIGNAL_SCORE.get(market_signal, 60.0)

            sector_code = self._sector_code(
                str(getattr(item, "ticker", "")),
                str(getattr(item, "name", "") or ""),
                market_sector,
            )
            sector_radar = self._radar(sector_code)
            sector_signal = getattr(sector_radar, "combined_signal", market_signal) if sector_radar else market_signal
            sector_score = SIGNAL_SCORE.get(sector_signal, market_score)
            radar_score = round((market_score + sector_score) / 2.0, 2)
            decision = self._decision(pattern_score, market_signal, sector_signal, risk_score)

            prediction = getattr(item, "prediction", None)
            reasons = self._reasons(pattern_score, market_signal, sector_signal, risk_score, decision)
            results.append(
                MetaScoreResult(
                    rank=0,
                    market_code=market_code,
                    ticker=str(getattr(item, "ticker", "")),
                    name=getattr(item, "name", None),
                    decision=decision,
                    # Legacy field: no composite score. It mirrors the original
                    # recommendation pattern similarity for DB compatibility.
                    meta_score=round(pattern_score, 2),
                    grade=self._grade(pattern_score),
                    breakdown=MetaScoreBreakdown(
                        replay=round(pattern_score, 2),
                        prediction=0.0,
                        jp_radar=radar_score,
                        market=round(market_score, 2),
                        sector=round(sector_score, 2),
                        risk=round(risk_score, 2),
                    ),
                    seven_day_up_probability=getattr(prediction, "seven_day_up_probability", None) if prediction else None,
                    seven_day_expected_return=getattr(prediction, "seven_day_expected_return", None) if prediction else None,
                    expected_peak_day=getattr(prediction, "expected_peak_day", None) if prediction else None,
                    target_return=getattr(prediction, "target_return", None) if prediction else None,
                    stop_return=getattr(prediction, "stop_return", None) if prediction else None,
                    jp_radar_signal=f"{market_signal} / {sector_signal}",
                    market_signal=market_signal,
                    sector_signal=sector_signal,
                    reasons=tuple(reasons),
                )
            )

        ranked = sorted(results, key=lambda x: (x.breakdown.replay, x.breakdown.risk), reverse=True)
        return [replace(item, rank=index) for index, item in enumerate(ranked, start=1)]

    def _radar(self, sector_code: str):
        if sector_code in self._radar_cache:
            return self._radar_cache[sector_code]
        try:
            result = self.radar_engine.analyze(sector_code, refresh=False)
        except Exception:
            result = None
        self._radar_cache[sector_code] = result
        return result

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
    def _decision(pattern: float, market: str, sector: str, risk: float) -> str:
        blocked = {"SELL", "STRONG SELL"}
        if pattern >= 90 and market not in blocked and sector not in blocked and risk >= 60:
            return "FINAL BUY"
        if pattern >= 85 and market != "STRONG SELL" and sector != "STRONG SELL" and risk >= 40:
            return "BUY WATCH"
        if pattern >= 80:
            return "HOLD"
        return "PASS"

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 95:
            return "매우 높음"
        if score >= 90:
            return "높음"
        if score >= 85:
            return "양호"
        if score >= 80:
            return "보통"
        return "낮음"

    @staticmethod
    def _reasons(pattern: float, market: str, sector: str, risk: float, decision: str) -> list[str]:
        return [
            f"급등직전 패턴 유사도 {pattern:.2f}% — 추천 순위의 유일한 점수",
            f"시장 상태 {market} — 독립 검증 항목",
            f"업종 상태 {sector} — 독립 검증 항목",
            f"위험 상태 {'PASS' if risk >= 60 else '주의'} ({risk:.0f})",
            f"검증 결과 {decision} — 별도 종합점수는 계산하지 않음",
        ]

    @staticmethod
    def _market_sector(market_code: str, ticker: str) -> str:
        if market_code in {"us", "usa", "nasdaq", "nyse"}:
            return "nasdaq30"
        if ticker.endswith(".KQ"):
            return "kosdaq50"
        return "kospi50"

    @staticmethod
    def _sector_code(ticker: str, name: str, default_market: str) -> str:
        if any(keyword in name for keyword in ("조선", "해양", "중공업")):
            return "ship"
        if any(keyword in name for keyword in ("바이오", "제약", "셀트리온", "에이비엘", "알테오젠")):
            return "bio"
        return default_market

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(100.0, value))
