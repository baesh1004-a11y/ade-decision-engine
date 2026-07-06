from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from pattern.cross_universe_replay import CrossUniverseReplayResult


class ReplayChartReportWriter:
    def __init__(self, repository: PriceRepository, output_dir: str | Path = "reports/replay") -> None:
        self.repository = repository
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, result: CrossUniverseReplayResult) -> Path:
        path = self.output_dir / f"{datetime.now().date()}_{result.target_market}_{result.target_ticker}_replay.html"
        path.write_text(self._html(result), encoding="utf-8")
        return path

    def _html(self, result: CrossUniverseReplayResult) -> str:
        current = self.repository.fetch_dataframe(result.target_market, result.target_ticker, source="fdr")
        best = result.cases[0] if result.cases else None
        past = self.repository.fetch_dataframe(best.market, best.ticker, source="fdr") if best else pd.DataFrame()
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>ADE Replay</title>
<style>
body{{font-family:Arial;background:#f4f7fb;color:#111827;margin:32px}}
.card{{background:white;border-radius:18px;padding:24px;margin-bottom:22px;box-shadow:0 8px 28px #0001}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
.metric{{font-size:34px;font-weight:900}}
.badge{{display:inline-block;background:#eaf2ff;color:#1d4ed8;border-radius:999px;padding:7px 13px;font-weight:800}}
.small{{font-size:13px;color:#64748b}} svg{{width:100%;height:auto}}
table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left}}
</style></head><body>
<div class='card'><span class='badge'>ADE Visual Replay Report</span><h1>{result.target_market.upper()}:{result.target_ticker}</h1>
<div class='grid'><div><small>Replay Probability</small><div class='metric'>{result.replay_probability}%</div></div><div><small>Grade / Action</small><div class='metric'>{result.grade} / {result.action}</div></div><div><small>Avg 20D Return</small><div class='metric'>{self._fmt(result.avg_return_20d)}</div></div><div><small>20D Win Rate</small><div class='metric'>{self._fmt(result.win_rate_20d)}</div></div></div></div>
<div class='grid'><div class='card'><h2>1. Current Chart</h2>{self._price_chart(current)}</div><div class='card'><h2>2. Best Historical Match</h2>{self._best_header(best)}{self._past_chart(past, best)}</div></div>
<div class='card'><h2>3. Current vs Past Overlay</h2>{self._overlay_chart(current, past, best)}</div>
<div class='grid'><div class='card'><h2>4. RSI Compare</h2>{self._rsi_compare(current, past, best)}</div><div class='card'><h2>5. Volume Flow Compare</h2>{self._volume_compare(current, past, best)}</div></div>
<div class='card'><h2>6. Replay Cases</h2>{self._case_table(result)}</div>
<div class='card'><h2>7. Decision Summary</h2>{self._summary(result)}</div>
</body></html>"""

    @staticmethod
    def _fmt(value: float | int | None) -> str:
        return "N/A" if value is None else f"{value}%"

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            data[col] = pd.to_numeric(data[col], errors="coerce")
        return data.dropna(subset=["Close", "Volume"]).reset_index(drop=True)

    def _price_chart(self, df: pd.DataFrame) -> str:
        data = self._prepare(df).tail(100)
        if data.empty:
            return "<p>No data</p>"
        close = data["Close"]
        ma20 = close.rolling(20, min_periods=5).mean().bfill()
        ma60 = close.rolling(60, min_periods=10).mean().bfill()
        return self._line_chart([("Close", close.tolist(), "#2563eb"), ("MA20", ma20.tolist(), "#f97316"), ("MA60", ma60.tolist(), "#16a34a")], 620, 260) + self._bar_chart(data["Volume"].tolist(), 620, 120, "#94a3b8")

    def _best_header(self, best) -> str:
        if best is None:
            return "<p>No similar case.</p>"
        return f"<p><b>{best.market.upper()}:{best.ticker}</b> {best.name or ''}<br>{best.start_date} ~ {best.end_date}<br>Similarity {best.similarity}% · 20D {best.forward_return_20d}% · 60D {best.forward_return_60d}%</p>"

    def _past_chart(self, df: pd.DataFrame, best) -> str:
        if best is None or df.empty:
            return ""
        return self._price_chart(self._slice(df, best.start_date, best.end_date))

    def _overlay_chart(self, current_df: pd.DataFrame, past_df: pd.DataFrame, best) -> str:
        if best is None or current_df.empty or past_df.empty:
            return "<p>No overlay data.</p>"
        current = self._normalize(self._prepare(current_df).tail(120)["Close"])
        past = self._normalize(self._slice(past_df, best.start_date, best.end_date)["Close"])
        n = min(len(current), len(past))
        return self._line_chart([("Current", current[-n:], "#2563eb"), ("Past", past[-n:], "#64748b")], 760, 320)

    def _rsi_compare(self, current_df: pd.DataFrame, past_df: pd.DataFrame, best) -> str:
        if best is None or current_df.empty or past_df.empty:
            return "<p>No RSI data.</p>"
        cur = self._rsi(self._prepare(current_df).tail(120)["Close"])
        old = self._rsi(self._slice(past_df, best.start_date, best.end_date)["Close"])
        n = min(len(cur), len(old))
        return self._line_chart([("Current RSI", cur[-n:], "#7c3aed"), ("Past RSI", old[-n:], "#94a3b8")], 620, 260)

    def _volume_compare(self, current_df: pd.DataFrame, past_df: pd.DataFrame, best) -> str:
        if best is None or current_df.empty or past_df.empty:
            return "<p>No volume data.</p>"
        cur = self._volume_ratio(self._prepare(current_df).tail(120))
        old = self._volume_ratio(self._slice(past_df, best.start_date, best.end_date))
        n = min(len(cur), len(old))
        return self._line_chart([("Current Volume Ratio", cur[-n:], "#0ea5e9"), ("Past Volume Ratio", old[-n:], "#94a3b8")], 620, 260)

    def _case_table(self, result: CrossUniverseReplayResult) -> str:
        rows = []
        for i, c in enumerate(result.cases[:20], start=1):
            rows.append(f"<tr><td>{i}</td><td>{c.market.upper()}:{c.ticker}</td><td>{c.name or ''}</td><td>{c.start_date}~{c.end_date}</td><td>{c.similarity}%</td><td>{c.state_similarity}%</td><td>{c.shape_similarity}%</td><td>{c.forward_return_20d}%</td><td>{c.forward_return_60d}%</td><td>{c.drawdown_20d}%</td></tr>")
        return "<table><tr><th>#</th><th>Symbol</th><th>Name</th><th>Period</th><th>Total</th><th>State</th><th>Shape</th><th>20D</th><th>60D</th><th>MDD20</th></tr>" + "".join(rows) + "</table>"

    def _summary(self, result: CrossUniverseReplayResult) -> str:
        labels = "".join(f"<li>{x}</li>" for x in result.current_state.labels) or "<li>No strong current labels</li>"
        return f"<ul>{labels}</ul><p><b>State Score:</b> {result.current_state.state_score}/100 · <b>Replay:</b> {result.replay_probability}% · <b>Action:</b> {result.action}</p>"

    def _slice(self, df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        data = self._prepare(df)
        dates = pd.to_datetime(data["Date"])
        return data[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].reset_index(drop=True)

    @staticmethod
    def _normalize(series: pd.Series) -> list[float]:
        values = pd.to_numeric(series, errors="coerce").dropna().astype(float).tolist()
        if not values or values[0] <= 0:
            return []
        return [v / values[0] - 1 for v in values]

    @staticmethod
    def _volume_ratio(df: pd.DataFrame) -> list[float]:
        volume = pd.to_numeric(df["Volume"], errors="coerce")
        ma = volume.rolling(20, min_periods=5).mean().replace(0, pd.NA)
        return (volume / ma).fillna(1).clip(upper=10).tolist()

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> list[float]:
        close = pd.to_numeric(series, errors="coerce")
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period, min_periods=3).mean()
        loss = (-delta.clip(upper=0)).rolling(period, min_periods=3).mean().replace(0, pd.NA)
        return (100 - (100 / (1 + gain / loss))).fillna(50).tolist()

    def _line_chart(self, series_list: list[tuple[str, list[float], str]], width: int, height: int) -> str:
        vals = [v for _, s, _ in series_list for v in s if pd.notna(v)]
        if not vals:
            return "<p>No chart data</p>"
        min_v, max_v = min(vals), max(vals)
        spread = max(max_v - min_v, 1e-9)
        left, top, right, bottom = 40, 25, width - 25, height - 35
        lines = []
        for name, values, color in series_list:
            pts = []
            for i, v in enumerate(values):
                x = left + i * (right - left) / max(len(values) - 1, 1)
                y = bottom - ((v - min_v) / spread * (bottom - top))
                pts.append(f"{x:.1f},{y:.1f}")
            lines.append(f"<polyline points='{ ' '.join(pts) }' fill='none' stroke='{color}' stroke-width='3'/>")
        legend = " ".join(f"<text x='{left + i*135}' y='{height-8}' font-size='12' fill='{color}'>{name}</text>" for i, (name, _, color) in enumerate(series_list))
        return f"<svg viewBox='0 0 {width} {height}'><line x1='{left}' y1='{bottom}' x2='{right}' y2='{bottom}' stroke='#d1d5db'/><line x1='{left}' y1='{top}' x2='{left}' y2='{bottom}' stroke='#d1d5db'/>{''.join(lines)}{legend}</svg>"

    def _bar_chart(self, values: list[float], width: int, height: int, color: str) -> str:
        if not values:
            return ""
        max_v = max(values) or 1
        bars = []
        left, top, bottom = 40, 15, height - 25
        bar_w = (width - 65) / max(len(values), 1)
        for i, value in enumerate(values):
            h = (value / max_v) * (bottom - top)
            x = left + i * bar_w
            y = bottom - h
            bars.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{max(bar_w-1,1):.1f}' height='{h:.1f}' fill='{color}'/>")
        return f"<svg viewBox='0 0 {width} {height}'>{''.join(bars)}</svg>"
