"""The day overview, opened from a calendar day: the time in each program, and the day's productivity rating"""

from __future__ import annotations

from datetime import date
from typing import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app_config import format_duration
from stat_lines import DAY_ABBREVIATIONS, format_clock
from tracker import ActivityStore

from .app_dialog import AppDialog
from .header import fit_text
from .icons import icon
from .theme import Fonts, color, draw_outline_text, draw_text, line_height, text_width

# Laid out as the Tk dialog was packed, see ui_calendar._open_day_overview. A Tk label kept its text this far from
# its edges, two pixels of border and one of padding, which its height and the rows' spacing still follow
LABEL_INSET = 3
AWARD_BADGE_SIZE = 16
# Pixels the award is nudged down so its middle lines up with the middle of the text beside it
AWARD_BADGE_DROP = 5
STAR_COUNT = 10
# The rating star as the calendar and stats show it: the star emoji drawn as a plain shape, gold up to the rating and
# a dim grey after it
STAR = "\U00002b50"
UNRATED_STAR = "#5c5c5c"


class DayOverview(AppDialog):
    def __init__(
        self, parent: QWidget, fonts: Fonts, store: ActivityStore, session_day: date, on_rated: Callable[[date, int], None]
    ) -> None:
        # The date is carried by the title bar alone, such as "Thu, 1 Oct 2026", to keep the window compact
        super().__init__(parent, f"{DAY_ABBREVIATIONS[session_day.weekday()]}, {session_day.day} {session_day.strftime('%b %Y')}")
        self.fonts = fonts
        self.store = store
        self.session_day = session_day
        self.on_rated = on_rated
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.rating = store.productivity_rating(session_day) or 0
        # The star that Tab has moved to, which Enter or Space chooses, as with the Tk dialog's stars
        self.focused_star: int | None = None
        # The star under the mouse: the stars light up to it, showing the rating a click would give, as on the website
        self.hovered_star: int | None = None
        self._lay_out()

    def _lay_out(self) -> None:
        fonts = self.fonts
        small, bold = line_height(fonts.small), line_height(fonts.bold)
        label_height = small + 2 * LABEL_INSET
        # Each piece is (kind, left, top, ...), in the order drawn
        self.pieces: list[tuple] = []
        widths = []
        top = 0
        longest = self.store.longest_session()
        # The day holding the all-time record carries a badge; it moves on when a longer session is tracked
        if longest is not None and longest[0] == self.session_day:
            top += 9
            image_height = AWARD_BADGE_SIZE + 2
            text_height = bold + 2
            row_height = max(AWARD_BADGE_DROP + image_height, text_height)
            image_top = top + AWARD_BADGE_DROP + (row_height - AWARD_BADGE_DROP - image_height) // 2
            self.pieces.append(("award", 14, image_top + 1))
            text_left = 14 + AWARD_BADGE_SIZE + 2
            # Centred on the row as the Tk label was, which put its text a pixel lower than the arithmetic says
            self.pieces.append(("text", text_left, top + (row_height - text_height) // 2 + 2, "Longest session", "text", fonts.bold))
            widths.append(text_left + text_width(fonts.bold, "Longest session") + 14)
            top += row_height
        breakdown = self.store.day_application_totals(self.session_day)
        # A total is only worth a line of its own when several programs add up to it; one program's row says it all
        summary = ""
        if not breakdown:
            summary = "No activity recorded"
        elif len(breakdown) > 1:
            summary = f"Total tracked: {format_duration(sum(seconds for _, seconds, _ in breakdown))}"
            starts = [started_at for _, _, started_at in breakdown if started_at]
            if starts:
                # The session began when the first program of the day was picked up
                summary += f" · started {format_clock(min(starts))}"
        if summary:
            top += 12
            self.pieces.append(("text", 16 + LABEL_INSET, top + LABEL_INSET, summary, "muted", fonts.small))
            widths.append(2 * 16 + text_width(fonts.small, summary) + 2 * LABEL_INSET)
            top += label_height + 10
        rows = []
        for application, seconds, started_at in breakdown:
            detail = format_duration(seconds)
            if started_at:
                detail += f" · started {format_clock(started_at)}"
            rows.append((application, detail))
            widths.append(2 * 16 + 2 + 2 * 10 + text_width(fonts.small, application) + text_width(fonts.small, detail) + 4 * LABEL_INSET)
        # As wide as PS Focus's window, which it opens over
        width = self.parentWidget().window().width() if self.parentWidget() is not None else max(widths)
        if rows:
            top += 0 if summary else 14
            panel_top = top
            top += 1
            for application, detail in rows:
                top += 6
                left = 16 + 1 + 10 + LABEL_INSET
                right = width - 16 - 1 - 10 - LABEL_INSET
                detail_left = right - text_width(fonts.small, detail)
                # In a window as narrow as PS Focus's, a long program name gives way to its time
                name = fit_text(application, fonts.small, detail_left - 8 - left)
                self.pieces.append(("text", left, top + LABEL_INSET, name, "text", fonts.small))
                self.pieces.append(("text", detail_left, top + LABEL_INSET, detail, "muted", fonts.small))
                top += label_height + 6
            top += 1
            self.panel = (16, panel_top, width - 32, top - panel_top)
            top += 14
        else:
            self.panel = None
        self.pieces.append(("text", 16 + LABEL_INSET, top + LABEL_INSET, "How productive was this session?", "text", fonts.bold))
        top += bold + 2 * LABEL_INSET + 6
        star_width = text_width(fonts.rating_star, STAR) + 4
        star_height = line_height(fonts.rating_star) + 2 * LABEL_INSET
        # Ten stars for the ratings 1 to 10, spread evenly across the window, each in its own area that a click rates by
        step = (width - 2 * 15 - star_width) / (STAR_COUNT - 1)
        self.star_areas = [(round(15 + index * step), top, star_width, star_height) for index in range(STAR_COUNT)]
        top += star_height + 12
        self.setFixedSize(width, top)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        if self.panel is not None:
            left, top, width, height = self.panel
            painter.fillRect(left, top, width, height, color("panel"))
            painter.setPen(color("border"))
            painter.drawRect(left, top, width - 1, height - 1)
        ratio = self.devicePixelRatioF()
        for piece in self.pieces:
            if piece[0] == "award":
                painter.drawImage(QPoint(piece[1], piece[2]), icon("award", AWARD_BADGE_SIZE, color("background").name(), ratio=ratio))
            else:
                _kind, left, top, text, color_name, font = piece
                draw_text(painter, left, top, text, color(color_name), font)
        for value, (left, top, _width, _height) in enumerate(self.star_areas, start=1):
            filled = value <= (self.hovered_star or self.rating)
            draw_outline_text(
                painter, left + 2, top + LABEL_INSET, STAR, color("gold") if filled else QColor(UNRATED_STAR), self.fonts.rating_star,
            )
        painter.end()

    def _star_at(self, point: QPoint) -> int | None:
        return next(
            (value for value, (left, top, width, height) in enumerate(self.star_areas, start=1)
             if left <= point.x() < left + width and top <= point.y() < top + height),
            None,
        )

    def _rate(self, value: int) -> None:
        self.on_rated(self.session_day, value)
        self.rating = self.store.productivity_rating(self.session_day) or 0
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        value = self._star_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and value is not None:
            self._rate(value)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        star = self._star_at(event.position().toPoint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if star is not None else Qt.CursorShape.ArrowCursor)
        self._hover_star(star)

    def leaveEvent(self, _event) -> None:
        self._hover_star(None)

    def _hover_star(self, star: int | None) -> None:
        if star != self.hovered_star:
            self.hovered_star = star
            self.update()

    def focusNextPrevChild(self, forward: bool) -> bool:
        # Tab and Shift+Tab move between the stars rather than out of the dialog
        current = self.focused_star if self.focused_star is not None else (0 if forward else 1)
        self.focused_star = (current + (1 if forward else -1) - 1) % STAR_COUNT + 1
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.focused_star is not None:
            self._rate(self.focused_star)
            return
        # Escape closes the overview, as the title bar's X does; there is no Close button
        super().keyPressEvent(event)
