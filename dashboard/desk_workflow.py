"""Pure display workflow; saved recommendation order is never recalculated."""

from __future__ import annotations

from recommendation.evidence import decode

REVIEW_FILTERS = ("전체", "미검토", "검토 중", "관찰", "주문 검토")


def review_status(review: dict | None) -> str:
    return str(review.get("verdict") or "검토 중") if review else "미검토"


def candidates(
    rows: list[dict], reviews: dict[str, dict], query: str = "", status: str = "전체"
) -> list[dict]:
    term = query.strip().casefold()
    result = []
    for source in rows:
        row = dict(source)
        row["symbol"] = (
            row.get("name")
            or decode(row.get("payload_json")).get("name")
            or str(row["ticker"])
        )
        row["review_status"] = review_status(reviews.get(str(row["ticker"])))
        if term and term not in f"{row['ticker']} {row['symbol']}".casefold():
            continue
        if status != "전체" and status != row["review_status"]:
            continue
        result.append(row)
    return result


def next_unreviewed(
    rows: list[dict], reviews: dict[str, dict], ticker: str
) -> str | None:
    tickers = [str(row["ticker"]) for row in rows]
    if ticker not in tickers:
        return next((value for value in tickers if value not in reviews), None)
    start = tickers.index(ticker) + 1
    ordered = tickers[start:] + tickers[: start - 1]
    return next((value for value in ordered if value not in reviews), None)
