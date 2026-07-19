from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from meta_score.models import MetaScoreBreakdown, MetaScoreResult
from meta_score.validation_context import EnvironmentAdvisor, NEUTRAL_VALIDATION_CONTEXT, ValidationContext


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
    """Apply one integrated environment-advice result without a second ranking score.

    Callers should normally inject ``validation_contexts``. For legacy call sites that
    omit it, the engine now computes the real market, sector and stock-risk contexts
    instead of silently using neutral HOLD/HOLD/100 defaults.
    """

    def score(
        self,
        recommendations: Iterable[object],
        validation_contexts: Mapping[str, ValidationContext] | None = None,
    ) -> list[MetaScoreResult]:
        items = list(recommendations)
        if validation_contexts is None:
            advisor = EnvironmentAdvisor()
            contexts = {
                str(getattr(item, "ticker", "")): advisor.analyze(item)
                for item in items
            }
        else:
            contexts = dict(validation_contexts)

        results: list[MetaScoreResult] = []
        for item in items:
            market_code = str(getattr(item, "market", "kr")).lower()
            ticker = str(getattr(item, "ticker", ""))
            pattern_score = self._clamp(float(getattr(item, "final_similarity", 0.0) or 0.0))

            context = contexts.get(ticker, NEUTRAL_VALIDATION_CONTEXT)
            market_signal = self._normalize_signal(context.market_signal)
            sector_signal = self._normalize_signal(context.sector_signal)
            risk_score = self._clamp(float(context.risk_score))
            market_score = SIGNAL_SCORE[market_signal]
            sector_score = SIGNAL_SCORE[sector_signal]
            radar_score = round((market_score + sector_score) / 2.0, 2)
            decision = self._decision(pattern_score, market_signal, sector_signal, risk_score)

            prediction = getattr(item, "prediction", None)
            reasons = self._reasons(pattern_score, market_signal, sector_signal, risk_score, decision)
            results.append(
                MetaScoreResult(
                    rank=0,
                    market_code=market_code,
                    ticker=ticker,
                    name=getattr(item, "name", None),
                    decision=decision,
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
            f"통합 환경 조언 — 전체 시장 {market}, 해당 업종 {sector}, 종목 위험 {risk:.0f}",
            f"조언 결과 {decision} — 별도 종합점수는 계산하지 않음",
        ]

    @staticmethod
    def _normalize_signal(value: str) -> str:
        signal = str(value or "HOLD").upper().strip()
        return signal if signal in SIGNAL_SCORE else "HOLD"

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(100.0, value))
