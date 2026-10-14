"""A friend's figures, opened by double-clicking their name strip: a small popup over PS Focus, titled with their name,
closed by a click anywhere else, see app_popup"""

from PySide6.QtGui import QPainter

from .app_popup import CLOSE_MARGIN, CLOSE_SIZE, TITLE_HEIGHT, TITLE_LEFT, AppPopup
from .theme import color, draw_text, line_height, text_width


class FriendDetails(AppPopup):
    def __init__(self, parent, fonts, name, details):
        super().__init__(parent, fonts, name)
        self.lines = details.splitlines()
        height = line_height(fonts.normal) + 8
        width = max(
            220,
            max((text_width(fonts.normal, line) for line in self.lines), default=0) + 2 * TITLE_LEFT,
            TITLE_LEFT + text_width(fonts.bold, name) + 6 + CLOSE_SIZE + CLOSE_MARGIN,
        )
        self.setFixedSize(width, TITLE_HEIGHT + len(self.lines) * height + 12)

    def paintEvent(self, event):
        painter = QPainter(self)
        self.paint_frame(painter)
        for index, line in enumerate(self.lines):
            # The figures stand out; when they joined is in grey beneath them
            tone = "muted" if line.startswith("Member since") else "text"
            draw_text(painter, TITLE_LEFT, TITLE_HEIGHT + 4 + index * (line_height(self.fonts.normal) + 8), line, color(tone), self.fonts.normal)
        painter.end()
