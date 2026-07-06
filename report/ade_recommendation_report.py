from __future__ import annotations

from datetime import datetime
from pathlib import Path

from datahub.provenance import DataProvenanceStore
from recommendation.ade_engine import ADERecommendation


class ADERecommendationReportWriter:
    def __init__(self, output_dir: str | Path = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, recommendations: list[ADERecommendation]) -> Path:
        path = self.output_dir / f"{datetime.now().date()}_ade_recommendations.html"
        path.write_text(self._html(recommendations), encoding="utf-8")
        return path

    def _html(self, recommendations: list[ADERecommendation]) -> str:
        rows = "".join(self._row(item) for item in recommendations)
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>ADE Recommendations</title>
<style>
body{{font-family:Arial;background:#f4f7fb;color:#111827;margin:32px}}
.card{{background:white;border-radius:18px;padding:24px;margin-bottom:22px;box-shadow:0 8px 28px #0001}}
.badge{{display:inline-block;background:#eaf2ff;color:#1d4ed8;border-radius:999px;padding:7px 13px;font-weight:800}}
.metric{{font-size:32px;font-weight:900}} table{{width:100%;border-collapse:collapse}}td,th{{padding:11px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}}
.S{{color:#dc2626;font-weight:900}}.A{{color:#16a34a;font-weight:900}}.B{{color:#2563eb;font-weight:900}}.C{{color:#b45309;font-weight:900}}
.small{{font-size:13px;color:#64748b}}
</style></head><body>
<div class='card'><span class='badge'>ADE Daily Recommendation</span><h1>Top Recommendations</h1>{self._provenance()}</div>
<div class='card'><table><tr><th>Rank</th><th>Symbol</th><th>Final</th><th>Grade</th><th>Action</th><th>Candidate</th><th>Replay</th><th>Evidence</th><th>Report</th></tr>{rows}</table></div>
</body></html>"""

    def _row(self, item: ADERecommendation) -> str:
        c = item.candidate
        r = item.replay
        reasons = "".join(f"<li>{reason}</li>" for reason in item.reasons[:6])
        link = f"<a href='{Path(item.report_path).as_posix()}'>open</a>" if item.report_path else "-"
        return f"""<tr>
<td>{item.rank}</td><td><b>{c.market.upper()}:{c.ticker}</b><br>{c.name or ''}</td><td class='metric'>{item.final_score}</td><td class='{item.grade}'>{item.grade}</td><td>{item.action}</td>
<td>{c.score}<br><span class='small'>centerline {c.centerline_score} / state {c.state_score}</span></td>
<td>{r.replay_probability}%<br><span class='small'>20D {r.avg_return_20d}% / win {r.win_rate_20d}%</span></td>
<td><ul>{reasons}</ul></td><td>{link}</td></tr>"""

    def _provenance(self) -> str:
        store = DataProvenanceStore("datahub/market.db")
        try:
            s = store.summary()
        finally:
            store.close()
        return f"<p class='small'>Historical: {s.historical_source} · Realtime: {s.realtime_source} · DB: {s.database_source} · Quality: {s.quality_label} · Updated: {s.last_updated} · Symbols: {s.total_symbols} · Rows: {s.total_rows}</p>"
