from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

from report.chart_viewer import RecommendationChartViewer


def render_recommendation_html(
    recommendations: Iterable[object],
    output_path: str | Path = "output/recommendation_report.html",
    lookback_months: int = 6,
) -> Path:
    rows = list(recommendations)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    chart_viewer = RecommendationChartViewer(output_dir=path.parent / "charts")
    chart_paths: dict[tuple[int, int], str] = {}
    try:
        for idx, item in enumerate(rows, start=1):
            matches = list(getattr(item, "replay_matches", []) or [])
            if not matches:
                chart_path = chart_viewer.render(item, idx, lookback_months=lookback_months)
                if chart_path:
                    chart_paths[(idx, 1)] = os.path.relpath(chart_path, start=path.parent).replace("\\", "/")
                continue
            for match_rank, match in enumerate(matches[:5], start=1):
                chart_path = chart_viewer.render_replay_match(item, match, idx, match_rank, lookback_months=lookback_months)
                if chart_path:
                    chart_paths[(idx, match_rank)] = os.path.relpath(chart_path, start=path.parent).replace("\\", "/")
    finally:
        chart_viewer.close()

    table_rows = []
    cards = []
    for idx, item in enumerate(rows, start=1):
        name = html.escape(str(getattr(item, "name", "") or ""))
        ticker = html.escape(str(getattr(item, "ticker", "")))
        market = html.escape(str(getattr(item, "market", "")).upper())
        decision = html.escape(str(getattr(item, "decision", "")))
        final = _num(getattr(item, "final_similarity", 0))
        weekly = _num(getattr(item, "weekly_similarity", 0))
        sto = _num(getattr(item, "sto_similarity", 0))
        max_return = _num(getattr(item, "matched_max_return", 0))
        mdd = _num(getattr(item, "matched_max_drawdown", 0))
        recent_event = html.escape(str(getattr(item, "recent_event_date", "")))
        money = _num(getattr(item, "recent_money_ratio", 0))
        matches = list(getattr(item, "replay_matches", []) or [])

        table_rows.append(
            f"""
            <tr>
              <td class="rank">{idx}</td>
              <td><b>{name or ticker}</b><span>{market}:{ticker}</span></td>
              <td>{_badge(decision)}</td>
              <td>{_bar(final)}</td>
              <td>{_bar(weekly)}</td>
              <td>{_bar(sto)}</td>
              <td class="pos">{max_return:.2f}%</td>
              <td class="neg">{mdd:.2f}%</td>
              <td>{recent_event}</td>
            </tr>
            """
        )

        replay_rows = []
        chart_sections = []
        for match_rank, match in enumerate(matches[:5], start=1):
            m_event_id = html.escape(str(getattr(match, "event_id", "")))
            m_name = html.escape(str(getattr(match, "name", "") or getattr(match, "ticker", "")))
            m_market = html.escape(str(getattr(match, "market", "")).upper())
            m_ticker = html.escape(str(getattr(match, "ticker", "")))
            m_weekly = _num(getattr(match, "weekly_similarity", 0))
            m_sto = _num(getattr(match, "sto_similarity", 0))
            m_final = _num(getattr(match, "final_similarity", 0))
            m_return = _num(getattr(match, "max_return", 0))
            m_mdd = _num(getattr(match, "max_drawdown", 0))
            replay_rows.append(
                f"""
                <tr>
                  <td class="rank">Top {match_rank}</td>
                  <td><b>{m_name}</b><span>{m_market}:{m_ticker}</span></td>
                  <td>{m_event_id}</td>
                  <td>{_bar(m_final)}</td>
                  <td>{_bar(m_weekly)}</td>
                  <td>{_bar(m_sto)}</td>
                  <td class="pos">{m_return:.2f}%</td>
                  <td class="neg">{m_mdd:.2f}%</td>
                </tr>
                """
            )
            img = chart_paths.get((idx, match_rank))
            chart_img = f'<div class="chart-box"><img src="{html.escape(img)}" alt="ADE Top{match_rank} chart comparison" /></div>' if img else '<div class="chart-missing">Chart image could not be generated.</div>'
            chart_sections.append(
                f"""
                <details class="replay-detail" {'open' if match_rank == 1 else ''}>
                  <summary>Top {match_rank} Replay · {m_name} · {m_event_id} · Final {m_final:.2f}%</summary>
                  {chart_img}
                </details>
                """
            )

        if not replay_rows:
            replay_rows.append('<tr><td colspan="8">No replay matches</td></tr>')

        reason_items = "".join(f"<li>{html.escape(str(reason))}</li>" for reason in getattr(item, "reasons", []))
        cards.append(
            f"""
            <section class="card">
              <div class="card-head">
                <div>
                  <div class="eyebrow">Recommendation #{idx}</div>
                  <h2>{name or ticker} <small>{market}:{ticker}</small></h2>
                </div>
                {_badge(decision)}
              </div>
              <div class="grid">
                <div class="metric"><label>Final similarity</label>{_bar(final)}</div>
                <div class="metric"><label>Weekly shape</label>{_bar(weekly)}</div>
                <div class="metric"><label>STO structure</label>{_bar(sto)}</div>
                <div class="metric"><label>Top1 max return</label><strong class="pos">{max_return:.2f}%</strong></div>
                <div class="metric"><label>Top1 MDD</label><strong class="neg">{mdd:.2f}%</strong></div>
                <div class="metric"><label>Recent money event</label><strong>{recent_event}</strong><small>{money:.2f}x</small></div>
              </div>
              <div class="replay">
                <b>Top5 Replay Matches</b> · 같은 종목일 필요 없음 · Replay DB 전체에서 주봉 Shape와 STO 구조가 모두 유사한 과거 이벤트
              </div>
              <div class="mini-table">
                <table>
                  <thead><tr><th>Rank</th><th>Replay stock</th><th>Event</th><th>Final</th><th>Weekly</th><th>STO</th><th>Max return</th><th>MDD</th></tr></thead>
                  <tbody>{''.join(replay_rows)}</tbody>
                </table>
              </div>
              {''.join(chart_sections)}
              <ul>{reason_items}</ul>
            </section>
            """
        )

    html_text = f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ADE Recommendation Report</title>
<style>
:root {{ --bg:#f5f8fc; --card:#ffffffcc; --ink:#162033; --muted:#6b778c; --blue:#2f80ed; --green:#10a37f; --red:#d64545; --line:#dbe5f2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Segoe UI, Apple SD Gothic Neo, Malgun Gothic, Arial, sans-serif; background:linear-gradient(135deg,#eef6ff,#f8fbff); color:var(--ink); }}
.wrap {{ max-width:1500px; margin:0 auto; padding:34px; }}
.hero {{ display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:24px; }}
h1 {{ margin:0; font-size:34px; letter-spacing:-.04em; }}
.sub {{ color:var(--muted); margin-top:8px; }}
.pill {{ padding:10px 14px; border:1px solid var(--line); border-radius:999px; background:#fff; color:var(--muted); }}
.panel, .card {{ background:var(--card); border:1px solid var(--line); border-radius:24px; box-shadow:0 18px 50px #2d5b9a14; backdrop-filter:blur(12px); }}
.panel {{ overflow:hidden; margin-bottom:24px; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ text-align:left; font-size:12px; color:var(--muted); text-transform:uppercase; padding:16px; border-bottom:1px solid var(--line); }}
td {{ padding:16px; border-bottom:1px solid #edf2f8; vertical-align:middle; }}
td span, small {{ display:block; color:var(--muted); font-size:12px; margin-top:4px; }}
.rank {{ font-weight:800; color:var(--blue); white-space:nowrap; }}
.badge {{ display:inline-flex; align-items:center; padding:7px 10px; border-radius:999px; font-weight:800; font-size:12px; background:#edf5ff; color:var(--blue); }}
.badge.RECOMMEND {{ background:#e8fff7; color:var(--green); }}
.badge.WATCH {{ background:#fff7e6; color:#b7791f; }}
.badge.WAIT {{ background:#eef2f7; color:#64748b; }}
.bar {{ min-width:120px; }}
.bar-top {{ display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-bottom:6px; }}
.track {{ height:9px; background:#edf2f8; border-radius:999px; overflow:hidden; }}
.fill {{ height:100%; background:linear-gradient(90deg,#7cc4ff,#2f80ed); border-radius:999px; }}
.pos {{ color:var(--green); font-weight:800; }}
.neg {{ color:var(--red); font-weight:800; }}
.cards {{ display:grid; grid-template-columns:1fr; gap:22px; }}
.card {{ padding:22px; }}
.card-head {{ display:flex; justify-content:space-between; align-items:center; gap:20px; margin-bottom:18px; }}
.eyebrow {{ color:var(--blue); font-size:12px; font-weight:800; text-transform:uppercase; }}
h2 {{ margin:4px 0 0; font-size:24px; }}
.grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:14px; margin-bottom:16px; }}
.metric {{ background:#f8fbff; border:1px solid #e8eef7; border-radius:18px; padding:14px; }}
.metric label {{ display:block; color:var(--muted); font-size:12px; margin-bottom:8px; }}
.metric strong {{ font-size:22px; }}
.replay {{ padding:14px; background:#f8fbff; border-radius:16px; margin:10px 0 14px; color:var(--muted); }}
.replay b {{ color:var(--ink); }}
.mini-table {{ overflow:auto; border:1px solid #e8eef7; border-radius:18px; background:#fff; margin-bottom:14px; }}
.mini-table th, .mini-table td {{ padding:12px; }}
.replay-detail {{ margin:12px 0; border:1px solid #e8eef7; background:#fff; border-radius:18px; overflow:hidden; }}
.replay-detail summary {{ cursor:pointer; padding:14px 16px; font-weight:800; color:#1f3b64; background:#f8fbff; }}
.chart-box {{ background:#fff; border-top:1px solid #e8eef7; padding:12px; overflow:auto; }}
.chart-box img {{ width:100%; min-width:1050px; display:block; border-radius:14px; }}
.chart-missing {{ padding:24px; border:1px dashed #ccd7e5; border-radius:18px; color:var(--muted); margin:14px 0; }}
ul {{ margin:0; padding-left:20px; color:#344054; }}
li {{ margin:6px 0; }}
@media (max-width:1100px) {{ .grid {{ grid-template-columns:repeat(2,1fr); }} .hero {{ display:block; }} .panel {{ overflow-x:auto; }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div>
      <h1>ADE Recommendation Report</h1>
      <div class="sub">각 추천종목마다 Replay DB 전체에서 찾은 Top5 유사 이벤트를 보여줍니다. 좌측은 현재 6개월 주봉, 우측은 Replay 이후 6개월 흐름입니다.</div>
    </div>
    <div class="pill">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  </div>

  <div class="panel">
    <table>
      <thead>
        <tr><th>Rank</th><th>Stock</th><th>Decision</th><th>Top1 Final</th><th>Top1 Weekly</th><th>Top1 STO</th><th>Top1 Max return</th><th>Top1 MDD</th><th>Recent event</th></tr>
      </thead>
      <tbody>{''.join(table_rows) or '<tr><td colspan="9">No recommendations</td></tr>'}</tbody>
    </table>
  </div>

  <div class="cards">{''.join(cards)}</div>
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


def _badge(text: str) -> str:
    safe = html.escape(text)
    return f'<span class="badge {safe}">{safe}</span>'


def _bar(value: float) -> str:
    width = max(0.0, min(100.0, value))
    return f'<div class="bar"><div class="bar-top"><span>score</span><b>{value:.2f}%</b></div><div class="track"><div class="fill" style="width:{width:.2f}%"></div></div></div>'
