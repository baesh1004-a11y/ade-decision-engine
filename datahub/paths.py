from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    root = Path(os.getenv("ADE_DATA_DIR", "datahub")).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def market_db_path() -> Path:
    return data_root() / "market.db"


def us_market_db_path() -> Path:
    return data_root() / "us_market.db"


def archive_path(filename: str) -> Path:
    return data_root() / filename
