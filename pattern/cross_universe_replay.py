from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from pattern.replay_probability import PatternState, ReplayProbabilityEngine
from universe.manager import DynamicUniverseManager


@dataclass(frozen=True)
class CrossUniverseReplayCase:
    market: str
    ticker: str
    name: str | None
    sector: str | None
    start_date: str
    end_date: str
    similarity: float
    forward_return_20d: float | None
    forward_return_60d: float | None
    drawdown_20d: float | None
    state: PatternState

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CrossUniverseReplayResult:
    target_market: str
    target_ticker: str
    current_state: PatternState
    cases: list[CrossUniverseReplayCase]
    avg_return_20d: float | None
    avg_return_60d: float | None
    win_rate_20d: float | None
    avg_drawdown_20d: float | None
    replay_probability: int
    grade: str
    action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CrossUniverseReplayEngine:
    """Search similar ADE states across all stored universe symbols.

    This implements the practical version of the user's process:
    current target state -> all other stored symbols/windows -> matched cases -> forward returns.
    """

    def __init__(
        self,
        repository: PriceRepository,
        window: int = 120,
        forward_20d: int = 20,
        forward_60d: int = 60,
        step: int = 5,
    ) -> None:
        self.repository = repository
        self.window = window
        self.forward_20d = forward_20d
        self.forward_60d = forward_60d
        self.step = step
        self.state_engine = ReplayProbabilityEngine(window=window, forward_20d=forward_20d, forward_60d=forward_60d)

    def search(
        self,
        target_market: str,
        target_ticker: str,
        *,
        source: str = "fdr",
        top_n: int = 20,
        min_similarity: float = 55.0,
    ) -> CrossUniverseReplayResult:
        target_data = self.repository.fetch_dataframe(target_market, target_ticker, source=source)
        current_state = self.state_engine.extract_state(target_data.tail(self.window))
        meta = {(s.market, s.ticker): s for s in DynamicUniverseManager().active()}

        cases: list[CrossUniverseReplayCase] = []
        for symbol in DynamicUniverseManager().active():
            data = self.repository.fetch_dataframe(symbol.market, symbol.ticker, source=source)
            if len(data) < self.window + self.forward_60d + 20:
                continue
            prepared = self.state_engine._prepare(data)
            latest_start = len(prepared) - self.window
            for start in range(0, latest_start - self.forward_60d, self.step):
                end = start + self.window
                window_df = prepared.iloc[start:end].reset_index(drop=True)
                state = self.state_engine.extract_state(window_df)
                similarity = self.state_engine._state_similarity(current_state, state)
                if similarity < min_similarity:
                    continue
                cases.append(
                    CrossUniverseReplayCase(
                        market=symbol.market,
                        ticker=symbol.ticker,
                        name=meta.get((symbol.market, symbol.ticker), symbol).name,
                        sector=meta.get((symbol.market, symbol.ticker), symbol).sector,
                        start_date=str(pd.Timestamp(prepared.iloc[start]["Date"]).date()),
                        end_date=str(pd.Timestamp(prepared.iloc[end - 1]["Date"]).date()),
                        similarity=round(similarity, 1),
                        forward_return_20d=self.state_engine._future_return(prepared, end - 1, self.forward_20d),
                        forward_return_60d=self.state_engine._future_return(prepared, end - 1, self.forward_60d),
                        drawdown_20d=self.state_engine._future_drawdown(prepared, end - 1, self.forward_20d),
                        state=state,
                    )
                )

        cases = sorted(cases, key=lambda item: item.similarity, reverse=True)[:top_n]
        avg_return_20d = self._avg([c.forward_return_20d for c in cases])
        avg_return_60d = self._avg([c.forward_return_60d for c in cases])
        win_rate_20d = self._win_rate([c.forward_return_20d for c in cases])
        avg_drawdown_20d = self._avg([c.drawdown_20d for c in cases])
        replay_probability = self._probability(current_state, cases, avg_return_20d, win_rate_20d)
        grade = self.state_engine._grade(replay_probability)
        action = self.state_engine._action(grade)

        return CrossUniverseReplayResult(
            target_market=target_market,
            target_ticker=target_ticker,
            current_state=current_state,
            cases=cases,
            avg_return_20d=avg_return_20d,
            avg_return_60d=avg_return_60d,
            win_rate_20d=win_rate_20d,
            avg_drawdown_20d=avg_drawdown_20d,
            replay_probability=replay_probability,
            grade=grade,
            action=action,
        )

    @staticmethod
    def _avg(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return None if not valid else round(sum(valid) / len(valid), 2)

    @staticmethod
    def _win_rate(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return None if not valid else round(sum(v > 0 for v in valid) / len(valid) * 100, 1)

    @staticmethod
    def _probability(
        state: PatternState,
        cases: list[CrossUniverseReplayCase],
        avg_return_20d: float | None,
        win_rate_20d: float | None,
    ) -> int:
        similarity_score = sum(c.similarity for c in cases) / len(cases) if cases else 0
        return_score = 50 if avg_return_20d is None else min(100, max(0, 50 + avg_return_20d * 5))
        win_score = 50 if win_rate_20d is None else win_rate_20d
        sample_score = min(100, len(cases) * 5)
        score = state.state_score * 0.25 + similarity_score * 0.30 + return_score * 0.20 + win_score * 0.15 + sample_score * 0.10
        return round(max(0, min(100, score)))
