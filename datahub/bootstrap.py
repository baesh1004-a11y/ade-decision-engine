from __future__ import annotations

from datahub.paths import market_db_path, us_market_db_path
from datahub.repository import PriceRepository


def ensure_market_databases() -> None:
    """Create local SQLite files and base schema when they are missing."""
    for db_path in (market_db_path(), us_market_db_path()):
        repo = PriceRepository(db_path)
        repo.close()
