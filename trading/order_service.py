from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from broker.base import BrokerOrder
from broker.kis import kis_broker_from_env
from broker.kis_account_sync import KISAccountSync


@dataclass(frozen=True)
class OrderRequest:
    request_id: str
    ticker: str
    name: str | None
    side: str
    quantity: int
    order_type: str
    limit_price: float | None
    target_return: float | None
    stop_return: float | None
    status: str


class TradingOrderService:
    """Human-approved KIS order workflow.

    Orders are never sent during request creation. A second explicit approval step is
    required. Live orders additionally require KIS_LIVE_ORDER_ENABLED=YES in the
    environment and the exact approval phrase shown by the dashboard.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trade_order_requests (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                sent_at TEXT,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                order_type TEXT NOT NULL,
                limit_price REAL,
                target_return REAL,
                stop_return REAL,
                source_run_id TEXT,
                source_rank INTEGER,
                status TEXT NOT NULL,
                approval_text TEXT,
                error_message TEXT,
                broker_order_id TEXT,
                broker_message TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS trade_execution_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                captured_at TEXT NOT NULL,
                broker_order_id TEXT,
                ticker TEXT NOT NULL,
                side TEXT,
                ordered_quantity INTEGER,
                filled_quantity INTEGER,
                filled_price REAL,
                status TEXT NOT NULL,
                raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trade_risk_rules (
                ticker TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                target_return REAL,
                stop_return REAL,
                last_action TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trade_request_status ON trade_order_requests(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_trade_execution_order ON trade_execution_events(broker_order_id, captured_at);
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_request(
        self,
        *,
        ticker: str,
        name: str | None,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: float | None = None,
        target_return: float | None = None,
        stop_return: float | None = None,
        source_run_id: str | None = None,
        source_rank: int | None = None,
    ) -> str:
        order = BrokerOrder(
            market="kr",
            ticker=ticker,
            side=side.upper(),
            quantity=int(quantity),
            order_type=order_type.upper(),
            limit_price=limit_price,
            dry_run=False,
        )
        order.validate()
        request_id = f"ORD-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO trade_order_requests(
                request_id, created_at, market, ticker, name, side, quantity,
                order_type, limit_price, target_return, stop_return,
                source_run_id, source_rank, status
            ) VALUES (?, ?, 'kr', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL')
            """,
            (
                request_id,
                datetime.now().isoformat(timespec="seconds"),
                ticker,
                name,
                order.side,
                order.quantity,
                order.order_type,
                order.limit_price,
                target_return,
                stop_return,
                source_run_id,
                source_rank,
            ),
        )
        self.conn.commit()
        return request_id

    def approve_and_send(self, request_id: str, approval_text: str) -> dict[str, object]:
        row = self.conn.execute(
            "SELECT * FROM trade_order_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise ValueError("주문 요청을 찾을 수 없습니다.")
        if row["status"] != "PENDING_APPROVAL":
            raise ValueError(f"승인 가능한 상태가 아닙니다: {row['status']}")

        expected = f"{row['ticker']} {row['side']} {row['quantity']}주 승인"
        if approval_text.strip() != expected:
            raise ValueError(f"승인 문구가 일치하지 않습니다. 정확히 입력: {expected}")

        broker = kis_broker_from_env()
        order = BrokerOrder(
            market="kr",
            ticker=str(row["ticker"]),
            side=str(row["side"]),
            quantity=int(row["quantity"]),
            order_type=str(row["order_type"]),
            limit_price=row["limit_price"],
            dry_run=False,
        )
        approved_at = datetime.now().isoformat(timespec="seconds")
        try:
            result = broker.place_order(order)
            status = "SENT" if result.accepted else "REJECTED"
            self.conn.execute(
                """
                UPDATE trade_order_requests
                SET approved_at=?, sent_at=?, status=?, approval_text=?, broker_order_id=?,
                    broker_message=?, raw_json=?
                WHERE request_id=?
                """,
                (
                    approved_at,
                    datetime.now().isoformat(timespec="seconds"),
                    status,
                    approval_text,
                    result.order_id,
                    result.message,
                    json.dumps(result.raw or {}, ensure_ascii=False),
                    request_id,
                ),
            )
            if result.accepted and row["side"] == "BUY":
                self.conn.execute(
                    """
                    INSERT INTO trade_risk_rules(ticker, enabled, target_return, stop_return, updated_at)
                    VALUES (?, 1, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        enabled=1, target_return=excluded.target_return,
                        stop_return=excluded.stop_return, updated_at=excluded.updated_at
                    """,
                    (
                        row["ticker"],
                        row["target_return"],
                        row["stop_return"],
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            self.conn.commit()
            return result.to_dict()
        except Exception as exc:
            self.conn.execute(
                """
                UPDATE trade_order_requests
                SET approved_at=?, status='FAILED', approval_text=?, error_message=?
                WHERE request_id=?
                """,
                (approved_at, approval_text, str(exc), request_id),
            )
            self.conn.commit()
            raise

    def refresh_executions(self) -> list[dict[str, object]]:
        broker = kis_broker_from_env()
        executions = broker.get_order_executions()
        captured_at = datetime.now().isoformat(timespec="seconds")
        for item in executions:
            order_id = str(item.get("order_id") or "")
            request = self.conn.execute(
                "SELECT request_id FROM trade_order_requests WHERE broker_order_id=? ORDER BY created_at DESC LIMIT 1",
                (order_id,),
            ).fetchone()
            request_id = request["request_id"] if request else None
            self.conn.execute(
                """
                INSERT INTO trade_execution_events(
                    request_id, captured_at, broker_order_id, ticker, side,
                    ordered_quantity, filled_quantity, filled_price, status, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    captured_at,
                    order_id,
                    item.get("ticker", ""),
                    item.get("side"),
                    item.get("ordered_quantity", 0),
                    item.get("filled_quantity", 0),
                    item.get("filled_price", 0.0),
                    item.get("status", "UNKNOWN"),
                    json.dumps(item, ensure_ascii=False),
                ),
            )
            if request_id:
                self.conn.execute(
                    "UPDATE trade_order_requests SET status=? WHERE request_id=?",
                    (item.get("status", "UNKNOWN"), request_id),
                )
        self.conn.commit()
        return executions

    def sync_positions(self) -> list[dict[str, object]]:
        sync = KISAccountSync(self.db_path)
        try:
            _snapshot, positions = sync.sync()
            return positions
        finally:
            sync.close()

    def monitor_risk(self, *, execute: bool = False) -> list[dict[str, object]]:
        """Evaluate stop/take-profit rules.

        execute=False only reports triggers. execute=True creates SELL requests that still
        require the same separate human approval step; it never sends an order directly.
        """
        positions = self.sync_positions()
        actions: list[dict[str, object]] = []
        for pos in positions:
            rule = self.conn.execute(
                "SELECT * FROM trade_risk_rules WHERE ticker=? AND enabled=1",
                (pos["ticker"],),
            ).fetchone()
            if rule is None:
                continue
            pnl_rate = float(pos["pnl_rate"])
            trigger = None
            if rule["target_return"] is not None and pnl_rate >= float(rule["target_return"]):
                trigger = "TAKE_PROFIT"
            elif rule["stop_return"] is not None and pnl_rate <= float(rule["stop_return"]):
                trigger = "STOP_LOSS"
            if trigger is None:
                continue
            action = {
                "ticker": pos["ticker"],
                "name": pos["name"],
                "quantity": int(pos["quantity"]),
                "pnl_rate": pnl_rate,
                "trigger": trigger,
                "request_id": None,
            }
            if execute:
                action["request_id"] = self.create_request(
                    ticker=str(pos["ticker"]),
                    name=str(pos["name"]),
                    side="SELL",
                    quantity=int(pos["quantity"]),
                    order_type="MARKET",
                )
                self.conn.execute(
                    "UPDATE trade_risk_rules SET last_action=?, updated_at=? WHERE ticker=?",
                    (trigger, datetime.now().isoformat(timespec="seconds"), pos["ticker"]),
                )
            actions.append(action)
        self.conn.commit()
        return actions

    def pending_requests(self, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM trade_order_requests ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_executions(self, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM trade_execution_events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]
