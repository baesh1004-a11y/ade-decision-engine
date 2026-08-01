from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
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


_CACHE: tuple[float, list[EconomicEvent]] | None = None
_CACHE_TTL_SECONDS = 6 * 60 * 60


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
        rows.append(
            EconomicEvent(
                datetime.combine(event_date, dt_time(0, 0), ny),
                "미국",
                "휴장",
                title,
                "높음",
                "NYSE/Nasdaq 일정 규칙",
                "정확한 연도별 예외는 거래소 공지로 재확인",
            )
        )
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
    return [
        EconomicEvent(
            datetime.combine(event_date, dt_time(0, 0), seoul),
            "한국",
            "휴장",
            title,
            "높음",
            "KRX 공휴일 기본 규칙",
            "설·추석·대체공휴일은 별도 공급원 연결 전 참고용",
        )
        for event_date, title in fixed
    ]


def _quarterly_expiry(year: int) -> list[EconomicEvent]:
    seoul = ZoneInfo("Asia/Seoul")
    rows: list[EconomicEvent] = []
    for month in (3, 6, 9, 12):
        kr_day = _nth_weekday(year, month, 3, 2)
        us_day = _nth_weekday(year, month, 4, 3)
        rows.append(
            EconomicEvent(
                datetime.combine(kr_day, dt_time(15, 20), seoul),
                "한국",
                "파생상품",
                "선물·옵션 동시만기",
                "높음",
                "KRX 정기 만기 규칙",
            )
        )
        rows.append(
            EconomicEvent(
                datetime.combine(us_day, dt_time(16, 0), ZoneInfo("America/New_York")),
                "미국",
                "파생상품",
                "분기 선물·옵션 만기",
                "높음",
                "미국 분기 만기 규칙",
            )
        )
    return rows


def load_economic_calendar(*, days_ahead: int = 90, refresh: bool = False) -> tuple[list[dict[str, str]], str | None]:
    global _CACHE
    now = datetime.now(timezone.utc)
    if not refresh and _CACHE and time.time() - _CACHE[0] <= _CACHE_TTL_SECONDS:
        events = _CACHE[1]
    else:
        years = {now.year, (now + timedelta(days=days_ahead)).year}
        events: list[EconomicEvent] = []
        for year in sorted(years):
            events.extend(_us_holidays(year))
            events.extend(_kr_holidays(year))
            events.extend(_quarterly_expiry(year))
        events.sort(key=lambda item: item.when)
        _CACHE = (time.time(), events)

    end = now + timedelta(days=days_ahead)
    selected = [event for event in events if now - timedelta(days=1) <= event.when.astimezone(timezone.utc) <= end]
    warning = (
        "현재는 규칙 기반 휴장·만기 일정만 제공합니다. FOMC·CPI·고용·한국은행 금통위는 "
        "공식 일정 공급원 연결 전까지 표시하지 않습니다."
    )
    return [event.to_dict() for event in selected], warning
