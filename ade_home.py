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

    st.set_page_config(page_title="ADE Command Center", page_icon="?뱤", layout="wide")
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
          <div><div class="eyebrow">ADE 쨌 INVESTMENT OPERATIONS TERMINAL</div><h1>Command Center</h1><p>異붿쿇, 寃利? 二쇰Ц, 怨꾩쥖? ?쒖뒪???곹깭瑜?5珥??덉뿉 ?뺤씤?⑸땲??</p></div>
          <div class="mode">KIS {mode} 쨌 {now}</div>
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
    portfolio = _portfolio_summary(kr_db, us_db)
    kis_detail, kis_health = _kis_connection_status()

    st.markdown('<div class="section"><h2>?ㅻ뒛???댁쁺 ?꾪솴</h2><span>異붿쿇 쨌 寃利?쨌 二쇰Ц 쨌 怨꾩쥖</span></div>', unsafe_allow_html=True)
    a, b, c, d, e, f = st.columns(6)
    a.metric("?쒓뎅 異붿쿇", kr_rec)
    b.metric("誘멸뎅 異붿쿇", us_rec)
    c.metric("寃利??꾨즺", kr_valid + us_valid)
    d.metric("?뱀씤 ?湲?, pending_orders)
    e.metric("蹂댁쑀 醫낅ぉ", portfolio.total_holdings, help=f"?쒓뎅 {portfolio.kr_holdings} 쨌 誘멸뎅 {portfolio.us_holdings}")
    f.metric("?쒓뎅 怨꾩쥖 ?됯?", _format_money(portfolio.krw_value) if portfolio.krw_value is not None else "誘몄뿰??)

    left, right = st.columns([1, 1], gap="medium")
    with left:
        st.markdown('<div class="section"><h2>?쒖옣蹂??곹깭</h2><span>異붿쿇怨??곗씠??以鍮꾨룄</span></div>', unsafe_allow_html=True)
        for title, status, rec_count, valid_count in [
            ("?눖?눟 ?쒓뎅?쒖옣", kr, kr_rec, kr_valid),
            ("?눣?눡 誘멸뎅?쒖옣", us, us_rec, us_valid),
        ]:
            state_class = "ok" if status.ready else "warn"
            state_text = "?뺤긽" if status.ready else "?뺤씤 ?꾩슂"
            st.markdown(
                f"""
                <div class="market-card">
                  <h3>{title} <span class="{state_class}">쨌 {state_text}</span></h3>
                  <p>理쒓렐 異붿쿇 {rec_count}媛?쨌 寃利??꾨즺 {valid_count}媛?/p>
                  <p>?쒖꽦醫낅ぉ {status.active_symbols:,} 쨌 媛寃?{status.price_rows:,}??쨌 Replay {status.replay_events:,}嫄?/p>
                  <p>媛寃?理쒖떊??{status.latest_price_date or '-'} 쨌 Replay 理쒖떊??{status.latest_replay_date or '-'}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if not status.ready and status.issues:
                st.caption("?뺤씤: " + " / ".join(status.issues))

    with right:
        st.markdown('<div class="section"><h2>怨꾩쥖 諛?二쇰Ц</h2><span>KIS ?곌껐 湲곗?</span></div>', unsafe_allow_html=True)
        s1, s2, s3 = st.columns(3)
        s1.metric("?쒓뎅 ?꾧툑", _format_money(portfolio.krw_cash) if portfolio.krw_cash is not None else "誘몄뿰??)
        s2.metric("誘멸뎅 ?됯?", _format_usd(portfolio.usd_value) if portfolio.usd_value is not None else "誘몄뿰??)
        s3.metric("?뱀씤 ?湲?二쇰Ц", pending_orders)
        kis_state = "?ㅼ쟾 二쇰Ц" if mode == "LIVE" else "紐⑥쓽?ъ옄"
        kis_class = "warn" if mode == "LIVE" else "ok"
        st.markdown(
            f"""
            <div class="system-card">
              <h3>KIS ?댁쁺紐⑤뱶 <span class="{kis_class}">쨌 {kis_state}</span></h3>
              <p>?ㅼ젣 二쇰Ц ???뱀씤 ?덉감瑜??좎??⑸땲??</p>
              <p>?쒓뎅 {_format_money(portfolio.krw_value) if portfolio.krw_value is not None else '誘몄뿰??} 쨌 誘멸뎅 {_format_usd(portfolio.usd_value) if portfolio.usd_value is not None else '誘몄뿰??}</p>
              <p>蹂댁쑀醫낅ぉ ?쒓뎅 {portfolio.kr_holdings}媛?쨌 誘멸뎅 {portfolio.us_holdings}媛?/p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section"><h2>?쒖뒪???곹깭</h2><span>KIS 쨌 DB 쨌 異붿쿇?붿쭊 쨌 ?곗씠??/span></div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    _system_box(s1, "KIS ?곌껐", kis_detail, kis_health)
    _system_box(s2, "?쒓뎅 DB", "?뺤긽" if kr.ready else "?뺤씤 ?꾩슂", kr.ready)
    _system_box(s3, "誘멸뎅 DB", "?뺤긽" if us.ready else "?뺤씤 ?꾩슂", us.ready)
    _system_box(s4, "異붿쿇 ?붿쭊", "理쒓렐 ?ㅽ뻾 ?덉쓬" if (kr_rec + us_rec) > 0 else "?ㅽ뻾 ?대젰 ?놁쓬", (kr_rec + us_rec) > 0)

    st.markdown('<div class="section"><h2>?낅Т ?먮쫫</h2><span>異붿쿇 ??寃利???二쇰Ц ???깃낵</span></div>', unsafe_allow_html=True)
    w1, w2, w3, w4 = st.columns(4)
    w1.markdown('<div class="flow"><strong>01 異붿쿇 ?앹꽦</strong><span>?쒓뎅쨌誘멸뎅 ?꾨낫 醫낅ぉ ?앹꽦</span></div>', unsafe_allow_html=True)
    w2.markdown('<div class="flow"><strong>02 寃利?諛??먮떒</strong><span>洹쇨굅 鍮꾧탳? AI Radar ?뺤씤</span></div>', unsafe_allow_html=True)
    w3.markdown('<div class="flow"><strong>03 ?뱀씤 二쇰Ц</strong><span>?ъ슜???뱀씤 ??KIS ?꾩넚</span></div>', unsafe_allow_html=True)
    w4.markdown('<div class="flow"><strong>04 ?깃낵 ?먭?</strong><span>?ы듃?대━?ㅼ? ?깃낵 遺꾩꽍</span></div>', unsafe_allow_html=True)

    st.markdown('<div class="section"><h2>理쒓렐 ?ㅽ뻾</h2><span>異붿쿇 諛?二쇰Ц ?대깽??/span></div>', unsafe_allow_html=True)
    recent = _recent_activity(kr_db, us_db)
    if recent.empty:
        st.info("理쒓렐 ?ㅽ뻾 ?대젰???놁뒿?덈떎.")
    else:
        st.dataframe(recent, use_container_width=True, hide_index=True)

    st.markdown('<div class="section"><h2>鍮좊Ⅸ ?ㅽ뻾</h2><span>?먯＜ ?ъ슜?섎뒗 湲곕뒫</span></div>', unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    q1.page_link("pages/7_Daily_Center.py", label="?쒓뎅 異붿쿇 ?앹꽦", icon="?뱢", use_container_width=True)
    q2.page_link("pages/10_US_Daily_Center.py", label="誘멸뎅 異붿쿇 ?앹꽦", icon="?뱤", use_container_width=True)
    q3.page_link("pages/9_Trading_Desk.py", label="?쒓뎅 二쇰Ц愿由?, icon="?뮩", use_container_width=True)
    q4.page_link("pages/12_US_Trading_Desk.py", label="誘멸뎅 二쇰Ц愿由?, icon="?뮫", use_container_width=True)


def _system_box(column, title: str, detail: str, healthy: bool | None) -> None:
    state_class = "ok" if healthy is True else "warn"
    state_text = "?뺤긽" if healthy is True else "?곌껐 誘명솗?? if healthy is None else "?뺤씤 ?꾩슂"
    column.markdown(
        f'<div class="system-card"><h3>{title}</h3><p><span class="{state_class}">??{state_text}</span></p><p>{detail}</p></div>',
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
        return "?ㅼ젙 ?꾨씫: " + ", ".join(missing), False
    return "?몄쬆?뺣낫 ?ㅼ젙??쨌 ?ㅼ젣 API ?곌껐? ?꾩쭅 ?뺤씤?섏? ?딆쓬", None


def _recent_activity(kr_path: Path, us_path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for market, path in (("?쒓뎅", kr_path), ("誘멸뎅", us_path)):
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
                        "?쒓컖": data.get(time_col) or "-",
                        "?쒖옣": market,
                        "援щ텇": "異붿쿇 ?앹꽦",
                        "?곹깭": data.get("status") or "-",
                        "?댁슜": f"異붿쿇 {int(data.get('recommendation_count') or 0)}媛?,
                    })
            order_table = "trade_order_requests" if market == "?쒓뎅" else "us_trade_order_requests"
            if _table_exists(conn, order_table):
                columns = _columns(conn, order_table)
                time_col = next((c for c in ("updated_at", "created_at", "requested_at") if c in columns), None)
                if time_col:
                    for row in conn.execute(f"SELECT * FROM {order_table} ORDER BY {time_col} DESC LIMIT 3").fetchall():
                        data = dict(row)
                        rows.append({
                            "?쒓컖": data.get(time_col) or "-",
                            "?쒖옣": market,
                            "援щ텇": "二쇰Ц",
                            "?곹깭": data.get("status") or "-",
                            "?댁슜": str(data.get("ticker") or data.get("symbol") or "-")
                        })
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    if not rows:
        return pd.DataFrame(columns=["?쒓컖", "?쒖옣", "援щ텇", "?곹깭", "?댁슜"])
    frame = pd.DataFrame(rows)
    return frame.sort_values("?쒓컖", ascending=False).head(8)


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
        return "誘몄뿰??
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:,.1f}?듭썝"
    if abs(value) >= 10_000:
        return f"{value / 10_000:,.0f}留뚯썝"
    return f"{value:,.0f}??


def _format_usd(value: float | None) -> str:
    return "誘몄뿰?? if value is None else f"${value:,.2f}"


if __name__ == "__main__":
    main()

