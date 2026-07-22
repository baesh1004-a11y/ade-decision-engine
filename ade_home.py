from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from broker.kis import load_kis_env
from dashboard.system_status import inspect_market_db


@dataclass(frozen=True)
class PortfolioSummary:
    kr_holdings: int = 0
    us_holdings: int = 0
    krw_value: float | None = None
    krw_cash: float | None = None
    usd_value: float | None = None

    @property
    def total_holdings(self) -> int:
        return self.kr_holdings + self.us_holdings


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
    kr_pending = _pending_count(kr_db, "trade_order_requests")
    us_pending = _pending_count(us_db, "us_trade_order_requests")
    pending_orders = _count_sum(kr_pending, us_pending)
    validation_total = _count_sum(kr_valid, us_valid)
    recommendation_total = _count_sum(kr_rec, us_rec)
    portfolio = _portfolio_summary(kr_db, us_db)
    kis_detail, kis_health = _kis_connection_status()

    st.markdown('<div class="section"><h2>오늘의 운영 현황</h2><span>추천 · 검증 · 주문 · 계좌</span></div>', unsafe_allow_html=True)
    a, b, c, d, e, f = st.columns(6)
    a.metric("한국 추천", _count_text(kr_rec))
    b.metric("미국 추천", _count_text(us_rec))
    c.metric("검증 완료", _count_text(validation_total))
    d.metric("승인 대기", _count_text(pending_orders))
    e.metric("보유 종목", portfolio.total_holdings, help=f"한국 {portfolio.kr_holdings} · 미국 {portfolio.us_holdings}")
    f.metric("한국 계좌 평가", _format_money(portfolio.krw_value) if portfolio.krw_value is not None else "미연동")
    unavailable = [
        label for label, value in (
            ("한국 추천", kr_rec), ("미국 추천", us_rec),
            ("한국 검증", kr_valid), ("미국 검증", us_valid),
            ("한국 승인 대기", kr_pending), ("미국 승인 대기", us_pending),
        ) if value is None
    ]
    if unavailable:
        st.warning("DB 조회 실패로 확인할 수 없는 항목: " + ", ".join(unavailable))

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
                  <p>최근 추천 {_count_with_unit(rec_count, '개')} · 검증 완료 {_count_with_unit(valid_count, '개')}</p>
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
        s1, s2, s3 = st.columns(3)
        s1.metric("한국 현금", _format_money(portfolio.krw_cash) if portfolio.krw_cash is not None else "미연동")
        s2.metric("미국 평가", _format_usd(portfolio.usd_value) if portfolio.usd_value is not None else "미연동")
        s3.metric("승인 대기 주문", _count_text(pending_orders))
        kis_state = "실전 주문" if mode == "LIVE" else "모의투자"
        kis_class = "warn" if mode == "LIVE" else "ok"
        st.markdown(
            f"""
            <div class="system-card">
              <h3>KIS 운영모드 <span class="{kis_class}">· {kis_state}</span></h3>
              <p>실제 주문 전 승인 절차를 유지합니다.</p>
              <p>한국 {_format_money(portfolio.krw_value) if portfolio.krw_value is not None else '미연동'} · 미국 {_format_usd(portfolio.usd_value) if portfolio.usd_value is not None else '미연동'}</p>
              <p>보유종목 한국 {portfolio.kr_holdings}개 · 미국 {portfolio.us_holdings}개</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section"><h2>시스템 상태</h2><span>KIS · DB · 추천엔진 · 데이터</span></div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    _system_box(s1, "KIS 연결", kis_detail, kis_health)
    _system_box(s2, "한국 DB", "정상" if kr.ready else "확인 필요", kr.ready)
    _system_box(s3, "미국 DB", "정상" if us.ready else "확인 필요", us.ready)
    _system_box(
        s4,
        "추천 엔진",
        "조회 실패" if recommendation_total is None else "최근 실행 있음" if recommendation_total > 0 else "실행 이력 없음",
        None if recommendation_total is None else recommendation_total > 0,
    )

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
        st.dataframe(recent, width="stretch", hide_index=True)

    st.markdown('<div class="section"><h2>빠른 실행</h2><span>자주 사용하는 기능</span></div>', unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    q1.page_link("pages/7_Daily_Center.py", label="한국 추천 생성", icon="📈", width="stretch")
    q2.page_link("pages/10_US_Daily_Center.py", label="미국 추천 생성", icon="📊", width="stretch")
    q3.page_link("pages/9_Trading_Desk.py", label="한국 주문관리", icon="💳", width="stretch")
    q4.page_link("pages/12_US_Trading_Desk.py", label="미국 주문관리", icon="💵", width="stretch")


def _system_box(column, title: str, detail: str, healthy: bool | None) -> None:
    state_class = "ok" if healthy is True else "warn"
    state_text = "정상" if healthy is True else "연결 미확인" if healthy is None else "확인 필요"
    column.markdown(
        f'<div class="system-card"><h3>{title}</h3><p><span class="{state_class}">● {state_text}</span></p><p>{detail}</p></div>',
        unsafe_allow_html=True,
    )


def _latest_recommendation_count(path: Path) -> int | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    try:
        if not _table_exists(conn, "recommendation_runs"):
            return 0
        row = conn.execute(
            "SELECT recommendation_count FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _latest_validation_count(path: Path) -> int | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    try:
        for table in ("final_decisions", "meta_score_results", "recommendation_validations"):
            if not _table_exists(conn, table):
                continue
            columns = _columns(conn, table)
            if "source_run_id" in columns:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source_run_id=(SELECT run_id FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1)"
                ).fetchone()
            elif "run_id" in columns:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE run_id=(SELECT run_id FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1)"
                ).fetchone()
            else:
                continue
            return int(row[0]) if row else 0
        return 0
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _pending_count(path: Path, table: str) -> int | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    try:
        if not _table_exists(conn, table):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status='PENDING_APPROVAL'").fetchone()[0])
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _portfolio_summary(kr_path: Path, us_path: Path) -> PortfolioSummary:
    kr_holdings, krw_value, krw_cash = _domestic_portfolio_summary(kr_path)
    us_holdings, usd_value = _us_portfolio_summary(us_path)
    return PortfolioSummary(
        kr_holdings=kr_holdings,
        us_holdings=us_holdings,
        krw_value=krw_value,
        krw_cash=krw_cash,
        usd_value=usd_value,
    )


def _domestic_portfolio_summary(path: Path) -> tuple[int, float | None, float | None]:
    if not path.exists():
        return 0, None, None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        holdings = 0
        positions_value = 0.0
        positions_found = False
        for table in ("portfolio_positions", "account_positions", "positions", "kis_holdings"):
            if not _table_exists(conn, table):
                continue
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            holdings = len(rows)
            positions_value = sum(
                _first_number(dict(row), ("evaluation_amount", "market_value", "eval_amount", "value")) or 0.0
                for row in rows
            )
            positions_found = True
            break

        cash: float | None = None
        account_value: float | None = None
        for table in ("portfolio_state", "account_summary", "kis_account_summary"):
            if not _table_exists(conn, table):
                continue
            row = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 1").fetchone()
            if row:
                data = dict(row)
                cash = _first_number(data, ("cash", "available_cash", "cash_balance", "deposit"))
                account_value = _first_number(data, ("total_equity", "evaluation_amount", "account_value", "total_asset"))
            break

        if account_value is None and (positions_found or cash is not None):
            account_value = positions_value + (cash or 0.0)
        return holdings, account_value, cash
    except sqlite3.Error:
        return 0, None, None
    finally:
        conn.close()


def _us_portfolio_summary(path: Path) -> tuple[int, float | None]:
    if not path.exists():
        return 0, None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "us_position_snapshots"):
            return 0, None
        latest = conn.execute("SELECT MAX(captured_at) FROM us_position_snapshots").fetchone()[0]
        if not latest:
            return 0, None
        rows = conn.execute(
            "SELECT ticker, evaluation_amount FROM us_position_snapshots WHERE captured_at=?",
            (latest,),
        ).fetchall()
        return len(rows), sum(float(row["evaluation_amount"] or 0.0) for row in rows)
    except (sqlite3.Error, TypeError, ValueError):
        return 0, None
    finally:
        conn.close()


def _kis_connection_status() -> tuple[str, bool | None]:
    load_kis_env()
    missing = []
    if not os.getenv("KIS_APP_KEY"):
        missing.append("APP_KEY")
    if not os.getenv("KIS_APP_SECRET"):
        missing.append("APP_SECRET")
    if not (os.getenv("KIS_ACCOUNT") or os.getenv("KIS_ACCOUNT_NO")):
        missing.append("ACCOUNT")
    if missing:
        return "설정 누락: " + ", ".join(missing), False
    return "인증정보 설정됨 · 실제 API 연결은 아직 확인하지 않음", None


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


def _format_usd(value: float | None) -> str:
    return "미연동" if value is None else f"${value:,.2f}"


def _count_sum(*values: int | None) -> int | None:
    return None if any(value is None for value in values) else sum(int(value) for value in values if value is not None)


def _count_text(value: int | None) -> str:
    return "확인 불가" if value is None else f"{value:,}"


def _count_with_unit(value: int | None, unit: str) -> str:
    return "확인 불가" if value is None else f"{value:,}{unit}"


if __name__ == "__main__":
    main()
