"""Floating modules: the graph, calendar and stats can be dragged out of the window by their grip into windows of
their own, which snap to each other and to the window, move together while they touch, and dock back in. The rules
are those of the Tk version on the tk-floating-panels branch (ui_docking.py), with these changes the user asked for:
anything not a control moves the window or panel pressed on, with all that touches it; a lone panel let go over the
window, or just past its far end (below it, or right of it in landscape), docks there, a blue marker showing where

Positions are in Qt's screen units. A rectangle is (left, top, right, bottom), right and bottom just past the edge
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app_config import MODULE_GAP, TODAY_PANEL_WIDTH, WINDOW_MARGIN

from .theme import color
from .window import visible_frame

Rect = tuple[int, int, int, int]
# How near an edge has to come before it snaps to another
SNAP_DISTANCE = 20
# How far outside the window a module's grip may be dragged and still be put back in order rather than float
DOCK_MARGIN = 24
# How far past the window's far end, below it or in landscape right of it, a panel let go still docks
DOCK_ZONE = 40
# Edges this close count as touching
TOUCH_TOLERANCE = 4
# Where the pointer holds a module just dragged out of the window, from its top left corner
GRAB_OFFSET = QPoint(30, 12)
# How long the window and panels have to stay still before their positions are saved
SAVE_DELAY_MS = 350
# The marker showing where a panel will dock: its thickness, and how see-through the panel is meanwhile
MARKER_THICKNESS = 4
DOCKING_OPACITY = 0.7

if os.name == "nt":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.BeginDeferWindowPos.argtypes = [ctypes.c_int]
    _user32.BeginDeferWindowPos.restype = ctypes.c_void_p
    _user32.DeferWindowPos.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [ctypes.c_uint]
    _user32.DeferWindowPos.restype = ctypes.c_void_p
    _user32.EndDeferWindowPos.argtypes = [ctypes.c_void_p]
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
# SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
_MOVE_ONLY = 0x0001 | 0x0004 | 0x0010


def snap_position(
    x: int, y: int, width: int, height: int, neighbours: list[Rect], distance: int = SNAP_DISTANCE, side_targets: list[Rect] = ()
) -> tuple[int, int]:
    """Snap to the nearest touching edge with either end aligned. A side target, a block inside the window, is snapped
    to only beside the window, level with the block's top or bottom"""
    candidates = []
    for left, top, right, bottom in neighbours:
        if y <= bottom + distance and y + height >= top - distance:
            for edge in (left - width, right):
                if abs(edge - x) <= distance:
                    candidates.extend((edge, anchor) for anchor in (top, bottom - height))
        if x <= right + distance and x + width >= left - distance:
            for edge in (top - height, bottom):
                if abs(edge - y) <= distance:
                    candidates.extend((anchor, edge) for anchor in (left, right - width))
    for left, top, right, bottom in side_targets:
        if y > bottom + distance or y + height < top - distance:
            continue
        for edge in (left - width, right):
            if abs(edge - x) <= distance:
                candidates.extend((edge, anchor) for anchor in (top, bottom - height))
    return min(candidates, key=lambda point: abs(point[0] - x) + abs(point[1] - y)) if candidates else (x, y)


def attached_panels(start: Rect, panels: dict[str, Rect], tolerance: int = TOUCH_TOLERANCE) -> set[str]:
    """The whole chain of panels touching this rectangle, edge to edge, directly or through one another"""
    connected: set[str] = set()
    frontier = [start]
    while frontier:
        left, top, right, bottom = frontier.pop()
        for name, (pl, pt, pr, pb) in panels.items():
            if name in connected:
                continue
            vertical_overlap = min(bottom, pb) - max(top, pt) > 0
            horizontal_overlap = min(right, pr) - max(left, pl) > 0
            if ((vertical_overlap and min(abs(right - pl), abs(left - pr)) <= tolerance)
                    or (horizontal_overlap and min(abs(bottom - pt), abs(top - pb)) <= tolerance)):
                connected.add(name)
                frontier.append((pl, pt, pr, pb))
    return connected


def overlaps(a: Rect, b: Rect) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def overlap_area(a: Rect, b: Rect) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def left_button_down() -> bool:
    """Whether the left mouse button is held, even while Windows itself is moving the window by its title bar"""
    if os.name == "nt":
        return bool(_user32.GetAsyncKeyState(1) & 0x8000)
    return bool(QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton)


class WindowMover:
    """Moves several windows the same distance at once. Moved one after another they would visibly trail each other;
    Windows' deferred positioning moves them all in a single step. Distances are worked out from where each window
    started, in its own screen's pixels, so rounding cannot build up over a long drag"""

    def __init__(self) -> None:
        self.entries: list[tuple[QWidget, QPoint, tuple[int, int] | None, float]] = []

    def begin(self, windows: list[QWidget]) -> None:
        native = os.name == "nt" and QGuiApplication.platformName() == "windows"
        self.entries = []
        for window in windows:
            start = None
            if native:
                rect = wintypes.RECT()
                if _user32.GetWindowRect(int(window.winId()), ctypes.byref(rect)):
                    start = (rect.left, rect.top)
            self.entries.append((window, window.pos(), start, window.devicePixelRatio()))

    def move(self, delta: QPoint) -> None:
        if self.entries and all(start is not None for _window, _position, start, _ratio in self.entries):
            batch = _user32.BeginDeferWindowPos(len(self.entries))
            for window, _position, (x, y), ratio in self.entries:
                if not batch:
                    break
                batch = _user32.DeferWindowPos(
                    batch, int(window.winId()), None, x + round(delta.x() * ratio), y + round(delta.y() * ratio), 0, 0, _MOVE_ONLY
                )
            if batch and _user32.EndDeferWindowPos(batch):
                return
        for window, position, _start, _ratio in self.entries:
            window.move(position + delta)


class FloatingPanel(QWidget):
    """A window of its own holding one module: no title bar, the module's own name row standing in for it. Owned by
    the main window, so it has no taskbar button, stays above that window and minimizes with it"""

    def __init__(self, owner: QWidget, name: str, block: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.block_name = name
        self.block = block
        # Coming up under the pointer mid-drag, it leaves the keyboard where it was
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle(f"PS Focus - {block.title}")
        block.setParent(self)
        block.move(0, 0)
        block.show()
        self.setFixedSize(block.size())
        # The module grows and shrinks, such as the stats gaining a line or the calendar a week, and the window with it
        block.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.block and event.type() == QEvent.Type.Resize:
            self.setFixedSize(self.block.size())
        return False

    def bounds(self) -> Rect:
        return (self.x(), self.y(), self.x() + self.width(), self.y() + self.height())

    def release_block(self) -> QWidget:
        """Hand the module back, hidden and without a parent, for the window to take in again"""
        block = self.block
        block.removeEventFilter(self)
        block.hide()
        block.setParent(None)
        return block


class DockMarker(QWidget):
    """The blue bar in the window where a panel being dragged will dock, between the blocks it will go between"""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color("calendar_blue"))
        radius = min(self.width(), self.height()) / 2
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)
        painter.end()


class Docking:
    """Floats, docks and moves the modules for the app. The app's BlockDrag passes on presses, drags and releases;
    Docking moves the windows. It also keeps panels touching the main window moving with it when Windows moves it by
    its title bar"""

    def __init__(self, app) -> None:
        self.app = app
        self.window = app.window
        self.floating: dict[str, FloatingPanel] = {}
        # Set while a module changes parent, so the drag does not take it being hidden for the end of the drag
        self.reparenting = False
        self.mover = WindowMover()
        self.marker = DockMarker(self.window)
        self._reset_drag()
        # The main window's visible frame when last seen, to tell how far it moved; and the panels moving with it
        # while the mouse button is held, fixed for the move so that it does not gather up panels it passes
        self.main_last_bounds = self.main_bounds()
        self.main_drag_members: set[str] | None = None
        self.moving_main = False
        self.save_timer = QTimer(singleShot=True, interval=SAVE_DELAY_MS, timeout=self.save_positions)

    def _reset_drag(self) -> None:
        self.source: str | None = None
        # "window": the main window moved, with the panels touching it; "group": a floating panel moved with the
        # panels touching it; "detach": a floating panel moved by its grip, alone; "grip": a docked module's grip,
        # putting it in order inside the window until it is dragged out
        self.kind: str | None = None
        self.origin = QPoint()
        self.grab_offset = GRAB_OFFSET
        self.group_positions: dict[str, QPoint] = {}
        self.moves_main = False
        # Where a panel moved by its grip started, for a swap; None for a module dragged out of the window
        self.swap_origin: QPoint | None = None
        # The slot a panel moved by its grip left, and the panels around it then, so the gap can be closed
        self.gap_source: Rect | None = None
        self.gap_panels: dict[str, Rect] = {}
        self.gap_closed = True
        # Where in the window's order the panel being dragged would dock if let go now, or None
        self.dock_slot: int | None = None
        self._show_dock_slot(None)

    # Where things are

    def is_floating(self, name: str) -> bool:
        return name in self.floating

    def main_bounds(self) -> Rect:
        """The main window's frame as drawn, without Windows' invisible resize border"""
        frame = self.window.frameGeometry()
        visible = visible_frame(int(self.window.winId())) if self.window.isVisible() else None
        if visible is not None:
            ratio = self.window.devicePixelRatio()
            return (round(visible.left / ratio), round(visible.top / ratio), round(visible.right / ratio), round(visible.bottom / ratio))
        return (frame.left(), frame.top(), frame.left() + frame.width(), frame.top() + frame.height())

    def visible_panels(self, leave_out: set[str] = frozenset()) -> dict[str, Rect]:
        return {name: panel.bounds() for name, panel in self.floating.items() if panel is not None and panel.isVisible() and name not in leave_out}

    def _main_shown(self) -> bool:
        return self.window.isVisible() and not self.window.isMinimized()

    def dock_target(self, point: QPoint, margin: int = 0) -> bool:
        """Whether a point is over the main window, or within this many pixels of it"""
        if not self._main_shown():
            return False
        return self.window.geometry().adjusted(-margin, -margin, margin, margin).contains(point)

    # Floating and docking

    def float_module(self, name: str, top_left: QPoint) -> None:
        if name in self.floating:
            return
        block = self.app.modules[name]
        # Out of the window's blocks first, then into a window of its own
        self.floating[name] = None  # type: ignore[assignment]
        self.reparenting = True
        try:
            self.app._arrange_blocks()
            block.floating = True
            block.set_layout(False, 0)
            panel = FloatingPanel(self.window, name, block)
        finally:
            self.reparenting = False
        self.floating[name] = panel
        panel.move(top_left)
        panel.setVisible(self._panel_should_show(name))
        self.app._refresh_module(name)

    def dock_module(self, name: str, slot: int | None = None, relayout: bool = True) -> None:
        """Put a floating module back in the window: before the slot'th block shown there, or after them all, or with
        no slot given in its place in the order"""
        panel = self.floating.get(name)
        if panel is None:
            return
        if slot is not None:
            self._insert_at_slot(name, slot)
        self.reparenting = True
        try:
            del self.floating[name]
            block = panel.release_block()
            block.floating = False
            panel.deleteLater()
            if relayout:
                self.app._arrange_blocks()
                self.app._refresh_module(name)
        finally:
            self.reparenting = False
        if relayout:
            self.save_positions()

    def _shown_names(self) -> list[str]:
        """The blocks shown in the window, in order"""
        return [name for name in self.app.block_order if self.app._block_shown(name)]

    def _insert_at_slot(self, name: str, slot: int) -> None:
        shown = [key for key in self._shown_names() if key != name]
        order = [key for key in self.app.block_order if key != name]
        if slot < len(shown):
            index = order.index(shown[slot])
        else:
            index = order.index(shown[-1]) + 1 if shown else len(order)
        order.insert(index, name)
        self.app.block_order = order
        self.app.settings["block_order"] = order.copy()

    def dock_all(self) -> None:
        """Every module back in the window, as choosing Portrait or Landscape does"""
        for name in list(self.floating):
            self.dock_module(name, relayout=False)
        self._reset_drag()
        self.app.settings["floating_modules"] = {}

    def _panel_should_show(self, name: str) -> bool:
        return self.app.module_ticked[name] and self._main_shown()

    def sync_visibility(self, hidden: bool = False) -> None:
        """Floating panels go to the tray with the window, and a module unticked hides its panel"""
        for name, panel in self.floating.items():
            if panel is not None:
                panel.setVisible(not hidden and self._panel_should_show(name))

    # Positions kept between runs

    def save_positions(self) -> None:
        self.save_timer.stop()
        settings = self.app.settings
        changed = False
        if self._main_shown():
            position = [self.window.x(), self.window.y()]
            if settings.get("main_window_position") != position:
                settings["main_window_position"] = position
                changed = True
        panels = {name: [panel.x(), panel.y()] for name, panel in self.floating.items() if panel is not None}
        if settings.get("floating_modules") != panels:
            settings["floating_modules"] = panels
            changed = True
        if changed:
            self.app._save_settings()

    def restore(self) -> None:
        """Put the window where it was left, or with no saved place in the top right corner; then float the modules
        that were floating. A place on a screen no longer connected comes back onto one"""
        position = self.app.settings.get("main_window_position")
        if isinstance(position, list) and len(position) == 2 and all(type(value) is int for value in position):
            point = QPoint(*position)
            screen = QGuiApplication.screenAt(point + QPoint(40, 10)) or QGuiApplication.primaryScreen()
            work = screen.availableGeometry()
            frame = self.window.frameGeometry()
            x = max(work.left(), min(point.x(), work.right() + 1 - frame.width()))
            y = max(work.top(), min(point.y(), work.bottom() + 1 - min(frame.height(), work.height())))
            self.window.move(x, y)
        else:
            self.window.place_top_right()
        self.main_last_bounds = self.main_bounds()
        saved = self.app.settings.get("floating_modules")
        if isinstance(saved, dict):
            for name, place in saved.items():
                if name not in self.app.modules or not (isinstance(place, list) and len(place) == 2 and all(type(v) is int for v in place)):
                    continue
                point = QPoint(*place)
                if QGuiApplication.screenAt(point) is None:
                    point = self.window.pos() + QPoint(30, 30)
                self.float_module(name, point)
        self.sync_visibility()

    def main_moved(self) -> None:
        """The main window moved: by its title bar, the panels touching it go with it; moved by a drag here, they are
        already being moved"""
        current = self.main_bounds()
        previous, self.main_last_bounds = self.main_last_bounds, current
        if self.window.isVisible():
            self.save_timer.start()
        if self.moving_main or not self.floating:
            return
        dx, dy = current[0] - previous[0], current[1] - previous[1]
        if not (dx or dy):
            return
        panels = self.visible_panels()
        connected = attached_panels(previous, panels)
        if left_button_down():
            if self.main_drag_members is None:
                self.main_drag_members = connected
            connected = self.main_drag_members & panels.keys()
        else:
            self.main_drag_members = None
        if connected:
            mover = WindowMover()
            mover.begin([self.floating[name] for name in connected])
            mover.move(QPoint(dx, dy))

    # Dragging

    def _raise_group(self, name: str | None) -> None:
        """Bring the panels moving together to the front together, the one pressed on last"""
        panels = self.visible_panels()
        if name is None or name not in panels:
            group = attached_panels(self.main_bounds(), panels) if self._main_shown() else set()
        else:
            group = {name} | attached_panels(panels[name], {key: rect for key, rect in panels.items() if key != name})
        for key in sorted(group - {name}):
            self.floating[key].raise_()
        if name in panels:
            self.floating[name].raise_()

    def press(self, name: str | None, on_grip: bool, point: QPoint) -> None:
        """A press on a block's grip, or anywhere else in the window (name None) or a floating panel"""
        self._reset_drag()
        self.main_drag_members = None
        self.source = name
        self.origin = point
        self._raise_group(name if name in self.floating else None)
        floating = name in self.floating
        if on_grip and floating:
            panel = self.floating[name]
            self.kind = "detach"
            self.grab_offset = point - panel.pos()
            self.swap_origin = panel.pos()
            self.gap_source = panel.bounds()
            self.gap_panels = self.visible_panels(leave_out={name})
            self.gap_closed = False
            self._begin_group(name, detach=True)
        elif on_grip:
            self.kind = "grip"
        elif floating:
            self.kind = "group"
            self.grab_offset = point - self.floating[name].pos()
            self._begin_group(name, detach=False)
        else:
            self.kind = "window"
            self.source = None
            members = attached_panels(self.main_bounds(), self.visible_panels()) if self._main_shown() else set()
            self.group_positions = {key: self.floating[key].pos() for key in members}
            self.mover.begin([self.window] + [self.floating[key] for key in sorted(members)])

    def _begin_group(self, name: str, detach: bool) -> None:
        panels = self.visible_panels()
        main_group = attached_panels(self.main_bounds(), panels) if self._main_shown() else set()
        self.moves_main = not detach and name in main_group
        group = {name}
        if not detach:
            if self.moves_main:
                group |= main_group
            elif name in panels:
                group |= attached_panels(panels[name], {key: rect for key, rect in panels.items() if key != name})
        self.group_positions = {key: self.floating[key].pos() for key in group}
        self.mover.begin(([self.window] if self.moves_main else []) + [self.floating[key] for key in sorted(group)])

    def drag(self, point: QPoint) -> bool:
        """Follow the pointer; False leaves the drag to BlockDrag, to put a docked module in order by its grip"""
        if self.kind == "window":
            self._move_together(point - self.origin, moves_main=True)
            return True
        if self.kind == "grip":
            if self.dock_target(point, margin=DOCK_MARGIN):
                return False
            # Dragged out of the window: it floats under the pointer, and is moved alone from then on
            self.float_module(self.source, point - GRAB_OFFSET)
            self.kind = "detach"
            self.grab_offset = GRAB_OFFSET
            self.swap_origin = None
            self.moves_main = False
            panel = self.floating[self.source]
            self.group_positions = {self.source: panel.pos()}
            self.mover.begin([panel])
        if self.kind in ("group", "detach") and self.source in self.floating:
            self._move_floating(point)
            return True
        return False

    def _move_together(self, delta: QPoint, moves_main: bool) -> None:
        self.moving_main = moves_main
        try:
            self.mover.move(delta)
        finally:
            self.moving_main = False
        if moves_main:
            self.main_last_bounds = self.main_bounds()

    def _can_dock(self) -> bool:
        """A panel docks only when moved alone"""
        return self.kind == "detach" or (self.kind == "group" and not self.moves_main and len(self.group_positions) == 1)

    def _move_floating(self, point: QPoint) -> None:
        name = self.source
        panel = self.floating[name]
        target = point - self.grab_offset
        x, y = target.x(), target.y()
        slot = self._dock_slot_at(point, (x, y, x + panel.width(), y + panel.height())) if self._can_dock() else None
        # Over the window, or just past its far end, the panel docks rather than snaps
        if slot is None and not self.moves_main and len(self.group_positions) <= 1:
            x, y = self._snap(name, x, y)
        self._show_dock_slot(slot)
        if self.kind == "detach" and self.gap_source is not None and not self.gap_closed and self.swap_origin is not None:
            left, top, right, bottom = self.gap_source
            dx, dy = x - self.swap_origin.x(), y - self.swap_origin.y()
            # The slot is kept while any of the panel is still in it, and the snapping distance around it
            if (right + dx < left - SNAP_DISTANCE or left + dx > right + SNAP_DISTANCE
                    or bottom + dy < top - SNAP_DISTANCE or top + dy > bottom + SNAP_DISTANCE):
                self._close_gap()
        self._move_together(QPoint(x, y) - self.group_positions[name], self.moves_main)

    def _dock_slot_at(self, point: QPoint, rect: Rect) -> int | None:
        """Where a panel let go now would dock: before the slot'th block shown in the window, or after them all;
        None when it would not dock. It docks when the pointer is over the window, or when the panel's near edge
        lies just past the window's far end: its bottom, or in landscape its right edge"""
        if not self._main_shown():
            return None
        names = self._shown_names()
        if self.dock_target(point):
            if self.app.settings_shown:
                return len(names)
            landscape = self.app.landscape
            for index, name in enumerate(names):
                block = self.app.blocks_by_name()[name]
                top_left = block.mapToGlobal(QPoint(0, 0))
                middle = top_left.x() + block.width() // 2 if landscape else top_left.y() + block.height() // 2
                if (point.x() if landscape else point.y()) < middle:
                    return index
            return len(names)
        main_left, main_top, main_right, main_bottom = self.main_bounds()
        left, top, right, bottom = rect
        if self.app.landscape:
            beside = min(bottom, main_bottom) - max(top, main_top) > min(bottom - top, main_bottom - main_top) // 2
            if beside and main_right - SNAP_DISTANCE <= left <= main_right + DOCK_ZONE:
                return len(names)
        else:
            below = min(right, main_right) - max(left, main_left) > min(right - left, main_right - main_left) // 2
            if below and main_bottom - SNAP_DISTANCE <= top <= main_bottom + DOCK_ZONE:
                return len(names)
        return None

    def _show_dock_slot(self, slot: int | None) -> None:
        """Show the blue marker where the panel will dock, and the panel see-through meanwhile"""
        if slot == self.dock_slot and (slot is None) == (not self.marker.isVisible()):
            return
        self.dock_slot = slot
        panel = self.floating.get(self.source) if self.source else None
        if panel is not None:
            panel.setWindowOpacity(1.0 if slot is None else DOCKING_OPACITY)
        if slot is None or self.app.settings_shown:
            self.marker.hide()
            return
        window = self.window
        blocks = [self.app.blocks_by_name()[name] for name in self._shown_names()]
        thickness, half_gap = MARKER_THICKNESS, MODULE_GAP // 2
        if self.app.landscape:
            if slot < len(blocks):
                x = blocks[slot].mapTo(window, QPoint(0, 0)).x() - half_gap
            elif blocks:
                last = blocks[-1]
                x = last.mapTo(window, QPoint(last.width(), 0)).x() + half_gap
            else:
                x = WINDOW_MARGIN + TODAY_PANEL_WIDTH + half_gap
            x = max(0, min(x - thickness // 2, window.width() - thickness))
            self.marker.setGeometry(x, 0, thickness, window.height())
        else:
            if slot < len(blocks):
                y = blocks[slot].mapTo(window, QPoint(0, 0)).y() - half_gap
            elif blocks:
                last = blocks[-1]
                y = last.mapTo(window, QPoint(0, last.height())).y() + half_gap
            else:
                y = window.top_height() + half_gap
            y = max(0, min(y - thickness // 2, window.height() - thickness))
            self.marker.setGeometry(WINDOW_MARGIN, y, TODAY_PANEL_WIDTH, thickness)
        self.marker.raise_()
        self.marker.show()

    def _snap(self, name: str, x: int, y: int) -> tuple[int, int]:
        panel = self.floating[name]
        neighbours = list(self.visible_panels(leave_out=set(self.group_positions) | {name}).values())
        side_targets = []
        if self._main_shown():
            main = self.main_bounds()
            neighbours.append(main)
            # Beside the window, a panel also lines up with the top or bottom of each block in it
            for block in self.app._shown_blocks():
                if not block.isVisible():
                    continue
                block_top = block.mapToGlobal(QPoint(0, 0)).y()
                block_bottom = block_top + block.height()
                if main[1] <= block_top < main[3]:
                    side_targets.append((main[0], block_top, main[2], min(block_bottom, main[3])))
        return snap_position(x, y, panel.width(), panel.height(), neighbours, side_targets=side_targets)

    def release(self, point: QPoint) -> None:
        name, kind, slot = self.source, self.kind, self.dock_slot
        self._show_dock_slot(None)
        if name in self.floating and kind in ("group", "detach"):
            if slot is not None:
                self.dock_module(name, slot)
            else:
                self._resolve_overlap(name)
                self.save_positions()
        elif kind == "window":
            self.save_positions()
        self._reset_drag()

    def cancel(self) -> None:
        self._reset_drag()

    def _close_gap(self) -> None:
        """Slide the panels left behind into the slot the dragged panel left, so the group closes up"""
        self.gap_closed = True
        left, top, right, bottom = source = self.gap_source
        panels = self.gap_panels
        remaining = attached_panels(source, panels)
        main = self.main_bounds()
        main_group = attached_panels(main, {**panels, "_removed": source}) if self._main_shown() else set()
        if "_removed" in main_group:
            anchored = attached_panels(main, panels)
        else:
            # A row or column apart from the window keeps its first panel where it is
            leading = [key for key in remaining if panels[key][2] <= left + TOUCH_TOLERANCE or panels[key][3] <= top + TOUCH_TOLERANCE]
            anchor = min(leading, key=lambda key: (panels[key][1], panels[key][0])) if leading else None
            anchored = ({anchor} | attached_panels(panels[anchor], panels)) if anchor else set()
        pending = remaining - anchored
        anchors = [panels[key] for key in anchored]
        if "_removed" in main_group:
            anchors.append(main)
        fill_left, fill_top, fill_right, fill_bottom = left, top, right, bottom
        for al, at, ar, ab in anchors:
            if min(bottom, ab) > max(top, at):
                if abs(ar - left) <= TOUCH_TOLERANCE:
                    fill_left = ar
                if abs(al - right) <= TOUCH_TOLERANCE:
                    fill_right = al
            if min(right, ar) > max(left, al):
                if abs(ab - top) <= TOUCH_TOLERANCE:
                    fill_top = ab
                if abs(at - bottom) <= TOUCH_TOLERANCE:
                    fill_bottom = at
        while pending:
            key = min(pending, key=lambda key: (panels[key][1], panels[key][0]))
            component = ({key} | attached_panels(panels[key], {k: panels[k] for k in pending})) & pending
            # The edge of this branch that met the slot moves to the slot's far side
            dx = dy = 0
            for member in component:
                pl, pt, pr, pb = panels[member]
                if min(bottom, pb) > max(top, pt):
                    if abs(pl - right) <= TOUCH_TOLERANCE:
                        dx = fill_left - pl
                        break
                    if abs(pr - left) <= TOUCH_TOLERANCE:
                        dx = fill_right - pr
                        break
                if min(right, pr) > max(left, pl):
                    if abs(pt - bottom) <= TOUCH_TOLERANCE:
                        dy = fill_top - pt
                        break
                    if abs(pb - top) <= TOUCH_TOLERANCE:
                        dy = fill_bottom - pb
                        break
            moved = [self.floating[member] for member in component if member in self.floating]
            if moved and (dx or dy):
                mover = WindowMover()
                mover.begin(moved)
                mover.move(QPoint(dx, dy))
            pending -= component

    def _resolve_overlap(self, name: str) -> None:
        """Let go over another floating panel by its grip, a panel swaps places with it; then panels a larger one now
        covers move aside to the nearest clear edge, the dragged group staying as it is"""
        moving = (set(self.group_positions) or {name}) & set(self.floating)
        source = self.floating[name]
        bounds = source.bounds()
        targets = [(key, panel) for key, panel in self.floating.items()
                   if key not in moving and panel.isVisible() and overlaps(bounds, panel.bounds())]
        if targets and self.kind == "detach":
            key, target = max(targets, key=lambda item: overlap_area(bounds, item[1].bounds()))
            destination = target.pos()
            if self.swap_origin is None:
                # A module dragged out of the window swaps its place in the window too
                order = self.app.block_order
                a, b = order.index(name), order.index(key)
                order[a], order[b] = order[b], order[a]
                self.app.settings["block_order"] = order.copy()
                self.dock_module(key)
            else:
                target.move(self.swap_origin)
            source.move(destination)
        occupied = [self.floating[key].bounds() for key in moving if key in self.floating]
        for key, panel in self.floating.items():
            if key in moving or not panel.isVisible():
                continue
            left, top, right, bottom = panel.bounds()
            width, height = right - left, bottom - top
            while any(overlaps((left, top, left + width, top + height), rect) for rect in occupied):
                left = max(rect[2] for rect in occupied if overlaps((left, top, left + width, top + height), rect))
            panel.move(left, top)
            occupied.append((left, top, left + width, top + height))
