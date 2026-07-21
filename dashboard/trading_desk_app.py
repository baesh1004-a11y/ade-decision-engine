from __future__ import annotations

import argparse
import os
import sqlite3
from types import SimpleNamespace

import pandas as pd

from dashboard.charts import CHART_CONFIG, build_trading_chart
from markets.symbol_display import display_symbol, normalize_ticker
from meta_score.validation_context import EnvironmentAdvisor
from trading.order_service import TradingOrderService


ELIGIBLE_DECISIONS = {"FINAL BUY", "BUY WATCH"}


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE ?쒓뎅 二쇰Ц愿由?, page_icon="?뮩", layout="wide")

    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    service = TradingOrderService(db_path)
    try:
        recommendations = service.latest_recommendations(50)
        requests = service.pending_requests(100)
        current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
        pending_count = sum(
            1
            for row in requests
            if row["status"] == "PENDING_APPROVAL"
            and (not current_run_id or str(row.get("source_run_id") or "") == current_run_id)
        )
        _style(st)
        _render_status_header(st, env, live_enabled, len(recommendations), pending_count)

        st.markdown("### 1. 異붿쿇 Watch List")
        if not recommendations:
            st.warning("理쒖떊 ?꾨즺 異붿쿇 寃곌낵媛 ?놁뒿?덈떎. 癒쇱? ?듯빀 異붿쿇 ?뚰겕踰ㅼ튂?먯꽌 異붿쿇???앹꽦?섏꽭??")
        else:
            run_id = str(recommendations[0]["run_id"])
            run_finished = str(recommendations[0].get("run_finished_at") or "-")
            st.caption(
                f"異붿쿇 ?꾨즺: {run_finished} 쨌 "
                "?쇱そ 紐⑸줉?먯꽌 醫낅ぉ???좏깮?섎㈃ ?ㅻⅨ履?李⑦듃? 遺꾩꽍쨌二쇰Ц ?붾㈃???④퍡 諛붾앸땲??"
            )

            labels = [_watch_label(row) for row in recommendations]
            selected_from_workbench = normalize_ticker(st.session_state.get("workbench_selected_kr") or "", "kr")
            default_index = next(
                (
                    i
                    for i, row in enumerate(recommendations)
                    if normalize_ticker(row["ticker"], "kr") == selected_from_workbench
                ),
                0,
            )

            watch_column, detail_column = st.columns([1, 3], gap="large")
            with watch_column:
                st.markdown("#### 異붿쿇 醫낅ぉ")
                index = st.radio(
                    "異붿쿇 醫낅ぉ ?좏깮",
                    range(len(recommendations)),
                    index=default_index,
                    format_func=lambda i: labels[i],
                    key="trading_order_selected_kr",
                    label_visibility="collapsed",
                )
                st.caption("??留ㅼ닔 寃?? ??愿李? ??蹂대쪟  ???쒖쇅  ??誘멸?利?)
                st.caption(f"珥?{len(recommendations)}媛?異붿쿇 醫낅ぉ")

            selected = recommendations[index]
            selected_code = normalize_ticker(selected["ticker"], "kr")
            selected_label = display_symbol(selected.get("name"), selected_code, "kr")
            st.session_state["workbench_selected_kr"] = selected_code

            with detail_column:
                _render_selected_summary(st, selected, selected_label)
                _render_ai_confidence_card(st, selected, selected_code)
                _render_analysis_actions(st, selected, selected_code)
                _render_live_chart(st, db_path, selected_code, selected_label)

            st.divider()
            _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        _render_pending_approval(st, service, recommendations)
        _render_execution_and_history(st, service)
    finally:
        service.close()


def _render_status_header(st, env: str, live_enabled: bool, recommendation_count: int, pending_count: int) -> None:
    if env == "live" and live_enabled:
        mode_label = "?ㅼ쟾二쇰Ц ?쒖꽦"
        mode_class = "danger"
    elif env == "live":
        mode_label = "?ㅼ쟾?섍꼍 쨌 二쇰Ц ?좉툑"
        mode_class = "warning"
    else:
        mode_label = "紐⑥쓽?ъ옄"
        mode_class = "safe"

    st.markdown(
        f"""
        <div class="status-hero">
          <div>
            <div class="eyebrow">ADE 쨌 異붿쿇 ??醫낅ぉ 二쇰Ц ?곌퀎</div>
            <h1>?쒓뎅 二쇰Ц愿由?/h1>
            <p>異붿쿇 Watch List ???좏깮 醫낅ぉ ?먮떒 ?꾧뎄쨌李⑦듃 ???쇰컲 二쇰Ц ???ъ슜???뱀씤 ??KIS ?꾩넚</p>
          </div>
          <div class="status-cluster">
            <span class="status-badge {mode_class}">??{mode_label}</span>
            <span class="status-badge neutral">異붿쿇 {recommendation_count}醫낅ぉ</span>
            <span class="status-badge neutral">?뱀씤 ?湲?{pending_count}嫄?/span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _watch_label(row: dict) -> str:
    decision = str(row.get("decision") or "UNVALIDATED")
    marker = _decision_marker(decision)
    name = display_symbol(row.get("name"), row.get("ticker"), "kr")
    rank = int(row.get("rank_no") or 0)
    weekly = float(row.get("weekly_similarity") or 0.0)
    sto = float(row.get("sto_similarity") or 0.0)
    return (
        f"{marker} #{rank} {name} 쨌 {_decision_label(decision)}\n"
        f"二쇰큺 {weekly:.1f}%  쨌  STO {sto:.1f}%"
    )


def _render_selected_summary(st, selected: dict, label: str) -> None:
    st.markdown(f"### {label}")
    decision = str(selected.get("decision") or "UNVALIDATED")
    cols = st.columns(4)
    cols[0].metric("異붿쿇 ?쒖쐞", f"{int(selected.get('rank_no') or 0)}??)
    cols[1].metric("二쇰큺 ?좎궗??, f"{float(selected.get('weekly_similarity') or 0.0):.2f}%")
    cols[2].metric("STO", f"{float(selected.get('sto_similarity') or 0.0):.2f}%")
    cols[3].metric("寃利?議곗뼵", _decision_label(decision))


def _render_ai_confidence_card(st, selected: dict, ticker: str) -> None:
    score, level, tone, opinion, factors = _ai_confidence(selected, st.session_state.get(f"jp_radar_result_{ticker}"))
    score_text = str(score) if score is not None else "誘명솗??
    rows = "".join(
        f'<div class="confidence-row"><span>{label}</span><strong>{value}</strong><span class="signal {signal}">??/span></div>'
        for label, value, signal in factors
    )
    st.markdown(
        f"""
        <div class="confidence-card {tone}">
          <div class="confidence-head">
            <div>
              <div class="confidence-eyebrow">AI 醫낇빀 ?먮떒 蹂댁“</div>
              <div class="confidence-title">{_confidence_icon(tone)} AI ?좊ː??쨌 {level}</div>
            </div>
            <div class="confidence-score">{score_text}<span>{'?? if score is not None else ''}</span></div>
          </div>
          <div class="confidence-grid">{rows}</div>
          <div class="confidence-opinion"><strong>AI 醫낇빀 ?섍껄</strong><br>{opinion}</div>
          <div class="confidence-note">?뺤씤??{sum(value != '誘명솗?? for _, value, _ in factors)}/{len(factors)}媛???ぉ留?諛섏쁺?덉뒿?덈떎. ?ъ옄 ?먮떒?대굹 二쇰Ц ?뱀씤????좏븯吏 ?딆뒿?덈떎.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _ai_confidence(selected: dict, radar) -> tuple[int | None, str, str, str, list[tuple[str, str, str]]]:
    weekly = _optional_score(selected.get("weekly_similarity"))
    sto = _optional_score(selected.get("sto_similarity"))
    market = _optional_score(selected.get("market_score"))
    sector = _optional_score(selected.get("sector_score"))
    risk = _optional_score(selected.get("risk_score"))

    radar_score: float | None = None
    radar_label = "誘명솗??
    if radar is not None:
        market_signal = str(getattr(radar, "market_signal", "") or "")
        sector_signal = str(getattr(radar, "sector_signal", "") or "")
        radar_text = f"{market_signal} {sector_signal}".lower()
        if any(token in radar_text for token in ("媛뺤꽭", "positive", "bull", "?묓샇")):
            radar_score, radar_label = 80.0, "媛뺤꽭"
        elif any(token in radar_text for token in ("?쎌꽭", "negative", "bear", "二쇱쓽")):
            radar_score, radar_label = 30.0, "?쎌꽭"
        else:
            radar_score, radar_label = 55.0, "以묐┰"

    weighted_values = [
        (weekly, 0.28),
        (sto, 0.22),
        (market, 0.16),
        (sector, 0.14),
        (risk, 0.15),
        (radar_score, 0.05),
    ]
    available = [(value, weight) for value, weight in weighted_values if value is not None]
    score = round(sum(value * weight for value, weight in available) / sum(weight for _, weight in available)) if available else None

    decision = str(selected.get("decision") or "UNVALIDATED")
    if score is not None and decision == "FINAL BUY":
        score = min(100, score + 5)
    elif score is not None and decision in {"HOLD", "PASS"}:
        score = max(0, score - 10)
    elif score is not None and decision == "UNVALIDATED":
        score = min(score, 69)

    if score is None:
        level, tone = "怨꾩궛 遺덇?", "neutral"
        opinion = "?뺤씤??遺꾩꽍 ?곗씠?곌? ?놁뼱 ?좊ː?꾨? 怨꾩궛?섏? ?딆븯?듬땲?? 異붿쿇 寃利앹쓣 癒쇱? ?ㅽ뻾?섏꽭??"
    elif score >= 80:
        level, tone = "留ㅼ슦 ?믪쓬", "high"
        opinion = "?꾩옱 ?곗씠?곕뒗 ?곴레?곸씤 留ㅼ닔 寃?좉? 媛?ν븳 援ш컙??媛由ы궢?덈떎. 二쇰Ц ??李⑦듃? 寃利?議곗뼵???④퍡 ?뺤씤?섏꽭??"
    elif score >= 65:
        level, tone = "?믪쓬", "good"
        opinion = "湲띿젙 ?좏샇媛 ?곗꽭?섏?留??쇰? 議곌굔 ?뺤씤???꾩슂?⑸땲?? 遺꾪븷 ?묎렐怨??꾪뿕 湲곗? ?뺤씤???곸젅?⑸땲??"
    elif score >= 45:
        level, tone = "蹂댄넻", "neutral"
        opinion = "?좏샇媛 ?쇱옱?섏뼱 ?덉뒿?덈떎. 異붽? 寃利??꾩뿉??愿李?以묒떖 ?묎렐???곸젅?⑸땲??"
    else:
        level, tone = "??쓬", "low"
        opinion = "?꾪뿕 ?먮뒗 ?쏀븳 ?좏샇媛 ?곗꽭?⑸땲?? ?꾩옱??愿留앷낵 ?ш?利앹쓣 ?곗꽑?섎뒗 ?몄씠 ?덉쟾?⑸땲??"

    environment_values = [value for value in (market, sector) if value is not None]
    environment = sum(environment_values) / len(environment_values) if environment_values else None
    factors = [
        ("二쇰큺 ?좎궗??, _score_text(weekly, "%"), _signal_class(weekly)),
        ("STO", _score_text(sto, "%"), _signal_class(sto)),
        ("JP Radar", radar_label, _signal_class(radar_score)),
        ("?쒖옣쨌?낆쥌", _score_text(environment, "??), _signal_class(environment)),
        ("由ъ뒪??, _risk_label(risk) if risk is not None else "誘명솗??, _signal_class(risk)),
    ]
    return score, level, tone, opinion, factors


def _optional_score(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _score_text(value: float | None, suffix: str) -> str:
    return "誘명솗?? if value is None else f"{value:.0f}{suffix}"


def _clamp_score(value, default: float = 0.0) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return default


def _signal_class(score: float | None) -> str:
    if score is None:
        return "unknown"
    return "high" if score >= 70 else "mid" if score >= 45 else "low"


def _confidence_icon(tone: str) -> str:
    return {"high": "?윟", "good": "?뵷", "neutral": "?윝", "low": "?뵶"}.get(tone, "??)


def _render_live_chart(st, db_path: str, ticker: str, label: str) -> None:
    st.markdown(f"### ?꾩옱 李⑦듃 쨌 {label}")
    bars, source = _load_live_bars(db_path, ticker)
    if bars.empty:
        st.warning("?꾩옱 李⑦듃 ?곗씠?곕? 遺덈윭?ㅼ? 紐삵뻽?듬땲??")
        return
    st.plotly_chart(build_trading_chart(bars, label), use_container_width=True, config=CHART_CONFIG)
    st.caption(f"?쒖꽭 異쒖쿂: {source} 쨌 醫낅ぉ??蹂寃쏀븯嫄곕굹 ?덈줈怨좎묠?섎㈃ 理쒖떊 ?곗씠?곕? ?ㅼ떆 議고쉶?⑸땲??")


def _load_live_bars(db_path: str, ticker: str) -> tuple[pd.DataFrame, str]:
    try:
        import yfinance as yf

        for yahoo_ticker in _yahoo_tickers(ticker):
            frame = yf.download(
                yahoo_ticker,
                period="5d",
                interval="5m",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if not frame.empty:
                if isinstance(frame.columns, pd.MultiIndex):
                    frame.columns = frame.columns.get_level_values(0)
                frame = frame.reset_index()
                date_column = "Datetime" if "Datetime" in frame.columns else "Date"
                frame = frame.rename(columns={date_column: "Date"})
                keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in frame.columns]
                return frame[keep].dropna(subset=["Close"]), f"Yahoo Finance 5遺꾨큺 ({yahoo_ticker})"
    except Exception:
        pass

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT trade_date AS Date, open AS Open, high AS High, low AS Low,
                      close AS Close, volume AS Volume
               FROM price_bars
               WHERE market='kr' AND ticker=?
               ORDER BY trade_date DESC LIMIT 120""",
            (ticker,),
        ).fetchall()
        return pd.DataFrame([dict(row) for row in reversed(rows)]), "?대? 理쒖떊 ????쒖꽭"
    finally:
        conn.close()


def _yahoo_tickers(ticker: str) -> list[str]:
    raw = str(ticker).strip().upper()
    code = normalize_ticker(ticker, "kr")
    if raw.endswith(".KQ"):
        return [f"{code}.KQ"]
    if raw.endswith(".KS"):
        return [f"{code}.KS"]
    return [f"{code}.KS", f"{code}.KQ"]


def _yahoo_ticker(ticker: str) -> str:
    """Compatibility helper for callers that only need the first candidate."""
    return _yahoo_tickers(ticker)[0]


def _render_analysis_actions(st, selected: dict, ticker: str) -> None:
    st.markdown("#### ?먮떒 ?꾧뎄")
    c1, c2, c3 = st.columns(3)
    if c1.button("JP Radar", use_container_width=True, key=f"jp_radar_{ticker}"):
        recommendation = SimpleNamespace(
            market="kr",
            ticker=ticker,
            name=selected.get("name"),
            prediction=None,
            matched_max_drawdown=float(selected.get("matched_max_drawdown") or 0.0),
        )
        st.session_state[f"jp_radar_result_{ticker}"] = EnvironmentAdvisor().analyze(recommendation)
        st.rerun()

    if c2.button("異붿쿇 寃利?, use_container_width=True, key=f"validation_{ticker}"):
        st.session_state[f"validation_open_{ticker}"] = True

    if c3.button("李⑦듃 ?덈줈怨좎묠", use_container_width=True, key=f"refresh_chart_{ticker}"):
        st.rerun()

    radar = st.session_state.get(f"jp_radar_result_{ticker}")
    if radar is not None:
        a, b = st.columns(2)
        a.metric("?꾩껜 ?쒖옣 JP Radar", str(radar.market_signal))
        b.metric("?대떦 ?낆쥌 JP Radar", str(radar.sector_signal))

    if st.session_state.get(f"validation_open_{ticker}"):
        decision = str(selected.get("decision") or "UNVALIDATED")
        st.markdown(f"**異붿쿇 寃利?議곗뼵:** {_decision_label(decision)}")
        cols = st.columns(3)
        cols[0].metric("?꾩껜 ?쒖옣", _score_label(selected.get("market_score")))
        cols[1].metric("?대떦 ?낆쥌", _score_label(selected.get("sector_score")))
        cols[2].metric("醫낅ぉ ?꾪뿕", _risk_label(selected.get("risk_score")))
        if decision == "UNVALIDATED":
            st.info("?꾩쭅 ??λ맂 寃利?議곗뼵???놁뒿?덈떎. ?듯빀 異붿쿇 ?뚰겕踰ㅼ튂?먯꽌 ??醫낅ぉ???섍꼍 議곗뼵???ㅽ뻾?섏꽭??")
            st.page_link("pages/2_Meta_Score.py", label="異붿쿇 寃利??붾㈃ ?닿린", icon="??, use_container_width=True)


def _render_order_form(st, service, selected: dict, ticker: str, label: str, run_id: str) -> None:
    st.markdown("### ?쇰컲 二쇰Ц")
    decision = str(selected.get("decision") or "UNVALIDATED")
    validated = bool(selected.get("validation_available"))
    eligible = decision in ELIGIBLE_DECISIONS

    st.markdown(f"**?좏깮 醫낅ぉ:** {label}")
    side_labels = {"留ㅼ닔": "BUY", "留ㅻ룄": "SELL"}
    order_type_labels = {"?쒖옣媛": "MARKET", "吏?뺢?": "LIMIT"}

    c1, c2, c3 = st.columns([1, 1, 1.2])
    side_label = c1.selectbox("二쇰Ц 諛⑺뼢", list(side_labels), key=f"side_label_{ticker}")
    quantity = c2.number_input("?섎웾", min_value=1, value=1, step=1, key=f"quantity_{ticker}")
    order_type_label = c3.selectbox("二쇰Ц ?좏삎", list(order_type_labels), key=f"order_type_label_{ticker}")

    side = side_labels[side_label]
    order_type = order_type_labels[order_type_label]
    limit_price = 0.0
    if order_type == "LIMIT":
        limit_price = st.number_input(
            "吏?뺢?",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key=f"limit_price_{ticker}",
        )

    r1, r2 = st.columns(2)
    target = r1.number_input(
        "?듭젅 湲곗? ?섏씡瑜?%)",
        value=float(selected.get("target_return") or 0.0),
        step=0.1,
        key=f"target_{ticker}",
    )
    stop = r2.number_input(
        "?먯젅 湲곗? ?섏씡瑜?%)",
        value=float(selected.get("stop_return") or 0.0),
        step=0.1,
        key=f"stop_{ticker}",
    )

    price_phrase = "?쒖옣媛濡? if order_type == "MARKET" else f"{float(limit_price):,.0f}??吏?뺢?濡?
    summary = f"{label} {int(quantity)}二쇰? {price_phrase} {side_label}?⑸땲??"
    risk_summary = f"紐⑺몴 ?섏씡瑜?{float(target):+.1f}% 쨌 ?먯젅 湲곗? {float(stop):+.1f}%"
    st.markdown(
        f"""
        <div class="order-summary">
          <div class="order-summary-label">二쇰Ц ?붿빟</div>
          <div class="order-summary-main">{summary}</div>
          <div class="order-summary-risk">{risk_summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not validated:
        st.caption("誘멸?利?醫낅ぉ??二쇰Ц 由ъ뒪?몄? 二쇰Ц ?낅젰? ?좎??⑸땲?? 留ㅼ닔 ?붿껌 ??寃利?議곗뼵 ?뺤씤??沅뚯옣?⑸땲??")
    elif not eligible and side == "BUY":
        st.warning(f"?꾩옱 寃利?議곗뼵? {_decision_label(decision)}?낅땲?? 二쇰Ц ???ъ슜?먭? 吏곸젒 ?먮떒?댁빞 ?⑸땲??")

    invalid_limit = order_type == "LIMIT" and float(limit_price) <= 0
    if invalid_limit:
        st.warning("吏?뺢? 二쇰Ц? 0?먮낫????媛寃⑹쓣 ?낅젰?댁빞 ?⑸땲??")

    if st.button(
        "二쇰Ц ?붿껌 留뚮뱾湲?,
        type="primary",
        use_container_width=True,
        key=f"create_order_{ticker}",
        disabled=invalid_limit,
    ):
        request_id = service.create_request(
            ticker=ticker,
            name=selected.get("name"),
            side=side,
            quantity=int(quantity),
            order_type=order_type,
            limit_price=None if order_type == "MARKET" else float(limit_price),
            target_return=float(target),
            stop_return=float(stop),
            source_run_id=run_id,
            source_rank=int(selected["rank_no"]),
        )
        st.success(f"二쇰Ц ?붿껌 ?앹꽦: {request_id}. ?꾩쭅 KIS濡??꾩넚?섏? ?딆븯?듬땲??")


def _render_pending_approval(st, service, recommendations: list[dict]) -> None:
    st.markdown("### 2. ?ъ슜???뱀씤 ??KIS 二쇰Ц ?꾩넚")
    requests = service.pending_requests(100)
    current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
    pending = [
        row for row in requests
        if row["status"] == "PENDING_APPROVAL" and str(row.get("source_run_id") or "") == current_run_id
    ]
    if not pending:
        st.caption("?꾩옱 異붿쿇 ?ㅽ뻾???뱀씤 ?湲?二쇰Ц???놁뒿?덈떎.")
        return

    request_index = st.selectbox(
        "?뱀씤 ?湲?二쇰Ц",
        range(len(pending)),
        format_func=lambda i: (
            f"{display_symbol(pending[i].get('name'), pending[i]['ticker'], 'kr')} 쨌 "
            f"{normalize_ticker(pending[i]['ticker'], 'kr')} {pending[i]['side']} {pending[i]['quantity']}二?
        ),
    )
    row = pending[request_index]
    code = normalize_ticker(row["ticker"], "kr")
    expected = f"{code} {row['side']} {row['quantity']}二??뱀씤"
    st.code(expected)
    approval = st.text_input("???뱀씤 臾멸뎄瑜??뺥솗???낅젰")
    confirm = st.checkbox("醫낅ぉ쨌諛⑺뼢쨌?섎웾쨌二쇰Ц?좏삎??吏곸젒 ?뺤씤?덉뒿?덈떎.")
    if st.button("?뱀씤?섍퀬 KIS濡??꾩넚", disabled=not confirm, type="primary"):
        try:
            result = service.approve_and_send(str(row["request_id"]), approval)
            st.success(f"二쇰Ц ?꾩넚 寃곌낵: {result.get('message')} 쨌 二쇰Ц踰덊샇 {result.get('order_id')}")
        except Exception as exc:
            st.error(f"二쇰Ц ?꾩넚 ?ㅽ뙣: {exc}")


def _render_execution_and_history(st, service) -> None:
    st.markdown("### 3. 二쇰Ц 寃곌낵쨌泥닿껐 ?뺤씤")
    a, b, c = st.columns(3)
    if a.button("泥닿껐?댁뿭 ?덈줈怨좎묠", use_container_width=True):
        try:
            rows = service.refresh_executions()
            st.success(f"KIS 二쇰Ц쨌泥닿껐 {len(rows)}嫄??뺤씤")
        except Exception as exc:
            st.error(f"泥닿껐 議고쉶 ?ㅽ뙣: {exc}")
    if b.button("蹂댁쑀醫낅ぉ ?먮룞 諛섏쁺", use_container_width=True):
        try:
            rows = service.sync_positions()
            st.success(f"蹂댁쑀醫낅ぉ {len(rows)}媛??숆린??)
        except Exception as exc:
            st.error(f"蹂댁쑀醫낅ぉ ?숆린???ㅽ뙣: {exc}")
    create_sell = c.checkbox("?먯젅쨌?듭젅 諛쒖깮 ??留ㅻ룄?붿껌 ?앹꽦", value=False)
    if st.button("?먯젅쨌?듭젅 議곌굔 ?먭?", use_container_width=True):
        try:
            actions = service.monitor_risk(create_sell_requests=create_sell)
            if actions:
                st.warning(f"議곌굔 異⑹” {len(actions)}嫄?)
                st.dataframe(pd.DataFrame(actions), use_container_width=True, hide_index=True)
            else:
                st.success("?꾩옱 ?먯젅쨌?듭젅 議곌굔 異⑹” 醫낅ぉ???놁뒿?덈떎.")
        except Exception as exc:
            st.error(f"?꾪뿕愿由??먭? ?ㅽ뙣: {exc}")

    st.markdown("### 二쇰Ц ?붿껌 ?대젰")
    history = pd.DataFrame(service.pending_requests(100))
    if not history.empty:
        history["醫낅ぉ肄붾뱶"] = history["ticker"].map(lambda value: normalize_ticker(value, "kr"))
        history["醫낅ぉ"] = history.apply(lambda row: display_symbol(row.get("name"), row.get("ticker"), "kr"), axis=1)
        keep = [c for c in [
            "created_at", "source_run_id", "source_rank", "醫낅ぉ", "醫낅ぉ肄붾뱶", "side", "quantity",
            "order_type", "limit_price", "status", "broker_order_id", "broker_message", "error_message",
        ] if c in history.columns]
        st.dataframe(history[keep], use_container_width=True, hide_index=True)

    st.markdown("### 泥닿껐 ?대젰")
    executions = pd.DataFrame(service.latest_executions(100))
    if not executions.empty:
        executions["醫낅ぉ肄붾뱶"] = executions["ticker"].map(lambda value: normalize_ticker(value, "kr"))
        keep = [c for c in [
            "captured_at", "broker_order_id", "醫낅ぉ肄붾뱶", "side", "ordered_quantity",
            "filled_quantity", "filled_price", "status",
        ] if c in executions.columns]
        st.dataframe(executions[keep], use_container_width=True, hide_index=True)

    st.caption("?먯젅쨌?듭젅 媛먯떆???먮룞 留ㅻ룄瑜?吏곸젒 ?꾩넚?섏? ?딄퀬 ?뱀씤 ?湲?留ㅻ룄?붿껌留??앹꽦?⑸땲??")


def _decision_marker(value: str) -> str:
    return {
        "FINAL BUY": "?윟",
        "BUY WATCH": "?뵷",
        "HOLD": "?윝",
        "PASS": "??,
        "UNVALIDATED": "??,
    }.get(value, "??)


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "留ㅼ닔 寃??,
        "BUY WATCH": "愿李?,
        "HOLD": "蹂대쪟",
        "PASS": "?쒖쇅",
        "UNVALIDATED": "誘멸?利?,
    }.get(value, value)


def _score_label(value) -> str:
    if value is None:
        return "誘명솗??
    score = float(value)
    return "?묓샇" if score >= 70 else "蹂댄넻" if score >= 45 else "二쇱쓽"


def _risk_label(value) -> str:
    if value is None:
        return "誘명솗??
    score = float(value)
    return "??쓬" if score >= 70 else "蹂댄넻" if score >= 45 else "?믪쓬"


def _style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1800px;padding-top:.75rem}
        .status-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:18px 24px;border-radius:22px;background:rgba(255,255,255,.88);border:1px solid rgba(72,145,210,.22);box-shadow:0 14px 40px rgba(64,106,147,.11);margin-bottom:12px}
        .status-hero h1{margin:2px 0;font-size:2rem}.status-hero p{margin:3px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        .status-cluster{display:flex;justify-content:flex-end;align-items:center;gap:8px;flex-wrap:wrap}
        .status-badge{display:inline-flex;align-items:center;padding:7px 11px;border-radius:999px;font-size:.84rem;font-weight:750;white-space:nowrap;border:1px solid transparent}
        .status-badge.safe{color:#137044;background:#e9f8f0;border-color:#bde8cf}
        .status-badge.warning{color:#986314;background:#fff6dd;border-color:#f0d58e}
        .status-badge.danger{color:#b42318;background:#fff0ef;border-color:#f3bbb6}
        .status-badge.neutral{color:#36516b;background:#f2f7fb;border-color:#d6e3ed}
        .confidence-card{margin:12px 0 16px;padding:17px 19px;border-radius:18px;background:rgba(255,255,255,.9);border:1px solid rgba(72,145,210,.24);box-shadow:0 10px 28px rgba(64,106,147,.09)}
        .confidence-card.high{border-left:6px solid #26a269}.confidence-card.good{border-left:6px solid #3479b9}.confidence-card.neutral{border-left:6px solid #d28b26}.confidence-card.low{border-left:6px solid #c43d36}
        .confidence-head{display:flex;align-items:center;justify-content:space-between;gap:18px}
        .confidence-eyebrow{font-size:.76rem;font-weight:800;letter-spacing:.09em;color:#6a8095;text-transform:uppercase}
        .confidence-title{margin-top:2px;font-size:1.16rem;font-weight:800;color:#17324d}
        .confidence-score{font-size:2rem;font-weight:850;line-height:1;color:#17324d}.confidence-score span{font-size:.85rem;margin-left:2px;color:#6d8194}
        .confidence-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:14px 0 10px}
        .confidence-row{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:6px;padding:9px 10px;border-radius:11px;background:#f5f9fc;font-size:.84rem;color:#5b7186}
        .confidence-row strong{color:#203a54}.signal.high{color:#26a269}.signal.mid{color:#d28b26}.signal.low{color:#c43d36}.signal.unknown{color:#9aa9b6}
        .confidence-opinion{padding:11px 13px;border-radius:12px;background:#eef6fc;color:#314d67;line-height:1.5}
        .confidence-note{margin-top:7px;font-size:.75rem;color:#7d8fa0}
        .order-summary{margin:14px 0 10px;padding:16px 18px;border-radius:16px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.24);box-shadow:0 8px 24px rgba(64,106,147,.08)}
        .order-summary-label{font-size:.78rem;font-weight:800;letter-spacing:.08em;color:#3479b9;text-transform:uppercase;margin-bottom:5px}
        .order-summary-main{font-size:1.08rem;font-weight:760;color:#17324d}
        .order-summary-risk{margin-top:4px;color:#62788e;font-size:.93rem}
        div[role="radiogroup"]{gap:.45rem}
        div[role="radiogroup"] label{padding:.68rem .75rem;border:1px solid rgba(72,145,210,.18);border-radius:12px;background:rgba(255,255,255,.72);line-height:1.35}
        div[role="radiogroup"] label:hover{border-color:rgba(52,121,185,.48);background:rgba(239,248,255,.96)}
        @media(max-width:1100px){.confidence-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:900px){.status-hero{align-items:flex-start;flex-direction:column}.status-cluster{justify-content:flex-start}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE ?쒓뎅 二쇰Ц愿由?)
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()

