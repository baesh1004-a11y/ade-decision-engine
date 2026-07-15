from __future__ import annotations

import sqlite3
from pathlib import Path


def purge_disabled_us_replay(db_path: str | Path = "datahub/us_market.db") -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        table_names = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "us_universe" not in table_names or "replay_events" not in table_names:
            return {"events": 0, "flows": 0, "vectors": 0, "checkpoints": 0}

        stale_ids = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT e.event_id
                FROM replay_events e
                LEFT JOIN us_universe u ON u.symbol=e.ticker AND u.enabled=1
                WHERE e.market='us' AND u.symbol IS NULL
                """
            ).fetchall()
        ]
        stale_tickers = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT e.ticker
                FROM replay_events e
                LEFT JOIN us_universe u ON u.symbol=e.ticker AND u.enabled=1
                WHERE e.market='us' AND u.symbol IS NULL
                """
            ).fetchall()
        ]

        counts = {"events": 0, "flows": 0, "vectors": 0, "checkpoints": 0}
        if stale_ids:
            placeholders = ",".join("?" for _ in stale_ids)
            if "replay_event_flow" in table_names:
                cur = conn.execute(
                    f"DELETE FROM replay_event_flow WHERE event_id IN ({placeholders})",
                    stale_ids,
                )
                counts["flows"] = max(0, int(cur.rowcount))
            if "replay_event_vectors" in table_names:
                cur = conn.execute(
                    f"DELETE FROM replay_event_vectors WHERE event_id IN ({placeholders})",
                    stale_ids,
                )
                counts["vectors"] = max(0, int(cur.rowcount))
            cur = conn.execute(
                f"DELETE FROM replay_events WHERE event_id IN ({placeholders})",
                stale_ids,
            )
            counts["events"] = max(0, int(cur.rowcount))

        if stale_tickers and "replay_build_state" in table_names:
            placeholders = ",".join("?" for _ in stale_tickers)
            cur = conn.execute(
                f"DELETE FROM replay_build_state WHERE market='us' AND ticker IN ({placeholders})",
                stale_tickers,
            )
            counts["checkpoints"] = max(0, int(cur.rowcount))

        conn.commit()
        return counts
    finally:
        conn.close()
