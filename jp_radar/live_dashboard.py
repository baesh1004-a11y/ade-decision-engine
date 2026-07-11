from __future__ import annotations

import argparse

from jp_radar.live_chart import make_live_radar_chart
from jp_radar.live_engine import JPRadarLiveEngine
from jp_radar.sectors import SECTORS


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="JP Radar Live", page_icon="📡", layout="wide")
    _style(st)

    st.markdown(
        """
        <div class="hero">
          <div>
            <div class="eyebrow">JP RADAR · LIVE MARKET CONTROL</div>
            <h1>시장·업종 에너지 실시간 레이더</h1>
            <p>일봉·주봉 에너지와 실시간 지수·MACD를 한 화면에서 확인합니다.</p>
          </div>
          <div class="badge"><span></span> LIVE MONITOR</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 2])
    sector_code = c1.selectbox("시장·업종", sorted(SECTORS), format_func=lambda code: SECTORS[code].name)
    interval = c2.selectbox("자동 갱신", [30, 60, 120, 300], index=1, format_func=lambda x: f"{x}초")
    refresh_history = c3.checkbox("일봉·주봉 재수집", value=False)
    force = c4.button("지금 새로고침", type="primary")

    def render() -> None:
        with st.spinner("JP Radar 실시간 계산 중..."):
            result = JPRadarLiveEngine().analyze(
                sector_code=sector_code,
                refresh_history=refresh_history,
                intraday_period="5d",
                intraday_interval="5m",
            )

        radar = result.radar
        a, b, c, d, e = st.columns(5)
        a.metric("종합 판단", radar.combined_signal)
        b.metric("실시간 지수", f"{result.latest_price:,.2f}", f"{result.change_rate:+.2f}%")
        c.metric("일봉 에너지", f"{radar.daily.latest_energy:.2f}", radar.daily.signal_grade)
        d.metric("주봉 에너지", f"{radar.weekly.latest_energy:.2f}", radar.weekly.signal_grade)
        e.metric("갱신 시각", result.updated_at.split("T")[-1], result.source)

        st.plotly_chart(make_live_radar_chart(result), use_container_width=True)

        st.markdown("### JP Radar 해석")
        st.info(_interpret(result))

        with st.expander("시가총액 가중치"):
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


def _interpret(result: object) -> str:
    radar = result.radar
    intraday = result.change_rate
    daily = radar.daily.latest_energy
    weekly = radar.weekly.latest_energy

    if radar.combined_signal in {"STRONG BUY", "BUY"} and intraday >= 0:
        return "일봉·주봉 에너지와 장중 흐름이 함께 개선되고 있습니다. 신규 매수 검토 구간입니다."
    if radar.combined_signal in {"STRONG SELL", "SELL"} and intraday <= 0:
        return "에너지 약화와 장중 하락이 동시에 나타납니다. 신규 매수는 보류하고 보유 비중을 점검할 구간입니다."
    if daily <= 2.5 and weekly > 2.5:
        return "단기 과매도 구간이지만 주봉 추세는 아직 완전히 꺾이지 않았습니다. 반등 확인 후 접근하는 편이 안전합니다."
    if daily >= 8 and weekly >= 8:
        return "일봉과 주봉 모두 과열권입니다. 추격매수보다 이익실현과 변동성 확대에 유의해야 합니다."
    return "일봉과 주봉 신호가 혼재합니다. 실시간 MACD와 장중 등락률을 함께 확인하며 관망하는 구간입니다."


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:#0b0f14;color:#f5f7fb}
        .block-container{max-width:1760px;padding-top:1.2rem}
        .hero{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border:1px solid #243244;border-radius:24px;background:linear-gradient(135deg,#101720,#0d1219);box-shadow:0 18px 50px rgba(0,0,0,.35);margin-bottom:14px}
        .hero h1{margin:3px 0;font-size:34px;letter-spacing:-.04em}.hero p{margin:5px 0;color:#8fa3b8}
        .eyebrow{font-size:12px;font-weight:800;letter-spacing:.16em;color:#4fc3f7}
        .badge{padding:10px 15px;border-radius:999px;background:#102a1d;color:#42d392;font-weight:800}.badge span{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:6px;box-shadow:0 0 12px #22c55e}
        @media (max-width: 768px){.block-container{padding:.8rem}.hero{display:block;padding:18px}.hero h1{font-size:26px}.badge{display:inline-block;margin-top:12px}}
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
