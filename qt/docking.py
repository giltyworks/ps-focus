"""Floating modules: the graph, calendar and stats can be dragged out of the window by their grip into windows of
their own, which snap to each other and to the window, move together while they touch, and dock back in. The rules
are those of the Tk version on the tk-floating-panels branch (ui_docking.py)

Positions are in Qt's screen units. A rectangle is (left, top, right, bottom), right and bottom just past the edge
"""

from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from .window import visible_frame

Rect = tuple[int, int, int, int]
# How near an edge has to come before it snaps to another
SNAP_DISTANCE = 20
# How far outside the window a module's grip may be dragged and still be put back in order rather than float
DOCK_MARGIN = 24
# Edges this close count as touching
TOUCH_TOLERANCE = 4
# Where the pointer holds a module just dragged out of the window, from its top left corner
GRAB_OFFSET = QPoint(30, 12)
# How long the window and panels have to stay still before their positions are saved
SAVE_DELAY_MS = 350


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
        return bool(ctypes.windll.user32.GetAsyncKeyState(1) & 0x8000)
    return bool(QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton)


class FloatingPanel(QWidget):
    """A window of its own holding one module: no title bar, the module's own name row standing in for it. Owned by
    the main window, so it has no taskbar button, stays above that window and minimizes with it"""

    def __init__(self, owner: QWidget, block: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.block = block
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


class Docking:
    """Floats, docks and moves the modules for the app. The app's BlockDrag passes on presses, drags and releases on
    the modules; Docking moves the windows. Docking also keeps panels touching the main window moving with it when it
    is moved by its title bar"""

    def __init__(self, app) -> None:
        self.app = app
        self.window = app.window
        self.floating: dict[str, FloatingPanel] = {}
        # Set while a module changes parent, so the drag does not take it being hidden for the end of the drag
        self.reparenting = False
        self._reset_drag()
        # The main window's visible frame when last seen, to tell how far it moved; and the panels moving with it
        # while the mouse button is held, fixed for the move so that it does not gather up panels it passes
        self.main_last_bounds = self.main_bounds()
        self.main_drag_members: set[str] | None = None
        self.moving_main = False
        self.save_timer = QTimer(singleShot=True, interval=SAVE_DELAY_MS, timeout=self.save_positions)

    def _reset_drag(self) -> None:
        self.source: str | None = None
        # "window": a docked module's name dragged, moving the main window and the panels touching it; "group": a
        # floating panel moved with the panels touching it; "detach": a floating panel moved by its grip, alone;
        # "grip": a docked module's grip, putting it in order inside the window until it is dragged out
        self.kind: str | None = None
        self.origin = QPoint()
        self.grab_offset = GRAB_OFFSET
        self.group_positions: dict[str, QPoint] = {}
        self.main_start = QPoint()
        self.moves_main = False
        # Where a panel moved by its grip started, for a swap; None for a module dragged out of the window
        self.swap_origin: QPoint | None = None
        # The slot a panel moved by its grip left, and the panels around it then, so the gap can be closed
        self.gap_source: Rect | None = None
        self.gap_panels: dict[str, Rect] = {}
        self.gap_closed = True

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

    def _main_offset(self) -> QPoint:
        """From the main window's visible frame to the position it is moved by"""
        left, top, _right, _bottom = self.main_bounds()
        return self.window.pos() - QPoint(left, top)

    def visible_panels(self, leave_out: set[str] = frozenset()) -> dict[str, Rect]:
        return {name: panel.bounds() for name, panel in self.floating.items() if panel.isVisible() and name not in leave_out}

    def dock_target(self, point: QPoint, margin: int = 0) -> bool:
        """Whether a point is over the main window, or within this many pixels of it"""
        if not self.window.isVisible() or self.window.isMinimized():
            return False
        area = self.window.geometry().adjusted(-margin, -margin, margin, margin)
        return area.contains(point)

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
            panel = FloatingPanel(self.window, block)
        finally:
            self.reparenting = False
        self.floating[name] = panel
        panel.move(top_left)
        panel.setVisible(self._panel_should_show(name))
        self.app._refresh_module(name)

    def dock_module(self, name: str, drop: QPoint | None = None, relayout: bool = True) -> None:
        """Put a floating module back in the window: where it was let go, between the blocks either side, or with no
        drop point in its place in the order"""
        panel = self.floating.get(name)
        if panel is None:
            return
        if drop is not None:
            self._insert_at(name, drop)
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

    def _insert_at(self, name: str, drop: QPoint) -> None:
        order = [key for key in self.app.block_order if key != name]
        landscape = self.app.landscape
        coordinate = drop.x() if landscape else drop.y()
        blocks = {**self.app.panels, **self.app.modules}
        insert = len(order)
        for index, key in enumerate(order):
            block = blocks[key]
            if key in self.floating or not block.isVisible():
                continue
            top_left = block.mapToGlobal(QPoint(0, 0))
            middle = top_left.x() + block.width() // 2 if landscape else top_left.y() + block.height() // 2
            if coordinate < middle:
                insert = index
                break
        order.insert(insert, name)
        self.app.block_order = order
        self.app.settings["block_order"] = order.copy()

    def dock_all(self) -> None:
        """Every module back in the window, as choosing Portrait or Landscape does"""
        for name in list(self.floating):
            self.dock_module(name, relayout=False)
        self._reset_drag()
        self.app.settings["floating_modules"] = {}

    def _panel_should_show(self, name: str) -> bool:
        return self.app.module_ticked[name] and self.window.isVisible() and not self.window.isMinimized()

    def sync_visibility(self, hidden: bool = False) -> None:
        """Floating panels go to the tray with the window, and a module unticked hides its panel"""
        for name, panel in self.floating.items():
            panel.setVisible(not hidden and self._panel_should_show(name))

    # Positions kept between runs

    def save_positions(self) -> None:
        self.save_timer.stop()
        settings = self.app.settings
        changed = False
        if self.window.isVisible() and not self.window.isMinimized():
            position = [self.window.x(), self.window.y()]
            if settings.get("main_window_position") != position:
                settings["main_window_position"] = position
                changed = True
        panels = {name: [panel.x(), panel.y()] for name, panel in self.floating.items()}
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
        panels = self.visible_panels(leave_out={self.source} if self.source else set())
        connected = attached_panels(previous, panels)
        if left_button_down():
            if self.main_drag_members is None:
                self.main_drag_members = connected
            connected = self.main_drag_members & panels.keys()
        else:
            self.main_drag_members = None
        for name in connected:
            panel = self.floating[name]
            panel.move(panel.x() + dx, panel.y() + dy)

    # Dragging

    def _raise_group(self, name: str | None) -> None:
        """Bring the panels moving together to the front together, the one pressed on last"""
        panels = self.visible_panels()
        if name is None or name not in panels:
            group = attached_panels(self.main_bounds(), panels) if self.window.isVisible() else set()
        else:
            group = {name} | attached_panels(panels[name], {key: rect for key, rect in panels.items() if key != name})
        for key in sorted(group - {name}):
            self.floating[key].raise_()
        if name in self.floating:
            self.floating[name].raise_()

    def press(self, name: str, on_grip: bool, point: QPoint) -> None:
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
            self.main_start = self.window.pos()
            panels = self.visible_panels()
            members = attached_panels(self.main_bounds(), panels) if self.window.isVisible() else set()
            self.group_positions = {key: self.floating[key].pos() for key in members}

    def _begin_group(self, name: str, detach: bool) -> None:
        panels = self.visible_panels()
        main_group = attached_panels(self.main_bounds(), panels) if self.window.isVisible() else set()
        self.moves_main = not detach and name in main_group
        self.main_start = self.window.pos()
        group = {name}
        if not detach:
            if self.moves_main:
                group |= main_group
            elif name in panels:
                group |= attached_panels(panels[name], {key: rect for key, rect in panels.items() if key != name})
        self.group_positions = {key: self.floating[key].pos() for key in group}

    def drag(self, point: QPoint) -> bool:
        """Follow the pointer; False leaves the drag to BlockDrag, to put a docked module in order by its grip"""
        if self.kind == "window":
            self._move_main_and_group(point - self.origin)
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
            self.group_positions = {self.source: self.floating[self.source].pos()}
        if self.kind in ("group", "detach") and self.source in self.floating:
            self._move_floating(point)
            return True
        return False

    def _move_main_and_group(self, delta: QPoint) -> None:
        self.moving_main = True
        try:
            self.window.move(self.main_start + delta)
            for key, start in self.group_positions.items():
                if key in self.floating:
                    self.floating[key].move(start + delta)
        finally:
            self.moving_main = False
        self.main_last_bounds = self.main_bounds()

    def _move_floating(self, point: QPoint) -> None:
        name = self.source
        target = point - self.grab_offset
        x, y = target.x(), target.y()
        if not self.moves_main and len(self.group_positions) <= 1:
            x, y = self._snap(name, x, y)
        if self.kind == "detach" and self.gap_source is not None and not self.gap_closed and self.swap_origin is not None:
            left, top, right, bottom = self.gap_source
            dx, dy = x - self.swap_origin.x(), y - self.swap_origin.y()
            # The slot is kept while any of the panel is still in it, and the snapping distance around it
            if (right + dx < left - SNAP_DISTANCE or left + dx > right + SNAP_DISTANCE
                    or bottom + dy < top - SNAP_DISTANCE or top + dy > bottom + SNAP_DISTANCE):
                self._close_gap()
        delta = QPoint(x, y) - self.group_positions[name]
        if self.moves_main:
            self._move_main_and_group(delta)
        else:
            for key, start in self.group_positions.items():
                if key in self.floating:
                    self.floating[key].move(start + delta)

    def _snap(self, name: str, x: int, y: int) -> tuple[int, int]:
        panel = self.floating[name]
        neighbours = list(self.visible_panels(leave_out=set(self.group_positions) | {name}).values())
        side_targets = []
        if self.window.isVisible() and not self.window.isMinimized():
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
        name, kind = self.source, self.kind
        if name in self.floating and kind in ("group", "detach"):
            if kind == "detach" and self.dock_target(point):
                self.dock_module(name, point)
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
        main_group = attached_panels(main, {**panels, "_removed": source}) if self.window.isVisible() else set()
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
            for member in component:
                panel = self.floating.get(member)
                if panel is not None:
                    panel.move(panel.x() + dx, panel.y() + dy)
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
