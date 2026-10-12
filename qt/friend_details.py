"""Friend statistics opened from their name strip, without a hover popup."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog
from windows_startup import set_title_bar_colors_for_handle
from .theme import color, draw_text, line_height, text_width


class FriendDetails(QDialog):
    def __init__(self, parent, fonts, name, details):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(name)
        self.fonts = fonts
        self.lines = details.splitlines()
        height = line_height(fonts.normal)+8
        self.setFixedSize(max(220, max((text_width(fonts.normal, line) for line in self.lines), default=0)+32), len(self.lines)*height+24)
        set_title_bar_colors_for_handle(int(self.winId()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("panel"))
        for index, line in enumerate(self.lines):
            draw_text(painter, 16, 12+index*(line_height(self.fonts.normal)+8), line, color("text"), self.fonts.normal)
        painter.end()
