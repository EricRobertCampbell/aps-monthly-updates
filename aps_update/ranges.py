from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Window:
    """Inclusive start, exclusive end, on the report calendar."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"empty window {self.start} .. {self.end}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    @property
    def id(self) -> str:
        return f"{self.start.isoformat()}_{self.end.isoformat()}"

    @property
    def last_day(self) -> date:
        return self.end - timedelta(days=1)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Expected YYYY-MM-DD, got {value!r}") from exc


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise SystemExit(f"Unknown timezone {name!r}") from exc


def today_in(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def utc_stamp(day: date, tz: ZoneInfo, *, end_of_day: bool = False) -> str:
    """UTC timestamp for local midnight, or one second before the next midnight."""
    moment = datetime(day.year, day.month, day.day, tzinfo=tz)
    if end_of_day:
        moment = moment + timedelta(days=1) - timedelta(seconds=1)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def retention_floor(today: date, days: int) -> date:
    return today - timedelta(days=days)


def covers_retention(window: Window, today: date, days: int = 31) -> bool:
    return window.start >= retention_floor(today, days)


def split_for_storage(window: Window) -> list[Window]:
    """Keep a short window whole. Split a longer one on calendar months.

    A month is the unit worth keeping when meetings are skipped. Buffer's
    insight history is about 31 days, which is also the longest month, so
    one month is the largest window that can still be collected intact.
    """
    if window.days <= 31:
        return [window]
    chunks: list[Window] = []
    cursor = window.start
    while cursor < window.end:
        if cursor.month == 12:
            month_end = date(cursor.year + 1, 1, 1)
        else:
            month_end = date(cursor.year, cursor.month + 1, 1)
        chunk_end = min(window.end, month_end)
        chunks.append(Window(cursor, chunk_end))
        cursor = chunk_end
    return chunks


def slice_days(window: Window, size: int) -> list[Window]:
    chunks: list[Window] = []
    cursor = window.start
    while cursor < window.end:
        chunks.append(Window(cursor, min(window.end, cursor + timedelta(days=size))))
        cursor = chunks[-1].end
    return chunks


def overlaps(left: Window, right: Window) -> bool:
    return left.start < right.end and right.start < left.end


def default_window(today: date, last_end: date | None) -> Window | None:
    """Through yesterday. First run keeps the last 30 days Buffer can still return."""
    end = today
    start = last_end if last_end is not None else end - timedelta(days=30)
    if start >= end:
        return None
    return Window(start, end)


def format_day(day: date) -> str:
    return f"{day.day} {day.strftime('%b')} {day.year}"


def format_window(window: Window) -> str:
    start, last = window.start, window.last_day
    if start == last:
        return format_day(start)
    if start.year == last.year and start.month == last.month:
        return f"{start.day}–{last.day} {start.strftime('%b')} {start.year}"
    if start.year == last.year:
        return f"{start.day} {start.strftime('%b')} – {last.day} {last.strftime('%b')} {start.year}"
    return f"{format_day(start)} – {format_day(last)}"
