from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dashboard.system_status import inspect_market_db


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Command Center", page_icon="📊", layout="wide")
    st.markdown(
        """
        <style>
        :root{--ink:#14263a;--muted:#708397;--line:rgba(76,124,168,.18);--blue:#2f80ed;--glass:rgba(255,255,255,.86)}
        .stApp{background:radial-gradient(circle at 10% 0%,rgba(125,190,255,.20),transparent 28%),linear-gradient(135deg,#f8fbfe,#edf4fa 55%,#f9fcff);color:var(--ink)}
        .block-container{max-width:1580px;padding-top:1rem;padding-bottom:3rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(248,252,255,.98),rgba(232,242,251,.98));border-right:1px solid var(--line)}
        [data-testid="stSidebar"] a{border-radius:11px!important;margin:2px 7px!important;font-weight:680!important;color:#31485d!important}
        [data-testid="stSidebar"] a[aria-current="page"]{background:linear-gradient(135deg,#dcecff,#eef6ff)!important;color:#1768bd!important}
        .hero{display:flex;justify-content:space-between;align-items:flex-end;padding:30px 34px;border-radius:28px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(239,247,255,.88));border:1px solid var(--line);box-shadow:0 22px 60px rgba(42,88,130,.12);margin-bottom:18px}
        .hero h1{margin:4px 0 7px;font-size:38px;letter-spacing:-.045em}.hero p{margin:0;color:var(--muted)}
        .eyebrow{font-size:12px;letter-spacing:.17em;font-weight:850;color:#2f78ba}.mode{font-size:13px;font-weight:850;color:#226bad;background:#e9f3ff;border:1px solid rgba(47,128,237,.16);padding:9px 13px;border-radius:999px}
        .section{display:flex;justify-content:space-between;align-items:center;margin:24px 0 10px}.section h2{font-size:21px;margin:0;letter-spacing:-.03em}.section span{color:var(--muted);font-size:13px}
        .status-card{padding:19px 20px;border-radius:19px;background:var(--glass);border:1px solid var(--line);box-shadow:0 9px 26px rgba(56,100,139,.07);min-height:132px}
        .status-card h3{margin:0 0 7px;font-size:17px}.status-card p{margin:4px 0;color:var(--muted);font-size:13px}.ok{color:#16724d;font-weight:850}.warn{color:#b36b16;font-weight:850}
        div[data-testid="stMetric"]{background:rgba(255,255,255,.82);border:1px solid var(--line);padding:16px 18px;border-radius:18px;box-shadow:0 9px 26px rgba(56,100,139,.07)}
        div[data-testid="stMetricLabel"]{font-weight:720;color:#708397}div[data-testid="stMetricValue"]{font-size:1.85rem;font-weight:880;letter-spacing:-.04em;color:#1a3249}
        div[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 9px 26px rgba(56,100,139,.07)}
        @media(max-width:768px){.block-container{padding:.7rem}.hero{display:block;padding:22px}.mode{display:inline-block;margin-top:14px}.hero h1{font-size:30px}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    mode = os.getenv("KIS_ENV", "paper").upper()
    st.markdown(
        f"""
        <div class="hero">
          <div><div class="eyebrow">ADE · INVESTMENT OPERATIONS TERMINAL</div><h1>Command Center</h1><p>추천, 판단, 주문, 데이터 상태를 시장별로 한 화면에서 확인합니다.</p></div>
          <div class="mode">KIS {mode}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kr = inspect_market_db("datahub/market.db", "kr")
    us = inspect_market_db("datahub/us_market.db", "us")
    kr_rec, us_rec, pending_orders = _summary_counts()

    a, b, c, d = st.columns(4)
    a.metric("KR 최근 추천", kr_rec)
    b.metric("US 최근 추천", us_rec)
    c.metric("승인 대기 주문", pending_orders)
    d.metric("운영 준비 시장", f"{int(kr.ready) + int(us.ready)} / 2")

    st.markdown('<div class="section"><h2>Market Readiness</h2><span>가격 · Universe · Replay · Vector</span></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for col, title, status, price_cmd, replay_cmd in [
        (c1, "🇰🇷 KOREA", kr, "python run_build_replay_db.py", "python run_build_replay_db.py"),
        (c2, "🇺🇸 USA", us, "python run_build_us_market_db.py", "python run_build_us_replay_db.py"),
    ]:
        with col:
            state_class = "ok" if status.ready else "warn"
            state_text = "READY" if status.ready else "ACTION REQUIRED"
            st.markdown(
                f"""
                <div class="status-card">
                  <h3>{title} <span class="{state_class}">· {state_text}</span></h3>
                  <p>활성종목 {status.active_symbols:,} · 가격 {status.price_rows:,}행 · Replay {status.replay_events:,}건 · Vector {status.replay_vectors:,}건</p>
                  <p>가격 최신일 {status.latest_price_date or '-'} · Replay 최신일 {status.latest_replay_date or '-'}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if not status.ready:
                st.warning(" / ".join(status.issues))
                st.code(f"{price_cmd}\n{replay_cmd}", language="bash")

    st.markdown('<div class="section"><h2>Decision Workflow</h2><span>추천 → 판단 → 주문 → 성과</span></div>', unsafe_allow_html=True)
    w1, w2, w3, w4 = st.columns(4)
    w1.info("**01 RECOMMEND**\n\nDaily Center에서 후보 생성")
    w2.info("**02 DECIDE**\n\nMeta Score와 Radar 검토")
    w3.info("**03 EXECUTE**\n\nTrading Desk 승인 주문")
    w4.info("**04 REVIEW**\n\nCockpit·Performance 확인")

    st.markdown('<div class="section"><h2>Quick Access</h2><span>업무 흐름 중심</span></div>', unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    q1.page_link("pages/7_Daily_Center.py", label="KR Daily Recommendation", icon="📈")
    q2.page_link("pages/10_US_Daily_Center.py", label="US Daily Recommendation", icon="📊")
    q3.page_link("pages/9_Trading_Desk.py", label="KR Trading Desk", icon="💳")
    q4.page_link("pages/12_US_Trading_Desk.py", label="US Trading Desk", icon="💵")


def _summary_counts() -> tuple[int, int, int]:
    kr_rec = _latest_recommendation_count(Path("datahub/market.db"))
    us_rec = _latest_recommendation_count(Path("datahub/us_market.db"))
    pending = _pending_count(Path("datahub/market.db"), "trade_order_requests")
    pending += _pending_count(Path("datahub/us_market.db"), "us_trade_order_requests")
    return kr_rec, us_rec, pending


def _latest_recommendation_count(path: Path) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recommendation_runs'").fetchone()
        if not exists:
            return 0
        row = conn.execute("SELECT recommendation_count FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _pending_count(path: Path, table: str) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            return 0
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status='PENDING_APPROVAL'").fetchone()[0])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
