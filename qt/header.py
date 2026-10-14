"""The header row, with the level, the account and today's progress dot, and the settings button; and the row of
module checkboxes under it. Both are painted, with areas that respond to clicks, as their Tk versions were drawn"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QAbstractAnimation, QPoint, QPointF, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QFocusEvent, QFont, QFontMetrics, QImage, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QLineEdit, QToolTip, QWidget

from app_config import EDGE_PADDING, LEVEL_BADGE_SIZE, TODAY_PANEL_WIDTH

from .badge import render_level_badge
from .module import paint_hover_box, paint_dropdown_arrow, DROPDOWN_BUTTON_SIZE
from .theme import Fonts, color, draw_text, halo_strength, line_height

# The same measurements as the Tk header, see ui_header.py: the header is as wide as the panels; the square the
# level badge and the settings button each take, and the least height of the row; the space holding the progress
# dot; from the edge of the account's area to its text; and the least space between the account and its neighbours
HEADER_WIDTH = TODAY_PANEL_WIDTH
# What the version becomes in Settings once a newer one is published; the version itself shows on hover
UPDATE_LABEL = "Update"
HEADER_ICON_SIZE = 26
PROGRESS_DOT_SPACE = 18
ACCOUNT_TEXT_INSET_X = 5
ACCOUNT_TEXT_INSET_Y = 4
HEADER_GROUP_GAP = 6
# The arrow after the account name that opens the friends status menu: the space it takes, and its half-width
STATUS_ARROW_ROOM = DROPDOWN_BUTTON_SIZE
# How far the status line under the name tucks up into the name's line, which has space below its letters
STATUS_LINE_OVERLAP = 2
# How far a Tk label kept its text from its own edge, which the word Level is still placed by
LABEL_TEXT_INSET = 3
# Where the settings button starts, which leaves its three dots the usual distance from the header's edge
SETTINGS_BUTTON_LEFT = HEADER_WIDTH - HEADER_ICON_SIZE - 2
# The rounded square of a checkbox, as Settings draws them
CHECKBOX_BOX_SIZE = 14
CHECKBOX_CORNER_RADIUS = 4
# The pulse when today reaches its goal: rings spreading from the progress dot and fading, each starting a little after
# the last, and the dot swelling briefly with them
GOAL_PULSE_DELAYS = (0.0, 0.28)
GOAL_PULSE_SECONDS = 0.75
GOAL_PULSE_SPREAD = 5.0
GOAL_PULSE_SWELL = 1.5
MODULE_LABELS = (("graph", "Graph"), ("calendar", "Calendar"), ("stats", "Stats"), ("friends", "Friends"))
# The module buttons: each an icon in a square, with this much between them; a shown module's icon is bright, a hidden
# one's dim
MODULE_BUTTON_SIZE = 22
MODULE_ICON_SIZE = 14
MODULE_BUTTON_GAP = 2
MODULE_ICON_OFF = "#4f5857"
# The display name field is as wide as this many characters, as the Tk entry; a name may be this long
NAME_ENTRY_CHARACTERS = 20
NAME_MAX_LENGTH = 32

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


def draw_checkbox(painter: QPainter, center: QPointF, checked: bool, hovered: bool = False) -> None:
    """The rounded square of a checkbox, filled when ticked, with a two-pixel outline. Under the mouse the inside of an
    empty one fills a shade lighter, as a button's box shows; a ticked one stays as it is"""
    outline = color("calendar_blue") if checked else color("border")
    fill = color("calendar_blue") if checked else color("border" if hovered else "panel")
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


def paint_module_icon(painter: QPainter, kind: str, rect: QRectF, icon_color: QColor) -> None:
    """A module's icon drawn in thin lines inside the square: a rising line for the graph, a page with rings and days
    for the calendar, rows of figures for the stats, and two people for friends"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(icon_color, 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    x, y, size = rect.x(), rect.y(), rect.width()

    def at(fx: float, fy: float) -> QPointF:
        return QPointF(x + fx * size, y + fy * size)

    if kind == "graph":
        painter.drawPolyline([at(0.05, 0.95), at(0.95, 0.95)])
        painter.drawPolyline([at(0.08, 0.75), at(0.35, 0.45), at(0.58, 0.62), at(0.92, 0.18)])
    elif kind == "calendar":
        painter.drawRoundedRect(QRectF(at(0.06, 0.16), at(0.94, 0.94)), 2, 2)
        painter.drawLine(at(0.06, 0.38), at(0.94, 0.38))
        painter.drawLine(at(0.3, 0.04), at(0.3, 0.24))
        painter.drawLine(at(0.7, 0.04), at(0.7, 0.24))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_color)
        for fx in (0.28, 0.5, 0.72):
            for fy in (0.56, 0.77):
                painter.drawEllipse(at(fx, fy), 0.065 * size, 0.065 * size)
    elif kind == "stats":
        for fy, length in ((0.2, 0.92), (0.5, 0.92), (0.8, 0.92)):
            painter.drawLine(at(0.08, fy), at(0.4, fy))
            painter.drawLine(at(0.6, fy), at(length, fy))
    elif kind == "transparency":
        # A circle half filled, half see-through
        painter.drawEllipse(QRectF(at(0.06, 0.06), at(0.94, 0.94)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_color)
        painter.drawPie(QRectF(at(0.06, 0.06), at(0.94, 0.94)), 90 * 16, 180 * 16)
    else:
        # The friend behind, then the one in front
        painter.drawEllipse(at(0.68, 0.28), 0.13 * size, 0.13 * size)
        painter.drawArc(QRectF(at(0.5, 0.5), at(0.98, 1.1)), 30 * 16, 120 * 16)
        painter.drawEllipse(at(0.36, 0.34), 0.16 * size, 0.16 * size)
        painter.drawArc(QRectF(at(0.04, 0.58), at(0.68, 1.3)), 15 * 16, 150 * 16)
    painter.restore()


def paint_glass_background(painter: QPainter, rect, alpha: int) -> None:
    """The app's background, as see-through as the window, replacing what is under it rather than adding to it"""
    background = color("background")
    background.setAlpha(alpha)
    painter.save()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(rect, background)
    painter.restore()


class GlassMixin:
    """How solid a part of the window's background is, from 255 down, set by the window's transparency"""

    glass_alpha = 255

    def set_glass(self, alpha: int) -> None:
        if alpha != self.glass_alpha:
            self.glass_alpha = alpha
            # A see-through part leaves Qt to clear behind it first
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, alpha == 255)
            self.update()


class NameEntry(QLineEdit):
    """The field for typing a display name, shown in place of the account text while a name is edited. Enter or
    clicking elsewhere keeps the name, Escape drops it; on_finished is called with the name, or None when dropped"""

    def __init__(self, parent: QWidget, fonts: Fonts) -> None:
        super().__init__(parent)
        self.on_finished: Callable[[str | None], None] = lambda _name: None
        self.setFont(fonts.account)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrame(False)
        self.setStyleSheet(
            f"QLineEdit {{ background: {color('panel_alt').name()}; color: {color('text').name()};"
            f" selection-background-color: {color('accent_dark').name()}; padding: 0; }}"
        )
        self.setFixedSize(QFontMetrics(fonts.account).horizontalAdvance("0" * NAME_ENTRY_CHARACTERS) + 2, line_height(fonts.account) + 2)
        self.hide()

    def _finish(self, name: str | None) -> None:
        if self.isVisible():
            self.hide()
            self.on_finished(name)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(self.text())
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        # The field's own right-click menu, for pasting, leaves it open
        if event.reason() != Qt.FocusReason.PopupFocusReason:
            self._finish(self.text())


class Header(GlassMixin, QWidget):
    """What it shows is set by the app through its attributes, followed by update()"""

    def __init__(self, fonts: Fonts) -> None:
        super().__init__()
        self.fonts = fonts
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # The account text, its colour and font; the Settings page shows the version and credit instead
        self.account_text = "Local only"
        self.account_color = "muted"
        # Under the name while friends are on, as Steam shows it: Online, Away, Invisible or Offline, and its colour
        self.status_text = ""
        self.status_color = "muted"
        self.account_font = fonts.small
        self.progress_reached = False
        # Whether the dot has been set once: reaching the goal pulses it, but finding it already reached at start does not
        self.progress_known = False
        # Made the first time the goal is reached
        self.pulse: QVariantAnimation | None = None
        self.settings_shown = False
        self.version_text, self.version_is_link = "", False
        self.version_hovered = False
        self.level_clickable = False
        # What the level shows on hover, the XP to the next level; empty while the level is still hidden
        self.level_tip = ""
        # Whether the mouse is over the settings button, which then shows its box
        self.settings_hovered = False
        # Whether the arrow for the friends status menu follows the account name, while friends are on, and whether
        # the mouse is over it
        self.status_arrow_shown = False
        self.status_hovered = False
        self.badge: QImage | None = None
        self.badge_state: tuple[int, bool, float] | None = None
        # What a click does in each area, set by the app
        self.on_level: Callable[[], None] = lambda: None
        self.on_account: Callable[[], None] = lambda: None
        self.on_account_double: Callable[[], None] = lambda: None
        self.on_version: Callable[[], None] = lambda: None
        self.on_settings: Callable[[], None] = lambda: None
        # When today reaches the session minimum while the app runs; the app pulses the dot and fills today's square
        self.on_goal_reached: Callable[[], None] = lambda: None
        # Given where the status menu should open, in screen coordinates
        self.on_status: Callable[[QPoint], None] = lambda _point: None
        # Areas that respond to the pointer, as (left, top, right, bottom); empty while not shown
        self.level_area = self.account_area = self.version_area = NO_AREA
        self.settings_area: Area = NO_AREA
        self.status_area: Area = NO_AREA
        self.setFixedSize(HEADER_WIDTH, self.row_height())
        self.name_entry = NameEntry(self, fonts)
        # Always as wide, so always in the same place beside the progress dot
        self.name_entry.move(self._group_left(self.name_entry.width()) + PROGRESS_DOT_SPACE, (self.height() - self.name_entry.height()) // 2)

    def edit_name(self, name: str, on_finished: Callable[[str | None], None]) -> None:
        """Show the display name field in place of the account text, holding this name, all of it selected"""
        self.name_entry.on_finished = on_finished
        self.name_entry.setText(name)
        self.name_entry.selectAll()
        self.name_entry.show()
        self.name_entry.setFocus()
        self.update()

    def row_height(self) -> int:
        """The same whatever the row shows, so nothing below it moves when the account text changes"""
        return max(HEADER_ICON_SIZE, line_height(self.fonts.account) + 2 * ACCOUNT_TEXT_INSET_Y, self._account_block_height() + 2)

    def _account_block_height(self) -> int:
        """The name with the status under it, the two lines overlapping a little where the name's line has room"""
        return line_height(self.fonts.account) + line_height(self.fonts.caption) - STATUS_LINE_OVERLAP

    def set_level(self, level: int, revealed: bool) -> None:
        ratio = self.devicePixelRatioF()
        if self.badge_state != (level, revealed, ratio):
            self.badge_state = (level, revealed, ratio)
            self.badge = render_level_badge(level, revealed, ratio)
            self.update()

    def set_level_tip(self, tip: str) -> None:
        """The XP shown on hovering the level, kept up to date while it shows, so Remaining XP counts down each second"""
        if tip == self.level_tip:
            return
        showing = QToolTip.isVisible() and self.toolTip() == self.level_tip and bool(self.level_tip)
        self.level_tip = tip
        if showing:
            self.setToolTip(tip)
            QToolTip.showText(QCursor.pos(), tip, self)

    def set_progress_reached(self, reached: bool) -> None:
        if reached != self.progress_reached:
            if reached and self.progress_known:
                self.on_goal_reached()
            self.progress_reached = reached
            self.update()
        self.progress_known = True

    def pulse_progress_dot(self) -> None:
        # Only while it can be seen: hidden in the tray or minimized there is nothing to animate
        if not self.isVisible():
            return
        if self.pulse is None:
            self.pulse = QVariantAnimation(self)
            self.pulse.setStartValue(0.0)
            self.pulse.setEndValue(1.0)
            self.pulse.setDuration(round((max(GOAL_PULSE_DELAYS) + GOAL_PULSE_SECONDS) * 1000))
            self.pulse.valueChanged.connect(self.update)
            self.pulse.finished.connect(self.update)
        self.pulse.stop()
        self.pulse.start()

    def pulsing(self) -> bool:
        return self.pulse is not None and self.pulse.state() == QAbstractAnimation.State.Running


    @staticmethod
    def level_width(fonts: Fonts) -> int:
        """Width from the window's edge to the end of the badge: padding, the word Level, a gap, and the badge"""
        return EDGE_PADDING + QFontMetrics(fonts.normal).horizontalAdvance("Level") + 4 + LEVEL_BADGE_SIZE

    def badge_center(self) -> QPointF:
        """The middle of the level badge, which the first firework of a level-up bursts from"""
        top = (self.height() - HEADER_ICON_SIZE) // 2
        return QPointF(self.level_width(self.fonts) - LEVEL_BADGE_SIZE / 2, top + HEADER_ICON_SIZE / 2)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.halo = halo_strength(self.glass_alpha)
        paint_glass_background(painter, self.rect(), self.glass_alpha)
        height = self.height()
        self.level_area = self.account_area = self.version_area = self.status_area = NO_AREA
        if self.settings_shown:
            self._paint_credit(painter, height)
        else:
            self._paint_account(painter, height)
            self._paint_level(painter, height)
        self._paint_settings_button(painter, height)
        painter.end()

    def _text(self, painter: QPainter, x: int, top: int, text: str, text_color: QColor, font: QFont) -> None:
        draw_text(painter, x, top, text, text_color, font)

    def _paint_credit(self, painter: QPainter, height: int) -> None:
        """What the Settings page shows in place of the level and account: the version, and the credit. When a newer
        version has been published the version becomes a link to the download page"""
        small, account = self.fonts.small, self.fonts.account
        if self.version_is_link:
            # An Update button, as the accent buttons in Settings; the version it gets shows on hover
            box = QRectF(EDGE_PADDING - 2, (height - line_height(small)) / 2 - 3,
                         QFontMetrics(small).horizontalAdvance(UPDATE_LABEL) + 16, line_height(small) + 6)
            paint_hover_box(painter, box, color("accent_dark").lighter(130 if self.version_hovered else 100))
            self._text(painter, int(box.x()) + 8, (height - line_height(small)) // 2, UPDATE_LABEL, color("accent"), small)
            self.version_area = (int(box.left()), int(box.top()), int(box.right()), int(box.bottom()))
        else:
            self._text(painter, EDGE_PADDING, (height - line_height(small)) // 2, self.version_text, color("muted"), small)
        credit = "by giltyworks"
        self._text(
            painter, (HEADER_WIDTH - QFontMetrics(account).horizontalAdvance(credit)) // 2,
            (height - line_height(account)) // 2, credit, color("active_green"), account,
        )

    def _group_left(self, content_width: int) -> int:
        """Where the progress dot and the account beside it start: centred in the window when they fit there, otherwise
        as far from the level as they need to be to fit before the settings button"""
        room_left = self.level_width(self.fonts) + HEADER_GROUP_GAP
        room_right = SETTINGS_BUTTON_LEFT + 8 - HEADER_GROUP_GAP
        group_width = PROGRESS_DOT_SPACE + content_width
        return max(room_left, min((HEADER_WIDTH - group_width) // 2, room_right - group_width))

    def _paint_account(self, painter: QPainter, height: int) -> None:
        """The progress dot with the account text beside it, kept to one line: centred in the window when it fits there,
        moved towards the settings button when it only fits between the level and that button, and shortened when it
        fits neither"""
        font = self.account_font
        room_left = self.level_width(self.fonts) + HEADER_GROUP_GAP
        room_right = SETTINGS_BUTTON_LEFT + 8 - HEADER_GROUP_GAP
        editing = self.name_entry.isVisible()
        arrow_room = STATUS_ARROW_ROOM if self.status_arrow_shown and not editing else 0
        text = fit_text(self.account_text, font, room_right - room_left - PROGRESS_DOT_SPACE - 2 * ACCOUNT_TEXT_INSET_X - arrow_room)
        if editing:
            content_width = self.name_entry.width()
        else:
            content_width = QFontMetrics(font).horizontalAdvance(text) + 2 * ACCOUNT_TEXT_INSET_X + arrow_room
        group_left = self._group_left(content_width)
        content_left = group_left + PROGRESS_DOT_SPACE
        dot_top = (height - HEADER_ICON_SIZE) // 2
        reached = self.progress_reached
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(color("calendar_blue" if reached else "border"))
        painter.setBrush(color("calendar_blue" if reached else "panel_alt"))
        # Tk's oval from (2, 6) to (16, 20), its outline running along the inside of that box
        dot = QRectF(group_left + 2.5, dot_top + 6.5, 13, 13)
        if self.pulsing():
            elapsed = self.pulse.currentTime() / 1000
            swell = GOAL_PULSE_SWELL * max(0.0, 1 - abs(elapsed / GOAL_PULSE_SECONDS * 2 - 1)) if elapsed < GOAL_PULSE_SECONDS else 0.0
            painter.drawEllipse(dot.adjusted(-swell, -swell, swell, swell))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for delay in GOAL_PULSE_DELAYS:
                share = (elapsed - delay) / GOAL_PULSE_SECONDS
                if 0 <= share <= 1:
                    # Eased out: quick to spread, slowing as it fades
                    spread = GOAL_PULSE_SPREAD * (1 - (1 - share) ** 3)
                    ring = QColor(color("calendar_blue"))
                    ring.setAlphaF(1 - share)
                    painter.setPen(QPen(ring, 1.5))
                    painter.drawEllipse(dot.adjusted(-spread, -spread, spread, spread))
        else:
            painter.drawEllipse(dot)
        painter.restore()
        if editing:
            return
        # Always in its own colour: a backup or upload going on in the background does not grey it
        text_color = color(self.account_color)
        if self.status_text:
            # The name with its status under it, the two centred on the row together
            name_top = (height - self._account_block_height()) // 2
            status_top = name_top + line_height(font) - STATUS_LINE_OVERLAP
            self._text(painter, content_left + ACCOUNT_TEXT_INSET_X, status_top, self.status_text, color(self.status_color), self.fonts.caption)
        else:
            name_top = (height - line_height(font)) // 2
        self._text(painter, content_left + ACCOUNT_TEXT_INSET_X, name_top, text, text_color, font)
        self.account_area = (content_left, 0, content_left + content_width - arrow_room, height)
        if arrow_room:
            self._paint_status_arrow(painter, content_left + content_width - arrow_room - 2, name_top + line_height(font) / 2)

    def _paint_status_arrow(self, painter: QPainter, left: int, middle_y: float) -> None:
        """A small downward chevron, which opens the friends status menu; under the mouse a faint box shows behind it"""
        top = round(middle_y - DROPDOWN_BUTTON_SIZE / 2)
        self.status_area = (left, top, left + DROPDOWN_BUTTON_SIZE, top + DROPDOWN_BUTTON_SIZE)
        paint_dropdown_arrow(painter, QRectF(left, top, DROPDOWN_BUTTON_SIZE, DROPDOWN_BUTTON_SIZE),
                             self.status_hovered)

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
        if self.settings_hovered:
            paint_hover_box(painter, QRectF(SETTINGS_BUTTON_LEFT + 2, top + 4, HEADER_ICON_SIZE - 4, HEADER_ICON_SIZE - 8), color("border"))
        # The same grey as the dock icon
        dot_color = color("muted")
        y = top + HEADER_ICON_SIZE // 2
        for index in range(3):
            x = SETTINGS_BUTTON_LEFT + 8 + index * 5
            painter.fillRect(x, y, 2, 1, dot_color)
            painter.fillRect(x, y + 1, 1, 1, dot_color)

    def interactive_at(self, point: QPoint) -> bool:
        """Whether a press here is a click on something, rather than the start of moving the window"""
        return (
            _inside(self.settings_area, point) or _inside(self.account_area, point) or _inside(self.version_area, point)
            or _inside(self.status_area, point) or (self.level_clickable and _inside(self.level_area, point))
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        if _inside(self.settings_area, point):
            self.on_settings()
        elif _inside(self.status_area, point):
            left, _top, _right, bottom = self.status_area
            self.on_status(self.mapToGlobal(QPoint(left, bottom + 2)))
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

    def leaveEvent(self, _event) -> None:
        self.setToolTip("")
        if self.settings_hovered or self.status_hovered or self.version_hovered:
            self.settings_hovered = self.status_hovered = self.version_hovered = False
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over_settings = _inside(self.settings_area, point)
        over_status = _inside(self.status_area, point)
        if (over_settings, over_status) != (self.settings_hovered, self.status_hovered):
            self.settings_hovered, self.status_hovered = over_settings, over_status
            self.update()
        over_version = self.version_is_link and _inside(self.version_area, point)
        if over_version != self.version_hovered:
            self.version_hovered = over_version
            self.update()
        tip = self.version_text if over_version else self.level_tip if _inside(self.level_area, point) else ""
        if tip != self.toolTip():
            self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.interactive_at(point) else Qt.CursorShape.ArrowCursor)


class ModuleControls(GlassMixin, QWidget):
    """The module buttons in a row at the right, one icon each; clicking one shows or hides its module. The mouse over
    one shows its rounded box and its name. At the left end, the transparency icon opens its slider"""

    def __init__(
        self, fonts: Fonts, ticked: dict[str, bool], on_toggle: Callable[[str], None],
        on_transparency: Callable[[QRect], None] = lambda _area: None,
    ) -> None:
        super().__init__()
        self.fonts = fonts
        self.ticked = ticked
        self.on_toggle = on_toggle
        # Told the icon's square, to open the slider under it
        self.on_transparency = on_transparency
        # The transparency setting, from 0 (solid) to 100, which the icon dims with
        self.transparency = 0
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # Each module's square, laid out from the right edge
        self.areas: dict[str, QRect] = {}
        right = TODAY_PANEL_WIDTH - EDGE_PADDING + (MODULE_BUTTON_SIZE - MODULE_ICON_SIZE) // 2
        for name, _label in reversed(MODULE_LABELS):
            self.areas[name] = QRect(right - MODULE_BUTTON_SIZE, 0, MODULE_BUTTON_SIZE, MODULE_BUTTON_SIZE)
            right -= MODULE_BUTTON_SIZE + MODULE_BUTTON_GAP
        # At the left end of the row, lined up with the level in the header above, as it shows no module
        left = EDGE_PADDING - (MODULE_BUTTON_SIZE - MODULE_ICON_SIZE) // 2
        self.transparency_area = QRect(left, 0, MODULE_BUTTON_SIZE, MODULE_BUTTON_SIZE)
        self.setFixedSize(TODAY_PANEL_WIDTH, MODULE_BUTTON_SIZE)
        # The module whose button the mouse is over, which then shows its box
        self.hovered: str | None = None

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.halo = halo_strength(self.glass_alpha)
        paint_glass_background(painter, self.rect(), self.glass_alpha)
        inset = (MODULE_BUTTON_SIZE - MODULE_ICON_SIZE) / 2
        for name, _label in MODULE_LABELS:
            area = QRectF(self.areas[name])
            if name == self.hovered:
                paint_hover_box(painter, area.adjusted(1, 1, -1, -1), color("border"))
            icon_color = color("text") if self.ticked[name] else QColor(MODULE_ICON_OFF)
            paint_module_icon(painter, name, area.adjusted(inset, inset, -inset, -inset), icon_color)
        area = QRectF(self.transparency_area)
        if self.hovered == "transparency":
            paint_hover_box(painter, area.adjusted(1, 1, -1, -1), color("border"))
        # Solid, the icon is as bright as a shown module's; fully see-through, about as dim as a hidden one's
        icon_color = color("text")
        icon_color.setAlphaF(1 - 0.75 * self.transparency / 100)
        paint_module_icon(painter, "transparency", area.adjusted(inset, inset, -inset, -inset), icon_color)
        painter.end()

    def interactive_at(self, point: QPoint) -> bool:
        return self._control_at(point) is not None

    def _control_at(self, point: QPoint) -> str | None:
        if self.transparency_area.contains(point):
            return "transparency"
        return next((name for name, area in self.areas.items() if area.contains(point)), None)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        name = self._control_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and name == "transparency":
            self.on_transparency(self.transparency_area)
        elif event.button() == Qt.MouseButton.LeftButton and name is not None:
            self.ticked[name] = not self.ticked[name]
            # Its name now offers the opposite
            self.hovered = None
            self._hover(name)
            self.on_toggle(name)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # A quick second click toggles again; on the transparency icon it closes the slider, as the popup does
        if self._control_at(event.position().toPoint()) != "transparency":
            self.mousePressEvent(event)

    def _hover(self, name: str | None) -> None:
        if name != self.hovered:
            self.hovered = name
            labels = dict(MODULE_LABELS)
            if name == "transparency":
                self.setToolTip("Transparency")
            else:
                self.setToolTip(f"{'Hide' if name and self.ticked[name] else 'Show'} {labels[name]}" if name else "")
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        name = self._control_at(event.position().toPoint())
        self._hover(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor if name is not None else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, _event) -> None:
        self._hover(None)
