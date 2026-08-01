from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest


def test_order_candidate_store_owner_isolation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['ADE_UI_STATE_DB'] = str(Path(tmp) / 'state.sqlite3')
        import dashboard.order_candidate_store as store
        importlib.reload(store)
        store.upsert_candidate('owner-a', 'kr', '005930', '삼성전자')
        store.upsert_candidate('owner-b', 'kr', '005930', '삼성전자')
        assert len(store.list_candidates('owner-a')) == 1
        assert len(store.list_candidates('owner-b')) == 1


def test_websocket_rejects_invalid_ticker() -> None:
    from broker.kis_websocket import KISWebSocketMarketClient

    client = KISWebSocketMarketClient()
    with pytest.raises(ValueError):
        client.subscribe('ABC')


def test_websocket_parser_rejects_short_payloads() -> None:
    from broker.kis_websocket import KISWebSocketMarketClient

    client = KISWebSocketMarketClient()
    assert client._parse_orderbook('005930^1^2') is None
    assert client._parse_trade('005930^123000^70000') is None


def test_market_metric_uses_last_bar_timestamp() -> None:
    from dashboard.market_overview_service import _history_metric

    index = pd.to_datetime(['2026-08-01T01:00:00Z', '2026-08-01T01:01:00Z'])
    history = pd.DataFrame({'Close': [100.0, 101.0]}, index=index)
    metric = _history_metric('TEST', 'TEST', history, 9999999999.0)
    assert metric.value == 101.0
    assert metric.updated_at == pytest.approx(index[-1].timestamp())


def test_kis_config_matches_broker_config_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    from broker.kis import kis_config_from_env

    monkeypatch.setenv('KIS_APP_KEY', 'key')
    monkeypatch.setenv('KIS_APP_SECRET', 'secret')
    monkeypatch.setenv('KIS_ACCOUNT_NO', '12345678')
    monkeypatch.setenv('KIS_ACCOUNT_PRODUCT_CODE', '01')
    monkeypatch.setenv('KIS_ENV', 'paper')
    monkeypatch.delenv('KIS_ACCOUNT', raising=False)

    config = kis_config_from_env()
    assert config.account_no == '12345678'
    assert config.account_product_code == '01'
    assert config.environment == 'paper'
    assert config.is_live is False


def test_kis_config_splits_full_account_number(monkeypatch: pytest.MonkeyPatch) -> None:
    from broker.kis import kis_config_from_env

    monkeypatch.setenv('KIS_APP_KEY', 'key')
    monkeypatch.setenv('KIS_APP_SECRET', 'secret')
    monkeypatch.setenv('KIS_ACCOUNT_NO', '12345678-01')
    monkeypatch.delenv('KIS_ACCOUNT_PRODUCT_CODE', raising=False)
    monkeypatch.delenv('KIS_PRODUCT_CODE', raising=False)
    monkeypatch.delenv('KIS_ACCOUNT', raising=False)

    config = kis_config_from_env()
    assert config.account_no == '12345678'
    assert config.account_product_code == '01'


def test_kis_config_rejects_invalid_account_length(monkeypatch: pytest.MonkeyPatch) -> None:
    from broker.base import BrokerError
    from broker.kis import kis_config_from_env

    monkeypatch.setenv('KIS_APP_KEY', 'key')
    monkeypatch.setenv('KIS_APP_SECRET', 'secret')
    monkeypatch.setenv('KIS_ACCOUNT_NO', '1234')
    monkeypatch.delenv('KIS_ACCOUNT', raising=False)

    with pytest.raises(BrokerError, match='exactly 8 digits'):
        kis_config_from_env()
