from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from replay.vector_store import ReplayVectorStore
from state.vector import ADEStateVectorEngine


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v2 Replay State Vector Builder")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    price_repo = PriceRepository(DB_PATH)
    vector_store = ReplayVectorStore(DB_PATH)
    engine = ADEStateVectorEngine()
    saved = 0
    try:
        rows = vector_store.conn.execute("SELECT event_id, market, ticker, event_date FROM replay_events ORDER BY event_date").fetchall()
        if args.limit > 0:
            rows = rows[: args.limit]
        for idx, row in enumerate(rows, start=1):
            data = price_repo.fetch_dataframe(row["market"], row["ticker"], source="fdr")
            df = data.copy()
            dates = pd.to_datetime(df["Date"]).dt.date.astype(str)
            matches = dates[dates == row["event_date"]]
            if matches.empty:
                continue
            event_index = int(matches.index[0])
            window = df.iloc[max(0, event_index - 119) : event_index + 1]
            state_vector = engine.extract(window)
            vector_store.save(row["event_id"], state_vector.vector, state_vector.feature_names, state_vector.labels)
            saved += 1
            if saved % 100 == 0:
                vector_store.commit()
            print(f"[{idx}/{len(rows)}] {row['event_id']} vector_saved")
        vector_store.commit()
    finally:
        price_repo.close()
        total = vector_store.count()
        vector_store.close()

    print("\n========================================")
    print(" ADE v2 STATE VECTOR BUILD")
    print("========================================")
    print(f"Saved vectors : {saved}")
    print(f"Total vectors : {total}")


if __name__ == "__main__":
    main()
