from __future__ import annotations

import sqlite3

from markets.symbol_display import build_name_map, resolve_name
from trading.order_service import TradingOrderService


_ORIGINAL = TradingOrderService.latest_recommendations


def _latest_recommendations_with_scores(self: TradingOrderService, limit: int = 30) -> list[dict[str, object]]:
    tables = {
        str(row["name"])
        for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "recommendation_runs" not in tables or "daily_recommendations" not in tables:
        return []

    run = self.conn.execute(
        """
        SELECT r.run_id, r.started_at, r.finished_at, r.run_type
        FROM recommendation_runs r
        WHERE r.status='COMPLETED'
          AND EXISTS(
            SELECT 1 FROM daily_recommendations d
            WHERE d.run_id=r.run_id AND d.market='kr'
          )
        ORDER BY r.started_at DESC
        LIMIT 1
        """
    ).fetchone()
    if run is None:
        return []

    if "final_decisions" not in tables:
        rows = _ORIGINAL(self, limit)
    else:
        try:
            fetched = self.conn.execute(
                """
                SELECT d.run_id, d.rank_no, d.ticker,
                       COALESCE(NULLIF(d.name, ''), NULLIF(f.name, ''), d.ticker) AS name,
                       COALESCE(f.decision, 'UNVALIDATED') AS decision,
                       COALESCE(f.grade, '') AS grade,
                       d.weekly_similarity AS ranking_score,
                       d.weekly_similarity, d.sto_similarity,
                       f.market_score, f.sector_score, f.risk_score,
                       f.target_return, f.stop_return,
                       CASE WHEN f.ticker IS NULL THEN 0 ELSE 1 END AS validation_available,
                       ? AS run_started_at, ? AS run_finished_at, ? AS run_type
                FROM daily_recommendations d
                LEFT JOIN final_decisions f
                  ON f.source_run_id=d.run_id AND f.ticker=d.ticker
                WHERE d.run_id=? AND d.market='kr'
                ORDER BY d.rank_no
                LIMIT ?
                """,
                (run["started_at"], run["finished_at"], run["run_type"], run["run_id"], int(limit)),
            ).fetchall()
            rows = [dict(row) for row in fetched]
        except sqlite3.OperationalError:
            rows = _ORIGINAL(self, limit)

    name_map = build_name_map(self.conn, "kr")
    normalized: list[dict[str, object]] = []
    for source in rows:
        row = dict(source)
        row["name"] = resolve_name(row.get("ticker"), row.get("name"), name_map, "kr")
        normalized.append(row)
    return normalized


def install_order_service_patch() -> None:
    if getattr(TradingOrderService.latest_recommendations, "_ade_scores_patch", False):
        return
    _latest_recommendations_with_scores._ade_scores_patch = True  # type: ignore[attr-defined]
    TradingOrderService.latest_recommendations = _latest_recommendations_with_scores  # type: ignore[method-assign]
