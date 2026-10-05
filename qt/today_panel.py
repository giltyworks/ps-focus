"""A program's panel: its name, today's time in large figures, and its sessions, hours and status"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app_config import TODAY_PANEL_WIDTH

from .theme import Fonts, ascent, color, line_height

# The same measurements as the Tk panel, see main.py: space inside the panel above its first row and below its
# last, and at each side of its text; above and below the big figure's digits; between the last two rows
TODAY_PANEL_PADDING = 9
TODAY_PANEL_SIDE_PADDING = 8
TODAY_FIGURE_SPACE = (12, 15)
TODAY_ROW_GAP = 7


@dataclass
class PanelText:
    # Left edge of the text, or its right edge when right_aligned; top is where the font's line starts
    x: int
    top: int
    right_aligned: bool
    text: str
    color: QColor
    font: QFont


class TodayPanel(QWidget):
    """Four rows: name and two-week total, today's time, sessions and hours, status and last session

    The big figure's font reserves empty space above its digits and below its baseline. The rows around it are set
    against the digits themselves, not that space, which is what keeps the panel short
    """

    def __init__(self, application: str, fonts: Fonts, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.application = application
        # Blue while the panel is being dragged into a new place, see block_drag
        self.border_color = "border"
        metric_ascent = ascent(fonts.metric)
        digit_height = round(metric_ascent * 0.66)
        heights = (
            line_height(fonts.two_week),
            digit_height,
            line_height(fonts.small, fonts.counter),
            line_height(fonts.bold, fonts.counter),
        )
        heading_top = 1 + TODAY_PANEL_PADDING
        digits_top = heading_top + heights[0] + TODAY_FIGURE_SPACE[0]
        details_top = digits_top + digit_height + TODAY_FIGURE_SPACE[1]
        status_top = details_top + heights[2] + TODAY_ROW_GAP
        tops = (heading_top, digits_top, details_top, status_top)

        def text_top(row: int, font: QFont) -> int:
            if font is fonts.metric:
                return digits_top - (metric_ascent - digit_height)
            # Text of differing sizes sharing a row is centred on it, in whole pixels
            return tops[row] + (heights[row] - line_height(font)) // 2

        self.natural_height = status_top + heights[3] + TODAY_PANEL_PADDING + 1
        self.setFixedSize(TODAY_PANEL_WIDTH, self.natural_height)
        # The panel paints every pixel itself, so Qt need not clear it first
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        left, right = 1 + TODAY_PANEL_SIDE_PADDING, TODAY_PANEL_WIDTH - 1 - TODAY_PANEL_SIDE_PADDING
        muted = color("muted")

        def text(row: int, right_aligned: bool, content: str, text_color: QColor, font: QFont) -> PanelText:
            return PanelText(right if right_aligned else left, text_top(row, font), right_aligned, content, text_color, font)

        self.texts = {
            "name": text(0, False, application, muted, fonts.two_week),
            "two_week": text(0, True, "0.0 hours past 2 weeks", muted, fonts.two_week),
            "total": text(1, False, "0s", color("text"), fonts.metric),
            "sessions": text(2, False, "0 SESSIONS", muted, fonts.small),
            "record_hours": text(2, True, "0.0 hrs on record", muted, fonts.counter),
            "status": text(3, False, "NOT ACTIVE", muted, fonts.bold),
            "last_session": text(3, True, "last session on --", muted, fonts.counter),
        }

    def set_text(self, name: str, text: str, text_color: str | None = None) -> None:
        """Change one line of text, repainting only when something changed; most seconds change one line or none"""
        item = self.texts[name]
        new_color = color(text_color) if text_color else item.color
        if item.text == text and item.color == new_color:
            return
        item.text, item.color = text, new_color
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("panel"))
        painter.setPen(color(self.border_color))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        for item in self.texts.values():
            painter.setFont(item.font)
            painter.setPen(item.color)
            metrics = QFontMetrics(item.font)
            width = metrics.horizontalAdvance(item.text)
            x = item.x - width if item.right_aligned else item.x
            painter.drawText(QPoint(x, item.top + ascent(item.font)), item.text)
        painter.end()
