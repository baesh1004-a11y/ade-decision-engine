from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

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


@dataclass(frozen=True)
class KISTradeSnapshot:
    ticker: str
    received_at: float
    trade_time: str
    price: float
    change: float
    change_rate: float
    volume: int
    accumulated_volume: int
    trade_strength: float
    open: float
    high: float
    low: float


class KISWebSocketMarketClient:
    """Shared KIS domestic market-data WebSocket client with bounded subscriptions."""

    PAPER_APPROVAL_URL = "https://openapivts.koreainvestment.com:29443/oauth2/Approval"
    LIVE_APPROVAL_URL = "https://openapi.koreainvestment.com:9443/oauth2/Approval"
    PAPER_WS_URL = "ws://ops.koreainvestment.com:31000"
    LIVE_WS_URL = "ws://ops.koreainvestment.com:21000"
    ORDERBOOK_TR_ID = "H0STASP0"
    TRADE_TR_ID = "H0STCNT0"
    MAX_ACTIVE_TICKERS = 5
    APPROVAL_KEY_TTL_SECONDS = 3600

    def __init__(self) -> None:
        self._orderbooks: dict[str, KISOrderBookSnapshot] = {}
        self._trades: dict[str, KISTradeSnapshot] = {}
        self._subscriptions: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.RLock()
        self._approval_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: websocket.WebSocketApp | None = None
        self._approval_key: str | None = None
        self._approval_key_obtained_at = 0.0
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.connected = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="kis-market-ws")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def subscribe(self, ticker: str) -> None:
        normalized = str(ticker).zfill(6)
        removed: list[str] = []
        with self._lock:
            first = normalized not in self._subscriptions
            self._subscriptions.pop(normalized, None)
            self._subscriptions[normalized] = time.time()
            while len(self._subscriptions) > self.MAX_ACTIVE_TICKERS:
                old, _ = self._subscriptions.popitem(last=False)
                removed.append(old)
        self.start()
        if self.connected and self._ws is not None and self._approval_key:
            if first:
                self._send_subscription_messages(self._ws, self._approval_key, (normalized,), subscribe=True)
            for old in removed:
                self._send_subscription_messages(self._ws, self._approval_key, (old,), subscribe=False)
                self._drop_snapshots(old)

    def unsubscribe(self, ticker: str) -> None:
        normalized = str(ticker).zfill(6)
        with self._lock:
            existed = normalized in self._subscriptions
            self._subscriptions.pop(normalized, None)
        if existed and self.connected and self._ws is not None and self._approval_key:
            self._send_subscription_messages(self._ws, self._approval_key, (normalized,), subscribe=False)
        self._drop_snapshots(normalized)

    def set_active_tickers(self, tickers: tuple[str, ...] | list[str]) -> None:
        normalized = tuple(dict.fromkeys(str(t).zfill(6) for t in tickers))[-self.MAX_ACTIVE_TICKERS:]
        current = set(self.subscribed_tickers())
        desired = set(normalized)
        for ticker in current - desired:
            self.unsubscribe(ticker)
        for ticker in normalized:
            self.subscribe(ticker)

    def subscribed_tickers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._subscriptions.keys())

    def latest_received_at(self) -> float | None:
        with self._lock:
            times = [item.received_at for item in self._orderbooks.values()]
            times.extend(item.received_at for item in self._trades.values())
            return max(times) if times else None

    def health_snapshot(self) -> dict[str, object]:
        latest = self.latest_received_at()
        return {
            "connected": self.connected,
            "subscription_count": len(self.subscribed_tickers()),
            "subscribed_tickers": self.subscribed_tickers(),
            "latest_received_at": latest,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
        }

    def latest_orderbook(self, ticker: str) -> KISOrderBookSnapshot | None:
        with self._lock:
            return self._orderbooks.get(str(ticker).zfill(6))

    def latest_trade(self, ticker: str) -> KISTradeSnapshot | None:
        with self._lock:
            return self._trades.get(str(ticker).zfill(6))

    def _drop_snapshots(self, ticker: str) -> None:
        with self._lock:
            self._orderbooks.pop(ticker, None)
            self._trades.pop(ticker, None)

    def _run_forever(self) -> None:
        retry = 1.0
        while not self._stop.is_set():
            try:
                approval_key = self._request_approval_key()
                self._approval_key = approval_key
                self._ws = websocket.WebSocketApp(
                    self._ws_url(),
                    on_open=lambda ws: self._on_open(ws, approval_key),
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
                retry = 1.0
            except Exception as exc:
                self._set_error(str(exc))
                self.connected = False
                time.sleep(retry)
                retry = min(15.0, retry * 2)

    def _on_open(self, ws: websocket.WebSocketApp, approval_key: str) -> None:
        self.connected = True
        self.last_error = None
        self.last_error_at = None
        self._send_subscription_messages(ws, approval_key, self.subscribed_tickers(), subscribe=True)

    def _on_error(self, _ws: websocket.WebSocketApp, error: object) -> None:
        self._set_error(str(error))
        self.connected = False

    def _on_close(self, _ws: websocket.WebSocketApp, _code: int | None, message: str | None) -> None:
        self.connected = False
        if message:
            self._set_error(message)

    def _set_error(self, message: str) -> None:
        self.last_error = message
        self.last_error_at = time.time()

    def _send_subscription_messages(
        self,
        ws: websocket.WebSocketApp,
        approval_key: str,
        tickers: tuple[str, ...],
        *,
        subscribe: bool,
    ) -> None:
        tr_type = "1" if subscribe else "2"
        for ticker in tickers:
            for tr_id in (self.ORDERBOOK_TR_ID, self.TRADE_TR_ID):
                payload = {
                    "header": {
                        "approval_key": approval_key,
                        "custtype": "P",
                        "tr_type": tr_type,
                        "content-type": "utf-8",
                    },
                    "body": {"input": {"tr_id": tr_id, "tr_key": ticker}},
                }
                ws.send(json.dumps(payload))
                time.sleep(0.05)

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        if not message:
            return
        if message.startswith("{"):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return
            header = payload.get("header") or {}
            if str(header.get("tr_id")) == "PINGPONG":
                try:
                    ws.send(message)
                except Exception:
                    pass
                return
            body = payload.get("body") or {}
            rt_cd = str(body.get("rt_cd") or payload.get("rt_cd") or "")
            if rt_cd and rt_cd != "0":
                self._set_error(str(body.get("msg1") or payload.get("msg1") or "KIS realtime subscription error"))
            elif rt_cd == "0":
                self.last_error = None
                self.last_error_at = None
            return

        parts = message.split("|", 3)
        if len(parts) != 4:
            return
        tr_id = parts[1]
        if tr_id == self.ORDERBOOK_TR_ID:
            snapshot = self._parse_orderbook(parts[3])
            if snapshot is not None:
                with self._lock:
                    self._orderbooks[snapshot.ticker] = snapshot
                self.last_error = None
                self.last_error_at = None
        elif tr_id == self.TRADE_TR_ID:
            snapshot = self._parse_trade(parts[3])
            if snapshot is not None:
                with self._lock:
                    self._trades[snapshot.ticker] = snapshot
                self.last_error = None
                self.last_error_at = None

    @staticmethod
    def _number(fields: list[str], index: int) -> float:
        try:
            return float(str(fields[index]).replace(",", ""))
        except (TypeError, ValueError, IndexError):
            return 0.0

    def _parse_orderbook(self, payload: str) -> KISOrderBookSnapshot | None:
        fields = payload.split("^")
        if len(fields) < 45:
            return None
        ticker = str(fields[0]).zfill(6)
        asks = tuple(OrderBookLevel(self._number(fields, 3 + i), int(self._number(fields, 23 + i))) for i in range(10))
        bids = tuple(OrderBookLevel(self._number(fields, 13 + i), int(self._number(fields, 33 + i))) for i in range(10))
        return KISOrderBookSnapshot(
            ticker=ticker,
            received_at=time.time(),
            asks=asks,
            bids=bids,
            total_ask_quantity=int(self._number(fields, 43)),
            total_bid_quantity=int(self._number(fields, 44)),
        )

    def _parse_trade(self, payload: str) -> KISTradeSnapshot | None:
        fields = payload.split("^")
        if len(fields) < 30:
            return None
        ticker = str(fields[0]).zfill(6)
        return KISTradeSnapshot(
            ticker=ticker,
            received_at=time.time(),
            trade_time=str(fields[1]),
            price=self._number(fields, 2),
            change=self._number(fields, 4),
            change_rate=self._number(fields, 5),
            open=self._number(fields, 7),
            high=self._number(fields, 8),
            low=self._number(fields, 9),
            volume=int(self._number(fields, 12)),
            accumulated_volume=int(self._number(fields, 13)),
            trade_strength=self._number(fields, 18),
        )

    def _request_approval_key(self) -> str:
        with self._approval_lock:
            now = time.time()
            if self._approval_key and now - self._approval_key_obtained_at < self.APPROVAL_KEY_TTL_SECONDS:
                return self._approval_key
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
            self._approval_key = str(key)
            self._approval_key_obtained_at = now
            return self._approval_key

    @staticmethod
    def _is_paper() -> bool:
        return os.getenv("KIS_ENV", "paper").strip().lower() != "live"

    def _ws_url(self) -> str:
        return self.PAPER_WS_URL if self._is_paper() else self.LIVE_WS_URL


_SHARED_MARKET_CLIENT = KISWebSocketMarketClient()


def shared_market_client() -> KISWebSocketMarketClient:
    return _SHARED_MARKET_CLIENT


class KISWebSocketOrderBookClient:
    """Backward-compatible single-ticker facade over the shared market client."""

    def __init__(
        self,
        ticker: str,
        *,
        on_snapshot: Callable[[KISOrderBookSnapshot], None] | None = None,
    ) -> None:
        self.ticker = str(ticker).zfill(6)
        self.on_snapshot = on_snapshot
        self._client = shared_market_client()

    @property
    def latest(self) -> KISOrderBookSnapshot | None:
        snapshot = self._client.latest_orderbook(self.ticker)
        if snapshot is not None and self.on_snapshot:
            self.on_snapshot(snapshot)
        return snapshot

    def start(self) -> None:
        self._client.subscribe(self.ticker)

    def stop(self) -> None:
        self._client.unsubscribe(self.ticker)
