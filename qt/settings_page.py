"""The Settings page: which programs are counted, start-up and layout options, and the backups box with its Google
buttons. Painted as one widget, with areas that respond to clicks, laid out as the Tk ui_settings.py packs its labels"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app_config import COMPACT_BOTTOM_SPACE, EDGE_PADDING, PANEL_GAP, TODAY_PANEL_WIDTH

from .header import draw_checkbox
from .module import PaintedButton, draw_rounded_box
from .theme import Fonts, ascent, color, draw_text, line_height, text_width

# The same measurements as the Tk page, see ui_settings.py
PAGE_TEXT_WIDTH = TODAY_PANEL_WIDTH - 2 * EDGE_PADDING
TOGGLE_TEXT_WIDTH = PAGE_TEXT_WIDTH - 40
BOX_PADDING = 5
ORIENTATION_ICON_SIZE = (26, 18)
ORIENTATION_ICON_RADIUS = 4
ORIENTATION_ICON_GAP = 10
# The transparency slider: its length, the thickness of its track and the knob's size
SLIDER_WIDTH = 92
SLIDER_TRACK = 4
SLIDER_KNOB = 14
BACKUP_BOX_PADDING = 9
BACKUP_LINE_GAP = 7
CHECKBOX_LABEL_GAP = 6
CHECKBOX_GAP = 8
CHECKBOX_SIZE = 18
TITLE_PADDING = 8
TITLE_GAP = 6
DESCRIPTION_GAP = 14
# Padding of the page's buttons, as PSFocusApp._button gives them
BUTTON_PADX = 17
BUTTON_PADY = 6

PROGRAM_CHECKBOXES = (("tracking_enabled", "Photoshop"), ("tracking_clip_studio_paint", "CSP"), ("tracking_krita", "Krita"))
OPTION_CHECKBOXES = (("tracking_paused", "Pause tracking"), ("disable_fanfare_sound", "Disable fanfare sound"))
TOGGLES = (
    ("launch_on_startup", "Start with Windows", "Launch PS Focus when you sign in to Windows"),
    ("start_minimized", "Start minimized", "Open PS Focus minimized when launched at sign-in"),
)


def wrap(text: str, font: QFont, width: int) -> list[str]:
    """Break text into lines no wider than this, at spaces, as a Tk label with a wraplength does"""
    if width <= 0:
        return [text]
    lines: list[str] = []
    line = ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if line and text_width(font, candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line]


@dataclass
class Text:
    """Lines of text with the top left of the first at (x, y)"""

    x: int
    y: int
    lines: list[str]
    color: str
    font: QFont

    def width(self) -> int:
        return max(text_width(self.font, line) for line in self.lines)

    def height(self) -> int:
        return len(self.lines) * line_height(self.font)

    def contains(self, point: QPoint) -> bool:
        return self.x <= point.x() < self.x + self.width() and self.y <= point.y() < self.y + self.height()


class SettingsPage(QWidget):
    """The app passes in the settings it reads, and what each control does. Clicking a checkbox calls on_toggle with
    its setting's name; the app changes the setting, or refuses to, then calls update()"""

    def __init__(
        self,
        fonts: Fonts,
        settings: dict,
        on_toggle: Callable[[str], None],
        on_orientation: Callable[[bool], None],
        on_resized: Callable[[], None],
    ) -> None:
        super().__init__()
        self.fonts = fonts
        self.settings = settings
        self.on_toggle = on_toggle
        self.on_orientation = on_orientation
        self.on_resized = on_resized
        # Told the transparency while the slider is dragged, and once more, done, when it is let go
        self.on_transparency: Callable[[int, bool], None] = lambda _value, _done: None
        self.slider_left = self.slider_top = 0
        self.slider_dragging = False
        self.disabled_settings: set[str] = set()
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        # What the backups box shows, set by the app: the Google status line, which a click on resyncs while it is
        # clickable, and the backup status under it
        self.google_status = ("Not connected", "muted")
        self.google_status_clickable = False
        self.backup_status = ("Creating local backups", "muted")
        # Which Google buttons the row shows: "connect", "connected" or "reconnect", see _arrange_google_buttons
        self.google_buttons = "connect"
        self.on_google_status: Callable[[], None] = lambda: None
        button = lambda text, accent=False: PaintedButton(  # noqa: E731
            text, lambda: None, fonts, BUTTON_PADX, BUTTON_PADY, text_color="accent" if accent else "muted", fill="accent_dark" if accent else "panel_alt"
        )
        self.backup_button = button("Back up now", accent=True)
        self.connect_button = button("Connect Google", accent=True)
        self.reconnect_button = button("Reconnect", accent=True)
        self.switch_button = button("Switch account")
        self.logout_button = button("Log out")
        self.exit_button = button("Exit")
        # Shown once enough time has been tracked, see the app's feedback_unlocked
        self.feedback_button = button("Got feedback?")
        self.feedback_shown = False
        self.texts: list[Text] = []
        self.boxes: list[tuple[int, int]] = []
        self.checkboxes: dict[str, tuple[tuple[int, int, int, int], QPointF, str]] = {}
        self.orientation_areas: dict[bool, tuple[int, int, int, int]] = {}
        self.orientation_left = self.orientation_top = 0
        self.buttons: list[PaintedButton] = []
        self.google_status_text: Text | None = None
        self._lay_out()

    def set_google(self, status: tuple[str, str], clickable: bool, buttons: str) -> None:
        if (status, clickable, buttons) == (self.google_status, self.google_status_clickable, self.google_buttons):
            return
        self.google_status, self.google_status_clickable, self.google_buttons = status, clickable, buttons
        self._lay_out()

    def set_backup_status(self, text: str, color_name: str) -> None:
        if self.backup_status == (text, color_name):
            return
        self.backup_status = (text, color_name)
        self._lay_out()

    def set_feedback_shown(self, shown: bool) -> None:
        if shown != self.feedback_shown:
            self.feedback_shown = shown
            self._lay_out()

    def set_google_buttons_enabled(self, enabled: bool) -> None:
        for button in (self.connect_button, self.reconnect_button, self.switch_button, self.logout_button):
            button.enabled = enabled
        self.update()

    def _text(self, x: int, y: int, text: str, color_name: str, font: QFont, width: int = 0) -> Text:
        item = Text(x, y, wrap(text, font, width), color_name, font)
        self.texts.append(item)
        return item

    def _checkbox_row(self, y: int, checkboxes: tuple[tuple[str, str], ...]) -> int:
        """A row of named checkboxes ending at the right edge; returns its height"""
        font = self.fonts.small
        height = max(line_height(font), CHECKBOX_SIZE)
        right = TODAY_PANEL_WIDTH - EDGE_PADDING
        for key, label in reversed(checkboxes):
            left = right - text_width(font, label) - CHECKBOX_LABEL_GAP - CHECKBOX_SIZE
            self._text(left, y + (height - line_height(font)) // 2, label, "muted", font)
            center = QPointF(right - CHECKBOX_SIZE // 2, y + height // 2)
            self.checkboxes[key] = ((left, y, right, y + height), center, "background")
            right = left - CHECKBOX_GAP
        return height

    def _boxed_row(self, y: int, title: str, description: str, text_width_: int, control_height: int) -> tuple[int, int]:
        """A bordered row with a bold title and a description under it at its left; returns its height and the top of
        the control centred at its right"""
        title_text = self._text(1 + EDGE_PADDING, y + 1 + BOX_PADDING, title, "text", self.fonts.bold, text_width_)
        description_text = self._text(
            1 + EDGE_PADDING, title_text.y + title_text.height() + 2, description, "muted", self.fonts.small, text_width_
        )
        inner = max(2 * BOX_PADDING + title_text.height() + 2 + description_text.height(), control_height)
        self.boxes.append((y, inner + 2))
        return inner + 2, y + 1 + (inner - control_height) // 2

    def _lay_out(self) -> None:
        """Work out where everything goes, from the top of the page down"""
        fonts = self.fonts
        self.texts, self.boxes, self.checkboxes, self.buttons = [], [], {}, []
        # The title, set against its capitals rather than the space the large font reserves above them
        title_ascent = ascent(fonts.title)
        capital_height = round(title_ascent * 0.66)
        descent = line_height(fonts.title) - title_ascent
        self._text(EDGE_PADDING, TITLE_PADDING - (title_ascent - capital_height), "Settings", "text", fonts.title)
        y = TITLE_PADDING + capital_height + descent + 2 + TITLE_GAP
        description = self._text(
            EDGE_PADDING, y, "PS Focus counts time in Photoshop, Krita and CSP while they are in front and pauses when you're inactive",
            "muted", fonts.normal, PAGE_TEXT_WIDTH,
        )
        y += description.height() + DESCRIPTION_GAP
        y += self._checkbox_row(y, PROGRAM_CHECKBOXES) + PANEL_GAP
        for key, title, text in TOGGLES:
            height, control_top = self._boxed_row(y, title, text, TOGGLE_TEXT_WIDTH, CHECKBOX_SIZE)
            # The drawn box is two pixels inside its square, which puts its right side EDGE_PADDING from the edge
            left = TODAY_PANEL_WIDTH - 1 - (EDGE_PADDING - 2) - CHECKBOX_SIZE
            center = QPointF(left + CHECKBOX_SIZE // 2, control_top + CHECKBOX_SIZE // 2)
            self.checkboxes[key] = ((left, control_top, left + CHECKBOX_SIZE, control_top + CHECKBOX_SIZE), center, "panel")
            y += height + PANEL_GAP
        # Orientation: a tall shape for portrait and a wide one for landscape, the chosen one filled
        long_side, short_side = ORIENTATION_ICON_SIZE
        choice_width = short_side + ORIENTATION_ICON_GAP + long_side
        height, self.orientation_top = self._boxed_row(
            y, "Orientation", "Modules below or beside the program panels", PAGE_TEXT_WIDTH - choice_width - EDGE_PADDING, long_side
        )
        self.orientation_left = TODAY_PANEL_WIDTH - 1 - EDGE_PADDING - choice_width
        landscape_left = short_side + ORIENTATION_ICON_GAP
        for landscape, (left, right) in ((False, (0, short_side)), (True, (landscape_left, landscape_left + long_side))):
            self.orientation_areas[landscape] = (
                self.orientation_left + left - 3, self.orientation_top, self.orientation_left + right + 4, self.orientation_top + long_side
            )
        y += height + PANEL_GAP
        height, control_top = self._boxed_row(
            y, "Transparency", "PS Focus turns see-through while the mouse is elsewhere",
            PAGE_TEXT_WIDTH - SLIDER_WIDTH - EDGE_PADDING, SLIDER_KNOB,
        )
        self.slider_left = TODAY_PANEL_WIDTH - 1 - EDGE_PADDING - SLIDER_WIDTH
        self.slider_top = control_top
        y += height + PANEL_GAP
        y += self._checkbox_row(y, OPTION_CHECKBOXES) + PANEL_GAP
        y = self._lay_out_backups(y)
        # Exit at the left, and Got feedback? at the right once unlocked
        y += PANEL_GAP
        self.exit_button.place(EDGE_PADDING, y)
        self.buttons.append(self.exit_button)
        if self.feedback_shown:
            self.feedback_button.place(TODAY_PANEL_WIDTH - EDGE_PADDING - self.feedback_button.width, y)
            self.buttons.append(self.feedback_button)
        y += self.exit_button.height + COMPACT_BOTTOM_SPACE
        old_height = self.height()
        self.setFixedSize(TODAY_PANEL_WIDTH, y)
        self.update()
        if y != old_height:
            self.on_resized()

    def _lay_out_backups(self, top: int) -> int:
        """The bordered box about backups, with its status lines and a row of buttons; returns where it ends"""
        fonts = self.fonts
        x = 1 + EDGE_PADDING
        y = top + 1 + BACKUP_BOX_PADDING
        y += self._text(x, y, "Settings and activity backups", "text", fonts.bold).height() + BACKUP_LINE_GAP
        y += self._text(
            x, y, "Activity is saved locally on this PC and backed up to Google Drive when connected", "muted", fonts.normal,
            TOGGLE_TEXT_WIDTH + 40 - 2,
        ).height() + BACKUP_LINE_GAP + 2
        self.google_status_text = self._text(x, y, *self.google_status, fonts.small, PAGE_TEXT_WIDTH - 2)
        y += self.google_status_text.height() + BACKUP_LINE_GAP
        y += self._text(x, y, *self.backup_status, fonts.small, PAGE_TEXT_WIDTH - 2).height() + BACKUP_LINE_GAP + 3
        # Back up now at the left; Connect Google at the right, or once connected Log out at the right and Switch
        # account, or Reconnect when the sign-in needs renewing, centred in the space between
        self.backup_button.place(x, y)
        self.buttons.append(self.backup_button)
        right_edge = TODAY_PANEL_WIDTH - 1 - EDGE_PADDING
        right = self.connect_button if self.google_buttons == "connect" else self.logout_button
        right.place(right_edge - right.width, y)
        self.buttons.append(right)
        if self.google_buttons != "connect":
            middle = self.reconnect_button if self.google_buttons == "reconnect" else self.switch_button
            space_left = self.backup_button.right
            middle.place(space_left + (right.left - space_left - middle.width) // 2, y)
            self.buttons.append(middle)
        y += self.backup_button.height + BACKUP_BOX_PADDING + 1
        self.boxes.append((top, y - top))
        return y

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        for top, height in self.boxes:
            painter.fillRect(0, top, TODAY_PANEL_WIDTH, height, color("border"))
            painter.fillRect(1, top + 1, TODAY_PANEL_WIDTH - 2, height - 2, color("panel"))
        for text in self.texts:
            for index, line in enumerate(text.lines):
                draw_text(painter, text.x, text.y + index * line_height(text.font), line, color(text.color), text.font)
        for key, (_area, center, _surface) in self.checkboxes.items():
            draw_checkbox(painter, center, bool(self.settings.get(key)))
        self._paint_orientation(painter)
        self._paint_slider(painter)
        for button in self.buttons:
            button.paint(painter)
        painter.end()

    def _paint_orientation(self, painter: QPainter) -> None:
        long_side, short_side = ORIENTATION_ICON_SIZE
        chosen_landscape = bool(self.settings.get("landscape"))
        middle = self.orientation_top + long_side // 2
        for landscape, left in ((False, 0), (True, short_side + ORIENTATION_ICON_GAP)):
            width, height = (long_side, short_side) if landscape else (short_side, long_side)
            chosen = landscape == chosen_landscape
            box = QRectF(self.orientation_left + left, middle - height // 2, width, height)
            fill: QColor = color("text" if chosen else "panel")
            draw_rounded_box(painter, box, ORIENTATION_ICON_RADIUS, fill, color("text" if chosen else "muted"), outline_width=2)

    def transparency(self) -> int:
        try:
            return max(0, min(100, int(self.settings.get("panel_transparency", 0))))
        except (TypeError, ValueError):
            return 0

    def _paint_slider(self, painter: QPainter) -> None:
        """A track filled in blue up to the knob, as far as the panels are see-through"""
        middle = self.slider_top + SLIDER_KNOB / 2
        knob_x = self.slider_left + SLIDER_KNOB / 2 + (SLIDER_WIDTH - SLIDER_KNOB) * self.transparency() / 100
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        track = QRectF(self.slider_left, middle - SLIDER_TRACK / 2, SLIDER_WIDTH, SLIDER_TRACK)
        painter.setBrush(color("border"))
        painter.drawRoundedRect(track, SLIDER_TRACK / 2, SLIDER_TRACK / 2)
        painter.setBrush(color("calendar_blue"))
        painter.drawRoundedRect(QRectF(track.left(), track.top(), knob_x - track.left(), SLIDER_TRACK), SLIDER_TRACK / 2, SLIDER_TRACK / 2)
        painter.setBrush(color("text"))
        painter.drawEllipse(QPointF(knob_x, middle), SLIDER_KNOB / 2, SLIDER_KNOB / 2)
        painter.restore()

    def _over_slider(self, point: QPoint) -> bool:
        return (self.slider_left - 4 <= point.x() <= self.slider_left + SLIDER_WIDTH + 4
                and self.slider_top - 4 <= point.y() <= self.slider_top + SLIDER_KNOB + 4)

    def _slide_to(self, point: QPoint, done: bool) -> None:
        span = SLIDER_WIDTH - SLIDER_KNOB
        value = round(max(0, min(span, point.x() - self.slider_left - SLIDER_KNOB / 2)) * 100 / span)
        self.on_transparency(value, done)
        self.update()

    def _checkbox_at(self, point: QPoint) -> str | None:
        for key, ((left, top, right, bottom), _center, _surface) in self.checkboxes.items():
            if left <= point.x() < right and top <= point.y() < bottom:
                return key
        return None

    def _orientation_at(self, point: QPoint) -> bool | None:
        for landscape, (left, top, right, bottom) in self.orientation_areas.items():
            if left <= point.x() < right and top <= point.y() < bottom:
                return landscape
        return None

    def _over_status(self, point: QPoint) -> bool:
        return self.google_status_clickable and self.google_status_text is not None and self.google_status_text.contains(point)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        if any([button.press(point) for button in self.buttons]):
            self.update()
            return
        if self._over_slider(point):
            self.slider_dragging = True
            self._slide_to(point, False)
            return
        key = self._checkbox_at(point)
        landscape = self._orientation_at(point)
        if key is not None and key not in self.disabled_settings:
            self.on_toggle(key)
            self.update()
        elif landscape is not None:
            self.on_orientation(landscape)
            self.update()
        elif self._over_status(point):
            self.on_google_status()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # A quick second click on a checkbox toggles it again, as in the Tk page
        self.mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self.slider_dragging and event.button() == Qt.MouseButton.LeftButton:
            self.slider_dragging = False
            self._slide_to(point, True)
            return
        if event.button() == Qt.MouseButton.LeftButton and any([button.release(point) for button in self.buttons]):
            self.update()

    def leaveEvent(self, _event) -> None:
        if PaintedButton.update_hover(self.buttons, None):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if PaintedButton.update_hover(self.buttons, point):
            self.update()
        if self.slider_dragging:
            self._slide_to(point, False)
            return
        hand = self._over_slider(point) or (
            any(button.enabled and button.contains(point) for button in self.buttons)
            or (self._checkbox_at(point) is not None and self._checkbox_at(point) not in self.disabled_settings)
            or self._orientation_at(point) is not None
            or self._over_status(point)
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor if hand else Qt.CursorShape.ArrowCursor)
