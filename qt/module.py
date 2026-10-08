"""What the graph, calendar and stats modules share: a bordered panel with the module's name at its top, and the
rounded buttons drawn inside them"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from app_config import MODULE_MARGIN, TODAY_PANEL_WIDTH

from .theme import Fonts, color, draw_text, line_height, text_width

# Space above and below a module's name, as in ui_modules.py
MODULE_TITLE_PADDING = 5
# The corners of a rounded button, as widgets.BUTTON_CORNER_RADIUS
BUTTON_CORNER_RADIUS = 6
# The grip a module is dragged out of the window by, and the dock icon beside it while it floats: the square each
# takes at the right of the name row, and the space between them; in landscape the grip follows the name this far on
DOCK_CONTROL_SIZE = 18
DOCK_CONTROL_GAP = 4
GRIP_AFTER_TITLE = 6


def paint_grip(painter: QPainter, rect: QRect, hovered: bool) -> None:
    """Three short diagonal lines, as the Tk version drew its grip: muted under the mouse, otherwise the border's colour"""
    painter.save()
    painter.setPen(color("muted" if hovered else "border"))
    for inset in (0, 4, 8):
        painter.drawLine(rect.x() + 5 + inset, rect.y() + 14, rect.x() + 14, rect.y() + 5 + inset)
    painter.restore()


def draw_rounded_box(painter: QPainter, box: QRectF, radius: float, fill: QColor, outline: QColor, outline_width: int = 1) -> None:
    """A flat rounded rectangle with an outline this many pixels wide"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    if fill.alpha() < 255:
        # See-through, the outline is a ring, so the fill laid over it does not show it through
        inset = outline_width
        outer, inner = QPainterPath(), QPainterPath()
        outer.addRoundedRect(box, radius, radius)
        inner.addRoundedRect(box.adjusted(inset, inset, -inset, -inset), radius - inset, radius - inset)
        if outline != fill:
            painter.fillPath(outer.subtracted(inner), outline)
            painter.fillPath(inner, fill)
        else:
            painter.fillPath(outer, fill)
        painter.restore()
        return
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
        # How solid its fill is, lower on a see-through panel
        self.alpha = 255
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
        fill.setAlpha(self.alpha)
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
        # Whether it is in a window of its own, see docking; and which of its grip and dock icon the mouse is over
        self.floating = False
        self.hovered_control: str | None = None
        # How solid its background is: 255 in the window, lower on a see-through floating panel, its text and
        # figures staying solid
        self.glass_alpha = 255

    def set_content_height(self, height: int) -> None:
        self.setFixedSize(TODAY_PANEL_WIDTH, self.content_top + height + 1)

    def set_glass(self, alpha: int) -> None:
        """Make the background this solid, from 255 down; the module draws itself again"""
        if alpha == self.glass_alpha:
            return
        self.glass_alpha = alpha
        # A see-through module leaves Qt to clear behind it first
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, alpha == 255)
        for button in self.buttons:
            button.alpha = alpha
        self.glass_changed()
        self.update()

    def glass_changed(self) -> None:
        """Forget anything drawn ahead for the old background, to draw it again for the new one"""

    def surface(self, name: str) -> QColor:
        """A background colour, as see-through as the module"""
        result = color(name)
        result.setAlpha(self.glass_alpha)
        return result

    def picture_fill(self) -> QColor:
        """What a picture drawn ahead starts from: the panel, or nothing on a see-through module"""
        return color("panel") if self.glass_alpha == 255 else QColor(0, 0, 0, 0)

    def icon_background(self) -> str:
        return color("panel").name() if self.glass_alpha == 255 else ""

    def paint_frame(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), self.surface("panel"))
        painter.setPen(color(self.border_color))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        self.paint_title(painter)

    def paint_title(self, painter: QPainter) -> None:
        draw_text(painter, 1 + MODULE_MARGIN, 1 + MODULE_TITLE_PADDING, self.title, color("text"), self.fonts.bold)

    def docked_width(self) -> int:
        """Width in the window in landscape, where the graph and calendar have their strip beside them"""
        return TODAY_PANEL_WIDTH

    def grip_rect(self) -> QRect:
        """The grip: at the right of the name row, or in landscape's side strip just after the name"""
        top = 1 + MODULE_TITLE_PADDING + (line_height(self.fonts.bold) - DOCK_CONTROL_SIZE) // 2
        if getattr(self, "landscape", False) and not self.floating:
            left = 1 + MODULE_MARGIN + text_width(self.fonts.bold, self.title) + GRIP_AFTER_TITLE
        else:
            left = self.width() - 1 - MODULE_MARGIN - DOCK_CONTROL_SIZE
        return QRect(left, top, DOCK_CONTROL_SIZE, DOCK_CONTROL_SIZE)

    def dock_rect(self) -> QRect | None:
        """The dock icon, shown left of the grip while the module floats"""
        if not self.floating:
            return None
        return self.grip_rect().translated(-DOCK_CONTROL_SIZE - DOCK_CONTROL_GAP, 0)

    def control_at(self, point: QPoint) -> str | None:
        dock = self.dock_rect()
        if dock is not None and dock.contains(point):
            return "dock"
        return "grip" if self.grip_rect().contains(point) else None

    def paint_dock_controls(self, painter: QPainter) -> None:
        """Three short diagonal lines for the grip; for the dock icon, a window with a rail and an arrow into it, as
        the Tk version drew them. Muted while the mouse is over them, otherwise the border's colour"""
        paint_grip(painter, self.grip_rect(), self.hovered_control == "grip")
        painter.save()
        dock = self.dock_rect()
        if dock is not None:
            painter.setPen(color("muted" if self.hovered_control == "dock" else "border"))
            x, y = dock.x(), dock.y()
            painter.drawRect(x + 2, y + 3, 13, 11)
            painter.drawLine(x + 6, y + 3, x + 6, y + 14)
            painter.drawLine(x + 14, y + 9, x + 8, y + 9)
            painter.drawLine(x + 10, y + 6, x + 7, y + 9)
            painter.drawLine(x + 7, y + 9, x + 10, y + 12)
        painter.restore()

    def interactive_at(self, point: QPoint) -> bool:
        """Whether a press here is a click on something, rather than the start of moving the window"""
        return any(button.contains(point) for button in self.buttons) or self.control_at(point) is not None

    def hover_controls(self, point: QPoint | None) -> bool:
        """Note which control the mouse is over, repainting when that changes; return whether it is over one"""
        control = None if point is None else self.control_at(point)
        if control != self.hovered_control:
            self.hovered_control = control
            self.update()
        return control is not None

    def leaveEvent(self, _event) -> None:
        self.hover_controls(None)

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
        over_button = any(button.contains(point) for button in self.buttons) | self.hover_controls(point)
        self.setCursor(Qt.CursorShape.PointingHandCursor if over_button else Qt.CursorShape.ArrowCursor)
