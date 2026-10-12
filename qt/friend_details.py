"""A friend's figures, opened by double-clicking their name strip: a small window of its own, made as the day overview
is: modal, taking the focus as it opens, centred on PS Focus"""

from PySide6.QtGui import QPainter

from .app_dialog import AppDialog
from .theme import color, draw_text, line_height, text_width


class FriendDetails(AppDialog):
    def __init__(self, parent, fonts, name, details):
        super().__init__(parent, name)
        self.fonts = fonts
        self.lines = details.splitlines()
        height = line_height(fonts.normal) + 8
        self.setFixedSize(max(220, max((text_width(fonts.normal, line) for line in self.lines), default=0) + 32), len(self.lines) * height + 24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("panel"))
        for index, line in enumerate(self.lines):
            # The figures stand out; when they joined is in grey beneath them
            tone = "muted" if line.startswith("Member since") else "text"
            draw_text(painter, 16, 12 + index * (line_height(self.fonts.normal) + 8), line, color(tone), self.fonts.normal)
        painter.end()
