from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from pattern.replay_probability import ReplayProbabilityEngine, ReplayProbabilityResult
from recommendation.models import RecommendationScore


class RecommendationReportWriter:
    """Generate an HTML report with ADE 6-step replay probability evidence."""

    def __init__(self, output_dir: str | Path = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.replay_engine = ReplayProbabilityEngine(window=120, forward_20d=20, forward_60d=60)

    def write(self, score: RecommendationScore, market_data: pd.DataFrame) -> Path:
        ticker = score.ticker.replace("/", "_")
        path = self.output_dir / f"{datetime.now().date()}_{score.market}_{ticker}.html"
        path.write_text(self._html(score, market_data), encoding="utf-8")
        return path

    def _html(self, score: RecommendationScore, market_data: pd.DataFrame) -> str:
        data = market_data.copy().reset_index(drop=True)
        chart_data = data.tail(120).reset_index(drop=True)
        replay = self.replay_engine.evaluate(data, environment_score=70, top_n=5)
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
.step{{display:inline-block;background:#eef6ff;border:1px solid #cfe6ff;border-radius:12px;padding:10px 12px;margin:6px;font-weight:700}}
svg{{width:100%;height:auto}} li{{margin:7px 0}}
.small{{color:#64748b;font-size:13px}}
.good{{color:#15803d}} .warn{{color:#b45309}} .bad{{color:#b91c1c}}
</style></head><body>
<div class='card'>
<span class='badge'>ADE 6-Step Replay Probability Report</span>
<h1>{score.ticker} | {score.name or ''}</h1>
<p>{score.market.upper()} · {score.sector or '-'} · {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div class='grid'>
<div><small>Recommendation score</small><div class='metric'>{score.final_score}/100</div></div>
<div><small>Replay probability</small><div class='metric'>{replay.replay_probability}% ({replay.grade})</div></div>
<div><small>Replay action</small><div class='metric'>{replay.action}</div></div>
<div><small>Environment sync</small><div class='metric'>{replay.environment_score}/100</div></div>
</div></div>
<div class='card'><h2>1. 매매 후보 종목 탐색</h2>{self._candidate_box(replay)}</div>
<div class='card'><h2>2. 현재 상태 분석</h2>{self._state_chart(replay)}</div>
<div class='card'><h2>3. 과거 유사 종목·시점 탐색</h2>{self._historical_cases_chart(replay)}</div>
<div class='card'><h2>4. 과거 이후 흐름 확인</h2>{self._replay_outcome_chart(replay)}</div>
<div class='card'><h2>5. 환경 동기화 비교</h2>{self._environment_chart(replay)}</div>
<div class='card'><h2>6. 진입 가치 최종 판단</h2>{self._final_decision(replay)}</div>
<div class='card'><h2>Price trend evidence</h2>{self._price_chart(chart_data)}</div>
<div class='card'><h2>Recommendation reasons</h2><ul>{reasons}</ul></div>
<div class='card'><h2>Risk flags</h2><ul>{risks}</ul></div>
</body></html>"""

    def _candidate_box(self, replay: ReplayProbabilityResult) -> str:
        labels = replay.current_state.labels or ["아직 강한 후보 조건은 부족"]
        items = "".join(f"<li>{label}</li>" for label in labels)
        return f"""
<p class='small'>거래대금 10배, 장대양봉, 장기 바닥권, 돌파 여부를 후보 조건으로 판단합니다.</p>
<ul>{items}</ul>
<div class='metric'>{replay.current_state.state_score}/100</div>
"""

    def _state_chart(self, replay: ReplayProbabilityResult) -> str:
        state = replay.current_state
        bars = [
            ("STO 3층 구조", state.sto_stack_score),
            ("이평 배열", state.ma_alignment_score),
            ("주봉 위치", state.weekly_position_score),
            ("거래대금 흐름", state.volume_surge_score),
            ("장기 바닥권", state.long_base_score),
            ("돌파 상태", state.breakout_score),
        ]
        return self._bar_svg(bars, fill="#2563eb")

    def _historical_cases_chart(self, replay: ReplayProbabilityResult) -> str:
        if not replay.cases:
            return "<p>유사 상태 사례가 부족합니다. 더 긴 기간의 데이터를 수집해야 합니다.</p>"
        bars = [(f"{c.start_date}~{c.end_date}", c.similarity) for c in replay.cases]
        return self._bar_svg(bars, fill="#10b981", suffix="%")

    def _replay_outcome_chart(self, replay: ReplayProbabilityResult) -> str:
        if not replay.cases:
            return "<p>과거 이후 흐름 통계가 없습니다.</p>"
        rows = []
        y = 40
        for case in replay.cases:
            ret = case.forward_return_20d or 0.0
            width = int(min(420, max(0, 210 + ret * 8)))
            color = "#16a34a" if ret >= 0 else "#dc2626"
            label = f"{case.end_date} / 20D {ret:+.2f}% / MDD {case.drawdown_20d if case.drawdown_20d is not None else 'N/A'}%"
            rows.append(f"<text x='10' y='{y+15}' font-size='13'>{label}</text>")
            rows.append(f"<rect x='300' y='{y}' width='{width}' height='20' rx='5' fill='{color}'/>")
            y += 38
        return f"<svg viewBox='0 0 780 {y+20}'>{''.join(rows)}</svg>"

    def _environment_chart(self, replay: ReplayProbabilityResult) -> str:
        bars = [
            ("금리/DXY/유동성", replay.environment_score),
            ("과거 상태 유사도", round(sum(c.similarity for c in replay.cases) / len(replay.cases), 1) if replay.cases else 0),
            ("20D 승률", replay.win_rate_20d or 0),
            ("현재 상태 점수", replay.current_state.state_score),
        ]
        return self._bar_svg(bars, fill="#7c3aed", suffix="%")

    def _final_decision(self, replay: ReplayProbabilityResult) -> str:
        avg = "N/A" if replay.avg_return_20d is None else f"{replay.avg_return_20d:+.2f}%"
        win = "N/A" if replay.win_rate_20d is None else f"{replay.win_rate_20d:.1f}%"
        mdd = "N/A" if replay.avg_drawdown_20d is None else f"{replay.avg_drawdown_20d:.2f}%"
        return f"""
<div class='grid'>
<div><small>등급</small><div class='metric'>{replay.grade}</div></div>
<div><small>판단</small><div class='metric'>{replay.action}</div></div>
<div><small>재현 확률</small><div class='metric'>{replay.replay_probability}%</div></div>
<div><small>과거 유사 사례 수</small><div class='metric'>{len(replay.cases)}</div></div>
</div>
<p><b>과거 유사 흐름 20D 평균수익:</b> {avg} · <b>승률:</b> {win} · <b>평균 MDD:</b> {mdd}</p>
<p class='small'>A: 진입 유리 / B: 대기 또는 분할 / C: 관찰 / D: 제외</p>
"""

    def _bar_svg(self, bars: list[tuple[str, float]], fill: str, suffix: str = "") -> str:
        rows = []
        y = 40
        for label, value in bars:
            width = int(420 * max(0, min(100, value)) / 100)
            rows.append(f"<text x='10' y='{y+15}' font-size='13'>{label}</text>")
            rows.append(f"<rect x='180' y='{y}' width='{width}' height='20' rx='5' fill='{fill}'/>")
            rows.append(f"<text x='{190+width}' y='{y+15}' font-size='13'>{value}{suffix}</text>")
            y += 38
        return f"<svg viewBox='0 0 760 {y+20}'>{''.join(rows)}</svg>"

    def _price_chart(self, df: pd.DataFrame) -> str:
        if df.empty or 'Close' not in df.columns:
            return "<p>No price data</p>"
        close = pd.to_numeric(df['Close'], errors='coerce').dropna().tail(90).reset_index(drop=True)
        if close.empty:
            return "<p>No price data</p>"
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        min_v = float(min(close.min(), ma20.min(skipna=True), ma60.min(skipna=True)))
        max_v = float(max(close.max(), ma20.max(skipna=True), ma60.max(skipna=True)))
        spread = max(max_v - min_v, 1.0)

        def point(i: int, value: float) -> str:
            x = 40 + i * (520 / max(len(close) - 1, 1))
            y = 260 - ((value - min_v) / spread * 210)
            return f"{x:.1f},{y:.1f}"

        close_points = " ".join(point(i, float(v)) for i, v in enumerate(close))
        ma20_points = " ".join(point(i, float(v)) for i, v in enumerate(ma20) if not pd.isna(v))
        ma60_points = " ".join(point(i, float(v)) for i, v in enumerate(ma60) if not pd.isna(v))
        return f"""<svg viewBox='0 0 620 310'>
<line x1='40' y1='260' x2='580' y2='260' stroke='#d0d7e2'/><line x1='40' y1='40' x2='40' y2='260' stroke='#d0d7e2'/>
<polyline points='{close_points}' fill='none' stroke='#2563eb' stroke-width='3'/>
<polyline points='{ma20_points}' fill='none' stroke='#f97316' stroke-width='3'/>
<polyline points='{ma60_points}' fill='none' stroke='#16a34a' stroke-width='3'/>
<text x='45' y='25' font-size='13'>Close (blue) vs MA20 (orange) vs MA60 (green)</text>
<text x='45' y='292' font-size='12'>Latest close: {float(close.iloc[-1]):,.2f}</text>
</svg>"""
