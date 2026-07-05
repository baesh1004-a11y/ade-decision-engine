from broker.kis import kis_broker_from_env


def main() -> None:
    print("=== ADE KIS Login Test ===")
    broker = kis_broker_from_env()
    print("✅ Broker created")

    cash = broker.get_cash()
    print(f"💰 Available Cash: {cash:,.0f} KRW")

    positions = broker.get_positions()
    print(f"📈 Positions: {len(positions)}")
    for p in positions:
        print(f" - {p.ticker} {p.quantity}주 @ {p.current_price}")


if __name__ == "__main__":
    main()
