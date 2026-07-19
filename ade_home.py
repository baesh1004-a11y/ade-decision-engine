from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

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
        .hero{display:flex;justify-content:space-between;align-items:flex-end;padding:25px 30px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(239,247,255,.88));border:1px solid var(--line);box-shadow:0 18px 52px rgba(42,88,130,.11);margin-bottom:15px}
        .hero h1{margin:4px 0 7px;font-size:36px;letter-spacing:-.045em}.hero p{margin:0;color:var(--muted)}
        .eyebrow{font-size:12px;letter-spacing:.17em;font-weight:850;color:#2f78ba}.mode{font-size:13px;font-weight:850;color:#226bad;background:#e9f3ff;border:1px solid rgba(47,128,237,.16);padding:9px 13px;border-radius:999px}
        .section{display:flex;justify-content:space-between;align-items:center;margin:21px 0 9px}.section h2{font-size:20px;margin:0;letter-spacing:-.03em}.section span{color:var(--muted);font-size:13px}
        .market-card,.system-card{padding:18px 19px;border-radius:19px;background:var(--glass);border:1px solid var(--line);box-shadow:0 9px 26px rgba(56,100,139,.07);min-height:128px}
        .market-card h3,.system-card h3{margin:0 0 8px;font-size:17px}.market-card p,.system-card p{margin:5px 0;color:var(--muted);font-size:13px}.ok{color:#16724d;font-weight:850}.warn{color:#b36b16;font-weight:850}.bad{color:#b23b3b;font-weight:850}
        .flow{padding:16px 18px;border-radius:17px;background:rgba(255,255,255,.78);border:1px solid var(--line);min-height:92px}.flow strong{color:#246daa}.flow span{display:block;margin-top:6px;color:var(--muted);font-size:13px}
        div[data-testid="stMetric"]{background:rgba(255,255,255,.82);border:1px solid var(--line);padding:15px 17px;border-radius:18px;box-shadow:0 9px 26px rgba(56,100,139,.07)}
        div[data-testid="stMetricLabel"]{font-weight:720;color:#708397}div[data-testid="stMetricValue"]{font-size:1.75rem;font-weight:880;letter-spacing:-.04em;color:#1a3249}
        div[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 9px 26px rgba(56,100,139,.07)}
        @media(max-width:768px){.block-container{padding:.7rem}.hero{display:block;padding:22px}.mode{display:inline-block;margin-top:14px}.hero h1{font-size:30px}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    mode = os.getenv("KIS_ENV", "paper").upper()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(
        f"""
        <div class="hero">
          <div><div class="eyebrow">ADE · INVESTMENT OPERATIONS TERMINAL</div><h1>Command Center</h1><p>추천, 검증, 주문, 계좌와 시스템 상태를 5초 안에 확인합니다.</p></div>
          <div class="mode">KIS {mode} · {now}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kr_db = Path("datahub/market.db")
    us_db = Path("datahub/us_market.db")
    kr = inspect_market_db(str(kr_db), "kr")
    us = inspect_market_db(str(us_db), "us")

    kr_rec = _latest_recommendation_count(kr_db)
    us_rec = _latest_recommendation_count(us_db)
    kr_valid = _latest_validation_count(kr_db)
    us_valid = _latest_validation_count(us_db)
    pending_orders = _pending_count(kr_db, "trade_order_requests") + _pending_count(us_db, "us_trade_order_requests")
    holdings, account_value, cash = _portfolio_summary(kr_db, us_db)

    st.markdown('<div class="section"><h2>오늘의 운영 현황</h2><span>추천 · 검증 · 주문 · 계좌</span></div>', unsafe_allow_html=True)
    a, b, c, d, e, f = st.columns(6)
    a.metric("한국 추천", kr_rec)
    b.metric("미국 추천", us_rec)
    c.metric("검증 완료", kr_valid + us_valid)
    d.metric("승인 대기", pending_orders)
    e.metric("보유 종목", holdings if holdings is not None else "미연동")
    f.metric("계좌 평가", _format_money(account_value) if account_value is not None else "미연동")

    left, right = st.columns([1, 1], gap="medium")
    with left:
        st.markdown('<div class="section"><h2>시장별 상태</h2><span>추천과 데이터 준비도</span></div>', unsafe_allow_html=True)
        for title, status, rec_count, valid_count in [
            ("🇰🇷 한국시장", kr, kr_rec, kr_valid),
            ("🇺🇸 미국시장", us, us_rec, us_valid),
        ]:
            state_class = "ok" if status.ready else "warn"
            state_text = "정상" if status.ready else "확인 필요"
            st.markdown(
                f"""
                <div class="market-card">
                  <h3>{title} <span class="{state_class}">· {state_text}</span></h3>
                  <p>최근 추천 {rec_count}개 · 검증 완료 {valid_count}개</p>
                  <p>활성종목 {status.active_symbols:,} · 가격 {status.price_rows:,}행 · Replay {status.replay_events:,}건</p>
                  <p>가격 최신일 {status.latest_price_date or '-'} · Replay 최신일 {status.latest_replay_date or '-'}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if not status.ready and status.issues:
                st.caption("확인: " + " / ".join(status.issues))

    with right:
        st.markdown('<div class="section"><h2>계좌 및 주문</h2><span>KIS 연결 기준</span></div>', unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        s1.metric("현금", _format_money(cash) if cash is not None else "미연동")
        s2.metric("승인 대기 주문", pending_orders)
        kis_state = "실전 주문" if mode == "LIVE" else "모의투자"
        kis_class = "warn" if mode == "LIVE" else "ok"
        st.markdown(
            f"""
            <div class="system-card">
              <h3>KIS 운영모드 <span class="{kis_class}">· {kis_state}</span></h3>
              <p>실제 주문 전 승인 절차를 유지합니다.</p>
              <p>계좌 평가금액 {_format_money(account_value) if account_value is not None else '미연동'} · 보유종목 {holdings if holdings is not None else '미연동'}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section"><h2>시스템 상태</h2><span>KIS · DB · 추천엔진 · 데이터</span></div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    _system_box(s1, "KIS 연결", "운영모드 설정됨", True)
    _system_box(s2, "한국 DB", "정상" if kr.ready else "확인 필요", kr.ready)
    _system_box(s3, "미국 DB", "정상" if us.ready else "확인 필요", us.ready)
    _system_box(s4, "추천 엔진", "최근 실행 있음" if (kr_rec + us_rec) > 0 else "실행 이력 없음", (kr_rec + us_rec) > 0)

    st.markdown('<div class="section"><h2>업무 흐름</h2><span>추천 → 검증 → 주문 → 성과</span></div>', unsafe_allow_html=True)
    w1, w2, w3, w4 = st.columns(4)
    w1.markdown('<div class="flow"><strong>01 추천 생성</strong><span>한국·미국 후보 종목 생성</span></div>', unsafe_allow_html=True)
    w2.markdown('<div class="flow"><strong>02 검증 및 판단</strong><span>근거 비교와 AI Radar 확인</span></div>', unsafe_allow_html=True)
    w3.markdown('<div class="flow"><strong>03 승인 주문</strong><span>사용자 승인 후 KIS 전송</span></div>', unsafe_allow_html=True)
    w4.markdown('<div class="flow"><strong>04 성과 점검</strong><span>포트폴리오와 성과 분석</span></div>', unsafe_allow_html=True)

    st.markdown('<div class="section"><h2>최근 실행</h2><span>추천 및 주문 이벤트</span></div>', unsafe_allow_html=True)
    recent = _recent_activity(kr_db, us_db)
    if recent.empty:
        st.info("최근 실행 이력이 없습니다.")
    else:
        st.dataframe(recent, use_container_width=True, hide_index=True)

    st.markdown('<div class="section"><h2>빠른 실행</h2><span>자주 사용하는 기능</span></div>', unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    q1.page_link("pages/7_Daily_Center.py", label="한국 추천 생성", icon="📈", use_container_width=True)
    q2.page_link("pages/10_US_Daily_Center.py", label="미국 추천 생성", icon="📊", use_container_width=True)
    q3.page_link("pages/9_Trading_Desk.py", label="한국 주문관리", icon="💳", use_container_width=True)
    q4.page_link("pages/12_US_Trading_Desk.py", label="미국 주문관리", icon="💵", use_container_width=True)


def _system_box(column, title: str, detail: str, healthy: bool) -> None:
    state_class = "ok" if healthy else "warn"
    state_text = "정상" if healthy else "확인 필요"
    column.markdown(
        f'<div class="system-card"><h3>{title}</h3><p><span class="{state_class}">● {state_text}</span></p><p>{detail}</p></div>',
        unsafe_allow_html=True,
    )


def _latest_recommendation_count(path: Path) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        if not _table_exists(conn, "recommendation_runs"):
            return 0
        row = conn.execute(
            "SELECT recommendation_count FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _latest_validation_count(path: Path) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        for table in ("final_decisions", "meta_score_results", "recommendation_validations"):
            if not _table_exists(conn, table):
                continue
            columns = _columns(conn, table)
            if "run_id" in columns:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE run_id=(SELECT run_id FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1)"
                ).fetchone()
            else:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0]) if row else 0
        return 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _pending_count(path: Path, table: str) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        if not _table_exists(conn, table):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status='PENDING_APPROVAL'").fetchone()[0])
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _portfolio_summary(*paths: Path) -> tuple[int | None, float | None, float | None]:
    holdings_total = 0
    value_total = 0.0
    cash_total = 0.0
    found = False
    for path in paths:
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            for table in ("portfolio_positions", "account_positions", "positions", "kis_holdings"):
                if not _table_exists(conn, table):
                    continue
                columns = _columns(conn, table)
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                holdings_total += len(rows)
                for row in rows:
                    data = dict(row)
                    value_total += _first_number(data, ("evaluation_amount", "market_value", "eval_amount", "value")) or 0.0
                found = True
                break
            for table in ("portfolio_state", "account_summary", "kis_account_summary"):
                if not _table_exists(conn, table):
                    continue
                row = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 1").fetchone()
                if row:
                    data = dict(row)
                    cash_total += _first_number(data, ("cash", "available_cash", "cash_balance", "deposit")) or 0.0
                    account_value = _first_number(data, ("total_equity", "evaluation_amount", "account_value", "total_asset"))
                    if account_value is not None:
                        value_total += account_value
                    found = True
                break
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    if not found:
        return None, None, None
    return holdings_total, value_total, cash_total


def _recent_activity(kr_path: Path, us_path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for market, path in (("한국", kr_path), ("미국", us_path)):
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            if _table_exists(conn, "recommendation_runs"):
                columns = _columns(conn, "recommendation_runs")
                time_col = "finished_at" if "finished_at" in columns else "started_at"
                for row in conn.execute(
                    f"SELECT * FROM recommendation_runs ORDER BY {time_col} DESC LIMIT 4"
                ).fetchall():
                    data = dict(row)
                    rows.append({
                        "시각": data.get(time_col) or "-",
                        "시장": market,
                        "구분": "추천 생성",
                        "상태": data.get("status") or "-",
                        "내용": f"추천 {int(data.get('recommendation_count') or 0)}개",
                    })
            order_table = "trade_order_requests" if market == "한국" else "us_trade_order_requests"
            if _table_exists(conn, order_table):
                columns = _columns(conn, order_table)
                time_col = next((c for c in ("updated_at", "created_at", "requested_at") if c in columns), None)
                if time_col:
                    for row in conn.execute(f"SELECT * FROM {order_table} ORDER BY {time_col} DESC LIMIT 3").fetchall():
                        data = dict(row)
                        rows.append({
                            "시각": data.get(time_col) or "-",
                            "시장": market,
                            "구분": "주문",
                            "상태": data.get("status") or "-",
                            "내용": str(data.get("ticker") or data.get("symbol") or "-")
                        })
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    if not rows:
        return pd.DataFrame(columns=["시각", "시장", "구분", "상태", "내용"])
    frame = pd.DataFrame(rows)
    return frame.sort_values("시각", ascending=False).head(8)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _first_number(data: dict[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _format_money(value: float | None) -> str:
    if value is None:
        return "미연동"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:,.1f}억원"
    if abs(value) >= 10_000:
        return f"{value / 10_000:,.0f}만원"
    return f"{value:,.0f}원"


if __name__ == "__main__":
    main()
