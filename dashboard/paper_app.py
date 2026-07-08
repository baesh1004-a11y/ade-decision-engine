from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dashboard.data import PaperDashboardData
from recommendation.event_recommender import RecentMoneyEventRecommender
from report.chart_viewer import RecommendationChartViewer


def _money(value: float) -> str:
    return f"{value:,.0f}원"


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_num(value: object, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.00"


def _run_streamlit(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE AI Trading Cockpit", page_icon="◈", layout="wide")
    _inject_style(st)

    data = PaperDashboardData(db_path)
    try:
        metrics = data.metrics()
        positions = data.load_positions()
        orders = data.load_orders()
        curve = data.equity_curve()
    finally:
        data.close()

    st.markdown(
        f"""
        <div class="top-hero">
          <div>
            <div class="eyebrow">ADE v5 · PAPER TRADING COCKPIT</div>
            <h1>AI Decision Engine</h1>
            <p>추천종목 전부 모의매수 · 종목당 100만원 · Replay 근거 추적 · 매도 로직 미적용</p>
          </div>
          <div class="hero-status">
            <span class="pulse"></span>
            PAPER MODE
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    _metric(k1, "투자원금", _money(metrics.invested_amount), "Capital deployed")
    _metric(k2, "평가금액", _money(metrics.evaluation_amount), "Current valuation")
    _metric(k3, "평가손익", _money(metrics.pnl), "Unrealized P/L", metrics.pnl)
    _metric(k4, "수익률", _pct(metrics.pnl_rate), "Portfolio return", metrics.pnl_rate)
    _metric(k5, "보유종목", f"{len(positions)}개", "Open positions")
    _metric(k6, "승 / 패", f"{metrics.winners} / {metrics.losers}", "Positive / Negative")

    st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["◈ Cockpit", "▣ Positions", "⌁ Replay Basis", "◎ Orders", "🔎 추천 검증 1·2·3"])

    with tab1:
        left, center, right = st.columns([1.05, 1.55, 1.0])
        with left:
            st.markdown("<div class='panel-title'>Portfolio Radar</div>", unsafe_allow_html=True)
            _portfolio_radar(st, positions)
            st.markdown("<div class='panel-title'>Top Movers</div>", unsafe_allow_html=True)
            _top_movers(st, positions)
        with center:
            st.markdown("<div class='panel-title'>Capital Timeline</div>", unsafe_allow_html=True)
            _capital_timeline(st, curve)
            st.markdown("<div class='panel-title'>Position Heatmap</div>", unsafe_allow_html=True)
            _position_heatmap(st, positions)
        with right:
            st.markdown("<div class='panel-title'>System Status</div>", unsafe_allow_html=True)
            _system_status(st, orders, positions)
            st.markdown("<div class='panel-title'>Latest Orders</div>", unsafe_allow_html=True)
            _latest_orders_cards(st, orders)

    with tab2:
        st.markdown("<div class='panel-title'>Open Positions</div>", unsafe_allow_html=True)
        _positions_table(st, positions)

    with tab3:
        st.markdown("<div class='panel-title'>Replay Basis Monitor</div>", unsafe_allow_html=True)
        _replay_basis(st, positions)

    with tab4:
        st.markdown("<div class='panel-title'>Order History</div>", unsafe_allow_html=True)
        _orders_table(st, orders)

    with tab5:
        _recommendation_audit(st, db_path)

    st.caption("ADE Paper Dashboard v1. 매도 로직은 아직 적용하지 않았습니다. 현재 화면은 모의매수 주문과 보유 평가 확인용입니다.")


def _metric(col: object, label: str, value: str, sub: str, signed_value: float | None = None) -> None:
    cls = ""
    if signed_value is not None:
        cls = "pos" if signed_value >= 0 else "neg"
    col.markdown(
        f"""
        <div class="metric-card">
          <label>{label}</label>
          <strong class="{cls}">{value}</strong>
          <small>{sub}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _portfolio_radar(st: object, positions: pd.DataFrame) -> None:
    if positions.empty:
        st.markdown("<div class='empty-box'>보유 포지션이 없습니다.</div>", unsafe_allow_html=True)
        return
    total = max(float(positions["evaluation_amount"].sum()), 1.0)
    for _, row in positions.sort_values("evaluation_amount", ascending=False).head(8).iterrows():
        weight = float(row["evaluation_amount"]) / total * 100
        pnl = float(row["pnl_rate"])
        cls = "pos" if pnl >= 0 else "neg"
        st.markdown(
            f"""
            <div class="mini-row">
              <div><b>{row.get('name') or row.get('ticker')}</b><span>{str(row.get('market')).upper()}:{row.get('ticker')}</span></div>
              <div class="right {cls}">{_pct(pnl)}<span>{weight:.1f}%</span></div>
            </div>
            <div class="track"><div class="fill" style="width:{min(max(weight,0),100):.1f}%"></div></div>
            """,
            unsafe_allow_html=True,
        )


def _top_movers(st: object, positions: pd.DataFrame) -> None:
    if positions.empty:
        st.markdown("<div class='empty-box'>움직임 없음</div>", unsafe_allow_html=True)
        return
    movers = positions.sort_values("pnl_rate", ascending=False).head(5)
    for _, row in movers.iterrows():
        pnl = float(row["pnl_rate"])
        cls = "pos" if pnl >= 0 else "neg"
        st.markdown(
            f"<div class='ticker-card'><b>{row.get('name') or row.get('ticker')}</b><strong class='{cls}'>{_pct(pnl)}</strong><span>Replay {row.get('top1_event_id') or '-'}</span></div>",
            unsafe_allow_html=True,
        )


def _capital_timeline(st: object, curve: pd.DataFrame) -> None:
    if curve.empty:
        st.markdown("<div class='chart-empty'>주문 기록이 없습니다.</div>", unsafe_allow_html=True)
        return
    chart = curve.copy()
    chart["date"] = pd.to_datetime(chart["date"])
    st.line_chart(chart.set_index("date")["invested"], height=310)


def _position_heatmap(st: object, positions: pd.DataFrame) -> None:
    if positions.empty:
        st.markdown("<div class='empty-box'>포지션 히트맵 없음</div>", unsafe_allow_html=True)
        return
    html = ["<div class='heat-grid'>"]
    for _, row in positions.sort_values("pnl_rate", ascending=False).iterrows():
        pnl = float(row["pnl_rate"])
        cls = "heat-pos" if pnl >= 0 else "heat-neg"
        html.append(
            f"<div class='heat-cell {cls}'><b>{row.get('name') or row.get('ticker')}</b><span>{_pct(pnl)}</span></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _system_status(st: object, orders: pd.DataFrame, positions: pd.DataFrame) -> None:
    accepted = int((orders["accepted"] == 1).sum()) if not orders.empty and "accepted" in orders else 0
    rejected = int((orders["accepted"] == 0).sum()) if not orders.empty and "accepted" in orders else 0
    last_order = "-" if orders.empty else str(orders.iloc[0].get("created_at", "-"))
    st.markdown(
        f"""
        <div class="status-card"><label>Broker</label><strong>KIS Paper</strong><span>Mock trading mode</span></div>
        <div class="status-card"><label>Orders</label><strong>{accepted} / {rejected}</strong><span>accepted / rejected</span></div>
        <div class="status-card"><label>Positions</label><strong>{len(positions)}</strong><span>open symbols</span></div>
        <div class="status-card"><label>Last order</label><strong>{last_order[:16]}</strong><span>local DB timestamp</span></div>
        """,
        unsafe_allow_html=True,
    )


def _latest_orders_cards(st: object, orders: pd.DataFrame) -> None:
    if orders.empty:
        st.markdown("<div class='empty-box'>최근 주문 없음</div>", unsafe_allow_html=True)
        return
    for _, row in orders.head(5).iterrows():
        accepted = int(row.get("accepted", 0)) == 1
        cls = "pos" if accepted else "neg"
        st.markdown(
            f"""
            <div class="order-card">
              <div><b>{row.get('name') or row.get('ticker')}</b><span>{row.get('created_at')}</span></div>
              <strong class="{cls}">{'ACCEPTED' if accepted else 'REJECTED'}</strong>
              <small>{row.get('side')} · qty {row.get('quantity')} · {_money(float(row.get('estimated_amount') or 0))}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _positions_table(st: object, positions: pd.DataFrame) -> None:
    if positions.empty:
        st.info("아직 저장된 모의매수 포지션이 없습니다. `python run_paper_trading.py --execute` 실행 후 확인하세요.")
        return
    view = positions.copy()
    for col in ["invested_amount", "evaluation_amount", "pnl", "current_price", "avg_reference_price", "pnl_rate"]:
        view[col] = view[col].map(lambda x: round(float(x), 2))
    view = view[[
        "market", "ticker", "name", "quantity", "avg_reference_price", "current_price",
        "invested_amount", "evaluation_amount", "pnl", "pnl_rate",
        "final_similarity", "weekly_similarity", "sto_similarity", "top1_event_id",
    ]]
    st.dataframe(view, use_container_width=True, hide_index=True)


def _replay_basis(st: object, positions: pd.DataFrame) -> None:
    if positions.empty:
        st.info("Replay 근거를 표시할 보유 포지션이 없습니다.")
        return
    selected = st.selectbox(
        "Replay 확인 종목",
        positions.index,
        format_func=lambda idx: f"{positions.loc[idx, 'name'] or positions.loc[idx, 'ticker']} · {positions.loc[idx, 'ticker']}",
    )
    row = positions.loc[selected]
    pnl = float(row.get("pnl_rate", 0))
    cls = "pos" if pnl >= 0 else "neg"
    st.markdown(
        f"""
        <div class="replay-card">
          <div>
            <div class="eyebrow">CURRENT POSITION</div>
            <h2>{row.get('name') or row.get('ticker')} <small>{str(row.get('market')).upper()}:{row.get('ticker')}</small></h2>
          </div>
          <div class="replay-score {cls}">{_pct(pnl)}</div>
        </div>
        <div class="replay-grid">
          <div class="status-card"><label>Top1 Replay</label><strong>{row.get('top1_event_id') or '-'}</strong><span>matched historical pattern</span></div>
          <div class="status-card"><label>Final similarity</label><strong>{_fmt_num(row.get('final_similarity'))}%</strong><span>weekly + STO</span></div>
          <div class="status-card"><label>Weekly</label><strong>{_fmt_num(row.get('weekly_similarity'))}%</strong><span>shape similarity</span></div>
          <div class="status-card"><label>STO</label><strong>{_fmt_num(row.get('sto_similarity'))}%</strong><span>3-layer structure</span></div>
        </div>
        <div class="chart-empty">추천 검증 1·2·3 탭에서 현재 차트 vs Replay 차트를 확인할 수 있습니다.</div>
        """,
        unsafe_allow_html=True,
    )


def _orders_table(st: object, orders: pd.DataFrame) -> None:
    if orders.empty:
        st.info("주문 기록이 없습니다.")
        return
    recent = orders.head(200).copy()
    show_cols = [
        "created_at", "market", "ticker", "name", "side", "quantity", "reference_price",
        "estimated_amount", "accepted", "order_id", "message", "final_similarity", "top1_event_id",
    ]
    st.dataframe(recent[[c for c in show_cols if c in recent.columns]], use_container_width=True, hide_index=True)


def _recommendation_audit(st: object, db_path: str) -> None:
    st.markdown("<div class='panel-title'>추천 검증 1·2·3</div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="chart-empty">
        Step 1: 왜 추천됐는지 확인 → Step 2: Top5 Replay가 정말 좋은지 확인 → Step 3: 현재 차트와 Replay 차트를 눈으로 검증합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    top_n = c1.number_input("추천 수", min_value=1, max_value=30, value=10, step=1)
    weekly_pool = c2.number_input("Weekly Pool", min_value=20, max_value=300, value=100, step=10)
    min_weekly = c3.number_input("주봉 기준", min_value=70.0, max_value=99.0, value=85.0, step=1.0)
    min_sto = c4.number_input("STO 기준", min_value=70.0, max_value=99.0, value=85.0, step=1.0)

    if st.button("오늘 추천 검증 실행", type="primary"):
        st.session_state["audit_recommendations"] = _load_recommendations(
            db_path=db_path,
            top_n=int(top_n),
            weekly_pool_n=int(weekly_pool),
            min_weekly=float(min_weekly),
            min_sto=float(min_sto),
        )

    recommendations = st.session_state.get("audit_recommendations", [])
    if not recommendations:
        st.info("버튼을 누르면 현재 데이터 기준 추천종목을 계산하고, Step 1·2·3 검증 화면을 보여줍니다.")
        return

    rec_df = pd.DataFrame([
        {
            "rank": i,
            "market": r.market.upper(),
            "ticker": r.ticker,
            "name": r.name,
            "decision": r.decision,
            "final": r.final_similarity,
            "weekly": r.weekly_similarity,
            "sto": r.sto_similarity,
            "top1_replay": r.matched_event_id,
            "max_return": r.matched_max_return,
            "mdd": r.matched_max_drawdown,
        }
        for i, r in enumerate(recommendations, start=1)
    ])
    st.dataframe(rec_df, use_container_width=True, hide_index=True)

    selected_rank = st.selectbox(
        "검증할 추천종목",
        list(range(len(recommendations))),
        format_func=lambda i: f"#{i+1} {recommendations[i].name or recommendations[i].ticker} · {recommendations[i].ticker}",
    )
    item = recommendations[selected_rank]

    st.markdown("<div class='audit-steps'>", unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.markdown(
        f"""
        <div class="step-card">
          <div class="step-no">STEP 1</div>
          <h3>왜 추천됐나?</h3>
          <b>{item.name or item.ticker}</b><span>{item.market.upper()}:{item.ticker}</span>
          <p>Final {_fmt_num(item.final_similarity)}% · Weekly {_fmt_num(item.weekly_similarity)}% · STO {_fmt_num(item.sto_similarity)}%</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    best = item.replay_matches[0] if item.replay_matches else None
    b.markdown(
        f"""
        <div class="step-card">
          <div class="step-no">STEP 2</div>
          <h3>Replay가 최적인가?</h3>
          <b>{best.name if best else '-'}</b><span>{best.event_id if best else '-'}</span>
          <p>Top5 Replay 전체를 아래 표에서 비교합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c.markdown(
        f"""
        <div class="step-card">
          <div class="step-no">STEP 3</div>
          <h3>눈으로 검증</h3>
          <b>SAME AS NOW</b><span>슬라이딩 매칭 위치</span>
          <p>현재 차트와 Replay 이후 흐름을 나란히 확인합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-title'>Step 1 · 추천 사유</div>", unsafe_allow_html=True)
    for reason in item.reasons:
        st.markdown(f"- {reason}")

    st.markdown("<div class='panel-title'>Step 2 · Top5 Replay 비교</div>", unsafe_allow_html=True)
    match_df = pd.DataFrame([
        {
            "rank": f"Top {i}",
            "event_id": m.event_id,
            "name": m.name,
            "ticker": m.ticker,
            "final": m.final_similarity,
            "weekly": m.weekly_similarity,
            "sto": m.sto_similarity,
            "max_return": m.max_return,
            "mdd": m.max_drawdown,
            "same_as_now_week": m.equivalent_week_index,
            "future_weeks": m.future_weeks_available,
        }
        for i, m in enumerate(item.replay_matches, start=1)
    ])
    st.dataframe(match_df, use_container_width=True, hide_index=True)

    if item.replay_matches:
        match_idx = st.selectbox(
            "차트로 볼 Replay",
            list(range(len(item.replay_matches))),
            format_func=lambda i: f"Top {i+1} · {item.replay_matches[i].name or item.replay_matches[i].ticker} · {item.replay_matches[i].event_id}",
        )
        st.markdown("<div class='panel-title'>Step 3 · 현재 vs Replay 비교차트</div>", unsafe_allow_html=True)
        if st.button("비교차트 생성/새로고침"):
            chart_viewer = RecommendationChartViewer(db_path=db_path, output_dir="output/dashboard_charts")
            try:
                chart_path = chart_viewer.render_replay_match(item, item.replay_matches[match_idx], selected_rank + 1, match_idx + 1)
            finally:
                chart_viewer.close()
            st.session_state["audit_chart_path"] = chart_path
        chart_path = st.session_state.get("audit_chart_path")
        if chart_path and Path(chart_path).exists():
            st.image(chart_path, use_container_width=True)
        else:
            st.info("비교차트 생성/새로고침 버튼을 누르면 HTS 스타일 차트가 표시됩니다.")


def _load_recommendations(db_path: str, top_n: int, weekly_pool_n: int, min_weekly: float, min_sto: float) -> list[object]:
    engine = RecentMoneyEventRecommender(db_path=db_path)
    try:
        return engine.recommend(
            candidate_years=2,
            lookback_months=6,
            top_n=top_n,
            weekly_pool_n=weekly_pool_n,
            min_weekly_similarity=min_weekly,
            min_sto_similarity=min_sto,
            replay_top_n=5,
        )
    finally:
        engine.close()


def _inject_style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp { background: radial-gradient(circle at 15% 10%, #e7f5ff 0, transparent 32%), linear-gradient(135deg, #f5f9ff 0%, #eef6ff 44%, #f9fbff 100%); }
        .block-container { padding-top: 1.6rem; max-width: 1580px; }
        [data-testid="stHeader"] { background: rgba(255,255,255,0); }
        .top-hero { display:flex; justify-content:space-between; align-items:center; padding:28px 32px; border:1px solid #dbe5f2; border-radius:32px; background:rgba(255,255,255,.78); box-shadow:0 24px 70px rgba(45,91,154,.13); backdrop-filter:blur(18px); margin-bottom:18px; }
        .eyebrow { color:#2f80ed; font-size:12px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
        .top-hero h1 { margin:4px 0 0; font-size:44px; letter-spacing:-.055em; color:#162033; }
        .top-hero p { margin:8px 0 0; color:#6b778c; font-size:15px; }
        .hero-status { padding:12px 16px; border:1px solid #dbe5f2; border-radius:999px; background:#fff; color:#1f3b64; font-weight:800; box-shadow:0 10px 30px rgba(45,91,154,.08); }
        .pulse { display:inline-block; width:9px; height:9px; border-radius:50%; background:#10a37f; margin-right:8px; box-shadow:0 0 0 7px rgba(16,163,127,.12); }
        .metric-card, .status-card, .ticker-card, .order-card, .replay-card, .step-card { border:1px solid #dbe5f2; border-radius:24px; background:rgba(255,255,255,.82); box-shadow:0 16px 45px rgba(45,91,154,.09); backdrop-filter:blur(14px); }
        .metric-card { padding:18px; min-height:118px; }
        .metric-card label, .status-card label { color:#6b778c; font-size:12px; display:block; }
        .metric-card strong { display:block; margin-top:9px; font-size:25px; color:#162033; letter-spacing:-.03em; }
        .metric-card small, .status-card span, .mini-row span, .ticker-card span, .order-card span, .order-card small, .step-card span { display:block; margin-top:5px; color:#7b8798; font-size:12px; }
        .pos { color:#10a37f !important; } .neg { color:#d64545 !important; }
        .section-gap { height:14px; }
        .panel-title { font-size:20px; font-weight:850; letter-spacing:-.035em; color:#162033; margin:8px 0 12px; }
        .empty-box, .chart-empty { padding:22px; border:1px dashed #cbd8e7; border-radius:22px; background:rgba(255,255,255,.55); color:#6b778c; }
        .mini-row { display:flex; justify-content:space-between; align-items:center; margin:12px 0 6px; padding:12px 14px; border-radius:18px; background:rgba(255,255,255,.62); border:1px solid #e7eef8; }
        .mini-row b { color:#162033; } .mini-row .right { text-align:right; font-weight:800; }
        .track { height:7px; background:#eaf1f9; border-radius:999px; overflow:hidden; margin-bottom:8px; }
        .fill { height:100%; background:linear-gradient(90deg,#7cc4ff,#2f80ed); border-radius:999px; }
        .ticker-card { padding:14px 15px; margin-bottom:10px; }
        .ticker-card b { color:#162033; } .ticker-card strong { float:right; }
        .status-card { padding:16px; margin-bottom:10px; }
        .status-card strong { display:block; margin-top:6px; font-size:18px; color:#162033; overflow-wrap:anywhere; }
        .order-card { padding:14px; margin-bottom:10px; }
        .order-card { display:block; } .order-card strong { float:right; font-size:12px; }
        .heat-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; }
        .heat-cell { padding:14px; min-height:82px; border-radius:20px; border:1px solid rgba(255,255,255,.7); box-shadow:0 12px 30px rgba(45,91,154,.07); }
        .heat-cell b { display:block; font-size:14px; color:#162033; } .heat-cell span { display:block; margin-top:10px; font-size:20px; font-weight:900; }
        .heat-pos { background:linear-gradient(135deg,#ebfff7,#ffffff); } .heat-pos span { color:#10a37f; }
        .heat-neg { background:linear-gradient(135deg,#fff0f0,#ffffff); } .heat-neg span { color:#d64545; }
        .replay-card { display:flex; justify-content:space-between; align-items:center; padding:22px; margin-bottom:14px; }
        .replay-card h2 { margin:4px 0 0; font-size:30px; letter-spacing:-.04em; }
        .replay-card small { color:#6b778c; font-size:14px; }
        .replay-score { font-size:34px; font-weight:950; }
        .replay-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:14px; }
        .audit-steps { margin:14px 0; }
        .step-card { padding:18px; min-height:170px; }
        .step-card h3 { margin:6px 0 10px; font-size:22px; letter-spacing:-.04em; color:#162033; }
        .step-card b { font-size:18px; color:#162033; }
        .step-card p { color:#536176; font-size:13px; margin-top:12px; }
        .step-no { display:inline-flex; padding:6px 10px; border-radius:999px; background:#edf5ff; color:#2f80ed; font-size:12px; font-weight:900; }
        @media(max-width:1100px){ .top-hero{display:block;} .heat-grid{grid-template-columns:repeat(2,1fr);} .replay-grid{grid-template-columns:repeat(2,1fr);} }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Paper Trading Dashboard")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    _run_streamlit(args.db)


if __name__ == "__main__":
    main()
