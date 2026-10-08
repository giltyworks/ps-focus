"""Dragging the program panels and modules into a new order, as in the Tk ModulesMixin: press on a block, move the
pointer a few pixels and the block is outlined in blue; it moves past the block under the pointer as the pointer
crosses that block's middle, and the order is kept when the button is let go

The modules also float, see docking: dragged by the grip at the right of their name they are put in order while the
pointer stays in the window, and float once it leaves; dragged by anything else they move the window, or as a
floating panel themselves, with whatever touches them. Docking moves the windows; this follows the mouse for it.
From a press until the button is let go the whole app's mouse events are watched, since a module dragged out of the
window changes to a window of its own under the pointer"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWindow
from PySide6.QtWidgets import QApplication, QWidget

# How far the pointer moves with the button down before a press becomes a drag
DRAG_DISTANCE = 5


class BlockDrag(QObject):
    def __init__(
        self, blocks: dict[str, QWidget], order: Callable[[], list[str]], on_reorder: Callable[[list[str]], None],
        on_finished: Callable[[], None], landscape: Callable[[], bool] = lambda: False, docking=None,
    ) -> None:
        super().__init__()
        self.blocks = blocks
        self.order = order
        self.on_reorder = on_reorder
        self.on_finished = on_finished
        self.landscape = landscape
        self.docking = docking
        self.candidate: str | None = None
        self.origin = QPoint()
        self.dragged: str | None = None
        self.order_changed = False
        self.watching = False
        for block in blocks.values():
            block.installEventFilter(self)

    def _name_of(self, widget: QObject) -> str | None:
        return next((name for name, block in self.blocks.items() if block is widget), None)

    def _watch(self, watching: bool) -> None:
        """Watch every mouse event in the app while a press lasts, wherever the module being dragged now is"""
        if watching != self.watching:
            self.watching = watching
            if watching:
                QApplication.instance().installEventFilter(self)
            else:
                QApplication.instance().removeEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        is_block = self._name_of(watched) is not None
        if kind == QEvent.Type.MouseButtonPress and is_block and event.button() == Qt.MouseButton.LeftButton:
            # Seen once by the block's own filter and once by the app's while watching; the first is enough
            if self.candidate is None:
                return self._pressed(watched, event)
            return False
        if kind == QEvent.Type.Hide:
            # Switching pages or hiding to the tray may end a drag without a mouse release; a module changing to a
            # window of its own does not
            if is_block and self.candidate is not None and self._name_of(watched) == self.candidate:
                if self.docking is None or not self.docking.reparenting:
                    self._released(None)
            return False
        # A move or release is taken at the window it reached, before any widget in it, or at a block given it directly
        if self.candidate is None or not (is_block or isinstance(watched, QWindow)):
            return False
        if kind == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
            return self._moved(event)
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            return self._released(event.globalPosition().toPoint())
        return False

    def _is_module(self, name: str) -> bool:
        return self.docking is not None and name in self.docking.app.modules

    def _pressed(self, block: QObject, event: QMouseEvent) -> bool:
        point = event.position().toPoint()
        name = self._name_of(block)
        control = block.control_at(point) if self._is_module(name) else None
        if control == "dock":
            self.docking.dock_module(name)
            return True
        # A press on a button drawn in a module is a click on that button, not the start of a drag
        if control is None and any(button.contains(point) for button in getattr(block, "buttons", ())):
            return False
        self.candidate = name
        self.origin = event.globalPosition().toPoint()
        self.dragged = None
        self.order_changed = False
        if self._is_module(name):
            self.docking.press(name, control == "grip", self.origin)
        self._watch(True)
        # The grip is the drag's alone; elsewhere the block still has the press, for a calendar day for instance
        return control == "grip"

    def _moved(self, event: QMouseEvent) -> bool:
        pointer = event.globalPosition().toPoint()
        if self.dragged is None:
            moved = pointer - self.origin
            if max(abs(moved.x()), abs(moved.y())) < DRAG_DISTANCE:
                return False
            self.dragged = self.candidate
            self._mark(True)
            QApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)
        source = self.dragged
        if self._is_module(source) and self.docking.drag(pointer):
            return True
        # Blocks pass one another by height when stacked, and by width side by side in landscape, where a column is
        # taken whole, the header standing on the panel under it included
        landscape = self.landscape()
        target, middle = None, 0
        for name, block in self.blocks.items():
            if name == source or not block.isVisible() or (self.docking is not None and self.docking.is_floating(name)):
                continue
            top_left = block.mapToGlobal(QPoint(0, 0))
            across = top_left.x() <= pointer.x() <= top_left.x() + block.width()
            down = top_left.y() <= pointer.y() <= top_left.y() + block.height()
            if across and (down or landscape):
                target = name
                middle = top_left.x() + block.width() // 2 if landscape else top_left.y() + block.height() // 2
                break
        if target is not None:
            order = list(self.order())
            source_index, target_index = order.index(source), order.index(target)
            insert_index = target_index + int((pointer.x() if landscape else pointer.y()) > middle)
            if source_index < insert_index:
                insert_index -= 1
            if source_index != insert_index:
                order.insert(insert_index, order.pop(source_index))
                self.order_changed = True
                self.on_reorder(order)
        # While dragging, the block's own handling of the pointer, such as the graph's readout, is left out
        return True

    def _mark(self, dragged: bool) -> None:
        block = self.blocks[self.dragged]
        block.border_color = "calendar_blue" if dragged else "border"
        block.update()

    def _released(self, pointer: QPoint | None) -> bool:
        was_dragged = self.dragged is not None
        self._watch(False)
        if was_dragged:
            self._mark(False)
            QApplication.restoreOverrideCursor()
        if self.docking is not None and self.candidate is not None and self._is_module(self.candidate):
            if was_dragged and pointer is not None:
                self.docking.release(pointer)
            else:
                self.docking.cancel()
        if self.order_changed:
            self.on_finished()
        self.candidate = self.dragged = None
        self.order_changed = False
        # A drag let go over a button is not a click on it
        return was_dragged
