"""PS Focus application window: tracking loop, header, program panels, and tray icon"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes
from datetime import date, datetime, timedelta
from pathlib import Path

import pystray
from PIL import Image
from pystray import MenuItem

import app_config
import uninstall
from app_config import (
    APP_NAME,
    BACKUP_INTERVAL_MS,
    CHART_PERIODS,
    COLORS,
    DEFAULT_SETTINGS,
    FEEDBACK_UNLOCK_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    MAX_TICK_CREDIT_SECONDS,
    COMPACT_BOTTOM_SPACE,
    MIN_WINDOW_HEIGHT,
    MODULE_GAP,
    TODAY_PANEL_WIDTH,
    PROGRAM_PANEL_SETTINGS,
    WINDOW_MARGIN,
    format_duration,
    load_settings,
    resource_path,
    user_level,
)
from feedback import FeedbackOutbox
from google_drive import GoogleDriveSync
from tracker import ActivityStore, foreground_application, user_is_active
from ui_backup import BackupMixin
from ui_calendar import CalendarMixin
from ui_celebration import CelebrationMixin
from ui_chart import ChartMixin
from ui_feedback import FeedbackMixin
from ui_google import GoogleMixin
from ui_header import HeaderMixin
from ui_modules import BLOCK_NAMES, ModulesMixin
from ui_settings import SettingsMixin
from ui_updates import UpdateMixin
from unpack_cleanup import remove_stale_unpack_folders
from widgets import CanvasText, OutlinedButton, checkbox_image
from windows_startup import (
    SingleInstance,
    SizeLimits,
    apply_first_run_startup,
    migrate_legacy_app_data,
    migrate_legacy_startup,
    refresh_startup_entry,
    set_app_user_model_id,
    set_title_bar_colors,
)

# How much of the window's top is always kept on its screen, so it can be dragged back by its title bar
TITLE_BAR_KEPT = 40
# Space inside a program panel: above its first row and below its last, and at each side of its text
TODAY_PANEL_PADDING = 9
TODAY_PANEL_SIDE_PADDING = 8
# Space above and below the digits of a program panel's big time figure
TODAY_FIGURE_SPACE = (12, 15)
# Space between a program panel's last two rows
TODAY_ROW_GAP = 7
# Longest the app may take to close after Exit before it is ended regardless
EXIT_TIMEOUT_SECONDS = 10


class PSFocusApp(ModulesMixin, ChartMixin, CalendarMixin, SettingsMixin, BackupMixin, GoogleMixin, FeedbackMixin, CelebrationMixin, UpdateMixin, HeaderMixin):
    # The claim to be the only running copy, when started through main
    instance: SingleInstance | None = None
    # Set once the app has begun closing, see _close
    closing = False

    def __init__(self, root: tk.Tk, instance: SingleInstance | None = None) -> None:
        self.root = root
        self.instance = instance
        self.settings = load_settings()
        # One program panel is always shown; settings from before that rule may have none, so Photoshop's comes back
        if not any(self.settings.get(key) for key in PROGRAM_PANEL_SETTINGS.values()):
            self.settings["tracking_enabled"] = True
        self.block_order = self._read_block_order()
        self.google = GoogleDriveSync(app_config.APP_DATA, resource_path("credentials.json"))
        self.backup_restore_message: str | None = None
        if (
            not ActivityStore.database_is_usable(app_config.DATABASE_PATH)
            and ActivityStore.latest_valid_backup(app_config.BACKUP_DIRECTORIES) is None
            and self.google.connected
        ):
            try:
                remote_backup = self.google.download_activity_backup()
                if remote_backup and ActivityStore.restore_backup_bytes(app_config.DATABASE_PATH, remote_backup, app_config.BACKUP_DIRECTORIES[0]):
                    self.backup_restore_message = "Activity history restored from Google Drive"
                else:
                    self.backup_restore_message = "No valid Google Drive activity backup was found"
            except Exception as error:
                self.backup_restore_message = f"Could not restore Google Drive backup: {error}"
        self.store = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
        if self.store.recovered_from_backup and self.backup_restore_message is None:
            self.backup_restore_message = "Activity history restored from a local backup"
        self.backup_in_progress = False
        self.drive_backup_path: Path | None = None
        self.results: queue.Queue[tuple[str, bool, str]] = queue.Queue()
        self.remote_backup_payloads: queue.Queue[bytes] = queue.Queue()
        self.google_reauthentication_required = False
        self.google_account_email: str | None = None
        self.editing_display_name = False
        self.level_revealed = bool(self.settings.get("feedback_submitted"))
        self.feedback = FeedbackOutbox(app_config.APP_DATA / "feedback-outbox.json")
        self.feedback_send_in_progress = False
        self.feedback_unlocked = False
        self.available_update: tuple[str, str] | None = None
        self.update_announced = False
        self.settings_resync_in_progress = False
        self.module_frames: dict[str, tk.Frame] = {}
        self.module_headers: dict[str, tk.Frame] = {}
        self.module_contents: dict[str, tk.Frame] = {}
        self.module_vars: dict[str, tk.BooleanVar] = {}
        self.indicator_images: dict[tuple[bool, str], tk.PhotoImage] = {}
        self.drag_candidate: str | None = None
        self.drag_origin: tuple[int, int] | None = None
        self.dragged_module: str | None = None
        self.module_order_changed = False
        self.period = self.settings.get("period")
        if self.period not in CHART_PERIODS:
            self.period = "Day"
        self.calendar_month = date.today().replace(day=1)
        self.calendar_view = "Month"
        self.calendar_last_refresh: datetime | None = None
        self.calendar_visual_state: tuple | None = None
        self.calendar_refresh_scheduled = False
        self.stats_last_refresh: datetime | None = None
        self.chart_redraw_after_id: str | None = None
        self.chart_last_drawn_day: date | None = None
        self.chart_state: dict | None = None
        self.chart_hover_index: int | None = None
        self.fitted_content_height: int | None = None
        self.active = False
        self.view = "Overview"
        self.tray_icon: pystray.Icon | None = None
        self.tray_thread: threading.Thread | None = None
        self._configure_window()
        self._build()
        self._set_minimum_height()
        self._show_view()
        self._resize_to_content(fit=True, compact=True)
        if any(variable.get() for variable in self.module_vars.values()):
            # Modules left open last time are restored, so the window grows to fit them
            self._resize_to_content(fit=True)
        self._place_window_top_right()
        self._start_tray_icon()
        self.root.bind("<Map>", self._window_shown, add="+")
        self.last_tick_time = time.monotonic()
        self.unrecorded_active_seconds = 0.0
        self._tick()
        self.root.after(150, self._poll_results)
        self.root.after(BACKUP_INTERVAL_MS, self._periodic_activity_backup)
        self._backup_activity_now()
        if self.backup_restore_message:
            restored = self.backup_restore_message.startswith("Activity history restored")
            self.activity_backup_status.configure(
                text=self.backup_restore_message,
                fg=COLORS["active_green"] if restored else COLORS["red"],
            )
        self._send_pending_feedback()
        self._check_for_updates()
        if self.google.connected:
            self.account_label.configure(text="Loading Google account…")
            threading.Thread(target=self._load_google_account, daemon=True).start()
        if "--minimized" in sys.argv:
            self.root.iconify()

    def _configure_window(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry("480x900")
        self.root.minsize(TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2, MIN_WINDOW_HEIGHT)
        # Keeps the window from sliding when an edge is dragged past these limits, see SizeLimits
        self.size_limits = SizeLimits(self.root)
        # Portrait lets the window be dragged taller or shorter; see _set_window_resizable once settings are read
        self.root.resizable(False, True)
        self.root.configure(bg=COLORS["background"])
        self._set_title_bar_colors()
        self._set_window_icon()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        # When Windows closes the app, for an installer upgrading it or for signing out or shutting down, Tk
        # first reports it as WM_SAVE_YOURSELF and then as WM_DELETE_WINDOW, the same as the window's X, which
        # only hides the app. Closing on the first keeps Windows from waiting and then ending the app by force
        self.root.protocol("WM_SAVE_YOURSELF", self._exit)
        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.font_bold = tkfont.Font(family="Segoe UI Semibold", size=10)
        self.font_small = tkfont.Font(family="Segoe UI", size=9)
        self.font_account = tkfont.Font(family="Segoe UI", size=11)
        self.font_counter = tkfont.Font(family="Segoe UI", size=10)
        self.font_two_week = tkfont.Font(family="Segoe UI", size=app_config.HEADING_FONT_SIZE)
        self.font_title = tkfont.Font(family="Segoe UI Semibold", size=20)
        self.font_metric = tkfont.Font(family="Segoe UI Semibold", size=app_config.METRIC_FONT_SIZE)

    def _set_title_bar_colors(self, window: tk.Misc | None = None) -> None:
        set_title_bar_colors(window or self.root)

    def _set_window_icon(self) -> None:
        taskbar_image = tk.PhotoImage(file=str(resource_path("assets/icons/PSFocus_Taskbar_48.png")))
        window_image = tk.PhotoImage(file=str(resource_path("assets/icons/PSFocus_AppWindow_32.png")))
        self.window_icons = (taskbar_image, window_image)
        self.root.iconphoto(True, *self.window_icons)
        try:
            self.root.iconbitmap(str(resource_path("assets/icons/PSFocus.ico")))
        except tk.TclError:
            pass

    def _build(self) -> None:
        self.displayed_level: tuple[int, bool] | None = None
        self._build_header()
        self._draw_level_badge(0)
        self._prepare_celebration()

        # The two pages sit directly in the window at their natural height, see _show_view. A frame that
        # stretches with the window is repainted on every step of a resize, so none is used
        self.overview = tk.Frame(self.root, bg=COLORS["background"])
        self.settings_page = tk.Frame(self.root, bg=COLORS["background"])
        # Holds the program panels and modules, which are made in the window itself and packed into it. It is made
        # before them, as a frame made after them would be drawn over them
        # The container is placed inside this frame and slid within it, so the program panel holding the header
        # stays in view however small the window, see _scroll_blocks
        self.module_viewport = tk.Frame(self.root, bg=COLORS["background"])
        self.module_container = tk.Frame(self.root, bg=COLORS["background"])
        self.module_container.bind("<Configure>", self._blocks_resized)
        self.settings_page.bind("<Configure>", self._settings_page_resized)
        self._build_overview()
        self._build_calendar()
        self._build_stats()
        self._build_module_controls()
        self._build_clip_margin()
        self._build_settings()
        self._update_google_status()
        for name, block in self._blocks().items():
            self._bind_module_drag(name, block)
        self._set_window_resizable()
        self._arrange_modules()

    def _indicator_image(self, checked: bool, surface: str) -> tk.PhotoImage:
        # Drawn once for each state and surface colour, then reused by every checkbox
        if (checked, surface) not in self.indicator_images:
            self.indicator_images[(checked, surface)] = checkbox_image(checked, surface)
        return self.indicator_images[(checked, surface)]

    def _draw_square_indicator(self, indicator: tk.Canvas, checked: bool) -> None:
        indicator.delete("all")
        indicator.create_image(
            indicator.winfo_reqwidth() // 2, indicator.winfo_reqheight() // 2, image=self._indicator_image(checked, indicator.cget("bg"))
        )

    def _resize_to_content(self, fit: bool = False, compact: bool = False, keep_right: bool = False) -> None:
        """Size the window to its content. A change in width keeps the window's left edge, and with it the header,
        in place while blocks come and go; with keep_right the right edge stays put instead"""
        self.root.update_idletasks()
        landscape = self._landscape() and self.view == "Overview" and not compact
        if self.view == "Overview":
            # The smallest height follows the modules shown, so it is brought up to date before sizing
            self._set_minimum_height()
        if landscape:
            # As wide as every column, or as narrow as the user has dragged the window, the columns that do not
            # fit cut off at its right edge. It cannot be dragged wider than every column
            width = self._landscape_full_width()
            self.root.maxsize(width, 100000)
            self._sync_size_limits()
            chosen = getattr(self, "landscape_chosen_width", None)
            if chosen is not None and chosen < width:
                width = chosen
        else:
            width = TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2
        full_height = self._full_height() if self.view == "Overview" and not landscape else self.root.winfo_reqheight()
        full_height = max(MIN_WINDOW_HEIGHT, full_height)
        if not landscape:
            # In portrait the window cannot be dragged taller than everything it shows. Windows' snap, which
            # stretches a window to the screen's full height, then shifts the window instead, which is accepted:
            # without the limit an empty strip under the blocks showed scraps of earlier pictures while resizing
            self.root.maxsize(width, full_height)
            self._sync_size_limits()
        if compact:
            requested_height = self._compact_height()
        elif fit:
            requested_height = full_height
        else:
            requested_height = self.root.winfo_reqheight()
        requested_height = max(MIN_WINDOW_HEIGHT, requested_height)
        current_height = self.root.winfo_height()
        height = requested_height if fit or current_height <= 1 else max(current_height, requested_height)
        current_width, current_x = self.root.winfo_width(), self.root.winfo_x()
        # A size asked for moments ago may not have reached the window yet; it is then the one to go by
        placed = getattr(self, "window_placement", None)
        if placed is not None and current_width != placed[0]:
            current_width, current_x = placed
        # Noted so a resize the user makes can be told from the app's own, see _window_resized
        self.requested_width = width
        if current_width > 1 and width != current_width and self.root.winfo_viewable():
            # Either way the window then moves left as far as it must to stay on its screen
            if keep_right:
                x = current_x + current_width - width
            else:
                x = min(current_x, self._screen_right() - width)
            x = max(self._screen_left(), x)
            self.root.geometry(f"{width}x{height}+{x}+{self.root.winfo_y()}")
            # The sums above go by the window's outer frame; this checks the frame as drawn
            x = self._nudge_onto_screen(x)
            self.window_placement = (width, x)
        else:
            self.root.geometry(f"{width}x{height}")
            if width != current_width:
                # Sized before it was shown, so there is no placement to remember
                self.window_placement = None
        # Noted so _refit_if_content_changed only reacts to changes made after this sizing
        self.fitted_content_height = self.root.winfo_reqheight()

    def _refit_if_content_changed(self) -> None:
        """Resize the window when its content has grown or shrunk, such as stats lines appearing

        The window is refitted only when the height the content needs has changed, so a height the user has
        dragged the window to is otherwise left alone
        """
        if self.view != "Overview":
            return
        self.root.update_idletasks()
        needed = self.root.winfo_reqheight()
        if self.fitted_content_height is not None and needed != self.fitted_content_height:
            self._resize_to_content(fit=True)
        self.fitted_content_height = needed

    def _place_window_top_right(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        right, top = self.root.winfo_screenwidth(), 0
        if os.name != "nt":
            self.root.geometry(f"{width}x{height}+{max(0, right - width)}+{top}")
            return

        # Use the desktop area left free by the taskbar, so the window is not placed underneath it
        work_area = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work_area), 0):
            right, top = work_area.right, work_area.top
        x, y = max(0, right - width), top
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.update_idletasks()

        # Windows pads a window with an invisible resize border, so shift by the gap between the frame Tk
        # positioned and the frame actually drawn to sit flush against the corner
        visible = self._visible_frame()
        if visible is not None:
            self.root.geometry(f"+{x + right - visible.right}+{y + top - visible.top}")

    def _visible_frame(self) -> wintypes.RECT | None:
        """The window's frame as drawn on screen, without the invisible resize border Windows pads it with"""
        if os.name != "nt":
            return None
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        window_handle = user32.GetAncestor(ctypes.c_void_p(self.root.winfo_id()), 2)
        visible = wintypes.RECT()
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwmapi.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        if window_handle and dwmapi.DwmGetWindowAttribute(window_handle, 9, ctypes.byref(visible), ctypes.sizeof(visible)) == 0:
            if visible.right > visible.left:
                return visible
        return None

    def _nudge_onto_screen(self, x: int) -> int:
        """Move the window, if need be, so its visible frame is within its screen sideways and its title bar is on it,
        and return its new x"""
        self.root.update_idletasks()
        visible = self._visible_frame()
        if visible is None:
            return x
        screen_left, screen_right = self._screen_edges()
        screen_top, screen_bottom = self._screen_heights()
        shift = 0
        if visible.right > screen_right:
            shift = screen_right - visible.right
        if visible.left + shift < screen_left:
            shift = screen_left - visible.left
        # The title bar is kept on the screen, so the window can always be dragged back
        drop = 0
        if visible.top < screen_top:
            drop = screen_top - visible.top
        elif visible.top > screen_bottom - TITLE_BAR_KEPT:
            drop = screen_bottom - TITLE_BAR_KEPT - visible.top
        if shift or drop:
            x += shift
            self.root.geometry(f"+{x}+{self.root.winfo_y() + drop}")
        return x
        screen_left, screen_right = self._screen_edges()
        shift = 0
        if visible.right > screen_right:
            shift = screen_right - visible.right
        if visible.left + shift < screen_left:
            shift = screen_left - visible.left
        if shift:
            x += shift
            self.root.geometry(f"+{x}+{self.root.winfo_y()}")
        return x

    def _screen_heights(self) -> tuple[int, int]:
        """Top and bottom of the work area of the screen the window is on"""
        work = self._work_area()
        return (work[1], work[3]) if work else (0, self.root.winfo_screenheight())

    def _screen_edges(self) -> tuple[int, int]:
        """Left and right edges of the work area of the screen the window is on"""
        work = self._work_area()
        return (work[0], work[2]) if work else (0, self.root.winfo_screenwidth())

    def _work_area(self) -> tuple[int, int, int, int] | None:
        """The work area, left, top, right and bottom, of the screen the window is on, without the taskbar"""
        if os.name != "nt":
            return None

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT), ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        window_handle = user32.GetAncestor(ctypes.c_void_p(self.root.winfo_id()), 2)
        # 2: the nearest screen, should the window be off every screen
        monitor = user32.MonitorFromWindow(ctypes.c_void_p(window_handle), 2)
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if monitor and user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
            return info.work.left, info.work.top, info.work.right, info.work.bottom
        return None

    def _screen_left(self) -> int:
        return self._screen_edges()[0]

    def _screen_right(self) -> int:
        return self._screen_edges()[1]

    def _header_rows_height(self) -> int:
        """Height of the header and the module checkboxes under it, with the space kept below them"""
        return self.header_canvas.winfo_reqheight() + 2 + self.module_control_footer.winfo_reqheight() + COMPACT_BOTTOM_SPACE

    def _full_height(self) -> int:
        """Height of the portrait window showing everything: the viewport is sized to every shown block, see
        _size_viewport"""
        return self.root.winfo_reqheight()

    def _compact_height(self) -> int:
        """Smallest height of the window in portrait: the header and checkboxes, and the program panel holding the
        header in landscape, so it is never cut off; the other blocks slide out of view around it"""
        anchor = self._anchor_block()
        panel = MODULE_GAP + self.application_panels[anchor].winfo_reqheight() if anchor is not None else 0
        return self._header_rows_height() + panel

    def _set_minimum_height(self) -> None:
        """Stop the window being dragged shorter than what it has to show

        The Settings page is always shown whole. The overview can be shortened until only the header, the
        program panels and the checkbox row are left, its modules disappearing behind the window's edge
        """
        self.root.update_idletasks()
        # In landscape the modules stand beside the panels and are about as tall, so none of them is cut off either
        if self.view == "Settings" or self._landscape():
            needed = self.root.winfo_reqheight()
        else:
            # Never more than the whole overview, so the window always fits everything at its least height
            needed = min(self._compact_height(), self._full_height())
        self.root.minsize(TODAY_PANEL_WIDTH + WINDOW_MARGIN * 2, max(MIN_WINDOW_HEIGHT, needed))
        self._sync_size_limits()

    def _sync_size_limits(self) -> None:
        """Give the edge-dragging guard the same limits as Tk"""
        limits = getattr(self, "size_limits", None)
        if limits is not None:
            limits.set(self.root.minsize(), self.root.maxsize())

    def _settings_page_resized(self, _event: tk.Event) -> None:
        # A status message running onto a second line makes the page taller while it is open
        if self.view == "Settings":
            self.root.after_idle(self._set_minimum_height)

    def _anchor_overhead(self) -> int:
        """Height the header and module checkboxes add on top of the anchor panel in landscape"""
        return self.header_canvas.winfo_reqheight() + 2 + self.module_control_footer.winfo_reqheight() + MODULE_GAP

    def _stretch_today_panels(self, extra: int, anchor: str | None = None, anchor_extra: int = 0) -> None:
        """Make the program panels this much taller, their contents kept in the middle, so in landscape they are as
        tall as the modules beside them; the anchor panel, under the header, by anchor_extra. 0 returns them to
        their own height"""
        stretches = getattr(self, "today_panel_stretch", {})
        self.today_panel_stretch = stretches
        for application, panel in self.application_panels.items():
            share = max(0, anchor_extra if application == anchor else extra)
            old = stretches.get(application, 0)
            if share != old:
                panel.configure(height=self.today_panel_height + share)
                panel.move("all", 0, share // 2 - old // 2)
                stretches[application] = share

    def _create_today_panel(self, application: str) -> tk.Canvas:
        """Build one program's panel as a single canvas; its lines of text are updated every second like labels"""
        def line(*fonts: tkfont.Font) -> int:
            return max(font.metrics("linespace") for font in fonts)

        # Four rows from the top: name and two-week total, today's time, sessions and hours, status and last session.
        # The big figure's font reserves empty space above its digits and below its baseline. The rows around it
        # are set against the digits themselves, not that space, which is what keeps the panel short
        figure_ascent = self.font_metric.metrics("ascent")
        digit_height = round(figure_ascent * 0.66)
        heights = (line(self.font_two_week), digit_height, line(self.font_small, self.font_counter), line(self.font_bold, self.font_counter))
        heading_top = 1 + TODAY_PANEL_PADDING
        digits_top = heading_top + heights[0] + TODAY_FIGURE_SPACE[0]
        details_top = digits_top + digit_height + TODAY_FIGURE_SPACE[1]
        status_top = details_top + heights[2] + TODAY_ROW_GAP
        tops = (heading_top, digits_top, details_top, status_top)

        def text_top(row: int, font: tkfont.Font) -> int:
            if font is self.font_metric:
                return digits_top - (figure_ascent - digit_height)
            # Text of differing sizes sharing a row is centred on it, in whole pixels
            return tops[row] + (heights[row] - line(font)) // 2

        panel_height = status_top + heights[3] + TODAY_PANEL_PADDING + 1
        # Every panel is this tall unless stretched to line up with the modules, see _stretch_today_panels
        self.today_panel_height = panel_height - 2
        # Made in the window itself, like the modules, so it can be packed in among them
        panel = tk.Canvas(
            self.root,
            width=TODAY_PANEL_WIDTH - 2,
            height=panel_height - 2,
            bg=COLORS["panel"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        left, right = 1 + TODAY_PANEL_SIDE_PADDING, TODAY_PANEL_WIDTH - 1 - TODAY_PANEL_SIDE_PADDING

        def text(row: int, side: str, content: str, color: str, font: tkfont.Font) -> CanvasText:
            return CanvasText(panel, left if side == "w" else right, text_top(row, font), "n" + side, content, color, font)

        text(0, "w", application, COLORS["muted"], self.font_two_week)
        two_week = text(0, "e", "0.0 hours past 2 weeks", COLORS["muted"], self.font_two_week)
        total = text(1, "w", "0m", COLORS["text"], self.font_metric)
        sessions = text(2, "w", "0 SESSIONS", COLORS["muted"], self.font_small)
        record_hours = text(2, "e", "0.0 hrs on record", COLORS["muted"], self.font_counter)
        status = text(3, "w", "NOT ACTIVE", COLORS["muted"], self.font_bold)
        last_session = text(3, "e", "last session on --", COLORS["muted"], self.font_counter)
        self.application_totals[application] = total
        self.application_two_week_labels[application] = two_week
        self.application_session_labels[application] = sessions
        self.application_record_hours_labels[application] = record_hours
        self.application_status_labels[application] = status
        self.application_last_session_labels[application] = last_session
        return panel

    def _build_overview(self) -> None:
        self.application_panels: dict[str, tk.Canvas] = {}
        self.application_totals: dict[str, CanvasText] = {}
        self.application_two_week_labels: dict[str, CanvasText] = {}
        self.application_session_labels: dict[str, CanvasText] = {}
        self.application_record_hours_labels: dict[str, CanvasText] = {}
        self.application_status_labels: dict[str, CanvasText] = {}
        self.application_last_session_labels: dict[str, CanvasText] = {}
        for application in PROGRAM_PANEL_SETTINGS:
            panel = self._create_today_panel(application)
            self.application_panels[application] = panel

        # The overview holds the module checkboxes, under the header; filled in by _draw_module_controls
        self.module_control_footer = tk.Canvas(
            self.overview, width=TODAY_PANEL_WIDTH, height=1, bg=COLORS["background"], highlightthickness=0
        )
        self._build_chart()

    def _button(self, parent: tk.Widget, text: str, command, accent: bool = False, pady: int = 6) -> OutlinedButton:
        bg = COLORS["accent_dark"] if accent else COLORS["panel_alt"]
        fg = COLORS["accent"] if accent else COLORS["text"]
        return OutlinedButton(parent, text=text, command=command, bg=bg, fg=fg, padx=17, pady=pady, font=self.font_small)

    def _navigate(self, view: str) -> None:
        self.view = view
        self._show_view()
        self._set_minimum_height()
        self._resize_to_content(fit=True)

    def _toggle_settings(self) -> None:
        self._navigate("Overview" if self.view == "Settings" else "Settings")

    def _show_view(self) -> None:
        """Show the overview or the Settings page under the header

        In landscape the overview, holding the header and the module checkboxes, sits on top of the anchor panel
        among the other blocks, see _arrange_modules; otherwise the header runs across the top
        """
        header = self.header_canvas
        for widget in (header, self.overview, self.settings_page, self.module_control_footer):
            widget.pack_forget()
        if self.view == "Overview" and self._landscape():
            header.pack(in_=self.overview, anchor="w", pady=(0, 2))
            self.module_control_footer.pack(anchor="w")
            self._arrange_modules()
        else:
            # In the overview the space under the header belongs to the overview, which the blocks slide under
            header.pack(in_=self.root, anchor="w", padx=WINDOW_MARGIN, pady=(0, 0 if self.view == "Overview" else 2))
            page = self.overview if self.view == "Overview" else self.settings_page
            page.pack(fill="x", padx=WINDOW_MARGIN)
            if self.view == "Overview":
                self.module_control_footer.pack(anchor="w", pady=(2, 0))
        self._draw_module_controls()
        self._place_module_container()
        if self.view == "Settings":
            self._finish_display_name_edit(save=True)
        # The header shows a credit on the Settings page and the level and account otherwise
        self._draw_header()
        self._update_clip_margin()
        if self.view == "Overview":
            if self.module_vars["calendar"].get():
                self._schedule_calendar_refresh()
            if self.module_vars["graph"].get():
                self._draw_chart()
            if self.module_vars["stats"].get():
                self._draw_stats()

    def _read_block_order(self) -> list[str]:
        """The saved order of the program panels and modules, with any missing added at the end

        Versions before 1.0.6 kept the modules' order alone and the program panels together, with some modules
        possibly before them; that arrangement is carried over
        """
        order = self.settings.get("block_order")
        if not isinstance(order, list):
            modules = self.settings.get("module_order")
            modules = [name for name in modules if isinstance(name, str)] if isinstance(modules, list) else []
            before = self.settings.get("modules_left")
            before = before if isinstance(before, list) else []
            order = [name for name in modules if name in before] + list(PROGRAM_PANEL_SETTINGS) + [name for name in modules if name not in before]
        order = list(dict.fromkeys(name for name in order if name in BLOCK_NAMES))
        return order + [name for name in BLOCK_NAMES if name not in order]

    def _chosen_panels(self) -> list[str]:
        chosen = self.settings.get("program_panels_chosen")
        return [name for name in chosen if isinstance(name, str)] if isinstance(chosen, list) else []

    def _note_panel_chosen(self, application: str) -> None:
        """Remember that this program's panel has been shown or hidden, so it is not switched on automatically"""
        chosen = self._chosen_panels()
        if application not in chosen:
            self.settings["program_panels_chosen"] = chosen + [application]

    def _reveal_panel_on_first_use(self, application: str) -> None:
        """Switch on a program's panel the first time the program is used, so its time is not counted unseen

        Only a panel that is off by default and has never been shown or hidden by hand is switched on. A panel
        the user has hidden stays hidden: Photoshop's is on by default, so if it is off, the user turned it off
        """
        key = PROGRAM_PANEL_SETTINGS[application]
        if self.settings.get(key) or DEFAULT_SETTINGS[key] or application in self._chosen_panels():
            return
        self.settings[key] = True
        self._note_panel_chosen(application)
        if key in getattr(self, "setting_vars", {}):
            self.setting_vars[key].set(True)
            self._draw_square_indicator(self.checkbox_indicators[key], True)
        self._save_settings()
        self._update_application_panels()

    def _update_application_panels(self) -> None:
        self._arrange_modules()
        if self._landscape():
            self._match_landscape_heights()
        self._set_minimum_height()
        self._resize_to_content(fit=True)

    def _refresh_activity_views(self) -> None:
        if self.module_vars["calendar"].get():
            self._schedule_calendar_refresh()
        if self.module_vars["graph"].get():
            self.root.after_idle(self._draw_chart)
        if self.module_vars["stats"].get():
            self._draw_stats()

    def _poll_results(self) -> None:
        # Always schedule the next poll, so one failed handler cannot stop every later result being handled
        try:
            # A drag of the left or top edge has ended: the blocks, left where they were during it, are slid into place
            limits = getattr(self, "size_limits", None)
            if limits is not None and limits.drag_ended:
                limits.drag_ended = False
                if self.view == "Overview":
                    self._scroll_blocks()
            # Starting the app a second time brings up this copy's window instead, see main
            if self.instance is not None and self.instance.show_requested():
                self._restore_from_tray()
            # The installer asks the app to close before replacing its files
            if self.instance is not None and self.instance.exit_requested():
                self._exit()
            self._handle_results()
        finally:
            self.root.after(150, self._poll_results)

    def _handle_results(self) -> None:
        try:
            while True:
                kind, success, message = self.results.get_nowait()
                if kind == "backup":
                    self.backup_in_progress = False
                    self.activity_backup_status.configure(
                        text=message,
                        fg=COLORS["active_green"] if success else COLORS["red"],
                    )
                    continue
                if kind == "drive_backup":
                    self._backup_activity_now()
                    continue
                if kind == "update":
                    self._show_available_update(message)
                    continue
                if kind in ("restore_backup", "merge_backup"):
                    try:
                        backup_content = self.remote_backup_payloads.get_nowait()
                    except queue.Empty:
                        self.backup_in_progress = False
                        self.activity_backup_status.configure(text="Could not load Google Drive backup", fg=COLORS["red"])
                    else:
                        if kind == "restore_backup":
                            self._restore_downloaded_activity_backup(backup_content)
                        else:
                            self._merge_downloaded_activity_backup(backup_content)
                    continue
                if kind == "resync":
                    self.settings_resync_in_progress = False
                    self._set_google_action_state("normal")
                    self.google_settings_status.configure(
                        text=message[:48],
                        fg=COLORS["active_green"] if success else COLORS["red"],
                    )
                    self.root.after(5000, self._update_google_status)
                    continue
                if kind == "logout":
                    self.google_account_email = None
                    self.google_reauthentication_required = False
                    self.account_label.configure(state="normal")
                    self._set_google_action_state("normal")
                    self._update_google_status()
                    self._message(message, error=not success)
                    self.root.after(4000, self._update_google_status)
                    continue
                elif kind == "switch":
                    self.account_label.configure(state="normal")
                    self._set_google_action_state("normal")
                    if success:
                        self.google_reauthentication_required = False
                        self._update_google_status(message)
                        continue
                    else:
                        self.google_account_email = None
                        self._update_google_status()
                        self._message(f"Could not switch Google accounts: {message}", error=True)
                        continue
                elif kind == "account":
                    if not self.google.connected:
                        self._update_google_status()
                        continue
                    if success:
                        self._update_google_status(message)
                        continue
                    else:
                        self._message(f"Could not load Google account: {message}", error=True)
                        continue
                elif kind == "reauth":
                    self.google_reauthentication_required = True
                    self.account_label.configure(state="normal")
                    self._set_google_action_state("normal")
                    self._update_google_status()
                    self._message(message, error=True)
                    continue
                elif kind in ("connect", "sync"):
                    if kind == "sync" and not self.google.connected:
                        continue
                    self.account_label.configure(state="normal")
                    self._set_google_action_state("normal")
                    if success:
                        if kind == "connect":
                            self.google_reauthentication_required = False
                            self._update_google_status(message)
                            continue
                        else:
                            self._update_google_status()
                    elif kind == "connect":
                        self._update_google_status()
                self._message(message, error=not success)
        except queue.Empty:
            pass

    def _start_tray_icon(self) -> None:
        image_path = resource_path("assets/icons/PSFocus_Settings_64.png")
        tray_image = Image.open(image_path).convert("RGBA")
        self.tray_icon = pystray.Icon(
            APP_NAME,
            tray_image,
            APP_NAME,
            menu=pystray.Menu(
                MenuItem("Show PS Focus", self._show_from_tray, default=True),
                MenuItem("Exit", self._exit),
            ),
        )
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()

    def _show_from_tray(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self.root.after(0, self._restore_from_tray)

    def _restore_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _window_shown(self, event: tk.Event) -> None:
        # The window's own appearance is the only one of interest; its widgets report theirs through it as well
        if event.widget is not self.root:
            return
        # The edge-dragging guard can only be attached once the window is on screen
        self._sync_size_limits()
        if self.view == "Overview":
            self._refresh_activity_views()

    def _tick(self) -> None:
        # Always schedule the next tick, so one failed update cannot silently stop tracking for good
        try:
            self._track_and_refresh()
        finally:
            self.root.after(1000, self._tick)

    def _credit_active_time(self, application: str | None) -> None:
        """Record tracked time from the real time since the last tick, which runs slightly over a second apart"""
        now = time.monotonic()
        elapsed = min(now - self.last_tick_time, MAX_TICK_CREDIT_SECONDS)
        self.last_tick_time = now
        if not self.active:
            return
        self.unrecorded_active_seconds += elapsed
        while self.unrecorded_active_seconds >= 1:
            self.store.record_active_second(datetime.now(), application)
            self.unrecorded_active_seconds -= 1

    def _track_and_refresh(self) -> None:
        foreground_app = foreground_application()
        paused = bool(self.settings.get("tracking_paused"))
        # Every supported program is counted, whether or not its panel is shown
        self.active = not paused and foreground_app is not None and user_is_active(IDLE_TIMEOUT_SECONDS)
        self._credit_active_time(foreground_app)
        if self.active:
            self._reveal_panel_on_first_use(foreground_app)
        today = date.today()
        total_today_seconds = 0
        lifetime_seconds = 0
        for app_name in PROGRAM_PANEL_SETTINGS:
            today_seconds = self.store.total_for_day(today, app_name)
            two_weeks_seconds = self.store.total_for_range(today - timedelta(days=13), today, app_name)
            session_count = self.store.lifetime_sessions(application=app_name)
            total_seconds = self.store.total_seconds(app_name)
            last_session = self.store.last_recorded_day(app_name)
            total_today_seconds += today_seconds
            lifetime_seconds += total_seconds
            self.application_totals[app_name].configure(text=format_duration(today_seconds))
            self.application_two_week_labels[app_name].configure(text=f"{two_weeks_seconds / 3600:.1f} hours past 2 weeks")
            self.application_session_labels[app_name].configure(text=f"{session_count} SESSIONS")
            self.application_record_hours_labels[app_name].configure(text=f"{total_seconds / 3600:.1f} hrs on record")
            last_session_text = last_session.strftime("%d %b").lstrip("0") if last_session else "--"
            self.application_last_session_labels[app_name].configure(text=f"last session on {last_session_text}")
            app_active = self.active and foreground_app == app_name
            self.application_status_labels[app_name].configure(
                text="ACTIVE" if app_active else "PAUSED" if paused else "NOT ACTIVE",
                fg=COLORS["active_green"] if app_active else COLORS["muted"],
            )
        self._draw_progress_indicator(total_today_seconds)
        level = user_level(lifetime_seconds)
        self._draw_level_badge(level)
        self._celebrate_level_up(level)
        self._set_feedback_unlocked(lifetime_seconds >= FEEDBACK_UNLOCK_SECONDS)
        # Hidden in the tray or minimized, which is where the app spends most of its time, there is nothing to
        # redraw: the graph alone takes several times longer to draw than everything above. The modules are
        # brought up to date when the window is shown again, see _window_shown
        if not self.root.winfo_viewable():
            return
        if self.view == "Overview":
            now = datetime.now()
            if self.module_vars["calendar"].get() and (
                self.calendar_last_refresh is None or (now - self.calendar_last_refresh).total_seconds() >= 15
            ):
                self._schedule_calendar_refresh()
            if self.module_vars["stats"].get() and (
                self.stats_last_refresh is None or (now - self.stats_last_refresh).total_seconds() >= 15
            ):
                self._draw_stats()
        if self.view == "Overview" and self.module_vars["graph"].get() and (self.active or self.chart_last_drawn_day != today):
            self._draw_chart()
            self.chart_last_drawn_day = today

    def _exit(self, _icon: pystray.Icon | None = None, _item: MenuItem | None = None) -> None:
        # The tray runs its menu on its own thread, and the window and the database may only be used from the
        # main one, so the closing is handed over to it
        self.root.after(0, self._close)

    def _close(self) -> None:
        # Windows and the tray may both ask, so only the first request closes
        if self.closing:
            return
        self.closing = True
        # Should the final backup stall, on an unreachable folder for instance, the app still ends
        watchdog = threading.Timer(EXIT_TIMEOUT_SECONDS, os._exit, (0,))
        watchdog.daemon = True
        watchdog.start()
        self.root.withdraw()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        if self.tray_thread is not None and self.tray_thread is not threading.current_thread():
            self.tray_thread.join(timeout=2)
        try:
            self.store.create_local_backups()
        except Exception:
            pass
        self.store.close()
        self.root.destroy()


def main() -> None:
    if "--uninstall" in sys.argv:
        # Handled before anything is opened, so no file the uninstall deletes is in use by this process
        uninstall.main()
        return
    set_app_user_model_id()
    instance = SingleInstance()
    if instance.already_running:
        # Started by hand, the copy already running shows its window; started with Windows, nothing is needed
        if "--minimized" not in sys.argv:
            instance.ask_running_copy_to_show()
        return
    migrate_legacy_app_data()
    first_run = not app_config.SETTINGS_PATH.exists()
    settings = load_settings()
    migrate_legacy_startup(settings)
    if first_run:
        apply_first_run_startup(settings)
    else:
        refresh_startup_entry(settings)
    app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
    # Earlier runs that were ended by force left their unpack folders behind; cleared off the main thread,
    # as there can be many of them
    threading.Thread(target=remove_stale_unpack_folders, daemon=True).start()
    root = tk.Tk()
    PSFocusApp(root, instance)
    root.mainloop()


if __name__ == "__main__":
    main()
