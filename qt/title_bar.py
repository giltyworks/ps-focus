"""The main window's own title bar, in place of Windows', so its background can turn see-through like a floating
panel's; and the grips its edges are resized by"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from app_config import APP_NAME, EDGE_PADDING

from .module import paint_hover_box
from .theme import Fonts, color, draw_text, halo_strength, line_height

TITLE_BAR_HEIGHT = 28
BUTTON_WIDTH = 36
ICON_SIZE = 16
# The close button's box under the mouse, as Windows shows it
CLOSE_HOVER = "#c42b1c"
# How thick the grip along a resizable edge is
GRIP_SIZE = 5


class TitleBar(QWidget):
    """The icon and name at the left, minimise and close at the right; dragged anywhere else, it moves the window, see
    block_drag; a right click opens a menu with Always on top. What the buttons do is set by the app"""

    def __init__(self, parent: QWidget, fonts: Fonts) -> None:
        super().__init__(parent)
        self.fonts = fonts
        self.setMouseTracking(True)
        self.glass_alpha = 255
        self.hovered: str | None = None
        self.pressed: str | None = None
        self.on_minimize: Callable[[], None] = lambda: None
        self.on_close: Callable[[], None] = lambda: None
        # Given where to open the menu, in screen coordinates
        self.on_menu: Callable[[QPoint], None] = lambda _point: None
        self.setFixedHeight(TITLE_BAR_HEIGHT)

    def set_glass(self, alpha: int) -> None:
        if alpha != self.glass_alpha:
            self.glass_alpha = alpha
            self.update()

    def button_rects(self) -> dict[str, QRect]:
        close = QRect(self.width() - BUTTON_WIDTH, 0, BUTTON_WIDTH, self.height())
        return {"close": close, "minimize": close.translated(-BUTTON_WIDTH, 0)}

    def _button_at(self, point: QPoint) -> str | None:
        return next((name for name, rect in self.button_rects().items() if rect.contains(point)), None)

    def interactive_at(self, point: QPoint) -> bool:
        """Whether a press here is a click on a button, rather than the start of moving the window"""
        return self._button_at(point) is not None

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.halo = halo_strength(self.glass_alpha)
        background = color("background")
        background.setAlpha(self.glass_alpha)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), background)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        icon = self.window().windowIcon().pixmap(ICON_SIZE, ICON_SIZE)
        painter.drawPixmap(EDGE_PADDING, (self.height() - ICON_SIZE) // 2, icon)
        draw_text(painter, EDGE_PADDING + ICON_SIZE + 8, (self.height() - line_height(self.fonts.small)) // 2, APP_NAME, color("text"), self.fonts.small)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for name, rect in self.button_rects().items():
            if self.hovered == name:
                if name == "close":
                    fill = QColor(CLOSE_HOVER)
                    if self.pressed == name:
                        fill = fill.darker(115)
                    painter.fillRect(rect, fill)
                else:
                    paint_hover_box(painter, QRectF(rect).adjusted(4, 4, -4, -4), color("border").lighter(140 if self.pressed == name else 100))
            pen = QPen(color("text"), 1.1)
            painter.setPen(pen)
            middle = QPointF(rect.center()) + QPointF(0.5, 0.5)
            if name == "minimize":
                painter.drawLine(middle + QPointF(-5, 0), middle + QPointF(5, 0))
            else:
                painter.drawLine(middle + QPointF(-4.5, -4.5), middle + QPointF(4.5, 4.5))
                painter.drawLine(middle + QPointF(4.5, -4.5), middle + QPointF(-4.5, 4.5))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.RightButton:
            self.on_menu(event.globalPosition().toPoint() + QPoint(2, 2))
        elif event.button() == Qt.MouseButton.LeftButton:
            self.pressed = self._button_at(point)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        pressed, self.pressed = self.pressed, None
        self.update()
        # Letting go outside the button cancels the click, as for a standard button
        if event.button() == Qt.MouseButton.LeftButton and pressed is not None and pressed == self._button_at(event.position().toPoint()):
            (self.on_close if pressed == "close" else self.on_minimize)()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        button = self._button_at(event.position().toPoint())
        if button != self.hovered:
            self.hovered = button
            self.setToolTip({"close": "Close to the tray", "minimize": "Minimise"}.get(button, ""))
            self.update()

    def leaveEvent(self, _event) -> None:
        if self.hovered is not None:
            self.hovered = None
            self.update()


class EdgeGrip(QWidget):
    """A thin strip along a resizable edge of the window, the bottom in portrait or the right in landscape, which
    resizes it as Windows' own frame did: the system does the resizing, within the window's least and greatest size"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.edge = Qt.Edge.BottomEdge
        self.hide()

    def set_edge(self, edge: Qt.Edge) -> None:
        self.edge = edge
        self.setCursor(Qt.CursorShape.SizeVerCursor if edge == Qt.Edge.BottomEdge else Qt.CursorShape.SizeHorCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemResize(self.edge)
