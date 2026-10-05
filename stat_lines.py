"""What the Stats module says: its rows of figures and the sessions in the period the calendar shows. Shared by the
Tk and Qt interfaces, so it holds no drawing"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app_config import COLORS, MONTHLY_AVERAGE_DAYS, ROLLING_AVERAGE_DAYS
from tracker import ActivityStore

DAY_ABBREVIATIONS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ROLLING_AVERAGES = (ROLLING_AVERAGE_DAYS, MONTHLY_AVERAGE_DAYS)
# The medal shown beside this week's total, by how its total ranks among past weeks: the colour for a week
# in the top 10, 25 or 50 percent. Drawn like the longest-session award, in the tier's colour
MEDAL_TIERS = ((10, "gold"), (25, "silver"), (50, "bronze"))


def format_change(seconds: float) -> str:
    """Describe how much a daily average moved against the period before, such as '+24m' or '-1h 05m'"""
    if round(abs(seconds) / 60) == 0:
        return "same"
    return f"{'+' if seconds > 0 else '-'}{format_hours_minutes(abs(seconds))}"


def format_hours_minutes(seconds: float) -> str:
    """Format a duration without seconds, such as '14h 32m'"""
    minutes = round(max(0, seconds) / 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def format_clock(started_at: str) -> str:
    """A time stored as '13:05', as '1:05 PM'"""
    return datetime.strptime(started_at, "%H:%M").strftime("%I:%M %p").lstrip("0")


def medal_for_rank(rank: int | None) -> str:
    """Return the medal colour for a week ranked in the top `rank` percent of weeks, or '' for none"""
    return next((name for limit, name in MEDAL_TIERS if rank is not None and rank <= limit), "")


@dataclass(frozen=True)
class StatLine:
    """One row of the Stats module: what it is on the left, and its value in a column on the right

    Values line up down the right so the eye can run down one column of figures. A row may also carry a medal
    before its value, and a note in a narrow last column: how an average changed, or a day's rating
    """

    label: str
    value: str = ""
    label_color: str = COLORS["muted"]
    value_color: str = COLORS["text"]
    value_bold: bool = False
    # A colour name from COLORS, see MEDAL_TIERS
    medal: str = ""
    note: str = ""
    note_color: str = COLORS["muted"]
    # The note is a rating, drawn like the rating on a calendar day
    rating: bool = False
    # Space above and below the row
    above: int = 0
    below: int = 1


def figure_lines(store: ActivityStore, today: date) -> list[StatLine]:
    """This week, the averages, the best day, the longest session and the best start time. These always run up
    to today, whichever period the calendar shows"""
    week_seconds = store.total_for_range(today - timedelta(days=today.weekday()), today)
    rank = store.week_rank(today)
    medal = medal_for_rank(rank)
    lines = [StatLine("This week", format_hours_minutes(week_seconds), value_bold=True, medal=medal, below=0 if medal else 3)]
    if medal:
        lines.append(StatLine("", f"top {rank}% of your weeks", value_color=COLORS["muted"], below=3))
    for days in ROLLING_AVERAGES:
        average_seconds = store.rolling_daily_average(days, today)
        change = average_seconds - store.rolling_daily_average(days, today - timedelta(days=days))
        lines.append(
            StatLine(
                f"{days}-day average",
                f"{format_hours_minutes(average_seconds)}/day",
                note=format_change(change),
                note_color=COLORS["active_green"] if round(change / 60) > 0 else COLORS["muted"],
            )
        )
    best_weekday = store.best_weekday_average(today)
    if best_weekday is None:
        lines.append(StatLine("Best day", "--"))
    else:
        weekday, weekday_seconds = best_weekday
        lines.append(StatLine("Best day", f"{DAY_ABBREVIATIONS[weekday]} ·{format_hours_minutes(weekday_seconds)}/day"))
    longest = store.longest_session()
    if longest is None:
        lines.append(StatLine("Longest session", "--"))
    else:
        record_day, record_seconds = longest
        lines.append(StatLine("Longest session", f"{record_day.day} {record_day.strftime('%b %Y')} · {format_hours_minutes(record_seconds)}"))
    # Shown only once a day has been rated
    best_start = store.best_start_time()
    if best_start is not None:
        started_at, rating = best_start
        lines.append(StatLine("Best start time", format_clock(started_at), note=f"\U00002b50 {rating}", note_color=COLORS["gold"], rating=True))
    return lines


def calendar_period(view: str, month: date) -> tuple[date, date]:
    """The first and last day the calendar shows: its month, or in the year view its year"""
    if view == "Year":
        return date(month.year, 1, 1), date(month.year, 12, 31)
    return month, date(month.year + month.month // 12, month.month % 12 + 1, 1) - timedelta(days=1)


def _period_name(view: str, start: date) -> str:
    return str(start.year) if view == "Year" else calendar.month_name[start.month]


def session_summary_lines(store: ActivityStore, view: str, month: date) -> list[StatLine]:
    """Unlike the figures above, the sessions counted are those in the period the calendar shows"""
    start, end = calendar_period(view, month)
    sessions = store.qualifying_sessions(start, end)
    if not sessions:
        return [StatLine(no_sessions_text(store, view, start, end), above=3)]
    start_minutes = [int(started_at[:2]) * 60 + int(started_at[3:5]) for _, started_at, _ in sessions]
    average_minutes = round(sum(start_minutes) / len(start_minutes))
    average_start = (datetime.min + timedelta(minutes=average_minutes)).strftime("%I:%M %p").lstrip("0")
    count = f"{len(sessions)} session{'' if len(sessions) == 1 else 's'} in {_period_name(view, start)}"
    return [StatLine(count, f"avg start {average_start}", value_color=COLORS["muted"], above=3)]


def no_sessions_text(store: ActivityStore, view: str, start: date, end: date) -> str:
    period_seconds = store.total_for_range(start, end)
    if not period_seconds:
        return "No sessions for this period"
    # Time was tracked, but no single day reached the session minimum
    return f"{format_hours_minutes(period_seconds)} tracked in {_period_name(view, start)} · no day reached 15m"
