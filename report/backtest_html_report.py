from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Iterable


def render_backtest_html(summary: object, trades: Iterable[object], output_path: str | Path = "output/backtest_report.html") -> Path:
    rows = list(trades)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    equity = 100.0
    equity_rows = []
    for trade in sorted(rows, key=lambda x: getattr(x, "entry_date", "")):
        ret = _num(getattr(trade, "return_pct", 0))
        equity *= 1 + ret / 100.0
        equity_rows.append({"date": getattr(trade, "entry_date", ""), "equity": round(equity, 2)})

    points = " ".join(_svg_point(i, p["equity"], len(equity_rows), equity_rows) for i, p in enumerate(equity_rows))
    polyline = "" if not equity_rows else f'<polyline fill="none" stroke="#2f80ed" stroke-width="3" points="{points}" />'

    table_rows = []
    for i, trade in enumerate(rows, start=1):
        table_rows.append(
            f"""
            <tr>
              <td class="rank">{i}</td>
              <td>{html.escape(str(getattr(trade, 'signal_date', '')))}</td>
              <td><b>{html.escape(str(getattr(trade, 'name', '') or getattr(trade, 'ticker', '')))}</b><span>{html.escape(str(getattr(trade, 'market', '')).upper())}:{html.escape(str(getattr(trade, 'ticker', '')))}</span></td>
              <td>{html.escape(str(getattr(trade, 'entry_date', '')))}</td>
              <td>{html.escape(str(getattr(trade, 'exit_date', '')))}</td>
              <td class="{_cls(_num(getattr(trade, 'return_pct', 0)))}">{_num(getattr(trade, 'return_pct', 0)):.2f}%</td>
              <td class="pos">{_num(getattr(trade, 'max_return_pct', 0)):.2f}%</td>
              <td class="neg">{_num(getattr(trade, 'max_drawdown_pct', 0)):.2f}%</td>
              <td>{_num(getattr(trade, 'top1_final_similarity', 0)):.2f}%<span>W {_num(getattr(trade, 'top1_weekly_similarity', 0)):.2f}% / STO {_num(getattr(trade, 'top1_sto_similarity', 0)):.2f}%</span></td>
              <td>{html.escape(str(getattr(trade, 'top1_event_id', '')))}<span>week #{html.escape(str(getattr(trade, 'equivalent_week_index', '')))}</span></td>
            </tr>
            """
        )

    html_text = f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ADE Backtest Report</title>
<style>
:root {{ --card:#ffffffcc; --ink:#162033; --muted:#6b778c; --blue:#2f80ed; --green:#10a37f; --red:#d64545; --line:#dbe5f2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Segoe UI, Apple SD Gothic Neo, Malgun Gothic, Arial, sans-serif; background:linear-gradient(135deg,#eef6ff,#f8fbff); color:var(--ink); }}
.wrap {{ max-width:1450px; margin:0 auto; padding:34px; }}
.hero {{ display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:24px; }}
h1 {{ margin:0; font-size:34px; letter-spacing:-.04em; }}
.sub {{ color:var(--muted); margin-top:8px; }}
.pill {{ padding:10px 14px; border:1px solid var(--line); border-radius:999px; background:#fff; color:var(--muted); }}
.grid {{ display:grid; grid-template-columns:repeat(8,1fr); gap:14px; margin-bottom:20px; }}
.metric, .panel {{ background:var(--card); border:1px solid var(--line); border-radius:22px; box-shadow:0 18px 50px #2d5b9a14; backdrop-filter:blur(12px); }}
.metric {{ padding:16px; }}
.metric label {{ display:block; color:var(--muted); font-size:12px; margin-bottom:8px; }}
.metric strong {{ font-size:24px; }}
.panel {{ padding:18px; margin-bottom:22px; overflow:auto; }}
svg {{ width:100%; height:260px; background:#fff; border-radius:18px; border:1px solid #edf2f8; }}
table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:18px; overflow:hidden; }}
th {{ text-align:left; font-size:12px; color:var(--muted); text-transform:uppercase; padding:14px; border-bottom:1px solid var(--line); }}
td {{ padding:14px; border-bottom:1px solid #edf2f8; vertical-align:middle; }}
td span {{ display:block; color:var(--muted); font-size:12px; margin-top:4px; }}
.rank {{ font-weight:800; color:var(--blue); }}
.pos {{ color:var(--green); font-weight:800; }}
.neg {{ color:var(--red); font-weight:800; }}
@media(max-width:1100px) {{ .grid {{ grid-template-columns:repeat(2,1fr); }} .hero {{ display:block; }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div>
      <h1>ADE Walk-forward Backtest</h1>
      <div class="sub">각 기준일에는 그 이전 Replay만 사용하고, 이후 보유기간 성과를 검증합니다.</div>
    </div>
    <div class="pill">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  </div>
  <div class="grid">
    <div class="metric"><label>Trades</label><strong>{getattr(summary, 'trades', 0)}</strong></div>
    <div class="metric"><label>Win rate</label><strong>{_num(getattr(summary, 'win_rate', 0)):.2f}%</strong></div>
    <div class="metric"><label>Avg return</label><strong class="{_cls(_num(getattr(summary, 'avg_return', 0)))}">{_num(getattr(summary, 'avg_return', 0)):.2f}%</strong></div>
    <div class="metric"><label>Median return</label><strong class="{_cls(_num(getattr(summary, 'median_return', 0)))}">{_num(getattr(summary, 'median_return', 0)):.2f}%</strong></div>
    <div class="metric"><label>Avg max return</label><strong class="pos">{_num(getattr(summary, 'avg_max_return', 0)):.2f}%</strong></div>
    <div class="metric"><label>Avg MDD</label><strong class="neg">{_num(getattr(summary, 'avg_max_drawdown', 0)):.2f}%</strong></div>
    <div class="metric"><label>Best</label><strong class="pos">{_num(getattr(summary, 'best_return', 0)):.2f}%</strong></div>
    <div class="metric"><label>Worst</label><strong class="neg">{_num(getattr(summary, 'worst_return', 0)):.2f}%</strong></div>
  </div>
  <div class="panel">
    <h2>Equity curve</h2>
    <svg viewBox="0 0 1000 260" preserveAspectRatio="none">
      <line x1="35" y1="220" x2="980" y2="220" stroke="#dbe5f2" />
      <line x1="35" y1="30" x2="35" y2="220" stroke="#dbe5f2" />
      {polyline}
    </svg>
  </div>
  <div class="panel">
    <h2>Trades</h2>
    <table>
      <thead><tr><th>#</th><th>Signal</th><th>Stock</th><th>Entry</th><th>Exit</th><th>Return</th><th>Max</th><th>MDD</th><th>Similarity</th><th>Top1 Replay</th></tr></thead>
      <tbody>{''.join(table_rows) or '<tr><td colspan="10">No trades</td></tr>'}</tbody>
    </table>
  </div>
</div>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")
    return path


def _num(value: object) -> float:
    try:
        return float(value) if value is not None else 0.0
    except Exception:
        return 0.0


def _cls(value: float) -> str:
    return "pos" if value >= 0 else "neg"


def _svg_point(i: int, equity: float, n: int, rows: list[dict[str, object]]) -> str:
    if n <= 1:
        return "35,220"
    values = [float(r["equity"]) for r in rows]
    lo, hi = min(values), max(values)
    span = max(hi - lo, 1.0)
    x = 35 + (945 * i / (n - 1))
    y = 220 - ((equity - lo) / span * 180)
    return f"{x:.1f},{y:.1f}"
