from __future__ import annotations

from markets.symbol_display import build_name_map, normalize_ticker, resolve_name
from trading.order_service import TradingOrderService


_ORIGINAL_LATEST_RECOMMENDATIONS = TradingOrderService.latest_recommendations
_ORIGINAL_PENDING_REQUESTS = TradingOrderService.pending_requests
_ORIGINAL_LATEST_EXECUTIONS = TradingOrderService.latest_executions


def install_name_resolution_patch() -> None:
    if getattr(TradingOrderService, "_name_resolution_patch_installed", False):
        return

    def latest_recommendations(self: TradingOrderService, limit: int = 30):
        rows = _ORIGINAL_LATEST_RECOMMENDATIONS(self, limit)
        name_map = build_name_map(self.conn, "kr")
        for row in rows:
            code = normalize_ticker(row.get("ticker"), "kr")
            row["ticker"] = code
            row["name"] = resolve_name(code, row.get("name"), name_map, "kr")
        return rows

    def pending_requests(self: TradingOrderService, limit: int = 100):
        rows = _ORIGINAL_PENDING_REQUESTS(self, limit)
        name_map = build_name_map(self.conn, "kr")
        for row in rows:
            code = normalize_ticker(row.get("ticker"), "kr")
            row["ticker"] = code
            row["name"] = resolve_name(code, row.get("name"), name_map, "kr")
        return rows

    def latest_executions(self: TradingOrderService, limit: int = 100):
        rows = _ORIGINAL_LATEST_EXECUTIONS(self, limit)
        name_map = build_name_map(self.conn, "kr")
        for row in rows:
            code = normalize_ticker(row.get("ticker"), "kr")
            row["ticker"] = code
            row["name"] = resolve_name(code, None, name_map, "kr")
        return rows

    TradingOrderService.latest_recommendations = latest_recommendations
    TradingOrderService.pending_requests = pending_requests
    TradingOrderService.latest_executions = latest_executions
    TradingOrderService._name_resolution_patch_installed = True
