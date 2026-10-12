"""The transparency slider, opened from its icon beside the module icons: a small popup with the slider in it, the window
behind turning see-through as it moves, so the effect shows while it is chosen"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QApplication, QWidget

from .status_menu import PopupMenu
from .theme import Fonts, color

# The slider: its length, the thickness of its track and the knob's size; and the space around it in the popup, which
# holds only the slider, the icon's tooltip naming it
SLIDER_WIDTH = 80
SLIDER_TRACK = 4
SLIDER_KNOB = 12
PADDING = 6


def paint_slider(painter: QPainter, left: float, top: float, transparency: int) -> None:
    """A track filled in blue up to the knob; fully right is fully solid, leftwards it turns more see-through"""
    middle = top + SLIDER_KNOB / 2
    knob_x = left + SLIDER_KNOB / 2 + (SLIDER_WIDTH - SLIDER_KNOB) * (100 - transparency) / 100
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    track = QRectF(left, middle - SLIDER_TRACK / 2, SLIDER_WIDTH, SLIDER_TRACK)
    painter.setBrush(color("border"))
    painter.drawRoundedRect(track, SLIDER_TRACK / 2, SLIDER_TRACK / 2)
    painter.setBrush(color("calendar_blue"))
    painter.drawRoundedRect(QRectF(track.left(), track.top(), knob_x - track.left(), SLIDER_TRACK), SLIDER_TRACK / 2, SLIDER_TRACK / 2)
    painter.setBrush(color("text"))
    painter.drawEllipse(QPointF(knob_x, middle), SLIDER_KNOB / 2, SLIDER_KNOB / 2)
    painter.restore()


class TransparencyPopup(QWidget):
    """Closed by clicking anywhere else, as a menu is; clicking its icon again while it is open closes it"""

    OPENER = "transparency"

    def __init__(self, parent: QWidget, fonts: Fonts, transparency: Callable[[], int], on_change: Callable[[int, bool], None]) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        # No box: the slider stands on the row beside its icon, over the window's own background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.fonts = fonts
        self.transparency = transparency
        self.on_change = on_change
        self.dragging = False
        self.slider_left = PADDING
        self.slider_top = PADDING
        self.setFixedSize(SLIDER_WIDTH + 2 * PADDING, self.slider_top + SLIDER_KNOB + PADDING)

    def show_at(self, point: QPoint) -> None:
        """Open with its top left here, kept on the screen"""
        screen = (QApplication.screenAt(point) or self.screen()).availableGeometry()
        self.move(max(screen.left(), min(point.x(), screen.right() + 1 - self.width())),
                  max(screen.top(), min(point.y(), screen.bottom() + 1 - self.height())))
        self.show()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        # All but invisible, yet enough for Windows to give the popup the clicks on it: a fully clear pixel lets
        # them through to what is behind
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        paint_slider(painter, self.slider_left, self.slider_top, self.transparency())
        painter.end()

    def _over_slider(self, point: QPoint) -> bool:
        return (self.slider_left - 4 <= point.x() <= self.slider_left + SLIDER_WIDTH + 4
                and self.slider_top - 4 <= point.y() <= self.slider_top + SLIDER_KNOB + 4)

    def _slide_to(self, point: QPoint, done: bool) -> None:
        span = SLIDER_WIDTH - SLIDER_KNOB
        value = 100 - round(max(0, min(span, point.x() - self.slider_left - SLIDER_KNOB / 2)) * 100 / span)
        self.on_change(value, done)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if not self.rect().contains(point):
            PopupMenu.dismissed = (self.OPENER, time.monotonic())
            super().mousePressEvent(event)
        elif event.button() == Qt.MouseButton.LeftButton and self._over_slider(point):
            self.dragging = True
            self._slide_to(point, False)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self.dragging:
            self._slide_to(point, False)
            return
        inside = self.rect().contains(point)
        hand = (inside and self._over_slider(point)) or (not inside and self._icon_under(event.globalPosition().toPoint()))
        self.setCursor(Qt.CursorShape.PointingHandCursor if hand else Qt.CursorShape.ArrowCursor)

    def _icon_under(self, point: QPoint) -> bool:
        """Outside the popup, which has the mouse while open, the hand still shows over something to click"""
        under = QApplication.widgetAt(point)
        interactive = getattr(under, "interactive_at", None)
        return under is not self and interactive is not None and interactive(under.mapFromGlobal(point))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.dragging and event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self._slide_to(event.position().toPoint(), True)

    def closeEvent(self, event) -> None:
        if self.dragging:
            self.dragging = False
            self.on_change(self.transparency(), True)
        super().closeEvent(event)
