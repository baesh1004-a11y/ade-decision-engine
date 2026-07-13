from __future__ import annotations

import argparse

from jp_radar.live_chart import make_live_radar_chart
from jp_radar.live_engine import JPRadarLiveEngine
from jp_radar.sectors import SECTORS


PERIODS = {
    "3개월": 92,
    "6개월": 183,
    "1년": 365,
    "3년": 1095,
    "전체": 3650,
}


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="JP Radar Live", page_icon="📡", layout="wide")
    _style(st)

    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">JP RADAR · LIVE MARKET CONTROL</div>
            <h1>시장·업종 에너지 실시간 레이더</h1>
            <p>핵심 판단과 가격·에너지·MACD를 한 화면에서 빠르게 확인합니다.</p>
          </div>
          <div class="badge"><span></span> LIVE MONITOR</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5, c6 = st.columns([1.35, 0.85, 0.95, 0.95, 1.05, 1.1])
    sector_code = c1.selectbox("시장·업종", sorted(SECTORS), format_func=lambda code: SECTORS[code].name)
    interval = c2.selectbox("자동 갱신", [30, 60, 120, 300], index=1, format_func=lambda x: f"{x}초")
    period_label = c3.selectbox("표시 기간", list(PERIODS), index=2)
    refresh_history = c4.checkbox("일봉·주봉 재수집", value=False)
    mobile_view = c5.toggle("모바일 보기", value=False)
    force = c6.button("지금 새로고침", type="primary", use_container_width=True)

    def render() -> None:
        with st.spinner("JP Radar 실시간 계산 중..."):
            result = JPRadarLiveEngine().analyze(
                sector_code=sector_code,
                refresh_history=refresh_history,
                intraday_period="5d",
                intraday_interval="5m",
            )

        radar = result.radar
        yearly = radar.yearly
        signal_class = _signal_class(radar.combined_signal)
        change_class = "up" if result.change_rate >= 0 else "down"

        st.markdown(
            f"""
            <div class="metric-grid primary-grid">
              <div class="metric-card signal-card {signal_class}">
                <span>종합 판단</span><strong>{radar.combined_signal}</strong><small>현재 시장 상태</small>
              </div>
              <div class="metric-card">
                <span>실시간 지수</span><strong>{result.latest_price:,.2f}</strong><small class="{change_class}">{result.change_rate:+.2f}%</small>
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
                <h3>{radar.sector.name} · 일봉/주봉 에너지 + 실시간 지수 + 연봉 의미선</h3>
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

        st.caption(
            "기본 화면은 핵심선만 표시합니다. 범례를 눌러 보조 에너지선과 신호를 켜거나 끌 수 있습니다."
        )

        left, right = st.columns([1.35, 1])
        with left:
            st.markdown("### JP Radar 해석")
            st.info(_interpret(result))
        with right:
            with st.expander("시가총액 가중치", expanded=False):
                rows = sorted(radar.weights.items(), key=lambda x: x[1], reverse=True)
                st.dataframe(
                    [{"ticker": ticker, "weight_pct": round(weight * 100, 2)} for ticker, weight in rows],
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


def _interpret(result: object) -> str:
    radar = result.radar
    intraday = result.change_rate
    daily = radar.daily.latest_energy
    weekly = radar.weekly.latest_energy
    yearly = radar.yearly

    yearly_text = (
        f"연봉 의미선 기준 현재 위치는 {yearly.state}이며, "
        f"{yearly.year}년 연봉은 {'양봉' if yearly.bullish else '음봉'}입니다."
    )
    if radar.combined_signal in {"STRONG BUY", "BUY"} and intraday >= 0:
        return "일봉·주봉 에너지와 장중 흐름이 함께 개선되고 있습니다. " + yearly_text
    if radar.combined_signal in {"STRONG SELL", "SELL"} and intraday <= 0:
        return "에너지 약화와 장중 하락이 동시에 나타납니다. " + yearly_text
    if daily <= 2.5 and weekly > 2.5:
        return "단기 과매도 구간이지만 주봉 추세는 아직 완전히 꺾이지 않았습니다. " + yearly_text
    if daily >= 8 and weekly >= 8:
        return "일봉과 주봉 모두 과열권입니다. " + yearly_text
    return "일봉과 주봉 신호가 혼재합니다. " + yearly_text


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
        .metric-grid{display:grid;gap:10px;margin:10px 0}
        .primary-grid{grid-template-columns:repeat(6,minmax(0,1fr))}
        .secondary-grid{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:8px}
        .metric-card{min-height:104px;padding:15px 16px;border-radius:15px;background:linear-gradient(180deg,#111a24,#0d151e);border:1px solid #263648;box-shadow:0 8px 22px rgba(0,0,0,.18);display:flex;flex-direction:column;justify-content:center}
        .metric-card span{font-size:12px;color:#8fa4b9}.metric-card strong{font-size:25px;line-height:1.15;margin:7px 0;color:#f3f7fb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.metric-card small{font-size:11px;color:#48d991;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .metric-card.compact{min-height:82px;padding:12px 15px}.metric-card.compact strong{font-size:20px;margin:5px 0}
        .signal-card.sell{background:linear-gradient(145deg,#8d2027,#45151a);border-color:#c13a45}.signal-card.buy{background:linear-gradient(145deg,#0c7048,#103d2c);border-color:#1ead72}.signal-card.neutral{background:linear-gradient(145deg,#364150,#1d2630)}
        .signal-card strong{font-size:23px}.up{color:#41df91!important}.down{color:#ff6b78!important}
        .chart-header{display:flex;justify-content:space-between;align-items:center;margin:14px 0 5px;padding:0 4px}.chart-header span{font-size:10px;letter-spacing:.14em;color:#68c8ff;font-weight:800}.chart-header h3{margin:3px 0;font-size:17px;color:#eaf1f8}.period-pill{padding:7px 11px;border-radius:999px;background:#15283a;border:1px solid #2f4c67;color:#9ed8ff;font-size:12px;font-weight:800}
        div[data-testid="stPlotlyChart"]{border:1px solid #263648;border-radius:16px;overflow:hidden;background:#0b1118;box-shadow:0 12px 30px rgba(0,0,0,.22)}
        @media(max-width:1100px){.primary-grid{grid-template-columns:repeat(3,1fr)}.secondary-grid{grid-template-columns:repeat(2,1fr)}}
        @media(max-width:768px){
          .block-container{padding:.5rem .4rem 1rem;max-width:100%}
          .hero{display:block;padding:15px;border-radius:17px}.compact-hero h1{font-size:22px;line-height:1.2}.compact-hero p{font-size:12px;line-height:1.4}.badge{display:inline-block;margin-top:9px}
          .primary-grid,.secondary-grid{grid-template-columns:repeat(2,1fr);gap:7px}
          .metric-card{min-height:82px;padding:10px 11px;border-radius:12px}.metric-card strong{font-size:18px}.signal-card strong{font-size:17px}.metric-card span{font-size:10px}.metric-card small{font-size:9px}
          .metric-card.compact{min-height:72px;padding:9px 10px}.metric-card.compact strong{font-size:16px}
          .chart-header{align-items:flex-end}.chart-header h3{font-size:13px;max-width:260px}.period-pill{font-size:10px;padding:5px 8px}
          div[data-testid="stPlotlyChart"]{margin-left:-3px;margin-right:-3px;border-radius:12px}
        }
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
