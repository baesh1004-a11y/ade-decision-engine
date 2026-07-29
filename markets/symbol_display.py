from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping


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


def build_name_map(
    conn: sqlite3.Connection,
    market: str = "kr",
    tickers: Iterable[object] | None = None,
) -> dict[str, str]:
    """Collect company names in authoritative priority order.

    When ``tickers`` is supplied, only rows relevant to those securities are
    queried. This avoids scanning large history tables for screens that display
    only a small recommendation set.
    """
    requested_raw = {
        str(value or "").strip()
        for value in (tickers or ())
        if str(value or "").strip()
    }
    requested_normalized = {
        normalize_ticker(value, market)
        for value in requested_raw
        if normalize_ticker(value, market)
    }
    restrict = tickers is not None
    if restrict and not requested_normalized:
        return {}

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

        clauses: list[str] = []
        params: list[object] = []
        if "market" in columns:
            clauses.append("market=?")
            params.append(market)
        if restrict:
            lookup_values = sorted(requested_raw | requested_normalized)
            placeholders = ",".join("?" for _ in lookup_values)
            clauses.append(f"{ticker_col} IN ({placeholders})")
            params.extend(lookup_values)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        for row in conn.execute(
            f"SELECT {ticker_col} AS ticker, {name_col} AS name FROM {table}{where}",
            tuple(params),
        ).fetchall():
            ticker = normalize_ticker(row[0], market)
            if restrict and ticker not in requested_normalized:
                continue
            name = str(row[1] or "").strip()
            if ticker and name and name != ticker and not name.isdigit():
                result.setdefault(ticker, name)

        if restrict and requested_normalized.issubset(result):
            break
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
