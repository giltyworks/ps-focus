"""The calendar module: a month of days, blue once a day reaches a session, or a whole year of small squares; with
the week and rest-day streaks above it. A day that has passed opens its overview"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPixmap

from app_config import EDGE_PADDING, LINE_PADDING, MODULE_CANVAS_WIDTH, SESSION_MINIMUM_SECONDS
from stat_lines import DAY_ABBREVIATIONS
from tracker import ActivityStore

from .icons import icon
from .module import ModuleBlock, PaintedButton
from .theme import Fonts, anchored_top_left, color, draw_anchored, draw_outline_text, draw_text, line_height, text_width

# The same measurements as the Tk calendar, see ui_calendar.py. The first and last years it can be stepped to
CALENDAR_YEARS = (1, 9998)
# Above the days: the space under the title row and under the legend, and the legend's blue square
CALENDAR_ROW_GAP = 5
LEGEND_SQUARE_SIZE = 13
LEGEND_SQUARE_RADIUS = 3
# A streak counter's icon, the space between it and its text, and between the two counters
STREAK_ICON_SIZE = 14
STREAK_ICON_GAP = 5
STREAK_COUNTER_GAP = 6
# Month view: the space between one day's cell and the next, and below the weekday names; the cells' corners;
# how far the day number sits from the top of its cell and the rating from the bottom
CALENDAR_CELL_GAP = 3
CALENDAR_HEADER_GAP = 1
CALENDAR_CELL_RADIUS = 6
CALENDAR_DAY_NUMBER_INSET = 4
CALENDAR_RATING_INSET = 4
# Year view: three months to a row, each a block of this height holding squares of this size and spacing
YEAR_MONTH_HEIGHT = 82
YEAR_DAY_SIZE = (13, 8)
YEAR_DAY_PITCH = (15, 9)
YEAR_DAY_RADIUS = 2
# Gaps between the buttons of the title row: before the step buttons, and between them
TOGGLE_GAP = 4
STEP_BUTTON_GAP = 5

# A day that can be opened: its area on the calendar, and the day
DayBox = tuple[int, int, int, int, date]


class CalendarModule(ModuleBlock):
    def __init__(
        self, fonts: Fonts, store: ActivityStore, on_open_day: Callable[[date], None], on_period_changed: Callable[[], None],
        on_height_changed: Callable[[], None],
    ) -> None:
        super().__init__("Calendar", fonts)
        self.store = store
        self.on_open_day = on_open_day
        self.on_period_changed = on_period_changed
        self.on_height_changed = on_height_changed
        self.view = "Month"
        self.month = date.today().replace(day=1)
        self.toggle = PaintedButton("month", self._toggle_view, fonts, 11, 6, width_in_digits=6, text_color="text")
        self.previous_button = PaintedButton("<", lambda: self._step(-1), fonts, 14, 6, text_color="text")
        self.next_button = PaintedButton(">", lambda: self._step(1), fonts, 14, 6, text_color="text")
        self.buttons = [self.toggle, self.previous_button, self.next_button]
        width = MODULE_CANVAS_WIDTH
        # Placed in the module, whose contents start a pixel in, past its border
        self.next_button.place(1 + width - EDGE_PADDING + 2 - self.next_button.width, self.content_top)
        self.previous_button.place(self.next_button.left - STEP_BUTTON_GAP - self.previous_button.width, self.content_top)
        self.toggle.place(self.previous_button.left - TOGGLE_GAP - self.toggle.width, self.content_top)
        small = line_height(fonts.small)
        self.line_height = small + 2 * LINE_PADDING
        self.cell_height = CALENDAR_DAY_NUMBER_INSET + small + line_height(fonts.rating) + CALENDAR_RATING_INSET
        self.drawn_state: tuple | None = None
        self.picture: QPixmap | None = None
        self.day_boxes: list[DayBox] = []
        self.set_content_height(1)

    def _toggle_view(self) -> None:
        self.view = "Year" if self.view == "Month" else "Month"
        self.toggle.text = self.view.lower()
        self._period_changed()

    def _step(self, offset: int) -> None:
        if self.view == "Year":
            year, month = self.month.year + offset, self.month.month
        else:
            month_index = self.month.year * 12 + self.month.month - 1 + offset
            year, month = month_index // 12, month_index % 12 + 1
        # Stepping stops at the ends of the range of years the calendar can show
        if CALENDAR_YEARS[0] <= year <= CALENDAR_YEARS[1]:
            self.month = date(year, month, 1)
            self._period_changed()

    def _period_changed(self) -> None:
        self.refresh()
        # Stats cover the period the calendar shows, so they follow it straight away
        self.on_period_changed()

    def refresh(self, force: bool = False) -> None:
        """Read the days shown again, and draw them when anything has changed since they were last drawn"""
        year, month = self.month.year, self.month.month
        today = date.today()
        streaks = self.store.calendar_streaks()
        if self.view == "Year":
            title = str(year)
            # For each month, the days that reached the session minimum
            days: tuple = tuple(
                frozenset(day for day, seconds in self.store.month_totals(year, index).items() if seconds >= SESSION_MINIMUM_SECONDS)
                for index in range(1, 13)
            )
        else:
            title = f"{calendar.month_name[month]} {year}"
            totals = self.store.month_totals(year, month)
            ratings = self.store.month_ratings(year, month)
            days = tuple(
                (day, totals.get(day, 0) >= SESSION_MINIMUM_SECONDS, ratings.get(day))
                for week in calendar.monthcalendar(year, month) for day in week if day
            )
        state = (self.view, year, month, today, streaks, days)
        if state == self.drawn_state and not force:
            return
        self.drawn_state = state
        self._draw(title, days, today, *streaks)

    def _draw(self, title: str, days: tuple, today: date, week_streak: int, rest_day_streak: int) -> None:
        """Draw everything but the buttons as one picture, which repaints cheaply"""
        width = MODULE_CANVAS_WIDTH
        # The year view is the taller, so the picture is made big enough for either and cut to what was drawn
        height = self.toggle.height + 2 * CALENDAR_ROW_GAP + self.line_height + 4 * YEAR_MONTH_HEIGHT + 7 * (self.cell_height + CALENDAR_CELL_GAP) + self.line_height
        ratio = self.devicePixelRatioF()
        picture = QPixmap(round(width * ratio), round(height * ratio))
        picture.setDevicePixelRatio(ratio)
        picture.fill(color("panel"))
        painter = QPainter(picture)
        self.day_boxes = []
        top = self._draw_heading(painter, width, title, week_streak, rest_day_streak)
        if self.view == "Year":
            bottom = self._draw_year(painter, top, width, days, today)
        else:
            bottom = self._draw_month(painter, top, width, days, today)
        painter.end()
        self.picture = picture.copy(0, 0, round(width * ratio), round(bottom * ratio))
        self.picture.setDevicePixelRatio(ratio)
        old_height = self.height()
        # Only the rows in use are given room, so a six-week month is never cut short
        self.set_content_height(bottom)
        if self.height() != old_height:
            self.on_height_changed()
        self.update()

    @staticmethod
    def _cell(painter: QPainter, left: int, top: int, right: int, bottom: int, fill: QColor, radius: int) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(left, top, right - left, bottom - top), radius, radius)
        painter.restore()

    def _draw_heading(self, painter: QPainter, width: int, title: str, week_streak: int, rest_day_streak: int) -> int:
        """The title row's month or year, the legend and the streaks; return where the days start"""
        fonts, toggle = self.fonts, self.toggle
        # The month or year is centred in the space to the left of the buttons, which are placed in the module
        toggle_left = toggle.left - 1
        draw_text(
            painter, (EDGE_PADDING + toggle_left - text_width(fonts.two_week, title)) // 2,
            (toggle.height - line_height(fonts.two_week)) // 2, title, color("text"), fonts.two_week,
        )
        top = toggle.height + CALENDAR_ROW_GAP
        text_top = top + LINE_PADDING
        square_top = top + (self.line_height - LEGEND_SQUARE_SIZE) // 2
        self._cell(painter, EDGE_PADDING, square_top, EDGE_PADDING + LEGEND_SQUARE_SIZE, square_top + LEGEND_SQUARE_SIZE, color("calendar_blue"), LEGEND_SQUARE_RADIUS)
        muted = color("muted")
        draw_text(painter, EDGE_PADDING + LEGEND_SQUARE_SIZE + 6, text_top, "15 min+", muted, fonts.small)
        # The two streak counters are laid out from the right edge, each an icon followed by its text
        right = width - EDGE_PADDING + 2
        ratio = painter.device().devicePixelRatioF()
        for kind, text in (("moon", f"{rest_day_streak} rest days"), ("flame", f"{week_streak} week streak")):
            text_left = right - 2 - text_width(fonts.small, text)
            draw_text(painter, text_left, text_top, text, muted, fonts.small)
            icon_left = text_left - STREAK_ICON_GAP - STREAK_ICON_SIZE
            painter.drawImage(QPoint(icon_left, top + (self.line_height - STREAK_ICON_SIZE) // 2), icon(kind, STREAK_ICON_SIZE, color("panel").name(), ratio=ratio))
            right = icon_left - STREAK_COUNTER_GAP
        return top + self.line_height + CALENDAR_ROW_GAP

    def _draw_month(self, painter: QPainter, top: int, width: int, days: tuple, today: date) -> int:
        """The weekday names and a cell for each day; return where the month ends"""
        fonts = self.fonts
        year, month = self.month.year, self.month.month
        weeks = calendar.monthcalendar(year, month)
        day_info = {day: (active, rating) for day, active, rating in days}
        header_height = self.line_height
        row_height = self.cell_height + CALENDAR_CELL_GAP
        # Each column starts a hairline after the one before it; the first and last reach the module's sides
        column_edges = [round(column * (width + CALENDAR_CELL_GAP) / 7) for column in range(8)]
        painter.fillRect(0, top, width, header_height, color("background"))
        muted = color("muted")
        for column, weekday in enumerate(DAY_ABBREVIATIONS):
            left, right = column_edges[column], column_edges[column + 1] - CALENDAR_CELL_GAP
            draw_anchored(painter, (left + right) / 2, top + header_height / 2, "center", weekday, muted, fonts.small)
        weeks_top = top + header_height + CALENDAR_HEADER_GAP
        for row, week in enumerate(weeks):
            cell_top = weeks_top + row * row_height
            cell_bottom = cell_top + self.cell_height
            for column, day in enumerate(week):
                left, right = column_edges[column], column_edges[column + 1] - CALENDAR_CELL_GAP
                if day == 0:
                    # The days before the 1st are blacked out; those after the last day are left empty
                    if row == 0:
                        self._cell(painter, left, cell_top, right, cell_bottom, color("calendar_blank"), CALENDAR_CELL_RADIUS)
                    continue
                active, rating = day_info[day]
                session_day = date(year, month, day)
                self._cell(painter, left, cell_top, right, cell_bottom, color("calendar_blue" if active else "calendar_cell"), CALENDAR_CELL_RADIUS)
                center = (left + right) / 2
                day_color = color("calendar_blue" if session_day == today and not active else "text")
                draw_anchored(painter, center, cell_top + CALENDAR_DAY_NUMBER_INSET, "n", str(day), day_color, fonts.small)
                # A star appears only on days the user has rated; rating is done in the day overview
                if rating is not None:
                    text = f"\U00002b50 {rating}"
                    draw_outline_text(painter, *anchored_top_left(center, cell_bottom - CALENDAR_RATING_INSET, "s", text, fonts.rating), text, color("gold"), fonts.rating)
                # Days still to come cannot be opened
                if session_day <= today:
                    self.day_boxes.append((left, cell_top, right, cell_bottom, session_day))
        return weeks_top + len(weeks) * row_height - CALENDAR_CELL_GAP

    def _draw_year(self, painter: QPainter, top: int, width: int, active_days: tuple, today: date) -> int:
        """Twelve small months, three to a row; return where the year ends"""
        year = self.month.year
        column_edges = [column * width // 3 for column in range(4)]
        day_width, day_height = YEAR_DAY_SIZE
        for index in range(12):
            month = index + 1
            # Each small month is centred in its third of the width
            left = column_edges[index % 3] + (width // 3 - 7 * YEAR_DAY_PITCH[0]) // 2
            month_top = top + (index // 3) * YEAR_MONTH_HEIGHT + 2
            draw_anchored(painter, left + 1 + (7 * YEAR_DAY_PITCH[0] - 2) // 2, month_top + 7, "center", calendar.month_abbr[month], color("text"), self.fonts.bold)
            for row, week in enumerate(calendar.monthcalendar(year, month)):
                for column, day in enumerate(week):
                    if not day:
                        continue
                    x = left + 1 + column * YEAR_DAY_PITCH[0]
                    y = month_top + 22 + row * YEAR_DAY_PITCH[1]
                    fill = color("calendar_blue" if day in active_days[index] else "calendar_cell")
                    self._cell(painter, x, y, x + day_width, y + day_height, fill, YEAR_DAY_RADIUS)
                    # As in the month view, days still to come cannot be opened. A pixel of slack makes the small
                    # squares easier to hit and covers the thin gaps between them
                    if date(year, month, day) <= today:
                        self.day_boxes.append((x - 1, y - 1, x + day_width + 1, y + day_height + 1, date(year, month, day)))
        return top + 4 * YEAR_MONTH_HEIGHT

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        self.paint_frame(painter)
        if self.picture is not None:
            painter.drawPixmap(1, self.content_top, self.picture)
        for button in self.buttons:
            button.paint(painter)
        painter.end()

    def _day_at(self, point: QPoint) -> date | None:
        x, y = point.x() - 1, point.y() - self.content_top
        return next((day for left, top, right, bottom, day in self.day_boxes if left <= x < right and top <= y < bottom), None)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            day = self._day_at(event.position().toPoint())
            if day is not None:
                self.on_open_day(day)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over = any(button.contains(point) for button in self.buttons) or self._day_at(point) is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
