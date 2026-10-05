"""The PS Focus window: the program panels and modules one under another"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon, QPalette
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
        self.blocks: list[QWidget] = []
        # Asking for the window's handle makes it now, so the title bar is dark from the first frame shown
        set_title_bar_colors_for_handle(int(self.winId()))

    def set_top(self, header: QWidget, controls: QWidget) -> None:
        """The header, and the module checkboxes under it, which head the window"""
        self.header, self.controls = header, controls

    def show_blocks(self, blocks: list[QWidget]) -> None:
        """Show these blocks one under another in this order, each with a gap above it, and hide any others"""
        for block in self.blocks:
            if block not in blocks:
                block.hide()
        while self.column.count():
            self.column.takeAt(0)
        self.column.addWidget(self.header)
        self.column.addSpacing(HEADER_GAP)
        self.column.addWidget(self.controls)
        for block in blocks:
            self.column.addSpacing(MODULE_GAP)
            self.column.addWidget(block)
            block.show()
        # Without blocks, the space the Tk window kept under the checkboxes
        self.column.addSpacing(0 if blocks else COMPACT_BOTTOM_SPACE)
        self.column.addStretch(1)
        self.blocks = blocks
        self.column.activate()
        self.setFixedSize(TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2, max(1, self.column.sizeHint().height()))

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
