"""What the session story card says about one day's session: its date, title, programs, focus time, start and
records. The words and numbers only; qt/story_card.py draws them. The design is in design/session-story/README.md"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from stat_lines import DAY_ABBREVIATIONS
from tracker import ActivityStore

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
# The part of the day a session started in, by the hour it began before, as Runna names a run ("Saturday Lunch Run").
# Anything from 9 pm until 5 am is late night
PARTS_OF_DAY = ((5, "Late Night"), (12, "Morning"), (14, "Lunch"), (17, "Afternoon"), (21, "Evening"), (24, "Late Night"))
SEPARATOR = " · "


@dataclass(frozen=True)
class StoryText:
    """Every piece of text on the card; the person can change any of them before saving"""

    date: str
    title: str
    programs: str
    focus_time: str
    started: str
    record_names: tuple[str, ...]

    @property
    def record_count(self) -> int:
        return len(self.record_names)

    def edited(self, **changes: str) -> "StoryText":
        return replace(self, **changes)


def part_of_day(hour: int) -> str:
    return next(name for before, name in PARTS_OF_DAY if hour < before)


def format_focus_time(seconds: int) -> str:
    """Hours and minutes as the card shows them, such as '1h 52m', or under an hour '45m'"""
    minutes = max(0, seconds) // 60
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def format_start(started_at: str) -> str:
    """A time stored as '13:05', as '1:05pm'"""
    moment = datetime.strptime(started_at, "%H:%M")
    return f"{moment.hour % 12 or 12}:{moment.minute:02d}{'am' if moment.hour < 12 else 'pm'}"


def format_date(day: date) -> str:
    """Such as '31 OCTOBER 2026', in capitals as the card's date pill shows it"""
    return f"{day.day} {MONTH_NAMES[day.month - 1]} {day.year}".upper()


def record_name(kind: str, day: date, program: str) -> str:
    """Name a record from ActivityStore.session_records, as of the day it was set"""
    today = date.today()
    if kind == "ever":
        return "Longest session ever"
    if kind == "year":
        return "Longest session this year" if day.year == today.year else f"Longest session of {day.year}"
    if kind == "month":
        this_month = (day.year, day.month) == (today.year, today.month)
        return "Longest session this month" if this_month else f"Longest session of {MONTH_NAMES[day.month - 1]} {day.year}"
    return f"Longest {program} session"


def story_text(store: ActivityStore, day: date) -> StoryText | None:
    """The card's text for the day's session, or None for a day with nothing tracked"""
    breakdown = store.day_application_totals(day)
    if not breakdown:
        return None
    starts = [started_at for _application, _seconds, started_at in breakdown if started_at]
    started_at = min(starts) if starts else None
    weekday = DAY_ABBREVIATIONS[day.weekday()]
    title = f"{weekday} {part_of_day(int(started_at[:2]))} Session" if started_at else f"{weekday} Session"
    main_program = breakdown[0][0]
    return StoryText(
        date=format_date(day),
        title=title,
        programs=SEPARATOR.join(application for application, _seconds, _start in breakdown),
        focus_time=format_focus_time(sum(seconds for _application, seconds, _start in breakdown)),
        started=format_start(started_at) if started_at else "",
        record_names=tuple(record_name(kind, day, main_program) for kind in store.session_records(day)),
    )
