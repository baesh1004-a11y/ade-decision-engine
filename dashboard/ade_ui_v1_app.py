from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as recommendation_base
from dashboard.design_system import apply_design_system
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context


ORDER_CANDIDATES_PATH = Path("output/ade_order_candidates.json")


CUSTOM_CSS = """
<style>
:root {
  --ade-blue: #2f67d8;
  --ade-blue-soft: #edf3ff;
  --ade-red: #e5484d;
  --ade-green: #18a36f;
  --ade-ink: #172033;
  --ade-muted: #6b7484;
  --ade-line: #e7eaf0;
  --ade-panel: #ffffff;
}
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
section[data-testid="stSidebar"],
div[data-testid="stSidebarNav"],
[data-testid="collapsedControl"],
button[kind="headerNoPadding"] {
  display: none !important;
}
[data-testid="stAppViewContainer"] > .main,
[data-testid="stAppViewBlockContainer"],
.main .block-container {
  margin-left: 0 !important;
  max-width: 1480px !important;
  padding-left: 2rem !important;
  padding-right: 2rem !important;
}
.stApp { background: #f7f9fc; color: var(--ade-ink); }
.block-container { max-width: 1480px; padding-top: 0.7rem; padding-bottom: 5rem; }
[data-testid="stHeader"] { background: rgba(247,249,252,.94); }
.ade-brand { font-size: 1.35rem; font-weight: 900; letter-spacing: -.04em; }
.ade-subtle { color: var(--ade-muted); font-size: .86rem; }
.ade-divider { border-top: 1px solid var(--ade-line); margin: .8rem 0; }
.ade-statusbar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 999; background: rgba(255,255,255,.96); border-top: 1px solid var(--ade-line); padding: .55rem 1.2rem; display:flex; gap:1rem; justify-content:center; font-size:.82rem; backdrop-filter: blur(12px); }
.ade-ok { color: var(--ade-green); font-weight: 800; }
.ade-rank { font-weight:900; color:var(--ade-blue); }
.ade-orderbook { display:grid; grid-template-columns: 1fr 1fr 1fr; border:1px solid var(--ade-line); border-radius:14px; overflow:hidden; }
.ade-orderbook div { padding:10px 12px; border-bottom:1px solid var(--ade-line); text-align:right; }
.ade-orderbook .head { color:var(--ade-muted); font-size:.78rem; background:#fafbfe; font-weight:800; text-align:center; }
.ade-orderbook .ask { background:#fff5f5; }
.ade-orderbook .bid { background:#f3f7ff; }
.ade-orderbook .mid { font-weight:900; font-size:1.02rem; }
.ade-jp-separator { border-left:1px solid #d4d9e2; margin-left:1.4rem; padding-left:1.4rem; }
</style>
"""


def run() -> None:
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    apply_design_system()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    _init_state()
    _render_top_navigation()

    page = st.session_state.ade_primary_page
    if page == "상황종합판":
        _render_overview()
    elif page == "추천결과":
        _render_recommendations()
    elif page == "주문":
        _render_orders()
    else:
        _render_jp_radar()

    _render_status_bar()


def _init_state() -> None:
    defaults = {
        "ade_primary_page": "상황종합판",
        "ade_overview_tab": "시장",
        "ade_market": "kr",
        "ade_recommendation_detail": None,
        "ade_order_ticker": None,
        "ade_jp_ticker": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_top_navigation() -> None:
    c1, c2, c3, c4, c5, c6 = st.columns([1.8, 1.1, 1.1, 1, .28, 1.15])
    with c1:
        st.markdown('<div class="ade-brand">ADE <span class="ade-subtle">Decision Engine</span></div>', unsafe_allow_html=True)
    pages = [(c2, "상황종합판"), (c3, "추천결과"), (c4, "주문")]
    for col, label in pages:
        if col.button(label, type="primary" if st.session_state.ade_primary_page == label else "secondary", use_container_width=True):
            st.session_state.ade_primary_page = label
            st.session_state.ade_recommendation_detail = None
            st.rerun()
    with c5:
        st.markdown('<div class="ade-jp-separator">&nbsp;</div>', unsafe_allow_html=True)
    with c6:
        if st.button("JP Radar", type="primary" if st.session_state.ade_primary_page == "JP Radar" else "secondary", use_container_width=True):
            st.session_state.ade_primary_page = "JP Radar"
            st.rerun()
    st.markdown('<div class="ade-divider"></div>', unsafe_allow_html=True)


def _render_overview() -> None:
    tabs = st.segmented_control(
        "상황종합판 하위 메뉴",
        options=["시장", "이벤트", "내 투자"],
        default=st.session_state.ade_overview_tab,
        key="ade_overview_segment",
        label_visibility="collapsed",
    )
    st.session_state.ade_overview_tab = tabs or "시장"
    if tabs == "시장":
        _render_market_overview()
    elif tabs == "이벤트":
        _render_event_timeline()
    else:
        _render_portfolio_overview()


def _render_market_overview() -> None:
    st.markdown("### 시장의 현재 정보")
    cards = [
        ("KOSPI", "2,742.81", "+1.30%"),
        ("KOSDAQ", "872.32", "+1.42%"),
        ("S&P 500", "5,356.00", "+0.78%"),
        ("NASDAQ", "16,812.40", "+0.64%"),
        ("USD/KRW", "1,365.30", "-0.21%"),
        ("VIX", "13.64", "-2.01%"),
    ]
    cols = st.columns(6)
    for col, (label, value, delta) in zip(cols, cards):
        col.metric(label, value, delta)
    st.markdown("#### 오늘의 이벤트")
    _render_event_timeline(compact=True)
    st.markdown("#### 국내 섹터 강도")
    frame = pd.DataFrame(
        [["방산", 2.35], ["조선", 1.87], ["반도체", 1.24], ["은행", .45], ["2차전지", -.12], ["바이오", -.35], ["자동차", -.62], ["인터넷", -.81]],
        columns=["섹터", "등락률"],
    )
    st.bar_chart(frame.set_index("섹터"))


def _render_event_timeline(compact: bool = False) -> None:
    rows = [
        ("09:30", "한국 1분기 GDP", "발표"),
        ("10:00", "한국 5월 소비자심리지수", "예정"),
        ("21:30", "미국 1분기 GDP", "예정"),
        ("22:00", "미국 5월 신규주택판매", "예정"),
        ("05.29 03:00", "연준 베이지북", "예정"),
    ]
    if not compact:
        st.markdown("### 오늘의 이벤트 타임라인")
    for time_text, title, status in rows:
        c1, c2, c3 = st.columns([1, 5, 1])
        c1.markdown(f"**{time_text}**")
        c2.markdown(title)
        c3.caption(status)
        st.divider()


def _render_portfolio_overview() -> None:
    st.markdown("### 내 투자 현황")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 자산", "₩128,540,000", "+₩1,250,000")
    c2.metric("누적 수익률", "+18.56%")
    c3.metric("현금 비중", "23.4%")
    c4.metric("국내 / 미국", "63.2% / 36.8%")
    st.markdown("#### 보유종목 TOP 5")
    st.dataframe(pd.DataFrame([
        ["삼성전자", "₩25,450,000", "+2.35%"],
        ["SK하이닉스", "₩18,720,000", "+1.12%"],
        ["현대차", "₩11,280,000", "-0.35%"],
        ["한화에어로스페이스", "₩7,950,000", "+4.21%"],
        ["NAVER", "₩6,850,000", "-1.05%"],
    ], columns=["종목", "평가금액", "수익률"]), hide_index=True, use_container_width=True)


def _render_recommendations() -> None:
    market = _market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        _render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return
    recommendations, _context = _load_recommendations(market)
    st.markdown(f"### {'국내' if market == 'kr' else '미국'} 추천종목")
    for row in recommendations:
        _render_recommendation_row(row, market)
    if not recommendations:
        st.info("저장된 추천결과가 없습니다.")


def _render_recommendation_row(row: dict[str, Any], market: str) -> None:
    cols = st.columns([.55, 3.2, 1.25, 1.05, 1.05])
    cols[0].markdown(f'<div class="ade-rank">#{int(row.get("rank_no", 0))}</div>', unsafe_allow_html=True)
    symbol = str(row.get("symbol") or row.get("ticker"))
    ticker = str(row.get("ticker"))
    with cols[1]:
        if st.button(f"{symbol}\n\n{ticker}", key=f"open_detail_{market}_{ticker}", use_container_width=True):
            st.session_state.ade_recommendation_detail = ticker
            st.rerun()
    score = row.get("score") or row.get("final_similarity") or row.get("weekly_similarity")
    cols[2].metric("추천점수", f"{float(score or 0):.1f}")
    if cols[3].button("JP Radar", key=f"jp_{market}_{ticker}", use_container_width=True):
        st.session_state.ade_primary_page = "JP Radar"
        st.session_state.ade_jp_ticker = ticker
        st.session_state.ade_market = market
        st.rerun()
    if cols[4].button("주문", key=f"order_{market}_{ticker}", type="primary", use_container_width=True):
        _add_order_candidate(market, ticker, symbol)
        st.session_state.ade_primary_page = "주문"
        st.session_state.ade_order_ticker = ticker
        st.session_state.ade_market = market
        st.rerun()
    st.divider()


def _render_recommendation_detail(market: str, ticker: str) -> None:
    if st.button("← 추천종목으로 돌아가기"):
        st.session_state.ade_recommendation_detail = None
        st.rerun()
    recommendations, _context = _load_recommendations(market)
    selected = next((row for row in recommendations if str(row.get("ticker")) == ticker), None)
    if selected is None:
        st.warning("선택한 추천종목을 찾을 수 없습니다.")
        return
    st.markdown(f"## {selected.get('symbol') or ticker}")
    st.caption(f"{ticker} · 추천 상세")
    _render_current_chart(market, ticker)
    payload = _safe_json(selected.get("payload_json"))
    st.markdown("### 추천결과 상세")
    _render_detail_blocks(selected, payload)


def _render_current_chart(market: str, ticker: str) -> None:
    st.markdown("### 현재 차트")
    profile = get_market_profile(market)
    if not profile.db_path.exists():
        st.info("차트 데이터베이스가 없습니다.")
        return
    try:
        with sqlite3.connect(str(profile.db_path), timeout=5) as conn:
            bars = recommendation_base._current_bars(conn, market, normalize_ticker(ticker, market), profile.price_source)
        if bars is None or bars.empty:
            st.info("현재 차트 데이터가 없습니다.")
            return
        chart = bars.copy()
        date_col = "Date" if "Date" in chart.columns else chart.columns[0]
        close_col = "Close" if "Close" in chart.columns else chart.columns[-1]
        chart[date_col] = pd.to_datetime(chart[date_col])
        st.line_chart(chart.set_index(date_col)[close_col])
        if "Volume" in chart.columns:
            st.bar_chart(chart.set_index(date_col)["Volume"])
    except Exception as exc:
        st.info(f"현재 차트를 불러오지 못했습니다: {exc}")


def _render_detail_blocks(selected: dict[str, Any], payload: dict[str, Any]) -> None:
    fields = {
        "추천 이벤트 정보": ["recent_event_date", "recent_money_ratio", "market", "ticker", "symbol"],
        "가장 유사한 과거 사례": ["matched_event_id", "matched_event_date", "matched_ticker", "matched_name", "equivalent_week_index", "weeks_compared", "future_weeks_available"],
        "유사도 상세": ["weekly_similarity", "sto_similarity", "final_similarity", "current_sto_structure"],
        "과거 사례의 실제 성과": ["matched_max_return", "matched_max_drawdown"],
        "기간별 전망": ["prediction", "returns_by_day", "up_probabilities", "median_returns"],
        "주문 판단용 예상치": ["seven_day_up_probability", "seven_day_expected_return", "expected_max_return_7d", "expected_max_return_20d", "expected_max_drawdown_7d", "expected_peak_day", "holding_days", "target_return", "stop_return", "grade"],
        "최종 시스템 판단": ["decision", "action", "grade", "confidence"],
        "계산 과정 및 근거": ["reasons"],
        "유사 사례 Top N": ["replay_matches"],
    }
    merged = {**payload, **selected}
    for title, keys in fields.items():
        with st.expander(title, expanded=title in {"가장 유사한 과거 사례", "기간별 전망", "계산 과정 및 근거"}):
            values = {key: merged.get(key) for key in keys if merged.get(key) not in (None, "", [], {})}
            if not values:
                st.caption("표시할 데이터가 없습니다.")
                continue
            for key, value in values.items():
                if isinstance(value, (dict, list)):
                    st.json(value, expanded=False)
                else:
                    st.write(f"**{key}**: {value}")


def _render_orders() -> None:
    market = _market_selector("ade_order_market")
    st.markdown(f"### {'국내' if market == 'kr' else '미국'} 주문")
    search = st.text_input("종목명 또는 종목코드 검색", key=f"ade_order_search_{market}")
    add_cols = st.columns([4, 1])
    candidate = add_cols[0].text_input("추가할 종목", value=search, key=f"ade_order_add_{market}", label_visibility="collapsed")
    if add_cols[1].button("+ 추가", use_container_width=True, key=f"ade_add_order_{market}") and candidate.strip():
        _add_order_candidate(market, candidate.strip(), candidate.strip())
        st.rerun()
    candidates = _load_order_candidates().get(market, [])
    st.markdown("#### 주문 후보")
    for item in candidates:
        if st.button(f"{item['symbol']} · {item['ticker']}", use_container_width=True, key=f"open_order_candidate_{market}_{item['ticker']}"):
            st.session_state.ade_order_ticker = item["ticker"]
            st.rerun()
    st.markdown("#### 보유종목")
    st.caption("한국투자 계좌 연동 시 실제 보유종목이 표시됩니다.")
    for symbol in (["삼성전자", "SK하이닉스", "한화에어로스페이스"] if market == "kr" else ["NVDA", "AAPL", "MSFT"]):
        if st.button(symbol, use_container_width=True, key=f"holding_{market}_{symbol}"):
            st.session_state.ade_order_ticker = symbol
            st.rerun()
    if st.session_state.ade_order_ticker:
        st.divider()
        _render_order_ticket(market, str(st.session_state.ade_order_ticker))


def _render_order_ticket(market: str, ticker: str) -> None:
    st.markdown(f"### {ticker} 주문서")
    c1, c2 = st.columns([1.25, 1.6])
    with c1:
        st.markdown("#### 실시간 호가")
        _render_orderbook()
    with c2:
        st.markdown("#### 주문 입력")
        side = st.segmented_control("구분", ["매수", "매도"], default="매수", key=f"order_side_{market}_{ticker}")
        account = st.segmented_control("결제", ["현금", "신용"], default="현금", key=f"order_cash_{market}_{ticker}")
        st.segmented_control("시장", ["SOR", "KRX", "NXT"] if market == "kr" else ["NASDAQ", "NYSE", "ARCA"], default="SOR" if market == "kr" else "NASDAQ", key=f"order_venue_{market}_{ticker}")
        order_type = st.selectbox("주문유형", ["지정가", "시장가", "조건부", "최유리", "최우선"], key=f"order_type_{market}_{ticker}")
        price = st.number_input("주문가격", min_value=0.0, value=78200.0, step=100.0 if market == "kr" else .01, key=f"order_price_{market}_{ticker}")
        qty = st.number_input("주문수량", min_value=0, value=0, step=1, key=f"order_qty_{market}_{ticker}")
        st.caption(f"예상 주문금액: {price * qty:,.0f}")
        with st.expander("AI 참고정보", expanded=True):
            st.metric("상승확률", "78%")
            st.metric("기대수익", "+8.4%")
            st.metric("예상 최대낙폭", "-4.2%")
            st.metric("권장 보유기간", "7일")
        with st.expander("AI 추천주문", expanded=True):
            st.write("추천매수가: 77,800")
            st.write("추천수량: 12주")
            st.write("추천비중: 총자산의 3%")
            st.button("AI 추천 적용", use_container_width=True, key=f"apply_ai_order_{market}_{ticker}")
        st.button(f"{account} {order_type} {side} 주문", type="primary", use_container_width=True, key=f"submit_order_{market}_{ticker}")


def _render_orderbook() -> None:
    asks = [(78500, 110234), (78400, 98123), (78300, 76345)]
    bids = [(78100, 120234), (78000, 130456), (77900, 110234)]
    html = ['<div class="ade-orderbook"><div class="head">매도잔량</div><div class="head">호가</div><div class="head">매수잔량</div>']
    for price, volume in asks:
        html += [f'<div class="ask">{volume:,}</div>', f'<div class="ask mid">{price:,}</div>', '<div class="ask"></div>']
    for price, volume in bids:
        html += ['<div class="bid"></div>', f'<div class="bid mid">{price:,}</div>', f'<div class="bid">{volume:,}</div>']
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


def _render_jp_radar() -> None:
    market = _market_selector("ade_jp_market")
    st.markdown(f"### JP Radar · {'국내' if market == 'kr' else '미국'}")
    ticker = st.text_input("종목 검색", value=str(st.session_state.ade_jp_ticker or ""), key=f"jp_search_{market}")
    st.caption("추천결과의 JP Radar 버튼으로 들어오면 해당 종목이 자동 선택됩니다.")
    st.markdown("#### JP Radar 기본화면")
    c1, c2, c3 = st.columns(3)
    c1.metric("Radar Score", "82")
    c2.metric("대금 강도", "4.8x")
    c3.metric("실시간 등급", "A")
    st.line_chart(pd.DataFrame({"Radar": [41, 45, 52, 58, 63, 70, 74, 82]}))
    st.write(f"선택 종목: **{ticker or '없음'}**")


def _market_selector(key: str) -> str:
    market = st.segmented_control("시장", ["kr", "us"], default=st.session_state.get("ade_market", "kr"), format_func=lambda value: "국내" if value == "kr" else "미국", key=key, label_visibility="collapsed")
    st.session_state.ade_market = market or "kr"
    return str(market or "kr")


def _load_recommendations(market: str) -> tuple[list[dict[str, Any]], Any]:
    profile = get_market_profile(market)
    if not profile.db_path.exists():
        return [], None
    conn = None
    try:
        conn = sqlite3.connect(str(profile.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        context = load_latest_context(conn, profile.code, 25)
        if context is None:
            return [], None
        tickers = [str(row.get("ticker") or "") for row in context.recommendations]
        name_map = build_name_map(conn, profile.code, tickers)
        rows = recommendation_base._enrich_recommendations(context.recommendations, name_map, profile.code)
        return rows, context
    except Exception:
        return [], None
    finally:
        if conn is not None:
            conn.close()


def _load_order_candidates() -> dict[str, list[dict[str, str]]]:
    if not ORDER_CANDIDATES_PATH.exists():
        return {"kr": [], "us": []}
    try:
        payload = json.loads(ORDER_CANDIDATES_PATH.read_text(encoding="utf-8"))
        return {"kr": list(payload.get("kr") or []), "us": list(payload.get("us") or [])}
    except Exception:
        return {"kr": [], "us": []}


def _add_order_candidate(market: str, ticker: str, symbol: str) -> None:
    payload = _load_order_candidates()
    market_rows = payload.setdefault(market, [])
    if not any(str(row.get("ticker")) == str(ticker) for row in market_rows):
        market_rows.append({"ticker": str(ticker), "symbol": str(symbol), "added_at": datetime.now().isoformat(timespec="seconds")})
    ORDER_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORDER_CANDIDATES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _render_status_bar() -> None:
    st.markdown(
        '<div class="ade-statusbar">'
        '<span>AI <b class="ade-ok">● 정상</b></span>'
        '<span>DB <b class="ade-ok">● 정상</b></span>'
        '<span>KIS <b class="ade-ok">● 연결</b></span>'
        '<span>Yahoo <b class="ade-ok">● 연결</b></span>'
        f'<span>Sync {datetime.now().strftime("%H:%M:%S")}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run()
