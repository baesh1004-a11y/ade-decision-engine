from __future__ import annotations

import sqlite3
from collections.abc import Mapping


def normalize_ticker(value: object, market: str = "kr") -> str:
    """Return the canonical ticker used internally.

    Korean tickers are normalized to six digits for joins and API calls. They are
    not automatically appended to the user-facing Korean company name.
    """
    text = str(value or "").strip()
    if market.lower() == "kr":
        base = text.split(".", 1)[0]
        digits = "".join(ch for ch in base if ch.isdigit())
        if digits:
            return digits.zfill(6)[-6:]
    return text.upper()


def build_name_map(conn: sqlite3.Connection, market: str = "kr") -> dict[str, str]:
    """Collect company names in authoritative priority order."""
    result: dict[str, str] = {}
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    candidates = [
        ("stock_universe", "ticker", "name"),
        ("kr_universe", "ticker", "name"),
        ("us_universe", "symbol", "name"),
        ("daily_recommendations", "ticker", "name"),
        ("surge_patterns", "ticker", "name"),
        ("replay_events", "ticker", "name"),
        ("final_decisions", "ticker", "name"),
    ]
    for table, ticker_col, name_col in candidates:
        if table not in tables:
            continue
        columns = {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if ticker_col not in columns or name_col not in columns:
            continue
        where = ""
        params: tuple[object, ...] = ()
        if "market" in columns:
            where = " WHERE market=?"
            params = (market,)
        for row in conn.execute(
            f"SELECT {ticker_col} AS ticker, {name_col} AS name FROM {table}{where}",
            params,
        ).fetchall():
            ticker = normalize_ticker(row[0], market)
            name = str(row[1] or "").strip()
            if ticker and name and name != ticker and not name.isdigit():
                result.setdefault(ticker, name)
    return result


def resolve_name(
    ticker: object,
    name: object | None,
    name_map: Mapping[str, str],
    market: str = "kr",
) -> str:
    code = normalize_ticker(ticker, market)
    candidate = str(name or "").strip()
    if candidate and candidate != code and not candidate.isdigit():
        return candidate
    resolved = str(name_map.get(code) or "").strip()
    if resolved and resolved != code and not resolved.isdigit():
        return resolved
    return "종목명 미확인" if market.lower() == "kr" else code


def display_symbol(name: object, ticker: object, market: str = "kr") -> str:
    """Return the user-facing security name.

    Korean screens show only the Korean company name. The numeric ticker remains
    available in dedicated ticker columns and internal order/API fields.
    """
    code = normalize_ticker(ticker, market)
    company = str(name or "").strip()
    valid_company = bool(company and company != code and not company.isdigit())
    if market.lower() == "kr":
        return company if valid_company else "종목명 미확인"
    return f"{company} ({code})" if valid_company else code
