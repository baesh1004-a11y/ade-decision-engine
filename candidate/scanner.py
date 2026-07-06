from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from centerline.engine import CenterlineEngine
from datahub.repository import PriceRepository
from pattern.replay_probability import ReplayProbabilityEngine
from universe.manager import DynamicUniverseManager


@dataclass(frozen=True)
class CandidateScore:
    market: str
    ticker: str
    name: str | None
    sector: str | None
    score: int
    action: str
    reasons: list[str]
    latest_close: float
    latest_volume: float
    volume_ratio_20d: float
    volume_ratio_120d: float
    state_score: int
    centerline_score: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandidateScanner:
    """Find actionable ADE candidates before replay analysis."""

    def __init__(self, repository: PriceRepository, lookback: int = 260) -> None:
        self.repository = repository
        self.lookback = lookback
        self.state_engine = ReplayProbabilityEngine(window=120)
        self.centerline_engine = CenterlineEngine()

    def scan(self, source: str = "fdr", min_score: int = 55, top_n: int = 50) -> list[CandidateScore]:
        candidates: list[CandidateScore] = []
        for symbol in DynamicUniverseManager().active():
            data = self.repository.fetch_dataframe(symbol.market, symbol.ticker, source=source)
            if len(data) < 60:
                continue
            score = self.score_symbol(symbol.market, symbol.ticker, symbol.name, symbol.sector, data)
            if score.score >= min_score:
                candidates.append(score)
        return sorted(candidates, key=lambda item: item.score, reverse=True)[:top_n]

    def score_symbol(
        self,
        market: str,
        ticker: str,
        name: str | None,
        sector: str | None,
        data: pd.DataFrame,
    ) -> CandidateScore:
        df = self.state_engine._prepare(data).tail(self.lookback).reset_index(drop=True)
        close = df["Close"]
        open_ = df["Open"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        latest_close = float(close.iloc[-1])
        latest_volume = float(volume.iloc[-1])

        vol20 = float(volume.rolling(20, min_periods=5).mean().iloc[-1] or 0)
        vol120 = float(volume.rolling(120, min_periods=20).mean().iloc[-1] or 0)
        volume_ratio_20d = latest_volume / vol20 if vol20 > 0 else 1.0
        volume_ratio_120d = latest_volume / vol120 if vol120 > 0 else 1.0

        body_ratio = (close.iloc[-1] - open_.iloc[-1]) / max(high.iloc[-1] - low.iloc[-1], 1e-9)
        latest_return = close.iloc[-1] / close.iloc[-2] - 1 if len(close) >= 2 and close.iloc[-2] > 0 else 0
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        rolling_high_120 = high.rolling(120, min_periods=20).max().iloc[-1]
        rolling_low_120 = low.rolling(120, min_periods=20).min().iloc[-1]
        base_range = (rolling_high_120 - rolling_low_120) / rolling_low_120 if rolling_low_120 else 9.9
        breakout = latest_close >= rolling_high_120 * 0.95
        state = self.state_engine.extract_state(df.tail(120))
        centerline = self.centerline_engine.snapshot(df)

        points = 0
        reasons: list[str] = []

        if volume_ratio_120d >= 10:
            points += 20
            reasons.append("거래대금/거래량 120일 평균 대비 10배 이상")
        elif volume_ratio_20d >= 3:
            points += 15
            reasons.append("거래량 20일 평균 대비 3배 이상")
        elif volume_ratio_20d >= 1.5:
            points += 8
            reasons.append("거래량 증가")

        if latest_return >= 0.08 and body_ratio >= 0.55:
            points += 15
            reasons.append("장대양봉 출현")
        elif latest_return >= 0.03 and body_ratio >= 0.35:
            points += 8
            reasons.append("양봉 상승 전환")

        if state.sto_stack_score >= 85:
            points += 12
            reasons.append("STO 3층 구조")
        elif state.sto_stack_score >= 60:
            points += 6
            reasons.append("STO 상승 배열")

        if latest_close > ma5 > ma20 > ma60:
            points += 12
            reasons.append("5MA > 20MA > 60MA 정배열")
        elif latest_close > ma20 > ma60:
            points += 7
            reasons.append("중기 이평 우상향")

        if breakout and volume_ratio_20d >= 1.3:
            points += 12
            reasons.append("120일 박스권 상단 돌파 + 거래량 동반")
        elif breakout:
            points += 8
            reasons.append("120일 고점권 접근")

        if base_range <= 0.8 and latest_close > ma60:
            points += 8
            reasons.append("장기 바닥권 이후 회복")

        centerline_bonus = round(centerline.centerline_score * 0.21)
        points += centerline_bonus
        reasons.extend(centerline.labels[:4])

        points = min(100, points)
        action = "REPLAY_ANALYSIS" if points >= 70 else "WATCH" if points >= 55 else "EXCLUDE"
        return CandidateScore(
            market=market,
            ticker=ticker,
            name=name,
            sector=sector,
            score=round(points),
            action=action,
            reasons=reasons,
            latest_close=round(latest_close, 4),
            latest_volume=round(latest_volume, 2),
            volume_ratio_20d=round(volume_ratio_20d, 2),
            volume_ratio_120d=round(volume_ratio_120d, 2),
            state_score=state.state_score,
            centerline_score=centerline.centerline_score,
        )


def scan_candidates(db_path: str | Path = "datahub/market.db", min_score: int = 55, top_n: int = 50) -> list[CandidateScore]:
    repository = PriceRepository(db_path)
    try:
        return CandidateScanner(repository).scan(min_score=min_score, top_n=top_n)
    finally:
        repository.close()
