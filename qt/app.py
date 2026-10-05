"""PS Focus on Qt: the tracking loop, the window and the tray icon"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import app_config
from app_config import (
    APP_NAME,
    MODULE_GAP,
    CHART_PERIODS,
    DEFAULT_SETTINGS,
    FEEDBACK_UNLOCK_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    MAX_TICK_CREDIT_SECONDS,
    PROGRAM_PANEL_SETTINGS,
    SESSION_MINIMUM_SECONDS,
    format_duration,
    load_settings,
    resource_path,
    user_level,
)
from tracker import ActivityStore, foreground_application, user_is_active
from windows_startup import SingleInstance

from .block_drag import BlockDrag
from .calendar_module import CalendarModule
from .chart import ChartModule
from .day_overview import DayOverview
from .header import Header, ModuleControls
from .stats_module import StatsModule
from .theme import Fonts
from .today_panel import TodayPanel
from .window import MainWindow

# Every block that can be put in order: the program panels and the modules, as in the Tk ui_modules
MODULE_NAMES = ("graph", "calendar", "stats")
BLOCK_NAMES = tuple(PROGRAM_PANEL_SETTINGS) + MODULE_NAMES
# Longest the app may take to close after Exit before it is ended regardless
EXIT_TIMEOUT_SECONDS = 10


class PSFocusQt:
    def __init__(self, application: QApplication, instance: SingleInstance | None = None) -> None:
        self.application = application
        self.instance = instance
        self.closing = False
        self.settings = load_settings()
        # One program panel is always shown; settings from before that rule may have none, so Photoshop's comes back
        if not any(self.settings.get(key) for key in PROGRAM_PANEL_SETTINGS.values()):
            self.settings["tracking_enabled"] = True
        self.block_order = self._read_block_order()
        self.store = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
        self.fonts = Fonts()
        self.active = False
        self.level_revealed = bool(self.settings.get("feedback_submitted"))
        self.feedback_unlocked = False
        self.landscape = bool(self.settings.get("landscape", False))
        # In landscape, a width the user dragged the window narrower to, kept while blocks come and go until the
        # window is dragged as wide as everything again
        self.landscape_width: int | None = None
        self.arranging = False
        self.window = MainWindow(on_close=self.window_hidden, on_resized_by_user=self._window_width_chosen)
        self.header = Header(self.fonts)
        self.module_ticked = {name: bool(self.settings.get(f"show_{name}", True)) for name in MODULE_NAMES}
        self.module_controls = ModuleControls(self.fonts, self.module_ticked, self._module_toggled)
        self.window.set_top(self.header, self.module_controls)
        # Made without a parent, so a panel stays out of sight until the window's column takes it in
        self.panels = {name: TodayPanel(name, self.fonts) for name in PROGRAM_PANEL_SETTINGS}
        period = self.settings.get("period")
        self.chart = ChartModule(self.fonts, self.store, period if period in CHART_PERIODS else "Day", self._period_chosen)
        self.chart_drawn_day: date | None = None
        self.calendar = CalendarModule(self.fonts, self.store, self._open_day_overview, self._refresh_stats, self._block_resized)
        self.stats = StatsModule(self.fonts, self.store, self._block_resized)
        self.modules = {"graph": self.chart, "calendar": self.calendar, "stats": self.stats}
        # The calendar and stats change slowly, so they are worked out again every so many seconds
        self.slow_refresh_ticks = 0
        self.block_drag = BlockDrag(
            {**self.panels, **self.modules}, lambda: self.block_order, self._blocks_reordered, self._save_settings, lambda: self.landscape
        )
        self._arrange_blocks()
        self._start_tray_icon()
        self.last_tick_time = time.monotonic()
        self.unrecorded_active_seconds = 0.0
        self._tick()
        self.tick_timer = QTimer(interval=1000, timeout=self._tick)
        self.tick_timer.start()
        self.poll_timer = QTimer(interval=150, timeout=self._poll_signals)
        self.poll_timer.start()
        # Windows closing the app, for an installer upgrading it or for signing out or shutting down
        application.commitDataRequest.connect(lambda _manager: self.close())
        if "--minimized" in sys.argv:
            self.window.showMinimized()
        else:
            self.window.show()
        self.window.place_top_right()

    def _read_block_order(self) -> list[str]:
        """The saved order of the program panels and modules, with any missing added at the end; see the Tk
        PSFocusApp._read_block_order, which also carries over the order kept by versions before 1.0.6"""
        order = self.settings.get("block_order")
        order = order if isinstance(order, list) else list(BLOCK_NAMES)
        order = list(dict.fromkeys(name for name in order if name in BLOCK_NAMES))
        return order + [name for name in BLOCK_NAMES if name not in order]

    def _arrange_blocks(self) -> None:
        """Show the shown blocks in their order, one under another or in landscape side by side, every column then
        stretched to the same height"""
        self.arranging = True
        try:
            anchor = self._anchor_panel()
            # The stats' lines set how tall they need to be, which the height in landscape follows
            self._refresh_stats()
            if self.landscape:
                height = self._landscape_height(anchor)
                today_height = next(iter(self.panels.values())).natural_height - 2
                for panel in self.panels.values():
                    # The panel under the header is shorter by the header's height, so its column ends level too
                    panel.set_stretch(height - today_height - (self._header_overhead() if panel is anchor else 0))
            else:
                height = 0
                for panel in self.panels.values():
                    panel.set_stretch(0)
            for module in self.modules.values():
                module.set_layout(self.landscape, height)
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
        today_height = next(iter(self.panels.values())).natural_height - 2
        overhead = self._header_overhead()
        # With no anchor panel the header stands alone: its height, less a block's border of a pixel each side
        column = today_height + overhead if anchor is not None else overhead - MODULE_GAP - 2
        stats = self.stats.landscape_height() if self.module_ticked["stats"] else 0
        return max(self.chart.landscape_height(), stats, today_height, column)

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

    def _shown_blocks(self) -> list:
        blocks = {**self.panels, **self.modules}
        return [blocks[name] for name in self.block_order if self._block_shown(name)]

    def _anchor_panel(self) -> TodayPanel | None:
        """The program panel kept in view under the header as the window gets shorter: Photoshop's when it is
        shown, otherwise the first shown, or none"""
        shown = [name for name in self.block_order if name in self.panels and self._block_shown(name)]
        if not shown:
            return None
        return self.panels["Photoshop" if "Photoshop" in shown else shown[0]]

    def _blocks_reordered(self, order: list[str]) -> None:
        # Kept when the drag ends, see BlockDrag
        self.block_order = order
        self.settings["block_order"] = order.copy()
        self.window.reorder_blocks(self._shown_blocks())

    def _block_shown(self, name: str) -> bool:
        """A module ticked in the checkboxes, or a program panel ticked in Settings"""
        if name in self.module_ticked:
            return self.module_ticked[name]
        return bool(self.settings.get(PROGRAM_PANEL_SETTINGS[name]))

    def _module_toggled(self, name: str) -> None:
        self.settings[f"show_{name}"] = self.module_ticked[name]
        self._save_settings()
        self._arrange_blocks()
        if self.module_ticked[name]:
            self._refresh_module(name)

    def _refresh_module(self, name: str) -> None:
        if name == "graph":
            self.chart.refresh()
        elif name == "calendar":
            self.calendar.refresh()
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

    def _save_settings(self) -> None:
        app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
        temporary = app_config.SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        temporary.replace(app_config.SETTINGS_PATH)

    def _chosen_panels(self) -> list[str]:
        chosen = self.settings.get("program_panels_chosen")
        return [name for name in chosen if isinstance(name, str)] if isinstance(chosen, list) else []

    def _reveal_panel_on_first_use(self, application: str) -> None:
        """Switch on a program's panel the first time the program is used, so its time is not counted unseen; a
        panel the user has shown or hidden by hand is left alone, see the Tk version"""
        key = PROGRAM_PANEL_SETTINGS[application]
        if self.settings.get(key) or DEFAULT_SETTINGS[key] or application in self._chosen_panels():
            return
        self.settings[key] = True
        self.settings["program_panels_chosen"] = self._chosen_panels() + [application]
        self._save_settings()
        self._arrange_blocks()

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
        self.window.hide()

    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _poll_signals(self) -> None:
        if self.instance is None:
            return
        # Starting the app a second time brings up this copy's window instead
        if self.instance.show_requested():
            self.show_window()
        # The installer asks the app to close before replacing its files
        if self.instance.exit_requested():
            self.close()

    def _tick(self) -> None:
        try:
            self._track_and_refresh()
        except Exception:
            # One failed update must not stop tracking for good; the timer keeps calling
            import traceback

            traceback.print_exc()

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
        total_today_seconds = lifetime_seconds = 0
        for name, panel in self.panels.items():
            today_seconds = self.store.total_for_day(today, name)
            two_weeks_seconds = self.store.total_for_range(today - timedelta(days=13), today, name)
            total_seconds = self.store.total_seconds(name)
            last_session = self.store.last_recorded_day(name)
            total_today_seconds += today_seconds
            lifetime_seconds += total_seconds
            panel.set_text("total", format_duration(today_seconds))
            panel.set_text("two_week", f"{two_weeks_seconds / 3600:.1f} hours past 2 weeks")
            panel.set_text("sessions", f"{self.store.lifetime_sessions(application=name)} SESSIONS")
            panel.set_text("record_hours", f"{total_seconds / 3600:.1f} hrs on record")
            last_session_text = last_session.strftime("%d %b").lstrip("0") if last_session else "--"
            panel.set_text("last_session", f"last session on {last_session_text}")
            app_active = self.active and foreground_app == name
            panel.set_text(
                "status",
                "ACTIVE" if app_active else "PAUSED" if paused else "NOT ACTIVE",
                "active_green" if app_active else "muted",
            )
        self.header.set_progress_reached(total_today_seconds >= SESSION_MINIMUM_SECONDS)
        self.header.set_level(user_level(lifetime_seconds), self.level_revealed)
        # The graph moves on with the time being counted, and with a new day
        if self.module_ticked["graph"] and (self.active or self.chart_drawn_day != today):
            self.chart.refresh()
            self.chart_drawn_day = today
        # As in the Tk app, the calendar and stats are brought up to date every 15 seconds
        if self.slow_refresh_ticks % 15 == 0:
            for name in ("calendar", "stats"):
                if self.module_ticked[name]:
                    self._refresh_module(name)
        self.slow_refresh_ticks += 1
        self.feedback_unlocked = lifetime_seconds >= FEEDBACK_UNLOCK_SECONDS
        # The level opens the feedback form once feedback is unlocked, until the level is revealed
        self.header.level_clickable = self.feedback_unlocked and not self.level_revealed

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
        self.poll_timer.stop()
        self.window.hide()
        self.tray_icon.hide()
        try:
            self.store.create_local_backups()
        except Exception:
            pass
        self.store.close()
        self.application.quit()


def main(preview: bool) -> None:
    from windows_startup import set_app_user_model_id

    set_app_user_model_id()
    instance = None
    if not preview:
        instance = SingleInstance()
        if instance.already_running:
            if "--minimized" not in sys.argv:
                instance.ask_running_copy_to_show()
            return
    app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
    application = QApplication(sys.argv)
    # Hidden in the tray the app keeps running
    application.setQuitOnLastWindowClosed(False)
    application.setApplicationName(APP_NAME)
    app = PSFocusQt(application, instance)
    application.exec()
    del app
