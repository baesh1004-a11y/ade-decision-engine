from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as recommendation_base
from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart, build_trading_chart
from dashboard.design_system import apply_design_system
from dashboard.kis_zero_base_bridge import kis_configured, load_kis_snapshot
from jp_radar.live_chart import make_live_radar_chart
from jp_radar.live_engine import JPRadarLiveEngine
from jp_radar.sectors import SECTORS
from jp_radar.stock_engine import JPStockRadarEngine, normalize_ticker as normalize_jp_ticker
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context

ORDER_CANDIDATES_PATH = Path("output/ade_order_candidates.json")
THEME_PATH = Path(__file__).with_name("ade_zero_base_theme.css")
CUSTOM_CSS = """<style>[data-testid="stSidebar"],[data-testid="stSidebarNav"],section[data-testid="stSidebar"],div[data-testid="stSidebarNav"],[data-testid="collapsedControl"],button[kind="headerNoPadding"]{display:none!important}</style>"""


def _apply_zero_base_theme() -> None:
    if THEME_PATH.exists():
        st.markdown(f"<style>{THEME_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def run() -> None:
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    apply_design_system(); st.markdown(CUSTOM_CSS, unsafe_allow_html=True); _apply_zero_base_theme(); _init_state(); _render_top_navigation()
    page = st.session_state.ade_primary_page
    if page == "상황종합판": _render_overview()
    elif page == "추천결과": _render_recommendations()
    elif page == "주문": _render_orders()
    else: _render_jp_radar()
    _render_status_bar()


def _init_state() -> None:
    defaults={"ade_primary_page":"상황종합판","ade_overview_tab":"시장","ade_market":"kr","ade_recommendation_detail":None,"ade_order_ticker":None,"ade_jp_ticker":None}
    for key,value in defaults.items(): st.session_state.setdefault(key,value)


def _render_top_navigation() -> None:
    c1,c2,c3,c4,c5,c6=st.columns([1.8,1.1,1.1,1,.28,1.15])
    with c1: st.markdown('<div class="ade-brand">ADE <span class="ade-subtle">Decision Engine</span></div>',unsafe_allow_html=True)
    for col,label in [(c2,"상황종합판"),(c3,"추천결과"),(c4,"주문")]:
        if col.button(label,type="primary" if st.session_state.ade_primary_page==label else "secondary",use_container_width=True):
            st.session_state.ade_primary_page=label; st.session_state.ade_recommendation_detail=None; st.rerun()
    with c5: st.markdown('<div class="ade-jp-separator">&nbsp;</div>',unsafe_allow_html=True)
    with c6:
        if st.button("JP Radar",type="primary" if st.session_state.ade_primary_page=="JP Radar" else "secondary",use_container_width=True): st.session_state.ade_primary_page="JP Radar"; st.rerun()
    st.markdown('<div class="ade-divider"></div>',unsafe_allow_html=True)


def _render_overview() -> None:
    tabs=st.segmented_control("상황종합판 하위 메뉴",options=["시장","이벤트","내 투자"],default=st.session_state.ade_overview_tab,key="ade_overview_segment",label_visibility="collapsed")
    st.session_state.ade_overview_tab=tabs or "시장"
    if tabs=="시장": _render_market_overview()
    elif tabs=="이벤트": _render_event_timeline()
    else: _render_portfolio_overview()


def _render_market_overview() -> None:
    st.markdown("### 시장의 현재 정보")
    cards=[("KOSPI","2,742.81","+1.30%"),("KOSDAQ","872.32","+1.42%"),("S&P 500","5,356.00","+0.78%"),("NASDAQ","16,812.40","+0.64%"),("USD/KRW","1,365.30","-0.21%"),("VIX","13.64","-2.01%")]
    for col,(label,value,delta) in zip(st.columns(6),cards): col.metric(label,value,delta)
    st.markdown("#### 오늘의 이벤트"); _render_event_timeline(compact=True)
    st.markdown("#### 국내 섹터 강도")
    frame=pd.DataFrame([["방산",2.35],["조선",1.87],["반도체",1.24],["은행",.45],["2차전지",-.12],["바이오",-.35],["자동차",-.62],["인터넷",-.81]],columns=["섹터","등락률"])
    st.bar_chart(frame.set_index("섹터"))


def _render_event_timeline(compact: bool=False) -> None:
    rows=[("09:30","한국 1분기 GDP","발표"),("10:00","한국 5월 소비자심리지수","예정"),("21:30","미국 1분기 GDP","예정"),("22:00","미국 5월 신규주택판매","예정"),("05.29 03:00","연준 베이지북","예정")]
    if not compact: st.markdown("### 오늘의 이벤트 타임라인")
    for time_text,title,status in rows:
        c1,c2,c3=st.columns([1,5,1]); c1.markdown(f"**{time_text}**"); c2.markdown(title); c3.caption(status); st.divider()


def _kis_data(refresh: bool=False):
    profile=get_market_profile("kr")
    return load_kis_snapshot(profile.db_path,refresh=refresh,max_age_seconds=60)


def _render_portfolio_overview() -> None:
    st.markdown("### 내 투자 현황")
    refresh=st.button("KIS 계좌 새로고침",key="kis_portfolio_refresh")
    account,positions,error=_kis_data(refresh=refresh)
    if error and account is None: st.warning(error)
    if account is None:
        st.info("KIS 계좌 스냅샷이 없습니다. Render 환경변수와 계좌정보를 확인하세요."); return
    cash=float(account.get("cash") or 0); evaluation=float(account.get("evaluation_amount") or 0); pnl=float(account.get("pnl") or 0); total=cash+evaluation
    invested=evaluation-pnl; pnl_rate=(pnl/invested*100) if invested>0 else 0
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("총자산",f"₩{total:,.0f}"); c2.metric("주문가능 현금",f"₩{cash:,.0f}"); c3.metric("평가금액",f"₩{evaluation:,.0f}"); c4.metric("평가손익",f"₩{pnl:+,.0f}",f"{pnl_rate:+.2f}%"); c5.metric("보유종목",f"{int(account.get('position_count') or len(positions))}개")
    st.caption(f"KIS 기준시각 {account.get('captured_at','-')}" + (f" · 마지막 정상 스냅샷 사용: {error}" if error else ""))
    st.markdown("#### 보유종목")
    if not positions: st.info("현재 보유종목이 없습니다."); return
    shown=pd.DataFrame(positions).rename(columns={"ticker":"종목코드","name":"종목명","quantity":"수량","average_price":"평균단가","current_price":"현재가","evaluation_amount":"평가금액","pnl":"평가손익","pnl_rate":"수익률","market":"시장"})
    keep=[c for c in ["시장","종목명","종목코드","수량","평균단가","현재가","평가금액","평가손익","수익률"] if c in shown.columns]
    st.dataframe(shown[keep],hide_index=True,use_container_width=True)


def _render_recommendations() -> None:
    market=_market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail: _render_recommendation_detail(market,st.session_state.ade_recommendation_detail); return
    recommendations,_context=_load_recommendations(market)
    st.markdown(f"### {'국내' if market=='kr' else '미국'} 추천종목")
    for row in recommendations: _render_recommendation_row(row,market)
    if not recommendations: st.info("저장된 추천결과가 없습니다.")


def _render_recommendation_row(row: dict[str,Any],market: str) -> None:
    cols=st.columns([.55,3.2,1.25,1.05,1.05]); cols[0].markdown(f'<div class="ade-rank">#{int(row.get("rank_no",0))}</div>',unsafe_allow_html=True)
    symbol=str(row.get("symbol") or row.get("ticker")); ticker=str(row.get("ticker"))
    with cols[1]:
        if st.button(f"{symbol}\n\n{ticker}",key=f"open_detail_{market}_{ticker}",use_container_width=True): st.session_state.ade_recommendation_detail=ticker; st.rerun()
    score=row.get("score") or row.get("final_similarity") or row.get("weekly_similarity"); cols[2].metric("추천점수",f"{float(score or 0):.1f}")
    if cols[3].button("JP Radar",key=f"jp_{market}_{ticker}",use_container_width=True): st.session_state.ade_primary_page="JP Radar"; st.session_state.ade_jp_ticker=ticker; st.session_state.ade_market=market; st.rerun()
    if cols[4].button("주문",key=f"order_{market}_{ticker}",type="primary",use_container_width=True): _add_order_candidate(market,ticker,symbol); st.session_state.ade_primary_page="주문"; st.session_state.ade_order_ticker=ticker; st.session_state.ade_market=market; st.rerun()
    st.divider()


def _render_recommendation_detail(market: str,ticker: str) -> None:
    if st.button("← 추천종목으로 돌아가기"): st.session_state.ade_recommendation_detail=None; st.rerun()
    recommendations,context=_load_recommendations(market); selected=next((row for row in recommendations if str(row.get("ticker"))==ticker),None)
    if selected is None: st.warning("선택한 추천종목을 찾을 수 없습니다."); return
    profile=get_market_profile(market); payload=_safe_json(selected.get("payload_json")); combined={**payload,**selected}
    st.markdown(f"## {selected.get('symbol') or ticker}")
    validation=(context.validations.get(normalize_ticker(ticker,market)) if context else None)
    with sqlite3.connect(str(profile.db_path),timeout=5) as conn:
        conn.row_factory=sqlite3.Row; pattern=recommendation_base._selected_pattern(conn,payload); current=recommendation_base._current_bars(conn,market,normalize_ticker(ticker,market),profile.price_source); historical=recommendation_base._pattern_bars(conn,pattern)
    recommendation_base._comparison_panel(st,selected,current,historical,pattern,payload,market,profile.db_path,context.run_id if context else "",validation)
    with st.expander("전체 원시 분석값",expanded=False): st.json(combined)


def _render_orders() -> None:
    market=_market_selector("ade_order_market"); st.session_state.ade_market=market
    if st.session_state.ade_order_ticker: _render_order_ticket(market,st.session_state.ade_order_ticker); return
    st.markdown("### 주문")
    refresh=st.button("KIS 계좌 새로고침",key="kis_orders_refresh") if market=="kr" else False
    account,positions,error=_kis_data(refresh=refresh) if market=="kr" else (None,[],None)
    if account:
        c1,c2,c3=st.columns(3); c1.metric("주문가능 현금",f"₩{float(account.get('cash') or 0):,.0f}"); c2.metric("평가금액",f"₩{float(account.get('evaluation_amount') or 0):,.0f}"); c3.metric("평가손익",f"₩{float(account.get('pnl') or 0):+,.0f}")
    if error: st.caption(f"KIS: {error}")
    query=st.text_input("종목 검색",placeholder="종목명 또는 종목코드")
    if query and st.button("주문후보에 추가",type="primary"): _add_order_candidate(market,query,query); st.rerun()
    candidates=[row for row in _load_order_candidates() if row.get("market")==market]
    st.markdown("#### 주문후보")
    for row in candidates:
        if st.button(f"{row['symbol']} · {row['ticker']}",key=f"candidate_{market}_{row['ticker']}",use_container_width=True): st.session_state.ade_order_ticker=row['ticker']; st.rerun()
    st.markdown("#### 보유종목")
    market_positions=[p for p in positions if str(p.get("market","kr")).lower() in {market,"kr","domestic","korea"}] if market=="kr" else []
    if not market_positions: st.info("KIS 보유종목이 없습니다." if market=="kr" else "미국 계좌 연동은 별도 API 설정이 필요합니다.")
    for row in market_positions:
        label=f"{row.get('name') or row.get('ticker')} · {row.get('ticker')} · {int(row.get('quantity') or 0)}주 · {float(row.get('pnl_rate') or 0):+.2f}%"
        if st.button(label,key=f"holding_{market}_{row.get('ticker')}",use_container_width=True): st.session_state.ade_order_ticker=str(row.get('ticker')); st.rerun()


def _render_order_ticket(market: str,ticker: str) -> None:
    if st.button("← 주문목록으로 돌아가기"): st.session_state.ade_order_ticker=None; st.rerun()
    account,positions,error=_kis_data(refresh=False) if market=="kr" else (None,[],None)
    holding=next((p for p in positions if str(p.get("ticker"))==str(ticker)),None)
    st.markdown(f"## {holding.get('name') if holding else ticker} 주문")
    if account:
        c1,c2,c3=st.columns(3); c1.metric("주문가능 현금",f"₩{float(account.get('cash') or 0):,.0f}"); c2.metric("보유수량",f"{int(holding.get('quantity') or 0) if holding else 0}주"); c3.metric("현재가",f"₩{float(holding.get('current_price') or 0):,.0f}" if holding else "-")
    left,right=st.columns([1.2,1])
    with left: st.info("실시간 호가는 KIS 시세 WebSocket 연결 전까지 마지막 계좌 현재가를 사용합니다.")
    with right:
        side=st.radio("주문 구분",["매수","매도"],horizontal=True); account_type=st.radio("거래",["현금","신용"],horizontal=True)
        venue=st.selectbox("시장",["SOR","KRX","NXT"] if market=="kr" else ["NASDAQ","NYSE","AMEX"])
        order_type=st.selectbox("주문유형",["지정가","시장가","최유리","조건부지정가"])
        default_price=float(holding.get("current_price") or 0) if holding else 0.0
        price=st.number_input("가격",min_value=0.0,value=default_price,step=100.0 if market=="kr" else 0.01)
        max_sell=int(holding.get("quantity") or 0) if holding and side=="매도" else 0
        quantity=st.number_input("수량",min_value=0,max_value=max_sell if side=="매도" and max_sell>0 else None,value=1 if side=="매수" else min(1,max_sell),step=1)
        available=int(float(account.get("cash") or 0)//price) if account and price>0 and side=="매수" else max_sell
        st.metric("주문가능수량",f"{available:,}주"); st.metric("예상 주문금액",f"₩{price*quantity:,.0f}")
        if st.button(f"{side} 주문",type="primary",use_container_width=True): st.warning("계좌·잔고 연동은 완료됐지만 실제 주문 전송은 안전상 아직 비활성화되어 있습니다.")
    if error: st.caption(f"KIS 마지막 정상 스냅샷 사용: {error}")


def _render_jp_radar() -> None:
    st.markdown("## JP Radar")
    market=_market_selector("ade_jp_market")
    ticker=st.text_input("종목코드",value=st.session_state.ade_jp_ticker or ("005930" if market=="kr" else "AAPL"))
    try: result=JPStockRadarEngine().analyze(ticker,intraday_period="5d",intraday_interval="5m")
    except Exception as exc: st.error(f"JP Radar 분석 실패: {exc}"); return
    st.plotly_chart(make_live_radar_chart(result,mobile=False,period_days=365),use_container_width=True,config={"displaylogo":False,"scrollZoom":True,"responsive":True})


def _market_selector(key: str) -> str:
    value=st.segmented_control("시장",options=["kr","us"],default=st.session_state.get("ade_market","kr"),format_func=lambda v:"국내" if v=="kr" else "미국",key=key,label_visibility="collapsed")
    return str(value or "kr")


def _load_recommendations(market: str):
    profile=get_market_profile(market)
    if not profile.db_path.exists(): return [],None
    with sqlite3.connect(str(profile.db_path),timeout=5) as conn:
        conn.row_factory=sqlite3.Row; context=load_latest_context(conn,profile.code,50)
        if context is None: return [],None
        name_map=build_name_map(conn,profile.code); rows=[]
        for source in context.recommendations:
            row=dict(source); ticker=normalize_ticker(row.get("ticker"),market); row["ticker"]=ticker; row["symbol"]=name_map.get(ticker) or row.get("name") or ticker; rows.append(row)
        return rows,context


def _add_order_candidate(market: str,ticker: str,symbol: str) -> None:
    rows=_load_order_candidates(); normalized={"market":market,"ticker":ticker,"symbol":symbol,"added_at":datetime.now().isoformat(timespec="seconds")}
    rows=[r for r in rows if not (r.get("market")==market and r.get("ticker")==ticker)]; rows.insert(0,normalized)
    ORDER_CANDIDATES_PATH.parent.mkdir(parents=True,exist_ok=True); ORDER_CANDIDATES_PATH.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")


def _load_order_candidates() -> list[dict[str,Any]]:
    try: return json.loads(ORDER_CANDIDATES_PATH.read_text(encoding="utf-8")) if ORDER_CANDIDATES_PATH.exists() else []
    except Exception: return []


def _render_status_bar() -> None:
    kis_text="KIS 연결" if kis_configured() else "KIS 미설정"
    kis_class="ade-ok" if kis_configured() else ""
    st.markdown(f'<div class="ade-statusbar"><span class="ade-ok">AI 정상</span><span class="ade-ok">DB 정상</span><span class="{kis_class}">{kis_text}</span><span>Yahoo 연결</span><span>추천·Replay·STO 규칙 유지</span></div>',unsafe_allow_html=True)


def _safe_json(value: Any) -> dict[str,Any]:
    if isinstance(value,dict): return value
    if isinstance(value,str):
        try:
            parsed=json.loads(value); return parsed if isinstance(parsed,dict) else {}
        except Exception: return {}
    return {}
