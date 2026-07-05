from __future__ import annotations

import argparse

from broker.base import BrokerOrder
from broker.kis import kis_broker_from_env


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE KIS paper-order runner")
    parser.add_argument("ticker")
    parser.add_argument("quantity", type=int)
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument(
        "--send",
        action="store_true",
        help="send to KIS paper account; without this flag only a dry-run is performed",
    )
    args = parser.parse_args()

    broker = kis_broker_from_env()
    result = broker.place_order(
        BrokerOrder(
            market="kr",
            ticker=args.ticker,
            side=args.side,
            quantity=args.quantity,
            order_type="MARKET",
            dry_run=not args.send,
        )
    )
    print(result.to_dict())


if __name__ == "__main__":
    main()
