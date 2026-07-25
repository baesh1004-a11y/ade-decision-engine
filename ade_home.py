from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from html import escape
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
        :root{
          --mobile-bg:#0a1018;
          --mobile-panel:#111a26;
          --mobile-panel-2:#162231;
          --mobile-line:rgba(255,255,255,.08);
          --mobile-text:#f7fbff;
          --mobile-muted:#92a4b8;
          --mobile-blue:#68b7ff;
          --mobile-green:#5ad6a0;
          --mobile-amber:#ffd27d;
          --mobile-red:#ff9b9b;
        }
        .mobile-app{display:none}
        .desktop-home{display:block}
        .mobile-bottom-nav{display:none}
        .mobile-topbar,.mobile-summary-grid,.mobile-section,.mobile-action-list,.mobile-account,.mobile-events{display:none}
        .ops-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:12px 0 20px}
        .ops-card{padding:17px 18px;border:1px solid var(--ade-line);border-radius:18px;background:var(--ade-panel);box-shadow:var(--ade-shadow)}
        .ops-card span{display:block;color:var(--ade-muted);font-size:12px;font-weight:760}.ops-card strong{display:block;margin:8px 0 4px;font-size:22px;color:var(--ade-ink)}
        .ops-card small{color:var(--ade-muted)}
        .action-card{padding:18px;border:1px solid var(--ade-line);border-radius:18px;background:linear-gradient(145deg,#fff,#f6faff);min-height:170px}
        .action-card h3{margin:0 0 8px;font-size:18px}.action-card p{margin:5px 0;color:var(--ade-muted);font-size:13px}
        .market-card,.system-card{padding:18px 19px;border-radius:18px;background:var(--ade-panel);border:1px solid var(--ade-line);box-shadow:var(--ade-shadow);min-height:130px}
        .market-card h3,.system-card h3{margin:0 0 8px;font-size:17px}.market-card p,.system-card p{margin:5px 0;color:var(--ade-muted);font-size:13px}
        .flow{padding:16px 18px;border-radius:17px;background:var(--ade-panel);border:1px solid var(--ade-line);min-height:95px}.flow strong{color:var(--ade-blue)}.flow span{display:block;margin-top:6px;color:var(--ade-muted);font-size:13px}
        .recent-mobile{display:none}
        .recent-card{padding:14px 15px;border:1px solid rgba(255,255,255,.09);border-radius:16px;background:linear-gradient(145deg,rgba(26,37,51,.96),rgba(17,25,36,.96));box-shadow:0 10px 24px rgba(0,0,0,.18)}
        .recent-card+.recent-card{margin-top:10px}
        .recent-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px}
        .recent-card-title{font-size:15px;font-weight:800;color:#f4f8fc}
        .recent-card-symbol{margin-top:8px;font-size:21px;font-weight:850;letter-spacing:.02em;color:#fff}
        .recent-card-time{margin-top:7px;font-size:12px;color:#93a5b8;word-break:break-all}
        .recent-status{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;font-size:11px;font-weight:800;border:1px solid transparent}
        .recent-status.pending{background:rgba(245,184,73,.14);border-color:rgba(245,184,73,.3);color:#ffd889}
        .recent-status.filled{background:rgba(49,189,132,.14);border-color:rgba(49,189,132,.3);color:#7ee2b5}
        .recent-status.expired,.recent-status.failed,.recent-status.rejected,.recent-status.cancelled,.recent-status.canceled{background:rgba(233,93,93,.14);border-color:rgba(233,93,93,.3);color:#ffaaaa}
        .recent-status.neutral{background:rgba(132,156,184,.14);border-color:rgba(132,156,184,.3);color:#cad6e3}
        @media(max-width:900px){.ops-strip{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:640px){
          [data-testid="stSidebar"]{display:none!important}
          [data-testid="stSidebarCollapsedControl"]{display:none!important}
          [data-testid="stHeader"]{background:transparent!important}
          [data-testid="stToolbar"]{display:none!important}
          [data-testid="stDecoration"]{display:none!important}
          [data-testid="stAppViewContainer"]{background:var(--mobile-bg)!important}
          [data-testid="stAppViewContainer"] .main .block-container{max-width:none!important;padding:0 16px 104px!important}
          .desktop-home{display:none!important}
          .mobile-app{display:block;color:var(--mobile-text);padding-top:max(10px,env(safe-area-inset-top))}
          .mobile-topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 2px 10px}
          .mobile-topbar small{display:block;color:var(--mobile-muted);font-size:12px;font-weight:700;letter-spacing:.02em}
          .mobile-topbar h1{margin:5px 0 0;color:var(--mobile-text);font-size:29px;line-height:1.1;letter-spacing:-.04em}
          .mobile-status-dot{display:flex;align-items:center;gap:7px;padding:8px 10px;border-radius:999px;background:rgba(90,214,160,.1);border:1px solid rgba(90,214,160,.22);color:#8be9bd;font-size:11px;font-weight:800;white-space:nowrap}
          .mobile-status-dot:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--mobile-green);box-shadow:0 0 0 4px rgba(90,214,160,.12)}
          .mobile-summary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:8px}
          .mobile-summary-card{padding:16px;border-radius:20px;background:linear-gradient(145deg,var(--mobile-panel-2),var(--mobile-panel));border:1px solid var(--mobile-line);box-shadow:0 14px 30px rgba(0,0,0,.18)}
          .mobile-summary-card span{display:block;color:var(--mobile-muted);font-size:12px;font-weight:750}
          .mobile-summary-card strong{display:block;margin-top:8px;color:var(--mobile-text);font-size:26px;line-height:1;font-weight:900;letter-spacing:-.04em}
          .mobile-summary-card em{display:block;margin-top:7px;color:#b7c4d2;font-size:11px;font-style:normal}
          .mobile-section{display:block;margin-top:28px}
          .mobile-section-head{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:11px}
          .mobile-section-head h2{margin:0;color:var(--mobile-text);font-size:19px;letter-spacing:-.03em}
          .mobile-section-head span{color:var(--mobile-muted);font-size:11px}
          .mobile-action-list{display:grid;gap:10px}
          .mobile-action{display:grid;grid-template-columns:44px 1fr auto;align-items:center;gap:12px;padding:14px;border-radius:20px;background:var(--mobile-panel);border:1px solid var(--mobile-line);text-decoration:none!important}
          .mobile-action .icon{display:grid;place-items:center;width:44px;height:44px;border-radius:15px;background:#17293d;font-size:21px}
          .mobile-action strong{display:block;color:var(--mobile-text);font-size:15px}
          .mobile-action small{display:block;margin-top:4px;color:var(--mobile-muted);font-size:12px;line-height:1.35}
          .mobile-action .chev{color:#6f8297;font-size:22px}
          .mobile-account{display:block;padding:18px;border-radius:24px;background:linear-gradient(145deg,#14314b,#0e2235);border:1px solid rgba(104,183,255,.16);box-shadow:0 18px 36px rgba(0,0,0,.23)}
          .mobile-account .label{color:#a6bdd2;font-size:12px;font-weight:750}
          .mobile-account .value{margin-top:7px;color:#fff;font-size:28px;font-weight:900;letter-spacing:-.05em}
          .mobile-account-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:16px}
          .mobile-account-grid div{padding:12px;border-radius:16px;background:rgba(255,255,255,.055)}
          .mobile-account-grid span{display:block;color:#9db2c7;font-size:11px}
          .mobile-account-grid strong{display:block;margin-top:5px;color:#f5fbff;font-size:15px}
          .mobile-events{display:grid;gap:9px}
          .mobile-event{display:grid;grid-template-columns:1fr auto;gap:12px;padding:14px 15px;border-radius:18px;background:var(--mobile-panel);border:1px solid var(--mobile-line)}
          .mobile-event strong{display:block;color:var(--mobile-text);font-size:14px}
          .mobile-event small{display:block;margin-top:5px;color:var(--mobile-muted);font-size:11px}
          .mobile-event .symbol{margin-top:7px;color:#dbe8f4;font-size:17px;font-weight:850}
          .mobile-event .status{align-self:start;padding:5px 8px;border-radius:999px;font-size:10px;font-weight:850}
          .mobile-event .status.pending{background:rgba(255,210,125,.12);color:var(--mobile-amber)}
          .mobile-event .status.filled{background:rgba(90,214,160,.12);color:#86e6b9}
          .mobile-event .status.expired,.mobile-event .status.failed,.mobile-event .status.rejected,.mobile-event .status.cancelled,.mobile-event .status.canceled{background:rgba(255,155,155,.12);color:var(--mobile-red)}
          .mobile-event .status.neutral{background:rgba(146,164,184,.13);color:#c6d0da}
          .mobile-bottom-nav{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;left:0;right:0;bottom:0;z-index:1000;background:rgba(8,13,20,.97);backdrop-filter:blur(18px);border-top:1px solid rgba(255,255,255,.08);padding:8px 8px calc(8px + env(safe-area-inset-bottom));box-shadow:0 -12px 28px rgba(0,0,0,.28)}
          .mobile-bottom-nav a{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:48px;color:#8393a5!important;text-decoration:none!important;font-size:10px;font-weight:800;border-radius:14px}
          .mobile-bottom-nav a span:first-child{font-size:19px;line-height:1}
          .mobile-bottom-nav a.active{background:#15283c;color:#78c5ff!important}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    mode = os.getenv("KIS_ENV", "paper").upper()
    now = datetime.now().strftime("%m월 %d일 %H:%M")
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
    recent = _recent_activity(kr_db, us_db)

    st.markdown(
        _mobile_home(
            mode=mode,
            now=now,
            kr=kr,
            us=us,
            recommendation_total=recommendation_total,
            pending_orders=pending_orders,
            scheduled=scheduled,
            validation_total=validation_total,
            portfolio=portfolio,
            kis_detail=kis_detail,
            kis_health=kis_health,
            recent=recent,
        ),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="desktop-home">', unsafe_allow_html=True)
    page_hero(
        st,
        "상황판",
        "오늘 해야 할 일, 시장 준비도, 승인 대기 주문과 계좌 상태를 한 화면에서 확인합니다.",
        eyebrow="ADE · INVESTMENT OPERATIONS TERMINAL",
        badge=f"KIS {mode} · {now}",
    )

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
    _action_card(c1, "추천 생성", f"최근 추천 {_count_with_unit(recommendation_total, '개')}", "추천이 없거나 오래됐다면 한국·미국 추천 배치를 먼저 실행하세요.", "pages/14_Recommendation_Workbench.py", "워크벤치 열기", "📊")
    _action_card(c2, "승인 대기 주문", _count_with_unit(pending_orders, "건"), "추천 실행 ID와 위험 정보를 확인한 뒤 승인 여부를 결정하세요.", "pages/9_Trading_Desk.py", "한국 주문 열기", "💳")
    _action_card(c3, "예약주문", f"활성 {scheduled['active']} · 실패 {scheduled['failed']}", "다음 실행 시각과 실패·재시도 상태를 확인하세요.", "pages/15_Scheduled_Orders.py", "예약주문 관리", "🗓️")
    _action_card(c4, "포트폴리오 점검", f"보유 {portfolio.total_holdings}개", "현금 비중, 시장별 노출과 성과를 확인하세요.", "pages/1_ADE_Cockpit.py", "포트폴리오 열기", "💼")

    section_header(st, "운영 요약", "시장 준비도와 계좌 안전 상태")
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        for title, status, rec_count, valid_count in [("🇰🇷 한국시장", kr, kr_rec, kr_valid), ("🇺🇸 미국시장", us, us_rec, us_valid)]:
            badge = status_badge("정상" if status.ready else "확인 필요", "success" if status.ready else "warning")
            st.markdown(f'<div class="market-card"><h3>{title} {badge}</h3><p>최근 추천 {_count_with_unit(rec_count, "개")} · 검증 완료 {_count_with_unit(valid_count, "개")}</p><p>활성종목 {status.active_symbols:,} · 가격 {status.price_rows:,}행 · Replay {status.replay_events:,}건</p><p>가격 최신일 {status.latest_price_date or "-"} · Replay 최신일 {status.latest_replay_date or "-"}</p></div>', unsafe_allow_html=True)
            if not status.ready and status.issues:
                st.caption("확인: " + " / ".join(status.issues))
    with right:
        kis_state = "실전 주문" if mode == "LIVE" else "모의투자"
        kis_tone = "warning" if mode == "LIVE" else "success"
        st.markdown(f'<div class="system-card"><h3>KIS 운영모드 {status_badge(kis_state, kis_tone)}</h3><p>{kis_detail}</p><p>한국 계좌 {_format_money(portfolio.krw_value)} · 현금 {_format_money(portfolio.krw_cash)}</p><p>미국 평가 {_format_usd(portfolio.usd_value)} · 승인 대기 {_count_with_unit(pending_orders, "건")}</p></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ops-strip"><div class="ops-card"><span>오늘 실행 예정</span><strong>{scheduled["due_today"]}</strong><small>예약주문</small></div><div class="ops-card"><span>재시도 대기</span><strong>{scheduled["retry"]}</strong><small>예약주문</small></div><div class="ops-card"><span>한국 현금</span><strong>{_format_money(portfolio.krw_cash)}</strong><small>계좌 요약</small></div><div class="ops-card"><span>미국 평가</span><strong>{_format_usd(portfolio.usd_value)}</strong><small>계좌 요약</small></div></div>', unsafe_allow_html=True)

    section_header(st, "시스템 상태", "KIS · DB · 추천 엔진")
    s1, s2, s3, s4 = st.columns(4)
    _system_box(s1, "KIS 연결", kis_detail, kis_health)
    _system_box(s2, "한국 DB", "정상" if kr.ready else "확인 필요", kr.ready)
    _system_box(s3, "미국 DB", "정상" if us.ready else "확인 필요", us.ready)
    _system_box(s4, "추천 엔진", "조회 실패" if recommendation_total is None else "최근 실행 있음" if recommendation_total > 0 else "실행 이력 없음", None if recommendation_total is None else recommendation_total > 0)

    section_header(st, "업무 흐름", "추천 → 검증 → 주문 → 성과")
    w1, w2, w3, w4 = st.columns(4)
    w1.markdown('<div class="flow"><strong>01 추천 생성</strong><span>한국·미국 후보 종목 생성</span></div>', unsafe_allow_html=True)
    w2.markdown('<div class="flow"><strong>02 검증 및 판단</strong><span>차트, 과거 패턴, 환경 조언 확인</span></div>', unsafe_allow_html=True)
    w3.markdown('<div class="flow"><strong>03 승인 주문</strong><span>사용자 승인 후 KIS 전송</span></div>', unsafe_allow_html=True)
    w4.markdown('<div class="flow"><strong>04 성과 점검</strong><span>포트폴리오와 성과 분석</span></div>', unsafe_allow_html=True)

    section_header(st, "최근 실행", "추천 및 주문 이벤트")
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
    st.markdown('</div>', unsafe_allow_html=True)


def _mobile_home(
    *,
    mode: str,
    now: str,
    kr,
    us,
    recommendation_total: int | None,
    pending_orders: int | None,
    scheduled: dict[str, int],
    validation_total: int | None,
    portfolio: PortfolioSummary,
    kis_detail: str,
    kis_health: bool | None,
    recent: pd.DataFrame,
) -> str:
    system_ready = bool(kr.ready and us.ready and kis_health is not False)
    event_html = _mobile_event_cards(recent)
    return f'''
    <div class="mobile-app">
      <header class="mobile-topbar">
        <div><small>{escape(now)} · KIS {escape(mode)}</small><h1>상황판</h1></div>
        <div class="mobile-status-dot">{"정상" if system_ready else "확인 필요"}</div>
      </header>

      <section class="mobile-summary-grid">
        {_mobile_summary_card("AI 추천", _count_text(recommendation_total), "누적 추천")}
        {_mobile_summary_card("승인 대기", _count_text(pending_orders), "확인할 주문")}
        {_mobile_summary_card("활성 예약", str(scheduled["active"]), f'오늘 {scheduled["due_today"]}건 실행')}
        {_mobile_summary_card("검증 완료", _count_text(validation_total), "판단 준비")}
      </section>

      <section class="mobile-section">
        <div class="mobile-section-head"><h2>바로 실행</h2><span>자주 쓰는 기능</span></div>
        <div class="mobile-action-list">
          {_mobile_action("📈", "AI 추천", "한국·미국 추천 결과 확인", "/Recommendation_Workbench")}
          {_mobile_action("💳", "승인 대기 주문", f'{_count_text(pending_orders)}건 검토 필요', "/Trading_Desk")}
          {_mobile_action("🗓️", "예약주문", f'활성 {scheduled["active"]}건 · 실패 {scheduled["failed"]}건', "/Scheduled_Orders")}
          {_mobile_action("💼", "포트폴리오", f'보유 종목 {portfolio.total_holdings}개', "/ADE_Cockpit")}
        </div>
      </section>

      <section class="mobile-section">
        <div class="mobile-section-head"><h2>내 계좌</h2><span>{escape(kis_detail)}</span></div>
        <div class="mobile-account">
          <div class="label">한국 계좌 평가</div>
          <div class="value">{_format_money(portfolio.krw_value)}</div>
          <div class="mobile-account-grid">
            <div><span>현금</span><strong>{_format_money(portfolio.krw_cash)}</strong></div>
            <div><span>미국 평가</span><strong>{_format_usd(portfolio.usd_value)}</strong></div>
            <div><span>한국시장</span><strong>{"정상" if kr.ready else "확인 필요"}</strong></div>
            <div><span>미국시장</span><strong>{"정상" if us.ready else "확인 필요"}</strong></div>
          </div>
        </div>
      </section>

      <section class="mobile-section">
        <div class="mobile-section-head"><h2>최근 이벤트</h2><span>최신 주문</span></div>
        <div class="mobile-events">{event_html}</div>
      </section>
    </div>
    <nav class="mobile-bottom-nav">
      <a class="active" href="/"><span>⌂</span><span>홈</span></a>
      <a href="/Recommendation_Workbench"><span>📈</span><span>추천</span></a>
      <a href="/Trading_Desk"><span>💳</span><span>주문</span></a>
      <a href="/Scheduled_Orders"><span>🗓️</span><span>예약</span></a>
      <a href="/ADE_Cockpit"><span>💼</span><span>자산</span></a>
    </nav>
    '''


def _mobile_summary_card(label: str, value: str, detail: str) -> str:
    return f'<div class="mobile-summary-card"><span>{escape(label)}</span><strong>{escape(value)}</strong><em>{escape(detail)}</em></div>'


def _mobile_action(icon: str, title: str, detail: str, href: str) -> str:
    return f'<a class="mobile-action" href="{href}"><span class="icon">{icon}</span><span><strong>{escape(title)}</strong><small>{escape(detail)}</small></span><span class="chev">›</span></a>'


def _mobile_event_cards(frame: pd.DataFrame) -> str:
    if frame.empty:
        return '<div class="mobile-event"><div><strong>최근 이벤트 없음</strong><small>새 주문과 추천이 여기에 표시됩니다.</small></div></div>'
    cards: list[str] = []
    for row in frame.head(5).to_dict("records"):
        event_type = escape(str(row.get("구분", "-")))
        symbol = escape(str(row.get("종목", "-")))
        status = str(row.get("상태", "-")).upper()
        time_text = escape(str(row.get("시각", "-")))
        cards.append(
            f'<article class="mobile-event"><div><strong>{event_type}</strong><div class="symbol">{symbol}</div><small>{time_text}</small></div>'
            f'<span class="status {_status_class(status)}">{escape(status)}</span></article>'
        )
    return "".join(cards)


def _action_card(column, title: str, value: str, description: str, target: str, label: str, icon: str) -> None:
    column.markdown(f'<div class="action-card"><h3>{icon} {title}</h3><p><strong>{value}</strong></p><p>{description}</p></div>', unsafe_allow_html=True)
    column.page_link(target, label=label, icon=icon, width="stretch")


def _system_box(column, title: str, detail: str, healthy: bool | None) -> None:
    tone = "success" if healthy is True else "warning" if healthy is False else "neutral"
    state = "정상" if healthy is True else "확인 필요" if healthy is False else "알 수 없음"
    column.markdown(f'<div class="system-card"><h3>{title} {status_badge(state, tone)}</h3><p>{detail}</p></div>', unsafe_allow_html=True)


def _status_class(status: str) -> str:
    normalized = status.upper()
    if normalized in {"PENDING", "WAITING", "QUEUED"}:
        return "pending"
    if normalized in {"FILLED", "COMPLETED", "DONE", "SUCCESS"}:
        return "filled"
    if normalized in {"EXPIRED", "FAILED", "REJECTED", "CANCELLED", "CANCELED"}:
        return normalized.lower()
    return "neutral"


def _latest_recommendation_count(db_path: Path) -> int | None:
    return _latest_run_count(db_path, "recommendations")


def _latest_validation_count(db_path: Path) -> int | None:
    return _latest_run_count(db_path, "validation_results")


def _latest_run_count(db_path: Path, table: str) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def _pending_count(db_path: Path, table: str) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status='PENDING'").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def _scheduled_order_summary(db_path: Path) -> dict[str, int]:
    summary = {"active": 0, "failed": 0, "due_today": 0, "retry": 0}
    if not db_path.exists():
        return summary
    try:
        with sqlite3.connect(db_path) as conn:
            summary["active"] = conn.execute("SELECT COUNT(*) FROM scheduled_orders WHERE status='ACTIVE'").fetchone()[0]
            summary["failed"] = conn.execute("SELECT COUNT(*) FROM scheduled_orders WHERE status='FAILED'").fetchone()[0]
            summary["retry"] = conn.execute("SELECT COUNT(*) FROM scheduled_orders WHERE retry_count > 0 AND status='ACTIVE'").fetchone()[0]
            summary["due_today"] = conn.execute("SELECT COUNT(*) FROM scheduled_orders WHERE date(next_run_at)=date('now','localtime') AND status='ACTIVE'").fetchone()[0]
    except sqlite3.Error:
        pass
    return summary


def _portfolio_summary(kr_db: Path, us_db: Path) -> PortfolioSummary:
    return PortfolioSummary()


def _kis_connection_status() -> tuple[str, bool | None]:
    try:
        env = load_kis_env()
        app_key = getattr(env, "app_key", None)
        account = getattr(env, "account_no", None)
        if app_key and account:
            return "환경설정 확인됨", True
        return "환경설정 일부 누락", False
    except Exception:
        return "환경설정 조회 실패", None


def _recent_activity(kr_db: Path, us_db: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for label, path, table in [("한국 주문", kr_db, "trade_order_requests"), ("미국 주문", us_db, "us_trade_order_requests")]:
        if not path.exists():
            continue
        try:
            with sqlite3.connect(path) as conn:
                cursor = conn.execute(f"SELECT created_at, symbol, status FROM {table} ORDER BY created_at DESC LIMIT 5")
                rows.extend({"시각": created_at, "구분": label, "종목": symbol, "상태": status} for created_at, symbol, status in cursor.fetchall())
        except sqlite3.Error:
            continue
    if not rows:
        return pd.DataFrame(columns=["시각", "구분", "종목", "상태"])
    frame = pd.DataFrame(rows)
    return frame.sort_values("시각", ascending=False).head(10)


def _count_text(value: int | None) -> str:
    return "-" if value is None else f"{value:,}"


def _count_sum(*values: int | None) -> int | None:
    return None if any(value is None for value in values) else sum(int(value) for value in values if value is not None)


def _count_with_unit(value: int | None, unit: str) -> str:
    return "확인 불가" if value is None else f"{value:,}{unit}"


def _format_money(value: float | None) -> str:
    return "-" if value is None else f"₩{value:,.0f}"


def _format_usd(value: float | None) -> str:
    return "-" if value is None else f"${value:,.2f}"


if __name__ == "__main__":
    main()
