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
:root {
  --ade-blue: #2f67d8;
  --ade-red: #e5484d;
  --ade-green: #18a36f;
  --ade-ink: #172033;
  --ade-muted: #6b7484;
  --ade-line: #e7eaf0;
}
[data-testid="stSidebar"], [data-testid="stSidebarNav"], section[data-testid="stSidebar"],
div[data-testid="stSidebarNav"], [data-testid="collapsedControl"], button[kind="headerNoPadding"] {display:none!important;}
[data-testid="stAppViewContainer"]>.main,[data-testid="stAppViewBlockContainer"],.main .block-container{margin-left:0!important;max-width:1480px!important;padding-left:2rem!important;padding-right:2rem!important;}
.stApp{background:#f7f9fc;color:var(--ade-ink)}
.block-container{max-width:1480px;padding-top:.7rem;padding-bottom:5rem}
[data-testid="stHeader"]{background:rgba(247,249,252,.94)}
.ade-brand{font-size:1.35rem;font-weight:900;letter-spacing:-.04em}
.ade-subtle{color:var(--ade-muted);font-size:.86rem}
.ade-divider{border-top:1px solid var(--ade-line);margin:.8rem 0}
.ade-statusbar{position:fixed;left:0;right:0;bottom:0;z-index:999;background:rgba(255,255,255,.96);border-top:1px solid var(--ade-line);padding:.55rem 1.2rem;display:flex;gap:1rem;justify-content:center;font-size:.82rem;backdrop-filter:blur(12px)}
.ade-ok{color:var(--ade-green);font-weight:800}.ade-rank{font-weight:900;color:var(--ade-blue)}
.ade-orderbook{display:grid;grid-template-columns:1fr 1fr 1fr;border:1px solid var(--ade-line);border-radius:14px;overflow:hidden}
.ade-orderbook div{padding:10px 12px;border-bottom:1px solid var(--ade-line);text-align:right}.ade-orderbook .head{color:var(--ade-muted);font-size:.78rem;background:#fafbfe;font-weight:800;text-align:center}.ade-orderbook .ask{background:#fff5f5}.ade-orderbook .bid{background:#f3f7ff}.ade-orderbook .mid{font-weight:900;font-size:1.02rem}.ade-jp-separator{border-left:1px solid #d4d9e2;margin-left:1.4rem;padding-left:1.4rem}
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
    defaults = {"ade_primary_page":"상황종합판","ade_overview_tab":"시장","ade_market":"kr","ade_recommendation_detail":None,"ade_order_ticker":None,"ade_jp_ticker":None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_top_navigation() -> None:
    c1,c2,c3,c4,c5,c6=st.columns([1.8,1.1,1.1,1,.28,1.15])
    with c1:
        st.markdown('<div class="ade-brand">ADE <span class="ade-subtle">Decision Engine</span></div>',unsafe_allow_html=True)
    for col,label in [(c2,"상황종합판"),(c3,"추천결과"),(c4,"주문")]:
        if col.button(label,type="primary" if st.session_state.ade_primary_page==label else "secondary",use_container_width=True):
            st.session_state.ade_primary_page=label;st.session_state.ade_recommendation_detail=None;st.rerun()
    with c5: st.markdown('<div class="ade-jp-separator">&nbsp;</div>',unsafe_allow_html=True)
    with c6:
        if st.button("JP Radar",type="primary" if st.session_state.ade_primary_page=="JP Radar" else "secondary",use_container_width=True):
            st.session_state.ade_primary_page="JP Radar";st.rerun()
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
    st.markdown("#### 오늘의 이벤트");_render_event_timeline(compact=True)
    st.markdown("#### 국내 섹터 강도")
    frame=pd.DataFrame([["방산",2.35],["조선",1.87],["반도체",1.24],["은행",.45],["2차전지",-.12],["바이오",-.35],["자동차",-.62],["인터넷",-.81]],columns=["섹터","등락률"])
    st.bar_chart(frame.set_index("섹터"))


def _render_event_timeline(compact: bool=False) -> None:
    rows=[("09:30","한국 1분기 GDP","발표"),("10:00","한국 5월 소비자심리지수","예정"),("21:30","미국 1분기 GDP","예정"),("22:00","미국 5월 신규주택판매","예정"),("05.29 03:00","연준 베이지북","예정")]
    if not compact: st.markdown("### 오늘의 이벤트 타임라인")
    for time_text,title,status in rows:
        c1,c2,c3=st.columns([1,5,1]);c1.markdown(f"**{time_text}**");c2.markdown(title);c3.caption(status);st.divider()


def _render_portfolio_overview() -> None:
    st.markdown("### 내 투자 현황")
    c1,c2,c3,c4=st.columns(4);c1.metric("총 자산","₩128,540,000","+₩1,250,000");c2.metric("누적 수익률","+18.56%");c3.metric("현금 비중","23.4%");c4.metric("국내 / 미국","63.2% / 36.8%")
    st.markdown("#### 보유종목 TOP 5")
    st.dataframe(pd.DataFrame([["삼성전자","₩25,450,000","+2.35%"],["SK하이닉스","₩18,720,000","+1.12%"],["현대차","₩11,280,000","-0.35%"],["한화에어로스페이스","₩7,950,000","+4.21%"],["NAVER","₩6,850,000","-1.05%"]],columns=["종목","평가금액","수익률"]),hide_index=True,use_container_width=True)


def _render_recommendations() -> None:
    market=_market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        _render_recommendation_detail(market,st.session_state.ade_recommendation_detail);return
    recommendations,_context=_load_recommendations(market)
    st.markdown(f"### {'국내' if market=='kr' else '미국'} 추천종목")
    for row in recommendations: _render_recommendation_row(row,market)
    if not recommendations: st.info("저장된 추천결과가 없습니다.")


def _render_recommendation_row(row: dict[str,Any],market: str) -> None:
    cols=st.columns([.55,3.2,1.25,1.05,1.05]);cols[0].markdown(f'<div class="ade-rank">#{int(row.get("rank_no",0))}</div>',unsafe_allow_html=True)
    symbol=str(row.get("symbol") or row.get("ticker"));ticker=str(row.get("ticker"))
    with cols[1]:
        if st.button(f"{symbol}\n\n{ticker}",key=f"open_detail_{market}_{ticker}",use_container_width=True): st.session_state.ade_recommendation_detail=ticker;st.rerun()
    score=row.get("score") or row.get("final_similarity") or row.get("weekly_similarity");cols[2].metric("추천점수",f"{float(score or 0):.1f}")
    if cols[3].button("JP Radar",key=f"jp_{market}_{ticker}",use_container_width=True): st.session_state.ade_primary_page="JP Radar";st.session_state.ade_jp_ticker=ticker;st.session_state.ade_market=market;st.rerun()
    if cols[4].button("주문",key=f"order_{market}_{ticker}",type="primary",use_container_width=True): _add_order_candidate(market,ticker,symbol);st.session_state.ade_primary_page="주문";st.session_state.ade_order_ticker=ticker;st.session_state.ade_market=market;st.rerun()
    st.divider()


def _render_recommendation_detail(market: str,ticker: str) -> None:
    if st.button("← 추천종목으로 돌아가기"): st.session_state.ade_recommendation_detail=None;st.rerun()
    recommendations,context=_load_recommendations(market);selected=next((row for row in recommendations if str(row.get("ticker"))==ticker),None)
    if selected is None: st.warning("선택한 추천종목을 찾을 수 없습니다.");return
    st.markdown(f"## {selected.get('symbol') or ticker}");st.caption(f"{ticker} · 추천 상세")
    profile=get_market_profile(market);payload=_safe_json(selected.get("payload_json"));validation=(context.validations.get(normalize_ticker(ticker,market)) if context else None)
    with sqlite3.connect(str(profile.db_path),timeout=5) as conn:
        conn.row_factory=sqlite3.Row
        pattern=recommendation_base._selected_pattern(conn,payload)
        current=recommendation_base._current_bars(conn,market,normalize_ticker(ticker,market),profile.price_source)
        historical=recommendation_base._pattern_bars(conn,pattern)
    recommendation_base._comparison_panel(st,selected,current,historical,pattern,payload,market,profile.db_path,context.run_id if context else "",validation)
    st.markdown("### 추천결과 상세")
    _render_detail_blocks(selected,payload)


def _render_detail_blocks(selected: dict[str,Any],payload: dict[str,Any]) -> None:
    combined={**payload,**selected}
    blocks={
        "추천 이벤트 정보":["recent_event_date","recent_money_ratio","market","ticker","symbol"],
        "가장 유사한 과거 사례":["matched_event_id","matched_event_date","matched_ticker","matched_name","equivalent_week_index","weeks_compared","future_weeks_available"],
        "유사도 상세":["weekly_similarity","sto_similarity","final_similarity","current_sto_structure"],
        "과거 사례의 실제 성과":["matched_max_return","matched_max_drawdown"],
        "기간별 전망":["prediction","returns_by_day","up_probabilities","median_returns"],
        "주문 판단용 예상치":["seven_day_up_probability","seven_day_expected_return","expected_max_return_7d","expected_max_return_20d","expected_max_drawdown_7d","expected_peak_day","holding_days","target_return","stop_return","grade"],
        "최종 시스템 판단":["decision"],
        "계산 과정과 근거":["reasons"],
        "유사 사례 Top N":["replay_matches"],
    }
    for title,keys in blocks.items():
        st.markdown(f"#### {title}")
        values=[]
        for key in keys:
            value=combined.get(key)
            if value not in (None,"",[],{}): values.append({"항목":key,"내용":json.dumps(value,ensure_ascii=False,indent=2) if isinstance(value,(dict,list)) else value})
        if values: st.dataframe(pd.DataFrame(values),hide_index=True,use_container_width=True)
        else: st.caption("저장된 값이 없습니다.")


def _render_orders() -> None:
    market=_market_selector("ade_order_market");st.session_state.ade_market=market
    if st.session_state.ade_order_ticker: _render_order_ticket(market,st.session_state.ade_order_ticker);return
    st.markdown("### 주문")
    query=st.text_input("종목 검색",placeholder="종목명 또는 종목코드")
    if query and st.button("주문후보에 추가",type="primary"):
        _add_order_candidate(market,query,query);st.rerun()
    candidates=[row for row in _load_order_candidates() if row.get("market")==market]
    st.markdown("#### 주문후보")
    for row in candidates:
        if st.button(f"{row['symbol']} · {row['ticker']}",key=f"candidate_{market}_{row['ticker']}",use_container_width=True): st.session_state.ade_order_ticker=row['ticker'];st.rerun()
    st.markdown("#### 보유종목")
    st.info("KIS 보유종목 연결 영역")


def _render_order_ticket(market: str,ticker: str) -> None:
    if st.button("← 주문목록으로 돌아가기"): st.session_state.ade_order_ticker=None;st.rerun()
    st.markdown(f"## {ticker} 주문서")
    c1,c2=st.columns([1.1,1])
    with c1: _render_mock_orderbook()
    with c2:
        side=st.segmented_control("매매",["매수","매도"],default="매수")
        st.segmented_control("주문경로",["SOR","KRX","NXT"] if market=="kr" else ["NASDAQ","NYSE","ARCA"],default="SOR" if market=="kr" else "NASDAQ")
        order_type=st.selectbox("주문유형",["지정가","시장가","조건부","최유리","최우선"])
        price=st.number_input("주문가격",min_value=0.0,value=72000.0,step=100.0,disabled=order_type=="시장가")
        quantity=st.number_input("주문수량",min_value=1,value=1,step=1)
        st.metric("예상 주문금액",f"{price*quantity:,.0f}")
        st.markdown("#### AI 참고정보")
        st.dataframe(pd.DataFrame([["상승확률","-"],["기대수익","-"],["예상 최대수익","-"],["예상 최대낙폭","-"],["권장보유기간","-"],["목표가","-"],["손절가","-"]],columns=["항목","값"]),hide_index=True,use_container_width=True)
        st.markdown("#### AI 추천주문")
        st.dataframe(pd.DataFrame([["추천매수가","-"],["추천수량","-"],["추천비중","-"]],columns=["항목","값"]),hide_index=True,use_container_width=True)
        st.button("AI 추천 적용",use_container_width=True)
        st.button(f"{side or '매수'} 주문하기",type="primary",use_container_width=True)


def _render_mock_orderbook() -> None:
    asks=[(72500,1280),(72400,930),(72300,745),(72200,680),(72100,540)];bids=[(72000,820),(71900,960),(71800,1130),(71700,1410),(71600,1750)]
    html='<div class="ade-orderbook"><div class="head">잔량</div><div class="head">호가</div><div class="head">구분</div>'
    for price,qty in asks: html+=f'<div class="ask">{qty:,}</div><div class="ask">{price:,}</div><div class="ask">매도</div>'
    html+='<div></div><div class="mid">72,100</div><div>현재가</div>'
    for price,qty in bids: html+=f'<div class="bid">{qty:,}</div><div class="bid">{price:,}</div><div class="bid">매수</div>'
    st.markdown(html+'</div>',unsafe_allow_html=True)


def _render_jp_radar() -> None:
    st.markdown("### JP Radar")
    level=st.radio("분석 단계",["1단계 · 시장","2단계 · 업종","3단계 · 종목"],horizontal=True,key="ade_jp_level")
    c1,c2,c3,c4=st.columns([1.6,1,1,1])
    ticker=""
    if level.startswith("1단계"):
        target_code=c1.selectbox("시장",["kospi50","kosdaq50","nasdaq30"],format_func=lambda code:SECTORS[code].name,key="ade_jp_market_target");target_label=SECTORS[target_code].name
    elif level.startswith("2단계"):
        target_code=c1.selectbox("업종",["ship","bio"],format_func=lambda code:SECTORS[code].name,key="ade_jp_sector_target");target_label=SECTORS[target_code].name
    else:
        default_ticker=st.session_state.ade_jp_ticker or ("005930" if st.session_state.ade_market=="kr" else "NVDA")
        ticker=c1.text_input("종목코드",value=default_ticker,key="ade_jp_stock_target");target_code="stock";target_label=normalize_jp_ticker(ticker) if ticker.strip() else "종목"
    period_label=c2.selectbox("표시 기간",["3개월","6개월","1년","3년","전체"],index=2,key="ade_jp_period")
    mobile=c3.toggle("모바일 보기",value=False,key="ade_jp_mobile")
    force=c4.button("지금 새로고침",type="primary",use_container_width=True)
    try:
        with st.spinner(f"{target_label} JP Radar 계산 중..."):
            result=JPStockRadarEngine().analyze(ticker,intraday_period="5d",intraday_interval="5m") if level.startswith("3단계") else JPRadarLiveEngine().analyze(sector_code=target_code,refresh_history=bool(force),intraday_period="5d",intraday_interval="5m")
    except Exception as exc:
        st.error(f"JP Radar 분석 실패: {exc}");return
    radar=result.radar;yearly=radar.yearly
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("종합 판단",radar.combined_signal);c2.metric("실시간 가격",f"{result.latest_price:,.2f}",f"{result.change_rate:+.2f}%");c3.metric("일봉 에너지",f"{radar.daily.latest_energy:.2f}",radar.daily.signal_grade);c4.metric("주봉 에너지",f"{radar.weekly.latest_energy:.2f}",radar.weekly.signal_grade);c5.metric("연봉 의미 점수",f"{radar.yearly_score:+.1f}",yearly.state);c6.metric("갱신 시각",result.updated_at.split('T')[-1])
    periods={"3개월":92,"6개월":183,"1년":365,"3년":1095,"전체":3650}
    st.plotly_chart(make_live_radar_chart(result,mobile=mobile,period_days=periods[period_label]),use_container_width=True,config={"displaylogo":False,"scrollZoom":True,"responsive":True,"modeBarButtonsToRemove":["lasso2d","select2d"]})
    left,right=st.columns([1.35,1])
    with left:
        st.markdown("#### JP Radar 해석")
        st.info(_jp_interpret(result,level.split(" · ",1)[-1]))
    with right:
        st.markdown("#### 분석 대상")
        rows=[{"ticker":radar.sector.benchmark,"weight_pct":100.0}] if level.startswith("3단계") else [{"ticker":code,"weight_pct":round(weight*100,2)} for code,weight in sorted(radar.weights.items(),key=lambda x:x[1],reverse=True)]
        st.dataframe(rows,use_container_width=True,hide_index=True)


def _jp_interpret(result: object,level_name: str) -> str:
    radar=result.radar;yearly=radar.yearly;prefix=f"{level_name} 분석 결과, ";yearly_text=f"연봉 의미선 기준 현재 위치는 {yearly.state}이며, {yearly.year}년 연봉은 {'양봉' if yearly.bullish else '음봉'}입니다."
    if radar.combined_signal in {"STRONG BUY","BUY"} and result.change_rate>=0: return prefix+"일봉·주봉 에너지와 장중 흐름이 함께 개선되고 있습니다. "+yearly_text
    if radar.combined_signal in {"STRONG SELL","SELL"} and result.change_rate<=0: return prefix+"에너지 약화와 장중 하락이 동시에 나타납니다. "+yearly_text
    if radar.daily.latest_energy<=2.5 and radar.weekly.latest_energy>2.5: return prefix+"단기 과매도 구간이지만 주봉 추세는 아직 완전히 꺾이지 않았습니다. "+yearly_text
    if radar.daily.latest_energy>=8 and radar.weekly.latest_energy>=8: return prefix+"일봉과 주봉 모두 과열권입니다. "+yearly_text
    return prefix+"일봉과 주봉 신호가 혼재합니다. "+yearly_text


def _market_selector(key: str) -> str:
    market=st.segmented_control("시장",options=["kr","us"],default=st.session_state.ade_market,format_func=lambda value:"🇰🇷 국내" if value=="kr" else "🇺🇸 미국",key=key,label_visibility="collapsed")
    st.session_state.ade_market=str(market or "kr");return st.session_state.ade_market


def _load_recommendations(market: str):
    profile=get_market_profile(market)
    if not profile.db_path.exists(): return [],None
    conn=sqlite3.connect(str(profile.db_path),timeout=5);conn.row_factory=sqlite3.Row
    try:
        context=load_latest_context(conn,profile.code,25)
        if context is None:return [],None
        tickers=[str(row.get("ticker") or "") for row in context.recommendations]
        name_map=build_name_map(conn,profile.code,tickers)
        rows=recommendation_base._enrich_recommendations(context.recommendations,name_map,profile.code)
        return rows,context
    finally: conn.close()


def _load_order_candidates() -> list[dict[str,Any]]:
    if not ORDER_CANDIDATES_PATH.exists(): return []
    try:return json.loads(ORDER_CANDIDATES_PATH.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):return []


def _add_order_candidate(market: str,ticker: str,symbol: str) -> None:
    rows=_load_order_candidates()
    if not any(row.get("market")==market and row.get("ticker")==ticker for row in rows): rows.append({"market":market,"ticker":ticker,"symbol":symbol,"added_at":datetime.now().isoformat(timespec="seconds")})
    ORDER_CANDIDATES_PATH.parent.mkdir(parents=True,exist_ok=True);ORDER_CANDIDATES_PATH.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")


def _safe_json(value: Any) -> dict[str,Any]:
    if isinstance(value,dict):return value
    if not value:return {}
    try:return json.loads(value)
    except (TypeError,json.JSONDecodeError):return {}


def _render_status_bar() -> None:
    st.markdown('<div class="ade-statusbar"><span class="ade-ok">● AI</span><span class="ade-ok">● DB</span><span class="ade-ok">● KIS</span><span class="ade-ok">● Yahoo</span><span>Sync '+datetime.now().strftime('%H:%M:%S')+'</span></div>',unsafe_allow_html=True)


if __name__=="__main__": run()
