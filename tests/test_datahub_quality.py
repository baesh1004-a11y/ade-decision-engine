from __future__ import annotations

import pandas as pd

from datahub.quality import PriceDataQualityValidator
from datahub.service import DataHub


def _valid_market_data(rows: int = 80) -> pd.DataFrame:
    start = pd.Timestamp("2024-01-01")
    data = []
    for i in range(rows):
        close = 100 + i * 0.5
        data.append(
            {
                "Date": (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + i,
            }
        )
    return pd.DataFrame(data)


def test_price_quality_validator_accepts_valid_ohlcv_data() -> None:
    report = PriceDataQualityValidator().validate(_valid_market_data(), market="us", ticker="NVDA")

    assert report.is_usable is True
    assert report.error_count == 0
    assert report.row_count == 80
    assert report.start_date == "2024-01-01"
    assert report.end_date == "2024-03-20"


def test_price_quality_validator_rejects_invalid_ohlc_range() -> None:
    df = _valid_market_data()
    df.loc[10, "High"] = df.loc[10, "Low"] - 1

    report = PriceDataQualityValidator().validate(df, market="us", ticker="NVDA")

    assert report.is_usable is False
    assert report.error_count == 1
    assert report.issues[0].code == "INVALID_OHLC_RANGE"


def test_price_quality_validator_warns_on_short_history() -> None:
    report = PriceDataQualityValidator(min_rows=60).validate(_valid_market_data(20), market="us", ticker="NVDA")

    assert report.is_usable is True
    assert report.warning_count == 1
    assert report.issues[0].code == "SHORT_HISTORY"


def test_datahub_validate_prices_after_import() -> None:
    hub = DataHub(db_path=":memory:")
    hub.import_dataframe(_valid_market_data(), market="us", ticker="NVDA")

    report = hub.validate_prices(market="us", ticker="NVDA")

    assert report.is_usable is True
    assert report.row_count == 80
    hub.close()


class FakeKISDownloader:
    def download_daily_bars(self, ticker: str, start: str, end: str, market: str = "kr"):
        from datahub.models import PriceBar

        return [
            PriceBar(
                market=market,
                ticker=ticker,
                trade_date="2026-07-01",
                open=70000,
                high=71000,
                low=69000,
                close=70500,
                volume=1234567,
                source="kis",
            )
        ]


def test_datahub_sync_kis_accepts_injected_downloader_without_env() -> None:
    hub = DataHub(db_path=":memory:")

    sync = hub.sync_kis("005930", start="20260701", end="20260701", downloader=FakeKISDownloader())
    df = hub.get_prices(market="kr", ticker="005930", source="kis")

    assert sync.source == "kis"
    assert sync.row_count == 1
    assert df.iloc[0]["Close"] == 70500
    hub.close()
