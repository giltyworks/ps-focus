"""The dark tip that shows what something under the mouse is: a calendar day's date and time, or what a panel is for.
Drawn by PS Focus itself, as the website's demo draws it, rather than Windows' own tooltip"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from .theme import color, font

# Its corners, the space round its text, the gap to what it explains, and how wide a long tip runs before wrapping
TIP_RADIUS = 6
TIP_PADDING = (9, 6)
TIP_GAP = 6
TIP_WRAP_WIDTH = 230
TIP_FILL = "#151515"
TIP_BORDER = "#2c2c2c"
# A soft shadow under it, this many pixels deep
TIP_SHADOW = 4


class HoverTip(QWidget):
    """A window of its own, so it can stand past the edge of PS Focus; it never takes focus or the mouse"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.font_ = font(9)
        self.text = ""
        self.text_rect = QRect()
        self.owner: QWidget | None = None

    def show_for(self, owner: QWidget, target: QRect, text: str, wrap: bool = False) -> None:
        """Show above `target`, a rectangle in `owner`, or below it when there is no room above; inside the screen"""
        self.owner = owner
        self.text = text
        # Measured as this window will draw it, at its screen's scale
        metrics = QFontMetrics(self.font_, self)
        flags = int(Qt.TextFlag.TextWordWrap) if wrap else 0
        if wrap:
            bounds = metrics.boundingRect(QRect(0, 0, TIP_WRAP_WIDTH - 2 * TIP_PADDING[0], 10_000), flags, text)
        else:
            bounds = QRect(0, 0, metrics.horizontalAdvance(text) + 1, metrics.height())
        width = bounds.width() + 2 * TIP_PADDING[0] + 2
        height = bounds.height() + 2 * TIP_PADDING[1] + 2
        self.text_rect = QRect(1 + TIP_PADDING[0], 1 + TIP_PADDING[1], bounds.width() + 1, bounds.height())
        size = QSize(width + 2 * TIP_SHADOW, height + 2 * TIP_SHADOW)
        # Windows resizes a see-through window that is showing a moment late, so it would show the new text in the
        # old size; hidden first, it shows at its new size straight away
        if self.isVisible() and size != self.size():
            self.hide()
        self.setFixedSize(size)
        top_left = owner.mapToGlobal(target.topLeft())
        screen = (QGuiApplication.screenAt(top_left) or QGuiApplication.primaryScreen()).availableGeometry()
        x = top_left.x() + target.width() // 2 - width // 2
        y = top_left.y() - TIP_GAP - height
        if y < screen.top():
            y = top_left.y() + target.height() + TIP_GAP
        x = max(screen.left(), min(x, screen.right() - width))
        self.move(QPoint(x - TIP_SHADOW, y - TIP_SHADOW))
        self.update()
        self.show()
        self.raise_()

    def hide_for(self, owner: QWidget) -> None:
        """Hide, if it is showing for this widget"""
        if self.owner is owner:
            self.owner = None
            self.hide()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(TIP_SHADOW, TIP_SHADOW, -TIP_SHADOW, -TIP_SHADOW)
        for step in range(TIP_SHADOW, 0, -1):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 18))
            painter.drawRoundedRect(box.adjusted(-step, -step + 2, step, step + 2), TIP_RADIUS + step, TIP_RADIUS + step)
        painter.setBrush(QColor(TIP_FILL))
        painter.setPen(QColor(TIP_BORDER))
        painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), TIP_RADIUS, TIP_RADIUS)
        painter.setFont(self.font_)
        painter.setPen(color("text"))
        painter.drawText(self.text_rect.translated(TIP_SHADOW, TIP_SHADOW), int(Qt.TextFlag.TextWordWrap), self.text)
        painter.end()


def hover_tip(owner: QWidget) -> HoverTip:
    """The tip for this widget's window, made when first needed; it belongs to that window, so goes with it"""
    window = owner.window()
    tip = getattr(window, "hover_tip", None)
    if tip is None:
        tip = window.hover_tip = HoverTip(window)
    return tip
