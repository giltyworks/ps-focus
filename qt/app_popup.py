"""What the small windows opened from inside PS Focus share, a calendar day's overview and a friend's details: popups,
as the menus are, so a click anywhere else closes them, as Escape and their × do. A popup has no Windows title bar, so
they draw their own title, with Windows' close button at its right as the main window has, and a thin outline to stand
apart from the window under them; Windows 11 is asked to round their corners as it does an ordinary window's. Dragging
the title row moves the popup"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from windows_startup import round_window_corners

from .header import fit_text
from .theme import Fonts, color, draw_anchored
from .title_bar import BUTTON_WIDTH as CLOSE_WIDTH, CLOSE_HOVER

# The title row across the top, the title starting where the content's text does, and the close button at its right,
# as wide as the main window's and as tall as the row
TITLE_HEIGHT = 30
TITLE_LEFT = 19
# Half the length of each stroke of the ×
CLOSE_ARM = 4.5


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
        # Where in the popup a drag of its title row took hold, while one is under way
        self.drag_offset: QPoint | None = None
        # Room kept clear at the right of the title for controls a popup puts in its title row, left of the ×
        self.title_reserve = 0
        # How tall the title row is: the same for every popup but a window that draws a title row of its own
        self.title_height = TITLE_HEIGHT

    def title_control_at(self, _point: QPoint) -> bool:
        """Whether a control of the popup's own is under this point in the title row, which then takes the press and the
        move rather than the drag"""
        return False

    def close_area(self) -> QRect:
        """Windows' close button: in the corner, the whole height of the title row"""
        return QRect(self.width() - CLOSE_WIDTH, 0, CLOSE_WIDTH, self.title_height)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Asked once it shows, not before: a window's handle asked for early can stall its redraws. Only Windows 11 does it
        if QGuiApplication.platformName() == "windows":
            round_window_corners(int(self.winId()))

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
        """The background, the outline, and the title row; the content is drawn after, below the title row"""
        painter.fillRect(self.rect(), color("background"))
        close = self.close_area()
        title = fit_text(self.windowTitle(), self.fonts.bold, close.left() - 6 - TITLE_LEFT - self.title_reserve)
        draw_anchored(painter, TITLE_LEFT, self.title_height / 2, "w", title, color("text"), self.fonts.bold)
        self.paint_close(painter)
        painter.setPen(color("border"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def paint_close(self, painter: QPainter) -> None:
        """The close button, red under the mouse as Windows shows it, with a thin ×"""
        close = self.close_area()
        if self.close_hovered:
            painter.fillRect(close, QColor(CLOSE_HOVER))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color("text"), 1.1))
        middle = QPointF(close.center()) + QPointF(0.5, 0.5)
        painter.drawLine(middle + QPointF(-CLOSE_ARM, -CLOSE_ARM), middle + QPointF(CLOSE_ARM, CLOSE_ARM))
        painter.drawLine(middle + QPointF(-CLOSE_ARM, CLOSE_ARM), middle + QPointF(CLOSE_ARM, -CLOSE_ARM))
        painter.restore()

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
        elif point.y() < self.title_height and not self.title_control_at(point):
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self.content_pressed(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = None
            # Back to the open hand when the pointer is still over the title row, as a block's handle does
            over_title = self.rect().contains(event.position().toPoint()) and event.position().y() < self.title_height
            self.setCursor(Qt.CursorShape.OpenHandCursor if over_title else Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            return
        point = event.position().toPoint()
        over_close = self.close_area().contains(point)
        if over_close != self.close_hovered:
            self.close_hovered = over_close
            self.update()
        if over_close:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif not self.rect().contains(point):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif point.y() < self.title_height and not self.title_control_at(point):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
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
