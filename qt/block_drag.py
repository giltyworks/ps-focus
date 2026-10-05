"""Dragging the program panels and modules into a new order, as in the Tk ModulesMixin: press on a block, move the
pointer a few pixels and the block is outlined in blue; it moves past the block under the pointer as the pointer
crosses that block's middle, and the order is kept when the button is let go"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

# How far the pointer moves with the button down before a press becomes a drag
DRAG_DISTANCE = 5


class BlockDrag(QObject):
    def __init__(
        self, blocks: dict[str, QWidget], order: Callable[[], list[str]], on_reorder: Callable[[list[str]], None],
        on_finished: Callable[[], None],
    ) -> None:
        super().__init__()
        self.blocks = blocks
        self.order = order
        self.on_reorder = on_reorder
        self.on_finished = on_finished
        self.candidate: str | None = None
        self.origin = QPoint()
        self.dragged: str | None = None
        self.order_changed = False
        for block in blocks.values():
            block.installEventFilter(self)

    def _name_of(self, widget: QObject) -> str | None:
        return next((name for name, block in self.blocks.items() if block is widget), None)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._pressed(watched, event)
        elif kind == QEvent.Type.MouseMove and self.candidate is not None and event.buttons() & Qt.MouseButton.LeftButton:
            return self._moved(event)
        elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            return self._released()
        return False

    def _pressed(self, block: QObject, event: QMouseEvent) -> None:
        # A press on a button drawn in a module is a click on that button, not the start of a drag
        point = event.position().toPoint()
        if any(button.contains(point) for button in getattr(block, "buttons", ())):
            return
        self.candidate = self._name_of(block)
        self.origin = event.globalPosition().toPoint()
        self.dragged = None
        self.order_changed = False

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
        target, middle = None, 0
        for name, block in self.blocks.items():
            if name == source or not block.isVisible():
                continue
            top_left = block.mapToGlobal(QPoint(0, 0))
            if top_left.x() <= pointer.x() <= top_left.x() + block.width() and top_left.y() <= pointer.y() <= top_left.y() + block.height():
                target, middle = name, top_left.y() + block.height() // 2
                break
        if target is not None:
            order = list(self.order())
            source_index, target_index = order.index(source), order.index(target)
            insert_index = target_index + int(pointer.y() > middle)
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

    def _released(self) -> bool:
        was_dragged = self.dragged is not None
        if was_dragged:
            self._mark(False)
            QApplication.restoreOverrideCursor()
        if self.order_changed:
            self.on_finished()
        self.candidate = self.dragged = None
        self.order_changed = False
        # A drag let go over a button is not a click on it
        return was_dragged
