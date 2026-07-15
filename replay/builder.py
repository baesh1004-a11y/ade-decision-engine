from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from centerline.engine import CenterlineEngine
from datahub.repository import PriceRepository
from event.filter import MoneyExplosionEventFilter
from replay.analyzer import ReplayEventAnalyzer
from replay.models import ADE_VERSION, ReplayEvent, ReplayEventFlow
from replay.repository import ReplayEventRepository
from state.engine import ADEStateEngine
from universe.manager import DynamicUniverseManager
from universe.models import UniverseSymbol


class ReplayEventDBBuilder:
    def __init__(
        self,
        db_path: str | Path = "datahub/market.db",
        ade_version: str = ADE_VERSION,
        price_source: str = "fdr",
    ) -> None:
        self.db_path = Path(db_path)
        self.ade_version = ade_version
        self.price_source = price_source
        self.price_repo = PriceRepository(self.db_path)
        self.replay_repo = ReplayEventRepository(self.db_path)
        self.event_filter = MoneyExplosionEventFilter(min_ratio_120d=10.0)
        self.state_engine = ADEStateEngine()
        self.centerline_engine = CenterlineEngine()
        self.analyzer = ReplayEventAnalyzer(max_flow_days=240)
        self.last_stats: dict[str, int | str | None] = {}

    def close(self) -> None:
        self.price_repo.close()
        self.replay_repo.close()

    def build(self, market: str = "kr", limit: int = 0, clear: bool = False) -> tuple[int, int]:
        migrated_checkpoints = 0
        if clear:
            self.replay_repo.clear(self.ade_version)
        else:
            migrated_checkpoints = self.replay_repo.bootstrap_checkpoints_from_existing_replay(
                self.ade_version,
                market=market,
                source=self.price_source,
            )
            if migrated_checkpoints:
                print(
                    f"[MIGRATION] existing Replay DB reused; "
                    f"created checkpoints={migrated_checkpoints}"
                )

        symbols = self._active_symbols(market)
        if limit > 0:
            symbols = symbols[:limit]

        total_events = 0
        total_flows = 0
        updated_symbols = 0
        skipped_up_to_date = 0
        skipped_no_data = 0

        for idx, symbol in enumerate(symbols, start=1):
            data = self.price_repo.fetch_dataframe(
                symbol.market,
                symbol.ticker,
                source=self.price_source,
            )
            df = self._prepare(data)
            if len(df) < 180:
                skipped_no_data += 1
                print(f"[{idx}/{len(symbols)}] {symbol.market.upper()}:{symbol.ticker} SKIP no-data")
                continue

            latest_price_date = str(pd.Timestamp(df.iloc[-1]["Date"]).date())
            last_processed_date = None if clear else self.replay_repo.get_last_processed_date(
                self.ade_version,
                symbol.market,
                symbol.ticker,
            )

            if last_processed_date is not None and latest_price_date <= last_processed_date:
                skipped_up_to_date += 1
                print(
                    f"[{idx}/{len(symbols)}] {symbol.market.upper()}:{symbol.ticker} "
                    f"UP-TO-DATE last={last_processed_date}"
                )
                continue

            scan_df = self._incremental_scan_window(df, last_processed_date)
            detected_events = self.event_filter.historical_events(
                symbol.market,
                symbol.ticker,
                symbol.name,
                scan_df,
            )
            new_events = [
                event
                for event in detected_events
                if last_processed_date is None or event.event_date > last_processed_date
            ]

            symbol_event_count = 0
            symbol_flow_count = 0
            for event in new_events:
                event_index = self._index_by_date(df, event.event_date)
                if event_index is None or event_index + 5 >= len(df):
                    continue
                replay_event, flows = self._make_event(symbol.name, event, df, event_index)
                self.replay_repo.upsert_event(replay_event)
                self.replay_repo.replace_flow(replay_event.event_id, flows)
                total_events += 1
                total_flows += len(flows)
                symbol_event_count += 1
                symbol_flow_count += len(flows)

            self.replay_repo.set_last_processed_date(
                self.ade_version,
                symbol.market,
                symbol.ticker,
                latest_price_date,
            )
            self.replay_repo.commit()
            updated_symbols += 1
            print(
                f"[{idx}/{len(symbols)}] {symbol.market.upper()}:{symbol.ticker} "
                f"from={last_processed_date or 'FULL'} to={latest_price_date} "
                f"new_events={symbol_event_count} flows={symbol_flow_count}"
            )

        self.last_stats = {
            "symbols": len(symbols),
            "migrated_checkpoints": migrated_checkpoints,
            "updated_symbols": updated_symbols,
            "skipped_up_to_date": skipped_up_to_date,
            "skipped_no_data": skipped_no_data,
            "new_events": total_events,
            "new_flows": total_flows,
            "latest_checkpoint": self.replay_repo.latest_checkpoint(self.ade_version, market),
            "checkpoint_symbols": self.replay_repo.checkpoint_count(self.ade_version, market),
        }
        return total_events, total_flows

    def _active_symbols(self, market: str) -> list[UniverseSymbol]:
        if market.lower() != "us":
            return DynamicUniverseManager().active(market)

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='us_universe'"
            ).fetchone()
            if exists is None:
                return DynamicUniverseManager().active("us")
            rows = conn.execute(
                """
                SELECT symbol, name, sector
                FROM us_universe
                WHERE enabled=1
                ORDER BY market_cap DESC, avg_dollar_volume DESC, symbol
                """
            ).fetchall()
            if not rows:
                return DynamicUniverseManager().active("us")
            return [
                UniverseSymbol(
                    market="us",
                    ticker=str(row["symbol"]),
                    name=row["name"],
                    sector=row["sector"],
                    source="us_universe",
                )
                for row in rows
            ]
        finally:
            conn.close()

    @staticmethod
    def _incremental_scan_window(df: pd.DataFrame, last_processed_date: str | None) -> pd.DataFrame:
        if last_processed_date is None:
            return df
        dates = pd.to_datetime(df["Date"])
        matches = df.index[dates.dt.date.astype(str) <= last_processed_date].tolist()
        if not matches:
            return df
        last_index = int(matches[-1])
        start_index = max(0, last_index - 180)
        return df.iloc[start_index:].reset_index(drop=True)

    def _make_event(self, name: str | None, event, df: pd.DataFrame, event_index: int) -> tuple[ReplayEvent, list[ReplayEventFlow]]:
        state_window = df.iloc[max(0, event_index - 119) : event_index + 1]
        state = self.state_engine.extract(state_window)
        center = self.centerline_engine.snapshot(state_window)
        end_index, end_reason = self.analyzer.end_index(df, event_index)
        event_id = f"{event.market.upper()}:{event.ticker}:{event.event_date}"
        replay_event = ReplayEvent(
            event_id=event_id,
            ade_version=self.ade_version,
            market=event.market,
            ticker=event.ticker,
            name=name,
            event_date=event.event_date,
            money_ratio_20d=event.money_ratio_20d,
            money_ratio_120d=event.money_ratio_120d,
            bullish_body=event.bullish_body,
            long_base=event.long_base,
            sto_state=state.sto_structure,
            ma_state=state.ma_structure,
            weekly_position=state.weekly_position,
            money_flow=state.money_flow,
            year_center=center.yearly,
            half_center=center.half_year,
            quarter_center=center.quarterly,
            month_center=center.monthly,
            event_end_date=str(pd.Timestamp(df.iloc[end_index]["Date"]).date()),
            event_end_reason=end_reason,
            max_return=self.analyzer.max_return(df, event_index, end_index),
            max_drawdown=self.analyzer.max_drawdown(df, event_index, end_index),
        )
        return replay_event, self._make_flows(event_id, df, event_index, end_index)

    def _make_flows(self, event_id: str, df: pd.DataFrame, start: int, end: int) -> list[ReplayEventFlow]:
        entry = float(df.iloc[start]["Close"])
        peak = entry
        flows: list[ReplayEventFlow] = []
        for i in range(start, end + 1):
            flow_state = self.state_engine.extract(df.iloc[max(0, i - 119) : i + 1])
            close = float(df.iloc[i]["Close"])
            low = float(df.iloc[i]["Low"])
            peak = max(peak, close)
            flows.append(
                ReplayEventFlow(
                    event_id=event_id,
                    day_index=i - start,
                    trade_date=str(pd.Timestamp(df.iloc[i]["Date"]).date()),
                    close=round(close, 4),
                    volume=float(df.iloc[i]["Volume"]),
                    return_pct=0.0 if entry <= 0 else round((close / entry - 1) * 100, 2),
                    drawdown_pct=0.0 if peak <= 0 else round((low / peak - 1) * 100, 2),
                    sto_state=flow_state.sto_structure,
                    ma_state=flow_state.ma_structure,
                    weekly_position=flow_state.weekly_position,
                )
            )
        return flows

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _index_by_date(df: pd.DataFrame, date_text: str) -> int | None:
        dates = pd.to_datetime(df["Date"]).dt.date.astype(str)
        matches = dates[dates == date_text]
        return None if matches.empty else int(matches.index[0])
