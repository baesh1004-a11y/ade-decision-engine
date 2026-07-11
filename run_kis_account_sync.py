from __future__ import annotations

import argparse
import json

from broker.kis_account_sync import KISAccountSync


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize KIS paper account into ADE DB")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()

    sync = KISAccountSync(args.db)
    try:
        snapshot, positions = sync.sync()
    finally:
        sync.close()

    print(json.dumps({"account": snapshot.to_dict(), "positions": positions}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
