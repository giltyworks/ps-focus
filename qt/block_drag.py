"""Dragging in the window and the floating panels, one rule throughout: a block's title rearranges, anything else moves

- A block's title, its name row, puts the block in a new order: pressed and moved a few pixels, the block is outlined
  in blue and passes the block under the pointer as the pointer crosses that block's middle, as in the Tk
  ModulesMixin. A block dragged by its title out of the window floats in a window of its own, see docking.
- Anywhere else that is not a button, link or checkbox moves the window, or the floating panel pressed on, together
  with every panel touching it.

From a press until the button is let go every mouse event in the app is watched, since a module dragged out of the
window changes to a window of its own under the pointer"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from .docking import FloatingPanel

# How far the pointer moves with the button down before a press becomes a drag
DRAG_DISTANCE = 5


class BlockDrag(QObject):
    def __init__(
        self, blocks: dict[str, QWidget], order: Callable[[], list[str]], on_reorder: Callable[[list[str]], None],
        on_finished: Callable[[], None], landscape: Callable[[], bool] = lambda: False, docking=None,
        draggable: Callable[[QWidget], bool] = lambda _widget: False,
    ) -> None:
        super().__init__()
        self.blocks = blocks
        self.order = order
        self.on_reorder = on_reorder
        self.on_finished = on_finished
        self.landscape = landscape
        self.docking = docking
        # Whether a press on this widget, one of the window's own rather than a block, may move the window
        self.draggable = draggable
        self.candidate: str | None = None
        # "reorder": a block's title, putting it in order; "move": the window or a floating panel moved by Docking,
        # which also handles a module's title, giving the drag back to "reorder" while the module stays in the window
        self.mode: str | None = None
        self.origin = QPoint()
        self.dragged = False
        self.order_changed = False
        # The widget holding the mouse while a drag lasts, see _moved
        self.grabber: QWidget | None = None
        QApplication.instance().installEventFilter(self)

    def _name_of(self, widget: QObject) -> str | None:
        return next((name for name, block in self.blocks.items() if block is widget), None)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            if self.mode is None and isinstance(watched, QWidget) and event.button() == Qt.MouseButton.LeftButton:
                return self._pressed(watched, event)
            return False
        if kind == QEvent.Type.Hide:
            # Switching pages or hiding to the tray may end a drag without a mouse release; a module changing to a
            # window of its own does not
            if self.mode is not None and self.candidate is not None and watched is self.blocks.get(self.candidate):
                if self.docking is None or not self.docking.reparenting:
                    self._released(None)
            return False
        if self.mode is None or kind not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            return False
        # Taken at whichever widget Qt gives it to, the module pressed on even after it moved to a window of its own.
        # Not at the window before it: Qt's window keeps track of the button there, which a release must reach. A
        # parent also seeing an event its child let through sees the same position, which changes nothing
        if not isinstance(watched, QWidget):
            return False
        if kind == QEvent.Type.MouseMove:
            if event.buttons() & Qt.MouseButton.LeftButton:
                return self._moved(event.globalPosition().toPoint())
            return False
        if event.button() == Qt.MouseButton.LeftButton:
            return self._released(event.globalPosition().toPoint())
        return False

    def _is_module(self, name: str | None) -> bool:
        """Whether Docking handles this block's drags: every block can float. Without Docking, as in the layout
        tests, a title only puts its block in order"""
        return name is not None and self.docking is not None and name in self.docking.app.blocks_by_name()

    def _pressed(self, widget: QWidget, event: QMouseEvent) -> bool:
        top = widget.window()
        name = self._name_of(widget)
        floating = isinstance(top, FloatingPanel)
        if name is None and not (floating and widget is top) and not self.draggable(widget):
            return False
        point = event.position().toPoint()
        control = widget.control_at(point) if name is not None and hasattr(widget, "control_at") else None
        if control == "dock":
            self.docking.dock_module(name)
            return True
        # Buttons, links, checkboxes and calendar days keep their clicks
        if control is None and hasattr(widget, "interactive_at") and widget.interactive_at(point):
            return False
        self.origin = event.globalPosition().toPoint()
        self.dragged = False
        self.order_changed = False
        self.candidate = name
        if control == "title":
            self.mode = "move" if self._is_module(name) else "reorder"
            if self.mode == "move":
                self.docking.press(name, True, self.origin)
            # The title is the drag's alone
            return True
        if self.docking is None:
            self.candidate = None
            return False
        self.mode = "move"
        self.docking.press(top.block_name if floating else None, False, self.origin)
        # The widget still has the press, for anything it does with one
        return False

    def _moved(self, pointer: QPoint) -> bool:
        if not self.dragged:
            moved = pointer - self.origin
            if max(abs(moved.x()), abs(moved.y())) < DRAG_DISTANCE:
                return False
            self.dragged = True
            # Qt follows a press through the widget pressed on; a module changing to a window of its own mid-drag
            # would lose it. The main window, which never changes, holds the mouse until the drag ends instead
            if self.docking is not None and self.docking.window.isVisible():
                self.grabber = self.docking.window
                self.grabber.grabMouse()
            if self.candidate is not None and (self.mode == "reorder" or self.docking.kind == "title"):
                self._mark(True)
                QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
        if self.mode == "move":
            if self.docking.drag(pointer):
                return True
            if self.docking.kind != "title":
                return True
        self._reorder(pointer)
        # While dragging, the block's own handling of the pointer, such as the graph's readout, is left out
        return True

    def _reorder(self, pointer: QPoint) -> None:
        source = self.candidate
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

    def _mark(self, dragged: bool) -> None:
        block = self.blocks[self.candidate]
        block.border_color = "calendar_blue" if dragged else "border"
        block.update()

    def _released(self, pointer: QPoint | None) -> bool:
        was_dragged = self.dragged
        if self.grabber is not None:
            self.grabber.releaseMouse()
            self.grabber = None
        marked = was_dragged and self.candidate is not None and self.blocks[self.candidate].border_color != "border"
        if marked:
            self._mark(False)
            QApplication.restoreOverrideCursor()
        if self.mode == "move":
            if was_dragged and pointer is not None:
                # Windows may merge the last moves into the release, so the drag first catches up with where it ended
                self.docking.drag(pointer)
                self.docking.release(pointer)
            else:
                self.docking.cancel()
        if self.order_changed:
            self.on_finished()
        self.candidate = self.mode = None
        self.dragged = self.order_changed = False
        if self.docking is not None:
            # Solid while dragged, the windows now go see-through again if the mouse is off them
            self.docking.update_glass()
        # A drag let go over a button is not a click on it
        return was_dragged
