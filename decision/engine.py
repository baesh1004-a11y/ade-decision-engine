from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from centerline.engine import CenterlineEngine
from datahub.repository import PriceRepository
from event.filter import MoneyExplosionEvent, MoneyExplosionEventFilter
from state.engine import ADEState, ADEStateEngine
from universe.manager import DynamicUniverseManager


@dataclass(frozen=True)
class ReplayFlowCase:
    market: str
    ticker: str
    name: str | None
    event: MoneyExplosionEvent
    state: ADEState
    state_similarity: int
    flow_return_10w: float | None
    flow_return_20w: float | None
    max_return_30w: float | None
    max_drawdown_30w: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionResult:
    market: str
    ticker: str
    name: str | None
    event: MoneyExplosionEvent | None
    current_state: ADEState
    centerline_reference: dict[str, object]
    cases: list[ReplayFlowCase]
    replay_score: int
    environment_score: int
    reproduction_score: int
    decision: str
    decision_reason: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReplayDecisionEngine:
    """ADE v2: money event -> state match -> flow replay -> entry decision.

    This is not a top-N recommender. It answers: enter, wait, or exclude.
    """

    def __init__(self, repository: PriceRepository, environment_score: int = 70) -> None:
        self.repository = repository
        self.environment_score = environment_score
        self.event_filter = MoneyExplosionEventFilter(min_ratio_120d=10.0)
        self.state_engine = ADEStateEngine()
        self.centerline_engine = CenterlineEngine()

    def decide(self, market: str, ticker: str, name: str | None = None, top_n: int = 20) -> DecisionResult:
        current_data = self.repository.fetch_dataframe(market, ticker, source="fdr")
        current_event = self.event_filter.latest_event(market, ticker, name, current_data)
        current_state = self.state_engine.extract(current_data.tail(140))
        centerline = self.centerline_engine.snapshot(current_data)

        cases = self._find_matching_event_flows(current_state, top_n=top_n)
        replay_score = self._replay_score(cases)
        reproduction_score = round(replay_score * 0.70 + self.environment_score * 0.30)
        decision = self._decision(reproduction_score, current_event)
        reasons = self._reasons(current_event, current_state, centerline.centerline_score, cases, replay_score, reproduction_score, decision)

        return DecisionResult(
            market=market,
            ticker=ticker,
            name=name,
            event=current_event,
            current_state=current_state,
            centerline_reference=centerline.to_dict(),
            cases=cases,
            replay_score=replay_score,
            environment_score=self.environment_score,
            reproduction_score=reproduction_score,
            decision=decision,
            decision_reason=reasons,
        )

    def _find_matching_event_flows(self, current_state: ADEState, top_n: int) -> list[ReplayFlowCase]:
        all_cases: list[ReplayFlowCase] = []
        for symbol in DynamicUniverseManager().active("kr"):
            data = self.repository.fetch_dataframe(symbol.market, symbol.ticker, source="fdr")
            if len(data) < 180:
                continue
            df = self._prepare(data)
            for event in self.event_filter.historical_events(symbol.market, symbol.ticker, symbol.name, df):
                event_index = self._index_by_date(df, event.event_date)
                if event_index is None or event_index + 30 >= len(df):
                    continue
                state_window = df.iloc[max(0, event_index - 119) : event_index + 1]
                event_state = self.state_engine.extract(state_window)
                similarity = self.state_engine.similarity(current_state, event_state)
                if similarity < 75:
                    continue
                all_cases.append(
                    ReplayFlowCase(
                        market=symbol.market,
                        ticker=symbol.ticker,
                        name=symbol.name,
                        event=event,
                        state=event_state,
                        state_similarity=similarity,
                        flow_return_10w=self._future_return(df, event_index, 50),
                        flow_return_20w=self._future_return(df, event_index, 100),
                        max_return_30w=self._max_return(df, event_index, 150),
                        max_drawdown_30w=self._max_drawdown(df, event_index, 150),
                    )
                )
        return sorted(all_cases, key=lambda c: (c.state_similarity, c.max_return_30w or -999), reverse=True)[:top_n]

    @staticmethod
    def _replay_score(cases: list[ReplayFlowCase]) -> int:
        if not cases:
            return 0
        valid_returns = [c.flow_return_20w for c in cases if c.flow_return_20w is not None]
        win_rate = sum(v > 0 for v in valid_returns) / len(valid_returns) * 100 if valid_returns else 0
        avg_return = sum(valid_returns) / len(valid_returns) if valid_returns else 0
        sim = sum(c.state_similarity for c in cases) / len(cases)
        sample = min(100, len(cases) * 5)
        ret_score = min(100, max(0, 50 + avg_return * 2))
        return round(sim * 0.35 + win_rate * 0.25 + ret_score * 0.25 + sample * 0.15)

    @staticmethod
    def _decision(score: int, event: MoneyExplosionEvent | None) -> str:
        if event is None:
            return "WAIT"
        if score >= 70:
            return "ENTRY"
        if score >= 40:
            return "WAIT"
        return "EXCLUDE"

    @staticmethod
    def _reasons(event, state: ADEState, centerline_score: int, cases: list[ReplayFlowCase], replay_score: int, reproduction_score: int, decision: str) -> list[str]:
        reasons: list[str] = []
        if event is None:
            reasons.append("현재는 대금 10배 이벤트가 확인되지 않아 진입보다 대기 판단")
        else:
            reasons.extend(event.labels)
            reasons.append(f"대금 120일 평균 대비 {event.money_ratio_120d}배")
        reasons.append(f"현재 State: {state.state_key}")
        reasons.append(f"연봉 중심값은 매매 기준 참고용: centerline {centerline_score}/100")
        reasons.append(f"과거 동일 State 이벤트 {len(cases)}건")
        reasons.append(f"Replay score {replay_score}/100, reproduction {reproduction_score}/100")
        reasons.append(f"최종 판단: {decision}")
        return reasons

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _index_by_date(df: pd.DataFrame, date_text: str) -> int | None:
        dates = pd.to_datetime(df["Date"]).dt.date.astype(str)
        matches = dates[dates == date_text]
        return None if matches.empty else int(matches.index[0])

    @staticmethod
    def _future_return(df: pd.DataFrame, index: int, days: int) -> float | None:
        if index + days >= len(df):
            return None
        entry = float(df.iloc[index]["Close"])
        exit_price = float(df.iloc[index + days]["Close"])
        return None if entry <= 0 else round((exit_price / entry - 1) * 100, 2)

    @staticmethod
    def _max_return(df: pd.DataFrame, index: int, days: int) -> float | None:
        if index + 1 >= len(df):
            return None
        entry = float(df.iloc[index]["Close"])
        highs = df.iloc[index + 1 : min(len(df), index + days + 1)]["High"]
        return None if entry <= 0 or highs.empty else round((float(highs.max()) / entry - 1) * 100, 2)

    @staticmethod
    def _max_drawdown(df: pd.DataFrame, index: int, days: int) -> float | None:
        if index + 1 >= len(df):
            return None
        entry = float(df.iloc[index]["Close"])
        lows = df.iloc[index + 1 : min(len(df), index + days + 1)]["Low"]
        return None if entry <= 0 or lows.empty else round((float(lows.min()) / entry - 1) * 100, 2)
