"""What the small windows opened from inside PS Focus share, a calendar day's overview and a friend's details: popups,
as the menus are, so a click anywhere else closes them, as Escape and their × do. A popup has no Windows title bar, so
they draw their own title, with the × beside it, and a thin outline to stand apart from the window under them"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .header import fit_text
from .module import paint_hover_box
from .theme import Fonts, color, draw_anchored

# The title row across the top, the title starting where the content's text does, and the × at its right
TITLE_HEIGHT = 30
TITLE_LEFT = 19
CLOSE_SIZE = 22
CLOSE_MARGIN = 4
# Half the length of each stroke of the ×
CLOSE_ARM = 4


class AppPopup(QWidget):
    def __init__(self, parent: QWidget | None, fonts: Fonts, title: str) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setWindowTitle(title)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.fonts = fonts
        self.close_hovered = False

    def close_area(self) -> QRect:
        return QRect(self.width() - CLOSE_SIZE - CLOSE_MARGIN, (TITLE_HEIGHT - CLOSE_SIZE) // 2, CLOSE_SIZE, CLOSE_SIZE)

    def show_centred_on(self, window: QWidget) -> None:
        """Open over the middle of the window, kept on its screen, which may lie left of or above the main screen"""
        frame = window.frameGeometry()
        left = frame.x() + (frame.width() - self.width()) // 2
        top = frame.y() + (frame.height() - self.height()) // 2
        screen = (window.screen() or self.screen()).availableGeometry()
        left = max(screen.left(), min(left, screen.right() + 1 - self.width()))
        top = max(screen.top(), min(top, screen.bottom() + 1 - self.height()))
        self.move(QPoint(left, top))
        self.show()
        self.setFocus()

    def paint_frame(self, painter: QPainter) -> None:
        """The background, the outline, and the title row; the content is drawn after, below TITLE_HEIGHT"""
        painter.fillRect(self.rect(), color("background"))
        close = self.close_area()
        title = fit_text(self.windowTitle(), self.fonts.bold, close.left() - 6 - TITLE_LEFT)
        draw_anchored(painter, TITLE_LEFT, TITLE_HEIGHT / 2, "w", title, color("text"), self.fonts.bold)
        if self.close_hovered:
            paint_hover_box(painter, QRectF(close), color("border"))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color("text" if self.close_hovered else "muted"), 1.5))
        middle = QPointF(close.center()) + QPointF(0.5, 0.5)
        painter.drawLine(middle + QPointF(-CLOSE_ARM, -CLOSE_ARM), middle + QPointF(CLOSE_ARM, CLOSE_ARM))
        painter.drawLine(middle + QPointF(-CLOSE_ARM, CLOSE_ARM), middle + QPointF(CLOSE_ARM, -CLOSE_ARM))
        painter.restore()
        painter.setPen(color("border"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # Subclasses take the presses and moves on their content here, rather than overriding the events themselves
    def content_pressed(self, event: QMouseEvent) -> None:
        pass

    def content_moved(self, event: QMouseEvent) -> None:
        pass

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if not self.rect().contains(point):
            # A click anywhere else closes it, as it does a menu
            super().mousePressEvent(event)
        elif self.close_area().contains(point):
            if event.button() == Qt.MouseButton.LeftButton:
                self.close()
        else:
            self.content_pressed(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over_close = self.close_area().contains(point)
        if over_close != self.close_hovered:
            self.close_hovered = over_close
            self.update()
        if over_close:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif not self.rect().contains(point):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.content_moved(event)

    def leaveEvent(self, _event) -> None:
        if self.close_hovered:
            self.close_hovered = False
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
