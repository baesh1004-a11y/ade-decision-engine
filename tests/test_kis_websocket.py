from broker.kis_websocket import KISWebSocketMarketClient


def test_parse_orderbook_snapshot() -> None:
    client = KISWebSocketMarketClient()
    fields = ["005930", "090000", "0"]
    fields += [str(70000 + i * 100) for i in range(10)]
    fields += [str(69900 - i * 100) for i in range(10)]
    fields += [str(1000 + i) for i in range(10)]
    fields += [str(2000 + i) for i in range(10)]
    fields += ["12345", "23456"]
    snapshot = client._parse_orderbook("^".join(fields))
    assert snapshot is not None
    assert snapshot.ticker == "005930"
    assert snapshot.asks[0].price == 70000
    assert snapshot.bids[0].price == 69900
    assert snapshot.total_ask_quantity == 12345
    assert snapshot.total_bid_quantity == 23456


def test_parse_trade_snapshot() -> None:
    client = KISWebSocketMarketClient()
    fields = ["005930", "101530", "70100", "2", "500", "0.72", "0", "69500", "70500", "69000", "0", "0", "31", "123456"]
    fields += ["0", "0", "0", "0", "121.55"]
    fields += ["0"] * 12
    snapshot = client._parse_trade("^".join(fields))
    assert snapshot is not None
    assert snapshot.ticker == "005930"
    assert snapshot.price == 70100
    assert snapshot.change_rate == 0.72
    assert snapshot.volume == 31
    assert snapshot.accumulated_volume == 123456
    assert snapshot.trade_strength == 121.55
