from __future__ import annotations

from data.providers import FDRProvider
from universe.models import UniverseBuildResult, UniverseSymbol


DEFAULT_UNIVERSE = [
    UniverseSymbol("us", "NVDA", "NVIDIA", "Semiconductor", source="default"),
    UniverseSymbol("us", "MSFT", "Microsoft", "Software", source="default"),
    UniverseSymbol("us", "AAPL", "Apple", "Hardware", source="default"),
    UniverseSymbol("kr", "005930", "Samsung Electronics", "Semiconductor", source="default"),
    UniverseSymbol("kr", "000660", "SK Hynix", "Semiconductor", source="default"),
]


class DynamicUniverseManager:
    """Build and query the active recommendation universe.

    KR universe is loaded from FDR KOSPI/KOSDAQ listings when available.
    If FDR listing fails, it falls back to DEFAULT_UNIVERSE.
    """

    def build(
        self,
        base: list[UniverseSymbol] | None = None,
        include: list[UniverseSymbol] | None = None,
        exclude: list[UniverseSymbol] | None = None,
    ) -> UniverseBuildResult:
        base = self._default_base() if base is None else base
        include = include or []
        exclude = exclude or []

        merged: dict[str, UniverseSymbol] = {}
        for symbol in base + include:
            merged[symbol.key] = symbol

        excluded_keys = {symbol.key for symbol in exclude}
        final = [symbol for key, symbol in merged.items() if key not in excluded_keys]
        final = sorted(final, key=lambda item: (item.market, item.ticker))

        return UniverseBuildResult(
            total_candidates=len(base) + len(include),
            included_count=len(include),
            excluded_count=len(exclude),
            final_count=len(final),
            symbols=final,
        )

    def active(self, market: str | None = None) -> list[UniverseSymbol]:
        symbols = self.build().symbols
        if market is None:
            return symbols
        market = market.lower()
        return [item for item in symbols if item.market.lower() == market]

    def _default_base(self) -> list[UniverseSymbol]:
        try:
            kr_symbols = [
                UniverseSymbol(
                    market=str(item["market"]),
                    ticker=str(item["ticker"]),
                    name=item.get("name"),
                    sector=item.get("sector"),
                    source=str(item.get("source") or "FDR"),
                )
                for item in FDRProvider().list_kr_symbols()
            ]
            us_symbols = [s for s in DEFAULT_UNIVERSE if s.market == "us"]
            if kr_symbols:
                return kr_symbols + us_symbols
        except Exception:
            pass
        return DEFAULT_UNIVERSE
