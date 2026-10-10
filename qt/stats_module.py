"""The stats module: rows of figures, labels on the left and values in a column on the right"""

from __future__ import annotations

from datetime import date
from typing import Callable

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPixmap

from app_config import EDGE_PADDING, LINE_PADDING, MODULE_CANVAS_WIDTH
from stat_lines import StatLine, figure_lines, session_summary_lines
from tracker import ActivityStore

from .icons import icon
from .module import ModuleBlock
from .theme import Fonts, anchored_top_left, color, draw_anchored, draw_outline_text, line_height, text_width

# The same measurements as the Tk stats, see ui_calendar.py: the space kept on each side of the lines and under
# the last; the medal and the gap between it and its value; the gap between a value and the column of notes
STATS_MARGIN = EDGE_PADDING - 2
STATS_BOTTOM_PADDING = 5
MEDAL_SIZE = 14
MEDAL_GAP = 4
# The least space between a row's label and its value
STAT_LABEL_GAP = 10
STAT_NOTE_GAP = 8


class StatsModule(ModuleBlock):
    def __init__(self, fonts: Fonts, store: ActivityStore, on_height_changed: Callable[[], None]) -> None:
        super().__init__("Stats", fonts)
        self.store = store
        self.on_height_changed = on_height_changed
        self.drawn_lines: list[StatLine] | None = None
        self.drawn_ratio: float | None = None
        self.picture: QPixmap | None = None
        # Height of the lines, and in landscape the height the modules share, inside the border
        self.lines_height = 1
        self.shared_height = 0
        self.set_content_height(1)

    def landscape_height(self) -> int:
        """Height the stats need in landscape, inside their border, with their name above the lines"""
        return self.content_top - 1 + self.lines_height

    def glass_changed(self) -> None:
        # Drawn again from the lines worked out, in the new background
        if self.drawn_lines:
            self._draw(self.drawn_lines)

    def set_layout(self, landscape: bool, height: int = 0) -> None:
        """In landscape the stats stretch to the height the modules share; in portrait they are as tall as their lines"""
        self.shared_height = height if landscape else 0
        self._fit()

    def _fit(self) -> None:
        old_height = self.height()
        self.set_content_height(max(self.lines_height, self.shared_height - (self.content_top - 1)))
        if self.height() != old_height:
            self.on_height_changed()

    def refresh(self, calendar_view: str, calendar_month: date) -> None:
        """Work the figures out again, for the period the calendar shows, and draw them if they changed"""
        lines = figure_lines(self.store, date.today()) + session_summary_lines(self.store, calendar_view, calendar_month)
        ratio = self.devicePixelRatioF()
        if lines != self.drawn_lines or ratio != self.drawn_ratio:
            self.drawn_lines = lines
            self._draw(lines)
            self.drawn_ratio = ratio

    def _note_font(self, line: StatLine):
        # A rating is drawn like the rating on a calendar day, so the two read as the same thing
        return self.fonts.rating if line.rating else self.fonts.small

    def _draw(self, lines: list[StatLine]) -> None:
        fonts, width = self.fonts, MODULE_CANVAS_WIDTH
        rows = []
        y = 0
        for line in lines:
            value_font = fonts.bold if line.value_bold else fonts.small
            row_height = line_height(fonts.small, value_font) + 2 * LINE_PADDING
            y += line.above
            # Every piece of a row is centred on its middle, so text of different sizes sits on one line
            rows.append((line, value_font, y + row_height // 2))
            y += row_height + line.below
        height = max(1, y + STATS_BOTTOM_PADDING)
        ratio = self.devicePixelRatioF()
        picture = QPixmap(round(width * ratio), round(height * ratio))
        picture.setDevicePixelRatio(ratio)
        picture.fill(self.picture_fill())
        painter = QPainter(picture)
        right = width - STATS_MARGIN - 2
        # The notes share one narrow column at the right edge; the values line up just before it
        note_width = max((text_width(self._note_font(line), line.note) for line in lines if line.note), default=0)
        value_right = right - (note_width + STAT_NOTE_GAP if note_width else 0)
        for line, value_font, middle in rows:
            line_value_right = value_right
            # A row with no note whose label would run into its value, such as a long month's session count, takes
            # the notes' column too
            if line.label and line.value and not line.note:
                label_end = STATS_MARGIN + 2 + text_width(fonts.small, line.label) + STAT_LABEL_GAP
                if label_end > value_right - text_width(value_font, line.value):
                    line_value_right = right
            if line.label:
                draw_anchored(painter, STATS_MARGIN + 2, middle, "w", line.label, QColor(line.label_color), fonts.small)
            if line.value:
                draw_anchored(painter, line_value_right, middle, "e", line.value, QColor(line.value_color), value_font)
            if line.medal:
                medal_right = line_value_right - text_width(value_font, line.value) - MEDAL_GAP
                medal = icon("award", MEDAL_SIZE, self.icon_background(), line.medal, ratio)
                painter.drawImage(QPoint(medal_right - MEDAL_SIZE, middle - MEDAL_SIZE // 2), medal)
            if line.note:
                note_font = self._note_font(line)
                if line.rating:
                    draw_outline_text(painter, *anchored_top_left(right, middle, "e", line.note, note_font), line.note, QColor(line.note_color), note_font)
                else:
                    draw_anchored(painter, right, middle, "e", line.note, QColor(line.note_color), note_font)
        painter.end()
        self.picture = picture
        self.lines_height = height
        self._fit()
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        self.paint_frame(painter)
        if self.picture is not None:
            self.draw_picture(painter, QPoint(1, self.content_top), self.picture)
        self.paint_dock_controls(painter)
        painter.end()
