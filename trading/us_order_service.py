from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from broker.base import BrokerOrder
from broker.kis_overseas import kis_overseas_broker_from_env, normalize_exchange


class USTradingOrderService:
    def __init__(self, db_path: str | Path = "datahub/us_market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS us_trade_order_requests (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                sent_at TEXT,
                ticker TEXT NOT NULL,
                name TEXT,
                exchange TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                limit_price REAL NOT NULL,
                target_return REAL,
                stop_return REAL,
                source_run_id TEXT,
                source_rank INTEGER,
                status TEXT NOT NULL,
                approval_text TEXT,
                broker_order_id TEXT,
                broker_message TEXT,
                error_message TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS us_trade_execution_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                captured_at TEXT NOT NULL,
                broker_order_id TEXT,
                ticker TEXT NOT NULL,
                exchange TEXT,
                side TEXT,
                ordered_quantity INTEGER,
                filled_quantity INTEGER,
                filled_price REAL,
                status TEXT NOT NULL,
                raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS us_position_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                quantity INTEGER NOT NULL,
                average_price REAL,
                current_price REAL,
                evaluation_amount REAL,
                pnl REAL,
                pnl_rate REAL,
                currency TEXT NOT NULL DEFAULT 'USD'
            );
            CREATE TABLE IF NOT EXISTS us_trade_risk_rules (
                ticker TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                target_return REAL,
                stop_return REAL,
                last_action TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_us_trade_status ON us_trade_order_requests(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_us_execution_order ON us_trade_execution_events(broker_order_id, captured_at);
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def latest_recommendations(self, limit: int = 30) -> list[dict[str, object]]:
        run = self.conn.execute(
            "SELECT run_id FROM recommendation_runs WHERE status='COMPLETED' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None:
            return []
        rows = self.conn.execute(
            """
            SELECT run_id, rank_no, ticker, name, decision, target_return, stop_return,
                   seven_day_up_probability, seven_day_expected_return
            FROM daily_recommendations WHERE run_id=? ORDER BY rank_no LIMIT ?
            """,
            (run["run_id"], int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def exchange_for_ticker(self, ticker: str) -> str:
        row = self.conn.execute(
            "SELECT exchange FROM us_universe WHERE symbol=? ORDER BY enabled DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
        return normalize_exchange(str(row["exchange"])) if row and row["exchange"] else "NASD"

    def create_request(
        self,
        *,
        ticker: str,
        name: str | None,
        exchange: str,
        side: str,
        quantity: int,
        limit_price: float,
        target_return: float | None = None,
        stop_return: float | None = None,
        source_run_id: str | None = None,
        source_rank: int | None = None,
    ) -> str:
        order = BrokerOrder(
            market="us",
            ticker=ticker.upper(),
            side=side.upper(),
            quantity=int(quantity),
            order_type="LIMIT",
            limit_price=float(limit_price),
            dry_run=False,
        )
        order.validate()
        exchange = normalize_exchange(exchange)
        request_id = f"USORD-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO us_trade_order_requests(
                request_id, created_at, ticker, name, exchange, side, quantity,
                limit_price, target_return, stop_return, source_run_id,
                source_rank, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL')
            """,
            (
                request_id,
                self._now(),
                ticker.upper(),
                name,
                exchange,
                order.side,
                order.quantity,
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
            "SELECT * FROM us_trade_order_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise ValueError("미국주식 주문 요청을 찾을 수 없습니다.")
        if row["status"] != "PENDING_APPROVAL":
            raise ValueError(f"승인 가능한 상태가 아닙니다: {row['status']}")
        expected = f"{row['ticker']} {row['side']} {row['quantity']}주 ${float(row['limit_price']):.2f} 승인"
        if approval_text.strip() != expected:
            raise ValueError(f"승인 문구가 일치하지 않습니다. 정확히 입력: {expected}")

        order = BrokerOrder(
            market="us",
            ticker=str(row["ticker"]),
            side=str(row["side"]),
            quantity=int(row["quantity"]),
            order_type="LIMIT",
            limit_price=float(row["limit_price"]),
            dry_run=False,
        )
        broker = kis_overseas_broker_from_env()
        try:
            result = broker.place_us_order(order, str(row["exchange"]))
            status = "SENT" if result.accepted else "REJECTED"
            self.conn.execute(
                """
                UPDATE us_trade_order_requests SET approved_at=?, sent_at=?, status=?,
                    approval_text=?, broker_order_id=?, broker_message=?, raw_json=?
                WHERE request_id=?
                """,
                (
                    self._now(), self._now(), status, approval_text,
                    result.order_id, result.message,
                    json.dumps(result.raw or {}, ensure_ascii=False), request_id,
                ),
            )
            if result.accepted and row["side"] == "BUY":
                self.conn.execute(
                    """
                    INSERT INTO us_trade_risk_rules(ticker, enabled, target_return, stop_return, updated_at)
                    VALUES (?, 1, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET enabled=1,
                        target_return=excluded.target_return,
                        stop_return=excluded.stop_return,
                        updated_at=excluded.updated_at
                    """,
                    (row["ticker"], row["target_return"], row["stop_return"], self._now()),
                )
            self.conn.commit()
            return result.to_dict()
        except Exception as exc:
            self.conn.execute(
                """
                UPDATE us_trade_order_requests SET approved_at=?, status='FAILED',
                    approval_text=?, error_message=? WHERE request_id=?
                """,
                (self._now(), approval_text, str(exc), request_id),
            )
            self.conn.commit()
            raise

    def refresh_executions(self, days: int = 7) -> list[dict[str, object]]:
        rows = kis_overseas_broker_from_env().get_us_executions(days=days)
        for item in rows:
            order_id = str(item.get("order_id") or "")
            request = self.conn.execute(
                "SELECT request_id FROM us_trade_order_requests WHERE broker_order_id=? ORDER BY created_at DESC LIMIT 1",
                (order_id,),
            ).fetchone()
            request_id = request["request_id"] if request else None
            self.conn.execute(
                """
                INSERT INTO us_trade_execution_events(
                    request_id, captured_at, broker_order_id, ticker, exchange,
                    side, ordered_quantity, filled_quantity, filled_price,
                    status, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id, self._now(), order_id, item.get("ticker", ""),
                    item.get("exchange"), item.get("side"),
                    item.get("ordered_quantity", 0), item.get("filled_quantity", 0),
                    item.get("filled_price", 0.0), item.get("status", "UNKNOWN"),
                    json.dumps(item, ensure_ascii=False),
                ),
            )
            if request_id:
                self.conn.execute(
                    "UPDATE us_trade_order_requests SET status=? WHERE request_id=?",
                    (item.get("status", "UNKNOWN"), request_id),
                )
        self.conn.commit()
        return rows

    def sync_positions(self) -> list[dict[str, object]]:
        broker = kis_overseas_broker_from_env()
        positions = []
        seen: set[str] = set()
        for exchange in ("NASD", "NYSE", "AMEX"):
            for pos in broker.get_us_positions(exchange):
                if not pos.ticker or pos.ticker in seen:
                    continue
                seen.add(pos.ticker)
                positions.append(pos.to_dict())
        captured_at = self._now()
        for item in positions:
            self.conn.execute(
                """
                INSERT INTO us_position_snapshots(
                    captured_at, ticker, name, quantity, average_price,
                    current_price, evaluation_amount, pnl, pnl_rate, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')
                """,
                (
                    captured_at, item["ticker"], item["name"], item["quantity"],
                    item["average_price"], item["current_price"],
                    item["evaluation_amount"], item["pnl"], item["pnl_rate"],
                ),
            )
        self.conn.commit()
        return positions

    def monitor_risk(self, create_sell_requests: bool = False) -> list[dict[str, object]]:
        actions: list[dict[str, object]] = []
        for pos in self.sync_positions():
            rule = self.conn.execute(
                "SELECT * FROM us_trade_risk_rules WHERE ticker=? AND enabled=1",
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
            request_id = None
            if create_sell_requests:
                request_id = self.create_request(
                    ticker=str(pos["ticker"]),
                    name=str(pos["name"]),
                    exchange=self.exchange_for_ticker(str(pos["ticker"])),
                    side="SELL",
                    quantity=int(pos["quantity"]),
                    limit_price=float(pos["current_price"]),
                )
                self.conn.execute(
                    "UPDATE us_trade_risk_rules SET last_action=?, updated_at=? WHERE ticker=?",
                    (trigger, self._now(), pos["ticker"]),
                )
            actions.append({
                "ticker": pos["ticker"],
                "name": pos["name"],
                "quantity": int(pos["quantity"]),
                "pnl_rate": pnl_rate,
                "trigger": trigger,
                "request_id": request_id,
            })
        self.conn.commit()
        return actions

    def order_history(self, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM us_trade_order_requests ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def execution_history(self, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM us_trade_execution_events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")
