from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from datahub.repository import PriceRepository


class RecommendationChartViewer:
    """Create HTS-style timeline comparison charts for recommendation reports.

    Left side  : current chart ending at NOW.
    Right side : replay chart with the sliding-matched equivalent NOW point marked,
                 plus the future path after that point.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db", output_dir: str | Path = "output/charts") -> None:
        self.price_repo = PriceRepository(db_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.price_repo.close()

    def render(self, item: Any, rank: int, lookback_months: int = 6) -> str | None:
        matches = list(getattr(item, "replay_matches", []) or [])
        equivalent_week_index = getattr(matches[0], "equivalent_week_index", None) if matches else None
        return self.render_match(item, getattr(item, "matched_event_id"), rank, 1, lookback_months, equivalent_week_index)

    def render_replay_match(self, item: Any, match: Any, rank: int, match_rank: int, lookback_months: int = 6) -> str | None:
        proxy = SimpleNamespace(
            market=getattr(item, "market"),
            ticker=getattr(item, "ticker"),
            matched_event_id=getattr(match, "event_id"),
        )
        return self.render_match(
            proxy,
            getattr(match, "event_id"),
            rank,
            match_rank,
            lookback_months,
            getattr(match, "equivalent_week_index", None),
        )

    def render_match(
        self,
        item: Any,
        matched_event_id: str,
        rank: int,
        match_rank: int,
        lookback_months: int = 6,
        equivalent_week_index: int | None = None,
    ) -> str | None:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.patches import Rectangle
        except Exception:
            return None

        try:
            market = str(getattr(item, "market"))
            ticker = str(getattr(item, "ticker"))
            matched_market, matched_ticker, matched_date = self._parse_event_id(str(matched_event_id))
            current_daily = self.price_repo.fetch_dataframe(market, ticker, source="fdr")
            replay_daily = self.price_repo.fetch_dataframe(matched_market, matched_ticker, source="fdr")

            compare_days = max(60, lookback_months * 22)
            future_days = 132
            if equivalent_week_index is not None:
                replay_days = max(compare_days + future_days, (int(equivalent_week_index) + 30) * 5)
            else:
                replay_days = compare_days + future_days

            current_window = current_daily.tail(compare_days).reset_index(drop=True)
            replay_window = self._event_forward_window(replay_daily, matched_date, replay_days)
            if current_window.empty or replay_window.empty:
                return None

            current_weekly = self._to_weekly(current_window).tail(26).reset_index(drop=True)
            replay_weekly_full = self._to_weekly(replay_window).reset_index(drop=True)
            compare_weeks = len(current_weekly)
            fallback_index = min(compare_weeks - 1, len(replay_weekly_full) - 1)
            now_index = int(equivalent_week_index) if equivalent_week_index is not None else fallback_index
            now_index = max(0, min(now_index, len(replay_weekly_full) - 1))
            if len(current_weekly) < 5 or len(replay_weekly_full) < max(5, now_index + 1):
                return None

            fig, axes = plt.subplots(
                6,
                2,
                figsize=(16, 11.3),
                gridspec_kw={"height_ratios": [3.5, 1.1, 1.1, 1.1, 1.0, 1.25]},
                sharex="col",
            )
            fig.patch.set_facecolor("#f5f8fc")
            fig.suptitle(
                f"ADE Sliding Timeline #{rank}-{match_rank}  |  {market.upper()}:{ticker} NOW  →  {matched_event_id} week #{now_index}",
                fontsize=14,
                fontweight="bold",
                x=0.02,
                ha="left",
            )

            self._plot_price_panel(axes[0][0], current_weekly, "현재 6개월 주봉 · 마지막 봉 = NOW", Rectangle, marker_index=len(current_weekly) - 1, marker_label="NOW")
            self._plot_price_panel(axes[0][1], replay_weekly_full, f"Replay 전체 · 슬라이딩 매칭 위치 = {now_index}주", Rectangle, marker_index=now_index, marker_label="SAME AS NOW")

            for row, period, title in [(1, 5, "STO 5"), (2, 14, "STO 14"), (3, 34, "STO 34")]:
                self._plot_sto_panel(axes[row][0], current_weekly, period, f"현재 {title}", marker_index=len(current_weekly) - 1)
                self._plot_sto_panel(axes[row][1], replay_weekly_full, period, f"Replay {title}", marker_index=now_index)

            self._plot_volume_panel(axes[4][0], current_weekly, "현재 거래량", marker_index=len(current_weekly) - 1)
            self._plot_volume_panel(axes[4][1], replay_weekly_full, "Replay 거래량", marker_index=now_index)
            self._plot_future_return_panel(axes[5][0], current_weekly, "현재: 미래는 아직 없음", marker_index=len(current_weekly) - 1)
            self._plot_future_return_panel(axes[5][1], replay_weekly_full, "Replay: SAME AS NOW 이후 실제 수익률", marker_index=now_index)

            for ax_row in axes:
                for ax in ax_row:
                    ax.grid(True, alpha=0.18)
                    ax.tick_params(axis="both", labelsize=8)
                    for spine in ax.spines.values():
                        spine.set_alpha(0.18)

            fig.tight_layout(rect=[0, 0, 1, 0.965])
            file_name = f"recommendation_{rank:02d}_top{match_rank}_{market}_{ticker}_{matched_ticker}_{matched_date}_sliding_w{now_index}.png".replace(":", "_")
            out = self.output_dir / file_name
            fig.savefig(out, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return str(out.as_posix())
        except Exception:
            return None

    @staticmethod
    def _parse_event_id(event_id: str) -> tuple[str, str, str]:
        parts = event_id.split(":")
        if len(parts) >= 3:
            return parts[-3].lower(), parts[-2], parts[-1]
        raise ValueError(f"Invalid event id: {event_id}")

    @staticmethod
    def _event_forward_window(data: pd.DataFrame, event_date: str, days: int) -> pd.DataFrame:
        if data.empty or "Date" not in data.columns:
            return pd.DataFrame()
        df = data.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        dates = df["Date"].dt.date.astype(str)
        matches = dates[dates == event_date]
        if matches.empty:
            return pd.DataFrame()
        start = int(matches.index[0])
        end = min(len(df), start + max(60, days))
        return df.iloc[start:end].reset_index(drop=True)

    @staticmethod
    def _to_weekly(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" not in df.columns:
            df = df.reset_index().rename(columns={"index": "Date"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).sort_values("Date")
        return df.set_index("Date").resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().reset_index()

    @staticmethod
    def _norm_ohlc(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        base = float(out["Close"].iloc[0]) if float(out["Close"].iloc[0]) != 0 else 1.0
        for col in ["Open", "High", "Low", "Close"]:
            out[col] = out[col].astype(float) / base * 100.0
        return out

    def _plot_price_panel(self, ax: Any, weekly: pd.DataFrame, title: str, rectangle_cls: Any, marker_index: int | None = None, marker_label: str = "NOW") -> None:
        w = self._norm_ohlc(weekly)
        x = list(range(len(w)))
        ma5 = w["Close"].rolling(5, min_periods=2).mean()
        ma10 = w["Close"].rolling(10, min_periods=3).mean()
        ma20 = w["Close"].rolling(20, min_periods=5).mean()
        for i, row in w.iterrows():
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            color = "#e53935" if c >= o else "#1e5bff"
            ax.vlines(i, l, h, color=color, linewidth=1.1)
            low = min(o, c)
            height = max(abs(c - o), 0.4)
            ax.add_patch(rectangle_cls((i - 0.32, low), 0.64, height, facecolor=color, edgecolor=color, alpha=0.9))
        ax.plot(x, ma5, linewidth=1.1, label="MA5", alpha=0.85)
        ax.plot(x, ma10, linewidth=1.1, label="MA10", alpha=0.85)
        ax.plot(x, ma20, linewidth=1.1, label="MA20", alpha=0.85)
        low, high = float(w["Low"].min()), float(w["High"].max())
        for ratio in [0, 0.236, 0.382, 0.5, 0.618, 0.764, 1.0]:
            y = high - (high - low) * ratio
            ax.axhline(y, color="#8d3c75", linewidth=0.6, alpha=0.42)
        self._mark_equivalent_point(ax, w, marker_index, marker_label)
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold")
        ax.set_ylabel("Normalized")
        ax.legend(loc="upper left", fontsize=7, frameon=False, ncol=3)
        ax.set_xlim(-1, len(w))

    def _plot_sto_panel(self, ax: Any, weekly: pd.DataFrame, period: int, title: str, marker_index: int | None = None) -> None:
        sto = self._stochastic(weekly, period)
        signal = sto.rolling(3, min_periods=1).mean()
        x = list(range(len(sto)))
        ax.plot(x, sto, linewidth=1.2, color="#1e5bff", label="K")
        ax.plot(x, signal, linewidth=1.1, color="#ff8a00", label="D")
        ax.fill_between(x, sto, signal, where=(sto >= signal), alpha=0.18, color="#ff4f88")
        ax.axhline(80, color="#c018c0", linewidth=0.8, alpha=0.7)
        ax.axhline(20, color="#c018c0", linewidth=0.8, alpha=0.7)
        if marker_index is not None and 0 <= marker_index < len(sto):
            ax.axvline(marker_index, color="#111827", linewidth=1.2, linestyle="--", alpha=0.75)
            ax.scatter([marker_index], [float(sto.iloc[marker_index])], s=34, color="#111827", zorder=5)
        ax.set_ylim(0, 100)
        ax.set_title(title, loc="left", fontsize=9)
        ax.legend(loc="upper left", fontsize=7, frameon=False, ncol=2)

    @staticmethod
    def _plot_volume_panel(ax: Any, weekly: pd.DataFrame, title: str, marker_index: int | None = None) -> None:
        vol = weekly["Volume"].astype(float)
        norm = vol / max(float(vol.max()), 1.0) * 100.0
        colors = ["#e53935" if weekly["Close"].iloc[i] >= weekly["Open"].iloc[i] else "#1e5bff" for i in range(len(weekly))]
        ax.bar(range(len(weekly)), norm, color=colors, alpha=0.8, width=0.65)
        if marker_index is not None and 0 <= marker_index < len(weekly):
            ax.axvline(marker_index, color="#111827", linewidth=1.2, linestyle="--", alpha=0.75)
        ax.set_ylim(0, 110)
        ax.set_title(title, loc="left", fontsize=9)

    @staticmethod
    def _plot_future_return_panel(ax: Any, weekly: pd.DataFrame, title: str, marker_index: int | None = None) -> None:
        close = weekly["Close"].astype(float).reset_index(drop=True)
        if marker_index is None or marker_index < 0 or marker_index >= len(close):
            marker_index = len(close) - 1
        base = float(close.iloc[marker_index]) if float(close.iloc[marker_index]) != 0 else 1.0
        returns = (close / base - 1.0) * 100.0
        x = list(range(len(close)))
        ax.plot(x, returns, linewidth=1.4, color="#10a37f")
        ax.axhline(0, color="#111827", linewidth=0.8, alpha=0.55)
        ax.axvline(marker_index, color="#111827", linewidth=1.2, linestyle="--", alpha=0.78)
        ax.scatter([marker_index], [0], s=48, color="#111827", zorder=5)
        if marker_index + 1 < len(close):
            future = returns.iloc[marker_index:]
            max_future = float(future.max())
            min_future = float(future.min())
            ax.text(marker_index + 0.3, max_future, f"future max {max_future:.1f}%", fontsize=8, color="#10a37f", va="bottom")
            ax.text(marker_index + 0.3, min_future, f"future min {min_future:.1f}%", fontsize=8, color="#d64545", va="top")
        ax.set_title(title, loc="left", fontsize=9, fontweight="bold")
        ax.set_ylabel("Return %")

    @staticmethod
    def _mark_equivalent_point(ax: Any, w: pd.DataFrame, marker_index: int | None, marker_label: str) -> None:
        if marker_index is None or not (0 <= marker_index < len(w)):
            return
        y = float(w["Close"].iloc[marker_index])
        ax.axvline(marker_index, color="#111827", linewidth=1.35, linestyle="--", alpha=0.82)
        ax.scatter([marker_index], [y], s=70, color="#111827", edgecolor="white", linewidth=1.2, zorder=6)
        ax.annotate(
            marker_label,
            xy=(marker_index, y),
            xytext=(marker_index + 0.4, y * 1.02),
            fontsize=8,
            fontweight="bold",
            color="#111827",
            arrowprops={"arrowstyle": "->", "linewidth": 0.8, "color": "#111827"},
        )

    @staticmethod
    def _stochastic(df: pd.DataFrame, period: int) -> pd.Series:
        low = df["Low"].rolling(period, min_periods=max(3, period // 3)).min()
        high = df["High"].rolling(period, min_periods=max(3, period // 3)).max()
        return ((df["Close"] - low) / (high - low).replace(0, pd.NA) * 100).fillna(50)
