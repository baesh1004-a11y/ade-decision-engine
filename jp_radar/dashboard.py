from __future__ import annotations

import argparse

from jp_radar.chart import make_radar_chart
from jp_radar.engine import JPRadarEngine
from jp_radar.sectors import SECTORS


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="JP Radar", page_icon="📡", layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: linear-gradient(135deg,#07111f 0%,#101827 48%,#07111f 100%); color:#e5eefb; }
        .block-container { max-width: 1600px; padding-top: 1.5rem; }
        .hero { padding:24px 28px; border:1px solid rgba(125,190,255,.25); border-radius:28px; background:rgba(255,255,255,.06); box-shadow:0 20px 60px rgba(0,0,0,.25); margin-bottom:16px; }
        .hero h1 { margin:0; font-size:42px; letter-spacing:-.04em; }
        .hero p { color:#9fb3cc; margin:8px 0 0; }
        .signal-card { padding:18px; border-radius:22px; border:1px solid rgba(125,190,255,.22); background:rgba(255,255,255,.07); }
        .signal-card label { color:#9fb3cc; font-size:13px; }
        .signal-card strong { display:block; margin-top:8px; font-size:28px; }
        .buy { color:#34d399; } .sell { color:#fbbf24; } .hold { color:#93c5fd; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="hero">
          <h1>JP Radar</h1>
          <p>독립 테스트용 시장·업종 에너지 레이더 · ADE와 분리 실행</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    sector_code = col1.selectbox("섹터", sorted(SECTORS), format_func=lambda x: SECTORS[x].name)
    refresh = col2.checkbox("데이터 새로고침", value=False)
    run_button = col3.button("JP Radar 실행", type="primary")

    if run_button or "jp_radar_result" not in st.session_state:
        with st.spinner("데이터 수집 및 레이더 계산 중..."):
            st.session_state["jp_radar_result"] = JPRadarEngine().analyze(sector_code, refresh=refresh)
    result = st.session_state["jp_radar_result"]

    cls = result.combined_signal.lower()
    c1, c2, c3, c4, c5 = st.columns(5)
    _card(c1, "종합 신호", result.combined_signal, cls)
    _card(c2, "일봉 신호", f"{result.daily.latest_signal} · {result.daily.latest_signal_date or '-'}", result.daily.latest_signal.lower())
    _card(c3, "주봉 신호", f"{result.weekly.latest_signal} · {result.weekly.latest_signal_date or '-'}", result.weekly.latest_signal.lower())
    _card(c4, "일봉 에너지", f"{result.daily.latest_energy:.2f}", "hold")
    _card(c5, "주봉 에너지", f"{result.weekly.latest_energy:.2f}", "hold")

    st.plotly_chart(make_radar_chart(result), use_container_width=True)

    with st.expander("시가총액 가중치"):
        rows = sorted(result.weights.items(), key=lambda x: x[1], reverse=True)
        st.dataframe([{"ticker": k, "weight": round(v * 100, 2)} for k, v in rows], use_container_width=True, hide_index=True)


def _card(col: object, label: str, value: str, cls: str) -> None:
    col.markdown(f"<div class='signal-card'><label>{label}</label><strong class='{cls}'>{value}</strong></div>", unsafe_allow_html=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="JP Radar standalone dashboard")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
