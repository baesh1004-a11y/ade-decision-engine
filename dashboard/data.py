from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository


@dataclass(frozen=True)
class DashboardMetrics:
    orders: int
    accepted_orders: int
    invested_amount: float
    evaluation_amount: float
    pnl: float
    pnl_rate: float
    winners: int
    losers: int


class PaperDashboardData:
    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)

    def close(self) -> None:
        self.price_repo.close()
        self.conn.close()

    def load_orders(self) -> pd.DataFrame:
        self._ensure_table()
        rows = self.conn.execute(
            """
            SELECT * FROM paper_orders
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        df = pd.DataFrame([dict(row) for row in rows])
        if df.empty:
            return pd.DataFrame()
        for col in ["budget", "reference_price", "quantity", "estimated_amount", "weekly_similarity", "sto_similarity", "final_similarity", "accepted"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def load_positions(self) -> pd.DataFrame:
        orders = self.load_orders()
        if orders.empty:
            return pd.DataFrame()
        buys = orders[(orders["side"] == "BUY") & (orders["accepted"] == 1)].copy()
        if buys.empty:
            return pd.DataFrame()
        grouped = buys.groupby(["market", "ticker"], as_index=False).agg(
            name=("name", "last"),
            quantity=("quantity", "sum"),
            invested_amount=("estimated_amount", "sum"),
            avg_reference_price=("reference_price", "mean"),
            first_buy_at=("created_at", "min"),
            last_buy_at=("created_at", "max"),
            top1_event_id=("top1_event_id", "last"),
            weekly_similarity=("weekly_similarity", "last"),
            sto_similarity=("sto_similarity", "last"),
            final_similarity=("final_similarity", "last"),
        )
        rows = []
        for _, row in grouped.iterrows():
            market = str(row["market"])
            ticker = str(row["ticker"])
            current_price = self._latest_close(market, ticker)
            quantity = float(row["quantity"] or 0)
            invested = float(row["invested_amount"] or 0)
            evaluation = quantity * current_price
            pnl = evaluation - invested
            pnl_rate = (pnl / invested * 100) if invested > 0 else 0.0
            item = dict(row)
            item.update(
                {
                    "current_price": current_price,
                    "evaluation_amount": evaluation,
                    "pnl": pnl,
                    "pnl_rate": pnl_rate,
                }
            )
            rows.append(item)
        return pd.DataFrame(rows).sort_values("pnl_rate", ascending=False).reset_index(drop=True)

    def metrics(self) -> DashboardMetrics:
        orders = self.load_orders()
        positions = self.load_positions()
        if orders.empty:
            return DashboardMetrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0)
        invested = float(positions["invested_amount"].sum()) if not positions.empty else 0.0
        evaluation = float(positions["evaluation_amount"].sum()) if not positions.empty else 0.0
        pnl = evaluation - invested
        pnl_rate = (pnl / invested * 100) if invested > 0 else 0.0
        winners = int((positions["pnl"] > 0).sum()) if not positions.empty else 0
        losers = int((positions["pnl"] < 0).sum()) if not positions.empty else 0
        return DashboardMetrics(
            orders=int(len(orders)),
            accepted_orders=int((orders["accepted"] == 1).sum()) if "accepted" in orders.columns else 0,
            invested_amount=invested,
            evaluation_amount=evaluation,
            pnl=pnl,
            pnl_rate=pnl_rate,
            winners=winners,
            losers=losers,
        )

    def equity_curve(self) -> pd.DataFrame:
        orders = self.load_orders()
        if orders.empty:
            return pd.DataFrame(columns=["date", "invested"])
        buys = orders[(orders["side"] == "BUY") & (orders["accepted"] == 1)].copy()
        if buys.empty:
            return pd.DataFrame(columns=["date", "invested"])
        buys["date"] = pd.to_datetime(buys["created_at"]).dt.date.astype(str)
        curve = buys.groupby("date", as_index=False)["estimated_amount"].sum()
        curve["invested"] = curve["estimated_amount"].cumsum()
        return curve[["date", "invested"]]

    def _latest_close(self, market: str, ticker: str) -> float:
        df = self.price_repo.fetch_dataframe(market, ticker, source="fdr")
        if df.empty:
            df = self.price_repo.fetch_dataframe(market, ticker)
        if df.empty:
            return 0.0
        try:
            return float(df.iloc[-1]["Close"])
        except Exception:
            return 0.0

    def _ensure_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                side TEXT NOT NULL,
                budget INTEGER NOT NULL,
                reference_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                estimated_amount INTEGER NOT NULL,
                top1_event_id TEXT,
                weekly_similarity REAL,
                sto_similarity REAL,
                final_similarity REAL,
                accepted INTEGER NOT NULL,
                order_id TEXT,
                message TEXT,
                raw TEXT
            )
            """
        )
        self.conn.commit()
