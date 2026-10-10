"""The menu next to the user's name, which sets how they show to friends: online, away, invisible or offline"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from .theme import Fonts, color, draw_text, line_height, text_width

# Each choice: its status, its name, and a line saying what it does
CHOICES = (
    ("online", "Online", ""),
    ("away", "Away", "Friends see you're away"),
    ("invisible", "Invisible", "Appear offline, but still see your friends"),
    ("offline", "Offline", "Stop sharing with friends"),
)
PADDING_X = 12
PADDING_Y = 5
MIN_WIDTH = 150


class StatusMenu(QWidget):
    """A popup list, closed by choosing or by clicking anywhere else"""

    def __init__(self, parent: QWidget, fonts: Fonts, current: str, on_chosen: Callable[[str], None]) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.fonts = fonts
        self.current = current
        self.on_chosen = on_chosen
        self.hovered: str | None = None
        self.rows: list[tuple[str, str, str, QRect]] = []
        width = MIN_WIDTH
        for _status, name, note in CHOICES:
            width = max(width, text_width(fonts.normal, name) + 2 * PADDING_X, text_width(fonts.small, note) + 2 * PADDING_X)
        y = 1
        for status, name, note in CHOICES:
            height = line_height(fonts.normal) + (line_height(fonts.small) if note else 0) + 2 * PADDING_Y
            self.rows.append((status, name, note, QRect(1, y, width, height)))
            y += height
        self.setFixedSize(width + 2, y + 1)

    def show_at(self, point: QPoint) -> None:
        """Open with its top left here, kept on the screen"""
        screen = self.screen().availableGeometry()
        self.move(min(point.x(), screen.right() - self.width()), min(point.y(), screen.bottom() - self.height()))
        self.show()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("border"))
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), color("panel"))
        for status, name, note, area in self.rows:
            if status == self.hovered:
                painter.fillRect(area, color("panel_alt"))
            # The status chosen now is picked out in a light blue
            name_color = color("calendar_blue").lighter(150) if status == self.current else color("text")
            draw_text(painter, area.x() + PADDING_X - 1, area.y() + PADDING_Y, name, name_color, self.fonts.normal)
            if note:
                draw_text(painter, area.x() + PADDING_X - 1, area.y() + PADDING_Y + line_height(self.fonts.normal), note, color("muted"), self.fonts.small)
        painter.end()

    def _row_at(self, point: QPoint) -> str | None:
        return next((status for status, _name, _note, area in self.rows if area.contains(point)), None)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        status = self._row_at(event.position().toPoint())
        if status != self.hovered:
            self.hovered = status
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        status = self._row_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and status is not None:
            self.close()
            self.on_chosen(status)
