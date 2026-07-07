from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Replay DB validator")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM replay_events").fetchone()["c"]
        flows = conn.execute("SELECT COUNT(*) AS c FROM replay_event_flow").fetchone()["c"]
        future = conn.execute("SELECT COUNT(*) AS c FROM replay_events WHERE event_date > ?", (date.today().isoformat(),)).fetchone()["c"]
        malformed = conn.execute("SELECT COUNT(*) AS c FROM replay_events WHERE event_id LIKE '2.0:%'").fetchone()["c"]
        null_perf = conn.execute("SELECT COUNT(*) AS c FROM replay_events WHERE max_return IS NULL OR max_drawdown IS NULL").fetchone()["c"]
        short_flow = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM (
                SELECT event_id, COUNT(*) AS flow_count
                FROM replay_event_flow
                GROUP BY event_id
                HAVING flow_count < 40
            )
            """
        ).fetchone()["c"]
        stats = conn.execute(
            """
            SELECT
                AVG(max_return) AS avg_max_return,
                MIN(max_return) AS min_max_return,
                MAX(max_return) AS max_max_return,
                AVG(max_drawdown) AS avg_max_drawdown,
                MIN(max_drawdown) AS min_max_drawdown,
                MAX(max_drawdown) AS max_max_drawdown
            FROM replay_events
            WHERE max_return IS NOT NULL AND max_drawdown IS NOT NULL
            """
        ).fetchone()

        print("\n========================================")
        print(" ADE REPLAY DB VALIDATION")
        print("========================================")
        print(f"DB Path            : {DB_PATH}")
        print(f"Replay Events      : {total}")
        print(f"Replay Flow Rows   : {flows}")
        print(f"Future Dates       : {future}")
        print(f"Old Event ID Style : {malformed}")
        print(f"Null Performance   : {null_perf}")
        print(f"Short Flows < 40d  : {short_flow}")
        print("\nPerformance Summary")
        print(f"Avg Max Return     : {stats['avg_max_return']}")
        print(f"Min/Max Return     : {stats['min_max_return']} / {stats['max_max_return']}")
        print(f"Avg Max Drawdown   : {stats['avg_max_drawdown']}")
        print(f"Min/Max Drawdown   : {stats['min_max_drawdown']} / {stats['max_max_drawdown']}")

        print("\nRecent Events Sample")
        rows = conn.execute(
            """
            SELECT event_id, market, ticker, name, event_date, event_end_date,
                   event_end_reason, money_ratio_120d, max_return, max_drawdown
            FROM replay_events
            ORDER BY event_date DESC, money_ratio_120d DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        for row in rows:
            print(
                f"{row['event_id']} {row['name'] or ''} date={row['event_date']} "
                f"end={row['event_end_date']} reason={row['event_end_reason']} "
                f"money={row['money_ratio_120d']}x max={row['max_return']}% mdd={row['max_drawdown']}%"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
