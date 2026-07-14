from __future__ import annotations

import argparse

from jp_radar.live_chart import make_live_radar_chart
from jp_radar.live_engine import JPRadarLiveEngine
from jp_radar.sectors import SECTORS
from jp_radar.stock_engine import JPStockRadarEngine, normalize_ticker


PERIODS = {
    "3개월": 92,
    "6개월": 183,
    "1년": 365,
    "3년": 1095,
    "전체": 3650,
}
MARKET_CODES = ("kospi50", "kosdaq50", "nasdaq30")
SECTOR_CODES = ("ship", "bio")


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="JP Radar Live", page_icon="📡", layout="wide")
    _style(st)

    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">JP RADAR · 3 LEVEL ANALYSIS</div>
            <h1>시장 → 업종 → 종목 3단계 레이더</h1>
            <p>동일한 JP Radar 규칙으로 시장, 업종, 개별 종목을 순서대로 분석합니다.</p>
          </div>
          <div class="badge"><span></span> LIVE MONITOR</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    level = st.radio(
        "분석 단계",
        ["1단계 · 시장", "2단계 · 업종", "3단계 · 종목"],
        horizontal=True,
    )

    c1, c2, c3, c4, c5 = st.columns([1.45, 0.85, 0.95, 1.05, 1.1])
    ticker = ""
    if level.startswith("1단계"):
        target_code = c1.selectbox(
            "시장",
            MARKET_CODES,
            format_func=lambda code: SECTORS[code].name,
        )
        target_label = SECTORS[target_code].name
    elif level.startswith("2단계"):
        target_code = c1.selectbox(
            "업종",
            SECTOR_CODES,
            format_func=lambda code: SECTORS[code].name,
        )
        target_label = SECTORS[target_code].name
    else:
        ticker = c1.text_input(
            "종목코드",
            value=st.session_state.get("jp_stock_ticker", "005930"),
            placeholder="예: 005930, 005930.KS, AAPL, NVDA",
        )
        target_code = "stock"
        target_label = normalize_ticker(ticker) if ticker.strip() else "종목"

    interval = c2.selectbox("자동 갱신", [30, 60, 120, 300], index=1, format_func=lambda x: f"{x}초")
    period_label = c3.selectbox("표시 기간", list(PERIODS), index=2)
    mobile_view = c4.toggle("모바일 보기", value=False)
    force = c5.button("지금 새로고침", type="primary", use_container_width=True)

    if level.startswith("3단계"):
        st.caption("국내 6자리 코드는 기본적으로 KOSPI(.KS)로 해석합니다. KOSDAQ은 247540.KQ처럼 접미사를 입력하세요.")

    def render() -> None:
        try:
            with st.spinner(f"{target_label} JP Radar 계산 중..."):
                if level.startswith("3단계"):
                    if not ticker.strip():
                        st.info("종목코드를 입력하세요.")
                        return
                    st.session_state["jp_stock_ticker"] = ticker.strip()
                    result = JPStockRadarEngine().analyze(
                        ticker,
                        intraday_period="5d",
                        intraday_interval="5m",
                    )
                else:
                    result = JPRadarLiveEngine().analyze(
                        sector_code=target_code,
                        refresh_history=False,
                        intraday_period="5d",
                        intraday_interval="5m",
                    )
        except Exception as exc:
            st.error(f"JP Radar 분석 실패: {exc}")
            return

        radar = result.radar
        yearly = radar.yearly
        signal_class = _signal_class(radar.combined_signal)
        change_class = "up" if result.change_rate >= 0 else "down"
        level_name = level.split(" · ", 1)[-1]

        st.markdown(
            f"""
            <div class="stage-strip">
              <div><span>LEVEL</span><strong>{level_name}</strong></div>
              <div><span>TARGET</span><strong>{radar.sector.name}</strong></div>
              <div><span>SYMBOL</span><strong>{radar.sector.benchmark}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="metric-grid primary-grid">
              <div class="metric-card signal-card {signal_class}">
                <span>종합 판단</span><strong>{radar.combined_signal}</strong><small>{level_name} 상태</small>
              </div>
              <div class="metric-card">
                <span>실시간 가격</span><strong>{result.latest_price:,.2f}</strong><small class="{change_class}">{result.change_rate:+.2f}%</small>
              </div>
              <div class="metric-card">
                <span>일봉 에너지</span><strong>{radar.daily.latest_energy:.2f}</strong><small>{radar.daily.signal_grade}</small>
              </div>
              <div class="metric-card">
                <span>주봉 에너지</span><strong>{radar.weekly.latest_energy:.2f}</strong><small>{radar.weekly.signal_grade}</small>
              </div>
              <div class="metric-card">
                <span>연봉 의미 점수</span><strong>{radar.yearly_score:+.1f}</strong><small>{yearly.state}</small>
              </div>
              <div class="metric-card">
                <span>갱신 시각</span><strong>{result.updated_at.split('T')[-1]}</strong><small>{result.source}</small>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        close_text = f"{yearly.close:,.2f}" if yearly.show_close_line else "미표시"
        candle_text = "양봉" if yearly.bullish else "음봉"
        st.markdown(
            f"""
            <div class="metric-grid secondary-grid">
              <div class="metric-card compact"><span>현재가</span><strong>{yearly.current:,.2f}</strong><small>{radar.sector.name}</small></div>
              <div class="metric-card compact"><span>연봉 시가</span><strong>{yearly.open:,.2f}</strong><small>{yearly.year}년</small></div>
              <div class="metric-card compact"><span>연봉 종가</span><strong>{close_text}</strong><small>{candle_text}</small></div>
              <div class="metric-card compact"><span>연봉 상태</span><strong>{yearly.state}</strong><small>현재 위치</small></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="chart-header">
              <div>
                <span>JP RADAR CHART</span>
                <h3>{radar.sector.name} · 일봉/주봉 에너지 + 실시간 가격 + 연봉 의미선</h3>
              </div>
              <div class="period-pill">{period_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        chart = make_live_radar_chart(
            result,
            mobile=mobile_view,
            period_days=PERIODS[period_label],
        )
        st.plotly_chart(
            chart,
            use_container_width=True,
            config={
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            },
        )

        left, right = st.columns([1.35, 1])
        with left:
            st.markdown("### JP Radar 해석")
            st.info(_interpret(result, level_name))
        with right:
            if level.startswith("3단계"):
                st.markdown("### 분석 대상")
                st.dataframe(
                    [{"ticker": radar.sector.benchmark, "weight_pct": 100.0}],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                with st.expander("시가총액 가중치", expanded=False):
                    rows = sorted(radar.weights.items(), key=lambda x: x[1], reverse=True)
                    st.dataframe(
                        [{"ticker": code, "weight_pct": round(weight * 100, 2)} for code, weight in rows],
                        use_container_width=True,
                        hide_index=True,
                    )

    if force:
        st.session_state["jp_live_force"] = st.session_state.get("jp_live_force", 0) + 1

    if hasattr(st, "fragment"):
        @st.fragment(run_every=f"{int(interval)}s")
        def live_fragment() -> None:
            render()
        live_fragment()
    else:
        render()
        st.caption("현재 Streamlit 버전은 자동 갱신을 지원하지 않아 페이지 새로고침으로 갱신됩니다.")


def _signal_class(signal: str) -> str:
    normalized = signal.upper()
    if "BUY" in normalized:
        return "buy"
    if "SELL" in normalized:
        return "sell"
    return "neutral"


def _interpret(result: object, level_name: str) -> str:
    radar = result.radar
    intraday = result.change_rate
    daily = radar.daily.latest_energy
    weekly = radar.weekly.latest_energy
    yearly = radar.yearly
    yearly_text = (
        f"연봉 의미선 기준 현재 위치는 {yearly.state}이며, "
        f"{yearly.year}년 연봉은 {'양봉' if yearly.bullish else '음봉'}입니다."
    )
    prefix = f"{level_name} 분석 결과, "
    if radar.combined_signal in {"STRONG BUY", "BUY"} and intraday >= 0:
        return prefix + "일봉·주봉 에너지와 장중 흐름이 함께 개선되고 있습니다. " + yearly_text
    if radar.combined_signal in {"STRONG SELL", "SELL"} and intraday <= 0:
        return prefix + "에너지 약화와 장중 하락이 동시에 나타납니다. " + yearly_text
    if daily <= 2.5 and weekly > 2.5:
        return prefix + "단기 과매도 구간이지만 주봉 추세는 아직 완전히 꺾이지 않았습니다. " + yearly_text
    if daily >= 8 and weekly >= 8:
        return prefix + "일봉과 주봉 모두 과열권입니다. " + yearly_text
    return prefix + "일봉과 주봉 신호가 혼재합니다. " + yearly_text


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:#091018;color:#f4f7fb}
        .block-container{max-width:1760px;padding-top:.85rem;padding-bottom:1.5rem}
        .hero{display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border:1px solid #263648;border-radius:20px;background:linear-gradient(135deg,#111a24,#0c131c);box-shadow:0 16px 42px rgba(0,0,0,.28);margin-bottom:12px}
        .compact-hero h1{margin:3px 0;font-size:31px;letter-spacing:-.04em}.compact-hero p{margin:4px 0;color:#91a5b9}
        .eyebrow{font-size:11px;font-weight:800;letter-spacing:.15em;color:#4fc3f7}
        .badge{padding:9px 14px;border-radius:999px;background:#102a1d;color:#42d392;font-weight:800;font-size:13px}.badge span{display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px;box-shadow:0 0 11px #22c55e}
        .stage-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}.stage-strip div{padding:10px 14px;border-radius:12px;background:#101923;border:1px solid #263648}.stage-strip span{display:block;font-size:10px;color:#7890a7}.stage-strip strong{font-size:15px;color:#eaf2f9}
        .metric-grid{display:grid;gap:10px;margin:10px 0}.primary-grid{grid-template-columns:repeat(6,minmax(0,1fr))}.secondary-grid{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:8px}
        .metric-card{min-height:104px;padding:15px 16px;border-radius:15px;background:linear-gradient(180deg,#111a24,#0d151e);border:1px solid #263648;box-shadow:0 8px 22px rgba(0,0,0,.18);display:flex;flex-direction:column;justify-content:center}
        .metric-card span{font-size:12px;color:#8fa4b9}.metric-card strong{font-size:25px;line-height:1.15;margin:7px 0;color:#f3f7fb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.metric-card small{font-size:11px;color:#48d991;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .metric-card.compact{min-height:82px;padding:12px 15px}.metric-card.compact strong{font-size:20px;margin:5px 0}.signal-card.sell{background:linear-gradient(145deg,#8d2027,#45151a);border-color:#c13a45}.signal-card.buy{background:linear-gradient(145deg,#0c7048,#103d2c);border-color:#1ead72}.signal-card.neutral{background:linear-gradient(145deg,#364150,#1d2630)}
        .signal-card strong{font-size:23px}.up{color:#41df91!important}.down{color:#ff6b78!important}.chart-header{display:flex;justify-content:space-between;align-items:center;margin:14px 0 5px;padding:0 4px}.chart-header span{font-size:10px;letter-spacing:.14em;color:#68c8ff;font-weight:800}.chart-header h3{margin:3px 0;font-size:17px;color:#eaf1f8}.period-pill{padding:7px 11px;border-radius:999px;background:#15283a;border:1px solid #2f4c67;color:#9ed8ff;font-size:12px;font-weight:800}
        div[data-testid="stPlotlyChart"]{border:1px solid #263648;border-radius:16px;overflow:hidden;background:#0b1118;box-shadow:0 12px 30px rgba(0,0,0,.22)}
        @media(max-width:1100px){.primary-grid{grid-template-columns:repeat(3,1fr)}.secondary-grid{grid-template-columns:repeat(2,1fr)}}
        @media(max-width:768px){.block-container{padding:.5rem .4rem 1rem;max-width:100%}.hero{display:block;padding:15px;border-radius:17px}.compact-hero h1{font-size:22px;line-height:1.2}.compact-hero p{font-size:12px;line-height:1.4}.badge{display:inline-block;margin-top:9px}.stage-strip{grid-template-columns:1fr}.primary-grid,.secondary-grid{grid-template-columns:repeat(2,1fr);gap:7px}.metric-card{min-height:82px;padding:10px 11px;border-radius:12px}.metric-card strong{font-size:18px}.signal-card strong{font-size:17px}.metric-card span{font-size:10px}.metric-card small{font-size:9px}.metric-card.compact{min-height:72px;padding:9px 10px}.metric-card.compact strong{font-size:16px}.chart-header{align-items:flex-end}.chart-header h3{font-size:13px;max-width:260px}.period-pill{font-size:10px;padding:5px 8px}div[data-testid="stPlotlyChart"]{margin-left:-3px;margin-right:-3px;border-radius:12px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="JP Radar live dashboard")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
