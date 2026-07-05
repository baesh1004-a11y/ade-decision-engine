from __future__ import annotations

from universe.models import UniverseBuildResult, UniverseSymbol


DEFAULT_UNIVERSE = [
    UniverseSymbol("us", "NVDA", "NVIDIA", "Semiconductor", source="default"),
    UniverseSymbol("us", "MSFT", "Microsoft", "Software", source="default"),
    UniverseSymbol("us", "AAPL", "Apple", "Hardware", source="default"),
    UniverseSymbol("kr", "005930", "Samsung Electronics", "Semiconductor", source="default"),
    UniverseSymbol("kr", "000660", "SK Hynix", "Semiconductor", source="default"),
]


class DynamicUniverseManager:
    """Build and query the active recommendation universe."""

    def build(
        self,
        base: list[UniverseSymbol] | None = None,
        include: list[UniverseSymbol] | None = None,
        exclude: list[UniverseSymbol] | None = None,
    ) -> UniverseBuildResult:
        base = DEFAULT_UNIVERSE if base is None else base
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
