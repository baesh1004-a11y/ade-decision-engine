from __future__ import annotations

from cache.vector_cache import build_vector_cache


def main() -> None:
    count = build_vector_cache("datahub/market.db")
    print("\n========================================")
    print(" ADE VECTOR CACHE BUILD")
    print("========================================")
    print(f"Cached vectors: {count}")


if __name__ == "__main__":
    main()
