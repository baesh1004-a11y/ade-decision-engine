from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from broker.kis import load_kis_env
from dashboard.design_system import apply_global_style, page_hero, section_header, status_badge
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

    st.set_page_config(page_title="ADE 상황판", page_icon="📊", layout="wide")
    apply_global_style(st)
    st.markdown(
        """
        <style>
        .ops-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:12px 0 20px}
        .ops-card{padding:17px 18px;border:1px solid var(--ade-line);border-radius:18px;background:var(--ade-panel);box-shadow:var(--ade-shadow)}
        .ops-card span{display:block;color:var(--ade-muted);font-size:12px;font-weight:760}.ops-card strong{display:block;margin:8px 0 4px;font-size:22px;color:var(--ade-ink)}
        .ops-card small{color:var(--ade-muted)}
        .action-card{padding:18px;border:1px solid var(--ade-line);border-radius:18px;background:linear-gradient(145deg,#fff,#f6faff);min-height:170px}
        .action-card h3{margin:0 0 8px;font-size:18px}.action-card p{margin:5px 0;color:var(--ade-muted);font-size:13px}
        .market-card,.system-card{padding:18px 19px;border-radius:18px;background:var(--ade-panel);border:1px solid var(--ade-line);box-shadow:var(--ade-shadow);min-height:130px}
        .market-card h3,.system-card h3{margin:0 0 8px;font-size:17px}.market-card p,.system-card p{margin:5px 0;color:var(--ade-muted);font-size:13px}
        .flow{padding:16px 18px;border-radius:17px;background:var(--ade-panel);border:1px solid var(--ade-line);min-height:95px}.flow strong{color:var(--ade-blue)}.flow span{display:block;margin-top:6px;color:var(--ade-muted);font-size:13px}
        @media(max-width:900px){.ops-strip{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:640px){.ops-strip{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    mode = os.getenv("KIS_ENV", "paper").upper()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    page_hero(
        st,
        "상황판",
        "오늘 해야 할 일, 시장 준비도, 승인 대기 주문과 계좌 상태를 한 화면에서 확인합니다.",
        eyebrow="ADE · INVESTMENT OPERATIONS TERMINAL",
        badge=f"KIS {mode} · {now}",
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
    scheduled = _scheduled_order_summary(kr_db)
    pending_orders = _count_sum(kr_pending, us_pending)
    validation_total = _count_sum(kr_valid, us_valid)
    recommendation_total = _count_sum(kr_rec, us_rec)
    portfolio = _portfolio_summary(kr_db, us_db)
    kis_detail, kis_health = _kis_connection_status()

    section_header(st, "오늘의 핵심 상태", "추천 · 검증 · 주문 · 예약 · 계좌")
    a, b, c, d, e, f = st.columns(6)
    a.metric("한국 추천", _count_text(kr_rec))
    b.metric("미국 추천", _count_text(us_rec))
    c.metric("검증 완료", _count_text(validation_total))
    d.metric("승인 대기", _count_text(pending_orders))
    e.metric("활성 예약", _count_text(scheduled["active"]))
    f.metric("보유 종목", portfolio.total_holdings, help=f"한국 {portfolio.kr_holdings} · 미국 {portfolio.us_holdings}")

    unavailable = [
        label for label, value in (
            ("한국 추천", kr_rec), ("미국 추천", us_rec),
            ("한국 검증", kr_valid), ("미국 검증", us_valid),
            ("한국 승인 대기", kr_pending), ("미국 승인 대기", us_pending),
        ) if value is None
    ]
    if unavailable:
        st.warning("DB 조회 실패로 확인할 수 없는 항목: " + ", ".join(unavailable))

    section_header(st, "지금 해야 할 일", "운영 우선순위에 따라 바로 이동")
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    _action_card(
        c1,
        "추천 생성",
        f"최근 추천 {_count_with_unit(recommendation_total, '개')}",
        "추천이 없거나 오래됐다면 한국·미국 추천 배치를 먼저 실행하세요.",
        "pages/14_Recommendation_Workbench.py",
        "워크벤치 열기",
        "📊",
    )
    _action_card(
        c2,
        "승인 대기 주문",
        _count_with_unit(pending_orders, "건"),
        "추천 실행 ID와 위험 정보를 확인한 뒤 승인 여부를 결정하세요.",
        "pages/9_Trading_Desk.py",
        "한국 주문 열기",
        "💳",
    )
    _action_card(
        c3,
        "예약주문",
        f"활성 {scheduled['active']} · 실패 {scheduled['failed']}",
        "다음 실행 시각과 실패·재시도 상태를 확인하세요.",
        "pages/15_Scheduled_Orders.py",
        "예약주문 관리",
        "🗓️",
    )
    _action_card(
        c4,
        "포트폴리오 점검",
        f"보유 {portfolio.total_holdings}개",
        "현금 비중, 시장별 노출과 성과를 확인하세요.",
        "pages/1_ADE_Cockpit.py",
        "포트폴리오 열기",
        "💼",
    )

    section_header(st, "운영 요약", "시장 준비도와 계좌 안전 상태")
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        for title, status, rec_count, valid_count in [
            ("🇰🇷 한국시장", kr, kr_rec, kr_valid),
            ("🇺🇸 미국시장", us, us_rec, us_valid),
        ]:
            badge = status_badge("정상" if status.ready else "확인 필요", "success" if status.ready else "warning")
            st.markdown(
                f"""
                <div class="market-card">
                  <h3>{title} {badge}</h3>
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
        kis_state = "실전 주문" if mode == "LIVE" else "모의투자"
        kis_tone = "warning" if mode == "LIVE" else "success"
        st.markdown(
            f"""
            <div class="system-card">
              <h3>KIS 운영모드 {status_badge(kis_state, kis_tone)}</h3>
              <p>{kis_detail}</p>
              <p>한국 계좌 {_format_money(portfolio.krw_value)} · 현금 {_format_money(portfolio.krw_cash)}</p>
              <p>미국 평가 {_format_usd(portfolio.usd_value)} · 승인 대기 {_count_with_unit(pending_orders, '건')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="ops-strip">
              <div class="ops-card"><span>오늘 실행 예정</span><strong>{scheduled['due_today']}</strong><small>예약주문</small></div>
              <div class="ops-card"><span>재시도 대기</span><strong>{scheduled['retry']}</strong><small>예약주문</small></div>
              <div class="ops-card"><span>한국 현금</span><strong>{_format_money(portfolio.krw_cash)}</strong><small>계좌 요약</small></div>
              <div class="ops-card"><span>미국 평가</span><strong>{_format_usd(portfolio.usd_value)}</strong><small>계좌 요약</small></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    section_header(st, "시스템 상태", "KIS · DB · 추천 엔진")
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

    section_header(st, "업무 흐름", "추천 → 검증 → 주문 → 성과")
    w1, w2, w3, w4 = st.columns(4)
    w1.markdown('<div class="flow"><strong>01 추천 생성</strong><span>한국·미국 후보 종목 생성</span></div>', unsafe_allow_html=True)
    w2.markdown('<div class="flow"><strong>02 검증 및 판단</strong><span>차트, 과거 패턴, 환경 조언 확인</span></div>', unsafe_allow_html=True)
    w3.markdown('<div class="flow"><strong>03 승인 주문</strong><span>사용자 승인 후 KIS 전송</span></div>', unsafe_allow_html=True)
    w4.markdown('<div class="flow"><strong>04 성과 점검</strong><span>포트폴리오와 성과 분석</span></div>', unsafe_allow_html=True)

    section_header(st, "최근 실행", "추천 및 주문 이벤트")
    recent = _recent_activity(kr_db, us_db)
    if recent.empty:
        st.info("최근 실행 이력이 없습니다.")
    else:
        st.dataframe(recent, width="stretch", hide_index=True)

    section_header(st, "빠른 실행", "자주 사용하는 기능")
    q1, q2, q3, q4, q5 = st.columns(5)
    q1.page_link("pages/7_Daily_Center.py", label="한국 추천", icon="📈", width="stretch")
    q2.page_link("pages/10_US_Daily_Center.py", label="미국 추천", icon="📊", width="stretch")
    q3.page_link("pages/9_Trading_Desk.py", label="한국 주문", icon="💳", width="stretch")
    q4.page_link("pages/12_US_Trading_Desk.py", label="미국 주문", icon="💵", width="stretch")
    q5.page_link("pages/15_Scheduled_Orders.py", label="예약주문", icon="🗓️", width="stretch")


def _action_card(column, title: str, value: str, description: str, target: str, label: str, icon: str) -> None:
    column.markdown(
        f'<div class="action-card"><h3>{icon} {title}</h3><p><strong>{value}</strong></p><p>{description}</p></div>',
        unsafe_allow_html=True,
    )
    column.page_link(target, label=label, width="stretch")


def _system_box(column, title: str, detail: str, ok: bool | None) -> None:
    tone = "success" if ok else "warning" if ok is False else "neutral"
    badge = status_badge("정상" if ok else "확인 필요" if ok is False else "확인 불가", tone)
    column.markdown(
        f'<div class="system-card"><h3>{title} {badge}</h3><p>{detail}</p></div>',
        unsafe_allow_html=True,
    )


def _latest_recommendation_count(db_path: Path) -> int | None:
    query = """
        SELECT COUNT(*)
        FROM recommendation_results
        WHERE run_id = (SELECT MAX(run_id) FROM recommendation_results)
    """
    return _scalar(db_path, query)


def _latest_validation_count(db_path: Path) -> int | None:
    candidates = [
        "SELECT COUNT(*) FROM recommendation_validations WHERE run_id = (SELECT MAX(run_id) FROM recommendation_validations)",
        "SELECT COUNT(*) FROM validation_results WHERE run_id = (SELECT MAX(run_id) FROM validation_results)",
    ]
    for query in candidates:
        value = _scalar(db_path, query)
        if value is not None:
            return value
    return None


def _pending_count(db_path: Path, table: str) -> int | None:
    queries = [
        f"SELECT COUNT(*) FROM {table} WHERE LOWER(COALESCE(status, 'pending')) IN ('pending', 'ready', 'waiting', 'requested')",
        f"SELECT COUNT(*) FROM {table}",
    ]
    for query in queries:
        value = _scalar(db_path, query)
        if value is not None:
            return value
    return None


def _scheduled_order_summary(db_path: Path) -> dict[str, int]:
    defaults = {"active": 0, "failed": 0, "retry": 0, "due_today": 0}
    if not db_path.exists():
        return defaults
    try:
        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            table = next((name for name in ("scheduled_orders", "scheduled_order_requests", "trade_order_schedules") if name in tables), None)
            if not table:
                return defaults
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            status_col = next((name for name in ("status", "state") if name in columns), None)
            run_at_col = next((name for name in ("scheduled_at", "run_at", "execute_at", "next_run_at") if name in columns), None)
            retry_col = next((name for name in ("retry_count", "attempt_count", "retries") if name in columns), None)
            if status_col:
                rows = conn.execute(f"SELECT LOWER(COALESCE({status_col}, '')) AS status, COUNT(*) FROM {table} GROUP BY 1").fetchall()
                for status, count in rows:
                    if status in {"active", "pending", "scheduled", "ready"}:
                        defaults["active"] += count
                    if status in {"failed", "error"}:
                        defaults["failed"] += count
                    if status in {"retry", "retrying"}:
                        defaults["retry"] += count
            else:
                defaults["active"] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            if retry_col:
                defaults["retry"] = max(defaults["retry"], int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE COALESCE({retry_col}, 0) > 0").fetchone()[0]))
            if run_at_col:
                defaults["due_today"] = int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE date({run_at_col}) = date('now', 'localtime')").fetchone()[0])
    except (sqlite3.Error, TypeError, ValueError):
        return defaults
    return defaults


def _portfolio_summary(kr_db: Path, us_db: Path) -> PortfolioSummary:
    kr_holdings = _first_scalar(kr_db, [
        "SELECT COUNT(*) FROM portfolio_positions WHERE COALESCE(quantity, 0) > 0",
        "SELECT COUNT(*) FROM positions WHERE COALESCE(quantity, 0) > 0",
        "SELECT COUNT(*) FROM holdings WHERE COALESCE(quantity, 0) > 0",
    ]) or 0
    us_holdings = _first_scalar(us_db, [
        "SELECT COUNT(*) FROM portfolio_positions WHERE COALESCE(quantity, 0) > 0",
        "SELECT COUNT(*) FROM us_positions WHERE COALESCE(quantity, 0) > 0",
        "SELECT COUNT(*) FROM holdings WHERE COALESCE(quantity, 0) > 0",
    ]) or 0
    krw_value = _first_scalar_float(kr_db, [
        "SELECT SUM(COALESCE(market_value, evaluation_amount, quantity * current_price, 0)) FROM portfolio_positions",
        "SELECT SUM(COALESCE(market_value, evaluation_amount, quantity * current_price, 0)) FROM positions",
    ])
    krw_cash = _first_scalar_float(kr_db, [
        "SELECT cash_balance FROM account_snapshots ORDER BY rowid DESC LIMIT 1",
        "SELECT available_cash FROM account_snapshots ORDER BY rowid DESC LIMIT 1",
        "SELECT cash FROM portfolio_summary ORDER BY rowid DESC LIMIT 1",
    ])
    usd_value = _first_scalar_float(us_db, [
        "SELECT SUM(COALESCE(market_value, evaluation_amount, quantity * current_price, 0)) FROM portfolio_positions",
        "SELECT SUM(COALESCE(market_value, evaluation_amount, quantity * current_price, 0)) FROM us_positions",
    ])
    return PortfolioSummary(kr_holdings, us_holdings, krw_value, krw_cash, usd_value)


def _recent_activity(kr_db: Path, us_db: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    specs = [
        (kr_db, "한국 추천", "recommendation_results"),
        (kr_db, "한국 주문", "trade_order_requests"),
        (us_db, "미국 추천", "recommendation_results"),
        (us_db, "미국 주문", "us_trade_order_requests"),
    ]
    for db_path, source, table in specs:
        frame = _recent_table(db_path, table, source)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    return result.sort_values("시각", ascending=False).head(12)


def _recent_table(db_path: Path, table: str, source: str) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in tables:
                return pd.DataFrame()
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            time_col = next((name for name in ("created_at", "requested_at", "updated_at", "run_at", "date") if name in columns), None)
            symbol_col = next((name for name in ("symbol", "ticker", "code") if name in columns), None)
            status_col = next((name for name in ("status", "decision", "action", "side") if name in columns), None)
            selected = [name for name in (time_col, symbol_col, status_col) if name]
            if not selected:
                return pd.DataFrame()
            order = f" ORDER BY {time_col} DESC" if time_col else " ORDER BY rowid DESC"
            rows = conn.execute(f"SELECT {', '.join(selected)} FROM {table}{order} LIMIT 5").fetchall()
            records = []
            for row in rows:
                values = dict(zip(selected, row))
                records.append({
                    "시각": str(values.get(time_col, "-")) if time_col else "-",
                    "구분": source,
                    "종목": str(values.get(symbol_col, "-")) if symbol_col else "-",
                    "상태": str(values.get(status_col, "-")) if status_col else "-",
                })
            return pd.DataFrame(records)
    except sqlite3.Error:
        return pd.DataFrame()


def _kis_connection_status() -> tuple[str, bool | None]:
    try:
        env = load_kis_env()
    except Exception as exc:
        return f"설정 확인 필요: {exc}", False
    keys = [getattr(env, name, None) for name in ("app_key", "app_secret", "account_no")]
    if all(keys):
        return "API 키와 계좌 설정 확인됨", True
    return "일부 API 또는 계좌 설정이 비어 있습니다.", False


def _scalar(db_path: Path, query: str) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(query).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except (sqlite3.Error, TypeError, ValueError):
        return None


def _scalar_float(db_path: Path, query: str) -> float | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(query).fetchone()
            return float(row[0]) if row and row[0] is not None else None
    except (sqlite3.Error, TypeError, ValueError):
        return None


def _first_scalar(db_path: Path, queries: list[str]) -> int | None:
    for query in queries:
        value = _scalar(db_path, query)
        if value is not None:
            return value
    return None


def _first_scalar_float(db_path: Path, queries: list[str]) -> float | None:
    for query in queries:
        value = _scalar_float(db_path, query)
        if value is not None:
            return value
    return None


def _count_sum(*values: int | None) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _count_text(value: int | None) -> str:
    return "조회 실패" if value is None else f"{value:,}"


def _count_with_unit(value: int | None, unit: str) -> str:
    return "조회 실패" if value is None else f"{value:,}{unit}"


def _format_money(value: float | None) -> str:
    return "조회 불가" if value is None else f"₩{value:,.0f}"


def _format_usd(value: float | None) -> str:
    return "조회 불가" if value is None else f"${value:,.2f}"


if __name__ == "__main__":
    main()
