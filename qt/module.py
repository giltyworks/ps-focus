"""What the graph, calendar and stats modules share: a bordered panel with the module's name at its top, and the
rounded buttons drawn inside them"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from app_config import MODULE_MARGIN, TODAY_PANEL_WIDTH

from .theme import Fonts, color, draw_text, line_height, text_width

# Space above and below a module's name, as in ui_modules.py
MODULE_TITLE_PADDING = 5
# The corners of a rounded button, as widgets.BUTTON_CORNER_RADIUS
BUTTON_CORNER_RADIUS = 6
# The dock icon at the right of a floating module's name row: the square it takes
DOCK_CONTROL_SIZE = 18
# Space between the line under the name strip and the module's contents
STRIP_GAP = 4


def paint_title_strip(painter: QPainter, rect: QRect, hovered: bool, alpha: int = 255, line: bool = True) -> None:
    """The strip a block's name sits on, as a panel's tab bar in Photoshop: a shade lighter than the panel, a touch
    lighter again under the mouse, with a line under it. The whole strip is where the block is taken by"""
    fill = color("border" if hovered else "panel_alt")
    fill.setAlpha(alpha)
    painter.fillRect(rect, fill)
    if line:
        painter.fillRect(rect.left(), rect.bottom() + 1, rect.width(), 1, color("border"))


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
        # The name strip, its line, and a gap before the contents
        self.strip_height = MODULE_TITLE_PADDING + line_height(fonts.bold) + MODULE_TITLE_PADDING
        self.content_top = 1 + self.strip_height + 1 + STRIP_GAP
        # The module paints every pixel itself, so Qt need not clear it first
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.buttons: list[PaintedButton] = []
        # Blue while the module is being dragged into a new place, see block_drag
        self.border_color = "border"
        # Whether it is in a window of its own, see docking; and which of its name and dock icon the mouse is over
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
        """The name on its strip; in landscape's side strip the strip is just around the name, with no line, the
        strip's own rows starting close under it"""
        strip = self.title_rect()
        side = getattr(self, "landscape", False) and not self.floating
        paint_title_strip(painter, strip, self.hovered_control == "title", self.glass_alpha, line=not side)
        draw_text(painter, 1 + MODULE_MARGIN, 1 + MODULE_TITLE_PADDING, self.title, color("text"), self.fonts.bold)

    def docked_width(self) -> int:
        """Width in the window in landscape, where the graph and calendar have their strip beside them"""
        return TODAY_PANEL_WIDTH

    def title_rect(self) -> QRect:
        """Where the module is taken by to put it in a new order or out of the window: its name row, or in landscape,
        where the graph and calendar have their name in the strip beside them, the name itself"""
        if getattr(self, "landscape", False) and not self.floating:
            return QRect(1, 1, 2 * MODULE_MARGIN + text_width(self.fonts.bold, self.title), self.strip_height)
        return QRect(1, 1, self.width() - 2, self.strip_height)

    def dock_rect(self) -> QRect | None:
        """The dock icon, at the right of the name row while the module floats"""
        if not self.floating:
            return None
        top = 1 + MODULE_TITLE_PADDING + (line_height(self.fonts.bold) - DOCK_CONTROL_SIZE) // 2
        return QRect(self.width() - 1 - MODULE_MARGIN - DOCK_CONTROL_SIZE, top, DOCK_CONTROL_SIZE, DOCK_CONTROL_SIZE)

    def control_at(self, point: QPoint) -> str | None:
        dock = self.dock_rect()
        if dock is not None and dock.contains(point):
            return "dock"
        return "title" if self.title_rect().contains(point) else None

    def paint_dock_controls(self, painter: QPainter) -> None:
        """The dock icon of a floating module, two arrows pointing back, as Photoshop's panels have: muted on the name
        strip, brightening under the mouse"""
        dock = self.dock_rect()
        if dock is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color("text" if self.hovered_control == "dock" else "muted"), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        middle = dock.y() + dock.height() / 2
        for tip in (dock.x() + 4.5, dock.x() + 9.5):
            painter.drawPolyline([QPointF(tip + 4, middle - 4), QPointF(tip, middle), QPointF(tip + 4, middle + 4)])
        painter.restore()

    def interactive_at(self, point: QPoint) -> bool:
        """Whether a press here is a click on something, rather than the start of moving the window"""
        return any(button.contains(point) for button in self.buttons) or self.control_at(point) == "dock"

    def update_cursor(self, point: QPoint, clickable: bool = False) -> None:
        """A pointing hand over something to click, an open hand over the name the module is taken by"""
        control = self.hovered_control if self.hover_controls(point) else None
        if clickable or control == "dock":
            shape = Qt.CursorShape.PointingHandCursor
        elif control == "title":
            shape = Qt.CursorShape.OpenHandCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.setCursor(shape)

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
        self.update_cursor(point, any(button.contains(point) for button in self.buttons))
