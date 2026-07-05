from __future__ import annotations

from universe.models import UniverseBuildResult, UniverseSymbol


class DynamicUniverseManager:
    """Builds a flexible recommendation universe from multiple sources."""

    def build(
        self,
        base: list[UniverseSymbol] | None = None,
        include: list[UniverseSymbol] | None = None,
        exclude: list[UniverseSymbol] | None = None,
    ) -> UniverseBuildResult:
        base = base or []
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
