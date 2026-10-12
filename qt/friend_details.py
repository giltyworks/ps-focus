"""A friend's figures, opened by double-clicking their name strip: a small window of its own, made as the day overview
is: modal, taking the focus as it opens, centred on PS Focus"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QDialog, QWidget

from app_config import resource_path
from windows_startup import set_title_bar_colors_for_handle

from .theme import color, draw_text, line_height, text_width


class FriendDetails(QDialog):
    def __init__(self, parent, fonts, name, details):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle(name)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.fonts = fonts
        self.lines = details.splitlines()
        height = line_height(fonts.normal) + 8
        self.setFixedSize(max(220, max((text_width(fonts.normal, line) for line in self.lines), default=0) + 32), len(self.lines) * height + 24)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Coloured as it shows, not before: asking for the window's handle before it is shown made Windows stop
        # passing PS Focus's small redraws to the screen, so hover and scrolling seemed frozen until a full redraw
        set_title_bar_colors_for_handle(int(self.winId()))

    def show_centred_on(self, window: QWidget) -> None:
        frame = window.frameGeometry()
        x = window.x() + (frame.width() - self.frameGeometry().width()) // 2
        y = window.y() + (frame.height() - self.frameGeometry().height()) // 2
        self.move(max(0, x), max(0, y))
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("panel"))
        for index, line in enumerate(self.lines):
            draw_text(painter, 16, 12 + index * (line_height(self.fonts.normal) + 8), line, color("text"), self.fonts.normal)
        painter.end()
