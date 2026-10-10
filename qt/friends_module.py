"""The friends module: the people added by friend code, ranked by their hours over the past two weeks, with requests
waiting for an answer, and the user's own code. What it shows is handed to it as a FriendsView, see friends_sync"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QLineEdit, QWidget

from app_config import EDGE_PADDING, LINE_PADDING, TODAY_PANEL_WIDTH
from friends import format_code

from .header import fit_text
from .module import ModuleBlock, PaintedButton, paint_hover_box
from .theme import Fonts, color, draw_anchored, draw_text, line_height, text_width

# Space between the module's border and its text, as the stats keep
SIDE = 1 + EDGE_PADDING
BUTTON_PADX = 8
BUTTON_PADY = 3
BUTTON_GAP = 4
# Space between one person's rows and the next, and between the groups: requests, the ranking, the code row
ROW_GAP = 4
GROUP_GAP = 8
BOTTOM_PADDING = 6
# The dot beside someone's name: green drawing, blue online, orange away; none offline
ACTIVE_DOT_SIZE = 6
PRESENCE_COLORS = {"drawing": "active_green", "online": "calendar_blue", "away": "orange"}
# Short names for the programs, which share a line with the person's name
PROGRAM_SHORT_NAMES = {"Clip Studio Paint": "Clip Studio"}
# The list of requests and friends scrolls beyond this many friends' rows in portrait, and beyond the height the
# modules share in landscape; a turn of the mouse wheel moves it this far
PORTRAIT_LIST_ROWS = 4
SCROLL_STEP = 36
SCROLL_BAR_WIDTH = 3
# The code field takes a code typed with or without its dash
CODE_ENTRY_CHARACTERS = 11


@dataclass
class FriendsView:
    """What the module shows. mode is one of: unavailable, signed_out, off, offline, loading, on"""

    mode: str = "unavailable"
    code: str = ""
    # The friends ranked, as (name, stats, presence, program or None, code). Presence is drawing, online, away or offline
    people: list[tuple[str, dict, str, str | None, str]] = field(default_factory=list)
    incoming: list[tuple[str, str]] = field(default_factory=list)
    outgoing: list[tuple[str, str]] = field(default_factory=list)
    # A message under the list, and its colour
    message: tuple[str, str] | None = None
    busy: bool = False


@dataclass
class FriendsActions:
    sign_in: Callable[[], None] = lambda: None
    turn_on: Callable[[], None] = lambda: None
    turn_off: Callable[[], None] = lambda: None
    add: Callable[[str], None] = lambda _code: None
    accept: Callable[[str], None] = lambda _code: None
    decline: Callable[[str], None] = lambda _code: None
    # Unfriend someone (given their name, for asking first), or cancel a request sent
    remove: Callable[[str, str], None] = lambda _code, _name: None
    cancel: Callable[[str], None] = lambda _code: None
    copy_code: Callable[[str], None] = lambda _code: None
    # The mouse came onto the module, the moment someone looks at their friends
    looked_at: Callable[[], None] = lambda: None


def wrap(text: str, font, width: int) -> list[str]:
    """The text broken into lines no wider than this, at spaces"""
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and text_width(font, candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line] if line else lines


class CodeEntry(QLineEdit):
    """Where a friend's code is typed. Enter adds them, Escape or clicking elsewhere closes it"""

    def __init__(self, parent: QWidget, fonts: Fonts) -> None:
        super().__init__(parent)
        self.on_finished: Callable[[str | None], None] = lambda _code: None
        self.setFont(fonts.small)
        self.setFrame(False)
        self.setMaxLength(CODE_ENTRY_CHARACTERS)
        self.setPlaceholderText("Friend's code")
        self.setStyleSheet(
            f"QLineEdit {{ background: {color('panel_alt').name()}; color: {color('text').name()};"
            f" selection-background-color: {color('accent_dark').name()}; padding: 0 4px; border-radius: 4px; }}"
        )
        self.hide()

    def _finish(self, code: str | None) -> None:
        if self.isVisible():
            self.hide()
            self.on_finished(code)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(self.text())
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._finish(None)


class FriendsModule(ModuleBlock):
    def __init__(self, fonts: Fonts, on_height_changed: Callable[[], None]) -> None:
        super().__init__("Friends", fonts)
        # Not told of its first size, worked out below while the app is still being put together
        self.on_height_changed: Callable[[], None] = lambda: None
        self.actions = FriendsActions()
        self.view = FriendsView()
        # Height of what is shown, and in landscape the height the modules share, inside the border
        self.lines_height = 1
        self.shared_height = 0
        # Clickable areas other than buttons: each person's rows (their code and name) and the user's own code
        self.person_areas: list[tuple[QRect, str, str]] = []
        self.code_area = QRect()
        self.hovered_area: QRect | None = None
        self.code_copied = False
        # How far the list is scrolled, the most it can be, and where it shows
        self.scroll = 0
        self.max_scroll = 0
        self.list_rect = QRect()
        self.list_items = range(0)
        # Buttons in the list scrolled partly out of view: drawn cut off, but not clickable
        self.clipped_buttons: list[PaintedButton] = []
        self.entry = CodeEntry(self, fonts)
        self.entry.on_finished = self._code_entered
        # What paintEvent draws: (kind, arguments), worked out by _layout
        self.items: list[tuple] = []
        self._layout()
        self.on_height_changed = on_height_changed

    def landscape_height(self) -> int:
        return self.content_top - 1 + self.lines_height

    def set_layout(self, landscape: bool, height: int = 0) -> None:
        shared_height = height if landscape else 0
        if shared_height != self.shared_height:
            # The list's room changes with the height
            self.shared_height = shared_height
            self._layout()

    def _fit(self) -> None:
        old_height = self.height()
        self.set_content_height(max(self.lines_height, self.shared_height - (self.content_top - 1)))
        if self.height() != old_height:
            self.on_height_changed()

    def show_view(self, view: FriendsView) -> None:
        if view == self.view:
            return
        if view.code != self.view.code:
            self.code_copied = False
        self.view = view
        self._layout()

    def _button(self, text: str, command: Callable[[], None], main: bool = False) -> PaintedButton:
        button = PaintedButton(
            text, command, self.fonts, BUTTON_PADX, BUTTON_PADY,
            text_color="accent" if main else "muted", fill="accent_dark" if main else "panel_alt",
        )
        button.enabled = not self.view.busy
        button.alpha = self.glass_alpha
        self.buttons.append(button)
        return button

    def _layout(self) -> None:
        """Work out where everything goes, from the top of the contents down, and how tall that makes the module"""
        fonts, view = self.fonts, self.view
        width = TODAY_PANEL_WIDTH
        left, right = SIDE, width - SIDE
        small_line = line_height(fonts.small) + 2 * LINE_PADDING
        self.buttons, self.items, self.person_areas, self.code_area = [], [], [], QRect()
        self.clipped_buttons, self.list_rect, self.list_items, self.max_scroll = [], QRect(), range(0), 0
        y = self.content_top

        def text_block(text: str, tone: str = "muted") -> None:
            nonlocal y
            for line in wrap(text, fonts.small, right - left):
                self.items.append(("text", left, y, line, tone, fonts.small))
                y += small_line

        def centred_button(text: str, command: Callable[[], None]) -> None:
            nonlocal y
            button = self._button(text, command, main=True)
            button.place((width - button.width) // 2, y)
            y += button.height

        if view.mode == "unavailable":
            text_block("Friends are coming soon.")
        elif view.mode == "signed_out":
            text_block("Sign in with Google to add friends and see each other's hours.")
            y += ROW_GAP
            centred_button("Sign in with Google", self.actions.sign_in)
        elif view.mode == "off":
            text_block("Add friends with a code to see each other's hours. Friends see your name, your hours, level and "
                       "streak, and the program you're drawing in.")
            y += ROW_GAP
            centred_button("Turn on friends", self.actions.turn_on)
        elif view.mode == "offline":
            text_block("You're offline. Friends don't see your hours change until you go online, from the menu next to your name.")
        elif view.mode == "loading":
            text_block("Connecting…")
        else:
            y = self._layout_friends(y, left, right, small_line)
        if view.message:
            y += ROW_GAP
            text_block(*view.message)
        self.lines_height = y - self.content_top + BOTTOM_PADDING
        self._fit()
        self.update()

    def _list_room(self, list_top: int, small_line: int, person_height: int) -> int:
        """How tall the list may be before it scrolls: some friends' rows in portrait; in landscape what is left of
        the height the modules share under the code row and any message, and at least one friend's row"""
        fonts, view = self.fonts, self.view
        if not self.shared_height:
            return PORTRAIT_LIST_ROWS * (person_height + ROW_GAP) - ROW_GAP
        message = ROW_GAP + len(wrap(view.message[0], fonts.small, TODAY_PANEL_WIDTH - 2 * SIDE)) * small_line if view.message else 0
        code_row = line_height(fonts.small) + 2 * BUTTON_PADY
        # The contents end at the shared height, the module's border taking a pixel below it
        room = self.shared_height + 1 - BOTTOM_PADDING - list_top - GROUP_GAP - code_row - message
        return max(person_height, room)

    def _layout_friends(self, y: int, left: int, right: int, small_line: int) -> int:
        fonts, view = self.fonts, self.view
        # The list is laid out whole, then moved up by how far it is scrolled and cut to the room it has
        list_top = y
        first_item, first_button, first_area = len(self.items), len(self.buttons), len(self.person_areas)
        for code, name in view.incoming:
            decline = self._button("Decline", lambda code=code: self.actions.decline(code))
            accept = self._button("Accept", lambda code=code: self.actions.accept(code), main=True)
            decline.place(right - decline.width, y)
            accept.place(decline.left - BUTTON_GAP - accept.width, y)
            middle = y + accept.height // 2
            text = fit_text(f"{name} wants to be friends", fonts.small, accept.left - BUTTON_GAP - left)
            self.items.append(("anchored", left, middle, "w", text, "text", fonts.small))
            y += accept.height + ROW_GAP
        if view.incoming:
            y += GROUP_GAP - ROW_GAP
        rank_width = text_width(fonts.small, "00") + 6
        name_line = line_height(fonts.normal) + LINE_PADDING
        for rank, (name, stats, presence, active, code) in enumerate(view.people, 1):
            top = y
            hours = f"{stats.get('two_weeks', 0):.1f} hrs past 2 weeks"
            hours_left = right - text_width(fonts.small, hours)
            middle = y + name_line // 2
            self.items.append(("anchored", left, middle, "w", str(rank), "muted", fonts.small))
            self.items.append(("anchored", right, middle, "e", hours, "text", fonts.small))
            name_left = left + rank_width
            # Beside the name: what they are drawing in, or that they are away
            label = PROGRAM_SHORT_NAMES.get(active, active) if active else "Away" if presence == "away" else ""
            dot_color = PRESENCE_COLORS.get(presence)
            label_room = (ACTIVE_DOT_SIZE + 6 if dot_color else 0) + (text_width(fonts.small, label) + 4 if label else 0)
            name_room = hours_left - 8 - name_left - label_room
            shown_name = fit_text(name, fonts.normal, name_room)
            self.items.append(("anchored", name_left, middle, "w", shown_name, "text", fonts.normal))
            if dot_color:
                dot_left = name_left + text_width(fonts.normal, shown_name) + 6
                self.items.append(("dot", dot_left, middle, dot_color))
                if label:
                    self.items.append(("anchored", dot_left + ACTIVE_DOT_SIZE + 4, middle, "w", label, dot_color, fonts.small))
            y += name_line
            total = f"{stats.get('total', 0):.1f} hrs total"
            details = f"Lv {stats.get('level', 0)} · {stats.get('streak', 0)} wk streak · {stats.get('today', 0):.1f}h today"
            details_room = right - text_width(fonts.small, total) - 8 - name_left
            middle = y + small_line // 2
            self.items.append(("anchored", name_left, middle, "w", fit_text(details, fonts.small, details_room), "muted", fonts.small))
            self.items.append(("anchored", right, middle, "e", total, "muted", fonts.small))
            y += small_line
            self.person_areas.append((QRect(left - 4, top - 2, right - left + 8, y - top + 4), code, name))
            y += ROW_GAP
        if not view.people and not view.incoming and not view.outgoing:
            for line in wrap("No friends yet. Share your code, or add a friend's.", fonts.small, right - left):
                self.items.append(("text", left, y, line, "muted", fonts.small))
                y += small_line
            y += ROW_GAP
        for code, name in view.outgoing:
            cancel = self._button("Cancel", lambda code=code: self.actions.cancel(code))
            cancel.place(right - cancel.width, y)
            text = fit_text(f"Waiting for {name} to accept", fonts.small, cancel.left - BUTTON_GAP - left)
            self.items.append(("anchored", left, y + cancel.height // 2, "w", text, "muted", fonts.small))
            y += cancel.height + ROW_GAP
        full = y - ROW_GAP - list_top
        person_height = line_height(fonts.normal) + LINE_PADDING + small_line
        visible = min(full, self._list_room(list_top, small_line, person_height))
        self.max_scroll = max(0, full - visible)
        self.scroll = max(0, min(self.scroll, self.max_scroll))
        self.list_rect = QRect(1, list_top, TODAY_PANEL_WIDTH - 2, visible)
        shift = self.scroll
        self.items[first_item:] = [item[:2] + (item[2] - shift,) + item[3:] for item in self.items[first_item:]]
        self.list_items = range(first_item, len(self.items))
        list_buttons = self.buttons[first_button:]
        del self.buttons[first_button:]
        for button in list_buttons:
            button.top -= shift
            if self.list_rect.contains(QRect(button.left, button.top, button.width, button.height)):
                self.buttons.append(button)
            else:
                self.clipped_buttons.append(button)
        self.person_areas[first_area:] = [
            (area.translated(0, -shift).intersected(self.list_rect), code, name) for area, code, name in self.person_areas[first_area:]
            if area.translated(0, -shift).intersects(self.list_rect)
        ]
        y = list_top + visible + GROUP_GAP
        # The bottom row: the user's own code, which a click copies, and the buttons
        turn_off = self._button("Turn off", self.actions.turn_off)
        add = self._button("Cancel" if self.entry.isVisible() else "Add friend", self._toggle_entry, main=not self.entry.isVisible())
        turn_off.place(right - turn_off.width, y)
        add.place(turn_off.left - BUTTON_GAP - add.width, y)
        middle = y + add.height // 2
        if self.entry.isVisible():
            self.entry.setGeometry(left, y, add.left - BUTTON_GAP - left, add.height)
        else:
            label = "Your code "
            code_text = "Copied" if self.code_copied else format_code(view.code)
            self.items.append(("anchored", left, middle, "w", label, "muted", fonts.small))
            code_left = left + text_width(fonts.small, label)
            self.items.append(("anchored", code_left, middle, "w", code_text, "text", fonts.bold))
            self.code_area = QRect(code_left - 4, y, text_width(fonts.bold, code_text) + 8, add.height)
        return y + add.height

    # ----- Clicks -----

    def _toggle_entry(self) -> None:
        if self.entry.isVisible():
            self.entry.on_finished = lambda _code: None
            self.entry.hide()
            self.entry.on_finished = self._code_entered
        else:
            self.entry.clear()
            self.entry.show()
            self.entry.setFocus()
        self._layout()

    def _code_entered(self, code: str | None) -> None:
        self._layout()
        if code and code.strip():
            self.actions.add(code.strip())

    def _area_at(self, point: QPoint) -> QRect | None:
        if self.code_area.contains(point):
            return self.code_area
        return next((area for area, _code, _name in self.person_areas if area.contains(point)), None)

    def interactive_at(self, point: QPoint) -> bool:
        return super().interactive_at(point) or self._area_at(point) is not None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and not any(button.contains(point) for button in self.buttons):
            if self.code_area.contains(point) and self.view.code:
                self.actions.copy_code(self.view.code)
                self.code_copied = True
                self._layout()
                return
            for area, code, name in self.person_areas:
                if area.contains(point):
                    self.actions.remove(code, name)
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        area = self._area_at(point)
        if area != self.hovered_area:
            self.hovered_area = area
            self.update()
        self.update_cursor(point, area is not None or any(button.contains(point) for button in self.buttons))

    def wheelEvent(self, event) -> None:
        if not self.max_scroll:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120
        self.scroll = max(0, min(self.max_scroll, round(self.scroll - steps * SCROLL_STEP)))
        self.hovered_area = None
        self._layout()
        event.accept()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.actions.looked_at()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self.hovered_area is not None:
            self.hovered_area = None
            self.update()
        if self.code_copied:
            self.code_copied = False
            self._layout()

    # ----- Drawing -----

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        self.paint_frame(painter)
        if self.hovered_area is not None:
            fill = color("calendar_blank")
            fill.setAlpha(self.glass_alpha)
            paint_hover_box(painter, QRectF(self.hovered_area), fill)
        for index, item in enumerate(self.items):
            painter.setClipRect(self.list_rect if index in self.list_items else self.rect())
            kind = item[0]
            if kind == "text":
                _kind, x, top, text, tone, font = item
                draw_text(painter, x, top + LINE_PADDING, text, color(tone), font)
            elif kind == "anchored":
                _kind, x, y, anchor, text, tone, font = item
                draw_anchored(painter, x, y, anchor, text, color(tone), font)
            elif kind == "dot":
                _kind, x, y, dot_color = item
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color(dot_color))
                painter.drawEllipse(QRectF(x, y - ACTIVE_DOT_SIZE / 2, ACTIVE_DOT_SIZE, ACTIVE_DOT_SIZE))
                painter.restore()
        painter.setClipRect(self.list_rect)
        for button in self.clipped_buttons:
            button.paint(painter)
        if self.max_scroll:
            # A thin bar at the list's right edge, showing how much of it is in view and where
            full = self.list_rect.height() + self.max_scroll
            bar = max(12, self.list_rect.height() * self.list_rect.height() // full)
            top = self.list_rect.top() + (self.list_rect.height() - bar) * self.scroll // self.max_scroll
            paint_hover_box(painter, QRectF(self.width() - 1 - SCROLL_BAR_WIDTH - 1, top, SCROLL_BAR_WIDTH, bar), self.border())
        painter.setClipping(False)
        for button in self.buttons:
            button.paint(painter)
        self.paint_dock_controls(painter)
        painter.end()
