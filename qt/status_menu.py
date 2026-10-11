"""Small popup menus in the app's look: the one next to the user's name, which sets how they show to friends, and the
one a friend's row opens"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QCursor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QApplication, QWidget

from .theme import Fonts, color, draw_text, line_height, text_width

# The status menu's choices: each status, its name, and a line saying what it does
CHOICES = (
    ("online", "Online", ""),
    ("away", "Away", "Friends see you're away"),
    ("invisible", "Invisible", "Appear offline, but still see your friends"),
    ("offline", "Offline", "Stop sharing with friends"),
)
PADDING_X = 12
PADDING_Y = 5
MIN_WIDTH = 150
# A click that closes a menu, landing on what opened it, closes it only, if it reopens within this many seconds
REOPEN_GUARD_SECONDS = 0.4


class PopupMenu(QWidget):
    """A popup list, closed by choosing or by clicking anywhere else. Each choice is (key, name, note), the note a
    muted line under the name, or empty; the current choice is picked out in a light blue, and a choice whose key starts
    with "danger" in red

    `opener` names what opened the menu, such as the arrow by the user's name. Clicking it again while the menu is
    open closes the menu, rather than closing and reopening it, see opens"""

    # What opened the last menu closed by a click outside it, and when
    dismissed: tuple[object, float] | None = None

    @classmethod
    def opens(cls, opener: object) -> bool:
        """Whether a click on `opener` should open its menu: not when that click has just closed it"""
        dismissed, cls.dismissed = cls.dismissed, None
        return not (opener is not None and dismissed is not None and dismissed[0] == opener and time.monotonic() - dismissed[1] < REOPEN_GUARD_SECONDS)

    def __init__(
        self, parent: QWidget, fonts: Fonts, choices, current: str | None, on_chosen: Callable[[str], None], min_width: int = MIN_WIDTH,
        opener: object = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.fonts = fonts
        self.current = current
        self.on_chosen = on_chosen
        self.opener = opener
        self.hovered: str | None = None
        self.pressed = False
        self.rows: list[tuple[str, str, str, QRect]] = []
        width = min_width
        for _key, name, note in choices:
            width = max(width, text_width(fonts.normal, name) + 2 * PADDING_X, text_width(fonts.small, note) + 2 * PADDING_X)
        y = 1
        for key, name, note in choices:
            height = line_height(fonts.normal) + (line_height(fonts.small) if note else 0) + 2 * PADDING_Y
            self.rows.append((key, name, note, QRect(1, y, width, height)))
            y += height
        self.setFixedSize(width + 2, y + 1)

    def show_at(self, point: QPoint) -> None:
        """Open with its top left here, kept on the screen"""
        screen = self.screen().availableGeometry()
        self.move(min(point.x(), screen.right() - self.width()), min(point.y(), screen.bottom() - self.height()))
        self.show()
        # Over the arrow that opened it, the hand stays
        self.setCursor(self._cursor_outside(QCursor.pos()))

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("border"))
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), color("panel"))
        for key, name, note, area in self.rows:
            if key == self.hovered:
                painter.fillRect(area, color("panel_alt"))
            if key == self.current:
                name_color = color("calendar_blue").lighter(150)
            else:
                name_color = color("red" if key.startswith("danger") else "text")
            draw_text(painter, area.x() + PADDING_X - 1, area.y() + PADDING_Y, name, name_color, self.fonts.normal)
            if note:
                draw_text(painter, area.x() + PADDING_X - 1, area.y() + PADDING_Y + line_height(self.fonts.normal), note, color("muted"), self.fonts.small)
        painter.end()

    def _cursor_outside(self, point: QPoint) -> Qt.CursorShape:
        under = QApplication.widgetAt(point)
        interactive = getattr(under, "interactive_at", None)
        if under is not self and interactive is not None and interactive(under.mapFromGlobal(point)):
            return Qt.CursorShape.PointingHandCursor
        return Qt.CursorShape.ArrowCursor

    def _row_at(self, point: QPoint) -> str | None:
        return next((key for key, _name, _note, area in self.rows if area.contains(point)), None)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if not self.rect().contains(point):
            # The menu has the mouse while open, so outside it, it shows the hand the app would over something to
            # click, such as the arrow that opened it
            self.setCursor(self._cursor_outside(event.globalPosition().toPoint()))
        else:
            self.unsetCursor()
        key = self._row_at(point)
        if key != self.hovered:
            self.hovered = key
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.rect().contains(event.position().toPoint()):
            self.pressed = True
        else:
            PopupMenu.dismissed = (self.opener, time.monotonic())
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        # Only a click made in the menu chooses: letting go of the click that opened it does not
        key = self._row_at(event.position().toPoint())
        if self.pressed and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and key is not None:
            self.close()
            self.on_chosen(key)


class StatusMenu(PopupMenu):
    def __init__(self, parent: QWidget, fonts: Fonts, current: str, on_chosen: Callable[[str], None]) -> None:
        super().__init__(parent, fonts, CHOICES, current, on_chosen, opener="status")
