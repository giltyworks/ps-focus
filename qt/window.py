"""The PS Focus window: the header and module checkboxes, and the program panels and modules"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QCloseEvent, QIcon, QMoveEvent, QPainter, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QWidget

from app_config import APP_NAME, COMPACT_BOTTOM_SPACE, MODULE_GAP, TODAY_PANEL_WIDTH, WINDOW_MARGIN, resource_path

from .module import OUTLINE_MIN_ALPHA
from .theme import Fonts, color
from .title_bar import GRIP_SIZE, TITLE_BAR_HEIGHT, EdgeGrip, TitleBar



# A normal window's styles, which Windows' snapping and Win + arrow keys, and minimising from the taskbar, look for:
# WS_CAPTION, WS_THICKFRAME, WS_MINIMIZEBOX and WS_SYSMENU. The frame they would draw is never drawn, see nativeEvent
WINDOW_STYLES = 0x00C00000 | 0x00040000 | 0x00020000 | 0x00080000
# WS_POPUP, which Qt gives a window without a frame, as for a menu; Windows' shortcuts such as Win + Down leave such
# windows alone, so it is taken off
WS_POPUP = 0x80000000
WM_NCCALCSIZE = 0x0083
# Windows' resizing by the edge strip has ended
WM_EXITSIZEMOVE = 0x0232


def _keep_window_behaviour(window: QWidget) -> None:
    """Give the frameless window a normal window's styles back, so Windows treats it as one"""
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    handle = wintypes.HWND(int(window.winId()))
    # GWL_STYLE, then SWP_FRAMECHANGED, neither moving, sizing nor activating it, so the new styles take effect
    style = (user32.GetWindowLongW(handle, -16) & 0xFFFFFFFF & ~WS_POPUP) | WINDOW_STYLES
    user32.SetWindowLongW(handle, -16, ctypes.c_long(style - (1 << 32) if style >= 1 << 31 else style).value)
    user32.SetWindowPos(handle, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)

def let_compositor_blend(window: QWidget) -> None:
    """Have Windows' desktop compositor blend the window's see-through background with what is behind it, as it does
    for an ordinary window. Qt turns any frameless window with a see-through background into a layered one, which
    Windows redraws as a whole new picture at each size while the edge is dragged, so resizing stutters; the classic
    empty blur region (DWM_BB_ENABLE | DWM_BB_BLURREGION, a region of nothing) gives the same blending without that"""
    if os.name != "nt":
        return

    class BlurBehind(ctypes.Structure):
        _fields_ = [("flags", wintypes.DWORD), ("enable", wintypes.BOOL), ("region", wintypes.HRGN), ("transition", wintypes.BOOL)]

    gdi32 = ctypes.windll.gdi32
    gdi32.CreateRectRgn.restype = wintypes.HRGN
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmEnableBlurBehindWindow.argtypes = [wintypes.HWND, ctypes.POINTER(BlurBehind)]
    empty_region = gdi32.CreateRectRgn(0, 0, -1, -1)
    behind = BlurBehind(0x1 | 0x2, True, empty_region, False)
    dwmapi.DwmEnableBlurBehindWindow(wintypes.HWND(int(window.winId())), ctypes.byref(behind))
    gdi32.DeleteObject(empty_region)


# Space between the header and the module checkboxes under it
HEADER_GAP = 2


def set_topmost(window: QWidget, on: bool) -> None:
    """Keep the window above other programs' windows, or let them cover it again. A window not yet shown is left
    alone, since asking for its handle early makes Windows stop showing PS Focus's small redraws; a floating panel
    applies the setting as it shows, see FloatingPanel.showEvent"""
    if os.name != "nt" or not window.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
        return
    # HWND_TOPMOST or HWND_NOTOPMOST, neither moving, sizing nor activating it
    insert_after = wintypes.HWND(-1 if on else -2)
    ctypes.windll.user32.SetWindowPos(wintypes.HWND(int(window.winId())), insert_after, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def frame_insets(window: QWidget) -> tuple[float, float, float, float]:
    """How far the frame Windows draws lies inside the window's frame as Qt gives it, left, top, right and bottom, in
    Qt's units; negative where it lies outside, as Windows draws a pixel of outline beyond it. Windows' outer
    rectangle adds an invisible resize border at the sides and bottom, which Qt leaves out of its frame. Measured in
    the screen's own pixels and only the differences scaled, it holds on every screen however far from the first"""
    if os.name != "nt":
        return (0, 0, 0, 0)
    handle = int(window.winId())
    visible = visible_frame(handle)
    outer = wintypes.RECT()
    if visible is None or not ctypes.windll.user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(outer)):
        return (0, 0, 0, 0)
    ratio = window.devicePixelRatio()
    frame = window.frameGeometry()
    # The invisible border Qt leaves out, at each side and at the bottom; Qt's frame starts at the outer top
    side = ((outer.right - outer.left) - frame.width() * ratio) / 2
    bottom = (outer.bottom - outer.top) - frame.height() * ratio
    return (
        (visible.left - outer.left - side) / ratio, (visible.top - outer.top) / ratio,
        (outer.right - visible.right - side) / ratio, (outer.bottom - visible.bottom - bottom) / ratio,
    )


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

    def __init__(
        self, on_close: Callable[[], None], on_resized_by_user: Callable[[int], None] | None = None, fonts: Fonts | None = None,
        on_minimize: Callable[[], None] | None = None,
    ) -> None:
        # Without Windows' frame, which cannot have a see-through background behind it: the window draws its own title
        # bar and edges, and its background turns to glass as a floating panel's does
        # Not Qt's frameless flag, which would make the see-through window a layered one, see let_compositor_blend
        super().__init__(None, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Tooltips show while another program is in front, as PS Focus sits beside the art app the user works in
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        self.glass_alpha = 255
        # Whether Always on top is on, which the title bar's menu shows
        self.always_on_top = False
        self.on_close = on_close
        self.on_resized_by_user = on_resized_by_user
        # Told when the window moves, and when it is minimized or brought back, for the floating modules
        self.on_moved: Callable[[], None] | None = None
        self.on_state_changed: Callable[[], None] | None = None
        # Told when the mouse comes onto the window or leaves it, which turns it solid or see-through
        self.on_hover: Callable[[], None] | None = None
        self.setWindowTitle(APP_NAME)
        # Like the Tk window, there is nothing to maximize to: the window is as big as what it shows
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        self.title_bar = TitleBar(self, fonts or Fonts())
        self.title_bar.on_close = self.close
        # Minimising hides it in the tray, where it keeps counting, see the app's window_hidden
        self.title_bar.on_minimize = on_minimize or self.showMinimized
        # The blocks are placed in the container, which slides within the viewport
        self.viewport = QWidget(self)
        self.container = QWidget(self.viewport)
        self.blocks: list[QWidget] = []
        self.anchor: QWidget | None = None
        self.modules_shown = False
        self.landscape = False
        self.offset = 0
        self.settings_page: QWidget | None = None
        # The width the app last gave the window in landscape, to tell a width the user dragged to from it
        self.requested_width = 0
        # Set while the window resizes itself, so that a size Qt passes through then is not taken for the user's
        self.refitting = False
        # While the edge strip is being dragged, the only time a new width is the user's own, see resizeEvent
        self.user_resizing = False
        # Laid over the bottom of a window too short for its blocks, so they disappear behind a margin rather than
        # running right up to the edge, see the Tk ModulesMixin._update_clip_margin
        self.clip_margin = ClipMargin(self)
        self.clip_margin.hide()
        # The edge the window is resized by: the bottom in portrait, the right in landscape
        self.grip = EdgeGrip(self)
        _keep_window_behaviour(self)
        let_compositor_blend(self)

    # Windows is told the frame takes no room (see nativeEvent), so the window is exactly what Qt calls its geometry.
    # Qt still measures a frame for a window that isn't frameless, 8 pixels in from it, and moves and reports the window
    # by that, so these answer from the geometry instead, as for a frameless window
    def frameGeometry(self) -> QRect:
        return self.geometry()

    def x(self) -> int:
        return self.geometry().x()

    def y(self) -> int:
        return self.geometry().y()

    def pos(self) -> QPoint:
        return self.geometry().topLeft()

    def move(self, *position) -> None:
        point = position[0] if len(position) == 1 else QPoint(*position)
        self.setGeometry(QRect(point, self.size()))

    def nativeEvent(self, event_type, message):
        # The whole window is the app's to draw: Windows is told its frame takes no room, so none is drawn
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                return True, 0
            if msg.message == WM_EXITSIZEMOVE:
                self.user_resizing = False
        return super().nativeEvent(event_type, message)

    def show_always_on_top(self, on: bool) -> None:
        """Note whether Always on top is on, for the title bar's menu to tick it"""
        self.always_on_top = on

    def set_glass(self, alpha: int) -> None:
        """Make the window's own background, the title bar's, and the margin's this solid, from 255 down"""
        if alpha != self.glass_alpha:
            self.glass_alpha = alpha
            self.title_bar.set_glass(alpha)
            self.clip_margin.update()
            self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        """The background in the gaps between the blocks, as see-through as the window, with a faint outline"""
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        background = color("background")
        background.setAlpha(self.glass_alpha)
        painter.fillRect(self.rect(), background)
        outline = color("border")
        outline.setAlpha(max(self.glass_alpha, OUTLINE_MIN_ALPHA))
        painter.setPen(outline)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self.on_hover is not None:
            self.on_hover()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self.on_hover is not None:
            self.on_hover()

    def set_top(self, header: QWidget, controls: QWidget) -> None:
        """The header, and the module checkboxes under it"""
        self.header, self.controls = header, controls

    def show_blocks(
        self, blocks: list[QWidget], anchor: QWidget | None, modules_shown: bool, landscape: bool = False, width: int | None = None
    ) -> None:
        """Show these blocks in this order and hide any others. The anchor is the program panel kept in view as the
        window gets smaller; modules_shown, whether a module is among the blocks. In landscape the window is this
        wide, or with none given as wide as every block"""
        if self.settings_page is not None:
            self.settings_page.hide()
            self.settings_page = None
        self.viewport.show()
        for block in self.blocks:
            if block not in blocks:
                block.hide()
        self.blocks, self.anchor, self.modules_shown, self.landscape = blocks, anchor, modules_shown, landscape
        self._lay_out()
        for block in blocks:
            block.show()
        self.refit(width)

    def show_settings(self, page: QWidget) -> None:
        """Show the Settings page whole beneath the header, as in the Tk app."""
        self.settings_page = page
        self.viewport.hide()
        self.controls.hide()
        self.clip_margin.hide()
        self.grip.hide()
        self.header.setParent(self)
        self.header.move(WINDOW_MARGIN, TITLE_BAR_HEIGHT)
        self.header.show()
        page.setParent(self)
        page.move(WINDOW_MARGIN, TITLE_BAR_HEIGHT + self.header.height() + HEADER_GAP)
        page.show()
        width = TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2
        height = TITLE_BAR_HEIGHT + self.header.height() + HEADER_GAP + page.height()
        self.setFixedSize(width, height)

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
            self.viewport.move(WINDOW_MARGIN, TITLE_BAR_HEIGHT)
        else:
            for widget in (header, controls):
                if widget.parent() is not self:
                    widget.setParent(self)
            header.move(WINDOW_MARGIN, TITLE_BAR_HEIGHT)
            controls.move(WINDOW_MARGIN, TITLE_BAR_HEIGHT + header.height() + HEADER_GAP)
            top = 0
            for block in self.blocks:
                if block.parent() is not self.container:
                    block.setParent(self.container)
                top += MODULE_GAP
                block.move(0, top)
                top += block.height()
            self.container.resize(TODAY_PANEL_WIDTH, top)
            self.viewport.move(WINDOW_MARGIN, TITLE_BAR_HEIGHT + top_height)
        # Taken from one parent to another, a widget is hidden until shown again
        header.show()
        controls.show()

    def top_height(self) -> int:
        return self.header.height() + HEADER_GAP + self.controls.height()

    def full_size(self) -> tuple[int, int]:
        """Size of the window showing every block whole"""
        if self.landscape:
            return WINDOW_MARGIN + self.container.width(), TITLE_BAR_HEIGHT + self.container.height()
        content = self.container.height() if self.blocks else COMPACT_BOTTOM_SPACE
        return TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2, TITLE_BAR_HEIGHT + self.top_height() + content

    def compact_height(self) -> int:
        """Smallest height in portrait: the header and checkboxes, and the program panel holding the header, so it
        is never cut off; the other blocks slide out of view around it"""
        panel = MODULE_GAP + self.anchor.height() if self.anchor is not None and self.anchor in self.blocks else 0
        return TITLE_BAR_HEIGHT + self.top_height() + COMPACT_BOTTOM_SPACE + panel

    def refit(self, width: int | None = None) -> None:
        """Lay the blocks out again and size the window to all of them, after a block has come, gone, grown or
        shrunk. In portrait it can then be dragged shorter, down to its compact height; in landscape narrower, down
        to the width of a panel, and it is given this width if one is given and it is not wider than everything"""
        if self.settings_page is not None:
            self.show_settings(self.settings_page)
            return
        self._lay_out()
        self.refitting = True
        try:
            self._fit_to_blocks(width)
        finally:
            self.refitting = False
        self._slide()

    def _fit_to_blocks(self, width: int | None) -> None:
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
        # An ordinary window is sized as Windows creates it, before the app has given it its header
        if self.settings_page is not None or not hasattr(self, "header"):
            return
        self.viewport.resize(max(1, self.width() - self.viewport.x()), max(1, self.height() - self.viewport.y()))
        anchored = self.anchor is not None and self.anchor in self.blocks
        if self.landscape:
            start, end = (self.anchor.x(), self.anchor.x() + self.anchor.width()) if anchored else (0, 0)
            offset = min(max(0, end - (self.width() - WINDOW_MARGIN)), start)
            position = (-offset, 0)
            self.clip_margin.hide()
        else:
            start, end = (self.anchor.y(), self.anchor.y() + self.anchor.height()) if anchored else (0, 0)
            room = self.height() - TITLE_BAR_HEIGHT - self.top_height() - COMPACT_BOTTOM_SPACE
            offset = min(max(0, end - room), max(0, start - MODULE_GAP))
            position = (0, -offset)
            clipped = self.modules_shown and self.height() < self.full_size()[1]
            self.clip_margin.setVisible(clipped)
            if clipped:
                self.clip_margin.setGeometry(0, self.height() - COMPACT_BOTTOM_SPACE, self.width(), COMPACT_BOTTOM_SPACE)
                self.clip_margin.raise_()
        self.offset = offset
        self._place_grip()
        # Most resizes leave the blocks where they are; moving them only when they must keeps resizing smooth
        if (self.container.x(), self.container.y()) != position:
            self.container.move(*position)

    def _place_grip(self) -> None:
        """The grip along the edge the window can be dragged along, shown only while there is room to resize"""
        if self.landscape:
            resizable = self.minimumWidth() < self.maximumWidth()
            self.grip.set_edge(Qt.Edge.RightEdge)
            self.grip.setGeometry(self.width() - GRIP_SIZE, TITLE_BAR_HEIGHT, GRIP_SIZE, self.height() - TITLE_BAR_HEIGHT)
        else:
            resizable = self.minimumHeight() < self.maximumHeight()
            self.grip.set_edge(Qt.Edge.BottomEdge)
            self.grip.setGeometry(0, self.height() - GRIP_SIZE, self.width(), GRIP_SIZE)
        self.grip.setVisible(resizable and self.settings_page is None)
        self.grip.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.title_bar.setGeometry(0, 0, self.width(), TITLE_BAR_HEIGHT)
        self.title_bar.raise_()
        # Floating panels keep the window's new edges, see Docking.main_moved
        if self.on_moved is not None:
            self.on_moved()
        self._slide()
        # In landscape a width the user dragged the edge to is kept while blocks come and go. Only a drag counts: a
        # resize Windows applies late, such as the narrow Settings page's after leaving it, would otherwise be taken
        # for the user's and leave the window that narrow
        if (self.user_resizing and self.settings_page is None and self.landscape and not self.refitting
                and self.width() != self.requested_width and self.on_resized_by_user is not None):
            self.requested_width = self.width()
            self.on_resized_by_user(self.width())

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        if self.on_moved is not None:
            self.on_moved()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.on_state_changed is not None:
            self.on_state_changed()

    def place_top_right(self) -> None:
        """Put the window in the top right corner of its screen's work area, its visible frame flush with the corner"""
        work = self.screen().availableGeometry()
        frame = self.frameGeometry()
        self.move(work.right() + 1 - frame.width(), work.top())
        _left, top, right, _bottom = frame_insets(self)
        # The invisible border may run past the screen's edge; the drawn frame meets the corner
        self.move(self.x() + round(right), self.y() - round(top))

    def closeEvent(self, event: QCloseEvent) -> None:
        # The window's X, or Alt+F4, exits the app, which closes the window itself once it has saved
        event.ignore()
        self.on_close()


class ClipMargin(QWidget):
    """The strip laid over the bottom of a window too short for its blocks, in the window's background, as see-through
    as the window"""

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        background = color("background")
        background.setAlpha(self.window().glass_alpha)
        painter.fillRect(self.rect(), background)
        painter.end()
