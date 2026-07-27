from __future__ import annotations

from pathlib import Path

from datahub.repository import PriceRepository


def ensure_market_databases() -> None:
    """Create the local SQLite database files and base schema when missing.

    This is intentionally lightweight: it only creates the SQLite files and the
    normalized price_bars table/index. It does not download market history or
    generate recommendations.
    """
    for db_path in (Path("datahub/market.db"), Path("datahub/us_market.db")):
        repo = PriceRepository(db_path)
        repo.close()
