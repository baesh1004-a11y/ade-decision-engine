from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from collector.base import CollectorRequest, CollectorResult
from collector.fdr import FDRCollector


@dataclass(frozen=True)
class DataSourceInfo:
    historical: str = "FDR"
    realtime: str = "KIS"
    database: str = "SQLite DataHub"
    mode: str = "hybrid"


class FDRProvider:
    source_name = "FDR"

    def __init__(self) -> None:
        self.collector = FDRCollector()

    def fetch_history(self, market: str, ticker: str, period: str = "5y") -> CollectorResult:
        return self.collector.fetch(CollectorRequest(market=market, ticker=ticker, period=period, interval="1d"))

    def list_kr_symbols(self) -> list[dict[str, str | None]]:
        import FinanceDataReader as fdr

        symbols: list[dict[str, str | None]] = []
        for market_name in ["KOSPI", "KOSDAQ"]:
            listing = fdr.StockListing(market_name)
            code_col = "Code" if "Code" in listing.columns else "Symbol"
            name_col = "Name" if "Name" in listing.columns else code_col
            sector_col = "Sector" if "Sector" in listing.columns else None
            for row in listing.itertuples(index=False):
                row_dict = row._asdict()
                ticker = str(row_dict.get(code_col, "")).zfill(6)
                name = str(row_dict.get(name_col, "")) or None
                sector = str(row_dict.get(sector_col, "")) if sector_col else market_name
                if ticker and ticker != "000000":
                    symbols.append({"market": "kr", "ticker": ticker, "name": name, "sector": sector, "source": f"FDR:{market_name}"})
        unique: dict[str, dict[str, str | None]] = {}
        for item in symbols:
            unique[f"kr:{item['ticker']}"] = item
        return list(unique.values())


class KISProvider:
    source_name = "KIS"

    def status(self) -> dict[str, str]:
        try:
            from broker.kis import KISBroker  # type: ignore

            broker = KISBroker()
            return {"KIS": "CONFIGURED", "Broker": broker.__class__.__name__, "Realtime": "READY"}
        except Exception as exc:
            return {"KIS": "NOT_READY", "Reason": str(exc), "Realtime": "DISABLED"}


class HybridProvider:
    """ADE v1 hybrid source policy: FDR for history, KIS for realtime/account."""

    def __init__(self) -> None:
        self.history = FDRProvider()
        self.realtime = KISProvider()
        self.info = DataSourceInfo()

    def fetch_history(self, market: str, ticker: str, period: str = "5y") -> CollectorResult:
        return self.history.fetch_history(market, ticker, period=period)

    def list_kr_symbols(self) -> list[dict[str, str | None]]:
        return self.history.list_kr_symbols()

    def status(self) -> dict[str, str]:
        status = self.realtime.status()
        status.update({"Historical": self.info.historical, "Database": self.info.database, "Mode": self.info.mode})
        return status
