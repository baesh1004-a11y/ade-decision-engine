from __future__ import annotations

import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from html import unescape
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class EconomicEvent:
    when: datetime
    country: str
    category: str
    title: str
    importance: str
    source: str
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        local = self.when.astimezone(ZoneInfo("Asia/Seoul"))
        return {
            "일시(KST)": local.strftime("%Y-%m-%d %H:%M"),
            "국가": self.country,
            "구분": self.category,
            "이벤트": self.title,
            "중요도": self.importance,
            "출처": self.source,
            "비고": self.note,
        }


_CACHE: tuple[float, list[EconomicEvent], str | None] | None = None
_CACHE_TTL_SECONDS = 6 * 60 * 60
_HTTP_TIMEOUT_SECONDS = 15
_USER_AGENT = "Mozilla/5.0 (compatible; ADE-Decision-Engine/1.0; +https://github.com/baesh1004-a11y/ade-decision-engine)"

_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
_BLS_ICS_URLS = (
    "https://www.bls.gov/schedule/news_release/bls.ics",
    "https://www.bls.gov/schedule/news_release/bls.csv",
)
_BEA_URL = "https://www.bea.gov/news/schedule/"
_BOK_URL = "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?menuNo=200755&mtgSe=A&pYear={year}"


def _fetch_text(url: str, *, accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8") -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _clean_html(value: str) -> str:
    value = re.sub(r"<script.*?</script>|<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    current = date(year, month, 1)
    offset = (weekday - current.weekday()) % 7
    return current + timedelta(days=offset + (nth - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _us_holidays(year: int) -> list[EconomicEvent]:
    ny = ZoneInfo("America/New_York")
    rows: list[EconomicEvent] = []
    fixed = [
        (date(year, 1, 1), "New Year's Day"),
        (date(year, 7, 4), "Independence Day"),
        (date(year, 12, 25), "Christmas Day"),
    ]
    moving = [
        (_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
        (_nth_weekday(year, 2, 0, 3), "Presidents' Day"),
        (_last_weekday(year, 5, 0), "Memorial Day"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day"),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving Day"),
    ]
    for event_date, title in fixed + moving:
        rows.append(EconomicEvent(datetime.combine(event_date, dt_time(0, 0), ny), "미국", "휴장", title, "높음", "NYSE/Nasdaq 일정 규칙"))
    return rows


def _kr_holidays(year: int) -> list[EconomicEvent]:
    seoul = ZoneInfo("Asia/Seoul")
    fixed = [
        (date(year, 1, 1), "신정"),
        (date(year, 3, 1), "삼일절"),
        (date(year, 5, 5), "어린이날"),
        (date(year, 6, 6), "현충일"),
        (date(year, 8, 15), "광복절"),
        (date(year, 10, 3), "개천절"),
        (date(year, 10, 9), "한글날"),
        (date(year, 12, 25), "성탄절"),
    ]
    return [EconomicEvent(datetime.combine(event_date, dt_time(0, 0), seoul), "한국", "휴장", title, "높음", "KRX 공휴일 기본 규칙", "설·추석·대체공휴일은 거래소 공지로 재확인") for event_date, title in fixed]


def _quarterly_expiry(year: int) -> list[EconomicEvent]:
    seoul = ZoneInfo("Asia/Seoul")
    rows: list[EconomicEvent] = []
    for month in (3, 6, 9, 12):
        rows.append(EconomicEvent(datetime.combine(_nth_weekday(year, month, 3, 2), dt_time(15, 20), seoul), "한국", "파생상품", "선물·옵션 동시만기", "높음", "KRX 정기 만기 규칙"))
        rows.append(EconomicEvent(datetime.combine(_nth_weekday(year, month, 4, 3), dt_time(16, 0), ZoneInfo("America/New_York")), "미국", "파생상품", "분기 선물·옵션 만기", "높음", "미국 분기 만기 규칙"))
    return rows


def _load_fomc_events() -> list[EconomicEvent]:
    text = _clean_html(_fetch_text(_FOMC_URL))
    rows: list[EconomicEvent] = []
    eastern = ZoneInfo("America/New_York")
    month_map = {name: index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), start=1)}
    for year_text, block in re.findall(r"(20\d{2}) FOMC Meetings(.*?)(?=20\d{2} FOMC Meetings|Future Year:|$)", text, flags=re.S):
        year = int(year_text)
        for month_name, start_day, end_day in re.findall(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:-(\d{1,2}))?\*?",
            block,
        ):
            meeting_day = int(end_day or start_day)
            rows.append(EconomicEvent(datetime(year, month_map[month_name], meeting_day, 14, 0, tzinfo=eastern), "미국", "통화정책", "FOMC 금리결정", "매우 높음", "Federal Reserve", "정례회의 마지막 날 14:00 ET 기준"))
    return rows


def _unfold_ics(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_bls_datetime(raw: str) -> datetime:
    value = re.sub(r"[^0-9TZ]", "", raw)
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if "T" in value:
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo("America/New_York"))
    return datetime.strptime(value[:8], "%Y%m%d").replace(hour=8, minute=30, tzinfo=ZoneInfo("America/New_York"))


def _load_bls_ics(text: str) -> list[EconomicEvent]:
    lines = _unfold_ics(text)
    rows: list[EconomicEvent] = []
    current: dict[str, str] = {}
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            summary = current.get("SUMMARY", "")
            dt_raw = current.get("DTSTART", "")
            if not summary or not dt_raw:
                continue
            title_map = {
                "Consumer Price Index": ("물가", "미국 CPI 발표"),
                "Producer Price Index": ("물가", "미국 PPI 발표"),
                "Employment Situation": ("고용", "미국 고용보고서"),
            }
            matched = next((value for key, value in title_map.items() if key.lower() in summary.lower()), None)
            if not matched:
                continue
            category, title = matched
            rows.append(EconomicEvent(_parse_bls_datetime(dt_raw), "미국", category, title, "매우 높음", "U.S. Bureau of Labor Statistics", summary))
        elif ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";", 1)[0]] = value.replace("\\,", ",").replace("\\n", " ")
    return rows


def _load_bls_csv(text: str) -> list[EconomicEvent]:
    rows: list[EconomicEvent] = []
    eastern = ZoneInfo("America/New_York")
    title_map = {
        "Consumer Price Index": ("물가", "미국 CPI 발표"),
        "Producer Price Index": ("물가", "미국 PPI 발표"),
        "Employment Situation": ("고용", "미국 고용보고서"),
    }
    for line in text.splitlines():
        if not line.strip() or line.lower().startswith("date"):
            continue
        for key, (category, title) in title_map.items():
            if key.lower() not in line.lower():
                continue
            date_match = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", line)
            time_match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", line, flags=re.I)
            if not date_match:
                continue
            month, day, year = map(int, date_match.groups())
            hour, minute = (8, 30)
            if time_match:
                hour = int(time_match.group(1)) % 12
                minute = int(time_match.group(2))
                if time_match.group(3).upper() == "PM":
                    hour += 12
            rows.append(EconomicEvent(datetime(year, month, day, hour, minute, tzinfo=eastern), "미국", category, title, "매우 높음", "U.S. Bureau of Labor Statistics", line.strip()))
            break
    return rows


def _load_bls_events() -> list[EconomicEvent]:
    errors: list[str] = []
    for url in _BLS_ICS_URLS:
        try:
            text = _fetch_text(url, accept="text/calendar,text/csv,text/plain,*/*")
            rows = _load_bls_csv(text) if url.endswith(".csv") else _load_bls_ics(text)
            if rows:
                return rows
            errors.append(f"{url.rsplit('/', 1)[-1]}: 일정 없음")
        except Exception as exc:
            errors.append(f"{url.rsplit('/', 1)[-1]}: {exc}")
    raise RuntimeError("; ".join(errors))


def _load_bea_events() -> list[EconomicEvent]:
    text = _clean_html(_fetch_text(_BEA_URL))
    eastern = ZoneInfo("America/New_York")
    rows: list[EconomicEvent] = []
    pattern = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s+(AM|PM).*?(GDP \([^)]*Estimate\)[^|]{0,120}|GDP \([^)]*\)[^|]{0,120}|Personal Income and Outlays[^|]{0,120})", re.I)
    month_map = {name: index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), start=1)}
    year = datetime.now(timezone.utc).year
    for month_name, day, clock, meridiem, title in pattern.findall(text):
        hour, minute = map(int, clock.split(":"))
        if meridiem.upper() == "PM" and hour != 12:
            hour += 12
        if meridiem.upper() == "AM" and hour == 12:
            hour = 0
        clean_title = re.sub(r"\s+", " ", title).strip()
        category = "성장" if clean_title.startswith("GDP") else "소득·소비"
        rows.append(EconomicEvent(datetime(year, month_map[month_name.title()], int(day), hour, minute, tzinfo=eastern), "미국", category, clean_title, "높음", "U.S. Bureau of Economic Analysis"))
    return rows


def _load_bok_events(year: int) -> list[EconomicEvent]:
    text = _clean_html(_fetch_text(_BOK_URL.format(year=year)))
    seoul = ZoneInfo("Asia/Seoul")
    rows: list[EconomicEvent] = []
    for month, day in re.findall(r"(\d{2})월\s*(\d{2})일", text):
        rows.append(EconomicEvent(datetime(year, int(month), int(day), 10, 0, tzinfo=seoul), "한국", "통화정책", "한국은행 기준금리 결정", "매우 높음", "한국은행", "통화정책방향 결정회의"))
    unique: dict[tuple[datetime, str], EconomicEvent] = {(row.when, row.title): row for row in rows}
    return list(unique.values())


def _load_official_events(years: set[int]) -> tuple[list[EconomicEvent], list[str]]:
    events: list[EconomicEvent] = []
    errors: list[str] = []
    loaders = (("Fed", _load_fomc_events), ("BLS", _load_bls_events), ("BEA", _load_bea_events))
    for name, loader in loaders:
        try:
            events.extend(loader())
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    for year in sorted(years):
        try:
            events.extend(_load_bok_events(year))
        except Exception as exc:
            errors.append(f"BOK {year}: {exc}")
    return events, errors


def load_economic_calendar(*, days_ahead: int = 90, refresh: bool = False) -> tuple[list[dict[str, str]], str | None]:
    global _CACHE
    now = datetime.now(timezone.utc)
    if not refresh and _CACHE and time.time() - _CACHE[0] <= _CACHE_TTL_SECONDS:
        events, warning = _CACHE[1], _CACHE[2]
    else:
        years = {now.year, (now + timedelta(days=days_ahead)).year}
        events: list[EconomicEvent] = []
        for year in sorted(years):
            events.extend(_us_holidays(year))
            events.extend(_kr_holidays(year))
            events.extend(_quarterly_expiry(year))
        official, errors = _load_official_events(years)
        events.extend(official)
        events.sort(key=lambda item: item.when)
        warning = "일부 공식 일정 조회 실패: " + " | ".join(errors) if errors else None
        _CACHE = (time.time(), events, warning)

    end = now + timedelta(days=days_ahead)
    selected = [event for event in events if now - timedelta(days=1) <= event.when.astimezone(timezone.utc) <= end]
    deduped: dict[tuple[str, str, str], EconomicEvent] = {}
    for event in selected:
        key = (event.when.astimezone(timezone.utc).isoformat(), event.country, event.title)
        deduped[key] = event
    ordered = sorted(deduped.values(), key=lambda item: item.when)
    return [event.to_dict() for event in ordered], warning
