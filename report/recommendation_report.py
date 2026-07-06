from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from recommendation.models import RecommendationScore


class RecommendationReportWriter:
    """Generate an HTML report with evidence charts for each recommendation."""

    def __init__(self, output_dir: str | Path = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, score: RecommendationScore, market_data: pd.DataFrame) -> Path:
        ticker = score.ticker.replace("/", "_")
        path = self.output_dir / f"{datetime.now().date()}_{score.market}_{ticker}.html"
        path.write_text(self._html(score, market_data), encoding="utf-8")
        return path

    def _html(self, score: RecommendationScore, market_data: pd.DataFrame) -> str:
        data = market_data.copy().tail(120).reset_index(drop=True)
        reasons = "".join(f"<li>{reason}</li>" for reason in score.reasons)
        risks = "".join(f"<li>{risk}</li>" for risk in score.risk_flags) or "<li>No major risk flag</li>"
        return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>ADE Report {score.ticker}</title>
<style>
body{{font-family:Arial,sans-serif;background:#f6f8fb;color:#172033;margin:36px}}
.card{{background:white;border-radius:16px;padding:24px;margin-bottom:22px;box-shadow:0 6px 24px #0001}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
.metric{{font-size:34px;font-weight:800}}
.badge{{background:#e9f2ff;color:#1a5fb4;border-radius:999px;padding:6px 12px;font-weight:700}}
svg{{width:100%;height:auto}} li{{margin:7px 0}}
</style></head><body>
<div class='card'>
<span class='badge'>ADE Recommendation Evidence Report</span>
<h1>{score.ticker} | {score.name or ''}</h1>
<p>{score.market.upper()} · {score.sector or '-'} · {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div class='grid'>
<div><small>Final score</small><div class='metric'>{score.final_score}/100</div></div>
<div><small>Action</small><div class='metric'>{score.action}</div></div>
<div><small>Grade</small><div class='metric'>{score.grade}</div></div>
<div><small>Confidence</small><div class='metric'>{score.confidence:.0%}</div></div>
</div></div>
<div class='card'><h2>1. Score evidence chart</h2>{self._component_chart(score.components)}</div>
<div class='card'><h2>2. Price trend evidence</h2>{self._price_chart(data)}</div>
<div class='card'><h2>3. Similarity evidence</h2>{self._similarity_chart(score.components)}</div>
<div class='card'><h2>Recommendation reasons</h2><ul>{reasons}</ul></div>
<div class='card'><h2>Risk flags</h2><ul>{risks}</ul></div>
</body></html>"""

    def _component_chart(self, components: dict[str, int]) -> str:
        labels = list(components.keys())
        values = list(components.values())
        max_value = max(values) if values else 1
        rows = []
        y = 40
        for label, value in zip(labels, values):
            width = int(420 * value / max_value) if max_value else 0
            rows.append(f"<text x='10' y='{y+15}' font-size='13'>{label}</text>")
            rows.append(f"<rect x='120' y='{y}' width='{width}' height='20' rx='5' fill='#3b82f6'/>")
            rows.append(f"<text x='{130+width}' y='{y+15}' font-size='13'>{value}</text>")
            y += 36
        return f"<svg viewBox='0 0 620 {y+20}'>{''.join(rows)}</svg>"

    def _price_chart(self, df: pd.DataFrame) -> str:
        if df.empty or 'Close' not in df.columns:
            return "<p>No price data</p>"
        close = pd.to_numeric(df['Close'], errors='coerce').dropna().tail(90).reset_index(drop=True)
        if close.empty:
            return "<p>No price data</p>"
        ma20 = close.rolling(20).mean()
        min_v = float(min(close.min(), ma20.min(skipna=True)))
        max_v = float(max(close.max(), ma20.max(skipna=True)))
        spread = max(max_v - min_v, 1.0)
        def point(i: int, value: float) -> str:
            x = 40 + i * (520 / max(len(close) - 1, 1))
            y = 260 - ((value - min_v) / spread * 210)
            return f"{x:.1f},{y:.1f}"
        close_points = " ".join(point(i, float(v)) for i, v in enumerate(close))
        ma_points = " ".join(point(i, float(v)) for i, v in enumerate(ma20) if not pd.isna(v))
        return f"""<svg viewBox='0 0 620 310'>
<line x1='40' y1='260' x2='580' y2='260' stroke='#d0d7e2'/><line x1='40' y1='40' x2='40' y2='260' stroke='#d0d7e2'/>
<polyline points='{close_points}' fill='none' stroke='#2563eb' stroke-width='3'/>
<polyline points='{ma_points}' fill='none' stroke='#f97316' stroke-width='3'/>
<text x='45' y='25' font-size='13'>Close (blue) vs MA20 (orange)</text>
<text x='45' y='292' font-size='12'>Latest close: {float(close.iloc[-1]):,.2f}</text>
</svg>"""

    def _similarity_chart(self, components: dict[str, int]) -> str:
        trend = components.get('trend', 0) / 20 * 100
        volume = components.get('volume', 0) / 15 * 100
        momentum = components.get('momentum', 0) / 20 * 100
        risk = components.get('risk', 0) / 10 * 100
        pattern = components.get('pattern', 0) / 15 * 100
        similarity = round((trend * 0.25 + volume * 0.2 + momentum * 0.25 + risk * 0.15 + pattern * 0.15), 1)
        bars = [('Trend match', trend), ('Momentum match', momentum), ('Volume match', volume), ('Pattern match', pattern), ('Risk fit', risk), ('Overall similarity', similarity)]
        rows = []
        y = 40
        for label, value in bars:
            width = int(420 * value / 100)
            rows.append(f"<text x='10' y='{y+15}' font-size='13'>{label}</text>")
            rows.append(f"<rect x='150' y='{y}' width='{width}' height='20' rx='5' fill='#10b981'/>")
            rows.append(f"<text x='{160+width}' y='{y+15}' font-size='13'>{value:.1f}%</text>")
            y += 36
        return f"<svg viewBox='0 0 650 {y+20}'>{''.join(rows)}</svg>"
