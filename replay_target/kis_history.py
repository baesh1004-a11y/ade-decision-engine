from __future__ import annotations

from typing import Any

import pandas as pd
import requests


def load_reference_history(cfg: Any) -> tuple[pd.DataFrame, str, str | None]:
    """Load the historical AK reference with sources that can reach 2011.

    Priority is KIS REST because the ADE terminal already verifies that
    connection. Naver is a network fallback, followed by pykrx and yfinance.
    A source is accepted only when both the anchor/target windows and enough
    pre-history for the long STO are present.
    """

    start, end = _history_bounds(cfg)
    errors: list[str] = []

    loaders = (
        ("KIS REST · 수정주가", lambda: _load_kis(cfg.reference_ticker, start, end)),
        ("Naver Finance · 일봉", lambda: _load_naver(cfg.reference_ticker, start, end)),
        ("pykrx · KRX 수정주가", lambda: _load_pykrx(cfg.reference_ticker, start, end)),
        ("yfinance", lambda: _load_yfinance(cfg.reference_ticker, start, end)),
    )

    for label, loader in loaders:
        try:
            frame = _normalize(loader())
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            continue
        if frame.empty:
            errors.append(f"{label}: empty")
            continue
        if not _has_required_windows(frame, cfg):
            oldest = _date_text(frame.iloc[0]["Date"])
            latest = _date_text(frame.iloc[-1]["Date"])
            errors.append(f"{label}: 2011 기준구간 부족 ({oldest}~{latest})")
            continue
        return frame, label, None

    empty = pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    return empty, "역사 데이터 없음", " | ".join(errors)


def _load_kis(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    from broker.kis import kis_broker_from_env

    broker = kis_broker_from_env()
    rows: list[dict[str, Any]] = []
    cursor_end = end.normalize()
    normalized_ticker = str(ticker).zfill(6)

    # The daily-item-chart endpoint is bounded per response. Query short,
    # non-overlapping windows backwards so 2010~2012 history is not truncated.
    while cursor_end >= start:
        cursor_start = max(start, cursor_end - pd.Timedelta(days=90))
        payload = broker._get(  # intentional reuse of the authenticated ADE KIS client
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id="FHKST03010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": normalized_ticker,
                "FID_INPUT_DATE_1": cursor_start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": cursor_end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        output = payload.get("output2") or []
        if isinstance(output, dict):
            output = [output]
        for raw in output if isinstance(output, list) else []:
            day = str(raw.get("stck_bsop_date") or "").strip()
            if not day:
                continue
            rows.append(
                {
                    "Date": day,
                    "Open": raw.get("stck_oprc"),
                    "High": raw.get("stck_hgpr"),
                    "Low": raw.get("stck_lwpr"),
                    "Close": raw.get("stck_clpr"),
                    "Volume": raw.get("acml_vol"),
                }
            )
        cursor_end = cursor_start - pd.Timedelta(days=1)

    return pd.DataFrame(rows)


def _load_naver(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    # Naver's chart endpoint can return more than the 3000-row FDR slice.
    url = "https://fchart.stock.naver.com/sise.nhn"
    response = requests.get(
        url,
        params={
            "symbol": str(ticker).zfill(6),
            "timeframe": "day",
            "count": "8000",
            "requestType": "0",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=12,
    )
    response.raise_for_status()

    import re

    rows: list[dict[str, Any]] = []
    for match in re.finditer(r'<item\s+data="([^"]+)"', response.text):
        parts = match.group(1).split("|")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "Date": parts[0],
                "Open": parts[1],
                "High": parts[2],
                "Low": parts[3],
                "Close": parts[4],
                "Volume": parts[5],
            }
        )
    frame = _normalize(pd.DataFrame(rows))
    if frame.empty:
        return frame
    return frame[(frame["Date"] >= start) & (frame["Date"] <= end)].reset_index(drop=True)


def _load_pykrx(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    from pykrx import stock

    raw = stock.get_market_ohlcv_by_date(
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
        str(ticker).zfill(6),
        adjusted=True,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    data = raw.reset_index().rename(
        columns={
            "날짜": "Date",
            "일자": "Date",
            "시가": "Open",
            "고가": "High",
            "저가": "Low",
            "종가": "Close",
            "거래량": "Volume",
        }
    )
    if "Date" not in data.columns and len(data.columns):
        data = data.rename(columns={data.columns[0]: "Date"})
    return data


def _load_yfinance(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    import yfinance as yf

    for suffix in (".KS", ".KQ"):
        raw = yf.download(
            f"{str(ticker).zfill(6)}{suffix}",
            start=start.date().isoformat(),
            end=(end + pd.Timedelta(days=1)).date().isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        frame = _normalize(raw)
        if not frame.empty:
            return frame
    return pd.DataFrame()


def _history_bounds(cfg: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    core = [
        pd.Timestamp(cfg.reference_window_start),
        pd.Timestamp(cfg.reference_window_end),
        pd.Timestamp(cfg.reference_target_window_start),
        pd.Timestamp(cfg.reference_target_window_end),
    ]
    if getattr(cfg, "reference_anchor_date", None):
        core.append(pd.Timestamp(cfg.reference_anchor_date))
    if getattr(cfg, "reference_target_date", None):
        core.append(pd.Timestamp(cfg.reference_target_date))
    return min(core) - pd.Timedelta(days=550), max(core) + pd.Timedelta(days=120)


def _has_required_windows(frame: pd.DataFrame, cfg: Any) -> bool:
    data = _normalize(frame)
    if data.empty:
        return False
    anchor_start = pd.Timestamp(cfg.reference_window_start)
    anchor_end = pd.Timestamp(cfg.reference_window_end)
    target_start = pd.Timestamp(cfg.reference_target_window_start)
    target_end = pd.Timestamp(cfg.reference_target_window_end)
    anchor = data[(data["Date"] >= anchor_start) & (data["Date"] <= anchor_end)]
    target = data[(data["Date"] >= target_start) & (data["Date"] <= target_end)]
    prehistory = data[data["Date"] < anchor_start]
    return bool(not anchor.empty and not target.empty and len(prehistory) >= 120)


def _normalize(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [column[0] if isinstance(column, tuple) else column for column in data.columns]
    if "Date" not in data.columns:
        data = data.reset_index()
        if "Date" not in data.columns and "index" in data.columns:
            data = data.rename(columns={"index": "Date"})
    aliases = {
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "Adj Close": "Close",
    }
    data = data.rename(columns={key: value for key, value in aliases.items() if key in data.columns})
    if not all(column in data.columns for column in ["Date", "Open", "High", "Low", "Close"]):
        return pd.DataFrame(columns=columns)
    if "Volume" not in data.columns:
        data["Volume"] = 0
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return (
        data[columns]
        .dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _date_text(value: Any) -> str:
    try:
        return str(pd.Timestamp(value).date())
    except Exception:
        return "?"
