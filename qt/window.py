"""The PS Focus window: the header and module checkboxes, and the program panels and modules"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon, QPalette, QResizeEvent
from PySide6.QtWidgets import QWidget

from app_config import APP_NAME, COMPACT_BOTTOM_SPACE, MODULE_GAP, TODAY_PANEL_WIDTH, WINDOW_MARGIN, resource_path
from windows_startup import set_title_bar_colors_for_handle

from .theme import color

# Space between the header and the module checkboxes under it
HEADER_GAP = 2


def visible_frame(window_handle: int) -> wintypes.RECT | None:
    """The window's frame as drawn on screen, without the invisible resize border Windows pads it with"""
    if os.name != "nt":
        return None
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    dwmapi.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    frame = wintypes.RECT()
    # 9: DWMWA_EXTENDED_FRAME_BOUNDS
    if dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(window_handle), 9, ctypes.byref(frame), ctypes.sizeof(frame)) == 0 and frame.right > frame.left:
        return frame
    return None


class MainWindow(QWidget):
    """The header and module checkboxes over the blocks, which slide as the window gets smaller so the program panel
    holding the header, the anchor, stays in view; see the Tk ModulesMixin._scroll_blocks

    In portrait the blocks stand one under another below the header, each with a gap above it, and the window can be
    dragged shorter. In landscape they stand side by side, the header and checkboxes on top of the anchor panel, and
    the window can be dragged narrower. Everything is placed by hand, as the header moves between the two
    """

    def __init__(self, on_close: Callable[[], None], on_resized_by_user: Callable[[int], None] | None = None) -> None:
        super().__init__()
        self.on_close = on_close
        self.on_resized_by_user = on_resized_by_user
        self.setWindowTitle(APP_NAME)
        # Like the Tk window, there is nothing to maximize to: the window is as big as what it shows
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, color("background"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        # The blocks are placed in the container, which slides within the viewport
        self.viewport = QWidget(self)
        self.container = QWidget(self.viewport)
        self.blocks: list[QWidget] = []
        self.anchor: QWidget | None = None
        self.modules_shown = False
        self.landscape = False
        self.offset = 0
        # The width the app last gave the window in landscape, to tell a width the user dragged to from it
        self.requested_width = 0
        # Laid over the bottom of a window too short for its blocks, so they disappear behind a margin rather than
        # running right up to the edge, see the Tk ModulesMixin._update_clip_margin
        self.clip_margin = QWidget(self)
        self.clip_margin.setAutoFillBackground(True)
        self.clip_margin.hide()
        # Asking for the window's handle makes it now, so the title bar is dark from the first frame shown
        set_title_bar_colors_for_handle(int(self.winId()))

    def set_top(self, header: QWidget, controls: QWidget) -> None:
        """The header, and the module checkboxes under it"""
        self.header, self.controls = header, controls

    def show_blocks(
        self, blocks: list[QWidget], anchor: QWidget | None, modules_shown: bool, landscape: bool = False, width: int | None = None
    ) -> None:
        """Show these blocks in this order and hide any others. The anchor is the program panel kept in view as the
        window gets smaller; modules_shown, whether a module is among the blocks. In landscape the window is this
        wide, or with none given as wide as every block"""
        for block in self.blocks:
            if block not in blocks:
                block.hide()
        self.blocks, self.anchor, self.modules_shown, self.landscape = blocks, anchor, modules_shown, landscape
        self._lay_out()
        for block in blocks:
            block.show()
        self.refit(width)

    def reorder_blocks(self, blocks: list[QWidget]) -> None:
        """Show the same blocks in a new order, the window keeping its size"""
        self.blocks = blocks
        self._lay_out()
        self._slide()

    def _lay_out(self) -> None:
        """Put the header, checkboxes and blocks in place for the layout, their order and their sizes"""
        header, controls = self.header, self.controls
        top_height = self.top_height()
        if self.landscape:
            for widget in (header, controls, *self.blocks):
                if widget.parent() is not self.container:
                    widget.setParent(self.container)
            # The header and checkboxes stand first on their own when no program panel is shown to hold them
            units: list[QWidget | None] = list(self.blocks) if self.anchor in self.blocks else [None, *self.blocks]
            x = bottom = 0
            for unit in units:
                if unit is None or unit is self.anchor:
                    header.move(x, 0)
                    controls.move(x, header.height() + HEADER_GAP)
                    bottom = max(bottom, top_height)
                if unit is None:
                    width = TODAY_PANEL_WIDTH
                elif unit is self.anchor:
                    unit.move(x, top_height + MODULE_GAP)
                    width = unit.width()
                    bottom = max(bottom, unit.y() + unit.height())
                else:
                    unit.move(x, 0)
                    width = unit.width()
                    bottom = max(bottom, unit.height())
                x += width + MODULE_GAP
            self.container.resize(max(1, x - MODULE_GAP), bottom)
            self.viewport.move(WINDOW_MARGIN, 0)
        else:
            for widget in (header, controls):
                if widget.parent() is not self:
                    widget.setParent(self)
            header.move(WINDOW_MARGIN, 0)
            controls.move(WINDOW_MARGIN, header.height() + HEADER_GAP)
            top = 0
            for block in self.blocks:
                if block.parent() is not self.container:
                    block.setParent(self.container)
                top += MODULE_GAP
                block.move(0, top)
                top += block.height()
            self.container.resize(TODAY_PANEL_WIDTH, top)
            self.viewport.move(WINDOW_MARGIN, top_height)
        # Taken from one parent to another, a widget is hidden until shown again
        header.show()
        controls.show()

    def top_height(self) -> int:
        return self.header.height() + HEADER_GAP + self.controls.height()

    def full_size(self) -> tuple[int, int]:
        """Size of the window showing every block whole"""
        if self.landscape:
            return WINDOW_MARGIN + self.container.width(), self.container.height()
        content = self.container.height() if self.blocks else COMPACT_BOTTOM_SPACE
        return TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2, self.top_height() + content

    def compact_height(self) -> int:
        """Smallest height in portrait: the header and checkboxes, and the program panel holding the header, so it
        is never cut off; the other blocks slide out of view around it"""
        panel = MODULE_GAP + self.anchor.height() if self.anchor is not None and self.anchor in self.blocks else 0
        return self.top_height() + COMPACT_BOTTOM_SPACE + panel

    def refit(self, width: int | None = None) -> None:
        """Lay the blocks out again and size the window to all of them, after a block has come, gone, grown or
        shrunk. In portrait it can then be dragged shorter, down to its compact height; in landscape narrower, down
        to the width of a panel, and it is given this width if one is given and it is not wider than everything"""
        self._lay_out()
        full_width, full_height = self.full_size()
        if self.landscape:
            self.setMinimumSize(min(TODAY_PANEL_WIDTH, full_width), full_height)
            self.setMaximumSize(full_width, full_height)
            width = full_width if width is None else max(TODAY_PANEL_WIDTH, min(width, full_width))
            self.requested_width = width
            self._resize_on_screen(width, full_height)
        else:
            self.setMinimumSize(full_width, min(self.compact_height(), full_height))
            self.setMaximumSize(full_width, full_height)
            self._resize_on_screen(full_width, full_height)
        self._slide()

    def _resize_on_screen(self, width: int, height: int) -> None:
        """Resize keeping the window's left edge, and with it the header, in place; it then moves left as far as it
        must to stay on its screen"""
        old_width = self.width()
        self.resize(width, height)
        if self.isVisible() and width != old_width and self.screen() is not None:
            work = self.screen().availableGeometry()
            x = max(work.left(), min(self.x(), work.right() + 1 - self.frameGeometry().width()))
            if x != self.x():
                self.move(x, self.y())

    def _slide(self) -> None:
        """Shrinking first hides the blocks after the anchor panel behind the window's far edge; once the edge
        reaches that panel the blocks slide instead, hiding those before it under the header or off the left"""
        self.viewport.resize(max(1, self.width() - self.viewport.x()), max(1, self.height() - self.viewport.y()))
        anchored = self.anchor is not None and self.anchor in self.blocks
        if self.landscape:
            start, end = (self.anchor.x(), self.anchor.x() + self.anchor.width()) if anchored else (0, 0)
            offset = min(max(0, end - (self.width() - WINDOW_MARGIN)), start)
            position = (-offset, 0)
            self.clip_margin.hide()
        else:
            start, end = (self.anchor.y(), self.anchor.y() + self.anchor.height()) if anchored else (0, 0)
            room = self.height() - self.top_height() - COMPACT_BOTTOM_SPACE
            offset = min(max(0, end - room), max(0, start - MODULE_GAP))
            position = (0, -offset)
            clipped = self.modules_shown and self.height() < self.full_size()[1]
            self.clip_margin.setVisible(clipped)
            if clipped:
                self.clip_margin.setGeometry(0, self.height() - COMPACT_BOTTOM_SPACE, self.width(), COMPACT_BOTTOM_SPACE)
                self.clip_margin.raise_()
        self.offset = offset
        # Most resizes leave the blocks where they are; moving them only when they must keeps resizing smooth
        if (self.container.x(), self.container.y()) != position:
            self.container.move(*position)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._slide()
        # In landscape a width the app did not ask for is one the user dragged to, kept while blocks come and go
        if self.landscape and self.width() != self.requested_width and self.on_resized_by_user is not None:
            self.requested_width = self.width()
            self.on_resized_by_user(self.width())

    def place_top_right(self) -> None:
        """Put the window in the top right corner of its screen's work area, its visible frame flush with the corner"""
        work = self.screen().availableGeometry()
        frame = self.frameGeometry()
        self.move(work.right() + 1 - frame.width(), work.top())
        visible = visible_frame(int(self.winId()))
        if visible is not None:
            # Windows reports the handle's sizes in physical pixels; Qt places windows in its own units
            ratio = self.devicePixelRatio()
            shift_x = round((work.right() + 1) - visible.right / ratio)
            shift_y = round(work.top() - visible.top / ratio)
            self.move(self.x() + shift_x, self.y() + shift_y)

    def closeEvent(self, event: QCloseEvent) -> None:
        # The window's X hides the app to the tray, where it keeps counting
        event.ignore()
        self.on_close()
