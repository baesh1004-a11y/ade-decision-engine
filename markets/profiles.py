from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarketProfile:
    code: str
    name: str
    db_path: Path
    price_source: str
    timezone: str
    currency: str
    benchmark_radar: str
    scheduler_time: str


PROFILES: dict[str, MarketProfile] = {
    "kr": MarketProfile(
        code="kr",
        name="한국장",
        db_path=Path("datahub/market.db"),
        price_source="fdr",
        timezone="Asia/Seoul",
        currency="KRW",
        benchmark_radar="kospi50",
        scheduler_time="16:10",
    ),
    "us": MarketProfile(
        code="us",
        name="미국장",
        db_path=Path("datahub/us_market.db"),
        price_source="yfinance",
        timezone="America/New_York",
        currency="USD",
        benchmark_radar="nasdaq30",
        scheduler_time="16:20 ET",
    ),
}


def get_market_profile(code: str) -> MarketProfile:
    key = code.strip().lower()
    if key not in PROFILES:
        raise ValueError(f"지원하지 않는 시장입니다: {code}")
    return PROFILES[key]
