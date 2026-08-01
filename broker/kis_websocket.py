from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests
import websocket

from broker.base import BrokerError


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    quantity: int


@dataclass(frozen=True)
class KISOrderBookSnapshot:
    ticker: str
    received_at: float
    asks: tuple[OrderBookLevel, ...]
    bids: tuple[OrderBookLevel, ...]
    total_ask_quantity: int
    total_bid_quantity: int


class KISWebSocketOrderBookClient:
    """KIS domestic-stock paper/live WebSocket orderbook client.

    This client subscribes to the domestic orderbook stream and keeps the latest
    snapshot in memory. It is intentionally read-only; order submission remains in
    the REST broker adapter.
    """

    PAPER_APPROVAL_URL = "https://openapivts.koreainvestment.com:29443/oauth2/Approval"
    LIVE_APPROVAL_URL = "https://openapi.koreainvestment.com:9443/oauth2/Approval"
    PAPER_WS_URL = "ws://ops.koreainvestment.com:31000"
    LIVE_WS_URL = "ws://ops.koreainvestment.com:21000"
    DOMESTIC_ORDERBOOK_TR_ID = "H0STASP0"

    def __init__(
        self,
        ticker: str,
        *,
        on_snapshot: Callable[[KISOrderBookSnapshot], None] | None = None,
    ) -> None:
        self.ticker = str(ticker).zfill(6)
        self.on_snapshot = on_snapshot
        self._latest: KISOrderBookSnapshot | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: websocket.WebSocketApp | None = None

    @property
    def latest(self) -> KISOrderBookSnapshot | None:
        with self._lock:
            return self._latest

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run_forever(self) -> None:
        retry = 1.0
        while not self._stop.is_set():
            try:
                approval_key = self._approval_key()
                ws_url = self._ws_url()
                self._ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=lambda ws: self._subscribe(ws, approval_key),
                    on_message=self._on_message,
                    on_error=lambda _ws, _err: None,
                    on_close=lambda _ws, _code, _msg: None,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
                retry = 1.0
            except Exception:
                time.sleep(retry)
                retry = min(15.0, retry * 2)

    def _approval_key(self) -> str:
        app_key = os.getenv("KIS_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        if not app_key or not app_secret:
            raise BrokerError("KIS WebSocket requires KIS_APP_KEY and KIS_APP_SECRET")
        response = requests.post(
            self.PAPER_APPROVAL_URL if self._is_paper() else self.LIVE_APPROVAL_URL,
            json={"grant_type": "client_credentials", "appkey": app_key, "secretkey": app_secret},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        key = payload.get("approval_key")
        if not key:
            raise BrokerError(f"KIS approval response missing approval_key: {payload}")
        return str(key)

    def _subscribe(self, ws: websocket.WebSocket, approval_key: str) -> None:
        payload = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": self.DOMESTIC_ORDERBOOK_TR_ID,
                    "tr_key": self.ticker,
                }
            },
        }
        ws.send(json.dumps(payload))

    def _on_message(self, _ws: websocket.WebSocketApp, message: str) -> None:
        if not message or message.startswith("{"):
            return
        snapshot = self._parse_orderbook(message)
        if snapshot is None:
            return
        with self._lock:
            self._latest = snapshot
        if self.on_snapshot:
            self.on_snapshot(snapshot)

    def _parse_orderbook(self, message: str) -> KISOrderBookSnapshot | None:
        # KIS real-time messages use: encryption|tr_id|count|payload.
        parts = message.split("|", 3)
        if len(parts) != 4 or parts[1] != self.DOMESTIC_ORDERBOOK_TR_ID:
            return None
        fields = parts[3].split("^")
        if len(fields) < 59:
            return None

        def number(index: int) -> float:
            try:
                return float(str(fields[index]).replace(",", ""))
            except (TypeError, ValueError, IndexError):
                return 0.0

        asks = tuple(
            OrderBookLevel(price=number(3 + i), quantity=int(number(23 + i)))
            for i in range(10)
        )
        bids = tuple(
            OrderBookLevel(price=number(13 + i), quantity=int(number(33 + i)))
            for i in range(10)
        )
        return KISOrderBookSnapshot(
            ticker=self.ticker,
            received_at=time.time(),
            asks=asks,
            bids=bids,
            total_ask_quantity=int(number(43)),
            total_bid_quantity=int(number(44)),
        )

    def _is_paper(self) -> bool:
        return os.getenv("KIS_ENV", "paper").strip().lower() != "live"

    def _ws_url(self) -> str:
        return self.PAPER_WS_URL if self._is_paper() else self.LIVE_WS_URL
