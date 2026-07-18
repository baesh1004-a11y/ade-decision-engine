from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from dashboard.data import PaperDashboardData
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from monitoring.live_monitor import ADELiveMonitor
from recommendation.run_context import load_latest_context


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Live Monitor", page_icon="⚡", layout="wide")
    _style(st)

    st.markdown(
        """
        <div class="live-hero">
          <div><div class="eyebrow">ADE INTRADAY CONTROL</div><h1>추천종목 · 보유종목 실시간 모니터</h1>
          <p>최신 완료 추천은 그대로 유지하고, 사용자가 자동 갱신을 켠 경우에만 KIS 현재가를 다시 조회합니다.</p></div>
          <div class="live-badge"><span></span> KIS PAPER MONITOR</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    interval = c1.selectbox("갱신주기", [10, 20, 30, 60], index=0, format_func=lambda x: f"{x}초")
    auto = c2.toggle("자동 갱신", value=False)
    top_n = c3.number_input("모니터 추천 수", min_value=1, max_value=20, value=10, step=1)
    reload_latest = c4.button("최신 완료 추천 불러오기", type="primary", use_container_width=True)

    recommendations, run_info, name_map = _load_stored_recommendations(db_path, int(top_n))
    if reload_latest:
        st.session_state.pop("live_monitor_first", None)
        st.rerun()

    data = PaperDashboardData(db_path)
    try:
        positions = data.load_positions()
    finally:
        data.close()
    positions = _normalize_positions(positions, name_map)

    if run_info:
        st.caption(
            f"연결 실행 ID: {run_info['run_id']} · 완료 시각: {run_info.get('finished_at') or '-'} · "
            f"추천 계산은 반복하지 않고 현재가만 갱신합니다."
        )
    else:
        st.warning("저장된 최신 완료 추천 실행이 없습니다. 먼저 통합 추천 워크벤치에서 추천을 생성하세요.")

    info1, info2, info3, info4 = st.columns(4)
    info1.metric("추천 모니터", len(recommendations))
    info2.metric("보유 모니터", len(positions))
    info3.metric("가격 소스", "KIS → 로컬 fallback")
    info4.metric("화면 진입 시각", datetime.now().strftime("%H:%M:%S"))

    def monitor_body() -> None:
        monitor = ADELiveMonitor(db_path=db_path, prefer_kis=True)
        try:
            rows = monitor.monitor(recommendations, positions)
            kis_error = monitor.kis_error
        finally:
            monitor.close()

        if not rows:
            st.info("모니터링할 추천종목이나 보유종목이 없습니다.")
            return

        frame = pd.DataFrame([row.to_dict() for row in rows])
        if not frame.empty:
            frame["ticker"] = frame["ticker"].map(lambda value: normalize_ticker(value, "kr"))
            frame["name"] = frame.apply(
                lambda row: resolve_name(row.get("ticker"), row.get("name"), name_map, "kr"), axis=1
            )
            frame["symbol"] = frame.apply(
                lambda row: display_symbol(row.get("name"), row.get("ticker"), "kr"), axis=1
            )

        alerts = int((frame["status"] == "ALERT").sum())
        buy_zones = int((frame["status"] == "BUY ZONE").sum())
        watch = int(frame["status"].isin(["WATCH"]).sum())
        normal = len(frame) - alerts - buy_zones - watch

        a, b, c, d = st.columns(4)
        a.metric("즉시 확인", alerts)
        b.metric("매수 검토", buy_zones)
        c.metric("주의", watch)
        d.metric("정상", normal)

        if kis_error:
            st.warning(f"KIS 현재가 일부 호출 실패로 로컬 최신 종가를 사용했습니다: {kis_error}")

        st.markdown("### 실시간 판단표")
        display = frame.rename(
            columns={
                "kind": "구분", "market": "시장", "symbol": "종목", "ticker": "종목코드", "name": "종목명",
                "price": "현재가", "change_rate": "장중등락률", "reference_price": "평균단가",
                "pnl_rate": "보유수익률", "seven_day_up_probability": "7일상승확률",
                "seven_day_expected_return": "7일기대수익", "prediction_grade": "예측등급",
                "status": "상태", "reason": "판단이유", "source": "가격소스", "updated_at": "갱신시각",
            }
        )
        preferred = [
            "구분", "시장", "종목", "종목코드", "종목명", "현재가", "장중등락률", "평균단가",
            "보유수익률", "7일상승확률", "7일기대수익", "예측등급", "상태", "판단이유", "가격소스", "갱신시각",
        ]
        display = display[[column for column in preferred if column in display.columns]]
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "현재가": st.column_config.NumberColumn(format="%,.0f원"),
                "장중등락률": st.column_config.NumberColumn(format="%+.2f%%"),
                "평균단가": st.column_config.NumberColumn(format="%,.0f원"),
                "보유수익률": st.column_config.NumberColumn(format="%+.2f%%"),
                "7일상승확률": st.column_config.NumberColumn(format="%.1f%%"),
                "7일기대수익": st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )

        rec_df = frame[frame["kind"] == "RECOMMENDATION"].copy()
        pos_df = frame[frame["kind"] == "POSITION"].copy()
        left, right = st.columns(2)
        with left:
            st.markdown("### 추천종목 장중 체크")
            _cards(st, rec_df)
        with right:
            st.markdown("### 보유종목 장중 체크")
            _cards(st, pos_df)

        st.caption(f"현재가 마지막 갱신: {datetime.now().strftime('%H:%M:%S')}")

    if auto and hasattr(st, "fragment"):
        @st.fragment(run_every=f"{int(interval)}s")
        def auto_fragment() -> None:
            monitor_body()
        auto_fragment()
    else:
        if auto:
            st.caption("현재 Streamlit 버전은 자동 fragment 갱신을 지원하지 않아 수동 갱신으로 동작합니다.")
        if st.button("현재가 새로고침") or "live_monitor_first" not in st.session_state:
            st.session_state["live_monitor_first"] = True
            monitor_body()


def _load_stored_recommendations(db_path: str, top_n: int):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, "kr", limit=top_n)
        name_map = build_name_map(conn, "kr")
        if context is None:
            return [], {}, name_map
        items = []
        for row in context.recommendations[:top_n]:
            code = normalize_ticker(row.get("ticker"), "kr")
            name = resolve_name(code, row.get("name"), name_map, "kr")
            prediction = _prediction_from_payload(row.get("payload_json"))
            items.append(SimpleNamespace(market="kr", ticker=code, name=name, prediction=prediction))
        return items, {
            "run_id": context.run_id,
            "finished_at": context.finished_at,
            "run_type": context.run_type,
        }, name_map
    finally:
        conn.close()


def _prediction_from_payload(raw: object):
    try:
        payload = json.loads(str(raw)) if raw else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    prediction = payload.get("prediction")
    if not isinstance(prediction, dict):
        return None
    return SimpleNamespace(
        seven_day_up_probability=prediction.get("seven_day_up_probability"),
        seven_day_expected_return=prediction.get("seven_day_expected_return"),
        grade=prediction.get("grade"),
    )


def _normalize_positions(frame: pd.DataFrame, name_map: dict[str, str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    if "ticker" in result.columns:
        result["ticker"] = result["ticker"].map(lambda value: normalize_ticker(value, "kr"))
        result["name"] = result.apply(
            lambda row: resolve_name(row.get("ticker"), row.get("name"), name_map, "kr"), axis=1
        )
    return result


def _cards(st: object, frame: pd.DataFrame) -> None:
    if frame.empty:
        st.caption("대상 없음")
        return
    for _, row in frame.iterrows():
        status = str(row["status"])
        css = "alert" if status == "ALERT" else "buy-zone" if status == "BUY ZONE" else "watch" if status == "WATCH" else "normal"
        pnl = row.get("pnl_rate")
        pnl_text = "" if pd.isna(pnl) else f" · 보유 {float(pnl):+.2f}%"
        symbol = display_symbol(row.get("name"), row.get("ticker"), "kr")
        st.markdown(
            f"""
            <div class="monitor-card {css}">
              <div><b>{symbol}</b><small>{str(row['market']).upper()} · {row['source']}</small></div>
              <div class="price">{float(row['price']):,.0f}원 <span>{float(row['change_rate']):+.2f}%{pnl_text}</span></div>
              <div class="reason">{row['reason']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#edf7ff 0%,#f8fbff 45%,#e9f3ff 100%);color:#13253a}
        .block-container{max-width:1650px;padding-top:1.3rem}
        .live-hero{display:flex;justify-content:space-between;align-items:center;padding:25px 30px;border-radius:28px;background:rgba(255,255,255,.78);border:1px solid rgba(77,151,220,.25);box-shadow:0 20px 55px rgba(59,106,153,.13);margin-bottom:16px}
        .live-hero h1{margin:3px 0;font-size:36px;letter-spacing:-.04em}.live-hero p{margin:5px 0;color:#627991}
        .eyebrow{font-size:12px;font-weight:800;letter-spacing:.16em;color:#3479b9}.live-badge{padding:10px 15px;border-radius:999px;background:#eaf7ef;color:#18794e;font-weight:800}.live-badge span{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:6px}
        .monitor-card{padding:15px 17px;margin:9px 0;border-radius:18px;background:rgba(255,255,255,.82);border-left:5px solid #75a9d5;box-shadow:0 8px 28px rgba(57,93,128,.09)}
        .monitor-card.alert{border-left-color:#ef4444}.monitor-card.buy-zone{border-left-color:#22c55e}.monitor-card.watch{border-left-color:#f59e0b}.monitor-card.normal{border-left-color:#60a5fa}
        .monitor-card b{font-size:17px}.monitor-card small{display:block;color:#72869a;margin-top:2px}.monitor-card .price{font-size:22px;font-weight:850;margin-top:8px}.monitor-card .price span{font-size:14px;color:#49647e}.monitor-card .reason{margin-top:6px;color:#49647e}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE recommendation and position live monitor")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
