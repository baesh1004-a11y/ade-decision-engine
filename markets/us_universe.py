from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable

import pandas as pd
import requests
import yfinance as yf


NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
EXCHANGES = ("nasdaq", "nyse", "amex")
EXCLUDED_NAME_PATTERNS = re.compile(
    r"\b(ETF|ETN|ADR|ADS|DEPOSITARY|PREFERRED|PFD|WARRANT|RIGHTS|UNIT|UNITS|ACQUISITION|SPAC)\b",
    re.IGNORECASE,
)
EXCLUDED_SYMBOL_PATTERNS = re.compile(r"[\^/]|\.(WS|U|R|P)$", re.IGNORECASE)


@dataclass(frozen=True)
class USUniverseFilter:
    min_market_cap: float = 1_000_000_000.0
    min_avg_dollar_volume: float = 10_000_000.0
    min_history_years: float = 3.0
    liquidity_days: int = 60
    max_symbols: int = 1500
    exclude_etf: bool = True
    exclude_adr: bool = True
    exclude_preferred: bool = True


@dataclass(frozen=True)
class USUniverseMember:
    symbol: str
    name: str
    exchange: str
    market_cap: float
    avg_dollar_volume: float
    history_years: float
    ipo_year: int | None
    sector: str | None
    industry: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_us_universe(filters: USUniverseFilter) -> tuple[list[USUniverseMember], pd.DataFrame]:
    listings = download_us_listings()
    if listings.empty:
        raise RuntimeError("NASDAQ 종목 목록을 가져오지 못했습니다.")

    screened = _basic_filter(listings, filters)
    if filters.max_symbols > 0:
        screened = screened.nlargest(filters.max_symbols, "market_cap")

    symbols = screened["symbol"].tolist()
    market_history = download_market_history(symbols, period="5y")
    members: list[USUniverseMember] = []
    diagnostics: list[dict[str, object]] = []

    for row in screened.itertuples(index=False):
        frame = market_history.get(row.symbol, pd.DataFrame())
        avg_dollar_volume = 0.0
        history_years = 0.0
        reason = "PASS"
        if frame.empty:
            reason = "NO_PRICE_DATA"
        else:
            close = pd.to_numeric(frame.get("Close"), errors="coerce")
            volume = pd.to_numeric(frame.get("Volume"), errors="coerce")
            valid = pd.DataFrame({"close": close, "volume": volume}).dropna()
            if not valid.empty:
                recent = valid.tail(max(1, filters.liquidity_days))
                avg_dollar_volume = float((recent["close"] * recent["volume"]).mean())
                history_years = max(0.0, (valid.index.max() - valid.index.min()).days / 365.25)
            if avg_dollar_volume < filters.min_avg_dollar_volume:
                reason = "LOW_LIQUIDITY"
            elif history_years < filters.min_history_years:
                reason = "SHORT_HISTORY"

        diagnostics.append(
            {
                "symbol": row.symbol,
                "name": row.name,
                "exchange": row.exchange,
                "market_cap": row.market_cap,
                "avg_dollar_volume": avg_dollar_volume,
                "history_years": history_years,
                "result": reason,
            }
        )
        if reason != "PASS":
            continue

        members.append(
            USUniverseMember(
                symbol=row.symbol,
                name=row.name,
                exchange=row.exchange,
                market_cap=float(row.market_cap),
                avg_dollar_volume=avg_dollar_volume,
                history_years=history_years,
                ipo_year=row.ipo_year,
                sector=row.sector,
                industry=row.industry,
            )
        )

    members.sort(key=lambda item: (item.market_cap, item.avg_dollar_volume), reverse=True)
    return members, pd.DataFrame(diagnostics)


def download_us_listings() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (ADE US Universe Builder)",
        "Accept": "application/json,text/plain,*/*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
    }
    for exchange in EXCHANGES:
        response = requests.get(
            NASDAQ_SCREENER_URL,
            params={"tableonly": "true", "limit": 10000, "exchange": exchange, "download": "true"},
            headers=headers,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        rows = (((payload or {}).get("data") or {}).get("rows") or [])
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        frame["exchange"] = exchange.upper()
        frames.append(frame)
    if not frames:
        return pd.DataFrame()

    raw = pd.concat(frames, ignore_index=True)
    columns = {str(column).lower().replace(" ", ""): column for column in raw.columns}
    symbol_col = columns.get("symbol")
    name_col = columns.get("name")
    cap_col = columns.get("marketcap")
    ipo_col = columns.get("ipoyear")
    sector_col = columns.get("sector")
    industry_col = columns.get("industry")
    if symbol_col is None or name_col is None or cap_col is None:
        raise RuntimeError(f"NASDAQ 종목 목록 형식이 예상과 다릅니다: {list(raw.columns)}")

    result = pd.DataFrame(
        {
            "symbol": raw[symbol_col].astype(str).str.strip().str.upper(),
            "name": raw[name_col].astype(str).str.strip(),
            "exchange": raw["exchange"],
            "market_cap": raw[cap_col].map(_to_number),
            "ipo_year": raw[ipo_col].map(_to_int) if ipo_col else None,
            "sector": raw[sector_col].where(raw[sector_col].notna(), None) if sector_col else None,
            "industry": raw[industry_col].where(raw[industry_col].notna(), None) if industry_col else None,
        }
    )
    return result.drop_duplicates("symbol").reset_index(drop=True)


def download_market_history(symbols: Iterable[str], period: str = "5y", chunk_size: int = 100) -> dict[str, pd.DataFrame]:
    symbol_list = list(dict.fromkeys(str(symbol).upper() for symbol in symbols))
    result: dict[str, pd.DataFrame] = {}
    for start in range(0, len(symbol_list), max(1, chunk_size)):
        chunk = symbol_list[start : start + chunk_size]
        downloaded = yf.download(
            tickers=chunk,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
        )
        if downloaded.empty:
            continue
        if len(chunk) == 1:
            frame = downloaded.copy()
            frame.index = pd.to_datetime(frame.index).tz_localize(None)
            result[chunk[0]] = frame.dropna(how="all")
            continue
        for symbol in chunk:
            try:
                frame = downloaded[symbol].copy()
            except (KeyError, TypeError):
                continue
            if frame.empty:
                continue
            frame.index = pd.to_datetime(frame.index).tz_localize(None)
            result[symbol] = frame.dropna(how="all")
    return result


def _basic_filter(frame: pd.DataFrame, filters: USUniverseFilter) -> pd.DataFrame:
    out = frame.copy()
    out = out[out["market_cap"] >= float(filters.min_market_cap)]
    out = out[out["symbol"].str.match(r"^[A-Z][A-Z0-9.-]{0,9}$", na=False)]
    out = out[~out["symbol"].str.contains(EXCLUDED_SYMBOL_PATTERNS, na=False)]
    if filters.exclude_etf or filters.exclude_adr or filters.exclude_preferred:
        out = out[~out["name"].str.contains(EXCLUDED_NAME_PATTERNS, na=False)]
    return out.reset_index(drop=True)


def _to_number(value: object) -> float:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_int(value: object) -> int | None:
    try:
        number = int(float(str(value).strip()))
        return number if 1800 <= number <= date.today().year else None
    except (TypeError, ValueError):
        return None
