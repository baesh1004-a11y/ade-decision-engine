from __future__ import annotations

import json
import queue
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from broker.base import BrokerError
from broker.kis import kis_config_from_env

try:
    import websocket
except Exception:  # pragma: no cover - dependency/runtime guard
    websocket = None


LIVE_WS_URL = "ws://ops.koreainvestment.com:21000/tryitout"
PAPER_WS_URL = "ws://ops.koreainvestment.com:31000/tryitout"
TRADE_TR_ID = "H0STCNT0"
ORDERBOOK_TR_ID = "H0STASP0"


@dataclass
class RealtimeSnapshot:
    ticker: str
    connected: bool = False
    captured_at: str | None = None
    trades: list[dict[str, Any]] = field(default_factory=list)
    orderbook: dict[str, Any] | None = None
    messages: list[str] = field(default_factory=list)

    def candles(self, rule: str = "1min") -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        frame = pd.DataFrame(self.trades)
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date", "Close"]).set_index("Date").sort_index()
        if frame.empty:
            return pd.DataFrame()
        candles = frame["Close"].resample(rule).ohlc()
        candles.columns = ["Open", "High", "Low", "Close"]
        candles["Volume"] = frame["Volume"].resample(rule).sum()
        return candles.dropna(subset=["Close"]).reset_index()


class KISRealtimeClient:
    """Small blocking collector for KIS domestic-stock realtime trade/orderbook data.

    The client obtains a WebSocket approval key, subscribes to domestic execution
    and orderbook channels, then collects a short snapshot suitable for Streamlit.
    Secrets are read only through the existing KIS environment configuration.
    """

    def __init__(self, *, prefix: str = "KIS", verify_ssl: bool = True) -> None:
        if websocket is None:
            raise BrokerError("websocket-client 패키지가 필요합니다: pip install websocket-client")
        self.config = kis_config_from_env(prefix=prefix)
        self.verify_ssl = verify_ssl
        self.ws_url = LIVE_WS_URL if self.config.is_live else PAPER_WS_URL

    def collect(self, ticker: str, *, seconds: float = 5.0) -> RealtimeSnapshot:
        code = str(ticker).split(".", 1)[0].zfill(6)
        approval_key = self._approval_key()
        snapshot = RealtimeSnapshot(ticker=code)
        received: queue.Queue[str] = queue.Queue()
        opened = threading.Event()
        stopped = threading.Event()

        def on_open(ws) -> None:
            opened.set()
            ws.send(json.dumps(self._subscribe_body(approval_key, TRADE_TR_ID, code)))
            ws.send(json.dumps(self._subscribe_body(approval_key, ORDERBOOK_TR_ID, code)))

        def on_message(_ws, message: str) -> None:
            received.put(message)

        def on_error(_ws, error: object) -> None:
            snapshot.messages.append(f"WebSocket 오류: {error}")

        def on_close(_ws, status_code, close_msg) -> None:
            stopped.set()
            if status_code or close_msg:
                snapshot.messages.append(f"연결 종료: {status_code} {close_msg or ''}".strip())

        app = websocket.WebSocketApp(
            self.ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        sslopt = {} if self.verify_ssl else {"cert_reqs": ssl.CERT_NONE}
        worker = threading.Thread(
            target=app.run_forever,
            kwargs={"sslopt": sslopt, "ping_interval": 20, "ping_timeout": 10},
            daemon=True,
        )
        worker.start()
        if not opened.wait(timeout=8):
            app.close()
            raise BrokerError("KIS 실시간 WebSocket 연결 시간이 초과되었습니다.")

        snapshot.connected = True
        deadline = time.monotonic() + max(1.0, float(seconds))
        try:
            while time.monotonic() < deadline and not stopped.is_set():
                try:
                    message = received.get(timeout=0.25)
                except queue.Empty:
                    continue
                self._consume_message(message, snapshot, app)
        finally:
            app.close()
            worker.join(timeout=2)
            snapshot.captured_at = datetime.now().isoformat(timespec="seconds")
        return snapshot

    def _approval_key(self) -> str:
        base_url = self.config.base_url or (
            "https://openapi.koreainvestment.com:9443"
            if self.config.is_live
            else "https://openapivts.koreainvestment.com:29443"
        )
        response = requests.post(
            f"{base_url}/oauth2/Approval",
            headers={"content-type": "application/json; charset=utf-8"},
            json={"grant_type": "client_credentials", "appkey": self.config.app_key, "secretkey": self.config.app_secret},
            timeout=self.config.timeout_seconds,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise BrokerError(f"KIS WebSocket 접속키 발급 실패: {response.text}") from exc
        approval_key = payload.get("approval_key")
        if not approval_key:
            raise BrokerError(f"KIS WebSocket 접속키가 응답에 없습니다: {payload}")
        return str(approval_key)

    @staticmethod
    def _subscribe_body(approval_key: str, tr_id: str, ticker: str) -> dict[str, Any]:
        return {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": tr_id, "tr_key": ticker}},
        }

    def _consume_message(self, message: str, snapshot: RealtimeSnapshot, app) -> None:
        if not message:
            return
        if message.startswith("{"):
            payload = json.loads(message)
            header = payload.get("header") or {}
            body = payload.get("body") or {}
            if header.get("tr_id") == "PINGPONG":
                app.send(message)
                return
            msg = body.get("msg1") or body.get("msg_cd")
            if msg:
                snapshot.messages.append(str(msg))
            return

        parts = message.split("|", 3)
        if len(parts) < 4:
            return
        tr_id = parts[1]
        data = parts[3].split("^")
        if tr_id == TRADE_TR_ID:
            trade = self._parse_trade(data)
            if trade and trade["ticker"] == snapshot.ticker:
                snapshot.trades.append(trade)
        elif tr_id == ORDERBOOK_TR_ID:
            orderbook = self._parse_orderbook(data)
            if orderbook and orderbook["ticker"] == snapshot.ticker:
                snapshot.orderbook = orderbook

    @staticmethod
    def _parse_trade(values: list[str]) -> dict[str, Any] | None:
        if len(values) < 14:
            return None
        trade_time = values[1]
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = pd.to_datetime(f"{today} {trade_time[:2]}:{trade_time[2:4]}:{trade_time[4:6]}", errors="coerce")
        if pd.isna(timestamp):
            timestamp = pd.Timestamp.now()
        return {
            "ticker": values[0],
            "Date": timestamp,
            "Close": KISRealtimeClient._number(values[2]),
            "change": KISRealtimeClient._number(values[4]),
            "change_rate": KISRealtimeClient._number(values[5]),
            "Volume": KISRealtimeClient._number(values[12]),
            "acc_volume": KISRealtimeClient._number(values[13]),
        }

    @staticmethod
    def _parse_orderbook(values: list[str]) -> dict[str, Any] | None:
        if len(values) < 45:
            return None
        asks = [KISRealtimeClient._number(value) for value in values[3:13]]
        bids = [KISRealtimeClient._number(value) for value in values[13:23]]
        ask_qty = [KISRealtimeClient._number(value) for value in values[23:33]]
        bid_qty = [KISRealtimeClient._number(value) for value in values[33:43]]
        return {
            "ticker": values[0],
            "time": values[1],
            "asks": asks,
            "bids": bids,
            "ask_qty": ask_qty,
            "bid_qty": bid_qty,
            "total_ask_qty": KISRealtimeClient._number(values[43]),
            "total_bid_qty": KISRealtimeClient._number(values[44]),
        }

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0
