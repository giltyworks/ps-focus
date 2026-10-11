"""The notice that tells the user someone wants to be friends, with Accept and Decline, shown inside the main window at
its bottom right, over whatever is there, whether or not the friends module is open"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from .header import fit_text
from .module import PaintedButton, paint_hover_box
from .theme import Fonts, color, draw_text, line_height

POPUP_WIDTH = 260
PADDING = 10
BUTTON_GAP = 4
CLOSE_SIZE = 16
# Space from the window's corner, and between notices stacked above one another
WINDOW_MARGIN = 8
STACK_GAP = 6


class RequestPopup(QWidget):
    def __init__(
        self, owner: QWidget, fonts: Fonts, code: str, name: str, on_accept: Callable[[], None], on_decline: Callable[[], None],
    ) -> None:
        # A part of the main window, never a window of its own
        super().__init__(owner)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        # Its place among the notices, counted up from the bottom; kept in the corner as the window changes size
        self.index = 0
        owner.installEventFilter(self)
        self.fonts = fonts
        self.code = code
        self.name = fit_text(name, fonts.bold, POPUP_WIDTH - 2 * PADDING - CLOSE_SIZE)
        self.close_hovered = False
        self.on_closed: Callable[["RequestPopup"], None] = lambda _popup: None
        self.accept_button = PaintedButton("Accept", lambda: self._answer(on_accept), fonts, 10, 3, text_color="active_green", fill="accept_fill", solid=True)
        self.decline_button = PaintedButton("Decline", lambda: self._answer(on_decline), fonts, 10, 3, text_color="red", fill="decline_fill", solid=True)
        self.buttons = [self.accept_button, self.decline_button]
        top = PADDING + line_height(fonts.bold) + line_height(fonts.small) + 8
        self.decline_button.place(POPUP_WIDTH - PADDING - self.decline_button.width, top)
        self.accept_button.place(self.decline_button.left - BUTTON_GAP - self.accept_button.width, top)
        self.setFixedSize(POPUP_WIDTH, top + self.accept_button.height + PADDING)

    def _answer(self, answer: Callable[[], None]) -> None:
        self.close()
        answer()

    def close_rect(self) -> QRectF:
        return QRectF(self.width() - PADDING - CLOSE_SIZE + 4, PADDING - 4, CLOSE_SIZE, CLOSE_SIZE)

    def place(self, index: int) -> None:
        """In the bottom right corner of the main window, above any notices shown before it, in front of the rest"""
        self.index = index
        window = self.parentWidget()
        self.move(window.width() - WINDOW_MARGIN - self.width(), window.height() - WINDOW_MARGIN - (index + 1) * self.height() - index * STACK_GAP)
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.place(self.index)
        return False

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        self.on_closed(self)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("border"))
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), color("panel"))
        draw_text(painter, PADDING, PADDING, self.name, color("text"), self.fonts.bold)
        draw_text(painter, PADDING, PADDING + line_height(self.fonts.bold), "wants to be friends on PS Focus", color("muted"), self.fonts.small)
        for button in self.buttons:
            button.paint(painter)
        # The close cross, which leaves the request in the friends module to answer later
        box = self.close_rect()
        if self.close_hovered:
            paint_hover_box(painter, box, color("border"))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color("muted"), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        inset = 5
        painter.drawLine(box.topLeft() + QPoint(inset, inset), box.bottomRight() - QPoint(inset, inset))
        painter.drawLine(box.topRight() + QPoint(-inset, inset), box.bottomLeft() + QPoint(inset, -inset))
        painter.restore()
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if any([button.press(point) for button in self.buttons]):
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self.close_rect().contains(event.position()):
            self.close()
            return
        if any([button.release(point) for button in self.buttons]):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over_close = self.close_rect().contains(event.position())
        if PaintedButton.update_hover(self.buttons, point) or over_close != self.close_hovered:
            self.close_hovered = over_close
            self.update()
        clickable = over_close or any(button.contains(point) for button in self.buttons)
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, _event) -> None:
        if PaintedButton.update_hover(self.buttons, None) or self.close_hovered:
            self.close_hovered = False
            self.update()
