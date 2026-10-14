"""The friends module: the people added by friend code, ranked by their hours over the past two weeks, with requests
waiting for an answer, and the user's own code. What it shows is handed to it as a FriendsView, see friends_sync"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

from app_config import EDGE_PADDING, LINE_PADDING, MODULE_MARGIN, TODAY_PANEL_WIDTH
from friends import format_code

from .header import NAME_MAX_LENGTH, fit_text
from .module import DOCK_CONTROL_SIZE, MODULE_TITLE_PADDING, ModuleBlock, PaintedButton, paint_hover_box, paint_dropdown_arrow, DROPDOWN_BUTTON_SIZE
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
# The red ring round a friend's level
LEVEL_RING_SIZE = 20
# Away friends have a small zzz after their name, this wide, which shows Away under the mouse
AWAY_MARK_WIDTH = 15
# The arrow at the end of a friend's name, which opens their menu: the square it takes, and its half-width
NAME_ARROW_SIZE = DROPDOWN_BUTTON_SIZE
# A friend's name: green drawing, blue online, dimmed blue away, grey offline, each lighter than the line under it
NAME_COLORS = {"drawing": "name_drawing", "online": "name_online", "away": "name_away", "offline": "name_offline"}
# Short names for the programs, which share a line with the person's name
# A section's heading counts its friends from this many up
SECTION_COUNT_FROM = 4
PROGRAM_SHORT_NAMES = {"Clip Studio Paint": "Clip Studio"}
# The list of requests and friends scrolls beyond this many friends' rows in portrait, and beyond the height the
# modules share in landscape; a turn of the mouse wheel moves it this far
PORTRAIT_LIST_ROWS = 4


def time_ago(seconds: float) -> str:
    """How long ago, in the largest whole unit: '5 minutes ago', '11 hours ago', '3 days ago', or 'just now'"""
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        count = int(seconds // size)
        if count:
            return f"{count} {unit}{'' if count == 1 else 's'} ago"
    return "just now"


def friend_lines(fonts: Fonts) -> tuple[int, int]:
    """The heights of a friend's name line and the line of details under it, snug together"""
    return line_height(fonts.account) - 2, line_height(fonts.small) + LINE_PADDING
SCROLL_STEP = 36
# The list's scroll bar, as the website's demo shows it in the browser: a rounded grey bar this wide, this far in from
# the border, with a small arrow in a space at each end; lighter under the mouse and while dragged
SCROLL_BAR_WIDTH = 6
SCROLL_BAR_INSET = 2
SCROLL_ARROW_SPACE = 10
SCROLL_BAR_MIN = 16
SCROLL_BAR_COLORS = {None: "#333333", "hover": "#4d4d4d", "pressed": "#5c5c5c"}
# At the right of the name strip: Copy code, then the friend requests icon while any wait, and the add friend icon, each
# icon in a square as the dock icon is, with this much between them; and how long a copied code stays shown
ICON_GAP = 2
COPY_PADDING = 4
CODE_SHOWN_MS = 4000
# The code field takes a code typed with or without its dash
CODE_ENTRY_CHARACTERS = 11


@dataclass
class FriendsView:
    """What the module shows. mode is one of: unavailable, signed_out, offline, loading, on"""

    mode: str = "unavailable"
    code: str = ""
    # The friends ranked, favourites first, as (name, stats, presence, program or None, code, favourite). Presence is
    # drawing, online, away or offline
    people: list[tuple[str, dict, str, str | None, str, bool]] = field(default_factory=list)
    incoming: list[tuple[str, str]] = field(default_factory=list)
    outgoing: list[tuple[str, str]] = field(default_factory=list)
    # A message under the list, and its colour
    message: tuple[str, str] | None = None
    busy: bool = False


@dataclass
class FriendsActions:
    sign_in: Callable[[], None] = lambda: None
    delete_data: Callable[[], None] = lambda: None
    add: Callable[[str], None] = lambda _code: None
    accept: Callable[[str], None] = lambda _code: None
    decline: Callable[[str], None] = lambda _code: None
    # A click on a friend's row opens their menu, given their code, the name shown and where to open it
    person_menu: Callable[[str, str, QPoint], None] = lambda _code, _name, _point: None
    cancel: Callable[[str], None] = lambda _code: None
    copy_code: Callable[[str], None] = lambda _code: None
    # The mouse came onto the module, the moment someone looks at their friends
    looked_at: Callable[[], None] = lambda: None


def paint_person_icon(painter: QPainter, rect: QRect, icon_color: QColor, background: QColor, plus: bool = False) -> None:
    """A person's head and shoulders, filled; with plus, smaller and to the left, a circled plus at their lower right,
    for adding a friend"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    size = 12
    x = rect.x() + (rect.width() - size) / 2 - (1.5 if plus else 0)
    y = rect.y() + (rect.height() - size) / 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(icon_color)
    painter.drawEllipse(QPointF(x + size * 0.5, y + size * 0.27), size * 0.24, size * 0.24)
    shoulders = QPainterPath()
    shoulders.moveTo(x + size * 0.06, y + size)
    shoulders.cubicTo(x + size * 0.06, y + size * 0.52, x + size * 0.94, y + size * 0.52, x + size * 0.94, y + size)
    shoulders.closeSubpath()
    painter.drawPath(shoulders)
    if plus:
        center = QPointF(x + size * 0.92, y + size * 0.78)
        # A ring of the background cut round the badge, so it stands apart from the shoulders
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.setBrush(background)
        painter.drawEllipse(center, 4.6, 4.6)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(icon_color, 1.2)
        painter.setPen(pen)
        painter.drawEllipse(center, 3.4, 3.4)
        painter.drawLine(QPointF(center.x() - 1.7, center.y()), QPointF(center.x() + 1.7, center.y()))
        painter.drawLine(QPointF(center.x(), center.y() - 1.7), QPointF(center.x(), center.y() + 1.7))
    painter.restore()


def friend_section(person: tuple) -> str:
    """The part of the list a friend is in: Favourites, whether online or not; In App while drawing; Online, or away;
    or Offline"""
    if person[5]:
        return "Favourites"
    return {"drawing": "In App", "offline": "Offline"}.get(person[2], "Online")


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


class TickButton(QWidget):
    """The green tick at the end of a field, which keeps what is typed as Enter does; under the mouse a faint rounded box
    shows behind it, as the app's other buttons do. It never takes the keyboard, so the field stays open"""

    def __init__(self, parent: QWidget, on_click: Callable[[], None]) -> None:
        super().__init__(parent)
        self.on_click = on_click
        self.hovered = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Add")

    def enterEvent(self, _event) -> None:
        self.hovered = True
        self.update()

    def leaveEvent(self, _event) -> None:
        self.hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.on_click()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        if self.hovered:
            paint_hover_box(painter, QRectF(self.rect()).adjusted(1, 1, -1, -1), color("border").lighter(130))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color("active_green"), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        x, y = (self.width() - 10) / 2, (self.height() - 8) / 2
        painter.drawPolyline([QPointF(x, y + 4), QPointF(x + 3.2, y + 7.2), QPointF(x + 10, y)])
        painter.end()


class CodeEntry(QLineEdit):
    """Where a friend's code, or a nickname, is typed. Enter keeps it, Escape or clicking elsewhere closes it"""

    def __init__(self, parent: QWidget, font, max_length: int = CODE_ENTRY_CHARACTERS, placeholder: str = "Friend's code") -> None:
        super().__init__(parent)
        self.on_finished: Callable[[str | None], None] = lambda _code: None
        self.setFont(font)
        self.setFrame(False)
        self.setMaxLength(max_length)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(
            f"QLineEdit {{ background: {color('panel_alt').name()}; color: {color('text').name()};"
            f" selection-background-color: {color('accent_dark').name()}; padding: 0 4px; border-radius: 4px; }}"
        )
        # A tick at the end, shown once there is something to keep
        self.confirm = TickButton(self, lambda: self._finish(self.text()))
        self.confirm.setVisible(False)
        self.textChanged.connect(lambda text: self.confirm.setVisible(bool(text.strip())))
        self.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # A square at the right end, with the text kept clear of it
        side = self.height()
        self.confirm.setGeometry(self.width() - side, 0, side, side)
        self.setTextMargins(0, 0, side - 4, 0)

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
        # The field's own right-click menu, for pasting a code, leaves it open
        if event.reason() != Qt.FocusReason.PopupFocusReason:
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
        # Each friend's rows, which open their menu
        self.person_areas: list[tuple[QRect, str, str]] = []
        self.hovered_area: QRect | None = None
        self.hovered_icon: str | None = None
        self.hovered_arrow: str | None = None
        # The code shows, copied, for a few seconds after Copy code is clicked
        self.code_shown = False
        # A word shown there for a few seconds instead, such as Request sent
        self.strip_note = ""
        self.code_timer = QTimer(self, singleShot=True, interval=CODE_SHOWN_MS, timeout=self._hide_code)
        # Whether the requests, sent and received, are shown above the friends; opened from their icon
        self.requests_open = False
        # How far the list is scrolled, the most it can be, and where it shows
        self.scroll = 0
        self.max_scroll = 0
        self.list_rect = QRect()
        self.list_items = range(0)
        # The part of the scroll bar under the mouse, see _scroll_part; and while its bar is dragged, where the press
        # was and how far the list was scrolled then
        self.hovered_scroll: str | None = None
        # The friend whose figures open when the double-click's button is let go, see mouseDoubleClickEvent
        self.details_pending: tuple[str, str] | None = None
        self.scroll_drag: tuple[int, int] | None = None
        # Buttons in the list scrolled partly out of view: drawn cut off, but not clickable
        self.clipped_buttons: list[PaintedButton] = []
        self.entry = CodeEntry(self, fonts.small)
        # The field a nickname is typed in, over the friend's name, and where each friend's name is
        self.nickname_entry = CodeEntry(self, fonts.account, NAME_MAX_LENGTH, "Nickname")
        self.name_rects: dict[str, QRect] = {}
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
            self.code_shown = False
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

    def _answer_button(self, text: str, command: Callable[[], None], text_color: str, fill: str) -> PaintedButton:
        button = PaintedButton(text, command, self.fonts, BUTTON_PADX, BUTTON_PADY, text_color=text_color, fill=fill, solid=True)
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
        self.buttons, self.items, self.person_areas = [], [], []
        self.person_details: dict[str, str] = {}
        self.clipped_buttons, self.list_rect, self.list_items, self.max_scroll = [], QRect(), range(0), 0
        # Where each away friend's zzz is, and each friend's menu arrow, as laid out before the list is scrolled
        self.away_areas: list[QRect] = []
        self.arrow_rects: list[tuple[QRect, str]] = []
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
            text_block("Sign in with Google to add friends and see each other's hours. Friends see your name, your hours, "
                       "level and streak, and the program you're drawing in.")
            y += ROW_GAP
            centred_button("Sign in with Google", self.actions.sign_in)
        elif view.mode == "offline":
            text_block("You're offline, so friends don't see your hours change. Go online from the menu next to your name.")
            y += ROW_GAP
            button = self._button("Delete my friends data", self.actions.delete_data)
            button.place((TODAY_PANEL_WIDTH - button.width) // 2, y)
            y += button.height
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
        # The contents end at the shared height, the module's border taking a pixel below it
        room = self.shared_height + 1 - BOTTOM_PADDING - list_top - message
        return max(person_height, room)

    def _layout_friends(self, y: int, left: int, right: int, small_line: int) -> int:
        fonts, view = self.fonts, self.view
        # The list is laid out whole, then moved up by how far it is scrolled and cut to the room it has
        list_top = y
        first_item, first_button, first_area = len(self.items), len(self.buttons), len(self.person_areas)
        # With none waiting, the requests icon goes, and the list it opened closes
        if not view.incoming:
            self.requests_open = False
        incoming = view.incoming if self.requests_open else []
        for code, name in incoming:
            decline = self._answer_button("Decline", lambda code=code: self.actions.decline(code), "red", "decline_fill")
            accept = self._answer_button("Accept", lambda code=code: self.actions.accept(code), "active_green", "accept_fill")
            decline.place(right - decline.width, y)
            accept.place(decline.left - BUTTON_GAP - accept.width, y)
            middle = y + accept.height // 2
            text = fit_text(f"{name} wants to be friends", fonts.small, accept.left - BUTTON_GAP - left)
            self.items.append(("anchored", left, middle, "w", text, "text", fonts.small))
            y += accept.height + ROW_GAP
        if incoming:
            y += GROUP_GAP - ROW_GAP
        # Each friend's level stands at the left of their name in a red ring, as the user's own level badge
        level_width = LEVEL_RING_SIZE + 7
        # A friend's two lines sit snug together: the name's line trimmed, the details' line with a little under it
        name_line, detail_line = friend_lines(fonts)
        self.name_rects = {}
        # Favourites first, then those drawing, the others online, and those offline or invisible, each under a heading;
        # a list of only friends online needs none
        sections = [friend_section(person) for person in view.people]
        only_online = set(sections) == {"Online"}
        for index, (name, stats, presence, active, code, favourite) in enumerate(view.people):
            section = sections[index]
            if index == 0 or sections[index - 1] != section:
                if not only_online:
                    if index:
                        y += GROUP_GAP - ROW_GAP
                    # A count only once a section holds more than a glance takes in, such as "Online (4)"
                    count = sections.count(section)
                    heading = f"{section} ({count})" if count >= SECTION_COUNT_FROM else section
                    self.items.append(("text", left, y, heading, "muted", fonts.small))
                    y += small_line
            top = y
            # Detailed figures appear in the dialog opened by double-clicking their name.
            two_weeks, total = float(stats.get("two_weeks", 0) or 0), float(stats.get("total", 0) or 0)
            # The past two weeks show on the row itself, so the details leave them out
            self.person_details[code] = f"{total:.1f} hrs total"
            since = stats.get("since")
            if isinstance(since, str) and len(since) == 10:
                try:
                    day = date.fromisoformat(since)
                    self.person_details[code] += chr(10) + f"Member since {day.day} {day.strftime('%b %Y')}"
                except ValueError:
                    pass
            # Their hours over the past two weeks, which the list is ranked by, at the right of their name
            hours = f"{two_weeks:.1f} hrs past 2 weeks"
            hours_left = right - text_width(fonts.small, hours)
            middle = y + name_line // 2
            self.items.append(("level", left + LEVEL_RING_SIZE / 2, middle, str(stats.get("level", 0))))
            self.items.append(("anchored", right, middle, "e", hours, "muted", fonts.small))
            name_left = left + level_width
            # Beside the name, a zzz while they are away; what they are drawing in goes with today's time, below
            label = PROGRAM_SHORT_NAMES.get(active, active) if active else ""
            label_room = 0
            if presence == "away":
                label_room += AWAY_MARK_WIDTH + 4
            label_room += NAME_ARROW_SIZE + 2
            name_room = hours_left - 8 - name_left - label_room
            shown_name = fit_text(name, fonts.account_bold, name_room)
            self.items.append(("anchored", name_left, middle, "w", shown_name, NAME_COLORS.get(presence, "text"), fonts.account_bold))
            self.name_rects[code] = QRect(name_left - 4, top, hours_left - 8 - name_left + 4, name_line)
            after_name = name_left + text_width(fonts.account_bold, shown_name)
            if presence == "away":
                self.items.append(("zzz", after_name + 5, middle))
                self.away_areas.append(QRect(after_name + 3, middle - 8, AWAY_MARK_WIDTH + 4, 14))
                after_name += AWAY_MARK_WIDTH + 4
            # Last, the arrow that opens their menu, as a click anywhere on their rows does
            self.arrow_rects.append((QRect(after_name + 2, middle - NAME_ARROW_SIZE // 2, NAME_ARROW_SIZE, NAME_ARROW_SIZE), code))
            y += name_line
            # Today's time, with the program while they are drawing in it, such as "Photoshop (1.1 hrs)", in its colour
            # Under an hour, in minutes, such as "23 min"
            today = float(stats.get("today", 0) or 0)
            amount = f"{today:.1f} hrs" if today >= 1 else f"{round(today * 60)} min"
            # Drawing: the program and today's time in green. Online: today's time in blue, or just Online with none yet
            if label:
                details, details_color = f"{label} ({amount})", "active_green"
            elif presence == "online":
                details, details_color = (f"{amount} today" if today > 0 else "Online"), "friend_online"
            elif presence == "away":
                details, details_color = "Away", "friend_away"
            elif presence == "offline" and today <= 0:
                # Nothing today: when they were last online, if known, or just Offline
                ago = stats.get("last_online_ago")
                details, details_color = (f"Last online {time_ago(ago)}" if ago is not None else "Offline"), "muted"
            else:
                details, details_color = f"{amount} today", "muted"
            details_room = right - name_left
            middle = y + detail_line // 2
            self.items.append(("anchored", name_left, middle, "w", fit_text(details, fonts.small, details_room), details_color, fonts.small))
            y += detail_line
            self.person_areas.append((QRect(left - 4, top - 2, right - left + 8, y - top + 4), code, name))
            y += ROW_GAP
        if not view.people:
            for line in wrap("No friends yet. Copy your code to share it, or add a friend's with the icon above.", fonts.small, right - left):
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
        person_height = sum(friend_lines(fonts))
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
        self._place_entry()
        return list_top + visible

    # ----- The name strip's controls -----

    def _copy_texts(self) -> list[tuple[str, str, object]]:
        """What Copy code shows, as pieces of (text, colour, font): the words, or for a while the code, copied"""
        if self.strip_note:
            return [(self.strip_note, "active_green", self.fonts.small)]
        if self.code_shown:
            return [(format_code(self.view.code), "text", self.fonts.bold), (" copied", "active_green", self.fonts.small)]
        return [("Copy code", "muted", self.fonts.small)]

    def strip_controls(self) -> dict[str, QRect]:
        """Copy code, the requests icon while any wait, and the add friend icon, from the right of the name strip,
        left of the dock icon while floating"""
        if self.view.mode != "on":
            return {}
        top = 1 + MODULE_TITLE_PADDING + (line_height(self.fonts.bold) - DOCK_CONTROL_SIZE) // 2
        dock = self.dock_rect()
        right = dock.left() - ICON_GAP if dock is not None else self.width() - 1 - MODULE_MARGIN + 4
        controls = {"add": QRect(right - DOCK_CONTROL_SIZE, top, DOCK_CONTROL_SIZE, DOCK_CONTROL_SIZE)}
        right -= DOCK_CONTROL_SIZE + ICON_GAP
        if self.view.incoming:
            controls["requests"] = QRect(right - DOCK_CONTROL_SIZE, top, DOCK_CONTROL_SIZE, DOCK_CONTROL_SIZE)
            right -= DOCK_CONTROL_SIZE + ICON_GAP
        if not self.entry.isVisible():
            width = sum(text_width(font, text) for text, _tone, font in self._copy_texts()) + 2 * COPY_PADDING
            controls["copy"] = QRect(right - 2 - width, top, width, DOCK_CONTROL_SIZE)
        return controls

    def _place_entry(self) -> None:
        """The code field, while adding a friend, fills the name strip between the module's name and the icons"""
        if not self.entry.isVisible():
            return
        controls = self.strip_controls()
        icons_left = min(rect.left() for rect in controls.values()) if controls else self.width() - MODULE_MARGIN
        left = 1 + MODULE_MARGIN + text_width(self.fonts.bold, self.title) + 10
        top = 1 + MODULE_TITLE_PADDING + (line_height(self.fonts.bold) - DOCK_CONTROL_SIZE) // 2
        self.entry.setGeometry(left, top, icons_left - 4 - left, DOCK_CONTROL_SIZE)

    def _icon_at(self, point: QPoint) -> str | None:
        return next((name for name, rect in self.strip_controls().items() if rect.contains(point)), None)

    def control_at(self, point: QPoint) -> str | None:
        # The strip's controls are clicked, not taken to move the module
        return None if self._icon_at(point) else super().control_at(point)

    def copy_code(self) -> None:
        """Copy the code to the clipboard, and show it, copied, for a few seconds"""
        if not self.view.code:
            return
        self.actions.copy_code(self.view.code)
        self.code_shown, self.strip_note = True, ""
        self.code_timer.start()
        self.update()

    def flash(self, note: str) -> None:
        """Show a word in Copy code's place for a few seconds, such as Request sent"""
        self.code_shown, self.strip_note = False, note
        self.code_timer.start()
        self.update()

    def _hide_code(self) -> None:
        self.code_shown, self.strip_note = False, ""
        self.update()

    def toggle_requests(self) -> None:
        self.requests_open = not self.requests_open
        self.scroll = 0
        self._layout()

    def _paint_icons(self, painter: QPainter) -> None:
        for name, rect in self.strip_controls().items():
            hovered = self.hovered_icon == name
            if name == "copy":
                if hovered:
                    fill = color("border")
                    fill.setAlpha(self.glass_alpha)
                    paint_hover_box(painter, QRectF(rect), fill)
                x = rect.left() + COPY_PADDING
                for text, tone, font in self._copy_texts():
                    draw_anchored(painter, x, rect.center().y() + 1, "w", text, color(tone), font)
                    x += text_width(font, text)
                continue
            open_now = (name == "requests" and self.requests_open) or (name == "add" and self.entry.isVisible())
            if hovered or open_now:
                fill = color("border")
                fill.setAlpha(self.glass_alpha)
                paint_hover_box(painter, QRectF(rect), fill)
            paint_person_icon(painter, rect, color("text" if open_now else "muted"), self.surface("background"), plus=name == "add")
            count = len(self.view.incoming)
            if name == "requests" and count:
                # How many requests wait, on a red badge at the icon's top right, as a phone shows notifications
                text = str(count) if count < 10 else "9+"
                width = max(11, text_width(self.fonts.tiny, text) + 5)
                badge = QRectF(rect.right() - width + 5, rect.top() - 3, width, 11)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color("notification"))
                painter.drawRoundedRect(badge, 5.5, 5.5)
                painter.restore()
                draw_anchored(painter, badge.center().x(), badge.center().y(), "center", text, color("text"), self.fonts.tiny)

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

    def edit_nickname(self, code: str, name: str, on_done: Callable[[str | None], None]) -> None:
        """Show the nickname field over this friend's name, holding it selected; on_done gets the nickname typed, or
        None when Escape drops it"""
        rect = self.name_rects.get(code)
        if rect is None or not self.list_rect.contains(rect):
            return
        entry = self.nickname_entry
        entry.on_finished = on_done
        entry.setText(name)
        entry.selectAll()
        entry.setGeometry(rect)
        entry.show()
        entry.setFocus()

    def _code_entered(self, code: str | None) -> None:
        self._layout()
        if code and code.strip():
            self.actions.add(code.strip())

    def _area_at(self, point: QPoint) -> QRect | None:
        """The friend's rows under the mouse, which a faint box shows behind"""
        return next((area for area, _code, _name in self.person_areas if area.contains(point)), None)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Anywhere on a friend's rows, as their highlight shows, but their menu arrow. Their figures open once the
        # button is let go: a window opening while it is held takes the release, and PS Focus would go on thinking it
        # held, missing the next click
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and self._arrow_at(point) is None and self._scroll_part(point) is None:
            for area, code, name in self.person_areas:
                if area.contains(point):
                    self.details_pending = (code, name)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def _open_details(self, code: str, name: str) -> None:
        from .friend_details import FriendDetails

        self.details_dialog = FriendDetails(self.window(), self.fonts, name, self.person_details.get(code, ""))
        self.details_dialog.show_centred_on(self.window())

    def _arrow_at(self, point: QPoint) -> str | None:
        """The friend whose menu arrow is here, if any"""
        return next((code for rect, code in self.arrow_rects if self._shown(rect).contains(point)), None)

    def interactive_at(self, point: QPoint) -> bool:
        # A friend's row moves the window like any other part; only their arrow is clicked
        return (super().interactive_at(point) or self._arrow_at(point) is not None or self._icon_at(point) is not None
                or self._scroll_part(point) is not None)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        scroll_part = self._scroll_part(point) if event.button() == Qt.MouseButton.LeftButton else None
        if scroll_part is not None:
            self._scroll_pressed(scroll_part, point)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and not any(button.contains(point) for button in self.buttons):
            icon = self._icon_at(point)
            if icon == "requests":
                self.toggle_requests()
                return
            if icon == "add":
                self._toggle_entry()
                return
            if icon == "copy":
                self.copy_code()
                return
        if not any(button.contains(point) for button in self.buttons):
            # A friend's menu opens from a right click on their rows, or a click on the arrow after their name
            arrow = self._arrow_at(point) if event.button() == Qt.MouseButton.LeftButton else None
            for area, code, name in self.person_areas:
                if (event.button() == Qt.MouseButton.RightButton and area.contains(point)) or code == arrow:
                    self.actions.person_menu(code, name, event.globalPosition().toPoint() + QPoint(2, 2))
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self.scroll_drag is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._scroll_dragged(point)
                return
            # The button is up but its release never came: the drag is over
            self.scroll_drag = None
        scroll_part = self._scroll_part(point)
        if scroll_part != self.hovered_scroll:
            self.hovered_scroll = scroll_part
            self.update()
        if scroll_part is not None:
            # The scroll bar is not part of a friend's row
            if self.hovered_area is not None or self.hovered_arrow is not None:
                self.hovered_area = self.hovered_arrow = None
                self.update()
            self.setToolTip("")
            self.update_cursor(point)
            return
        area = self._area_at(point)
        icon = self._icon_at(point)
        arrow = self._arrow_at(point)
        if area != self.hovered_area or icon != self.hovered_icon or arrow != self.hovered_arrow:
            self.hovered_area, self.hovered_icon, self.hovered_arrow = area, icon, arrow
            self.update()
        away = any(self._shown(rect).contains(point) for rect in self.away_areas)
        self.setToolTip("Away" if away else {"requests": "Friend requests", "add": "Add friend", "copy": "Copy your friend code"}.get(icon, ""))
        self.update_cursor(point, arrow is not None or icon is not None or any(button.contains(point) for button in self.buttons))

    def _shown(self, rect: QRect) -> QRect:
        """Where something laid out in the list is, as it is scrolled, cut to the list's room"""
        return rect.translated(0, -self.scroll).intersected(self.list_rect)

    def _scroll_track(self) -> QRect:
        """Where the scroll bar moves, between the arrows at the list's right edge"""
        left = self.width() - 1 - SCROLL_BAR_INSET - SCROLL_BAR_WIDTH
        return QRect(left, self.list_rect.top() + SCROLL_ARROW_SPACE, SCROLL_BAR_WIDTH, self.list_rect.height() - 2 * SCROLL_ARROW_SPACE)

    def _scroll_bar(self) -> QRect:
        """The bar, as long as the share of the list in view, as far down as the list is scrolled"""
        track = self._scroll_track()
        length = max(SCROLL_BAR_MIN, track.height() * self.list_rect.height() // (self.list_rect.height() + self.max_scroll))
        length = min(length, track.height())
        top = track.top() + (track.height() - length) * self.scroll // max(1, self.max_scroll)
        return QRect(track.left(), top, SCROLL_BAR_WIDTH, length)

    def _scroll_part(self, point: QPoint) -> str | None:
        """Which part of the scroll bar is here: "up" or "down", its arrows; "bar"; "above" or "below" it on the track"""
        if not self.max_scroll:
            return None
        left = self.width() - 1 - SCROLL_BAR_INSET - SCROLL_BAR_WIDTH - 2
        if not (left <= point.x() < self.width() - 1 and self.list_rect.top() <= point.y() <= self.list_rect.bottom()):
            return None
        track, bar = self._scroll_track(), self._scroll_bar()
        if point.y() < track.top():
            return "up"
        if point.y() > track.bottom():
            return "down"
        if point.y() < bar.top():
            return "above"
        return "below" if point.y() > bar.bottom() else "bar"

    def _scroll_to(self, scroll: float) -> None:
        before = self.scroll
        self.scroll = max(0, min(self.max_scroll, round(scroll)))
        if self.scroll != before:
            self.hovered_area = self.hovered_arrow = self.hovered_icon = None
            self._layout()
            # Present scrolling before returning, even on a layered Windows surface.
            self.repaint(self.list_rect)

    def _scroll_pressed(self, part: str, point: QPoint) -> None:
        """An arrow scrolls a step, the track either side of the bar a page; the bar is taken to drag"""
        page = max(SCROLL_STEP, self.list_rect.height() - SCROLL_STEP)
        if part == "bar":
            self.scroll_drag = (point.y(), self.scroll)
            self.update()
        else:
            self._scroll_to(self.scroll + {"up": -SCROLL_STEP, "down": SCROLL_STEP, "above": -page, "below": page}[part])

    def _scroll_dragged(self, point: QPoint) -> None:
        start_y, start_scroll = self.scroll_drag
        room = self._scroll_track().height() - self._scroll_bar().height()
        if room > 0:
            self._scroll_to(start_scroll + (point.y() - start_y) * self.max_scroll / room)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        pending, self.details_pending = self.details_pending, None
        if pending is not None and event.button() == Qt.MouseButton.LeftButton:
            self._open_details(*pending)
            event.accept()
            return
        if self.scroll_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self.scroll_drag = None
            self.hovered_scroll = self._scroll_part(event.position().toPoint())
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        if not self.max_scroll:
            event.ignore()
            return
        self._scroll_to(self.scroll - (event.pixelDelta().y() or event.angleDelta().y() / 120 * SCROLL_STEP))
        event.accept()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.actions.looked_at()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self.hovered_scroll is not None and self.scroll_drag is None:
            self.hovered_scroll = None
            self.update()
        if self.hovered_area is not None or self.hovered_icon is not None or self.hovered_arrow is not None:
            self.hovered_area = self.hovered_icon = self.hovered_arrow = None
            self.update()

    # ----- Drawing -----

    def _paint_scroll_bar(self, painter: QPainter) -> None:
        """The rounded bar, and a small arrow at each end of its track, each lighter under the mouse"""
        def tone(part: str) -> QColor:
            if part == "bar" and self.scroll_drag is not None:
                return QColor(SCROLL_BAR_COLORS["pressed"])
            return QColor(SCROLL_BAR_COLORS["hover" if self.hovered_scroll == part else None])

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tone("bar"))
        radius = SCROLL_BAR_WIDTH / 2
        painter.drawRoundedRect(QRectF(self._scroll_bar()), radius, radius)
        track = self._scroll_track()
        middle = track.left() + SCROLL_BAR_WIDTH / 2
        for part, tip, base in (("up", self.list_rect.top() + 3.5, self.list_rect.top() + 6.5),
                                ("down", self.list_rect.bottom() - 2.5, self.list_rect.bottom() - 5.5)):
            painter.setBrush(tone(part))
            path = QPainterPath(QPointF(middle, tip))
            path.lineTo(middle + 3, base)
            path.lineTo(middle - 3, base)
            path.closeSubpath()
            painter.drawPath(path)
        painter.restore()

    def _paint_name_arrow(self, painter: QPainter, rect: QRect, hovered: bool) -> None:
        """A small downward chevron in the muted grey; under the mouse a faint box shows behind it"""
        paint_dropdown_arrow(painter, QRectF(rect), hovered, self.glass_alpha)

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
            elif kind == "zzz":
                # Three z's of one size, each a little higher than the last
                _kind, x, y = item
                for offset, rise, font in ((0, 3, self.fonts.tiny), (5, 0, self.fonts.tiny), (10, -3, self.fonts.tiny)):
                    draw_anchored(painter, x + offset, y + rise, "w", "z", color("muted"), font)
            elif kind == "level":
                _kind, x, y, text = item
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(color("red"), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                radius = LEVEL_RING_SIZE / 2 - 0.75
                painter.drawEllipse(QPointF(x, y), radius, radius)
                painter.restore()
                draw_anchored(painter, x, y, "center", text, color("text"), self.fonts.caption)
        painter.setClipRect(self.list_rect)
        for rect, code in self.arrow_rects:
            self._paint_name_arrow(painter, rect.translated(0, -self.scroll), code == self.hovered_arrow)
        for button in self.clipped_buttons:
            button.paint(painter)
        if self.max_scroll:
            self._paint_scroll_bar(painter)
        painter.setClipping(False)
        for button in self.buttons:
            button.paint(painter)
        self._paint_icons(painter)
        self.paint_dock_controls(painter)
        painter.end()
