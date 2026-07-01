from __future__ import annotations

from pathlib import Path

import pandas as pd

from datahub.loaders import CSVPriceLoader
from datahub.models import DataHubSyncResult, PriceBar
from datahub.repository import PriceRepository
from datahub.yahoo import YahooPriceDownloader


class DataHub:
    """Facade for market data ingestion, storage, and retrieval."""

    def __init__(self, db_path: str | Path = "ade.db") -> None:
        self.repository = PriceRepository(db_path)
        self.csv_loader = CSVPriceLoader()
        self.yahoo = YahooPriceDownloader()

    def import_csv(self, path: str | Path, market: str, ticker: str, source: str = "csv") -> DataHubSyncResult:
        records = self.csv_loader.load(path, market=market, ticker=ticker, source=source)
        return self._save(records, market=market, ticker=ticker, source=source)

    def import_dataframe(self, df: pd.DataFrame, market: str, ticker: str, source: str = "dataframe") -> DataHubSyncResult:
        records = self.csv_loader.from_dataframe(df, market=market, ticker=ticker, source=source)
        return self._save(records, market=market, ticker=ticker, source=source)

    def sync_yahoo(self, ticker: str, market: str = "us", start: str | None = None, end: str | None = None) -> DataHubSyncResult:
        records = self.yahoo.download(ticker=ticker, market=market, start=start, end=end)
        return self._save(records, market=market, ticker=ticker, source="yahoo")

    def get_prices(
        self,
        market: str,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
        source: str | None = None,
    ) -> pd.DataFrame:
        return self.repository.fetch_dataframe(
            market=market,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            source=source,
        )

    def close(self) -> None:
        self.repository.close()

    def _save(self, records: list[PriceBar], market: str, ticker: str, source: str) -> DataHubSyncResult:
        count = self.repository.upsert_many(records)
        dates = [record.trade_date for record in records]
        return DataHubSyncResult(
            market=market,
            ticker=ticker,
            source=source,
            row_count=count,
            start_date=min(dates) if dates else None,
            end_date=max(dates) if dates else None,
        )
