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
        rows = self.conn.execute("SELECT * FROM paper_orders ORDER BY created_at DESC, id DESC").fetchall()
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
        accepted = orders[orders["accepted"] == 1].copy()
        buys = accepted[accepted["side"].str.upper() == "BUY"].copy()
        if buys.empty:
            return pd.DataFrame()
        sells = accepted[accepted["side"].str.upper() == "SELL"].copy()

        buy_group = buys.groupby(["market", "ticker"], as_index=False).agg(
            name=("name", "last"),
            buy_quantity=("quantity", "sum"),
            buy_amount=("estimated_amount", "sum"),
            avg_reference_price=("reference_price", "mean"),
            first_buy_at=("created_at", "min"),
            last_buy_at=("created_at", "max"),
            top1_event_id=("top1_event_id", "last"),
            weekly_similarity=("weekly_similarity", "last"),
            sto_similarity=("sto_similarity", "last"),
            final_similarity=("final_similarity", "last"),
        )
        if sells.empty:
            sell_group = pd.DataFrame(columns=["market", "ticker", "sell_quantity", "sell_amount"])
        else:
            sell_group = sells.groupby(["market", "ticker"], as_index=False).agg(
                sell_quantity=("quantity", "sum"),
                sell_amount=("estimated_amount", "sum"),
            )

        grouped = buy_group.merge(sell_group, on=["market", "ticker"], how="left")
        grouped[["sell_quantity", "sell_amount"]] = grouped[["sell_quantity", "sell_amount"]].fillna(0)
        rows = []
        for _, row in grouped.iterrows():
            buy_qty = float(row["buy_quantity"] or 0)
            sell_qty = float(row["sell_quantity"] or 0)
            quantity = buy_qty - sell_qty
            if quantity <= 0:
                continue
            avg_price = float(row["buy_amount"] or 0) / buy_qty if buy_qty > 0 else 0.0
            invested = quantity * avg_price
            current_price = self._latest_close(str(row["market"]), str(row["ticker"]))
            evaluation = quantity * current_price
            pnl = evaluation - invested
            pnl_rate = (pnl / invested * 100) if invested > 0 else 0.0
            rows.append(
                {
                    "market": row["market"], "ticker": row["ticker"], "name": row["name"],
                    "quantity": quantity, "invested_amount": invested,
                    "avg_reference_price": avg_price, "first_buy_at": row["first_buy_at"],
                    "last_buy_at": row["last_buy_at"], "top1_event_id": row["top1_event_id"],
                    "weekly_similarity": row["weekly_similarity"], "sto_similarity": row["sto_similarity"],
                    "final_similarity": row["final_similarity"], "current_price": current_price,
                    "evaluation_amount": evaluation, "pnl": pnl, "pnl_rate": pnl_rate,
                }
            )
        if not rows:
            return pd.DataFrame()
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
        return DashboardMetrics(len(orders), int((orders["accepted"] == 1).sum()), invested, evaluation, pnl, pnl_rate, winners, losers)

    def equity_curve(self) -> pd.DataFrame:
        orders = self.load_orders()
        if orders.empty:
            return pd.DataFrame(columns=["date", "invested"])
        accepted = orders[orders["accepted"] == 1].copy()
        if accepted.empty:
            return pd.DataFrame(columns=["date", "invested"])
        accepted["date"] = pd.to_datetime(accepted["created_at"]).dt.date.astype(str)
        accepted["cash_flow"] = accepted.apply(
            lambda r: float(r["estimated_amount"]) if str(r["side"]).upper() == "BUY" else -float(r["estimated_amount"]), axis=1
        )
        curve = accepted.groupby("date", as_index=False)["cash_flow"].sum()
        curve["invested"] = curve["cash_flow"].cumsum()
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
