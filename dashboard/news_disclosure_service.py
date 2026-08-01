from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from threading import RLock
from typing import Any
from urllib.parse import quote_plus

import requests


@dataclass(frozen=True)
class MarketNewsItem:
    published_at: datetime
    title: str
    source: str
    url: str
    kind: str
    ticker: str = ""
    company: str = ""
    importance: str = "보통"

    def to_dict(self) -> dict[str, str]:
        local = self.published_at.astimezone(timezone(timedelta(hours=9)))
        return {
            "일시(KST)": local.strftime("%Y-%m-%d %H:%M"),
            "구분": self.kind,
            "종목": self.company or self.ticker or "시장",
            "제목": self.title,
            "출처": self.source,
            "중요도": self.importance,
            "링크": self.url,
        }


_CACHE_LOCK = RLock()
_CACHE: dict[str, tuple[float, list[dict[str, str]], str | None]] = {}
_CACHE_TTL_SECONDS = 15 * 60
_REQUEST_TIMEOUT_SECONDS = 12
_USER_AGENT = "ADE-Decision-Engine/1.0"
_IMPORTANT_DART_KEYWORDS = (
    "단일판매",
    "공급계약",
    "유상증자",
    "무상증자",
    "전환사채",
    "신주인수권",
    "영업실적",
    "매출액",
    "타법인주식",
    "최대주주",
    "합병",
    "분할",
    "자기주식",
)


def _clean_title(value: str) -> str:
    text = unescape(str(value or ""))
    while "<" in text and ">" in text:
        start = text.find("<")
        end = text.find(">", start)
        if end < 0:
            break
        text = text[:start] + text[end + 1 :]
    return " ".join(text.split())


def _parse_rss_datetime(value: str) -> datetime:
    raw = str(value or "").strip()
    for pattern in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            parsed = datetime.strptime(raw, pattern)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _dedupe(rows: list[MarketNewsItem]) -> list[MarketNewsItem]:
    result: list[MarketNewsItem] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: item.published_at, reverse=True):
        key = f"{row.kind}:{row.ticker}:{row.title.strip().lower()}"
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _fetch_google_news(query: str, *, ticker: str = "", company: str = "", limit: int = 8) -> list[MarketNewsItem]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )
    response = requests.get(url, timeout=_REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": _USER_AGENT})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows: list[MarketNewsItem] = []
    for item in root.findall("./channel/item")[:limit]:
        title = _clean_title(item.findtext("title") or "")
        link = str(item.findtext("link") or "").strip()
        published_at = _parse_rss_datetime(item.findtext("pubDate") or "")
        source_node = item.find("source")
        source = _clean_title(source_node.text if source_node is not None and source_node.text else "Google News")
        if not title or not link:
            continue
        rows.append(
            MarketNewsItem(
                published_at=published_at,
                title=title,
                source=source or "Google News",
                url=link,
                kind="뉴스",
                ticker=ticker,
                company=company,
                importance="보통",
            )
        )
    return rows


def _dart_importance(report_name: str) -> str:
    return "높음" if any(keyword in report_name for keyword in _IMPORTANT_DART_KEYWORDS) else "보통"


def _fetch_dart_disclosures(
    *,
    ticker: str = "",
    company: str = "",
    days: int = 7,
    limit: int = 20,
) -> tuple[list[MarketNewsItem], str | None]:
    api_key = os.getenv("DART_API_KEY", "").strip()
    if not api_key:
        return [], "DART_API_KEY 미설정"
    end = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date()
    begin = end - timedelta(days=max(1, int(days)))
    params: dict[str, Any] = {
        "crtfc_key": api_key,
        "bgn_de": begin.strftime("%Y%m%d"),
        "end_de": end.strftime("%Y%m%d"),
        "page_count": min(max(limit, 1), 100),
        "sort": "date",
        "sort_mth": "desc",
    }
    if company:
        params["corp_name"] = company
    response = requests.get(
        "https://opendart.fss.or.kr/api/list.json",
        params=params,
        timeout=_REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    status = str(payload.get("status") or "")
    if status == "013":
        return [], None
    if status and status != "000":
        return [], f"DART {status}: {payload.get('message', '조회 실패')}"
    rows: list[MarketNewsItem] = []
    for item in payload.get("list") or []:
        report_name = _clean_title(item.get("report_nm") or "")
        company_name = _clean_title(item.get("corp_name") or company)
        received = str(item.get("rcept_dt") or "")
        receipt_no = str(item.get("rcept_no") or "")
        if len(received) == 8:
            published_at = datetime.strptime(received, "%Y%m%d").replace(tzinfo=timezone(timedelta(hours=9)))
        else:
            published_at = datetime.now(timezone.utc)
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}" if receipt_no else "https://dart.fss.or.kr/"
        rows.append(
            MarketNewsItem(
                published_at=published_at.astimezone(timezone.utc),
                title=report_name,
                source="DART",
                url=url,
                kind="공시",
                ticker=ticker,
                company=company_name,
                importance=_dart_importance(report_name),
            )
        )
    return rows, None


def _cached(key: str, loader: Any) -> tuple[list[dict[str, str]], str | None]:
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] <= _CACHE_TTL_SECONDS:
            return cached[1], cached[2]
    rows, warning = loader()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), rows, warning)
    return rows, warning


def load_market_news(*, limit: int = 10, refresh: bool = False) -> tuple[list[dict[str, str]], str | None]:
    key = f"market:{limit}"
    if refresh:
        with _CACHE_LOCK:
            _CACHE.pop(key, None)

    def loader() -> tuple[list[dict[str, str]], str | None]:
        warnings: list[str] = []
        rows: list[MarketNewsItem] = []
        queries = [
            "한국 증시 코스피 코스닥",
            "미국 증시 연준 물가 고용",
            "반도체 2차전지 자동차 바이오 방산 증시",
        ]
        for query in queries:
            try:
                rows.extend(_fetch_google_news(query, limit=max(4, limit // len(queries) + 2)))
            except Exception as exc:
                warnings.append(f"뉴스 조회 실패: {exc}")
        normalized = [item.to_dict() for item in _dedupe(rows)[:limit]]
        return normalized, " · ".join(warnings) if warnings else None

    return _cached(key, loader)


def load_security_news(
    ticker: str,
    company: str,
    *,
    limit: int = 12,
    refresh: bool = False,
) -> tuple[list[dict[str, str]], str | None]:
    ticker_text = str(ticker or "").strip()
    company_text = str(company or "").strip()
    key = f"security:{ticker_text}:{company_text}:{limit}"
    if refresh:
        with _CACHE_LOCK:
            _CACHE.pop(key, None)

    def loader() -> tuple[list[dict[str, str]], str | None]:
        warnings: list[str] = []
        rows: list[MarketNewsItem] = []
        query = " ".join(part for part in (company_text, ticker_text, "주가 실적 공시") if part)
        try:
            rows.extend(_fetch_google_news(query or ticker_text, ticker=ticker_text, company=company_text, limit=limit))
        except Exception as exc:
            warnings.append(f"뉴스 조회 실패: {exc}")
        try:
            disclosures, dart_warning = _fetch_dart_disclosures(
                ticker=ticker_text,
                company=company_text,
                days=14,
                limit=limit,
            )
            rows.extend(disclosures)
            if dart_warning:
                warnings.append(dart_warning)
        except Exception as exc:
            warnings.append(f"DART 조회 실패: {exc}")
        normalized = [item.to_dict() for item in _dedupe(rows)[:limit]]
        return normalized, " · ".join(warnings) if warnings else None

    return _cached(key, loader)


def news_diagnostics() -> dict[str, Any]:
    return {
        "news_source": "Google News RSS",
        "dart_configured": bool(os.getenv("DART_API_KEY", "").strip()),
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
    }
