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
.stApp { background: #f7f9fc; color: var(--ade-ink); }
.block-container { max-width: 1480px; padding-top: 0.7rem; padding-bottom: 5rem; }
[data-testid="stHeader"] { background: rgba(247,249,252,.94); }
.ade-shell { background: white; border: 1px solid var(--ade-line); border-radius: 22px; box-shadow: 0 12px 34px rgba(29,53,87,.08); }
.ade-brand { font-size: 1.35rem; font-weight: 900; letter-spacing: -.04em; }
.ade-subtle { color: var(--ade-muted); font-size: .86rem; }
.ade-section-title { font-size: 1.06rem; font-weight: 850; margin: .2rem 0 .8rem; }
.ade-divider { border-top: 1px solid var(--ade-line); margin: .8rem 0; }
.ade-statusbar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 999; background: rgba(255,255,255,.96); border-top: 1px solid var(--ade-line); padding: .55rem 1.2rem; display:flex; gap:1rem; justify-content:center; font-size:.82rem; backdrop-filter: blur(12px); }
.ade-ok { color: var(--ade-green); font-weight: 800; }
.ade-warn { color: #cc8b12; font-weight: 800; }
.ade-row { border:1px solid var(--ade-line); background:white; border-radius:16px; padding:14px 16px; margin-bottom:10px; }
.ade-rank { font-weight:900; color:var(--ade-blue); }
.ade-symbol { font-size:1.02rem; font-weight:850; }
.ade-code { color:var(--ade-muted); font-size:.78rem; }
.ade-price-up { color:var(--ade-red); font-weight:800; }
.ade-price-down { color:#2267d9; font-weight:800; }
.ade-panel { background:white; border:1px solid var(--ade-line); border-radius:18px; padding:18px; }
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
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide")
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
        [
            ["방산", 2.35], ["조선", 1.87], ["반도체", 1.24], ["은행", .45],
            ["2차전지", -.12], ["바이오", -.35], ["자동차", -.62], ["인터넷", -.81],
        ], columns=["섹터", "등락률"]
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
    st.dataframe(
        pd.DataFrame([
            ["삼성전자", "₩25,450,000", "+2.35%"],
            ["SK하이닉스", "₩18,720,000", "+1.12%"],
            ["현대차", "₩11,280,000", "-0.35%"],
            ["한화에어로스페이스", "₩7,950,000", "+4.21%"],
            ["NAVER", "₩6,850,000", "-1.05%"],
        ], columns=["종목", "평가금액", "수익률"]),
        hide_index=True, use_container_width=True,
    )


def _render_recommendations() -> None:
    market = _market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        _render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return

    recommendations, context = _load_recommendations(market)
    st.markdown(f"### {'국내' if market == 'kr' else '미국'} 추천종목")
    st.caption("순위별 추천종목입니다. 종목명은 상세화면, JP Radar와 주문 버튼은 각 기능으로 바로 연결됩니다.")
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
    recommendations, context = _load_recommendations(market)
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
    except Exception as exc:  # UI must stay available even when source data is incomplete.
        st.info(f"현재 차트를 불러오지 못했습니다: {exc}")


def _render_detail_blocks(selected: dict[str, Any], payload: dict[str, Any]) -> None:
    fields = {
        "추천 이벤트 정보": ["recent_event_date", "recent_money_ratio", "market", "ticker", "symbol"],
        "가장 유사한 과거 사례": ["matched_event_id", "matched_event_date", "equivalent_week_index", "weeks_compared", "future_weeks_available"],
        "유사도 상세": ["weekly_similarity", "sto_similarity", "final_similarity"],
        "과거 사례의 실제 성과": ["matched_max_return", "matched_max_drawdown"],
        "기간별 전망": ["horizons", "seven_day_up_probability", "seven_day_expected_return", "seven_day_median_return"],
        "주문 판단용 예상치": ["expected_max_return_7d", "expected_max_return_20d", "expected_mdd_7d", "expected_peak_day", "holding_days", "target_return", "stop_return", "grade"],
        "최종 시스템 판단": ["decision"],
        "계산 과정 및 근거": ["reasons"],
        "유사 사례 Top N 전체 비교": ["replay_matches"],
    }
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    merged = {**payload, **prediction, **selected}
    for title, keys in fields.items():
        st.markdown(f"#### {title}")
        rows = []
        for key in keys:
            value = merged.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (dict, list)):
                st.json(value, expanded=False)
            else:
                rows.append([_label(key), value])
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=["항목", "값"]), hide_index=True, use_container_width=True)


def _render_orders() -> None:
    market = _market_selector("ade_order_market")
    if st.session_state.ade_order_ticker:
        _render_order_ticket(market, st.session_state.ade_order_ticker)
        return

    st.markdown(f"### {'국내' if market == 'kr' else '미국'} 주문")
    query = st.text_input("종목명 또는 종목코드 검색", placeholder="예: 삼성전자, 005930, NVDA")
    add_cols = st.columns([4, 1])
    with add_cols[0]:
        symbol_name = st.text_input("표시 이름", value=query, label_visibility="collapsed", key=f"order_symbol_name_{market}")
    if add_cols[1].button("+ 추가", use_container_width=True):
        ticker = query.strip().upper()
        if ticker:
            _add_order_candidate(market, ticker, symbol_name.strip() or ticker)
            st.rerun()

    candidates = _load_order_candidates().get(market, [])
    st.markdown("#### 주문 후보")
    if not candidates:
        st.info("주문 후보가 없습니다. 추천결과에서 주문을 누르거나 종목검색으로 추가하세요.")
    for item in candidates:
        c1, c2, c3 = st.columns([3.5, 1.2, .9])
        c1.markdown(f"**{item['symbol']}**  \n`{item['ticker']}`")
        c2.caption(f"추가 {item.get('added_at', '-')}")
        if c3.button("주문서", key=f"open_order_candidate_{market}_{item['ticker']}", type="primary", use_container_width=True):
            st.session_state.ade_order_ticker = item["ticker"]
            st.rerun()
        st.divider()

    st.markdown("#### 보유종목")
    holdings = _demo_holdings(market)
    for item in holdings:
        c1, c2, c3 = st.columns([3.2, 1.4, 1])
        c1.markdown(f"**{item['symbol']}**  \n`{item['ticker']}`")
        c2.metric("평가손익", item["pnl"])
        if c3.button("매수/매도", key=f"open_holding_{market}_{item['ticker']}", use_container_width=True):
            st.session_state.ade_order_ticker = item["ticker"]
            st.rerun()
        st.divider()


def _render_order_ticket(market: str, ticker: str) -> None:
    if st.button("← 주문목록으로 돌아가기"):
        st.session_state.ade_order_ticker = None
        st.rerun()
    symbol = _candidate_symbol(market, ticker)
    st.markdown(f"## {symbol}")
    st.caption(f"{ticker} · 주문서")
    top = st.columns([2, 1, 1, 1])
    top[0].metric("현재가", "78,200", "+1.56%")
    top[1].metric("고가", "78,500")
    top[2].metric("저가", "76,800")
    top[3].metric("거래량", "14,532,123")

    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("### 실시간 호가")
        _render_orderbook()
    with right:
        st.markdown("### 주문 입력")
        side = st.segmented_control("매매", ["매수", "매도"], default="매수", label_visibility="collapsed")
        cash_type = st.segmented_control("거래 구분", ["현금", "신용"], default="현금", label_visibility="collapsed")
        route = st.segmented_control("시장 경로", ["SOR", "KRX", "NXT"] if market == "kr" else ["NASDAQ", "NYSE", "ARCA"], default="SOR" if market == "kr" else "NASDAQ", label_visibility="collapsed")
        order_type = st.selectbox("주문 유형", ["지정가", "시장가", "조건부지정가", "최유리", "최우선"])
        price = st.number_input("주문가격", min_value=0.0, value=78200.0, step=100.0)
        quantity = st.number_input("주문수량", min_value=0, value=0, step=1)
        st.caption(f"예상 주문금액: {price * quantity:,.0f}")

        with st.expander("AI 참고정보", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("상승확률", "82%")
            c2.metric("기대수익", "+11.4%")
            c3.metric("최대낙폭", "-3.2%")
            d1, d2, d3 = st.columns(3)
            d1.metric("권장보유", "8일")
            d2.metric("목표가", "87,500")
            d3.metric("손절가", "74,900")

        with st.expander("AI 추천주문", expanded=False):
            st.write("추천매수가 77,800 · 추천수량 15주 · 추천비중 3%")
            if st.button("AI 추천 적용", use_container_width=True):
                st.info("프로토타입에서는 표시만 제공합니다. 실제 주문 연결 시 입력값에 반영됩니다.")

        button_label = f"{cash_type} {side} 주문"
        if st.button(button_label, type="primary", use_container_width=True):
            st.success("주문 요청을 접수했습니다. 실제 브로커 제출은 기존 주문 엔진 연결 시 활성화됩니다.")


def _render_orderbook() -> None:
    asks = [("85,234", "78,600", "110,234"), ("69,123", "78,500", "130,456"), ("102,456", "78,400", "98,123"), ("120,345", "78,300", "76,345")]
    bids = [("95,678", "78,200", "65,432"), ("108,212", "78,100", "82,443"), ("134,551", "78,000", "99,182"), ("88,219", "77,900", "105,340")]
    html = ['<div class="ade-orderbook">', '<div class="head">매도잔량</div><div class="head">호가</div><div class="head">매수잔량</div>']
    for left, price, right in asks:
        html.append(f'<div class="bid">{left}</div><div class="ask">{price}</div><div class="ask">{right}</div>')
    for index, (left, price, right) in enumerate(bids):
        cls = "mid" if index == 0 else ""
        html.append(f'<div class="bid">{left}</div><div class="bid {cls}">{price}</div><div class="ask">{right}</div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _render_jp_radar() -> None:
    market = _market_selector("ade_jp_market")
    st.markdown(f"### JP Radar · {'국내' if market == 'kr' else '미국'}")
    ticker = st.text_input("종목 검색", value=st.session_state.ade_jp_ticker or "", placeholder="종목명 또는 종목코드")
    if ticker:
        st.session_state.ade_jp_ticker = ticker.strip().upper()
        st.markdown(f"#### {st.session_state.ade_jp_ticker} JP Radar")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("추세", "상승")
        c2.metric("모멘텀", "76")
        c3.metric("변동성", "중간")
        c4.metric("종합", "B+")
        st.info("JP Radar의 기존 분석 엔진을 이 기본화면에 연결하는 구조입니다.")
    else:
        st.info("종목을 검색하거나 추천목록의 JP Radar 버튼으로 진입하세요.")


def _market_selector(key: str) -> str:
    market = st.segmented_control(
        "시장",
        options=["kr", "us"],
        default=st.session_state.ade_market,
        format_func=lambda value: "국내" if value == "kr" else "미국",
        key=key,
        label_visibility="collapsed",
    )
    st.session_state.ade_market = str(market or "kr")
    return st.session_state.ade_market


def _load_recommendations(market: str) -> tuple[list[dict[str, Any]], Any | None]:
    profile = get_market_profile(market)
    if not profile.db_path.exists():
        return [], None
    try:
        conn = sqlite3.connect(str(profile.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        context = load_latest_context(conn, profile.code, 25)
        if context is None:
            return [], None
        tickers = [str(row.get("ticker") or "") for row in context.recommendations]
        name_map = build_name_map(conn, profile.code, tickers)
        enriched = recommendation_base._enrich_recommendations(context.recommendations, name_map, profile.code)
        return [dict(item) for item in enriched], context
    except Exception:
        return [], None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _safe_json(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _load_order_candidates() -> dict[str, list[dict[str, str]]]:
    if not ORDER_CANDIDATES_PATH.exists():
        return {"kr": [], "us": []}
    try:
        payload = json.loads(ORDER_CANDIDATES_PATH.read_text(encoding="utf-8"))
        return {"kr": list(payload.get("kr", [])), "us": list(payload.get("us", []))}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {"kr": [], "us": []}


def _save_order_candidates(payload: dict[str, list[dict[str, str]]]) -> None:
    ORDER_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ORDER_CANDIDATES_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(ORDER_CANDIDATES_PATH)


def _add_order_candidate(market: str, ticker: str, symbol: str) -> None:
    payload = _load_order_candidates()
    existing = {str(item.get("ticker")) for item in payload[market]}
    if ticker not in existing:
        payload[market].append({"ticker": ticker, "symbol": symbol, "added_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        _save_order_candidates(payload)


def _candidate_symbol(market: str, ticker: str) -> str:
    for item in _load_order_candidates().get(market, []):
        if str(item.get("ticker")) == ticker:
            return str(item.get("symbol") or ticker)
    return ticker


def _demo_holdings(market: str) -> list[dict[str, str]]:
    if market == "kr":
        return [
            {"ticker": "000660", "symbol": "SK하이닉스", "pnl": "+12.8%"},
            {"ticker": "012450", "symbol": "한화에어로스페이스", "pnl": "+21.4%"},
            {"ticker": "373220", "symbol": "LG에너지솔루션", "pnl": "-3.1%"},
        ]
    return [
        {"ticker": "NVDA", "symbol": "NVIDIA", "pnl": "+18.2%"},
        {"ticker": "MSFT", "symbol": "Microsoft", "pnl": "+7.6%"},
        {"ticker": "TSLA", "symbol": "Tesla", "pnl": "-4.2%"},
    ]


def _render_status_bar() -> None:
    st.markdown(
        '<div class="ade-statusbar">'
        '<span>AI <b class="ade-ok">● 정상</b></span>'
        '<span>DB <b class="ade-ok">● 정상</b></span>'
        '<span>KIS <b class="ade-ok">● 연결</b></span>'
        '<span>Yahoo <b class="ade-ok">● 연결</b></span>'
        f'<span>Sync <b>{datetime.now().strftime("%H:%M:%S")}</b></span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _label(key: str) -> str:
    labels = {
        "recent_event_date": "최근 대금 이벤트일",
        "recent_money_ratio": "최근 120일 대비 거래대금 비율",
        "market": "시장",
        "ticker": "종목코드",
        "symbol": "종목명",
        "matched_event_id": "유사 사례 ID",
        "matched_event_date": "유사 사례 날짜",
        "equivalent_week_index": "현재 대응 주차",
        "weeks_compared": "비교 기간(주)",
        "future_weeks_available": "이후 확인 가능 기간(주)",
        "weekly_similarity": "주봉 흐름 유사도",
        "sto_similarity": "STO 구조 유사도",
        "final_similarity": "종합 유사도",
        "matched_max_return": "과거 사례 최대수익",
        "matched_max_drawdown": "과거 사례 최대낙폭",
        "seven_day_up_probability": "7거래일 상승확률",
        "seven_day_expected_return": "7거래일 기대수익률",
        "seven_day_median_return": "7거래일 중앙값 수익률",
        "expected_max_return_7d": "7거래일 예상 최대수익",
        "expected_max_return_20d": "20거래일 예상 최대수익",
        "expected_mdd_7d": "7거래일 예상 최대낙폭",
        "expected_peak_day": "예상 최고점 도달일",
        "holding_days": "권장 보유기간",
        "target_return": "목표수익률",
        "stop_return": "참고 손절폭",
        "grade": "전망 등급",
        "decision": "최종 시스템 판단",
    }
    return labels.get(key, key)


if __name__ == "__main__":
    run()
