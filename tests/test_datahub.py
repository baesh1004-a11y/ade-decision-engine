import pandas as pd

from core.context import DecisionContext
from core.pipeline import ADEPipeline
from datahub.loaders import CSVPriceLoader
from datahub.repository import PriceRepository
from datahub.service import DataHub


def _market_data(rows: int = 120) -> pd.DataFrame:
    data = []
    start = pd.Timestamp("2024-01-01")
    for i in range(rows):
        close = 100 + i * 0.4
        data.append(
            {
                "Date": (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + i * 1000,
            }
        )
    return pd.DataFrame(data)


def test_csv_loader_converts_dataframe_to_price_bars():
    records = CSVPriceLoader().from_dataframe(_market_data(5), market="us", ticker="NVDA")

    assert len(records) == 5
    assert records[0].ticker == "NVDA"
    assert records[0].open > 0


def test_price_repository_saves_and_fetches_dataframe():
    repo = PriceRepository()
    records = CSVPriceLoader().from_dataframe(_market_data(10), market="us", ticker="NVDA")
    count = repo.upsert_many(records)
    df = repo.fetch_dataframe(market="us", ticker="NVDA")

    assert count == 10
    assert repo.count("us", "NVDA") == 10
    assert len(df) == 10
    assert {"Date", "Open", "High", "Low", "Close", "Volume"}.issubset(df.columns)
    repo.close()


def test_datahub_import_dataframe_and_pipeline_usage():
    hub = DataHub(db_path=":memory:")
    sync = hub.import_dataframe(_market_data(120), market="us", ticker="NVDA")
    df = hub.get_prices(market="us", ticker="NVDA")

    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=df,
        account_balance=100_000_000,
        cash=50_000_000,
    )
    result = ADEPipeline().run(context)

    assert sync.row_count == 120
    assert len(df) == 120
    assert "candidate" in result.decisions
    hub.close()
