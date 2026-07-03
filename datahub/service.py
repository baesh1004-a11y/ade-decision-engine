from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from datahub.kis import KISPriceDownloader
from datahub.loaders import CSVPriceLoader
from datahub.models import DataHubSyncResult, PriceBar
from datahub.quality import DataQualityReport, PriceDataQualityValidator
from datahub.repository import PriceRepository
from datahub.yahoo import YahooPriceDownloader


class DataHub:
    """Facade for market data ingestion, storage, retrieval, and quality checks."""

    def __init__(self, db_path: str | Path = "ade.db") -> None:
        self.repository = PriceRepository(db_path)
        self.csv_loader = CSVPriceLoader()
        self.yahoo = YahooPriceDownloader()
        self.quality_validator = PriceDataQualityValidator()

    def import_csv(self, path: str | Path, market: str, ticker: str, source: str = "csv") -> DataHubSyncResult:
        records = self.csv_loader.load(path, market=market, ticker=ticker, source=source)
        return self._save(records, market=market, ticker=ticker, source=source)

    def import_dataframe(self, df: pd.DataFrame, market: str, ticker: str, source: str = "dataframe") -> DataHubSyncResult:
        records = self.csv_loader.from_dataframe(df, market=market, ticker=ticker, source=source)
        return self._save(records, market=market, ticker=ticker, source=source)

    def sync_yahoo(self, ticker: str, market: str = "us", start: str | None = None, end: str | None = None) -> DataHubSyncResult:
        records = self.yahoo.download(ticker=ticker, market=market, start=start, end=end)
        return self._save(records, market=market, ticker=ticker, source="yahoo")

    def sync_kis(
        self,
        ticker: str,
        start: str,
        end: str,
        market: str = "kr",
        app_key: str | None = None,
        app_secret: str | None = None,
        environment: str | None = None,
        downloader: KISPriceDownloader | None = None,
    ) -> DataHubSyncResult:
        """Sync Korean domestic daily bars from KIS into price_bars.

        Dates must be compact KIS dates, e.g. 20240101. Credentials may be
        passed directly for tests or loaded from KIS_APP_KEY/KIS_APP_SECRET.
        """
        kis = downloader or self._build_kis_downloader(app_key, app_secret, environment)
        records = kis.download_daily_bars(ticker=ticker, start=start, end=end, market=market)
        return self._save(records, market=market, ticker=ticker, source="kis")

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

    def validate_prices(
        self,
        market: str,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
        source: str | None = None,
    ) -> DataQualityReport:
        df = self.get_prices(
            market=market,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            source=source,
        )
        return self.quality_validator.validate(df, market=market, ticker=ticker)

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

    def _build_kis_downloader(
        self,
        app_key: str | None,
        app_secret: str | None,
        environment: str | None,
    ) -> KISPriceDownloader:
        resolved_app_key = app_key or os.getenv("KIS_APP_KEY")
        resolved_app_secret = app_secret or os.getenv("KIS_APP_SECRET")
        resolved_environment = environment or os.getenv("KIS_ENV", "paper")
        if not resolved_app_key or not resolved_app_secret:
            raise ValueError("KIS_APP_KEY and KIS_APP_SECRET are required for KIS sync")
        return KISPriceDownloader(
            app_key=resolved_app_key,
            app_secret=resolved_app_secret,
            environment=resolved_environment,
        )
