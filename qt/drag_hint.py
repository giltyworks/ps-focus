"""The tip shown once, the first time PS Focus opens with this way of dragging: a bubble under the first block's title
saying that blocks are taken by their title. It goes for good once dismissed, or once a title has been dragged"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from app_config import TODAY_PANEL_WIDTH

from .module import PaintedButton
from .settings_page import wrap
from .theme import Fonts, color, draw_text, line_height

HINT_TEXT = (
    "Drag a panel by its title to rearrange it, or pull a module's title out of the window to give it a window of "
    "its own. Drag anywhere else to move PS Focus."
)
# The bubble's inner padding, the pointer at its top, its corners, and how far in from the window's sides it sits
PADDING = 10
ARROW = 7
RADIUS = 6
SIDE_INSET = 12


class DragHint(QWidget):
    def __init__(self, window: QWidget, fonts: Fonts, on_dismissed: Callable[[], None]) -> None:
        super().__init__(window)
        self.fonts = fonts
        self.on_dismissed = on_dismissed
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMouseTracking(True)
        width = TODAY_PANEL_WIDTH - 2 * SIDE_INSET
        self.lines = wrap(HINT_TEXT, fonts.small, width - 2 * PADDING)
        self.button = PaintedButton("Got it", self.dismiss, fonts, 14, 4, text_color="accent", fill="accent_dark")
        text_height = len(self.lines) * line_height(fonts.small)
        self.button.place(width - PADDING - self.button.width, ARROW + PADDING + text_height + 8)
        self.setFixedSize(width, self.button.top + self.button.height + PADDING)
        # Where along the top the pointer is, under the title it points at
        self.arrow_x = 40
        self.hide()

    def point_at(self, title_bottom_left: QPoint) -> None:
        """Stand just under a title, given in the window's coordinates, its pointer under the title's start"""
        left = max(0, min(title_bottom_left.x(), self.parentWidget().width() - self.width()))
        self.move(left, title_bottom_left.y())
        self.arrow_x = max(RADIUS + ARROW, min(title_bottom_left.x() - left + 30, self.width() - RADIUS - ARROW))
        self.raise_()
        self.update()

    def dismiss(self) -> None:
        if self.isVisible():
            self.hide()
            self.on_dismissed()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(0.5, ARROW + 0.5, self.width() - 1, self.height() - ARROW - 1)
        path = QPainterPath()
        path.addRoundedRect(body, RADIUS, RADIUS)
        arrow = QPainterPath()
        arrow.moveTo(QPointF(self.arrow_x - ARROW, ARROW + 1))
        arrow.lineTo(QPointF(self.arrow_x, 0.5))
        arrow.lineTo(QPointF(self.arrow_x + ARROW, ARROW + 1))
        arrow.closeSubpath()
        path = path.united(arrow)
        painter.fillPath(path, color("panel_alt"))
        painter.setPen(QPen(color("calendar_blue"), 1))
        painter.drawPath(path)
        top = ARROW + PADDING
        for index, line in enumerate(self.lines):
            draw_text(painter, PADDING, top + index * line_height(self.fonts.small), line, color("text"), self.fonts.small)
        self.button.paint(painter)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.button.press(event.position().toPoint()):
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.button.release(event.position().toPoint()):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        over = self.button.contains(event.position().toPoint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)

    def interactive_at(self, _point: QPoint) -> bool:
        return True
