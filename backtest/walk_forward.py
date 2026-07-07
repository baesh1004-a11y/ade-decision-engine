from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from similarity.sliding_replay_matcher import SlidingReplayWindowMatcher
from sto.structure_similarity import STOStructureSimilarityEngine
from weekly.shape_similarity import WeeklyShapeSimilarityEngine


@dataclass(frozen=True)
class BacktestTrade:
    signal_date: str
    market: str
    ticker: str
    name: str | None
    entry_date: str
    entry_price: float
    exit_date: str | None
    exit_price: float | None
    holding_days: int
    return_pct: float | None
    max_return_pct: float | None
    max_drawdown_pct: float | None
    top1_event_id: str
    top1_weekly_similarity: float
    top1_sto_similarity: float
    top1_final_similarity: float
    equivalent_week_index: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestSummary:
    trades: int
    win_rate: float
    avg_return: float
    median_return: float
    avg_max_return: float
    avg_max_drawdown: float
    best_return: float
    worst_return: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WalkForwardBacktester:
    """Walk-forward ADE backtester.

    At each signal date, this backtester uses only replay events that happened
    before the signal date. It then checks the realized forward return over a
    fixed holding window.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)
        self.weekly_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_engine = STOStructureSimilarityEngine()
        self.sliding_matcher = SlidingReplayWindowMatcher(min_weeks=10, max_weeks=26)

    def close(self) -> None:
        self.price_repo.close()
        self.conn.close()

    def run(
        self,
        start: str,
        end: str,
        market: str = "kr",
        lookback_months: int = 6,
        hold_days: int = 126,
        min_weekly_similarity: float = 85.0,
        min_sto_similarity: float = 85.0,
        top_n: int = 20,
        event_limit: int = 0,
        weekly_pool_n: int = 80,
    ) -> list[BacktestTrade]:
        signal_events = self._signal_events(start, end, market, event_limit)
        trades: list[BacktestTrade] = []
        for idx, signal in enumerate(signal_events, start=1):
            trade = self._evaluate_signal(
                signal,
                lookback_months=lookback_months,
                hold_days=hold_days,
                min_weekly_similarity=min_weekly_similarity,
                min_sto_similarity=min_sto_similarity,
                weekly_pool_n=weekly_pool_n,
            )
            if trade is not None:
                trades.append(trade)
                trades = sorted(trades, key=lambda x: x.top1_final_similarity, reverse=True)[:top_n]
            print(f"[{idx}/{len(signal_events)}] {signal['event_date']} {signal['market']}:{signal['ticker']} trades={len(trades)}")
        return sorted(trades, key=lambda x: (x.signal_date, x.top1_final_similarity), reverse=True)

    def summarize(self, trades: list[BacktestTrade]) -> BacktestSummary:
        returns = [t.return_pct for t in trades if t.return_pct is not None]
        max_returns = [t.max_return_pct for t in trades if t.max_return_pct is not None]
        drawdowns = [t.max_drawdown_pct for t in trades if t.max_drawdown_pct is not None]
        if not returns:
            return BacktestSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        s = pd.Series(returns)
        return BacktestSummary(
            trades=len(returns),
            win_rate=round(float((s > 0).mean() * 100), 2),
            avg_return=round(float(s.mean()), 2),
            median_return=round(float(s.median()), 2),
            avg_max_return=round(float(pd.Series(max_returns).mean()), 2) if max_returns else 0.0,
            avg_max_drawdown=round(float(pd.Series(drawdowns).mean()), 2) if drawdowns else 0.0,
            best_return=round(float(s.max()), 2),
            worst_return=round(float(s.min()), 2),
        )

    def _evaluate_signal(
        self,
        signal: sqlite3.Row,
        lookback_months: int,
        hold_days: int,
        min_weekly_similarity: float,
        min_sto_similarity: float,
        weekly_pool_n: int,
    ) -> BacktestTrade | None:
        signal_date = str(signal["event_date"])
        market = str(signal["market"])
        ticker = str(signal["ticker"])
        data = self.price_repo.fetch_dataframe(market, ticker, source="fdr")
        if data.empty or "Date" not in data.columns:
            return None
        df = self._prepare(data)
        signal_idx = self._index_on_or_before(df, signal_date)
        if signal_idx is None:
            return None
        lookback_days = max(40, lookback_months * 22)
        current_window = df.iloc[max(0, signal_idx - lookback_days + 1) : signal_idx + 1].reset_index(drop=True)
        if len(current_window) < 40:
            return None
        current_shape = self.weekly_engine.extract(current_window)
        current_sto = self.sto_engine.extract(df.iloc[: signal_idx + 1].reset_index(drop=True))

        historical_events = self._historical_events_before(signal_date, market)
        weekly_hits: list[tuple[float, sqlite3.Row, pd.DataFrame]] = []
        for event in historical_events:
            replay_timeline = self._event_forward_window_days(event, days=max(260, lookback_months * 22 + hold_days))
            if replay_timeline.empty:
                continue
            first_segment = replay_timeline.head(lookback_days).reset_index(drop=True)
            if first_segment.empty:
                continue
            sim = self.weekly_engine.similarity(current_shape, self.weekly_engine.extract(first_segment))
            if sim >= min_weekly_similarity:
                weekly_hits.append((sim, event, replay_timeline))
        weekly_hits = sorted(weekly_hits, key=lambda x: x[0], reverse=True)[:weekly_pool_n]

        best = None
        for _score, event, replay_timeline in weekly_hits:
            sliding = self.sliding_matcher.find_best(current_window, replay_timeline, future_min_weeks=4)
            if sliding is None:
                continue
            if sliding.weekly_similarity < min_weekly_similarity or sliding.sto_similarity < min_sto_similarity:
                continue
            if best is None or sliding.final_similarity > best[0].final_similarity:
                best = (sliding, event)
        if best is None:
            return None

        entry_idx = min(signal_idx + 1, len(df) - 1)
        exit_idx = min(entry_idx + hold_days, len(df) - 1)
        if exit_idx <= entry_idx:
            return None
        entry_price = float(df.iloc[entry_idx]["Close"])
        exit_price = float(df.iloc[exit_idx]["Close"])
        future = df.iloc[entry_idx : exit_idx + 1]
        max_high = float(future["High"].max())
        min_low = float(future["Low"].min())
        ret = (exit_price / entry_price - 1) * 100 if entry_price > 0 else None
        max_ret = (max_high / entry_price - 1) * 100 if entry_price > 0 else None
        mdd = (min_low / entry_price - 1) * 100 if entry_price > 0 else None
        sliding, event = best
        return BacktestTrade(
            signal_date=signal_date,
            market=market,
            ticker=ticker,
            name=signal["name"],
            entry_date=str(pd.Timestamp(df.iloc[entry_idx]["Date"]).date()),
            entry_price=round(entry_price, 4),
            exit_date=str(pd.Timestamp(df.iloc[exit_idx]["Date"]).date()),
            exit_price=round(exit_price, 4),
            holding_days=exit_idx - entry_idx,
            return_pct=round(ret, 2) if ret is not None else None,
            max_return_pct=round(max_ret, 2) if max_ret is not None else None,
            max_drawdown_pct=round(mdd, 2) if mdd is not None else None,
            top1_event_id=str(event["event_id"]),
            top1_weekly_similarity=sliding.weekly_similarity,
            top1_sto_similarity=sliding.sto_similarity,
            top1_final_similarity=sliding.final_similarity,
            equivalent_week_index=sliding.end_week_index,
        )

    def _signal_events(self, start: str, end: str, market: str, limit: int = 0) -> list[sqlite3.Row]:
        sql = """
            SELECT * FROM replay_events
            WHERE event_date >= ? AND event_date <= ? AND market = ?
            ORDER BY event_date ASC, money_ratio_120d DESC
        """
        rows = self.conn.execute(sql, (start, end, market)).fetchall()
        if limit > 0:
            return rows[:limit]
        return rows

    def _historical_events_before(self, cutoff: str, market: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM replay_events
            WHERE event_date < ? AND market = ?
            ORDER BY event_date ASC
            """,
            (cutoff, market),
        ).fetchall()

    def _event_forward_window_days(self, event: sqlite3.Row, days: int) -> pd.DataFrame:
        data = self.price_repo.fetch_dataframe(event["market"], event["ticker"], source="fdr")
        if data.empty or "Date" not in data.columns:
            return pd.DataFrame()
        df = self._prepare(data)
        idx = self._index_on_or_after(df, str(event["event_date"]))
        if idx is None:
            return pd.DataFrame()
        end = min(len(df), idx + max(60, days))
        return df.iloc[idx:end].reset_index(drop=True)

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"]).sort_values("Date").reset_index(drop=True)

    @staticmethod
    def _index_on_or_before(df: pd.DataFrame, date_text: str) -> int | None:
        d = pd.to_datetime(date_text)
        matches = df.index[df["Date"] <= d].tolist()
        return int(matches[-1]) if matches else None

    @staticmethod
    def _index_on_or_after(df: pd.DataFrame, date_text: str) -> int | None:
        d = pd.to_datetime(date_text)
        matches = df.index[df["Date"] >= d].tolist()
        return int(matches[0]) if matches else None
