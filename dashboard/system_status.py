from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarketReadiness:
    db_exists: bool
    price_rows: int
    active_symbols: int
    replay_events: int
    replay_flows: int
    replay_vectors: int
    surge_patterns: int
    latest_price_date: str | None
    latest_replay_date: str | None
    latest_surge_date: str | None
    ready: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_market_db(db_path: str | Path, market: str) -> MarketReadiness:
    path = Path(db_path)
    if not path.exists():
        return MarketReadiness(
            False, 0, 0, 0, 0, 0, 0, None, None, None, False,
            (f"{path} 파일이 없습니다.",),
        )

    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        price_rows = _count(conn, "price_bars", "market=?", (market,)) if "price_bars" in tables else 0
        latest_price = _scalar(
            conn,
            "SELECT MAX(trade_date) FROM price_bars WHERE market=?",
            (market,),
        ) if "price_bars" in tables else None

        if market == "us" and "us_universe" in tables:
            active_symbols = _count(conn, "us_universe", "enabled=1")
        elif "price_bars" in tables:
            active_symbols = int(_scalar(
                conn,
                "SELECT COUNT(DISTINCT ticker) FROM price_bars WHERE market=?",
                (market,),
            ) or 0)
        else:
            active_symbols = 0

        replay_events = _count(conn, "replay_events", "market=?", (market,)) if "replay_events" in tables else 0
        replay_flows = int(_scalar(
            conn,
            """
            SELECT COUNT(*) FROM replay_event_flow f
            JOIN replay_events e ON e.event_id=f.event_id
            WHERE e.market=?
            """,
            (market,),
        ) or 0) if {"replay_event_flow", "replay_events"}.issubset(tables) else 0
        replay_vectors = int(_scalar(
            conn,
            """
            SELECT COUNT(*) FROM replay_event_vectors v
            JOIN replay_events e ON e.event_id=v.event_id
            WHERE e.market=?
            """,
            (market,),
        ) or 0) if {"replay_event_vectors", "replay_events"}.issubset(tables) else 0
        latest_replay = _scalar(
            conn,
            "SELECT MAX(event_date) FROM replay_events WHERE market=?",
            (market,),
        ) if "replay_events" in tables else None

        surge_patterns = _count(conn, "surge_patterns", "market=?", (market,)) if "surge_patterns" in tables else 0
        latest_surge = _scalar(
            conn,
            "SELECT MAX(surge_start_date) FROM surge_patterns WHERE market=?",
            (market,),
        ) if "surge_patterns" in tables else None

        issues: list[str] = []
        if price_rows <= 0:
            issues.append("가격 데이터가 없습니다.")
        if active_symbols <= 0:
            issues.append("활성 종목이 없습니다.")
        if replay_events <= 0:
            issues.append("Replay 이벤트가 없습니다.")
        if replay_flows <= 0:
            issues.append("Replay 흐름 데이터가 없습니다.")
        if replay_vectors <= 0:
            issues.append("Replay 벡터가 없습니다.")
        if surge_patterns <= 0:
            issues.append("급등직전 120일 패턴이 없습니다.")

        return MarketReadiness(
            db_exists=True,
            price_rows=price_rows,
            active_symbols=active_symbols,
            replay_events=replay_events,
            replay_flows=replay_flows,
            replay_vectors=replay_vectors,
            surge_patterns=surge_patterns,
            latest_price_date=str(latest_price) if latest_price else None,
            latest_replay_date=str(latest_replay) if latest_replay else None,
            latest_surge_date=str(latest_surge) if latest_surge else None,
            ready=not issues,
            issues=tuple(issues),
        )
    finally:
        conn.close()


def _count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple[object, ...] = ()) -> int:
    suffix = f" WHERE {where}" if where else ""
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}{suffix}", params).fetchone()[0])


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> object | None:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]
