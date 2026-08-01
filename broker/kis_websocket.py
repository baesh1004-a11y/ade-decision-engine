from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from collections import OrderedDict, defaultdict
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
    """Shared KIS domestic market-data WebSocket client with session leases."""

    PAPER_APPROVAL_URL = "https://openapivts.koreainvestment.com:29443/oauth2/Approval"
    LIVE_APPROVAL_URL = "https://openapi.koreainvestment.com:9443/oauth2/Approval"
    PAPER_WS_URL = "ws://ops.koreainvestment.com:31000"
    LIVE_WS_URL = "ws://ops.koreainvestment.com:21000"
    ORDERBOOK_TR_ID = "H0STASP0"
    TRADE_TR_ID = "H0STCNT0"
    MAX_ACTIVE_TICKERS = 20
    APPROVAL_KEY_TTL_SECONDS = 3600
    SNAPSHOT_TTL_SECONDS = 120
    ORDERBOOK_MIN_FIELDS = 45
    TRADE_MIN_FIELDS = 30

    def __init__(self) -> None:
        self._orderbooks: dict[str, KISOrderBookSnapshot] = {}
        self._trades: dict[str, KISTradeSnapshot] = {}
        self._subscriptions: OrderedDict[str, float] = OrderedDict()
        self._leases: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._send_lock = threading.RLock()
        self._approval_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: websocket.WebSocketApp | None = None
        self._approval_key: str | None = None
        self._approval_key_obtained_at = 0.0
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.connected = False
        self.parse_error_count = 0
        self.send_error_count = 0
        self.last_parse_error: str | None = None

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        normalized = str(ticker or "").strip()
        if not re.fullmatch(r"\d{6}", normalized):
            raise ValueError("KIS domestic ticker must be exactly 6 digits")
        return normalized

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_forever, daemon=True, name="kis-market-ws")
            self._thread.start()

    def stop(self, join_timeout: float = 3.0) -> None:
        self._stop.set()
        with self._lock:
            ws = self._ws
            thread = self._thread
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)

    def acquire(self, owner_id: str, ticker: str) -> None:
        normalized = self._normalize_ticker(ticker)
        owner = str(owner_id or "anonymous")
        with self._lock:
            first = not self._leases[normalized]
            self._leases[normalized].add(owner)
            self._subscriptions.pop(normalized, None)
            self._subscriptions[normalized] = time.time()
            if len(self._subscriptions) > self.MAX_ACTIVE_TICKERS:
                self._set_error_locked("KIS realtime active ticker limit reached")
        self.start()
        if first:
            self._send_for_current_connection((normalized,), subscribe=True)

    def release(self, owner_id: str, ticker: str) -> None:
        normalized = self._normalize_ticker(ticker)
        owner = str(owner_id or "anonymous")
        should_unsubscribe = False
        with self._lock:
            owners = self._leases.get(normalized)
            if owners:
                owners.discard(owner)
                if not owners:
                    self._leases.pop(normalized, None)
                    self._subscriptions.pop(normalized, None)
                    should_unsubscribe = True
        if should_unsubscribe:
            self._send_for_current_connection((normalized,), subscribe=False)
            self._drop_snapshots(normalized)

    def release_owner(self, owner_id: str) -> None:
        owner = str(owner_id or "anonymous")
        with self._lock:
            tickers = tuple(t for t, owners in self._leases.items() if owner in owners)
        for ticker in tickers:
            self.release(owner, ticker)

    def subscribe(self, ticker: str) -> None:
        self.acquire("legacy", ticker)

    def unsubscribe(self, ticker: str) -> None:
        self.release("legacy", ticker)

    def set_active_tickers(self, tickers: tuple[str, ...] | list[str]) -> None:
        owner = "legacy-set"
        desired = tuple(dict.fromkeys(self._normalize_ticker(t) for t in tickers))[-self.MAX_ACTIVE_TICKERS:]
        with self._lock:
            current = tuple(t for t, owners in self._leases.items() if owner in owners)
        for ticker in set(current) - set(desired):
            self.release(owner, ticker)
        for ticker in desired:
            self.acquire(owner, ticker)

    def subscribed_tickers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._subscriptions.keys())

    def latest_received_at(self) -> float | None:
        with self._lock:
            times = [item.received_at for item in self._orderbooks.values()]
            times.extend(item.received_at for item in self._trades.values())
            return max(times) if times else None

    def health_snapshot(self) -> dict[str, object]:
        self._cleanup_snapshots()
        with self._lock:
            times = [item.received_at for item in self._orderbooks.values()]
            times.extend(item.received_at for item in self._trades.values())
            latest = max(times) if times else None
            return {
                "connected": self.connected,
                "subscription_count": len(self._subscriptions),
                "subscribed_tickers": tuple(self._subscriptions.keys()),
                "lease_count": sum(len(v) for v in self._leases.values()),
                "latest_received_at": latest,
                "last_error": self.last_error,
                "last_error_at": self.last_error_at,
                "parse_error_count": self.parse_error_count,
                "send_error_count": self.send_error_count,
                "last_parse_error": self.last_parse_error,
                "orderbook_snapshot_count": len(self._orderbooks),
                "trade_snapshot_count": len(self._trades),
            }

    def latest_orderbook(self, ticker: str) -> KISOrderBookSnapshot | None:
        normalized = self._normalize_ticker(ticker)
        with self._lock:
            item = self._orderbooks.get(normalized)
            if item and time.time() - item.received_at <= self.SNAPSHOT_TTL_SECONDS:
                return item
        return None

    def latest_trade(self, ticker: str) -> KISTradeSnapshot | None:
        normalized = self._normalize_ticker(ticker)
        with self._lock:
            item = self._trades.get(normalized)
            if item and time.time() - item.received_at <= self.SNAPSHOT_TTL_SECONDS:
                return item
        return None

    def _drop_snapshots(self, ticker: str) -> None:
        with self._lock:
            self._orderbooks.pop(ticker, None)
            self._trades.pop(ticker, None)

    def _cleanup_snapshots(self) -> None:
        cutoff = time.time() - self.SNAPSHOT_TTL_SECONDS
        with self._lock:
            active = set(self._subscriptions)
            for ticker, item in list(self._orderbooks.items()):
                if ticker not in active or item.received_at < cutoff:
                    self._orderbooks.pop(ticker, None)
            for ticker, item in list(self._trades.items()):
                if ticker not in active or item.received_at < cutoff:
                    self._trades.pop(ticker, None)

    def _run_forever(self) -> None:
        retry = 1.0
        while not self._stop.is_set():
            try:
                approval_key = self._request_approval_key()
                with self._lock:
                    self._approval_key = approval_key
                    self._ws = websocket.WebSocketApp(
                        self._ws_url(),
                        on_open=lambda ws: self._on_open(ws, approval_key),
                        on_message=self._on_message,
                        on_error=self._on_error,
                        on_close=self._on_close,
                    )
                    ws = self._ws
                ws.run_forever(ping_interval=30, ping_timeout=10)
                retry = 1.0
            except Exception as exc:
                self._set_error(str(exc))
                with self._lock:
                    self.connected = False
                if self._stop.wait(retry + random.uniform(0, min(1.0, retry / 4))):
                    break
                retry = min(30.0, retry * 2)

    def _on_open(self, ws: websocket.WebSocketApp, approval_key: str) -> None:
        with self._lock:
            self.connected = True
            self.last_error = None
            self.last_error_at = None
            tickers = tuple(self._subscriptions.keys())
        self._send_subscription_messages(ws, approval_key, tickers, subscribe=True)

    def _on_error(self, _ws: websocket.WebSocketApp, error: object) -> None:
        self._set_error(str(error))
        with self._lock:
            self.connected = False

    def _on_close(self, _ws: websocket.WebSocketApp, _code: int | None, message: str | None) -> None:
        with self._lock:
            self.connected = False
        if message:
            self._set_error(message)

    def _set_error_locked(self, message: str) -> None:
        self.last_error = message
        self.last_error_at = time.time()

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._set_error_locked(message)

    def _record_parse_error(self, message: str) -> None:
        with self._lock:
            self.parse_error_count += 1
            self.last_parse_error = message

    def _send_for_current_connection(self, tickers: tuple[str, ...], *, subscribe: bool) -> None:
        with self._lock:
            connected = self.connected
            ws = self._ws
            approval_key = self._approval_key
        if connected and ws is not None and approval_key:
            self._send_subscription_messages(ws, approval_key, tickers, subscribe=subscribe)

    def _safe_send(self, ws: websocket.WebSocketApp, message: str) -> None:
        try:
            with self._send_lock:
                ws.send(message)
        except Exception as exc:
            with self._lock:
                self.send_error_count += 1
                self._set_error_locked(f"WebSocket send failed: {exc}")
            raise

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
                self._safe_send(ws, json.dumps(payload))
                time.sleep(0.05)

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        if not message:
            return
        if message.startswith("{"):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                self._record_parse_error("invalid JSON control frame")
                return
            header = payload.get("header") or {}
            if str(header.get("tr_id")) == "PINGPONG":
                try:
                    self._safe_send(ws, message)
                except Exception:
                    pass
                return
            body = payload.get("body") or {}
            rt_cd = str(body.get("rt_cd") or payload.get("rt_cd") or "")
            if rt_cd and rt_cd != "0":
                message_text = str(body.get("msg1") or payload.get("msg1") or "KIS realtime subscription error")
                self._set_error(message_text)
                if "approval" in message_text.lower() or "key" in message_text.lower():
                    with self._approval_lock:
                        self._approval_key = None
                        self._approval_key_obtained_at = 0.0
                    try:
                        ws.close()
                    except Exception:
                        pass
            elif rt_cd == "0":
                with self._lock:
                    self.last_error = None
                    self.last_error_at = None
            return

        parts = message.split("|", 3)
        if len(parts) != 4:
            self._record_parse_error("invalid realtime frame")
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
        return float(str(fields[index]).replace(",", ""))

    def _parse_orderbook(self, payload: str) -> KISOrderBookSnapshot | None:
        fields = payload.split("^")
        if len(fields) < self.ORDERBOOK_MIN_FIELDS:
            self._record_parse_error("orderbook field count too small")
            return None
        try:
            ticker = self._normalize_ticker(fields[0])
            asks = tuple(OrderBookLevel(self._number(fields, 3 + i), int(self._number(fields, 23 + i))) for i in range(10))
            bids = tuple(OrderBookLevel(self._number(fields, 13 + i), int(self._number(fields, 33 + i))) for i in range(10))
            total_ask = int(self._number(fields, 43))
            total_bid = int(self._number(fields, 44))
        except (ValueError, IndexError) as exc:
            self._record_parse_error(f"orderbook parse failed: {exc}")
            return None
        if not asks or not bids or any(level.price <= 0 or level.quantity < 0 for level in asks + bids):
            self._record_parse_error("orderbook contains invalid price or quantity")
            return None
        if total_ask < 0 or total_bid < 0:
            self._record_parse_error("orderbook contains invalid totals")
            return None
        return KISOrderBookSnapshot(ticker, time.time(), asks, bids, total_ask, total_bid)

    def _parse_trade(self, payload: str) -> KISTradeSnapshot | None:
        fields = payload.split("^")
        if len(fields) < self.TRADE_MIN_FIELDS:
            self._record_parse_error("trade field count too small")
            return None
        try:
            ticker = self._normalize_ticker(fields[0])
            trade_time = str(fields[1])
            price = self._number(fields, 2)
            change = self._number(fields, 4)
            change_rate = self._number(fields, 5)
            open_price = self._number(fields, 7)
            high = self._number(fields, 8)
            low = self._number(fields, 9)
            volume = int(self._number(fields, 12))
            accumulated_volume = int(self._number(fields, 13))
            trade_strength = self._number(fields, 18)
        except (ValueError, IndexError) as exc:
            self._record_parse_error(f"trade parse failed: {exc}")
            return None
        if not re.fullmatch(r"\d{6}", trade_time):
            self._record_parse_error("trade time must be HHMMSS")
            return None
        hh, mm, ss = int(trade_time[:2]), int(trade_time[2:4]), int(trade_time[4:])
        if hh > 23 or mm > 59 or ss > 59 or price <= 0 or volume < 0 or accumulated_volume < 0 or abs(change_rate) > 40:
            self._record_parse_error("trade contains out-of-range values")
            return None
        return KISTradeSnapshot(
            ticker=ticker,
            received_at=time.time(),
            trade_time=trade_time,
            price=price,
            change=change,
            change_rate=change_rate,
            volume=volume,
            accumulated_volume=accumulated_volume,
            trade_strength=trade_strength,
            open=open_price,
            high=high,
            low=low,
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
                raise BrokerError("KIS approval response missing approval_key")
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
        self.ticker = KISWebSocketMarketClient._normalize_ticker(ticker)
        self.on_snapshot = on_snapshot
        self._client = shared_market_client()
        self._owner_id = f"facade:{id(self)}"

    @property
    def latest(self) -> KISOrderBookSnapshot | None:
        snapshot = self._client.latest_orderbook(self.ticker)
        if snapshot is not None and self.on_snapshot:
            self.on_snapshot(snapshot)
        return snapshot

    def start(self) -> None:
        self._client.acquire(self._owner_id, self.ticker)

    def stop(self) -> None:
        self._client.release(self._owner_id, self.ticker)
