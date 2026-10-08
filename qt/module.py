"""What the graph, calendar and stats modules share: a bordered panel with the module's name at its top, and the
rounded buttons drawn inside them"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

from app_config import MODULE_MARGIN, TODAY_PANEL_WIDTH

from .theme import Fonts, color, draw_text, line_height, text_width

# Space above and below a module's name, as in ui_modules.py
MODULE_TITLE_PADDING = 5
# The corners of a rounded button, as widgets.BUTTON_CORNER_RADIUS
BUTTON_CORNER_RADIUS = 6


def draw_rounded_box(painter: QPainter, box: QRectF, radius: float, fill: QColor, outline: QColor, outline_width: int = 1) -> None:
    """A flat rounded rectangle with an outline this many pixels wide"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(outline)
    painter.drawRoundedRect(box, radius, radius)
    painter.setBrush(fill)
    inset = outline_width
    painter.drawRoundedRect(box.adjusted(inset, inset, -inset, -inset), radius - inset, radius - inset)
    painter.restore()


class PaintedButton:
    """A rounded button painted by the widget it sits in, as the Tk widgets.CanvasButton: its outline turns white
    while it is pressed or marked as selected. The widget passes its mouse presses and releases on. Its width is
    that of this many digits, or with none given, of its text; its text is muted unless the button is selected. A
    disabled button ignores clicks and shows muted text, as the Tk OutlinedButton"""

    def __init__(
        self,
        text: str,
        command: Callable[[], None],
        fonts: Fonts,
        padx: int,
        pady: int,
        width_in_digits: int = 0,
        text_color: str = "muted",
        fill: str = "panel_alt",
    ) -> None:
        self.text = text
        self.command = command
        self.font = fonts.small
        self.text_color = text_color
        self.fill = fill
        self.enabled = True
        self.width = text_width(self.font, "0" * width_in_digits if width_in_digits else text) + 2 * padx
        self.height = line_height(self.font) + 2 * pady
        self.left = self.top = 0
        self.selected = False
        self.pressed = False

    def place(self, left: int, top: int) -> None:
        self.left, self.top = left, top

    @property
    def right(self) -> int:
        return self.left + self.width

    def contains(self, point: QPoint) -> bool:
        return self.left <= point.x() < self.left + self.width and self.top <= point.y() < self.top + self.height

    def paint(self, painter: QPainter) -> None:
        box = QRectF(self.left, self.top, self.width, self.height)
        fill = color(self.fill)
        draw_rounded_box(painter, box, BUTTON_CORNER_RADIUS, fill, color("text") if self.selected or self.pressed else fill)
        # Centred in whole pixels, as a Tk label centres its text
        draw_text(
            painter,
            self.left + (self.width - text_width(self.font, self.text)) // 2,
            self.top + (self.height - line_height(self.font)) // 2,
            self.text,
            color("text") if self.selected else color(self.text_color if self.enabled else "muted"),
            self.font,
        )

    def press(self, point: QPoint) -> bool:
        self.pressed = self.enabled and self.contains(point)
        return self.pressed

    def release(self, point: QPoint) -> bool:
        """Letting go outside the button cancels the click, as it does for a standard button"""
        was_pressed, self.pressed = self.pressed, False
        if was_pressed and self.enabled and self.contains(point):
            self.command()
        return was_pressed


class ModuleBlock(QWidget):
    """The module's panel: a one-pixel border, and its name in bold above its contents, which start at content_top"""

    def __init__(self, title: str, fonts: Fonts) -> None:
        super().__init__()
        self.title = title
        self.fonts = fonts
        self.content_top = 1 + MODULE_TITLE_PADDING + line_height(fonts.bold) + MODULE_TITLE_PADDING
        # The module paints every pixel itself, so Qt need not clear it first
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.buttons: list[PaintedButton] = []
        # Blue while the module is being dragged into a new place, see block_drag
        self.border_color = "border"

    def set_content_height(self, height: int) -> None:
        self.setFixedSize(TODAY_PANEL_WIDTH, self.content_top + height + 1)

    def paint_frame(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), color("panel"))
        painter.setPen(color(self.border_color))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        self.paint_title(painter)

    def paint_title(self, painter: QPainter) -> None:
        draw_text(painter, 1 + MODULE_MARGIN, 1 + MODULE_TITLE_PADDING, self.title, color("text"), self.fonts.bold)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and any([button.press(point) for button in self.buttons]):
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and any([button.release(point) for button in self.buttons]):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over_button = any(button.contains(point) for button in self.buttons)
        self.setCursor(Qt.CursorShape.PointingHandCursor if over_button else Qt.CursorShape.ArrowCursor)
