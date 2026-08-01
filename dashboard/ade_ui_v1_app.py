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
from jp_radar.live_chart import make_live_radar_chart
from jp_radar.live_engine import JPRadarLiveEngine
from jp_radar.sectors import SECTORS
from jp_radar.stock_engine import JPStockRadarEngine, normalize_ticker as normalize_jp_ticker
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context


ORDER_CANDIDATES_PATH = Path("output/ade_order_candidates.json")


CUSTOM_CSS = """
<style>
:root{--ade-blue:#2f67d8;--ade-red:#e5484d;--ade-green:#18a36f;--ade-ink:#172033;--ade-muted:#6b7484;--ade-line:#e7eaf0;--ade-panel:#fff;}
[data-testid="stSidebar"],[data-testid="stSidebarNav"],section[data-testid="stSidebar"],div[data-testid="stSidebarNav"],[data-testid="collapsedControl"],button[kind="headerNoPadding"]{display:none!important}
[data-testid="stAppViewContainer"]>.main,[data-testid="stAppViewBlockContainer"],.main .block-container{margin-left:0!important;max-width:1480px!important;padding-left:2rem!important;padding-right:2rem!important}
.stApp{background:#f7f9fc;color:var(--ade-ink)}.block-container{max-width:1480px;padding-top:.7rem;padding-bottom:5rem}[data-testid="stHeader"]{background:rgba(247,249,252,.94)}
.ade-brand{font-size:1.35rem;font-weight:900;letter-spacing:-.04em}.ade-subtle{color:var(--ade-muted);font-size:.86rem}.ade-divider{border-top:1px solid var(--ade-line);margin:.8rem 0}
.ade-statusbar{position:fixed;left:0;right:0;bottom:0;z-index:999;background:rgba(255,255,255,.96);border-top:1px solid var(--ade-line);padding:.55rem 1.2rem;display:flex;gap:1rem;justify-content:center;font-size:.82rem;backdrop-filter:blur(12px)}
.ade-ok{color:var(--ade-green);font-weight:800}.ade-rank{font-weight:900;color:var(--ade-blue)}.ade-jp-separator{border-left:1px solid #d4d9e2;margin-left:1.4rem;padding-left:1.4rem}
.ade-hero{padding:20px 22px;border:1px solid var(--ade-line);border-radius:20px;background:linear-gradient(135deg,#fff,#f4f7ff);box-shadow:0 12px 30px rgba(38,61,94,.08);margin-bottom:16px}
.ade-hero h2{margin:0 0 6px;font-size:27px}.ade-hero p{margin:0;color:var(--ade-muted)}
.ade-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}.ade-card{background:#fff;border:1px solid var(--ade-line);border-radius:16px;padding:15px 16px;box-shadow:0 8px 22px rgba(34,56,86,.05)}
.ade-card span{display:block;color:var(--ade-muted);font-size:12px}.ade-card strong{display:block;margin-top:6px;font-size:21px}.ade-card small{display:block;margin-top:4px;color:var(--ade-muted)}
.ade-section{margin-top:20px}.ade-section h3{margin-bottom:6px}.ade-explain{color:var(--ade-muted);font-size:.9rem;margin-bottom:10px}.ade-badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#edf3ff;color:#2f67d8;font-weight:800;font-size:12px}
.ade-orderbook{display:grid;grid-template-columns:1fr 1fr 1fr;border:1px solid var(--ade-line);border-radius:14px;overflow:hidden}.ade-orderbook div{padding:10px 12px;border-bottom:1px solid var(--ade-line);text-align:right}.ade-orderbook .head{color:var(--ade-muted);font-size:.78rem;background:#fafbfe;font-weight:800;text-align:center}.ade-orderbook .ask{background:#fff5f5}.ade-orderbook .bid{background:#f3f7ff}.ade-orderbook .mid{font-weight:900;font-size:1.02rem}
.watch-row{display:grid;grid-template-columns:32px 2.2fr 1fr 1fr 1fr 110px;gap:10px;align-items:center;padding:12px 10px;border-bottom:1px solid var(--ade-line);background:#fff}.watch-row strong{font-size:15px}.watch-row small{display:block;color:var(--ade-muted)}.up{color:#e5484d;font-weight:800}.down{color:#2267d9;font-weight:800}.muted{color:var(--ade-muted)}
.ticket-head{display:flex;justify-content:space-between;align-items:flex-end;padding:8px 0 16px}.ticket-head h2{margin:0;font-size:28px}.ticket-head .price{font-size:31px;font-weight:900}.ticket-tabs{display:flex;gap:18px;border-bottom:1px solid var(--ade-line);margin-bottom:14px}.ticket-tabs span{padding:10px 0;font-weight:800}.ticket-tabs .active{color:var(--ade-red);border-bottom:3px solid var(--ade-red)}
</style>
"""


def run() -> None:
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    apply_design_system(); st.markdown(CUSTOM_CSS, unsafe_allow_html=True); _init_state(); _render_top_navigation()
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


def _render_portfolio_overview() -> None:
    st.markdown("### 내 투자 현황")
    c1,c2,c3,c4=st.columns(4); c1.metric("총 자산","₩128,540,000","+₩1,250,000"); c2.metric("누적 수익률","+18.56%"); c3.metric("현금 비중","23.4%"); c4.metric("국내 / 미국","63.2% / 36.8%")
    st.markdown("#### 보유종목 TOP 5")
    st.dataframe(pd.DataFrame([["삼성전자","₩25,450,000","+2.35%"],["SK하이닉스","₩18,720,000","+1.12%"],["현대차","₩11,280,000","-0.35%"],["한화에어로스페이스","₩7,950,000","+4.21%"],["NAVER","₩6,850,000","-1.05%"]],columns=["종목","평가금액","수익률"]),hide_index=True,use_container_width=True)


def _render_recommendations() -> None:
    market=_market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail: _render_recommendation_detail(market,st.session_state.ade_recommendation_detail); return
    recommendations,_context=_load_recommendations(market)
    st.markdown(f"### {'국내' if market=='kr' else '미국'} 추천종목")
    st.caption("추천 순위는 기존 주봉 유사도 규칙을 그대로 사용합니다. 상세 화면에서 차트, 과거 유사 사례, 전망, 위험, 주문 참고값을 모두 확인할 수 있습니다.")
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
    st.markdown(f'<div class="ade-hero"><span class="ade-badge">추천 상세 분석</span><h2>{selected.get("symbol") or ticker}</h2><p>{ticker} · 현재 차트, 과거 유사 사례, 확률 전망, 위험 및 주문 참고값</p></div>',unsafe_allow_html=True)
    _render_professional_summary(combined)
    validation=(context.validations.get(normalize_ticker(ticker,market)) if context else None)
    with sqlite3.connect(str(profile.db_path),timeout=5) as conn:
        conn.row_factory=sqlite3.Row; pattern=recommendation_base._selected_pattern(conn,payload); current=recommendation_base._current_bars(conn,market,normalize_ticker(ticker,market),profile.price_source); historical=recommendation_base._pattern_bars(conn,pattern)
    recommendation_base._comparison_panel(st,selected,current,historical,pattern,payload,market,profile.db_path,context.run_id if context else "",validation)
    _render_prediction_horizons(combined); _render_matched_case(combined); _render_replay_cases(combined); _render_risk_and_order_reference(combined); _render_reasoning(combined)
    with st.expander("전체 원시 분석값",expanded=False): _render_raw_payload(combined)


def _render_professional_summary(data: dict[str,Any]) -> None:
    decision=data.get("decision") or data.get("system_decision") or "미정"; weekly=_num(data.get("weekly_similarity")); sto=_num(data.get("sto_similarity")); final=_num(data.get("final_similarity")); grade=data.get("grade") or "-"
    cards=[("시스템 판단",str(decision),f"등급 {grade}"),("주봉 유사도",_pct(weekly),"추천 순위의 핵심 기준"),("STO 구조 유사도",_pct(sto),"구조 통과 여부 확인"),("최종 유사도",_pct(final),"종합 비교 결과")]
    st.markdown('<div class="ade-grid">'+''.join(f'<div class="ade-card"><span>{a}</span><strong>{b}</strong><small>{c}</small></div>' for a,b,c in cards)+'</div>',unsafe_allow_html=True)


def _render_prediction_horizons(data: dict[str,Any]) -> None:
    st.markdown("### 기간별 전망")
    rows=[]; probs=data.get("up_probabilities") or {}; returns=data.get("returns_by_day") or {}; medians=data.get("median_returns") or {}
    for day in [3,5,7,10,20]: rows.append({"기간":f"{day}일","상승확률":_pct(_first_number(probs.get(str(day)),probs.get(day),data.get(f"up_probability_{day}d"))),"기대수익률":_pct(_first_number(returns.get(str(day)),returns.get(day),data.get(f"expected_return_{day}d"))),"중앙값 수익률":_pct(_first_number(medians.get(str(day)),medians.get(day),data.get(f"median_return_{day}d")))})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)


def _render_matched_case(data: dict[str,Any]) -> None:
    st.markdown("### 가장 유사한 과거 사례")
    labels={"matched_name":"종목명","matched_ticker":"종목코드","matched_event_date":"이벤트 날짜","matched_event_id":"이벤트 ID","equivalent_week_index":"동일 주차","weeks_compared":"비교 주수","future_weeks_available":"향후 관측 주수","matched_max_return":"실현 최대수익률","matched_max_drawdown":"실현 최대낙폭"}
    rows=[]
    for key,label in labels.items():
        value=data.get(key)
        if value not in (None,"",[],{}): rows.append({"항목":label,"값":_format_value(key,value)})
    if rows: st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    else: st.caption("매칭된 과거 사례 정보가 없습니다.")


def _render_replay_cases(data: dict[str,Any]) -> None:
    st.markdown("### 유사 사례 Top N")
    matches=data.get("replay_matches")
    if not isinstance(matches,list) or not matches: st.caption("저장된 유사 사례 목록이 없습니다."); return
    rows=[]
    for index,item in enumerate(matches[:20],start=1):
        row=dict(item) if isinstance(item,dict) else {"사례":item}
        rows.append({"순위":index,"종목":row.get("name") or row.get("matched_name") or row.get("ticker") or row.get("matched_ticker") or "-","이벤트":row.get("event_date") or row.get("matched_event_date") or "-","주봉 유사도":_pct(_first_number(row.get("weekly_similarity"),row.get("similarity"))),"STO 유사도":_pct(_num(row.get("sto_similarity"))),"최대수익률":_pct(_first_number(row.get("max_return"),row.get("matched_max_return"))),"최대낙폭":_pct(_first_number(row.get("max_drawdown"),row.get("matched_max_drawdown")))})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)


def _render_risk_and_order_reference(data: dict[str,Any]) -> None:
    st.markdown("### 위험 및 주문 참고값")
    values=[("7일 상승확률",_pct(_first_number(data.get("seven_day_up_probability"),data.get("up_probability_7d")))),("7일 기대수익",_pct(_first_number(data.get("seven_day_expected_return"),data.get("expected_return_7d")))),("7일 기대 최대수익",_pct(data.get("expected_max_return_7d"))),("20일 기대 최대수익",_pct(data.get("expected_max_return_20d"))),("예상 최대낙폭",_pct(_first_number(data.get("expected_max_drawdown_7d"),data.get("expected_max_drawdown")))),("예상 고점일",_text(data.get("expected_peak_day"))),("권장 보유기간",_days(data.get("holding_days"))),("목표 / 손절",f"{_pct(data.get('target_return'))} / {_pct(data.get('stop_return'))}")]
    st.markdown('<div class="ade-grid">'+''.join(f'<div class="ade-card"><span>{a}</span><strong>{b}</strong></div>' for a,b in values)+'</div>',unsafe_allow_html=True)


def _render_reasoning(data: dict[str,Any]) -> None:
    st.markdown("### 계산 근거와 해석")
    reasons=data.get("reasons") or data.get("reasoning") or data.get("explanation")
    if isinstance(reasons,list):
        for reason in reasons: st.markdown(f"- {reason}")
    elif isinstance(reasons,dict):
        for key,value in reasons.items(): st.markdown(f"**{key}**: {value}")
    elif reasons: st.write(reasons)
    else: st.caption("저장된 계산 근거가 없습니다.")
    structure=data.get("current_sto_structure")
    if structure not in (None,"",[],{}): st.markdown("#### 현재 STO 배열"); st.json(structure if isinstance(structure,(dict,list)) else {"structure":structure},expanded=False)


def _render_raw_payload(data: dict[str,Any]) -> None:
    rows=[]
    for key in sorted(data):
        value=data[key]
        if value in (None,"",[],{}): continue
        rows.append({"필드":key,"값":json.dumps(value,ensure_ascii=False,indent=2) if isinstance(value,(dict,list)) else value})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)


def _render_orders() -> None:
    market=_market_selector("ade_order_market"); st.session_state.ade_market=market
    if st.session_state.ade_order_ticker: _render_order_ticket(market,st.session_state.ade_order_ticker); return
    st.markdown("## 주문 후보 · 보유종목")
    group=st.segmented_control("목록",options=["주문후보","보유종목","최근"],default="주문후보",label_visibility="collapsed")
    c1,c2,c3=st.columns([2.6,1,1]); query=c1.text_input("종목 검색",placeholder="종목명 또는 종목코드",label_visibility="collapsed"); c2.selectbox("정렬",["추천순","등락률순","거래량순","이름순"],label_visibility="collapsed"); c3.button("추가/편집",use_container_width=True)
    if query and st.button("검색 종목을 주문후보에 추가",type="primary"): _add_order_candidate(market,query,query); st.rerun()
    rows=[row for row in _load_order_candidates() if row.get("market")==market]
    if not rows: rows=[{"ticker":"005930" if market=="kr" else "NVDA","symbol":"삼성전자" if market=="kr" else "NVIDIA"},{"ticker":"000660" if market=="kr" else "TSLA","symbol":"SK하이닉스" if market=="kr" else "Tesla"}]
    st.markdown('<div class="watch-row muted"><div></div><div>종목</div><div>현재가</div><div>등락</div><div>거래량</div><div></div></div>',unsafe_allow_html=True)
    for i,row in enumerate(rows):
        ticker=str(row.get("ticker")); symbol=str(row.get("symbol") or ticker); price=100000+i*4370; change=(i%3-1)*2.14; cls="up" if change>0 else "down" if change<0 else "muted"
        st.markdown(f'<div class="watch-row"><div>▮</div><div><strong>{symbol}</strong><small>{ticker} · {"KRX+NXT" if market=="kr" else "NASDAQ"}</small></div><div><strong>{price:,.2f}</strong></div><div class="{cls}">{change:+.2f}%</div><div>{(1250000+i*382000):,}</div><div></div></div>',unsafe_allow_html=True)
        if st.button(f"{symbol} 주문",key=f"candidate_{market}_{ticker}",use_container_width=True): st.session_state.ade_order_ticker=ticker; st.rerun()


def _render_order_ticket(market: str,ticker: str) -> None:
    if st.button("← 주문목록으로 돌아가기"): st.session_state.ade_order_ticker=None; st.rerun()
    current=204000.0 if market=="kr" else 311.21
    st.markdown(f'<div class="ticket-head"><div><h2>{ticker}</h2><span class="muted">{ticker} · {"KRX+NXT" if market=="kr" else "미국주식"}</span></div><div><div class="price up">{current:,.2f}</div><span class="up">▲ 2.36%</span></div></div>',unsafe_allow_html=True)
    st.markdown('<div class="ticket-tabs"><span class="active">매수</span><span>매도</span><span>정정/취소</span><span>체결/예약</span><span>잔고</span></div>',unsafe_allow_html=True)
    left,right=st.columns([1.05,1.25],gap="large")
    with left:
        book_mode=st.segmented_control("호가",options=["호가","체결"],default="호가",label_visibility="collapsed")
        st.caption("상한가 / 하한가, 매도·매수 잔량, 현재가와 체결강도를 함께 표시합니다.")
        rows=[]
        for i in range(5,0,-1): rows.extend([f'<div class="ask">{current+i*500:,.0f}</div>',f'<div class="mid">{120+i*17:,}</div>',f'<div>{(900+i*130):,}</div>'])
        rows.extend(['<div class="head">가격</div>','<div class="head">건수</div>','<div class="head">잔량</div>'])
        for i in range(0,6): rows.extend([f'<div class="bid">{current-i*500:,.0f}</div>',f'<div class="mid">{3+i*41:,}</div>',f'<div>{(350+i*154):,}</div>'])
        st.markdown('<div class="ade-orderbook">'+''.join(rows)+'</div>',unsafe_allow_html=True)
        c1,c2,c3=st.columns(3); c1.metric("총 매도잔량","8,420"); c2.metric("체결강도","112.4%"); c3.metric("총 매수잔량","10,315")
    with right:
        side=st.segmented_control("주문 구분",options=["매수","매도"],default="매수",label_visibility="collapsed")
        cash=st.segmented_control("거래 구분",options=["현금","신용"],default="현금",label_visibility="collapsed")
        venues=["SOR","KRX","NXT"] if market=="kr" else ["NASDAQ","NYSE","AMEX"]; venue=st.segmented_control("시장",options=venues,default=venues[0],label_visibility="collapsed")
        order_type=st.selectbox("주문유형",["지정가","시장가","최유리","조건부지정가","최우선지정가"])
        price=st.number_input("가격",min_value=0.0,value=current,step=500.0 if market=="kr" else .01)
        quantity=st.number_input("수량",min_value=0,value=1,step=1)
        c1,c2=st.columns(2); c1.metric("주문가능수량","128주"); c2.metric("미수가능수량","0주")
        st.markdown("#### AI 주문 참고")
        ai1,ai2,ai3=st.columns(3); ai1.metric("권장 진입가",f"{current*0.992:,.2f}"); ai2.metric("권장 수량",f"{max(1,quantity)}주"); ai3.metric("포트폴리오 비중","3.0%")
        st.caption("추천 엔진의 참고값이며 주문 승인 로직은 변경하지 않습니다.")
        st.metric("예상 주문금액",f"{price*quantity:,.0f}")
        c1,c2=st.columns([1,2]); c1.button("예약주문",use_container_width=True); submit=c2.button(f"{cash} {side}",type="primary",use_container_width=True)
        if submit: st.warning("실제 증권사 주문 전송은 아직 비활성화되어 있습니다.")


def _render_jp_radar() -> None:
    st.markdown("## JP Radar")
    market=_market_selector("ade_jp_market"); default_level="종목" if st.session_state.ade_jp_ticker else "시장"; level=st.radio("분석 단계",["시장","업종","종목"],horizontal=True,index=["시장","업종","종목"].index(default_level))
    target_code=""; ticker=""; target_label=""
    if level=="시장": choices=["kospi50","kosdaq50"] if market=="kr" else ["nasdaq30"]; target_code=st.selectbox("시장",choices,format_func=lambda code:SECTORS[code].name); target_label=SECTORS[target_code].name
    elif level=="업종": target_code=st.selectbox("업종",["ship","bio"],format_func=lambda code:SECTORS[code].name); target_label=SECTORS[target_code].name
    else: ticker=st.text_input("종목코드",value=st.session_state.ade_jp_ticker or ("005930" if market=="kr" else "AAPL")); target_label=normalize_jp_ticker(ticker) if ticker else "종목"
    period_label=st.selectbox("표시 기간",["3개월","6개월","1년","3년","전체"],index=2); periods={"3개월":92,"6개월":183,"1년":365,"3년":1095,"전체":3650}
    try:
        with st.spinner(f"{target_label} JP Radar 계산 중..."): result=JPStockRadarEngine().analyze(ticker,intraday_period="5d",intraday_interval="5m") if level=="종목" else JPRadarLiveEngine().analyze(sector_code=target_code,refresh_history=False,intraday_period="5d",intraday_interval="5m")
    except Exception as exc: st.error(f"JP Radar 분석 실패: {exc}"); return
    radar=result.radar; yearly=radar.yearly
    st.markdown('<div class="ade-grid">'+''.join(f'<div class="ade-card"><span>{a}</span><strong>{b}</strong><small>{c}</small></div>' for a,b,c in [("종합 판단",radar.combined_signal,level),("실시간 가격",f"{result.latest_price:,.2f}",f"{result.change_rate:+.2f}%"),("일봉 에너지",f"{radar.daily.latest_energy:.2f}",radar.daily.signal_grade),("주봉 에너지",f"{radar.weekly.latest_energy:.2f}",radar.weekly.signal_grade),("연봉 의미 점수",f"{radar.yearly_score:+.1f}",yearly.state),("연봉 현재 위치",yearly.state,f"{yearly.year}년"),("연봉 시가",f"{yearly.open:,.2f}","양봉" if yearly.bullish else "음봉"),("데이터 갱신",result.updated_at.split("T")[-1],result.source)])+'</div>',unsafe_allow_html=True)
    st.plotly_chart(make_live_radar_chart(result,mobile=False,period_days=periods[period_label]),use_container_width=True,config={"displaylogo":False,"scrollZoom":True,"responsive":True})
    st.markdown("### 전문 해석"); st.info(_jp_interpretation(result,level))
    if level!="종목":
        with st.expander("구성종목 시가총액 가중치",expanded=False):
            rows=sorted(radar.weights.items(),key=lambda x:x[1],reverse=True); st.dataframe([{"ticker":code,"weight_pct":round(weight*100,2)} for code,weight in rows],use_container_width=True,hide_index=True)


def _jp_interpretation(result: Any,level: str) -> str:
    radar=result.radar; daily=radar.daily.latest_energy; weekly=radar.weekly.latest_energy; yearly=radar.yearly
    if radar.combined_signal in {"STRONG BUY","BUY"} and result.change_rate>=0: tone="일봉·주봉 에너지와 장중 흐름이 동시에 개선되고 있습니다."
    elif radar.combined_signal in {"STRONG SELL","SELL"} and result.change_rate<=0: tone="에너지 약화와 장중 하락이 동시에 나타나고 있습니다."
    elif daily<=2.5 and weekly>2.5: tone="단기 과매도 구간이지만 주봉 추세는 아직 완전히 훼손되지 않았습니다."
    elif daily>=8 and weekly>=8: tone="일봉과 주봉이 모두 과열권이므로 추격 진입보다 변동성 관리가 중요합니다."
    else: tone="일봉과 주봉 신호가 혼재해 방향성 확인이 더 필요합니다."
    return f"{level} 분석 결과, {tone} 연봉 의미선 기준 현재 위치는 {yearly.state}이며 {yearly.year}년 연봉은 {'양봉' if yearly.bullish else '음봉'}입니다."


def _market_selector(key: str) -> str:
    value=st.segmented_control("시장",options=["kr","us"],default=st.session_state.get("ade_market","kr"),format_func=lambda value:"국내" if value=="kr" else "미국",key=key,label_visibility="collapsed"); return str(value or "kr")


def _load_recommendations(market: str) -> tuple[list[dict[str,Any]],Any]:
    profile=get_market_profile(market)
    if not profile.db_path.exists(): return [],None
    with sqlite3.connect(str(profile.db_path),timeout=5) as conn:
        conn.row_factory=sqlite3.Row; context=load_latest_context(conn,profile.code,50)
        if context is None: return [],None
        name_map=build_name_map(conn,profile.code); rows=[]
        for row in context.recommendations:
            item=dict(row); code=normalize_ticker(item.get("ticker"),market); item["ticker"]=code; item["symbol"]=item.get("name") or name_map.get(code) or code; rows.append(item)
        return rows,context


def _load_order_candidates() -> list[dict[str,Any]]:
    if not ORDER_CANDIDATES_PATH.exists(): return []
    try: return json.loads(ORDER_CANDIDATES_PATH.read_text(encoding="utf-8"))
    except Exception: return []


def _add_order_candidate(market: str,ticker: str,symbol: str) -> None:
    rows=_load_order_candidates(); key=(market,str(ticker))
    if not any((row.get("market"),str(row.get("ticker")))==key for row in rows): rows.append({"market":market,"ticker":str(ticker),"symbol":str(symbol),"added_at":datetime.now().isoformat(timespec="seconds")})
    ORDER_CANDIDATES_PATH.parent.mkdir(parents=True,exist_ok=True); ORDER_CANDIDATES_PATH.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")


def _render_status_bar() -> None:
    st.markdown('<div class="ade-statusbar"><span>AI <b class="ade-ok">정상</b></span><span>DB <b class="ade-ok">정상</b></span><span>KIS <b class="ade-ok">연결</b></span><span>Yahoo <b class="ade-ok">연결</b></span></div>',unsafe_allow_html=True)


def _safe_json(value: Any) -> dict[str,Any]:
    if isinstance(value,dict): return value
    if not value: return {}
    try: parsed=json.loads(value); return parsed if isinstance(parsed,dict) else {}
    except Exception: return {}


def _num(value: Any) -> float:
    try: return float(value)
    except Exception: return 0.0


def _first_number(*values: Any) -> float:
    for value in values:
        if value not in (None,""): return _num(value)
    return 0.0


def _pct(value: Any) -> str: return f"{_num(value):.1f}%"
def _text(value: Any) -> str: return "-" if value in (None,"") else str(value)
def _days(value: Any) -> str: return "-" if value in (None,"") else f"{value}일"
def _format_value(key: str,value: Any) -> str: return _pct(value) if "return" in key or "drawdown" in key else str(value)
