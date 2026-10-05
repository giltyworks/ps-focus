"""The header row, with the level, the account and today's progress dot, and the settings button; and the row of
module checkboxes under it. Both are painted, with areas that respond to clicks, as their Tk versions were drawn"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app_config import EDGE_PADDING, LEVEL_BADGE_SIZE, TODAY_PANEL_WIDTH

from .badge import render_level_badge
from .theme import Fonts, ascent, color, line_height

# The same measurements as the Tk header, see ui_header.py: the header is as wide as the panels; the square the
# level badge and the settings button each take, and the least height of the row; the space holding the progress
# dot; from the edge of the account's area to its text; and the least space between the account and its neighbours
HEADER_WIDTH = TODAY_PANEL_WIDTH
HEADER_ICON_SIZE = 26
PROGRESS_DOT_SPACE = 18
ACCOUNT_TEXT_INSET_X = 5
ACCOUNT_TEXT_INSET_Y = 4
HEADER_GROUP_GAP = 6
# How far a Tk label kept its text from its own edge, which the word Level is still placed by
LABEL_TEXT_INSET = 3
# Where the settings button starts, which leaves its three dots the usual distance from the header's edge
SETTINGS_BUTTON_LEFT = HEADER_WIDTH - HEADER_ICON_SIZE - 2
# The module checkboxes, as in ui_modules.py: the gap between a name and its checkbox, the square the checkbox is
# centred in, and the space between one module's control and the next; and the rounded square of a checkbox
MODULE_LABEL_GAP = 6
MODULE_CHECKBOX_SIZE = 18
MODULE_CONTROL_GAP = 8
CHECKBOX_BOX_SIZE = 14
CHECKBOX_CORNER_RADIUS = 4
MODULE_LABELS = (("graph", "Graph"), ("calendar", "Calendar"), ("stats", "Stats"))

Area = tuple[int, int, int, int]
NO_AREA: Area = (0, 0, 0, 0)


def _inside(area: Area, point: QPoint) -> bool:
    left, top, right, bottom = area
    return left <= point.x() < right and top <= point.y() < bottom


def fit_text(text: str, font: QFont, width: int) -> str:
    """Return the text, cut short and ended with an ellipsis if it is wider than this many pixels"""
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(text) <= width:
        return text
    while text and metrics.horizontalAdvance(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def draw_checkbox(painter: QPainter, center: QPointF, checked: bool) -> None:
    """The rounded square of a checkbox, filled when ticked, with a two-pixel outline"""
    outline = color("calendar_blue") if checked else color("border")
    fill = color("calendar_blue") if checked else color("panel")
    half = CHECKBOX_BOX_SIZE / 2
    box = QRectF(center.x() - half, center.y() - half, CHECKBOX_BOX_SIZE, CHECKBOX_BOX_SIZE)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(outline)
    painter.drawRoundedRect(box, CHECKBOX_CORNER_RADIUS, CHECKBOX_CORNER_RADIUS)
    painter.setBrush(fill)
    painter.drawRoundedRect(box.adjusted(2, 2, -2, -2), CHECKBOX_CORNER_RADIUS - 2, CHECKBOX_CORNER_RADIUS - 2)
    painter.restore()


class Header(QWidget):
    """What it shows is set by the app through its attributes, followed by update()"""

    def __init__(self, fonts: Fonts) -> None:
        super().__init__()
        self.fonts = fonts
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # The account text, its colour and font; the Settings page shows the version and credit instead
        self.account_text = "Local only"
        self.account_color = "muted"
        self.account_font = fonts.small
        self.account_disabled = False
        self.progress_reached = False
        self.settings_shown = False
        self.version_text, self.version_is_link = "", False
        self.level_clickable = False
        self.badge: QImage | None = None
        self.badge_state: tuple[int, bool, float] | None = None
        # What a click does in each area, set by the app
        self.on_level: Callable[[], None] = lambda: None
        self.on_account: Callable[[], None] = lambda: None
        self.on_account_double: Callable[[], None] = lambda: None
        self.on_version: Callable[[], None] = lambda: None
        self.on_settings: Callable[[], None] = lambda: None
        # Areas that respond to the pointer, as (left, top, right, bottom); empty while not shown
        self.level_area = self.account_area = self.version_area = NO_AREA
        self.settings_area: Area = NO_AREA
        self.setFixedSize(HEADER_WIDTH, self.row_height())

    def row_height(self) -> int:
        """The same whatever the row shows, so nothing below it moves when the account text changes"""
        return max(HEADER_ICON_SIZE, line_height(self.fonts.account) + 2 * ACCOUNT_TEXT_INSET_Y)

    def set_level(self, level: int, revealed: bool) -> None:
        ratio = self.devicePixelRatioF()
        if self.badge_state != (level, revealed, ratio):
            self.badge_state = (level, revealed, ratio)
            self.badge = render_level_badge(level, revealed, ratio)
            self.update()

    def set_progress_reached(self, reached: bool) -> None:
        if reached != self.progress_reached:
            self.progress_reached = reached
            self.update()

    @staticmethod
    def level_width(fonts: Fonts) -> int:
        """Width from the window's edge to the end of the badge: padding, the word Level, a gap, and the badge"""
        return EDGE_PADDING + QFontMetrics(fonts.normal).horizontalAdvance("Level") + 4 + LEVEL_BADGE_SIZE

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        height = self.height()
        self.level_area = self.account_area = self.version_area = NO_AREA
        if self.settings_shown:
            self._paint_credit(painter, height)
        else:
            self._paint_account(painter, height)
            self._paint_level(painter, height)
        self._paint_settings_button(painter, height)
        painter.end()

    def _text(self, painter: QPainter, x: int, top: int, text: str, text_color: QColor, font: QFont) -> None:
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(QPoint(x, top + ascent(font)), text)

    def _paint_credit(self, painter: QPainter, height: int) -> None:
        """What the Settings page shows in place of the level and account: the version, and the credit. When a newer
        version has been published the version becomes a link to the download page"""
        small, account = self.fonts.small, self.fonts.account
        self._text(
            painter, EDGE_PADDING, (height - line_height(small)) // 2, self.version_text,
            color("accent" if self.version_is_link else "muted"), small,
        )
        if self.version_is_link:
            self.version_area = (0, 0, EDGE_PADDING + QFontMetrics(small).horizontalAdvance(self.version_text) + 4, height)
        credit = "by giltyworks"
        self._text(
            painter, (HEADER_WIDTH - QFontMetrics(account).horizontalAdvance(credit)) // 2,
            (height - line_height(account)) // 2, credit, color("active_green"), account,
        )

    def _paint_account(self, painter: QPainter, height: int) -> None:
        """The progress dot with the account text beside it, kept to one line: centred in the window when it fits there,
        moved towards the settings button when it only fits between the level and that button, and shortened when it
        fits neither"""
        font = self.account_font
        room_left = self.level_width(self.fonts) + HEADER_GROUP_GAP
        room_right = SETTINGS_BUTTON_LEFT + 8 - HEADER_GROUP_GAP
        text = fit_text(self.account_text, font, room_right - room_left - PROGRESS_DOT_SPACE - 2 * ACCOUNT_TEXT_INSET_X)
        content_width = QFontMetrics(font).horizontalAdvance(text) + 2 * ACCOUNT_TEXT_INSET_X
        group_width = PROGRESS_DOT_SPACE + content_width
        group_left = max(room_left, min((HEADER_WIDTH - group_width) // 2, room_right - group_width))
        content_left = group_left + PROGRESS_DOT_SPACE
        dot_top = (height - HEADER_ICON_SIZE) // 2
        reached = self.progress_reached
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(color("calendar_blue" if reached else "border"))
        painter.setBrush(color("calendar_blue" if reached else "panel_alt"))
        # Tk's oval from (2, 6) to (16, 20), its outline running along the inside of that box
        painter.drawEllipse(QRectF(group_left + 2.5, dot_top + 6.5, 13, 13))
        painter.restore()
        text_color = self.palette().color(self.palette().ColorGroup.Disabled, self.palette().ColorRole.Text) if self.account_disabled else color(self.account_color)
        self._text(painter, content_left + ACCOUNT_TEXT_INSET_X, (height - line_height(font)) // 2, text, text_color, font)
        self.account_area = (content_left, 0, content_left + content_width, height)

    def _paint_level(self, painter: QPainter, height: int) -> None:
        """The word Level and the badge at the left, centred on the row"""
        top = (height - HEADER_ICON_SIZE) // 2
        label_height = line_height(self.fonts.normal) + 2 * LABEL_TEXT_INSET
        self._text(
            painter, EDGE_PADDING, top + (HEADER_ICON_SIZE - label_height) // 2 + LABEL_TEXT_INSET, "Level", color("text"), self.fonts.normal
        )
        badge_left = self.level_width(self.fonts) - LEVEL_BADGE_SIZE
        if self.badge is not None:
            painter.drawImage(QPoint(badge_left, top), self.badge)
        self.level_area = (0, top, badge_left + LEVEL_BADGE_SIZE, top + HEADER_ICON_SIZE)

    def _paint_settings_button(self, painter: QPainter, height: int) -> None:
        """Three small dots, which open and close the Settings page. Each is the three pixels Tk drew for it: one, the one
        to its right, and the one below"""
        top = (height - HEADER_ICON_SIZE) // 2
        self.settings_area = (SETTINGS_BUTTON_LEFT, top, SETTINGS_BUTTON_LEFT + HEADER_ICON_SIZE, top + HEADER_ICON_SIZE)
        dot_color = color("text")
        y = top + HEADER_ICON_SIZE // 2
        for index in range(3):
            x = SETTINGS_BUTTON_LEFT + 8 + index * 5
            painter.fillRect(x, y, 2, 1, dot_color)
            painter.fillRect(x, y + 1, 1, 1, dot_color)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        if _inside(self.settings_area, point):
            self.on_settings()
        elif _inside(self.account_area, point):
            self.on_account()
        elif _inside(self.level_area, point):
            self.on_level()
        elif _inside(self.version_area, point):
            self.on_version()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and _inside(self.account_area, event.position().toPoint()):
            self.on_account_double()
        else:
            # Qt reports the second of two quick clicks only as a double-click; elsewhere it is just another click
            self.mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        hand = (
            _inside(self.settings_area, point)
            or _inside(self.account_area, point)
            or _inside(self.version_area, point)
            or (self.level_clickable and _inside(self.level_area, point))
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor if hand else Qt.CursorShape.ArrowCursor)


class ModuleControls(QWidget):
    """The three module names with their checkboxes in a row, laid out from the right edge; clicking a name or its
    checkbox toggles the module"""

    def __init__(self, fonts: Fonts, ticked: dict[str, bool], on_toggle: Callable[[str], None]) -> None:
        super().__init__()
        self.fonts = fonts
        self.ticked = ticked
        self.on_toggle = on_toggle
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        metrics = QFontMetrics(fonts.small)
        self.text_height = line_height(fonts.small)
        row_height = max(self.text_height, MODULE_CHECKBOX_SIZE)
        # For each module, the area of its control, the left of its name and the middle of its checkbox
        self.areas: dict[str, tuple[QRect, int, QPointF]] = {}
        right = TODAY_PANEL_WIDTH - EDGE_PADDING
        for name, label in reversed(MODULE_LABELS):
            left = right - metrics.horizontalAdvance(label) - MODULE_LABEL_GAP - MODULE_CHECKBOX_SIZE
            center = QPointF(right - MODULE_CHECKBOX_SIZE // 2, row_height // 2)
            self.areas[name] = (QRect(left, 0, right - left, row_height), left, center)
            right = left - MODULE_CONTROL_GAP
        self.setFixedSize(TODAY_PANEL_WIDTH, row_height)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        painter.setFont(self.fonts.small)
        painter.setPen(color("muted"))
        baseline = ascent(self.fonts.small)
        text_top = (self.height() - self.text_height) // 2
        for name, label in MODULE_LABELS:
            _area, left, center = self.areas[name]
            painter.drawText(QPoint(left, text_top + baseline), label)
            draw_checkbox(painter, center, self.ticked[name])
        painter.end()

    def _control_at(self, point: QPoint) -> str | None:
        return next((name for name, (area, _left, _center) in self.areas.items() if area.contains(point)), None)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        name = self._control_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and name is not None:
            self.ticked[name] = not self.ticked[name]
            self.update()
            self.on_toggle(name)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # A quick second click toggles again, as in the Tk row
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        on_control = self._control_at(event.position().toPoint()) is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if on_control else Qt.CursorShape.ArrowCursor)
