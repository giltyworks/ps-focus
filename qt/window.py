"""The PS Focus window: the program panels and modules one under another"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon, QPalette, QResizeEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

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


class BlockViewport(QWidget):
    """Shows the blocks one under another, each with a gap above it, and slides them up as the window gets shorter
    so the program panel holding the header stays in view; see the Tk ModulesMixin._scroll_blocks"""

    def __init__(self) -> None:
        super().__init__()
        self.container = QWidget(self)
        self.blocks: list[QWidget] = []
        self.offset = 0

    def set_blocks(self, blocks: list[QWidget]) -> None:
        for block in self.blocks:
            if block not in blocks:
                block.hide()
        self.blocks = blocks
        self.lay_out()
        for block in blocks:
            block.show()

    def lay_out(self) -> None:
        """Put the blocks in place for their order and heights"""
        top = 0
        for block in self.blocks:
            if block.parent() is not self.container:
                block.setParent(self.container)
            top += MODULE_GAP
            block.move(0, top)
            top += block.height()
        self.container.resize(TODAY_PANEL_WIDTH, top)

    def content_height(self) -> int:
        return self.container.height()

    def span(self, block: QWidget | None) -> tuple[int, int]:
        """Where a block starts and ends among the blocks, or nothing for none"""
        if block is None or block not in self.blocks:
            return 0, 0
        return block.y(), block.y() + block.height()

    def slide(self, room: int, anchor: QWidget | None) -> None:
        """Shrinking first hides the blocks after the anchor panel behind the window's bottom edge; once the edge
        reaches that panel the blocks slide up instead, hiding those before it under the header"""
        start, end = self.span(anchor)
        offset = min(max(0, end - room), max(0, start - MODULE_GAP))
        # Most resizes leave the blocks where they are; moving them only when they must keeps resizing smooth
        if offset != self.offset or self.container.y() != -offset:
            self.offset = offset
            self.container.move(0, -offset)


class MainWindow(QWidget):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__()
        self.on_close = on_close
        self.setWindowTitle(APP_NAME)
        # Like the Tk window, there is nothing to maximize to: the window is as big as what it shows
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, color("background"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(WINDOW_MARGIN, 0, WINDOW_MARGIN, 0)
        self.column.setSpacing(0)
        self.viewport = BlockViewport()
        self.anchor: QWidget | None = None
        self.modules_shown = False
        # Laid over the bottom of a window too short for its blocks, so they disappear behind a margin rather than
        # running right up to the edge, see the Tk ModulesMixin._update_clip_margin
        self.clip_margin = QWidget(self)
        self.clip_margin.setAutoFillBackground(True)
        self.clip_margin.hide()
        # Asking for the window's handle makes it now, so the title bar is dark from the first frame shown
        set_title_bar_colors_for_handle(int(self.winId()))

    def set_top(self, header: QWidget, controls: QWidget) -> None:
        """The header, and the module checkboxes under it, which head the window"""
        self.header, self.controls = header, controls
        self.column.addWidget(header)
        self.column.addSpacing(HEADER_GAP)
        self.column.addWidget(controls)
        self.column.addWidget(self.viewport, 1)
        self.bottom_space = self.column.count()
        self.column.addSpacing(0)

    def show_blocks(self, blocks: list[QWidget], anchor: QWidget | None, modules_shown: bool) -> None:
        """Show these blocks one under another in this order and hide any others. The anchor is the program panel
        kept in view as the window gets shorter; modules_shown, whether a module is among the blocks"""
        self.anchor, self.modules_shown = anchor, modules_shown
        self.viewport.set_blocks(blocks)
        # Without blocks, the space the Tk window kept under the checkboxes
        spacer = self.column.itemAt(self.bottom_space).spacerItem()
        spacer.changeSize(0, 0 if blocks else COMPACT_BOTTOM_SPACE)
        self.viewport.setVisible(bool(blocks))
        self.refit()

    def reorder_blocks(self, blocks: list[QWidget]) -> None:
        """Show the same blocks in a new order, the window keeping its size"""
        self.viewport.set_blocks(blocks)
        self._update_slide()

    def top_height(self) -> int:
        return self.header.height() + HEADER_GAP + self.controls.height()

    def full_height(self) -> int:
        """Height of the window showing every block whole"""
        blocks = self.viewport.blocks
        return self.top_height() + (self.viewport.content_height() if blocks else COMPACT_BOTTOM_SPACE)

    def compact_height(self) -> int:
        """Smallest height: the header and checkboxes, and the program panel holding the header, so it is never cut
        off; the other blocks slide out of view around it"""
        panel = MODULE_GAP + self.anchor.height() if self.anchor is not None and self.anchor in self.viewport.blocks else 0
        return self.top_height() + COMPACT_BOTTOM_SPACE + panel

    def refit(self) -> None:
        """Lay the blocks out again and make the window as tall as all of them, after a block has come, gone, grown
        or shrunk. It can then be dragged shorter, down to its compact height"""
        self.viewport.lay_out()
        full = self.full_height()
        width = TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2
        self.setMinimumSize(width, min(self.compact_height(), full))
        self.setMaximumSize(width, full)
        self.resize(width, full)
        self._update_slide()

    def _update_slide(self) -> None:
        if not self.viewport.blocks:
            return
        self.viewport.slide(self.height() - self.top_height() - COMPACT_BOTTOM_SPACE, self.anchor)
        clipped = self.modules_shown and self.height() < self.full_height()
        self.clip_margin.setVisible(clipped)
        if clipped:
            self.clip_margin.setGeometry(0, self.height() - COMPACT_BOTTOM_SPACE, self.width(), COMPACT_BOTTOM_SPACE)
            self.clip_margin.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_slide()

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
