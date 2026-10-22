"""PS Focus on Qt: the tracking loop, the window and the tray icon"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QProxyStyle, QStyle, QSystemTrayIcon

import app_config
from app_config import (
    APP_NAME,
    BACKUP_INTERVAL_MS,
    MODULE_GAP,
    CHART_PERIODS,
    DEFAULT_SETTINGS,
    FEEDBACK_COOLDOWN,
    FEEDBACK_UNLOCK_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    MAX_TICK_CREDIT_SECONDS,
    PROGRAMS,
    SESSION_MINIMUM_SECONDS,
    format_duration,
    level_xp_text,
    load_settings,
    resource_path,
    user_level,
)
from feedback import FeedbackOutbox
from tracker import ActivityStore, activity_slices, tracking_clock, foreground_application, user_is_active, running_applications
from unpack_cleanup import remove_stale_unpack_folders
from update_check import UPDATE_CHECK_INTERVAL_MS, available_update, is_safe_download_url
from windows_startup import (
    SingleInstance,
    apply_first_run_startup,
    migrate_legacy_app_data,
    migrate_legacy_startup,
    refresh_startup_entry,
    set_startup,
)
from friends import FriendsService
from google_drive import GoogleDriveSync

from .block_drag import BlockDrag
from .calendar_module import CalendarModule
from .celebration import Fireworks, play_celebration_sound
from .chart import ChartModule
from .day_overview import DayOverview
from .docking import Docking
from .feedback_dialog import FeedbackDialog
from .friends_module import FriendsModule
from .friends_sync import FriendsSync
from .header import Header, ModuleControls
from .stats_module import StatsModule
from .status_menu import PopupMenu
from .settings_page import SettingsPage
from .theme import Fonts
from .today_panel import TodayPanel
from .window import MainWindow, set_topmost
from .google_sync import GoogleSync

# The modules that can be put in order, beside the Today panel
MODULE_NAMES = ("graph", "calendar", "stats", "friends")
# The first order: the program panel, then Friends, the most used after it, then the rest
BLOCK_NAMES = ("today", "friends", "graph", "calendar", "stats")
# Longest the app may take to close after Exit before it is ended regardless
EXIT_TIMEOUT_SECONDS = 10


class PSFocusQt:
    def __init__(self, application: QApplication, instance: SingleInstance | None = None, dev: bool = False) -> None:
        self.application = application
        # The developer version, on a copy of the data with a menu of things to try; see dev_tools
        self.dev = dev
        # Set by the developer version's level up tool, whose level-up plays the fanfare
        self.dev_level_up_requested = False
        self.instance = instance
        self.closing = False
        self.settings = load_settings()
        self._adopt_program_panels()
        self.block_order = self._read_block_order()
        # Kept in the order as read, so names an older version saved do not linger in the file
        self.settings["block_order"] = self.block_order.copy()
        self.store = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
        self.fonts = Fonts()
        self.active = False
        self.level_revealed = bool(self.settings.get("feedback_submitted"))
        self.feedback_unlocked = False
        # Set by the developer menu to show or hide Got feedback? whatever has been tracked; None follows the hours
        self.feedback_unlock_override: bool | None = None
        self.feedback = FeedbackOutbox(app_config.APP_DATA / "feedback-outbox.json")
        self.feedback_send_in_progress = False
        self.fireworks: Fireworks | None = None
        # The level at the last tick, which a level-up is noticed against; None until the first tick sets it
        self.celebrated_level: int | None = None
        self.available_update: tuple[str, str] | None = None
        self.update_announced = False
        # Results from background threads, handed to the UI thread by the poll timer
        self.results: queue.Queue = queue.Queue()
        self.landscape = bool(self.settings.get("landscape", False))
        # In landscape, a width the user dragged the window narrower to, kept while blocks come and go until the
        # window is dragged as wide as everything again
        self.landscape_width: int | None = None
        self.arranging = False
        self.settings_shown = False
        # While the transparency slider is open, everything shows the transparency being chosen, see update_glass
        self.transparency_previewing = False
        self.modules_were_hidden = True
        self.window = MainWindow(
            on_close=self.close, on_resized_by_user=self._window_width_chosen, fonts=self.fonts, on_minimize=self.window_hidden,
        )
        self.header = Header(self.fonts)
        self.module_ticked = {name: bool(self.settings.get(f"show_{name}", True)) for name in MODULE_NAMES}
        self.module_controls = ModuleControls(self.fonts, self.module_ticked, self._module_toggled, self._open_transparency)
        self.module_controls.transparency = self._transparency()
        self.window.set_top(self.header, self.module_controls)
        # The title bar's right-click menu holds Always on top
        self.window.title_bar.on_menu = self._title_bar_menu
        if dev:
            from .dev_tools import DevTools

            self.dev_tools = DevTools(self)
            self.window.title_bar.on_dev = self.dev_tools.open_menu
        self.header.on_settings = self._toggle_settings
        self.header.on_level = self._level_clicked
        self.header.on_goal_reached = self.goal_reached
        self.header.on_version = self._open_update_page
        self.header.version_text = f"Version {app_config.APP_VERSION}"
        # One panel for the program in front, or the last one that was. Made without a parent, so it stays out of
        # sight until the window's column takes it in
        program = self.settings.get("today_program")
        self.today = TodayPanel(program if program in PROGRAMS else PROGRAMS[0], self.fonts)
        self.today.on_program = self._select_program
        self.manual_program = False
        self.open_programs: set[str] = set()
        self.open_programs_checked = float("-inf")
        period = self.settings.get("period")
        self.chart = ChartModule(self.fonts, self.store, period if period in CHART_PERIODS else "Day", self._period_chosen)
        self.chart_drawn_day: date | None = None
        self.calendar = CalendarModule(self.fonts, self.store, self._open_day_overview, self._refresh_stats, self._block_resized)
        self.stats = StatsModule(self.fonts, self.store, self._block_resized)
        self.friends = FriendsModule(self.fonts, self._block_resized)
        self.modules = {"graph": self.chart, "calendar": self.calendar, "stats": self.stats, "friends": self.friends}
        self.docking = Docking(self)
        self.window.on_moved = self.docking.main_moved
        if dev:
            # The developer menu stays beside the window as it moves
            self.window.on_moved = lambda: (self.docking.main_moved(), self.dev_tools.window_moved())
        self.window.on_hover = self.update_glass
        self.window.on_state_changed = lambda: self.docking.sync_visibility()
        # The calendar and stats change slowly, so they are worked out again every so many seconds
        self.slow_refresh_ticks = 0
        self.block_drag = BlockDrag(
            self.blocks_by_name(), lambda: self.block_order, self._blocks_reordered, self._save_settings, lambda: self.landscape,
            self.docking, self._moves_window,
        )
        window = self.window
        self.block_drag.watch(window, window.viewport, window.container, window.clip_margin, window.title_bar, self.header, self.module_controls)
        self._arrange_blocks()
        self.settings_page = SettingsPage(self.fonts, self.settings, self._setting_toggled, self._set_orientation, self._settings_resized)
        self.settings_page.exit_button.command = self.close
        self.settings_page.feedback_button.command = self._open_feedback_dialog
        data_copy = bool(app_config.DATA_DIRECTORY_OVERRIDE)
        # Starting with Windows is the installed app's alone: a copy of the data, or a copy run from source, would point
        # the Windows entry at itself
        if data_copy or not getattr(sys, "frozen", False):
            self.settings_page.disabled_settings.update(("launch_on_startup", "start_minimized"))
        self.settings_page.set_google_buttons_enabled(False)
        client = GoogleDriveSync(
            app_config.APP_DATA, resource_path("credentials.json"),
            settings_filename="qt-preview-settings.json" if data_copy else "settings.json",
            activity_filename="qt-preview-activity.sqlite3" if data_copy else "activity.sqlite3",
        )
        self.google_sync = GoogleSync(self, client)
        self.friends_sync = FriendsSync(self, self.friends, FriendsService(client.identity_token))
        if dev:
            # The developer version shows the made-up friends from the start; its menu turns them off
            self.friends_sync.sample_friends = True
            self.friends_sync.refresh_view()
        self.settings_page.backup_button.command = lambda: self._backup_activity_now(force=True)
        self._backup_activity_now()
        self.backup_timer = QTimer(interval=BACKUP_INTERVAL_MS, timeout=self._backup_activity_now)
        self.backup_timer.start()
        self._start_tray_icon()
        self.last_tick_time = tracking_clock()
        self.pending_activity: dict[tuple[str, int, str], tuple[float, str]] = {}
        self.tracking_error: str | None = None
        self.activity_state = (None, False, False)
        self._tick()
        self.tick_timer = QTimer(interval=1000, timeout=self._tick)
        self.tick_timer.start()
        # Cheap focus checks make status changes responsive without repainting charts at 10Hz.
        self.focus_timer = QTimer(interval=100, timeout=self._poll_activity)
        self.focus_timer.start()
        self.poll_timer = QTimer(interval=150, timeout=self._poll_signals)
        self.poll_timer.start()
        self.docking.hover_timer.start()
        self._send_pending_feedback()
        # A copy on its own data folder, run from source or as a test, is not the installed release, so only the real
        # app looks for a newer version
        self.update_timer = QTimer(interval=UPDATE_CHECK_INTERVAL_MS, timeout=self._check_for_updates)
        if not app_config.DATA_DIRECTORY_OVERRIDE:
            self._check_for_updates()
            self.update_timer.start()
        # Windows closing the app, for an installer upgrading it or for signing out or shutting down
        application.commitDataRequest.connect(lambda _manager: self.close())
        # Started minimised at sign-in, it is made as a minimised window, so it has all a shown one has, and then
        # hidden in the tray as minimising does
        minimized = "--minimized" in sys.argv
        if minimized:
            self.window.showMinimized()
        else:
            self.window.show()
        # Where the window was left, and the modules floating then
        self.docking.restore()
        self.apply_always_on_top()
        if minimized:
            self.window.hide()
            self.docking.sync_visibility(hidden=True)

    def _read_block_order(self) -> list[str]:
        """The saved order of the Today panel and modules, with any missing added at the end; it also carries over the
        order kept by versions before 1.0.6"""
        order = self.settings.get("block_order")
        if not isinstance(order, list):
            modules = self.settings.get("module_order")
            modules = [name for name in modules if isinstance(name, str)] if isinstance(modules, list) else []
            before = self.settings.get("modules_left")
            before = before if isinstance(before, list) else []
            order = [name for name in modules if name in before] + ["today"] + [name for name in modules if name not in before]
        # Before the panel followed the program in front, each program had one; the first of them gives its place
        order = ["today" if name in PROGRAMS else name for name in order]
        order = list(dict.fromkeys(name for name in order if name in BLOCK_NAMES))
        return order + [name for name in BLOCK_NAMES if name not in order]

    def _adopt_program_panels(self) -> None:
        """Settings from when each program had a panel of its own: a floating one floats the one panel in its place,
        Photoshop's first"""
        floating = self.settings.get("floating_modules")
        if isinstance(floating, dict):
            place = next((floating[name] for name in PROGRAMS if name in floating), None)
            if place is not None and "today" not in floating:
                floating["today"] = place
            for name in PROGRAMS:
                floating.pop(name, None)
        for key in ("tracking_enabled", "tracking_krita", "tracking_clip_studio_paint", "program_panels_chosen"):
            self.settings.pop(key, None)

    def _backup_activity_now(self, force: bool = False) -> None:
        """Use the shared store's snapshot/retention logic on its owning UI thread."""
        if self.closing:
            return
        try:
            paths = self.store.create_local_backups(force=force)
        except Exception as error:
            self.settings_page.set_backup_status(f"Local backup failed: {error}", "red")
            return
        if len(paths) < len(self.store.backup_directories):
            self.settings_page.set_backup_status("Local backup saved; some backup folders could not be written", "orange")
        else:
            self.settings_page.set_backup_status("Local activity backups saved", "muted")
        self.google_sync.backup(force=force)
        # Undelivered feedback is tried again with each periodic backup, as in the Tk app
        self._send_pending_feedback()

    def restore_activity(self, content: bytes) -> bool:
        """Replace the history with a backup's bytes, returning False (and keeping the history) when they are unusable.
        The store and everything that holds it are swapped here, so a new holder only has to be added here"""
        # A day overview reads the database it was opened with, which is about to be replaced
        for overview in self.window.findChildren(DayOverview):
            overview.close()
        self.store.close()
        try:
            return ActivityStore.restore_backup_bytes(app_config.DATABASE_PATH, content, app_config.BACKUP_DIRECTORIES[0])
        finally:
            self.store = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
            for module in (self.chart, self.calendar, self.stats):
                module.store = self.store

    def _settings_resized(self) -> None:
        if self.settings_shown and hasattr(self, "settings_page"):
            self.window.show_settings(self.settings_page)

    def update_glass(self) -> None:
        """How see-through the window and floating panels are, see Docking.update_glass"""
        self.docking.update_glass()

    def _toggle_settings(self) -> None:
        self.settings_shown = not self.settings_shown
        self.update_glass()
        self.header.settings_shown = self.settings_shown
        self.header.update()
        if self.settings_shown:
            from .settings_page import member_since_text

            since = member_since_text(self.store.first_day())
            if since != self.settings_page.member_since:
                self.settings_page.member_since = since
                self.settings_page._lay_out()
            self.window.show_settings(self.settings_page)
        else:
            self._arrange_blocks()
            self._refresh_visible_modules()

    def _setting_toggled(self, key: str) -> None:
        if key in self.settings_page.disabled_settings:
            return
        value = not bool(self.settings.get(key, DEFAULT_SETTINGS[key]))
        if key in ("launch_on_startup", "start_minimized"):
            launch = value if key == "launch_on_startup" else bool(self.settings.get("launch_on_startup"))
            minimized = value if key == "start_minimized" else bool(self.settings.get("start_minimized"))
            # Start minimized changes the Windows entry only while the app starts with Windows
            if key == "launch_on_startup" or launch:
                try:
                    set_startup(launch, minimized)
                except (OSError, ImportError) as error:
                    QMessageBox.warning(self.window, APP_NAME, f"Could not update Windows startup: {error}")
                    if key == "launch_on_startup":
                        return
        self.settings[key] = value
        if key == "tracking_paused":
            self._tick()
        self._save_settings()
        self.settings_page.update()

    def _title_bar_menu(self, point) -> None:
        if not PopupMenu.opens("title"):
            return
        choices = [("always_on_top", "Always on top", ""), ("minimize", "Minimise to the tray", ""), ("close", "Exit", "")]
        chosen = {"always_on_top": self._toggle_always_on_top, "minimize": self.window_hidden, "close": self.close}
        current = "always_on_top" if self.settings.get("always_on_top") else None
        PopupMenu(self.window, self.fonts, choices, current, lambda key: chosen[key](), opener="title").show_at(point)

    def _toggle_always_on_top(self) -> None:
        self.settings["always_on_top"] = not self.settings.get("always_on_top")
        self._save_settings()
        self.apply_always_on_top()

    def apply_always_on_top(self) -> None:
        """Keep the window and its floating panels above other programs, or not, as the setting says"""
        on = bool(self.settings.get("always_on_top"))
        set_topmost(self.window, on)
        self.window.show_always_on_top(on)
        for panel in self.docking.floating.values():
            if panel is not None:
                panel.topmost = on
                set_topmost(panel, on)

    def _open_transparency(self, area) -> None:
        """The transparency slider, under its icon; a click on the icon while it is open closes it"""
        from .transparency_popup import TransparencyPopup

        if not PopupMenu.opens(TransparencyPopup.OPENER):
            return
        controls = self.module_controls
        popup = TransparencyPopup(self.window, self.fonts, self._transparency, self._transparency_chosen)
        self.transparency_previewing = True
        popup.destroyed.connect(self._transparency_closed)
        self.update_glass()
        # Beside the icon, to its right, over the empty end of the row rather than the panel under it
        popup.show_at(controls.mapToGlobal(QPoint(area.right() + 3, area.top() + (area.height() - popup.height()) // 2)))

    def _transparency_closed(self) -> None:
        self.transparency_previewing = False
        self.update_glass()

    def _transparency(self) -> int:
        try:
            return max(0, min(100, int(self.settings.get("panel_transparency", 0))))
        except (TypeError, ValueError):
            return 0

    def _transparency_chosen(self, value: int, done: bool) -> None:
        """The panels follow the slider as it moves; the setting is saved once it is let go"""
        self.settings["panel_transparency"] = value
        self.module_controls.transparency = value
        self.module_controls.update()
        self.update_glass()
        if done:
            self._save_settings()

    def _set_orientation(self, landscape: bool) -> None:
        """Choosing Portrait or Landscape, even the one already chosen, also docks every floating module and puts
        the blocks back in their first order; which are shown stays as it was. Settings then closes, showing the
        layout chosen"""
        self.docking.dock_all()
        self.block_order = list(BLOCK_NAMES)
        self.settings["block_order"] = self.block_order.copy()
        self.landscape = landscape
        self.landscape_width = None
        self.settings["landscape"] = landscape
        self._save_settings()
        self.settings_page.update()
        if self.settings_shown:
            self._toggle_settings()

    def _refresh_visible_modules(self) -> None:
        if self.settings_shown or not self.window.isVisible() or self.window.isMinimized():
            self.modules_were_hidden = True
            return
        self.modules_were_hidden = False
        for name in MODULE_NAMES:
            if self.module_ticked[name]:
                self._refresh_module(name)

    def _arrange_blocks(self) -> None:
        """Show the shown blocks in their order, one under another or in landscape side by side, every column then
        stretched to the same height"""
        if self.settings_shown:
            return
        self.arranging = True
        try:
            anchor = self._anchor_panel()
            # The stats' lines set how tall they need to be, which the height in landscape follows
            self._refresh_stats()
            if self.landscape:
                height = self._landscape_height(anchor)
                if anchor is not None:
                    # The panel under the header is shorter by the header's height, so its column ends level too
                    self.today.set_stretch(height - (self.today.natural_height - 2) - self._header_overhead())
            else:
                height = 0
                self.today.set_stretch(0)
            for name, module in self.modules.items():
                # A floating module keeps the portrait layout, having no columns to share a height with
                if not self.docking.is_floating(name):
                    module.set_layout(self.landscape, height)
            if self.landscape and self.docking.preview_slot is not None:
                # The space for a module being docked stands as tall as the columns, as the module will
                self.docking.preview.setFixedSize(self.docking.preview.width(), height + 2)
            for name in ("graph", "calendar"):
                if self.module_ticked[name]:
                    self._refresh_module(name)
            self.window.show_blocks(self._shown_blocks(), anchor, any(self.module_ticked.values()), self.landscape, self.landscape_width)
        finally:
            self.arranging = False

    def _header_overhead(self) -> int:
        """Height the header and module checkboxes add on top of the anchor panel in landscape"""
        return self.window.top_height() + MODULE_GAP

    def _landscape_height(self, anchor: TodayPanel | None) -> int:
        """Height every column shares in landscape, inside the blocks' borders: what the tallest of them needs,
        counting the header and checkboxes on top of the anchor panel, so every column ends level"""
        today_height = self.today.natural_height - 2
        overhead = self._header_overhead()
        # With no anchor panel the header stands alone: its height, less a block's border of a pixel each side
        column = today_height + overhead if anchor is not None else overhead - MODULE_GAP - 2
        stats = self.stats.landscape_height() if self._block_shown("stats") else 0
        graph = self.chart.landscape_height() if not self.docking.is_floating("graph") else 0
        # The calendar and friends fit themselves to this height, the friends list scrolling, so neither sets it
        return max(graph, stats, today_height, column)

    def _block_resized(self) -> None:
        # A module growing or shrinking, such as the stats gaining a line, changes the size the window needs, and in
        # landscape the height every column shares
        if self.arranging:
            return
        if self.landscape:
            self._arrange_blocks()
        else:
            self.window.refit()

    def _window_width_chosen(self, width: int) -> None:
        self.landscape_width = width if width < self.window.full_size()[0] else None

    def blocks_by_name(self) -> dict:
        return {"today": self.today, **self.modules}

    def _moves_window(self, widget) -> bool:
        """Whether a press on this part of the window, not a block, moves it: the header and checkbox rows, the gaps
        and margins; not the Settings page"""
        window = self.window
        return widget in (window, window.viewport, window.container, window.clip_margin, window.title_bar, self.header, self.module_controls)

    def _shown_blocks(self) -> list:
        blocks = self.blocks_by_name()
        return self.docking.shown_with_preview([blocks[name] for name in self.block_order if self._block_shown(name)])

    def _anchor_panel(self) -> TodayPanel | None:
        """The program panel, kept in view under the header as the window gets shorter; none while it floats"""
        return self.today if self._block_shown("today") else None

    def _blocks_reordered(self, order: list[str]) -> None:
        # Kept when the drag ends, see BlockDrag
        self.block_order = order
        self.settings["block_order"] = order.copy()
        self.window.reorder_blocks(self._shown_blocks())

    def _block_wanted(self, name: str) -> bool:
        """A module ticked in the checkboxes, in the window or floating; the program panel always"""
        return self.module_ticked.get(name, True)

    def _block_shown(self, name: str) -> bool:
        """Wanted, and in the window rather than floating"""
        return self._block_wanted(name) and not self.docking.is_floating(name)

    def _module_toggled(self, name: str) -> None:
        self.settings[f"show_{name}"] = self.module_ticked[name]
        self._save_settings()
        self._arrange_blocks()
        self.docking.sync_visibility()
        if self.module_ticked[name]:
            self._refresh_module(name)

    def _refresh_module(self, name: str) -> None:
        # A program panel is brought up to date every second anyway
        if name == "today":
            return
        if name == "graph":
            self.chart.refresh()
        elif name == "calendar":
            self.calendar.refresh()
        elif name == "friends":
            # Blocks are first arranged before the friends sync is made
            if hasattr(self, "friends_sync"):
                self.friends_sync.refresh_view()
        else:
            self._refresh_stats()

    def _refresh_stats(self) -> None:
        if self.module_ticked["stats"]:
            self.stats.refresh(self.calendar.view, self.calendar.month)

    def _open_day_overview(self, session_day: date) -> None:
        DayOverview(self.window, self.fonts, self.store, session_day, self._set_productivity_rating).show_centred_on(self.window)

    def _set_productivity_rating(self, session_day: date, rating: int) -> None:
        """Rate a day from 1 to 10; choosing the rating it already has clears it"""
        if self.store.productivity_rating(session_day) == rating:
            self.store.clear_productivity_rating(session_day)
        else:
            self.store.set_productivity_rating(session_day, rating)
        if self.module_ticked["calendar"]:
            self.calendar.refresh()
        # The best start time depends on the ratings, so it follows a change straight away
        self._refresh_stats()

    def _period_chosen(self, period: str) -> None:
        self.settings["period"] = period
        self._save_settings()

    def _save_settings(self, upload: bool = True) -> None:
        """Save the settings, and back them up to Google Drive when connected unless told not to"""
        app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
        temporary = app_config.SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        temporary.replace(app_config.SETTINGS_PATH)
        # Settings are first saved while the window is built, before Google sync exists
        if upload and hasattr(self, "google_sync"):
            self.google_sync.settings_changed()

    def _follow_program(self, application: str | None) -> None:
        """The panel turns to the program in front; with none in front it keeps the last"""
        if application not in PROGRAMS or application == self.today.application:
            return
        self.today.set_application(application)
        self.docking.retitle("today")
        self.settings["today_program"] = application
        self._save_settings(upload=False)

    def _select_program(self, application: str) -> None:
        if application not in PROGRAMS:
            return
        self.manual_program = True
        self._follow_program(application)
        self._track_and_refresh()

    def _start_tray_icon(self) -> None:
        self.tray_menu = QMenu()
        show = QAction("Show PS Focus", self.tray_menu, triggered=self.show_window)
        self.tray_menu.addAction(show)
        self.tray_menu.setDefaultAction(show)
        self.tray_menu.addAction(QAction("Exit", self.tray_menu, triggered=self.close))
        self.tray_icon = QSystemTrayIcon(QIcon(str(resource_path("assets/icons/PSFocus_Settings_64.png"))))
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_icon.setContextMenu(self.tray_menu)
        # A left click shows the window, as with the Tk app's tray icon
        self.tray_icon.activated.connect(
            lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray_icon.show()

    def window_hidden(self) -> None:
        self.docking.save_positions()
        self.window.hide()
        self.docking.sync_visibility(hidden=True)

    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        self.docking.sync_visibility()
        self._refresh_visible_modules()

    def _poll_signals(self) -> None:
        self.google_sync.poll()
        self.friends_sync.poll()
        while True:
            try:
                kind, value = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "update":
                self._show_available_update(value)
        if self.instance is None:
            return
        # Starting the app a second time brings up this copy's window instead
        if self.instance.show_requested():
            self.show_window()
        # The installer asks the app to close before replacing its files
        if self.instance.exit_requested():
            self.close()

    def _tick(self, activity_state=None) -> None:
        if self.closing:
            return
        try:
            self._track_and_refresh(activity_state)
        except Exception as error:
            self.tracking_error = str(error)
            self.today.set_text("status", "TRACKING ERROR", "red")
            self.today.setToolTip("Tracking could not save or refresh: " + str(error))
            # One failed update must not stop tracking for good; the timer keeps calling
            import traceback

            traceback.print_exc()

    def _read_activity_state(self) -> tuple[str | None, bool, bool]:
        """The program in front, whether the user has been active lately, and whether tracking is paused"""
        return foreground_application(), user_is_active(IDLE_TIMEOUT_SECONDS), bool(self.settings.get("tracking_paused"))

    def _pending_rows(self) -> list[tuple]:
        return [(day, slot, seconds, program, first) for (day, slot, program), (seconds, first) in self.pending_activity.items()]

    def _poll_activity(self) -> None:
        if self.closing:
            return
        state = self._read_activity_state()
        if state != self.activity_state:
            self._tick(state)

    def _credit_active_time(self, application: str | None) -> None:
        now = tracking_clock()
        elapsed = max(0.0, min(now - self.last_tick_time, MAX_TICK_CREDIT_SECONDS))
        self.last_tick_time = max(self.last_tick_time, now)
        if application is not None and elapsed > 0:
            start = datetime.now() - timedelta(seconds=elapsed)
            for day, slot, seconds, program, started_at in activity_slices(start, elapsed, application):
                key = (day, slot, program)
                pending, first = self.pending_activity.get(key, (0.0, started_at))
                self.pending_activity[key] = (round(pending + seconds, 6), min(first, started_at))
        if self.pending_activity:
            self.store.record_activity(self._pending_rows())
            self.pending_activity.clear()
        self.tracking_error = None
        self.today.setToolTip("")

    def _track_and_refresh(self, activity_state=None) -> None:
        if activity_state is None:
            activity_state = self._read_activity_state()
        # Elapsed time belongs to the previously observed foreground state.
        previous_program, previous_present, previous_paused = self.activity_state
        foreground_app, idle_active, paused = activity_state
        self.activity_state = activity_state
        self.active = not paused and foreground_app is not None and idle_active
        self._credit_active_time(previous_program if previous_present and not previous_paused else None)
        if self.active:
            self.manual_program = False
        if self.active or not self.manual_program:
            self._follow_program(foreground_app)
        now = time.monotonic()
        if now - self.open_programs_checked >= 1:
            self.open_programs = running_applications()
            self.open_programs_checked = now
        open_programs = self.open_programs | ({foreground_app} if foreground_app else set())
        today = date.today()
        total_today_seconds = self.store.total_for_day(today)
        lifetime_seconds = self.store.total_seconds()
        application = self.today.application
        today_seconds = self.store.total_for_day(today, application)
        two_weeks_seconds = self.store.total_for_range(today - timedelta(days=13), today, application)
        total_seconds = self.store.total_seconds(application)
        last_session = self.store.last_recorded_day(application)
        self.today.set_text("total", format_duration(today_seconds))
        self.today.set_text("two_week", f"{two_weeks_seconds / 3600:.1f} hrs past 2 weeks")
        self.today.set_text("sessions", f"{self.store.lifetime_sessions(application=application)} SESSIONS")
        self.today.set_text("record_hours", f"{total_seconds / 3600:.1f} hrs on record")
        last_session_text = last_session.strftime("%d %b").lstrip("0") if last_session else "--"
        self.today.set_text("last_session", f"last session on {last_session_text}")
        app_active = self.active and foreground_app == application
        self.today.set_text("name", application, "active_green" if app_active else "name_online" if application in open_programs else "muted")
        self.today.set_text(
            "status",
            "PAUSED" if paused else "",
            "muted",
        )
        self.header.set_progress_reached(total_today_seconds >= SESSION_MINIMUM_SECONDS)
        level = user_level(lifetime_seconds)
        self.header.set_level(level, self.level_revealed)
        self.header.set_level_tip(level_xp_text(lifetime_seconds) if self.level_revealed else "")
        self.update_glass()
        self._celebrate_level_up(level)
        override = self.feedback_unlock_override
        self._set_feedback_unlocked(lifetime_seconds >= FEEDBACK_UNLOCK_SECONDS if override is None else override)
        self.friends_sync.tick(foreground_app if self.active else None, idle_active)
        # Tracking continues in the tray and Settings; drawing the modules out of sight waits for them to show.
        # Floating ones stay in view with Settings open, so they keep up
        if self.window.isVisible() and not self.window.isMinimized() and self.settings_shown:
            self._refresh_floating_modules(today)
        if self.settings_shown or not self.window.isVisible() or self.window.isMinimized():
            self.modules_were_hidden = True
            return
        refreshed_on_restore = self.modules_were_hidden
        if refreshed_on_restore:
            self._refresh_visible_modules()
        # The graph moves on with the time being counted, and with a new day
        if self.module_ticked["graph"] and (refreshed_on_restore or self.active or self.chart_drawn_day != today):
            if not refreshed_on_restore:
                self.chart.refresh()
            self.chart_drawn_day = today
        # As in the Tk app, the calendar and stats are brought up to date every 15 seconds
        if not refreshed_on_restore and self.slow_refresh_ticks % 15 == 0:
            for name in ("calendar", "stats", "friends"):
                if self.module_ticked[name]:
                    self._refresh_module(name)
        self.slow_refresh_ticks += 1

    def _refresh_floating_modules(self, today: date) -> None:
        """While Settings is open: the floating graph moves on with the time counted, the rest every 15 seconds"""
        if self.docking.is_floating("graph") and self.module_ticked["graph"] and (self.active or self.chart_drawn_day != today):
            self.chart.refresh()
            self.chart_drawn_day = today
        if self.slow_refresh_ticks % 15 == 0:
            for name in ("calendar", "stats", "friends"):
                if self.docking.is_floating(name) and self.module_ticked[name]:
                    self._refresh_module(name)
        self.slow_refresh_ticks += 1

    def _set_feedback_unlocked(self, unlocked: bool) -> None:
        """Feedback opens once enough time has been tracked: Settings shows Got feedback?, and the level, until it is
        revealed, opens the form"""
        self.feedback_unlocked = unlocked
        self.settings_page.set_feedback_shown(unlocked)
        self.header.level_clickable = unlocked and not self.level_revealed

    def _level_clicked(self) -> None:
        if self.feedback_unlocked and not self.level_revealed:
            self._open_feedback_dialog(reveal_prompt=True)

    def _open_feedback_dialog(self, reveal_prompt: bool = False) -> None:
        dialog = FeedbackDialog(
            self.window, self.fonts, self.feedback, self._feedback_cooldown_remaining, self._feedback_submitted, reveal_prompt
        )
        dialog.show_centred_on(self.window)

    def _feedback_cooldown_remaining(self) -> timedelta | None:
        try:
            cooldown_until = datetime.fromisoformat(self.settings.get("feedback_cooldown_until") or "")
        except (TypeError, ValueError):
            return None
        remaining = cooldown_until - datetime.now()
        return remaining if remaining > timedelta(0) else None

    def _feedback_submitted(self) -> None:
        """Count the feedback, sending it on and revealing the level; from the second one on, more waits a while"""
        self._send_pending_feedback()
        count = int(self.settings.get("feedback_count") or 0)
        if count == 0 and self.settings.get("feedback_submitted"):
            # Feedback sent before submissions were counted was the first one
            count = 1
        count += 1
        self.settings["feedback_count"] = count
        if count >= 2:
            self.settings["feedback_cooldown_until"] = (datetime.now() + FEEDBACK_COOLDOWN).isoformat(timespec="seconds")
        self.settings["feedback_submitted"] = True
        self._save_settings()
        self.level_revealed = True
        self.header.level_clickable = False
        if self.header.badge_state is not None:
            self.header.set_level(self.header.badge_state[0], True)

    def _send_pending_feedback(self) -> None:
        # Feedback tried out in the developer version stays on this PC
        if self.dev or self.feedback_send_in_progress or not self.feedback.configured or not self.feedback.pending():
            return
        self.feedback_send_in_progress = True
        threading.Thread(target=self._feedback_worker, daemon=True).start()

    def _feedback_worker(self) -> None:
        try:
            self.feedback.send_pending()
        except Exception:
            # Undelivered feedback stays in the outbox and is retried with the next periodic backup
            pass
        finally:
            self.feedback_send_in_progress = False

    def goal_reached(self) -> None:
        """Today has just reached the session minimum: the dot by the name pulses and today's square fills blue"""
        self.header.pulse_progress_dot()
        if self.module_ticked["calendar"]:
            self.calendar.fill_today()

    def _celebrate_level_up(self, level: int) -> None:
        """Celebrate when the level has risen since the last tick; the first tick only sets the starting point"""
        previous, self.celebrated_level = self.celebrated_level, level
        if previous is not None and level > previous:
            # The developer version counts the same drawing as the normal app beside it, so both rise together; two
            # fanfares a moment apart sound broken. Its level-ups stay quiet unless asked for from its menu
            self.celebrate(sound=not self.dev or self.dev_level_up_requested)
            self.dev_level_up_requested = False

    def celebrate(self, sound: bool = True) -> None:
        if self.fireworks is not None and not self.fireworks.finished:
            # A show is already running; restarting the sound alone would knock it out of step with the bursts
            return
        # With the window hidden in the tray or minimized there is nowhere to draw them, so only the sound plays
        if self.window.isVisible() and not self.window.isMinimized():
            origin = self.window.mapFromGlobal(self.header.mapToGlobal(self.header.badge_center()))
            self.fireworks = Fireworks(self.window, origin)
        if sound and not self.settings.get("disable_fanfare_sound"):
            play_celebration_sound()

    def _check_for_updates(self) -> None:
        threading.Thread(target=self._update_check_worker, daemon=True).start()

    def _update_check_worker(self) -> None:
        try:
            update = available_update(app_config.APP_VERSION)
        except RuntimeError:
            # Offline or the endpoint is unavailable; the next daily check tries again
            return
        if update is not None:
            self.results.put(("update", update))

    def _show_available_update(self, update: tuple[str, str]) -> None:
        """The version at the top of Settings becomes a link to the new one; the first time, the tray says so too"""
        self.available_update = update
        self.header.version_text, self.header.version_is_link = f"Get version {update[0]}", True
        self.header.update()
        if not self.update_announced:
            self.update_announced = True
            self.tray_icon.showMessage("PS Focus update", f"Version {update[0]} is available. Open Settings to download it")

    def _open_update_page(self) -> None:
        if self.available_update is not None and is_safe_download_url(self.available_update[1]):
            webbrowser.open(self.available_update[1])

    def close(self) -> None:
        # Windows and the tray may both ask, so only the first request closes
        if self.closing:
            return
        self.closing = True
        # Should the final backup stall, on an unreachable folder for instance, the app still ends
        watchdog = threading.Timer(EXIT_TIMEOUT_SECONDS, os._exit, (0,))
        watchdog.daemon = True
        watchdog.start()
        self.tick_timer.stop()
        self.focus_timer.stop()
        self.poll_timer.stop()
        self.docking.hover_timer.stop()
        self.backup_timer.stop()
        self.update_timer.stop()
        try:
            program, present, paused = self.activity_state
            self._credit_active_time(program if present and not paused else None)
        except Exception:
            # Keep failed writes for recovery on next launch; don't silently drop them.
            if self.pending_activity:
                try:
                    self.store.save_pending_activity(self._pending_rows())
                except Exception:
                    import traceback
                    traceback.print_exc()
        if self.fireworks is not None:
            self.fireworks.stop()
        self.docking.save_positions()
        self.docking.sync_visibility(hidden=True)
        self.window.hide()
        self.tray_icon.hide()
        try:
            self.store.create_local_backups()
        except Exception:
            pass
        self.store.close()
        self.application.quit()


class InstantTips(QProxyStyle):
    """The app's look, with tooltips shown as soon as the mouse is over what they explain"""

    def styleHint(self, hint, option=None, widget=None, return_data=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return 0
        return super().styleHint(hint, option, widget, return_data)


def main(data_copy: bool, smoke_test: bool = False, dev: bool = False) -> None:
    from windows_startup import set_app_user_model_id

    if dev:
        # Its own taskbar button, beside PS Focus's
        set_app_user_model_id("PSFocus.PSFocus.Dev")
    elif data_copy:
        # The "Preview" in this id, the window title and the data-copy file names is kept as it was, since Windows
        # and the saved files already know those names
        set_app_user_model_id("PSFocus.PSFocus.QtPreview")
    else:
        set_app_user_model_id()
    instance = None
    # The build's start-up check runs beside any PS Focus already open, and never touches Windows startup
    if not data_copy and not smoke_test:
        instance = SingleInstance()
        if instance.already_running:
            if "--minimized" not in sys.argv:
                instance.ask_running_copy_to_show()
            return
    if not data_copy and not smoke_test and getattr(sys, "frozen", False):
        # As the Tk app did: settings, history and sign-in carried over from the app's earlier name; on a first run
        # the Windows startup entry the installer was asked for; otherwise the entry pointed at this copy
        migrate_legacy_app_data()
        first_run = not app_config.SETTINGS_PATH.exists()
        settings = load_settings()
        migrate_legacy_startup(settings)
        if first_run:
            apply_first_run_startup(settings)
        else:
            refresh_startup_entry(settings)
        # The Tk versions before 1.1 unpacked themselves on every start; folders left by runs ended by force go
        threading.Thread(target=remove_stale_unpack_folders, daemon=True).start()
    app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
    application = QApplication(sys.argv)
    # Hidden in the tray the app keeps running
    application.setQuitOnLastWindowClosed(False)
    application.setApplicationName(APP_NAME)
    # The small tooltips on buttons are dark like the app's own tips, see hover_tip
    application.setStyleSheet("QToolTip { background: #151515; color: #eef3f1; border: 1px solid #2c2c2c; padding: 4px 6px; }")
    # And at once, as the calendar's and friends' own tips, rather than after Windows' usual wait
    application.setStyle(InstantTips())
    app = PSFocusQt(application, instance, dev)
    if dev:
        app.window.setWindowTitle("PS Focus Dev")
        app.tray_icon.setToolTip("PS Focus Dev")
    elif data_copy:
        app.window.setWindowTitle("PS Focus Qt Preview")
        app.tray_icon.setToolTip("PS Focus Qt Preview")
    if smoke_test:
        # Web requests use Windows' WinHTTP rather than OpenSSL; check it loads and opens a session (no request is sent)
        import web

        web._winhttp.WinHttpCloseHandle(web._open_session())
        # Google sign-in waits for its answer on a local listener, whose setting up needs Windows host names and so
        # the idna encoding; anything left out of the build that it needs shows here, not at a user's sign-in
        import http.server

        http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler).server_close()
        # Exercise the packed painter/assets/plugins, not just a default empty dashboard.
        application.processEvents()
        if app.window.windowIcon().pixmap(32, 32).isNull() or app.tray_icon.icon().pixmap(32, 32).isNull():
            raise RuntimeError("Packaged icons could not be decoded")
        for name in MODULE_NAMES:
            app.module_ticked[name] = True
        for landscape in (False, True):
            app.landscape = landscape
            app._arrange_blocks()
            application.processEvents()
            # The friends module draws as it paints, with no picture made ahead
            if any(module.picture is None or module.picture.isNull() for name, module in app.modules.items() if name != "friends"):
                raise RuntimeError("Packaged module rendering failed")
        app._toggle_settings()
        app._toggle_settings()
        QTimer.singleShot(250, app.close)
    application.exec()
    del app
