"""A program's panel: its name, today's time in large figures, and its sessions, hours and status"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app_config import TODAY_PANEL_WIDTH

from .module import DOCK_CONTROL_SIZE, paint_dock_icon, paint_title_strip
from .theme import Fonts, ascent, color, line_height

# The same measurements as the Tk panel, see main.py: space inside the panel above its first row and below its
# last, and at each side of its text; above and below the big figure's digits; between the last two rows
TODAY_PANEL_PADDING = 9
TODAY_PANEL_SIDE_PADDING = 8
TODAY_FIGURE_SPACE = (12, 15)
# The name strip: space below the name inside it, and between its line and the big figure's digits
TODAY_STRIP_PADDING = 7
TODAY_STRIP_GAP = 12
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
        # Its name, which a window of its own takes when it floats, see docking
        self.title = application
        # Whether it is in a window of its own; how solid its background is there, lower when see-through; and which
        # of its name strip and dock icon the mouse is over
        self.floating = False
        self.glass_alpha = 255
        self.hovered_control: str | None = None
        # Blue while the panel is being dragged into a new place, see block_drag
        self.border_color = "border"
        # Extra height in landscape, so the panel is as tall as the modules beside it; its text stays in the middle
        self.stretch = 0
        metric_ascent = ascent(fonts.metric)
        digit_height = round(metric_ascent * 0.66)
        heights = (
            line_height(fonts.two_week),
            digit_height,
            line_height(fonts.small, fonts.counter),
            line_height(fonts.bold, fonts.counter),
        )
        heading_top = 1 + TODAY_PANEL_PADDING
        # The name row stands on a strip, as a module's name does, with a line under it
        self.title_bottom = heading_top + heights[0] + TODAY_STRIP_PADDING
        digits_top = self.title_bottom + 1 + TODAY_STRIP_GAP
        details_top = digits_top + digit_height + TODAY_FIGURE_SPACE[1]
        status_top = details_top + heights[2] + TODAY_ROW_GAP
        tops = (heading_top, digits_top, details_top, status_top)

        def text_top(row: int, font: QFont) -> int:
            if font is fonts.metric:
                return digits_top - (metric_ascent - digit_height)
            # Text of differing sizes sharing a row is centred on it, in whole pixels
            return tops[row] + (heights[row] - line_height(font)) // 2

        self.natural_height = status_top + heights[3] + TODAY_PANEL_PADDING + 1
        # The name strip, which the panel is taken by to put it in a new order or out of the window; it brightens
        # under the mouse
        self.setMouseTracking(True)
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

    def title_rect(self) -> QRect:
        """The strip along the top; in landscape, where the panel is stretched, its rows stay together under it"""
        return QRect(1, 1, TODAY_PANEL_WIDTH - 2, self.title_bottom - 1)

    @property
    def title_hovered(self) -> bool:
        return self.hovered_control == "title"

    def dock_rect(self) -> QRect | None:
        """The dock icon, at the right of the name strip while the panel floats"""
        if not self.floating:
            return None
        left = TODAY_PANEL_WIDTH - 1 - TODAY_PANEL_SIDE_PADDING - DOCK_CONTROL_SIZE
        return QRect(left, 1 + (self.title_bottom - 1 - DOCK_CONTROL_SIZE) // 2, DOCK_CONTROL_SIZE, DOCK_CONTROL_SIZE)

    def control_at(self, point: QPoint) -> str | None:
        dock = self.dock_rect()
        if dock is not None and dock.contains(point):
            return "dock"
        return "title" if self.title_rect().contains(point) else None

    def interactive_at(self, point: QPoint) -> bool:
        return self.control_at(point) == "dock"

    def _hover(self, control: str | None) -> None:
        if control != self.hovered_control:
            self.hovered_control = control
            shape = {"dock": Qt.CursorShape.PointingHandCursor, "title": Qt.CursorShape.OpenHandCursor}.get(control, Qt.CursorShape.ArrowCursor)
            self.setCursor(shape)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._hover(self.control_at(event.position().toPoint()))

    def leaveEvent(self, _event) -> None:
        self._hover(None)

    # What a floating block does, as the modules do

    def set_layout(self, _landscape: bool, _height: int = 0) -> None:
        """In a window of its own it is as tall as its rows, the landscape stretch gone"""
        self.set_stretch(0)

    def docked_width(self) -> int:
        return TODAY_PANEL_WIDTH

    def set_glass(self, alpha: int) -> None:
        """Make the background this solid, from 255 down; its text stays solid"""
        if alpha != self.glass_alpha:
            self.glass_alpha = alpha
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, alpha == 255)
            self.update()

    def set_stretch(self, extra: int) -> None:
        extra = max(0, extra)
        if extra != self.stretch:
            self.stretch = extra
            self.setFixedSize(TODAY_PANEL_WIDTH, self.natural_height + extra)
            self.update()

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
        background = color("panel")
        background.setAlpha(self.glass_alpha)
        painter.fillRect(self.rect(), background)
        paint_title_strip(painter, self.title_rect(), self.title_hovered, self.glass_alpha)
        painter.setPen(color(self.border_color))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        for name, item in self.texts.items():
            painter.setFont(item.font)
            painter.setPen(color("text") if name == "name" and self.title_hovered else item.color)
            metrics = QFontMetrics(item.font)
            width = metrics.horizontalAdvance(item.text)
            x = item.x - width if item.right_aligned else item.x
            if name == "two_week" and self.floating:
                # Floating, the dock icon takes the strip's right end
                x -= DOCK_CONTROL_SIZE + 6
            # The name row keeps to its strip; the rows under it sit in the middle of what is left
            shift = 0 if item.top < self.title_bottom else self.stretch // 2
            painter.drawText(QPoint(x, item.top + shift + ascent(item.font)), item.text)
        dock = self.dock_rect()
        if dock is not None:
            paint_dock_icon(painter, dock, self.hovered_control == "dock")
        painter.end()
