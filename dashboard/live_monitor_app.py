from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from dashboard.data import PaperDashboardData
from dashboard.design_system import StatusBadge, apply_design_system, page_header, section
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from monitoring.live_monitor import ADELiveMonitor
from recommendation.run_context import load_latest_context


_STATUS_LABELS = {
    "ALERT": "즉시 확인",
    "BUY ZONE": "매수 검토",
    "WATCH": "주의",
    "NORMAL": "정상",
    "RECOMMENDATION": "추천종목",
    "POSITION": "보유종목",
}


def _status_label(value: object) -> str:
    text = str(value or "").strip().upper()
    return _STATUS_LABELS.get(text, str(value or "-"))


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 실시간 모니터", page_icon="📡", layout="wide")
    apply_design_system(st)

    page_header(
        title="실시간 모니터",
        subtitle="추천종목과 보유종목의 장중 흐름을 확인합니다. 자동 갱신을 켠 경우에만 KIS 현재가를 다시 조회합니다.",
        eyebrow="ADE · 실시간 모니터링",
        badges=(StatusBadge("KIS 모의투자", "success"),),
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    interval = c1.selectbox("갱신 주기", [10, 20, 30, 60], index=0, format_func=lambda x: f"{x}초")
    auto = c2.toggle("자동 갱신", value=False)
    top_n = c3.number_input("추천종목 수", min_value=1, max_value=20, value=10, step=1)
    reload_latest = c4.button("최신 추천 다시 불러오기", type="primary", use_container_width=True)

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
            "추천 계산은 반복하지 않고 현재가만 갱신합니다."
        )
    else:
        st.warning("저장된 최신 추천 결과가 없습니다. 추천종목 분석에서 추천을 먼저 생성해 주세요.")

    info1, info2, info3, info4 = st.columns(4)
    info1.metric("추천종목", len(recommendations))
    info2.metric("보유종목", len(positions))
    info3.metric("가격 데이터", "KIS → 로컬 대체")
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
            st.warning(f"KIS 현재가 일부 호출에 실패하여 로컬 최신 종가를 사용했습니다: {kis_error}")

        section("실시간 판단표", "추천종목과 보유종목의 현재 상태를 한눈에 확인합니다.")
        display = frame.rename(
            columns={
                "kind": "구분", "market": "시장", "symbol": "종목", "ticker": "종목코드", "name": "종목명",
                "price": "현재가", "change_rate": "장중등락률", "reference_price": "평균단가",
                "pnl_rate": "보유수익률", "seven_day_up_probability": "7일 상승확률",
                "seven_day_expected_return": "7일 기대수익", "prediction_grade": "예측등급",
                "status": "상태", "reason": "판단 이유", "source": "가격 데이터", "updated_at": "갱신 시각",
            }
        )
        if "구분" in display.columns:
            display["구분"] = display["구분"].map(_status_label)
        if "상태" in display.columns:
            display["상태"] = display["상태"].map(_status_label)
        if "시장" in display.columns:
            display["시장"] = display["시장"].map(lambda value: "국내" if str(value).lower() == "kr" else str(value).upper())

        preferred = [
            "구분", "시장", "종목", "종목코드", "종목명", "현재가", "장중등락률", "평균단가",
            "보유수익률", "7일 상승확률", "7일 기대수익", "예측등급", "상태", "판단 이유", "가격 데이터", "갱신 시각",
        ]
        display = display[[column for column in preferred if column in display.columns]].fillna("-")
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "현재가": st.column_config.NumberColumn(format="%,.0f원"),
                "장중등락률": st.column_config.NumberColumn(format="%+.2f%%"),
                "평균단가": st.column_config.NumberColumn(format="%,.0f원"),
                "보유수익률": st.column_config.NumberColumn(format="%+.2f%%"),
                "7일 상승확률": st.column_config.NumberColumn(format="%.1f%%"),
                "7일 기대수익": st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )

        rec_df = frame[frame["kind"] == "RECOMMENDATION"].copy()
        pos_df = frame[frame["kind"] == "POSITION"].copy()
        left, right = st.columns(2)
        with left:
            section("추천종목 장중 점검")
            _cards(st, rec_df)
        with right:
            section("보유종목 장중 점검")
            _cards(st, pos_df)

        st.caption(f"마지막 현재가 갱신: {datetime.now().strftime('%H:%M:%S')}")

    if auto and hasattr(st, "fragment"):
        @st.fragment(run_every=f"{int(interval)}s")
        def auto_fragment() -> None:
            monitor_body()
        auto_fragment()
    else:
        if auto:
            st.caption("현재 Streamlit 버전은 자동 갱신을 지원하지 않아 수동 갱신으로 동작합니다.")
        if st.button("현재가 다시 불러오기") or "live_monitor_first" not in st.session_state:
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
        st.markdown('<div class="ade-empty">대상이 없습니다.</div>', unsafe_allow_html=True)
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
              <div><b>{symbol}</b><small>국내 · {row['source']}</small></div>
              <div class="price">{float(row['price']):,.0f}원 <span>{float(row['change_rate']):+.2f}%{pnl_text}</span></div>
              <div class="reason"><strong>{_status_label(status)}</strong> · {row['reason']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE 추천종목 및 보유종목 실시간 모니터")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
