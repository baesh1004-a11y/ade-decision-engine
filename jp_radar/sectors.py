from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RadarSector:
    code: str
    name: str
    benchmark: str
    benchmark_name: str
    tickers: tuple[str, ...]


SECTORS: dict[str, RadarSector] = {
    "kosdaq50": RadarSector(
        code="kosdaq50",
        name="KOSDAQ 50",
        benchmark="^KQ11",
        benchmark_name="KOSDAQ",
        tickers=(
            "247540.KQ", "086520.KQ", "036930.KQ", "196170.KQ", "240810.KQ",
            "277810.KQ", "058470.KQ", "039030.KQ", "141080.KQ", "000250.KQ",
            "298380.KQ", "087010.KQ", "319660.KQ", "222800.KQ", "347850.KQ",
            "403870.KQ", "048410.KQ", "036570.KQ", "006090.KQ", "095340.KQ",
            "080220.KQ", "214370.KQ", "108490.KQ", "084370.KQ", "310210.KQ",
            "178320.KQ", "067310.KQ", "033640.KQ", "041960.KQ", "214450.KQ",
            "145020.KQ", "095610.KQ", "319400.KQ", "214150.KQ", "226950.KQ",
            "005290.KQ", "004090.KQ", "039490.KQ", "023350.KQ", "064760.KQ",
            "131290.KQ", "043340.KQ", "036120.KQ", "019660.KQ", "044340.KQ",
            "035810.KQ", "032190.KQ", "034120.KQ",
        ),
    ),
    "ship": RadarSector(
        code="ship",
        name="KODEX 조선TOP10",
        benchmark="0115D0.KS",
        benchmark_name="KODEX 조선",
        tickers=(
            "329180.KS", "009540.KS", "010140.KS", "042660.KS", "082740.KS",
            "071970.KS", "097230.KS", "439260.KS", "443060.KS", "017960.KS",
        ),
    ),
    "bio": RadarSector(
        code="bio",
        name="K-바이오",
        benchmark="244580.KS",
        benchmark_name="KODEX K-바이오",
        tickers=(
            "141080.KQ", "226950.KQ", "458870.KQ", "214450.KQ", "009420.KQ",
            "196170.KQ", "028300.KQ", "290650.KQ", "298380.KQ", "347850.KQ",
        ),
    ),
    "nasdaq30": RadarSector(
        code="nasdaq30",
        name="NASDAQ 30",
        benchmark="^IXIC",
        benchmark_name="NASDAQ",
        tickers=(
            "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST", "PEP",
            "AMD", "NFLX", "QCOM", "ADBE", "TXN", "AMGN", "ISRG", "HON", "INTU", "BKNG",
            "PANW", "MDLZ", "VRTX", "REGN", "GILD", "ADI", "ADP", "MELI", "LRCX", "MU",
        ),
    ),
}


def get_sector(code: str) -> RadarSector:
    key = code.lower().strip()
    if key not in SECTORS:
        available = ", ".join(sorted(SECTORS))
        raise ValueError(f"Unknown JP Radar sector: {code}. Available: {available}")
    return SECTORS[key]
