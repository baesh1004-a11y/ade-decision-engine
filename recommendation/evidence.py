"""Recommendation evidence, independent of Streamlit, with append-only snapshots."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any

import pandas as pd

from core.run_models import canonical_json, content_hash, utc_now

BAR_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
SNAPSHOT_VERSION = 1


def decode(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}
    return result if isinstance(result, dict) else {}


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


@dataclass(frozen=True)
class Evidence:
    current: pd.DataFrame
    historical: pd.DataFrame
    pattern: dict
    warnings: tuple[str, ...]
    source: str
    frozen: bool = False
    captured_at: str = ""
    digest: str = ""


class EvidenceIntegrityError(ValueError):
    pass


def _frame(rows) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows]).rename(
        columns={
            "trade_date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )


def _current(conn, market: str, ticker: str, cutoff: str):
    if not table_exists(conn, "price_bars"):
        return pd.DataFrame(), ""
    source_row = conn.execute(
        "SELECT source,COUNT(*) AS n FROM price_bars WHERE market=? AND ticker=? AND trade_date<=? "
        "GROUP BY source ORDER BY (source=?) DESC,n DESC,source LIMIT 1",
        (market, ticker, cutoff, "fdr" if market == "kr" else "yfinance"),
    ).fetchone()
    if not source_row:
        return pd.DataFrame(), ""
    source = str(source_row["source"])
    frame = (
        _frame(
            conn.execute(
                "SELECT * FROM price_bars WHERE market=? AND ticker=? AND source=? AND trade_date<=? "
                "ORDER BY trade_date DESC LIMIT 120",
                (market, ticker, source, cutoff),
            ).fetchall()
        )
        .sort_values("Date")
        .reset_index(drop=True)
    )
    return frame, source


def _historical(conn, market: str, match: dict):
    if not match or not table_exists(conn, "surge_patterns"):
        return pd.DataFrame(), {}, []
    pattern_id = str(match.get("pattern_id") or "")
    event_id = str(match.get("source_event_id") or match.get("event_id") or "")
    event_date = str(match.get("event_date") or "")[:10]
    # An exact pattern identity wins over other versions of the same source event.
    if pattern_id:
        rows = conn.execute(
            "SELECT * FROM surge_patterns WHERE market=? AND pattern_id=?",
            (str(match.get("market") or market), pattern_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM surge_patterns WHERE market=? AND "
            "(pattern_id=? OR (source_event_id=? AND surge_start_date=?))",
            (str(match.get("market") or market), event_id, event_id, event_date),
        ).fetchall()
    if len(rows) > 1:
        return (
            pd.DataFrame(),
            {},
            ["동일 사례의 패턴 버전이 여러 개입니다. 원천 패턴을 확정할 수 없습니다."],
        )
    if not rows:
        return pd.DataFrame(), {}, []
    pattern = dict(rows[0])
    historical = pd.DataFrame()
    if table_exists(conn, "surge_pattern_bars"):
        historical = _frame(
            conn.execute(
                "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index",
                (pattern["pattern_id"],),
            ).fetchall()
        )
    return historical, pattern, []


def _warnings(current, historical, warnings):
    result = list(warnings)
    if len(current) < 120:
        result.append(
            f"추천 시점 가격 이력이 {len(current)}거래일입니다. 120거래일 비교 자료가 필요합니다."
        )
    if len(historical) < 120:
        result.append("선택한 과거 사례의 120거래일 원천 차트가 충분하지 않습니다.")
    return tuple(result)


def read_live_evidence(
    conn, market: str, selected: dict, match: dict, cutoff: str
) -> Evidence:
    payload = decode(selected.get("payload_json"))
    cutoff = str(payload.get("recent_event_date") or cutoff)[:10]
    current, source = _current(conn, market, str(selected["ticker"]), cutoff)
    historical, pattern, warnings = _historical(conn, market, match)
    return Evidence(
        current, historical, pattern, _warnings(current, historical, warnings), source
    )


def initialize_evidence(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_evidence (
            run_id TEXT NOT NULL REFERENCES recommendation_runs(run_id),
            market TEXT NOT NULL, ticker TEXT NOT NULL, version INTEGER NOT NULL,
            captured_at TEXT NOT NULL, payload_json TEXT NOT NULL, content_hash TEXT NOT NULL,
            PRIMARY KEY(run_id,market,ticker)
        )
    """)


def _bars(frame: pd.DataFrame) -> list[dict]:
    # JSON round-tripping normalizes pandas scalars and missing values.
    return (
        json.loads(frame[BAR_COLUMNS].to_json(orient="records", double_precision=15))
        if not frame.empty
        else []
    )


def capture_run_evidence(
    conn,
    run_id: str,
    market: str,
    recommendations: list[dict],
    cutoff: str,
    parameters: dict,
) -> dict:
    """Join the caller's result transaction; never commit or replace existing rows."""
    captured_at = utc_now()
    hashes = {}
    for item in recommendations:
        ticker = str(item["ticker"])
        source_cutoff = str(item.get("recent_event_date") or cutoff)[:10]
        current, source = _current(conn, market, ticker, source_cutoff)
        matches = {}
        for match in item.get("replay_matches") or []:
            if not isinstance(match, dict):
                continue
            historical, pattern, warnings = _historical(conn, market, match)
            matches[content_hash(match)] = {
                "historical": _bars(historical),
                "pattern": pattern,
                "warnings": _warnings(current, historical, warnings),
            }
        payload = {
            "version": SNAPSHOT_VERSION,
            "run_id": run_id,
            "market": market,
            "ticker": ticker,
            "captured_at": captured_at,
            "cutoff": source_cutoff,
            "recommendation_hash": content_hash(item),
            "parameters": parameters,
            "current": _bars(current),
            "source": source,
            "matches": matches,
        }
        digest = content_hash(payload)
        conn.execute(
            "INSERT INTO recommendation_evidence VALUES(?,?,?,?,?,?,?)",
            (
                run_id,
                market,
                ticker,
                SNAPSHOT_VERSION,
                captured_at,
                canonical_json(payload),
                digest,
            ),
        )
        hashes[ticker] = digest
    return {"version": SNAPSHOT_VERSION, "captured_at": captured_at, "tickers": hashes}


def read_saved_evidence(
    conn, market: str, selected: dict, match: dict
) -> Evidence | None:
    if not selected.get("run_id"):
        return None
    manifest = None
    if table_exists(conn, "ade_run_artifacts"):
        manifest = conn.execute(
            "SELECT payload_json,content_hash FROM ade_run_artifacts "
            "WHERE run_id=? AND stage_name='PERSIST' AND name='evidence'",
            (selected["run_id"],),
        ).fetchone()
    row = None
    if table_exists(conn, "recommendation_evidence"):
        row = conn.execute(
            "SELECT * FROM recommendation_evidence WHERE run_id=? AND market=? AND ticker=?",
            (selected["run_id"], market, selected["ticker"]),
        ).fetchone()
    if row is None:
        # New recorded runs must never silently fall back to mutable source data.
        if manifest:
            raise EvidenceIntegrityError(
                "보관된 비교 자료가 누락되었습니다. 실행 기록을 확인하세요."
            )
        return None
    try:
        payload = json.loads(row["payload_json"])
        if content_hash(payload) != row["content_hash"]:
            raise ValueError("hash mismatch")
        if manifest:
            manifest_payload = json.loads(manifest["payload_json"])
            if (
                content_hash(manifest_payload) != manifest["content_hash"]
                or manifest_payload["tickers"][str(selected["ticker"])]
                != row["content_hash"]
            ):
                raise ValueError("manifest mismatch")
        if (
            payload["version"] != SNAPSHOT_VERSION
            or row["version"] != SNAPSHOT_VERSION
            or payload["run_id"] != selected["run_id"]
            or payload["market"] != market
            or payload["ticker"] != str(selected["ticker"])
            or payload["recommendation_hash"]
            != content_hash(decode(selected.get("payload_json")))
        ):
            raise ValueError("snapshot identity mismatch")
        evidence = payload["matches"][content_hash(match)]
        return Evidence(
            pd.DataFrame(payload["current"], columns=BAR_COLUMNS),
            pd.DataFrame(evidence["historical"], columns=BAR_COLUMNS),
            evidence["pattern"],
            tuple(evidence["warnings"]),
            payload["source"],
            True,
            payload["captured_at"],
            row["content_hash"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise EvidenceIntegrityError(
            "보관된 비교 자료의 무결성을 확인하지 못했습니다. 원천 시세로 대체하지 않습니다."
        ) from exc
