"""Document schedules and daily feeds.

Each facility expects documents on a schedule set from its asset class: what, in which format,
how often, by which channel and by Oxane's own deadline. Code works out every expected delivery
in a period and checks each against what arrived and when.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

HOLIDAYS = frozenset({date(2026, 5, 25), date(2026, 6, 19)})


def business_days(start: date, end: date, holidays: frozenset[date] = HOLIDAYS) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            days.append(day)
        day += timedelta(days=1)
    return days


def add_business_days(day: date, count: int, holidays: frozenset[date] = HOLIDAYS) -> date:
    while count:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            count -= 1
    return day


@dataclass(frozen=True)
class Delivery:
    feed: str
    as_of: date
    deadline: datetime
    received: datetime | None
    rows: int

    @property
    def status(self) -> str:
        if self.received is None:
            return "missing"
        return "late" if self.received > self.deadline else "on_time"

    @property
    def minutes_late(self) -> int:
        if self.received is None or self.received <= self.deadline:
            return 0
        return int((self.received - self.deadline).total_seconds() // 60)


def deadline_for(as_of: date, lag_business_days: int, at: time) -> datetime:
    """A daily file's deadline: `lag` business days after its as-of date, at a set time."""
    return datetime.combine(add_business_days(as_of, lag_business_days) if lag_business_days
                            else as_of, at)


def check_daily(feed: str, days: list[date], lag: int, at: time,
                arrived: dict[date, tuple[datetime | None, int]]) -> list[Delivery]:
    """Every expected delivery of one daily feed, with its status."""
    out = []
    for day in days:
        received, rows = arrived.get(day, (None, 0))
        out.append(Delivery(feed, day, deadline_for(day, lag, at), received, rows))
    return out


def coverage_gaps(held: dict[date, set[str]], priced: dict[date, set[str]]) -> dict[date, int]:
    """For each day, how many positions held have no price that day."""
    return {day: len(ids - priced.get(day, set())) for day, ids in held.items()}
