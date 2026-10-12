"""A friend's figures, opened by double-clicking their name strip: a small popup under the name, as the menus are, closed
by any click. Not a window of its own: a dialog took the focus from PS Focus mid-click, which could leave it holding the
mouse"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .theme import color, draw_text, line_height, text_width

PADDING_X = 11
PADDING_Y = 7
LINE_GAP = 2


class FriendDetails(QWidget):
    def __init__(self, parent, fonts, name, details):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(name)
        self.fonts = fonts
        self.name = name
        self.lines = details.splitlines()
        width = max([text_width(fonts.bold, name)] + [text_width(fonts.small, line) for line in self.lines])
        height = line_height(fonts.bold) + len(self.lines) * (line_height(fonts.small) + LINE_GAP)
        self.setFixedSize(width + 2 * PADDING_X, height + 2 * PADDING_Y)

    def show_at(self, point: QPoint) -> None:
        """Open with its top left here, kept on the screen"""
        screen = (QApplication.screenAt(point) or self.screen()).availableGeometry()
        self.move(max(screen.left(), min(point.x(), screen.right() + 1 - self.width())),
                  max(screen.top(), min(point.y(), screen.bottom() + 1 - self.height())))
        self.show()

    def mousePressEvent(self, event):
        # Any click closes it: inside, here; outside, Qt closes a popup by itself
        if self.rect().contains(event.position().toPoint()):
            self.close()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("border"))
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), color("panel"))
        draw_text(painter, PADDING_X, PADDING_Y, self.name, color("text"), self.fonts.bold)
        y = PADDING_Y + line_height(self.fonts.bold)
        for line in self.lines:
            y += LINE_GAP
            draw_text(painter, PADDING_X, y, line, color("muted"), self.fonts.small)
            y += line_height(self.fonts.small)
        painter.end()
