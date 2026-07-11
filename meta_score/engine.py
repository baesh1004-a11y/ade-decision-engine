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
    """Fixed-weight final decision layer.

    Weights:
      Replay 30%, Prediction 25%, JP Radar 20%,
      Market 10%, Sector 10%, Risk 5%.

    This module never modifies the recommendation engine. It only consumes its
    output and returns a ranked final-decision view.
    """

    WEIGHTS = {
        "replay": 0.30,
        "prediction": 0.25,
        "jp_radar": 0.20,
        "market": 0.10,
        "sector": 0.10,
        "risk": 0.05,
    }

    def __init__(self) -> None:
        self.radar_engine = JPRadarEngine()
        self._radar_cache: dict[str, object] = {}

    def score(self, recommendations: Iterable[object]) -> list[MetaScoreResult]:
        results: list[MetaScoreResult] = []
        for item in recommendations:
            market_code = str(getattr(item, "market", "kr")).lower()
            replay_score = self._clamp(float(getattr(item, "final_similarity", 0.0) or 0.0))
            prediction_score = self._prediction_score(getattr(item, "prediction", None))
            risk_score = self._risk_score(item)

            market_sector = self._market_sector(market_code, str(getattr(item, "ticker", "")))
            market_radar = self._radar(market_sector)
            market_signal = getattr(market_radar, "combined_signal", "HOLD") if market_radar is not None else "HOLD"
            market_score = SIGNAL_SCORE.get(market_signal, 60.0)

            sector_code = self._sector_code(str(getattr(item, "ticker", "")), str(getattr(item, "name", "") or ""), market_sector)
            sector_radar = self._radar(sector_code)
            sector_signal = getattr(sector_radar, "combined_signal", market_signal) if sector_radar is not None else market_signal
            sector_score = SIGNAL_SCORE.get(sector_signal, market_score)

            jp_radar_score = round((market_score + sector_score) / 2.0, 2)
            meta = round(
                replay_score * self.WEIGHTS["replay"]
                + prediction_score * self.WEIGHTS["prediction"]
                + jp_radar_score * self.WEIGHTS["jp_radar"]
                + market_score * self.WEIGHTS["market"]
                + sector_score * self.WEIGHTS["sector"]
                + risk_score * self.WEIGHTS["risk"],
                2,
            )
            prediction = getattr(item, "prediction", None)
            reasons = self._reasons(item, replay_score, prediction_score, market_signal, sector_signal, risk_score, meta)
            results.append(
                MetaScoreResult(
                    rank=0,
                    market_code=market_code,
                    ticker=str(getattr(item, "ticker", "")),
                    name=getattr(item, "name", None),
                    decision=self._decision(meta, market_signal, sector_signal),
                    meta_score=meta,
                    grade=self._grade(meta),
                    breakdown=MetaScoreBreakdown(
                        replay=round(replay_score, 2),
                        prediction=round(prediction_score, 2),
                        jp_radar=round(jp_radar_score, 2),
                        market=round(market_score, 2),
                        sector=round(sector_score, 2),
                        risk=round(risk_score, 2),
                    ),
                    seven_day_up_probability=getattr(prediction, "seven_day_up_probability", None) if prediction is not None else None,
                    seven_day_expected_return=getattr(prediction, "seven_day_expected_return", None) if prediction is not None else None,
                    expected_peak_day=getattr(prediction, "expected_peak_day", None) if prediction is not None else None,
                    target_return=getattr(prediction, "target_return", None) if prediction is not None else None,
                    stop_return=getattr(prediction, "stop_return", None) if prediction is not None else None,
                    jp_radar_signal=f"{market_signal} / {sector_signal}",
                    market_signal=market_signal,
                    sector_signal=sector_signal,
                    reasons=tuple(reasons),
                )
            )

        ranked = sorted(results, key=lambda x: (x.meta_score, x.breakdown.prediction, x.breakdown.replay), reverse=True)
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
    def _prediction_score(prediction: object | None) -> float:
        if prediction is None:
            return 0.0
        probability = float(getattr(prediction, "seven_day_up_probability", 0.0) or 0.0)
        expected = float(getattr(prediction, "seven_day_expected_return", 0.0) or 0.0)
        max_return = float(getattr(prediction, "expected_max_return_7d", 0.0) or 0.0)
        expected_component = max(0.0, min(100.0, 50.0 + expected * 8.0))
        max_component = max(0.0, min(100.0, max_return * 10.0))
        return max(0.0, min(100.0, probability * 0.60 + expected_component * 0.25 + max_component * 0.15))

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
    def _sector_code(ticker: str, name: str, default_market: str) -> str:
        ship_keywords = ("조선", "해양", "중공업")
        bio_keywords = ("바이오", "제약", "셀트리온", "에이비엘", "알테오젠")
        if any(keyword in name for keyword in ship_keywords):
            return "ship"
        if any(keyword in name for keyword in bio_keywords):
            return "bio"
        return default_market

    @staticmethod
    def _decision(meta: float, market_signal: str, sector_signal: str) -> str:
        if meta >= 85 and market_signal not in {"SELL", "STRONG SELL"} and sector_signal not in {"SELL", "STRONG SELL"}:
            return "FINAL BUY"
        if meta >= 75:
            return "BUY WATCH"
        if meta >= 60:
            return "HOLD"
        return "PASS"

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 90:
            return "A+"
        if score >= 85:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        return "D"

    @staticmethod
    def _reasons(item: object, replay: float, prediction: float, market: str, sector: str, risk: float, meta: float) -> list[str]:
        prediction_obj = getattr(item, "prediction", None)
        reasons = [
            f"Replay 최종 유사도 {replay:.2f}점",
            f"7일 예측 환산점수 {prediction:.2f}점",
            f"시장 JP Radar {market}",
            f"업종 JP Radar {sector}",
            f"위험관리 점수 {risk:.2f}점",
            f"고정 가중치 통합점수 {meta:.2f}점",
        ]
        if prediction_obj is not None:
            reasons.append(
                f"7일 상승확률 {float(getattr(prediction_obj, 'seven_day_up_probability', 0.0) or 0.0):.1f}%, "
                f"기대수익 {float(getattr(prediction_obj, 'seven_day_expected_return', 0.0) or 0.0):+.2f}%"
            )
        return reasons

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(100.0, value))
