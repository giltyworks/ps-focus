"""Calendar and stats modules, with the day overview and productivity rating dialogs"""

from __future__ import annotations

import calendar
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app_config import (
    COLORS,
    EDGE_PADDING,
    LINE_PADDING,
    MODULE_MARGIN,
    MODULE_CANVAS_WIDTH,
    MODULE_GAP,
    MONTHLY_AVERAGE_DAYS,
    ROLLING_AVERAGE_DAYS,
    SESSION_MINIMUM_SECONDS,
    format_duration,
)
from rendering import render_award_badge, render_crescent_icon, render_flame_icon, render_rounded_box, to_photo_image
from ui_modules import MODULE_TITLE_PADDING
from widgets import CONTROL_TAG, CanvasButton, drawing_surface, show_drawing


DAY_ABBREVIATIONS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# Font of the star and number showing a day's productivity rating, on the calendar and in Stats
CALENDAR_RATING_FONT = ("Segoe UI Emoji", 8)
# Pixel size of the gold award shown on the day that holds the longest-session record
AWARD_BADGE_SIZE = 16
# Bold thickens the outline of the empty stars in the day overview's productivity rating
RATING_STAR_FONT = ("Segoe UI Symbol", 16, "bold")
# Pixels the badge is nudged down so its middle lines up with the middle of the text beside it
AWARD_BADGE_DROP = 5
STREAK_ICON_SIZE = 14
# The first and last years the calendar can be stepped to. Dates stop at year 9999, and the month after
# the one shown must also exist for its totals to be worked out
CALENDAR_YEARS = (1, 9998)
# Calendar geometry, in pixels. Above the days: the space under the title row and under the legend,
# and the side of the legend's blue square
CALENDAR_ROW_GAP = 5
LEGEND_SQUARE_SIZE = 13
# The space between a streak counter's icon and its text, and between the two counters
STREAK_ICON_GAP = 5
STREAK_COUNTER_GAP = 6
# Month view: the space left between one day's cell and the next, and below the weekday names.
# The cells themselves run from one side of the module to the other
CALENDAR_CELL_GAP = 3
CALENDAR_HEADER_GAP = 1
# Corner radius of the month view's cells (as round as the buttons), the year view's squares and the
# legend's square; 0 is square
CALENDAR_CELL_RADIUS = 6
YEAR_DAY_RADIUS = 2
LEGEND_SQUARE_RADIUS = 3
# How far the day number sits from the top of its cell and the rating from the bottom, and how far the
# rating's line is drawn into the day number's, whose lowest pixels digits never use
CALENDAR_DAY_NUMBER_INSET = 4
CALENDAR_RATING_INSET = 4
CALENDAR_RATING_OVERLAP = 0
# The same three in the landscape layout, where the cells are kept as short as they can be
LANDSCAPE_DAY_NUMBER_INSET = 2
LANDSCAPE_RATING_INSET = 1
LANDSCAPE_RATING_OVERLAP = 3
# Year view: three months to a row, each a block of this height holding squares of this size and spacing
YEAR_MONTH_HEIGHT = 82
YEAR_MONTH_FONT = ("Segoe UI Semibold", 10)
YEAR_DAY_SIZE = (13, 8)
YEAR_DAY_PITCH = (15, 9)
# Landscape layout's side strip: how far the module's name sits from the top, as on other modules, and the
# space between the strip's rows
MODULE_TITLE_TOP = 5
SIDE_STRIP_GAP = 6
SIDE_ARROW_GAP = 5
# Space between the strip's widest line and the days: as far as the strip's text is from the module's edge
SIDE_STRIP_RIGHT_MARGIN = MODULE_MARGIN
# Stats: the space kept on each side of its lines
STATS_MARGIN = EDGE_PADDING - 2
# Space under the last line of the stats
STATS_BOTTOM_PADDING = 5
ROLLING_AVERAGES = (ROLLING_AVERAGE_DAYS, MONTHLY_AVERAGE_DAYS)
# The medal shown beside this week's total, by how its total ranks among past weeks: the colour for a week
# in the top 10, 25 or 50 percent. Drawn like the longest-session award, in the tier's colour
MEDAL_TIERS = ((10, "gold"), (25, "silver"), (50, "bronze"))
MEDAL_SIZE = 14
MEDAL_GAP = 4
# Space between a row's value and the narrow column of notes after it
STAT_NOTE_GAP = 8


def format_change(seconds: float) -> str:
    """Describe how much a daily average moved against the period before, such as '+24m' or '-1h 05m'"""
    if round(abs(seconds) / 60) == 0:
        return "same"
    return f"{'+' if seconds > 0 else '-'}{format_hours_minutes(abs(seconds))}"


def format_hours_minutes(seconds: float) -> str:
    """Format a duration without seconds, such as '14h 32m'"""
    minutes = round(max(0, seconds) / 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


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


class CalendarMixin:
    def _build_calendar(self) -> None:
        """Build the calendar as one canvas holding its title row, legend, and month or year of days

        Tk repaints every widget separately while the window is resized. Built from a widget for each day
        and label, the calendar alone had well over a hundred and made the window slow to drag
        """
        self.calendar_panel, calendar_content = self._create_module_frame("calendar", "Calendar")
        canvas = tk.Canvas(calendar_content, bg=COLORS["panel"], highlightthickness=0, width=MODULE_CANVAS_WIDTH, height=1)
        canvas.pack(fill="x")
        self.calendar_canvas = canvas

        def button(text: str, command, **options) -> CanvasButton:
            return CanvasButton(canvas, text, command, bg=COLORS["panel_alt"], fg=COLORS["text"], font=self.font_small, pady=6, **options)

        self.calendar_view_toggle = button("month", self._toggle_calendar_view, width=6, padx=11)
        self.calendar_step_buttons = (
            button("<", lambda: self._shift_calendar_month(-1), padx=14),
            button(">", lambda: self._shift_calendar_month(1), padx=14),
        )
        # The landscape strip's narrower pair, together as wide as the month/year toggle above them
        arrow_width = (self.calendar_view_toggle.width - SIDE_ARROW_GAP) // 2
        arrow_padx = (arrow_width - self.font_small.measure("<")) // 2
        self.calendar_side_step_buttons = (
            button("<", lambda: self._shift_calendar_month(-1), padx=arrow_padx),
            button(">", lambda: self._shift_calendar_month(1), padx=arrow_padx),
        )
        # Flat icons drawn to match the award badge; kept on self so the images outlive this method
        self.streak_icons = {
            "rest": to_photo_image(render_crescent_icon(STREAK_ICON_SIZE, COLORS["panel"])),
            "week": to_photo_image(render_flame_icon(STREAK_ICON_SIZE, COLORS["panel"])),
        }
        self.calendar_line_height = self.font_small.metrics("linespace") + 2 * LINE_PADDING
        rating_height = tkfont.Font(font=CALENDAR_RATING_FONT).metrics("linespace")
        self.calendar_landscape_cell_height = (
            LANDSCAPE_DAY_NUMBER_INSET + self.font_small.metrics("linespace") - LANDSCAPE_RATING_OVERLAP + rating_height + LANDSCAPE_RATING_INSET
        )
        self.calendar_cell_height = (
            CALENDAR_DAY_NUMBER_INSET + self.font_small.metrics("linespace") - CALENDAR_RATING_OVERLAP + rating_height + CALENDAR_RATING_INSET
        )
        self.calendar_drawn_width = 0
        # Rounded cells are pictures, one for each size and colour, kept here so they are drawn only once
        self.calendar_cell_pictures: dict[tuple, tk.PhotoImage] = {}
        # The area of each day that can be opened, as (left, top, right, bottom, day)
        self.calendar_day_boxes: list[tuple[int, int, int, int, date]] = []
        canvas.bind("<Configure>", self._calendar_canvas_resized)
        canvas.bind("<Button-1>", self._calendar_day_clicked)
        canvas.bind("<Motion>", self._calendar_pointer_moved)
        self._draw_calendar()

    def _build_stats(self) -> None:
        """Build the stats as one canvas of text lines, see _build_calendar for why"""
        self.stats_panel, stats_content = self._create_module_frame("stats", "Stats")
        self.stats_canvas = tk.Canvas(stats_content, bg=COLORS["panel"], highlightthickness=0, width=MODULE_CANVAS_WIDTH, height=1)
        self.stats_canvas.pack(fill="x")
        self.stats_drawn: tuple | None = None
        self.stats_canvas.bind("<Configure>", self._stats_canvas_resized)
        self.stat_rating_font = tkfont.Font(font=CALENDAR_RATING_FONT)
        self.stat_medals = {
            name: to_photo_image(render_award_badge(MEDAL_SIZE, COLORS["panel"], COLORS[name])) for _limit, name in MEDAL_TIERS
        }

    def _module_canvas_width(self, canvas: tk.Canvas) -> int:
        # Until its module has been laid out a canvas may be given less room than it asked for, or none at all,
        # so it is drawn at least as wide as it asked to be
        return max(canvas.winfo_width(), int(canvas.cget("width")), MODULE_CANVAS_WIDTH)

    def _draw_calendar(self) -> None:
        year = self.calendar_month.year
        month = self.calendar_month.month
        today = date.today()
        width = self._module_canvas_width(self.calendar_canvas)
        streaks = self.store.calendar_streaks()
        if self.calendar_view == "Year":
            title = str(year)
            # For each month, the days that reached the session minimum
            days = tuple(
                frozenset(day for day, seconds in self.store.month_totals(year, month_index).items() if seconds >= SESSION_MINIMUM_SECONDS)
                for month_index in range(1, 13)
            )
        else:
            title = f"{calendar.month_name[month]} {year}"
            totals = self.store.month_totals(year, month)
            ratings = self.store.month_ratings(year, month)
            weeks = calendar.monthcalendar(year, month)
            days = tuple(
                (day, totals.get(day, 0) >= SESSION_MINIMUM_SECONDS, ratings.get(day)) for week in weeks for day in week if day
            )
        landscape = self._landscape()
        visual_state = (self.calendar_view, year, month, today, width, streaks, days, landscape)
        self.calendar_last_refresh = datetime.now()
        if visual_state == self.calendar_visual_state:
            return
        self.calendar_visual_state = visual_state

        canvas = self.calendar_canvas
        canvas.delete("all")
        # Everything but the buttons is drawn on a hidden twin and shown as one picture, see widgets.drawing_surface
        self.calendar_surface = drawing_surface(canvas)
        self.calendar_drawn_width = width
        self.calendar_day_boxes = []
        if landscape:
            # The title, buttons and legend go down a strip on the left, and the days start at the very top
            side_bottom = self._draw_calendar_side(title, *streaks)
            top, grid_left = 0, self._calendar_side_width()
        else:
            top, grid_left = self._draw_calendar_heading(width, title, *streaks), 0
        if self.calendar_view == "Year":
            bottom = self._draw_year(top, width - grid_left, year, days, today, grid_left)
        else:
            bottom = self._draw_month(top, width - grid_left, year, month, weeks, totals, ratings, today, grid_left)
        if landscape:
            bottom = max(bottom, side_bottom)
        # Only the rows in use are given room, so a six-week month is never cut short
        canvas.configure(height=bottom)
        show_drawing(canvas, self.calendar_surface, width, bottom)

    def _draw_cell(self, left: int, top: int, right: int, bottom: int, color: str, radius: int) -> None:
        """Draw one calendar cell, with rounded corners when radius is above 0"""
        if radius <= 0:
            self.calendar_surface.create_rectangle(left, top, right, bottom, fill=color, outline="")
            return
        key = (right - left, bottom - top, color, radius)
        if key not in self.calendar_cell_pictures:
            shape = render_rounded_box(right - left, bottom - top, radius, color, color, COLORS["panel"])
            self.calendar_cell_pictures[key] = to_photo_image(shape)
        self.calendar_surface.create_image(left, top, anchor="nw", image=self.calendar_cell_pictures[key])

    def _calendar_side_width(self) -> int:
        """Width of the landscape strip: just enough for its widest line, the longest month name and year"""
        widest = max(
            self.font_two_week.measure("September 0000"),
            self.calendar_view_toggle.width,
            LEGEND_SQUARE_SIZE + 6 + self.font_small.measure("15 min+"),
            STREAK_ICON_SIZE + STREAK_ICON_GAP + self.font_small.measure("000 week streak"),
        )
        return MODULE_MARGIN + widest + SIDE_STRIP_RIGHT_MARGIN

    def _draw_calendar_side(self, title: str, week_streak: int, rest_day_streak: int) -> int:
        """Draw the landscape layout's strip: the module's name, the month or year, the buttons, the legend and
        the streaks, one under another. Return where the strip ends"""
        canvas = self.calendar_surface
        left = MODULE_MARGIN
        canvas.create_text(left, MODULE_TITLE_TOP, anchor="nw", text="Calendar", fill=COLORS["text"], font=self.font_bold)
        top = MODULE_TITLE_TOP + self.font_bold.metrics("linespace") + SIDE_STRIP_GAP
        canvas.create_text(left, top, anchor="nw", text=title, fill=COLORS["text"], font=self.font_two_week)
        top += self.font_two_week.metrics("linespace") + SIDE_STRIP_GAP
        toggle = self.calendar_view_toggle
        previous_button, next_button = self.calendar_side_step_buttons
        # The month/year toggle has a row to itself, above the buttons that step through the months
        toggle.place(left - 1, top)
        top += toggle.height + 4
        previous_button.place(left - 1, top)
        next_button.place(toggle.box[2] - next_button.width, top)
        top += previous_button.height + SIDE_STRIP_GAP
        square_top = top + (self.calendar_line_height - LEGEND_SQUARE_SIZE) // 2
        self._draw_cell(left, square_top, left + LEGEND_SQUARE_SIZE, square_top + LEGEND_SQUARE_SIZE, COLORS["calendar_blue"], LEGEND_SQUARE_RADIUS)
        canvas.create_text(left + LEGEND_SQUARE_SIZE + 6, top + LINE_PADDING, anchor="nw", text="15 min+", fill=COLORS["muted"], font=self.font_small)
        for icon, text in (("week", f"{week_streak} week streak"), ("rest", f"{rest_day_streak} rest days")):
            top += self.calendar_line_height
            canvas.create_image(left, top + (self.calendar_line_height - STREAK_ICON_SIZE) // 2, anchor="nw", image=self.streak_icons[icon])
            canvas.create_text(
                left + STREAK_ICON_SIZE + STREAK_ICON_GAP, top + LINE_PADDING, anchor="nw", text=text, fill=COLORS["muted"], font=self.font_small
            )
        return top + self.calendar_line_height + SIDE_STRIP_GAP

    def _draw_calendar_heading(self, width: int, title: str, week_streak: int, rest_day_streak: int) -> int:
        """Draw the title row and the legend, and return where the days start"""
        canvas = self.calendar_surface
        previous_button, next_button = self.calendar_step_buttons
        toggle = self.calendar_view_toggle
        next_button.place(width - EDGE_PADDING + 2 - next_button.width, 0)
        previous_button.place(next_button.box[0] - 5 - previous_button.width, 0)
        toggle.place(previous_button.box[0] - 4 - toggle.width, 0)
        # The month or year is centred in the space to the left of the buttons
        title_font = self.font_two_week
        canvas.create_text(
            (EDGE_PADDING + toggle.box[0] - title_font.measure(title)) // 2,
            (toggle.height - title_font.metrics("linespace")) // 2,
            anchor="nw",
            text=title,
            fill=COLORS["text"],
            font=title_font,
        )

        top = toggle.height + CALENDAR_ROW_GAP
        text_top = top + LINE_PADDING
        square_top = top + (self.calendar_line_height - LEGEND_SQUARE_SIZE) // 2
        self._draw_cell(
            EDGE_PADDING, square_top, EDGE_PADDING + LEGEND_SQUARE_SIZE, square_top + LEGEND_SQUARE_SIZE, COLORS["calendar_blue"], LEGEND_SQUARE_RADIUS
        )
        canvas.create_text(
            EDGE_PADDING + LEGEND_SQUARE_SIZE + 6, text_top, anchor="nw", text="15 min+", fill=COLORS["muted"], font=self.font_small
        )
        # The two streak counters are laid out from the right edge, each an icon followed by its text
        right = width - EDGE_PADDING + 2
        for icon, text in (("rest", f"{rest_day_streak} rest days"), ("week", f"{week_streak} week streak")):
            text_left = right - 2 - self.font_small.measure(text)
            canvas.create_text(text_left, text_top, anchor="nw", text=text, fill=COLORS["muted"], font=self.font_small)
            icon_left = text_left - STREAK_ICON_GAP - STREAK_ICON_SIZE
            canvas.create_image(
                icon_left, top + (self.calendar_line_height - STREAK_ICON_SIZE) // 2, anchor="nw", image=self.streak_icons[icon]
            )
            right = icon_left - STREAK_COUNTER_GAP
        return top + self.calendar_line_height + CALENDAR_ROW_GAP

    def _draw_month(
        self, top: int, width: int, year: int, month: int, weeks: list[list[int]], totals: dict, ratings: dict, today: date, offset: int = 0
    ) -> int:
        """Draw the weekday names and a cell for each day, and return where the month ends

        In landscape the weekday names go under the days instead of above them, and the cells are sized so that
        six weeks fill the height the modules share; every month uses that size, and a shorter month leaves
        space below its last week
        """
        canvas = self.calendar_surface
        landscape = self._landscape()
        header_height = self.calendar_line_height
        cell_height = self.calendar_landscape_cell_height if landscape else self.calendar_cell_height
        number_inset = LANDSCAPE_DAY_NUMBER_INSET if landscape else CALENDAR_DAY_NUMBER_INSET
        rating_inset = LANDSCAPE_RATING_INSET if landscape else CALENDAR_RATING_INSET
        row_height = cell_height + CALENDAR_CELL_GAP
        # Each column starts a hairline after the one before it; the first and last reach the module's sides
        column_edges = [offset + round(column * (width + CALENDAR_CELL_GAP) / 7) for column in range(8)]

        def weekday_row(row_top: int) -> None:
            # In landscape the names sit on the panel itself, as they do when written in the last week's gaps
            if not landscape:
                canvas.create_rectangle(offset, row_top, offset + width, row_top + header_height, fill=COLORS["background"], outline="")
            for column, weekday in enumerate(DAY_ABBREVIATIONS):
                left, right = column_edges[column], column_edges[column + 1] - CALENDAR_CELL_GAP
                canvas.create_text(
                    (left + right) / 2, row_top + header_height / 2, text=weekday, fill=COLORS["muted"], font=self.font_small
                )

        # In landscape the weekday names always stand along the bottom. A month of six weeks reaches the bottom
        # with its last week, which always has empty places after the last day, so the names go in those;
        # every other month has a row of names at the bottom
        last_week_gaps = [column for column, day in enumerate(weeks[-1]) if day == 0]
        names_in_gaps = landscape and len(weeks) == 6
        if landscape:
            weeks_top = top
            # A month of six weeks always has room for the weekday names in its last week, so six rows of cells
            # are the most a month needs
            cell_height = (self._landscape_module_height() - top + CALENDAR_CELL_GAP) // 6 - CALENDAR_CELL_GAP
            row_tops = [weeks_top + row * (cell_height + CALENDAR_CELL_GAP) for row in range(len(weeks) + 1)]
        else:
            weekday_row(top)
            weeks_top = top + header_height + CALENDAR_HEADER_GAP
            row_tops = [weeks_top + row * row_height for row in range(len(weeks) + 1)]
        for row, week in enumerate(weeks):
            cell_top = row_tops[row]
            cell_bottom = row_tops[row + 1] - CALENDAR_CELL_GAP
            for column, day in enumerate(week):
                left, right = column_edges[column], column_edges[column + 1] - CALENDAR_CELL_GAP
                if day == 0:
                    # The days before the 1st are blacked out; those after the last day are left empty
                    if row == 0:
                        self._draw_cell(left, cell_top, right, cell_bottom, COLORS["calendar_blank"], CALENDAR_CELL_RADIUS)
                    continue
                active = totals.get(day, 0) >= SESSION_MINIMUM_SECONDS
                session_day = date(year, month, day)
                self._draw_cell(
                    left, cell_top, right, cell_bottom, COLORS["calendar_blue"] if active else COLORS["calendar_cell"], CALENDAR_CELL_RADIUS
                )
                center = (left + right) / 2
                day_color = COLORS["calendar_blue"] if session_day == today and not active else COLORS["text"]
                canvas.create_text(
                    center, cell_top + number_inset, anchor="n", text=str(day), fill=day_color, font=self.font_small
                )
                rating = ratings.get(day)
                # A star appears only on days the user has rated; rating is done in the day overview
                if rating is not None:
                    canvas.create_text(
                        center,
                        cell_bottom - rating_inset,
                        anchor="s",
                        text=f"\U00002b50 {rating}",
                        fill=COLORS["gold"],
                        font=CALENDAR_RATING_FONT,
                    )
                # Days still to come cannot be opened
                if session_day <= today:
                    self.calendar_day_boxes.append((left, cell_top, right, cell_bottom, session_day))
        bottom = row_tops[-1] - CALENDAR_CELL_GAP
        if landscape:
            bottom = max(bottom, self._landscape_module_height())
            if names_in_gaps:
                # Centred a weekday row's height up from the bottom, where the row of names stands in other months
                middle = bottom - header_height / 2
                for column in last_week_gaps:
                    left, right = column_edges[column], column_edges[column + 1] - CALENDAR_CELL_GAP
                    canvas.create_text((left + right) / 2, middle, text=DAY_ABBREVIATIONS[column], fill=COLORS["muted"], font=self.font_small)
            else:
                weekday_row(bottom - header_height)
        return bottom

    def _landscape_module_height(self) -> int:
        """Height every block's contents share in landscape: what the tallest of them needs, counting the header
        and checkboxes on top of the anchor panel, so every block ends level with that column"""
        # Modules not built yet, while the window is first put together, count as hidden
        shown = self.module_vars.get("stats")
        stats = getattr(self, "stats_needed_height", 0) if shown is not None and shown.get() else 0
        if not hasattr(self, "module_control_footer"):
            return max(self._graph_needed_height(), stats, self.today_panel_height)
        overhead = self._anchor_overhead()
        # With no anchor panel the header stands alone: its height, less a block's border of a pixel each side
        column = self.today_panel_height + overhead if self._anchor_block() is not None else overhead - MODULE_GAP - 2
        return max(self._graph_needed_height(), stats, self.today_panel_height, column)

    def _match_landscape_heights(self) -> None:
        """Stretch the graph to the shared height, and redraw the calendar's month if that height has changed"""
        height = self._landscape_module_height()
        self.chart.configure(height=height)
        # The program panels stretch to the same height, the one under the header by that much less
        self._stretch_today_panels(height - self.today_panel_height, self._anchor_block(), height - self._anchor_overhead() - self.today_panel_height)
        if height != getattr(self, "landscape_height_drawn", None):
            self.landscape_height_drawn = height
            self.calendar_visual_state = None
            calendar_shown = self.module_vars.get("calendar")
            if calendar_shown is not None and calendar_shown.get():
                self._schedule_calendar_refresh()
            # The stats stretch to the new height too; drawing them comes back here, finding the height unchanged
            stats_shown = self.module_vars.get("stats")
            if stats_shown is not None and stats_shown.get() and getattr(self, "stats_drawn", None) is not None:
                self.stats_drawn = None
                self.root.after_idle(self._draw_stats)

    def _draw_year(self, top: int, width: int, year: int, active_days: tuple[frozenset, ...], today: date, offset: int = 0) -> int:
        """Draw twelve small months, three to a row, and return where the year ends"""
        canvas = self.calendar_surface
        column_edges = [offset + column * width // 3 for column in range(4)]
        day_width, day_height = YEAR_DAY_SIZE
        for index in range(12):
            month = index + 1
            # Each small month is centred in its third of the width
            left = column_edges[index % 3] + (width // 3 - 7 * YEAR_DAY_PITCH[0]) // 2
            month_top = top + (index // 3) * YEAR_MONTH_HEIGHT + 2
            canvas.create_text(left + 1 + (7 * YEAR_DAY_PITCH[0] - 2) // 2, month_top + 7, text=calendar.month_abbr[month], fill=COLORS["text"], font=YEAR_MONTH_FONT)
            for row, week in enumerate(calendar.monthcalendar(year, month)):
                for column, day in enumerate(week):
                    if not day:
                        continue
                    x = left + 1 + column * YEAR_DAY_PITCH[0]
                    y = month_top + 22 + row * YEAR_DAY_PITCH[1]
                    color = COLORS["calendar_blue"] if day in active_days[index] else COLORS["calendar_cell"]
                    self._draw_cell(x, y, x + day_width, y + day_height, color, YEAR_DAY_RADIUS)
                    session_day = date(year, month, day)
                    # As in the month view, days still to come cannot be opened. A pixel of slack
                    # makes the small squares easier to hit and covers the thin gaps between them
                    if session_day <= today:
                        self.calendar_day_boxes.append((x - 1, y - 1, x + day_width + 1, y + day_height + 1, session_day))
        return top + 4 * YEAR_MONTH_HEIGHT

    def _calendar_canvas_resized(self, event: tk.Event) -> None:
        # Only a new width moves anything; the height also changes whenever a short window clips the module
        if event.width != self.calendar_drawn_width:
            self._schedule_calendar_refresh()

    def _calendar_day_at(self, event: tk.Event) -> date | None:
        """Return the day under the pointer, in either view, if that day can be opened"""
        for left, top, right, bottom, session_day in self.calendar_day_boxes:
            if left <= event.x < right and top <= event.y < bottom:
                return session_day
        return None

    def _calendar_day_clicked(self, event: tk.Event) -> None:
        session_day = self._calendar_day_at(event)
        if session_day is not None:
            self._open_day_overview(session_day)

    def _calendar_pointer_moved(self, event: tk.Event) -> None:
        over_button = CONTROL_TAG in self.calendar_canvas.gettags("current")
        self.calendar_canvas.configure(cursor="hand2" if over_button or self._calendar_day_at(event) else "")

    def _open_day_overview(self, session_day: date) -> None:
        dialog = tk.Toplevel(self.root)
        # The date is carried by the title bar alone, such as "Thu, 1 Oct 2026", to keep the window compact
        dialog.title(f"{DAY_ABBREVIATIONS[session_day.weekday()]}, {session_day.day} {session_day.strftime('%b %Y')}")
        dialog.configure(bg=COLORS["background"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self._set_title_bar_colors(dialog)

        # The day holding the all-time record carries a badge; it moves on when a longer session is tracked
        longest = self.store.longest_session()
        if longest is not None and longest[0] == session_day:
            badge = tk.Frame(dialog, bg=COLORS["background"])
            badge.pack(padx=14, pady=(9, 0), anchor="w")
            # Kept on the dialog so the image lives as long as the label showing it
            dialog.award_image = to_photo_image(render_award_badge(AWARD_BADGE_SIZE, COLORS["background"]))
            tk.Label(badge, image=dialog.award_image, bg=COLORS["background"], bd=0, padx=0).pack(side="left", pady=(AWARD_BADGE_DROP, 0))
            tk.Label(
                badge,
                text="Longest session",
                bg=COLORS["background"],
                fg=COLORS["text"],
                font=self.font_bold,
                padx=0,
                bd=0,
            ).pack(side="left", padx=(2, 0))

        breakdown = self.store.day_application_totals(session_day)
        # A total is only worth a line of its own when several programs add up to it; one program's row says it all
        summary = ""
        if not breakdown:
            summary = "No activity recorded"
        elif len(breakdown) > 1:
            summary = f"Total tracked: {format_duration(sum(seconds for _, seconds, _ in breakdown))}"
            starts = [started_at for _, _, started_at in breakdown if started_at]
            if starts:
                # The session began when the first program of the day was picked up
                summary += f" · started {datetime.strptime(min(starts), '%H:%M').strftime('%I:%M %p').lstrip('0')}"
        if summary:
            tk.Label(
                dialog,
                text=summary,
                bg=COLORS["background"],
                fg=COLORS["muted"],
                font=self.font_small,
            ).pack(padx=16, pady=(12, 10), anchor="w")

        if breakdown:
            sessions_panel = tk.Frame(dialog, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
            sessions_panel.pack(padx=16, pady=(0 if summary else 14, 14), fill="x")
            for application, seconds, started_at in breakdown:
                row = tk.Frame(sessions_panel, bg=COLORS["panel"])
                row.pack(fill="x", padx=10, pady=6)
                tk.Label(row, text=application, bg=COLORS["panel"], fg=COLORS["text"], font=self.font_small).pack(side="left")
                detail = format_duration(seconds)
                if started_at:
                    start_time = datetime.strptime(started_at, "%H:%M").strftime("%I:%M %p").lstrip("0")
                    detail += f" · started {start_time}"
                tk.Label(row, text=detail, bg=COLORS["panel"], fg=COLORS["muted"], font=self.font_small).pack(side="right")

        tk.Label(
            dialog,
            text="How productive was this session?",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=self.font_bold,
        ).pack(padx=16, pady=(0, 6), anchor="w")
        scale = tk.Frame(dialog, bg=COLORS["background"])
        scale.pack(padx=14, pady=(0, 12), anchor="w")
        rating_stars: list[tk.Label] = []

        def show_rating() -> None:
            current = self.store.productivity_rating(session_day) or 0
            for value, star in enumerate(rating_stars, start=1):
                filled = value <= current
                star.configure(text="\U00002605" if filled else "\U00002606", fg=COLORS["gold"] if filled else COLORS["muted"])

        def rate(value: int) -> None:
            self._set_productivity_rating(session_day, value)
            show_rating()

        # Ten stars for the ratings 1 to 10; the stars up to the chosen one fill in
        for value in range(1, 11):
            star = tk.Label(
                scale,
                text="\U00002606",
                bg=COLORS["background"],
                fg=COLORS["muted"],
                font=RATING_STAR_FONT,
                padx=0,
                cursor="hand2",
                takefocus=True,
            )
            star.pack(side="left", padx=1)
            star.bind("<Button-1>", lambda _event, selected=value: rate(selected))
            star.bind("<Return>", lambda _event, selected=value: rate(selected))
            star.bind("<space>", lambda _event, selected=value: rate(selected))
            rating_stars.append(star)
        show_rating()
        # There is no Close button; the title bar's X or the Escape key closes the overview
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        dialog.focus_set()

    def _set_productivity_rating(self, session_day: date, rating: int) -> None:
        """Rate a day from 1 to 10; choosing the rating it already has clears it"""
        if self.store.productivity_rating(session_day) == rating:
            self.store.clear_productivity_rating(session_day)
        else:
            self.store.set_productivity_rating(session_day, rating)
        if self.calendar_view == "Month" and session_day.year == self.calendar_month.year and session_day.month == self.calendar_month.month:
            self.calendar_visual_state = None
            self._draw_calendar()
        # The best start time depends on the ratings, so it follows a change straight away
        if self.module_vars["stats"].get():
            self._draw_stats()

    def _schedule_calendar_refresh(self) -> None:
        if self.calendar_refresh_scheduled:
            return
        self.calendar_refresh_scheduled = True
        self.root.after_idle(self._refresh_calendar_if_visible)

    def _refresh_calendar_if_visible(self) -> None:
        self.calendar_refresh_scheduled = False
        if self.view == "Overview" and self.module_vars["calendar"].get():
            self._draw_calendar()

    def _draw_stats(self) -> None:
        lines = self._stat_figure_lines() + self._session_summary_lines()
        width = self._module_canvas_width(self.stats_canvas)
        if (width, lines, self._landscape()) != self.stats_drawn:
            self.stats_drawn = (width, lines, self._landscape())
            self._draw_stat_lines(lines, width)
        self.stats_last_refresh = datetime.now()
        self._refit_if_content_changed()

    def _stats_canvas_resized(self, event: tk.Event) -> None:
        # Text on the right is placed from the right edge, so a new width means drawing again
        if self.stats_drawn is not None and event.width != self.stats_drawn[0] and self.module_vars["stats"].get():
            self._draw_stats()

    def _draw_stat_lines(self, lines: list[StatLine], width: int) -> None:
        canvas = drawing_surface(self.stats_canvas)
        right = width - STATS_MARGIN - 2
        # The notes share one narrow column at the right edge; the values line up just before it
        note_width = max((self._stat_note_font(line).measure(line.note) for line in lines if line.note), default=0)
        value_right = right - (note_width + STAT_NOTE_GAP if note_width else 0)
        y = 0
        for line in lines:
            value_font = self.font_bold if line.value_bold else self.font_small
            row_height = max(self.font_small.metrics("linespace"), value_font.metrics("linespace")) + 2 * LINE_PADDING
            y += line.above
            # Every piece of a row is centred on its middle, so text of different sizes sits on one line
            middle = y + row_height // 2
            if line.label:
                canvas.create_text(STATS_MARGIN + 2, middle, anchor="w", text=line.label, fill=line.label_color, font=self.font_small)
            if line.value:
                canvas.create_text(value_right, middle, anchor="e", text=line.value, fill=line.value_color, font=value_font)
            if line.medal:
                medal_right = value_right - value_font.measure(line.value) - MEDAL_GAP
                canvas.create_image(medal_right, middle, anchor="e", image=self.stat_medals[line.medal])
            if line.note:
                canvas.create_text(right, middle, anchor="e", text=line.note, fill=line.note_color, font=self._stat_note_font(line))
            y += row_height + line.below
        y += STATS_BOTTOM_PADDING
        if self._landscape():
            # As tall as the calendar and graph beside it, less the stats' title row; and if the stats need more
            # height than they have, the other two grow to match
            title_height = self.module_headers["stats"].winfo_reqheight() + 2 * MODULE_TITLE_PADDING
            self.stats_needed_height = y + title_height
            y = max(y, self._landscape_module_height() - title_height)
            self._match_landscape_heights()
        self.stats_canvas.configure(height=max(1, y))
        show_drawing(self.stats_canvas, canvas, width, max(1, y))

    def _stat_note_font(self, line: StatLine) -> tkfont.Font:
        # A rating is drawn like the rating on a calendar day, so the two read as the same thing
        return self.stat_rating_font if line.rating else self.font_small

    def _stat_figure_lines(self) -> list[StatLine]:
        # These figures always run up to today, whichever period the calendar shows
        today = date.today()
        week_seconds = self.store.total_for_range(today - timedelta(days=today.weekday()), today)
        rank = self.store.week_rank(today)
        medal = medal_for_rank(rank)
        lines = [StatLine("This week", format_hours_minutes(week_seconds), value_bold=True, medal=medal, below=0 if medal else 3)]
        if medal:
            lines.append(StatLine("", f"top {rank}% of your weeks", value_color=COLORS["muted"], below=3))
        for days in ROLLING_AVERAGES:
            average_seconds = self.store.rolling_daily_average(days, today)
            change = average_seconds - self.store.rolling_daily_average(days, today - timedelta(days=days))
            lines.append(
                StatLine(
                    f"{days}-day average",
                    f"{format_hours_minutes(average_seconds)}/day",
                    note=format_change(change),
                    note_color=COLORS["active_green"] if round(change / 60) > 0 else COLORS["muted"],
                )
            )
        best_weekday = self.store.best_weekday_average(today)
        if best_weekday is None:
            lines.append(StatLine("Best day", "--"))
        else:
            weekday, weekday_seconds = best_weekday
            lines.append(StatLine("Best day", f"{DAY_ABBREVIATIONS[weekday]} ·{format_hours_minutes(weekday_seconds)}/day"))
        longest = self.store.longest_session()
        if longest is None:
            lines.append(StatLine("Longest session", "--"))
        else:
            record_day, record_seconds = longest
            lines.append(StatLine("Longest session", f"{record_day.day} {record_day.strftime('%b %Y')} · {format_hours_minutes(record_seconds)}"))
        # Shown only once a day has been rated
        best_start = self.store.best_start_time()
        if best_start is not None:
            started_at, rating = best_start
            start_time = datetime.strptime(started_at, "%H:%M").strftime("%I:%M %p").lstrip("0")
            lines.append(StatLine("Best start time", start_time, note=f"\U00002b50 {rating}", note_color=COLORS["gold"], rating=True))
        return lines

    def _session_summary_lines(self) -> list[StatLine]:
        # Unlike the figures above, the sessions counted are those in the period the calendar shows
        year = self.calendar_month.year
        if self.calendar_view == "Year":
            start = date(year, 1, 1)
            end = date(year, 12, 31)
        else:
            start = self.calendar_month
            end = date(year + start.month // 12, start.month % 12 + 1, 1) - timedelta(days=1)

        sessions = self.store.qualifying_sessions(start, end)
        if not sessions:
            return [StatLine(self._no_sessions_text(start, end), above=3)]
        start_minutes = [int(started_at[:2]) * 60 + int(started_at[3:5]) for _, started_at, _ in sessions]
        average_minutes = round(sum(start_minutes) / len(start_minutes))
        average_start = (datetime.min + timedelta(minutes=average_minutes)).strftime("%I:%M %p").lstrip("0")
        period_name = str(year) if self.calendar_view == "Year" else calendar.month_name[start.month]
        count = f"{len(sessions)} session{'' if len(sessions) == 1 else 's'} in {period_name}"
        return [StatLine(count, f"avg start {average_start}", value_color=COLORS["muted"], above=3)]

    def _no_sessions_text(self, start: date, end: date) -> str:
        period_seconds = self.store.total_for_range(start, end)
        if not period_seconds:
            return "No sessions for this period"
        # Time was tracked, but no single day reached the session minimum
        period_name = str(start.year) if self.calendar_view == "Year" else calendar.month_name[start.month]
        return f"{format_hours_minutes(period_seconds)} tracked in {period_name} · no day reached 15m"

    def _shift_calendar_month(self, offset: int) -> None:
        if self.calendar_view == "Year":
            year, month = self.calendar_month.year + offset, self.calendar_month.month
        else:
            month_index = self.calendar_month.year * 12 + self.calendar_month.month - 1 + offset
            year, month = month_index // 12, month_index % 12 + 1
        # Stepping stops at the ends of the range of years the calendar can show
        if not CALENDAR_YEARS[0] <= year <= CALENDAR_YEARS[1]:
            return
        self.calendar_month = date(year, month, 1)
        self._calendar_period_changed()

    def _toggle_calendar_view(self) -> None:
        self.calendar_view = "Year" if self.calendar_view == "Month" else "Month"
        self.calendar_view_toggle.configure(text=self.calendar_view.lower())
        self._calendar_period_changed()

    def _calendar_period_changed(self) -> None:
        self._draw_calendar()
        # Stats cover the period the calendar shows, so they follow it straight away
        if self.module_vars["stats"].get():
            self._draw_stats()
        # The year view is taller than the month view
        self._refit_if_content_changed()
