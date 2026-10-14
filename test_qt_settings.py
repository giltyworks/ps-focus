"""Settings navigation and tracking while the Qt dashboard is out of view."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        import app_config
        from qt.app import PSFocusQt

        self.start_tray_icon = PSFocusQt._start_tray_icon

        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        self.patches = [
            patch.object(app_config, "APP_DATA", folder),
            patch.object(app_config, "DATABASE_PATH", folder / "activity.sqlite3"),
            patch.object(app_config, "SETTINGS_PATH", folder / "settings.json"),
            patch.object(app_config, "BACKUP_DIRECTORIES", [folder / "backups"]),
            patch("qt.app.load_settings", return_value={**app_config.DEFAULT_SETTINGS, "show_graph": True, "show_calendar": True, "show_stats": True}),
            patch("qt.app.foreground_application", return_value=None),
            patch.object(PSFocusQt, "_start_tray_icon"),
            # The daily update check would go to the network
            patch.object(PSFocusQt, "_check_for_updates"),
            patch("qt.window.MainWindow.place_top_right"),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temporary.cleanup)
        for item in self.patches:
            self.addCleanup(item.stop)
        self.app = PSFocusQt(self.application)
        self.app.tick_timer.stop()
        self.app.focus_timer.stop()
        self.app.poll_timer.stop()
        self.app.backup_timer.stop()
        self.addCleanup(lambda: self.app.store.close())
        self.addCleanup(self.app.window.hide)
        self.application.processEvents()

    def test_choosing_an_orientation_closes_settings_on_that_layout(self):
        for landscape in (False, True):
            self.app._toggle_settings()
            self.assertTrue(self.app.settings_page.isVisible())
            self.assertFalse(self.app.window.viewport.isVisible())
            self.assertFalse(self.app.module_controls.isVisible())
            self.assertEqual(self.app.window.minimumSize(), self.app.window.maximumSize())
            self.app._set_orientation(landscape)
            self.assertFalse(self.app.settings_shown)
            self.assertFalse(self.app.header.settings_shown)
            self.assertEqual(self.app.window.landscape, landscape)
            self.assertTrue(self.app.window.viewport.isVisible())
            self.assertTrue(self.app.module_controls.isVisible())
            self.assertFalse(self.app.settings_page.isVisible())

    def test_panel_follows_the_program_in_front_and_keeps_the_last(self):
        self.app.store.record_active_second(application="Krita")
        with patch("qt.app.foreground_application", return_value="Krita"), patch("qt.app.user_is_active", return_value=False):
            self.app._track_and_refresh()
        panel = self.app.today
        self.assertEqual((panel.application, panel.texts["name"].text), ("Krita", "Krita"))
        self.assertEqual(panel.texts["total"].text, "1s")
        self.assertEqual(self.app.settings["today_program"], "Krita")
        with patch("qt.app.foreground_application", return_value=None):
            self.app._track_and_refresh()
        self.assertEqual(panel.application, "Krita")

    def test_settings_saved_by_an_older_version_survive_an_update(self):
        # A settings file as 1.1.0 left it, with every choice changed from the default and a key from a later
        # version unknown here; an update must keep every choice, carrying the old program panel settings over
        import json
        import app_config
        from qt.app import PSFocusQt

        chosen = {
            "panel_transparency": 70, "always_on_top": True, "landscape": True, "period": "Month",
            "show_graph": False, "show_calendar": True, "show_stats": False, "show_friends": True,
            "launch_on_startup": False, "start_minimized": True, "disable_fanfare_sound": True, "tracking_paused": True,
            "google_display_names": {"artist@example.com": "Inky"}, "friends_status": "away", "feedback_submitted": True,
            "main_window_position": [40, 60], "some_future_setting": "kept",
        }
        legacy = {"tracking_enabled": True, "tracking_krita": True, "program_panels_chosen": ["Krita"],
                  "block_order": ["graph", "Krita", "Photoshop", "stats"], "floating_modules": {"Photoshop": [10, 20]}}
        app_config.SETTINGS_PATH.write_text(json.dumps({**chosen, **legacy}), encoding="utf-8")
        with patch("qt.app.load_settings", app_config.load_settings):
            updated = PSFocusQt(self.application)
        try:
            for timer in (updated.tick_timer, updated.focus_timer, updated.poll_timer, updated.backup_timer):
                timer.stop()
            updated._save_settings(upload=False)
            saved = json.loads(app_config.SETTINGS_PATH.read_text(encoding="utf-8"))
            for key, value in chosen.items():
                self.assertEqual(saved.get(key), value, key)
            # The one program panel takes the old panels' place, floating where Photoshop's floated
            self.assertEqual(saved["block_order"][:2], ["graph", "today"])
            self.assertEqual(saved["floating_modules"].get("today"), [10, 20])
        finally:
            updated.store.close()
            updated.window.hide()

    def test_settings_from_one_panel_per_program_carry_over(self):
        self.app.settings.update({"tracking_krita": True, "program_panels_chosen": ["Krita"], "floating_modules": {"Krita": [10, 20], "stats": [5, 5]}})
        self.app._adopt_program_panels()
        self.assertEqual(self.app.settings["floating_modules"], {"today": [10, 20], "stats": [5, 5]})
        self.assertNotIn("tracking_krita", self.app.settings)
        self.app.settings["block_order"] = ["graph", "Krita", "Photoshop", "stats"]
        self.assertEqual(self.app._read_block_order(), ["graph", "today", "stats", "friends", "calendar"])

    def test_floating_today_panel_follows_each_program_without_replacing_widget(self):
        from app_config import PROGRAMS
        from PySide6.QtCore import QPoint
        panel = self.app.today
        self.app.docking.float_module("today", QPoint(100, 100))
        floating = self.app.docking.floating["today"]
        self.addCleanup(floating.hide)
        for program in PROGRAMS:
            self.app.store.record_active_second(application=program)
            with patch("qt.app.foreground_application", return_value=program), patch("qt.app.user_is_active", return_value=False):
                self.app._track_and_refresh()
            self.assertIs(self.app.today, panel)
            self.assertEqual(panel.application, program)
            self.assertEqual(panel.texts["total"].text, "1s")
            self.assertEqual(floating.windowTitle(), f"PS Focus - {program}")
        self.assertEqual(self.app.store.total_for_day(date.today()), len(PROGRAMS))

    def test_program_name_colors_open_active_paused_idle_and_closed(self):
        from qt.theme import color
        for foreground, running, active, paused, expected in (
            (None, {"Photoshop"}, True, False, "name_online"),
            ("Photoshop", {"Photoshop"}, True, False, "active_green"),
            ("Photoshop", {"Photoshop"}, False, False, "name_online"),
            ("Photoshop", {"Photoshop"}, True, True, "name_online"),
            (None, set(), True, False, "muted"),
        ):
            self.app.settings["tracking_paused"] = paused
            self.app.open_programs_checked = float("-inf")
            with patch("qt.app.foreground_application", return_value=foreground), patch("qt.app.running_applications", return_value=running), patch("qt.app.user_is_active", return_value=active):
                self.app._track_and_refresh()
            self.assertEqual(self.app.today.texts["name"].color, color(expected))

    def test_manual_program_selection_shows_history_until_tracking_resumes(self):
        self.app.store.record_active_second(application="Krita")
        with patch("qt.app.foreground_application", return_value=None):
            self.app._select_program("Krita")
            self.app._track_and_refresh()
        self.assertEqual(self.app.today.application, "Krita")
        self.assertEqual(self.app.today.texts["total"].text, "1s")
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True):
            self.app._track_and_refresh()
            self.app._select_program("Clip Studio Paint")
        self.assertEqual(self.app.today.application, "Photoshop")
        self.assertFalse(self.app.manual_program)

    def test_selection_rechecks_foreground_instead_of_using_stale_active_flag(self):
        self.app.active = True
        with patch("qt.app.foreground_application", return_value=None):
            self.app._select_program("Krita")
        self.assertEqual(self.app.today.application, "Krita")
        self.assertFalse(self.app.active)
        self.assertTrue(self.app.manual_program)

    def test_only_manual_pause_label_is_shown_above_session_count(self):
        for active, paused in ((False, False), (True, False), (True, True)):
            self.app.settings["tracking_paused"] = paused
            with patch("qt.app.foreground_application", return_value="Photoshop" if active else None), patch("qt.app.user_is_active", return_value=True):
                self.app._track_and_refresh()
            self.assertEqual(self.app.today.texts["status"].text, "PAUSED" if paused else "")
        self.assertLess(self.app.today.texts["status"].top, self.app.today.texts["sessions"].top)

    def test_photocraft_follows_foreground_and_records_separate_history(self):
        with patch("qt.app.tracking_clock", return_value=100):
            self.app.last_tick_time = 100
            self.app._track_and_refresh(("PhotoCraft", True, False))
        self.assertTrue(self.app.active)
        self.assertEqual(self.app.today.application, "PhotoCraft")
        with patch("qt.app.tracking_clock", return_value=101.5):
            self.app._track_and_refresh((None, True, False))
        self.assertEqual(self.app.store.total_seconds("PhotoCraft"), 1)
        self.assertEqual(self.app.store.total_seconds("Photoshop"), 0)
        self.assertEqual(self.app.today.application, "PhotoCraft")

    def test_activity_transition_credits_previous_program_only(self):
        with patch("qt.app.tracking_clock", return_value=100.0):
            self.app.last_tick_time = 98.0
            self.app._track_and_refresh(("Photoshop", True, False))
            self.assertEqual(self.app.store.total_seconds(), 0)
        with patch("qt.app.tracking_clock", return_value=102.0):
            self.app._track_and_refresh(("Krita", True, False))
            self.assertEqual(self.app.store.total_seconds("Photoshop"), 2)
            self.assertEqual(self.app.store.total_seconds("Krita"), 0)
        with patch("qt.app.tracking_clock", return_value=104.0):
            self.app._track_and_refresh((None, True, False))
            self.assertEqual(self.app.store.total_seconds("Krita"), 2)
        with patch("qt.app.tracking_clock", return_value=106.0):
            self.app._track_and_refresh((None, True, False))
            self.assertEqual(self.app.store.total_seconds(), 4)

    def test_failed_write_preserves_time_and_current_program_for_retry(self):
        import sqlite3
        self.app.activity_state = ("Photoshop", True, False)
        self.app.last_tick_time = 100
        with patch("qt.app.tracking_clock", return_value=101), patch.object(self.app.store, "record_activity", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                self.app._track_and_refresh(("Krita", True, False))
        self.assertEqual(self.app.activity_state, ("Krita", True, False))
        self.assertTrue(self.app.pending_activity)
        with patch("qt.app.tracking_clock", return_value=102):
            self.app._track_and_refresh((None, True, False))
        self.assertEqual(self.app.store.total_seconds("Photoshop"), 1)
        self.assertEqual(self.app.store.total_seconds("Krita"), 1)
        self.assertFalse(self.app.pending_activity)

    def test_fractional_exit_and_clock_changes_do_not_invent_time(self):
        self.app.activity_state = ("Photoshop", True, False)
        self.app.last_tick_time = 100
        with patch("qt.app.tracking_clock", return_value=100.375):
            self.app._credit_active_time("Photoshop")
        total = self.app.store.connection.execute("SELECT SUM(seconds) FROM activity").fetchone()[0]
        self.assertAlmostEqual(total, .375)
        with patch("qt.app.tracking_clock", return_value=99):
            self.app._credit_active_time("Photoshop")
        self.assertAlmostEqual(self.app.store.connection.execute("SELECT SUM(seconds) FROM activity").fetchone()[0], .375)

    def test_idle_and_paused_intervals_never_credit_time(self):
        self.app.last_tick_time = 100
        self.app.activity_state = ("Photoshop", False, False)
        with patch("qt.app.tracking_clock", return_value=101):
            self.app._track_and_refresh(("Photoshop", True, True))
        with patch("qt.app.tracking_clock", return_value=102):
            self.app._track_and_refresh(("Photoshop", True, False))
        self.assertEqual(self.app.store.total_seconds(), 0)
        with patch("qt.app.tracking_clock", return_value=103):
            self.app._track_and_refresh((None, True, False))
        self.assertEqual(self.app.store.total_seconds(), 1)

    def test_shutdown_flushes_or_preserves_fractional_time(self):
        import sqlite3
        from tracker import ActivityStore
        self.app.activity_state = ("Photoshop", True, False)
        self.app.last_tick_time = 100
        self.app.tray_icon = Mock()
        path = self.app.store.database_path
        with patch("qt.app.tracking_clock", return_value=100.25), patch("qt.app.threading.Timer"), patch.object(self.app.application, "quit"), patch.object(self.app.store, "record_activity", side_effect=sqlite3.OperationalError("locked")):
            self.app.close()
        recovered = ActivityStore(path)
        try:
            seconds = recovered.connection.execute("SELECT SUM(seconds) FROM activity").fetchone()[0]
            self.assertAlmostEqual(seconds, .25)
            self.assertFalse(path.with_suffix(".pending.json").exists())
        finally:
            recovered.close()

    def test_many_short_switches_preserve_each_programs_fractional_time(self):
        import random
        from app_config import PROGRAMS
        rng = random.Random(7)
        clock = 100.0
        state = (None, False, False)
        self.app.last_tick_time = clock
        self.app.activity_state = state
        expected = {program: 0.0 for program in PROGRAMS}
        with patch.object(self.app.chart, "refresh"), patch.object(self.app.friends_sync, "tick"):
            for _ in range(150):
                elapsed = rng.randint(1, 10) / 100
                clock = round(clock + elapsed, 6)
                if state[0] and state[1] and not state[2]:
                    expected[state[0]] += elapsed
                state = (rng.choice((*PROGRAMS, None)), rng.choice((True, False)), rng.choice((True, False)))
                with patch("qt.app.tracking_clock", return_value=clock):
                    self.app._track_and_refresh(state)
            with patch("qt.app.tracking_clock", return_value=clock):
                self.app._credit_active_time(None)
        for program, seconds in expected.items():
            row = self.app.store.connection.execute("SELECT COALESCE(SUM(seconds), 0) FROM activity WHERE application=?", (program,)).fetchone()
            self.assertAlmostEqual(row[0], seconds, places=5)

    def test_midnight_tick_splits_elapsed_time_between_days(self):
        from datetime import datetime
        self.app.last_tick_time = 100
        with patch("qt.app.tracking_clock", return_value=102), patch("qt.app.datetime") as wall:
            wall.now.return_value = datetime(2026, 10, 13, 0, 0, 1)
            self.app._credit_active_time("Photoshop")
        self.assertEqual(self.app.store.total_for_day(date(2026, 10, 12)), 1)
        self.assertEqual(self.app.store.total_for_day(date(2026, 10, 13)), 1)

    def test_transition_reuses_sample_and_process_snapshot(self):
        with patch("qt.app.foreground_application", return_value="Photoshop") as foreground, patch("qt.app.user_is_active", return_value=True), patch("qt.app.running_applications", return_value={"Photoshop"}) as running:
            self.app.open_programs_checked = float("-inf")
            self.app._poll_activity()
            self.assertEqual(foreground.call_count, 1)
            self.app._track_and_refresh(("Krita", True, False))
            self.assertEqual(running.call_count, 1)

    def test_popup_clamps_to_monitor_at_requested_position(self):
        from PySide6.QtCore import QPoint, QRect
        from qt.status_menu import PopupMenu
        screen = Mock()
        screen.availableGeometry.return_value = QRect(-1000, 0, 1000, 800)
        menu = PopupMenu(self.app.window, self.app.fonts, [("one", "One", "")], None, lambda _key: None)
        with patch("qt.status_menu.QApplication.screenAt", return_value=screen), patch.object(menu, "move") as move:
            menu.show_at(QPoint(-1200, -10))
            move.assert_called_once_with(-1000, 0)
        menu.close()
        self.application.processEvents()

    def test_focus_poll_updates_on_transition_without_continuous_refresh(self):
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True):
            self.app.activity_state = (None, True, False)
            self.app.settings["tracking_paused"] = False
            self.app._poll_activity()
            self.assertTrue(self.app.active)
            self.assertEqual(self.app.today.texts["name"].text, "Photoshop")
            with patch.object(self.app, "_tick") as tick:
                self.app._poll_activity()
                tick.assert_not_called()
        with patch("qt.app.foreground_application", return_value=None), patch("qt.app.user_is_active", return_value=True):
            self.app._poll_activity()
            self.assertFalse(self.app.active)
        self.assertLessEqual(self.app.focus_timer.interval(), 100)

    def test_program_chevron_visible_while_active_and_translucent(self):
        from PySide6.QtGui import QImage, QPainter
        from app_config import PROGRAMS
        from qt.module import paint_dropdown_arrow
        from qt.theme import color
        from PySide6.QtCore import QRectF
        panel = self.app.today
        for program in PROGRAMS:
            panel.set_application(program)
            for active in (False, True):
                panel.set_text("name", program, "active_green" if active else "name_online")
                for alpha in (255, 80):
                    panel.glass_alpha = alpha
                    for hovered in (False, True):
                        panel.hovered_control = "program" if hovered else None
                        actual = panel.grab().toImage()
                        rect = panel.program_rect()
                        expected = QImage(rect.size(), QImage.Format.Format_ARGB32)
                        expected.fill(color("background"))
                        painter = QPainter(expected)
                        paint_dropdown_arrow(painter, QRectF(0, 0, rect.width(), rect.height()))
                        painter.end()
                        # Central chevron pixels must match the shared fully visible glyph.
                        glyph_pixels = 0
                        for y in range(rect.height() // 2 - 2, rect.height() // 2 + 3):
                            for x in range(4, 12):
                                if expected.pixelColor(x, y) == color("muted"):
                                    glyph_pixels += 1
                                    self.assertEqual(actual.pixelColor(rect.x() + x, rect.y() + y), color("muted"))
                        self.assertGreater(glyph_pixels, 0)

    def test_program_dropdown_opens_without_starting_a_drag(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from app_config import PROGRAMS
        panel = self.app.today
        point = panel.program_rect().center()
        self.assertTrue(panel.interactive_at(point))
        self.assertIsNone(panel.control_at(point))
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point), QPointF(panel.mapToGlobal(point)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        panel.mousePressEvent(event)
        menu = panel.program_menu
        self.assertTrue(panel.program_menu_open)
        menu.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(menu.rows[0][3].center()), QPointF(menu.mapToGlobal(menu.rows[0][3].center())), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(menu.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        self.assertEqual([row[0] for row in menu.rows], list(PROGRAMS))
        with patch("qt.app.foreground_application", return_value=None):
            menu.on_chosen("Krita")
        self.assertEqual(panel.application, "Krita")
        menu.close()
        self.application.processEvents()
        self.assertFalse(panel.program_menu_open)

    def test_rating_stars_light_up_to_the_one_under_the_mouse(self):
        from datetime import date
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from qt.day_overview import DayOverview

        overview = DayOverview(self.app.window, self.app.fonts, self.app.store, date.today(), lambda _day, _rating: None)
        left, top, width, height = overview.star_areas[3]
        point = QPoint(left + width // 2, top + height // 2)
        QApplication.sendEvent(overview, QMouseEvent(QEvent.Type.MouseMove, QPointF(point), QPointF(overview.mapToGlobal(point)), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(overview.hovered_star, 4)
        QApplication.sendEvent(overview, QEvent(QEvent.Type.Leave))
        self.assertIsNone(overview.hovered_star)
        # As wide as the main window
        self.assertEqual(overview.width(), self.app.window.width())
        overview.deleteLater()
        # In landscape the window is a long strip; the rating window stays as wide as it is upright
        portrait = self.app.window.width()
        self.app.window.resize(3 * portrait, self.app.window.height())
        overview = DayOverview(self.app.window, self.app.fonts, self.app.store, date.today(), lambda _day, _rating: None)
        self.assertEqual(overview.width(), portrait)
        overview.deleteLater()

    def test_double_clicking_a_star_keeps_the_rating(self):
        from datetime import date
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from qt.day_overview import DayOverview

        overview = DayOverview(self.app.window, self.app.fonts, self.app.store, date.today(), self.app._set_productivity_rating)
        left, top, width, height = overview.star_areas[6]
        point = QPointF(left + width // 2, top + height // 2)
        global_point = QPointF(overview.mapToGlobal(point.toPoint()))
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            QApplication.sendEvent(overview, QMouseEvent(kind, point, global_point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.app.store.productivity_rating(date.today()), 7)
        overview.deleteLater()

    def test_day_and_friend_popups_close_on_a_click_elsewhere_escape_or_their_cross(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QKeyEvent, QMouseEvent
        from PySide6.QtWidgets import QApplication
        from qt.day_overview import DayOverview
        from qt.friend_details import FriendDetails

        window = self.app.window
        window.show()
        makers = (
            lambda: DayOverview(window, self.app.fonts, self.app.store, date.today(), lambda _day, _rating: None),
            lambda: FriendDetails(window, self.app.fonts, "Friend", "40.0 hrs total"),
        )

        def press(popup, point):
            QApplication.sendEvent(popup, QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point), QPointF(popup.mapToGlobal(point)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

        for make in makers:
            for close in (
                lambda popup: press(popup, QPoint(-20, -20)),
                lambda popup: QApplication.sendEvent(popup, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)),
                lambda popup: press(popup, popup.close_area().center()),
            ):
                popup = make()
                popup.show_centred_on(window)
                self.application.processEvents()
                self.assertTrue(popup.isVisible())
                # A click on its content leaves it open
                press(popup, QPoint(popup.width() // 2, popup.height() - 4))
                self.assertTrue(popup.isVisible())
                close(popup)
                self.assertFalse(popup.isVisible())
                self.application.processEvents()
        window.hide()

    def test_a_calendar_day_opens_when_the_button_is_let_go(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication

        calendar = self.app.calendar
        calendar.refresh()
        opened = []
        calendar.on_open_day = opened.append
        point = next(QPoint(x, y) for y in range(0, calendar.height(), 3) for x in range(0, calendar.width(), 3) if calendar._day_at(QPoint(x, y)))

        def send(kind, buttons):
            QApplication.sendEvent(calendar, QMouseEvent(kind, QPointF(point), QPointF(calendar.mapToGlobal(point)), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))

        send(QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton)
        self.assertEqual(opened, [])
        send(QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)
        self.assertEqual(opened, [calendar._day_at(point)])

    def test_windows_opened_from_the_app_get_no_handle_before_they_show(self):
        # Asking Windows for a window's handle before it is shown made it stop showing PS Focus's small redraws, so
        # hover, clicks and scrolling looked frozen after the rating or friend window had been open
        from datetime import date
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget
        from qt.day_overview import DayOverview
        from qt.feedback_dialog import FeedbackDialog
        from qt.friend_details import FriendDetails
        from qt.window import set_topmost

        created = Qt.WidgetAttribute.WA_WState_Created
        windows = [
            DayOverview(self.app.window, self.app.fonts, self.app.store, date.today(), lambda _day, _rating: None),
            FriendDetails(self.app.window, self.app.fonts, "Friend", "3.0 hrs past 2 weeks"),
            FeedbackDialog(self.app.window, self.app.fonts, self.app.feedback, lambda: None, lambda: None),
        ]
        hidden = QWidget(self.app.window, Qt.WindowType.Tool)
        set_topmost(hidden, True)
        for window in windows + [hidden]:
            self.assertFalse(window.testAttribute(created), type(window).__name__)
            window.deleteLater()

    def test_small_windows_open_over_ps_focus_on_its_screen(self):
        from datetime import date
        from unittest import mock
        from PySide6.QtCore import Qt
        from qt.day_overview import DayOverview
        from qt.feedback_dialog import FeedbackDialog
        from PySide6.QtWidgets import QWidget
        from qt.friend_details import FriendDetails

        window = self.app.window
        screen = window.screen().availableGeometry()
        # Hanging off its screen's left edge, the window's middle is too: the windows open inside the screen still
        window.move(screen.left() - window.width() + 40, screen.top() + 40)
        for make in (
            lambda: DayOverview(window, self.app.fonts, self.app.store, date.today(), lambda _day, _rating: None),
            lambda: FriendDetails(window, self.app.fonts, "Friend", "3.0 hrs past 2 weeks"),
            lambda: FeedbackDialog(window, self.app.fonts, self.app.feedback, lambda: None, lambda: None),
        ):
            dialog = make()
            with mock.patch("qt.app_dialog.set_title_bar_colors_for_handle") as colour:
                dialog.show_centred_on(window)
            name = type(dialog).__name__
            self.assertTrue(screen.contains(dialog.frameGeometry().topLeft()), name)
            if isinstance(dialog, FeedbackDialog):
                colour.assert_called_once_with(int(dialog.winId()))
            else:
                # The day overview and a friend's details are popups, closed by a click elsewhere, drawing their own title
                self.assertEqual(dialog.windowType(), Qt.WindowType.Popup, name)
                colour.assert_not_called()
            # Only the window itself is a Windows window: a part of it given its own handle draws apart from it
            self.assertFalse(any(child.testAttribute(Qt.WidgetAttribute.WA_NativeWindow) for child in dialog.findChildren(QWidget)), name)
            dialog.close()

    def test_transparency_icon_opens_its_slider(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from qt.transparency_popup import TransparencyPopup

        controls = self.app.module_controls
        point = controls.transparency_area.center()
        self.assertTrue(controls.interactive_at(point))
        QApplication.sendEvent(controls, QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point), QPointF(controls.mapToGlobal(point)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        popup = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, TransparencyPopup) and widget.isVisible())
        # Fully left on the slider is fully see-through
        left = QPoint(popup.slider_left, popup.slider_top + 5)
        for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton), (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            QApplication.sendEvent(popup, QMouseEvent(kind, QPointF(left), QPointF(popup.mapToGlobal(left)), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.app.settings["panel_transparency"], 100)
        # The window shows it at once, though the slider, and so the mouse, are over it
        from unittest.mock import patch as patch_
        with patch_("qt.docking.QCursor.pos", return_value=self.app.window.frameGeometry().center()):
            self.app.update_glass()
        self.assertLess(self.app.window.glass_alpha, 255)
        self.assertEqual(controls.transparency, 100)
        popup.close()
        popup.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(self.app.transparency_previewing)

    def test_startup_controls_do_not_change_settings(self):
        before = self.app.settings.copy()
        self.app._setting_toggled("launch_on_startup")
        self.app._setting_toggled("start_minimized")
        self.assertEqual(self.app.settings, before)

    def test_hidden_dashboard_tracks_without_refreshing_chart(self):
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True), patch.object(self.app.chart, "refresh") as refresh:
            self.app.window.hide()
            self.app._track_and_refresh()
            self.app.last_tick_time -= 2
            self.app._track_and_refresh()
            refresh.assert_not_called()
            self.assertGreaterEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)
            self.app.show_window()
            refresh.assert_called_once()

    def test_manual_backup_contains_new_activity_and_failure_recovers(self):
        from tracker import ActivityStore

        self.app.store.record_active_second(application="Krita")
        self.app.settings_page.backup_button.command()
        latest = self.app.store.backup_directories[0] / "activity-latest.sqlite3"
        snapshot = ActivityStore(latest, [Path(self.temporary.name) / "verification-backups"])
        try:
            self.assertEqual(snapshot.total_for_day(date.today(), "Krita"), 1)
        finally:
            snapshot.close()
        with patch.object(self.app.store, "create_local_backups", side_effect=OSError("folder unavailable")):
            self.app._backup_activity_now()
        self.assertEqual(self.app.settings_page.backup_status[1], "red")
        self.app._backup_activity_now()
        self.assertEqual(self.app.settings_page.backup_status, ("Local activity backups saved", "muted"))

    def test_partial_backup_reports_unavailable_folder(self):
        folders = self.app.store.backup_directories
        with patch.object(self.app.store, "backup_directories", [*folders, Path(self.temporary.name) / "unavailable"]), patch.object(self.app.store, "create_local_backups", return_value=[folders[0] / "snapshot.sqlite3"]):
            self.app._backup_activity_now()
        self.assertEqual(self.app.settings_page.backup_status[1], "orange")

    def test_periodic_backup_remains_active_with_hidden_window(self):
        self.app.window.hide()
        self.app.backup_timer.start()
        self.assertTrue(self.app.backup_timer.isActive())
        with patch.object(self.app.store, "create_local_backups", wraps=self.app.store.create_local_backups) as backup:
            self.app.backup_timer.timeout.emit()
            backup.assert_called_once_with(force=False)
        self.app.backup_timer.stop()

    def test_legacy_module_order_is_preserved(self):
        self.app.settings.pop("block_order", None)
        self.app.settings["module_order"] = ["stats", "graph", "calendar"]
        self.app.settings["modules_left"] = ["stats"]
        self.assertEqual(self.app._read_block_order(), ["stats", "today", "graph", "calendar", "friends"])

    def test_chart_reuses_picture_until_data_period_or_layout_changes(self):
        chart = self.app.chart
        chart.refresh()
        first = chart.picture.cacheKey()
        chart.refresh()
        self.assertEqual(chart.picture.cacheKey(), first)
        self.app.store.record_active_second(application="Photoshop")
        chart.refresh()
        after_data = chart.picture.cacheKey()
        self.assertNotEqual(after_data, first)
        chart._set_period("Week")
        after_period = chart.picture.cacheKey()
        self.assertNotEqual(after_period, after_data)
        self.app._set_orientation(True)
        self.app._arrange_blocks()
        self.assertNotEqual(chart.picture.cacheKey(), after_period)

    def test_pause_stops_credit_and_resume_continues(self):
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True):
            self.app._setting_toggled("tracking_paused")
            self.app._track_and_refresh()
            self.app.last_tick_time -= 2
            self.app._track_and_refresh()
            self.assertEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 0)
            self.app._setting_toggled("tracking_paused")
            self.app._track_and_refresh()
            self.app.last_tick_time -= 2
            self.app._track_and_refresh()
            self.assertGreaterEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)

    def test_minimized_window_refreshes_after_taskbar_restore(self):
        self.app.window.showMinimized()
        self.application.processEvents()
        with patch.object(self.app.chart, "refresh") as refresh:
            self.app._track_and_refresh()
            refresh.assert_not_called()
            self.app.window.showNormal()
            self.application.processEvents()
            self.app._track_and_refresh()
            refresh.assert_called_once()

    def test_settings_status_resize_keeps_dashboard_hidden(self):
        self.app._toggle_settings()
        self.app.settings_page.set_backup_status("Local backup failed: " + "unavailable folder " * 15, "red")
        self.application.processEvents()
        self.assertEqual(self.app.window.height(), self.app.window.title_bar.height() + self.app.header.height() + 2 + self.app.settings_page.height())
        self.assertFalse(self.app.module_controls.isVisible())
        self.assertFalse(self.app.window.viewport.isVisible())

    def test_calendar_and_stats_redraw_after_display_scale_changes(self):
        calendar, stats = self.app.calendar, self.app.stats
        calendar.refresh()
        stats.refresh(calendar.view, calendar.month)
        calendar_key, stats_key = calendar.picture.cacheKey(), stats.picture.cacheKey()
        changed_ratio = max(calendar.devicePixelRatioF(), stats.devicePixelRatioF()) + 1.0
        with patch.object(calendar, "devicePixelRatioF", return_value=changed_ratio), patch.object(stats, "devicePixelRatioF", return_value=changed_ratio):
            calendar.refresh()
            stats.refresh(calendar.view, calendar.month)
            self.assertNotEqual(calendar.picture.cacheKey(), calendar_key)
            self.assertNotEqual(stats.picture.cacheKey(), stats_key)
            self.assertEqual(calendar.picture.devicePixelRatio(), changed_ratio)
            self.assertEqual(stats.picture.devicePixelRatio(), changed_ratio)
            calendar_key, stats_key = calendar.picture.cacheKey(), stats.picture.cacheKey()
            calendar.refresh()
            stats.refresh(calendar.view, calendar.month)
            self.assertEqual(calendar.picture.cacheKey(), calendar_key)
            self.assertEqual(stats.picture.cacheKey(), stats_key)

    def _fake_google(self, immediate_workers=True):
        from qt.google_sync import GoogleSync

        client = Mock()
        client.connected = False
        client.account_email.return_value = "test@example.com"
        client.download_activity_backup.return_value = None
        client.sign_in.side_effect = lambda: setattr(client, "connected", True)
        def sign_out():
            client.connected = False
            return True
        client.sign_out.side_effect = sign_out
        self.app.google_sync = GoogleSync(self.app, client)
        # Run worker bodies immediately, but still apply their results only through poll().
        if immediate_workers:
            worker_patch = patch("qt.google_sync.threading.Thread")
            thread = worker_patch.start()
            thread.side_effect = lambda *, target, daemon: Mock(start=target)
            self.addCleanup(worker_patch.stop)
        return self.app.google_sync, client

    def test_google_connect_backup_switch_and_logout(self):
        controller, client = self._fake_google()
        controller.connect()
        self.assertTrue(controller.busy)
        self.assertEqual(controller.email, "")
        controller.poll()
        self.assertEqual(controller.email, "test@example.com")
        self.assertFalse(controller.busy)
        client.upload_activity_backup.assert_called_once()
        self.assertEqual(self.app.settings_page.google_buttons, "connected")
        controller.switch()
        controller.poll()
        self.assertEqual(client.sign_in.call_count, 2)
        controller.logout()
        controller.poll()
        self.assertEqual(controller.email, "")
        self.assertEqual(self.app.settings_page.google_buttons, "connect")

    def test_google_backup_skips_the_upload_while_drive_holds_this_unchanged_history(self):
        controller, client = self._fake_google()
        uploads = []
        client.upload_activity_backup.side_effect = uploads.append
        controller.connect()
        controller.poll()
        self.assertEqual(len(uploads), 1)
        # Drive now holds exactly that upload, and nothing has been recorded since
        client.download_activity_backup.return_value = uploads[-1]
        controller.backup()
        controller.poll()
        self.assertEqual(len(uploads), 1)
        self.assertEqual(self.app.settings_page.backup_status[1], "active_green")
        # New time is uploaded
        self.app.store.record_active_second(application="Krita")
        controller.backup()
        controller.poll()
        self.assertEqual(len(uploads), 2)
        # So is a copy another PC put there in place of this one, even with nothing new here
        client.download_activity_backup.return_value = uploads[0]
        controller.backup()
        controller.poll()
        self.assertEqual(len(uploads), 3)
        # And backing up by hand always uploads
        client.download_activity_backup.return_value = uploads[-1]
        self.app._backup_activity_now(force=True)
        controller.poll()
        self.assertEqual(len(uploads), 4)

    def test_google_settings_changes_wait_for_current_operation(self):
        controller, client = self._fake_google()
        controller.connect()
        self.app._setting_toggled("tracking_paused")
        controller.poll()
        self.assertTrue(client.upload_settings.call_args.args[0]["tracking_paused"])
        self.assertFalse(controller.busy)

    def test_google_reauthentication_and_failed_backup_keep_local_history(self):
        from google_drive import GoogleAccountAccessRequired

        controller, client = self._fake_google()
        controller.connect()
        controller.poll()
        self.app.store.record_active_second(application="Krita")
        client.download_activity_backup.side_effect = GoogleAccountAccessRequired("Reconnect required")
        controller.backup()
        controller.poll()
        self.assertTrue(controller.reauthentication_required)
        self.assertEqual(self.app.settings_page.google_buttons, "reconnect")
        self.assertEqual(self.app.store.total_for_day(date.today(), "Krita"), 1)
        self.assertEqual(self.app.settings_page.backup_status[1], "red")

    def test_google_restore_rebinds_modules_and_rejects_invalid_backup(self):
        from tracker import ActivityStore

        controller, client = self._fake_google()
        folder = Path(self.temporary.name)
        remote = ActivityStore(folder / "remote.sqlite3", [folder / "remote-backups"])
        remote.record_active_second(application="Krita")
        payload = remote.create_local_backups()[0].read_bytes()
        remote.close()
        controller.connect()
        controller.poll()
        client.download_activity_backup.return_value = payload
        controller.backup()
        controller.poll()
        self.assertEqual(self.app.store.total_for_day(date.today(), "Krita"), 1)
        for module in self.app.modules.values():
            self.assertIs(module.store, self.app.store)
        client.download_activity_backup.return_value = b"invalid database"
        previous_uploads = client.upload_activity_backup.call_count
        controller.backup()
        controller.poll()
        self.assertEqual(client.upload_activity_backup.call_count, previous_uploads)
        self.assertEqual(self.app.store.total_for_day(date.today(), "Krita"), 1)

    def test_google_cloud_filenames_are_configurable_without_changing_tk_defaults(self):
        from google_drive import GoogleDriveSync

        folder = Path(self.temporary.name)
        preview = GoogleDriveSync(folder, folder / "credentials.json", settings_filename="qt-preview-settings.json", activity_filename="qt-preview-activity.sqlite3")
        with patch.object(preview, "_upload_file") as upload, patch.object(preview, "_find_file", return_value=None) as find:
            preview.upload_settings({})
            preview.upload_activity_backup(b"test")
            preview.download_activity_backup()
            self.assertEqual(upload.call_args_list[0].args[0], "qt-preview-settings.json")
            self.assertEqual(upload.call_args_list[1].args[0], "qt-preview-activity.sqlite3")
            find.assert_called_once_with("qt-preview-activity.sqlite3")
        regular = GoogleDriveSync(folder, folder / "credentials.json")
        self.assertEqual(regular.settings_filename, "settings.json")
        self.assertEqual(regular.activity_filename, "activity.sqlite3")

    def test_google_merges_remote_history_without_losing_local_activity(self):
        from tracker import ActivityStore

        controller, client = self._fake_google()
        folder = Path(self.temporary.name)
        self.app.store.record_active_second(application="Photoshop")
        remote = ActivityStore(folder / "other-installation" / "activity.sqlite3", [folder / "other-backups"])
        remote.record_active_second(application="Krita")
        client.download_activity_backup.return_value = remote.create_local_backups()[0].read_bytes()
        remote.close()
        controller.connect()
        controller.poll()
        self.assertEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)
        self.assertEqual(self.app.store.total_for_day(date.today(), "Krita"), 1)
        self.assertEqual(self.app.settings_page.backup_status, ("Activity backup saved to Google Drive", "active_green"))

    def test_google_results_are_ignored_after_shutdown_starts(self):
        controller, client = self._fake_google()
        controller.connect()
        self.app.closing = True
        controller.poll()
        self.assertEqual(controller.email, "")
        client.upload_activity_backup.assert_not_called()

    def test_settings_changed_before_oauth_finishes_are_not_lost(self):
        controller, client = self._fake_google()
        controller.busy = True
        self.app._setting_toggled("tracking_paused")
        self.assertTrue(controller.pending_settings)
        client.connected = True
        controller.results.put(("connect", True, "test@example.com"))
        controller.poll()
        self.assertTrue(client.upload_settings.call_args.args[0]["tracking_paused"])

    def test_successful_signin_remains_visible_when_settings_upload_fails(self):
        controller, client = self._fake_google()
        client.upload_settings.side_effect = RuntimeError("Offline")
        controller.connect()
        controller.poll()
        self.assertEqual(controller.email, "test@example.com")
        self.assertTrue(client.connected)
        self.assertEqual(self.app.header.account_text, "test@example.com")
        self.assertEqual(self.app.settings_page.google_status, ("Offline", "red"))
        self.assertFalse(controller.busy)
        self.assertTrue(self.app.settings_page.google_status_clickable)
        client.upload_settings.side_effect = None
        self.app.settings_page.on_google_status()
        controller.poll()
        client.upload_activity_backup.assert_called_once()

    def test_worker_settings_snapshot_does_not_share_nested_preferences(self):
        controller, client = self._fake_google()
        controller.connect()
        controller.poll()
        self.app.settings["google_display_names"] = {"test@example.com": "Original"}
        controller.settings_changed()
        snapshot = client.upload_settings.call_args.args[0]
        self.app.settings["google_display_names"]["test@example.com"] = "Changed"
        self.assertEqual(snapshot["google_display_names"]["test@example.com"], "Original")

    def test_real_google_worker_threads_leave_ui_and_sqlite_work_for_poll(self):
        controller, client = self._fake_google(immediate_workers=False)
        ui_thread = threading.get_ident()
        worker_threads = []
        def sign_in():
            worker_threads.append(threading.get_ident())
            client.connected = True
        client.sign_in.side_effect = sign_in
        controller.connect()
        # Await a result, without allowing the worker to apply any Qt state.
        result = controller.results.get(timeout=2)
        self.assertEqual(controller.email, "")
        self.assertTrue(controller.busy)
        controller.results.put(result)
        with patch.object(self.app.store, "create_local_backups", wraps=self.app.store.create_local_backups) as backup:
            for _ in range(4):  # connect -> settings sync -> download -> upload
                controller.poll()
                if not controller.busy:
                    break
                result = controller.results.get(timeout=2)
                controller.results.put(result)
            controller.poll()
            self.assertGreater(backup.call_count, 0)
        self.assertFalse(controller.busy)
        self.assertEqual(controller.email, "test@example.com")
        self.assertTrue(all(identifier != ui_thread for identifier in worker_threads))
        client.upload_activity_backup.assert_called_once()

    def test_switch_lookup_failure_does_not_display_previous_account(self):
        controller, client = self._fake_google()
        controller.connect()
        controller.poll()
        client.account_email.side_effect = RuntimeError("Account lookup unavailable")
        controller.switch()
        controller.poll()
        self.assertEqual(controller.email, "")
        self.assertNotEqual(self.app.header.account_text, "test@example.com")
        self.assertFalse(controller.busy)

    def test_minimise_hides_to_tray_and_tray_action_restores_tracking_window(self):
        from qt.app import PSFocusQt

        self.start_tray_icon(self.app)
        self.addCleanup(self.app.tray_icon.hide)
        self.app.window.title_bar.on_minimize()
        self.application.processEvents()
        self.assertFalse(self.app.window.isVisible())
        self.assertFalse(self.app.closing)
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True):
            self.app._track_and_refresh()
            self.app.last_tick_time -= 2
            self.app._track_and_refresh()
        self.assertGreaterEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)
        self.app.tray_menu.actions()[0].trigger()
        self.application.processEvents()
        self.assertTrue(self.app.window.isVisible())
        self.assertFalse(self.app.window.isMinimized())

    def test_the_windows_close_exits_the_app(self):
        # Its X, Alt+F4 or Windows' own close: PS Focus exits rather than hiding in the tray
        with patch.object(self.app, "close") as close:
            self.app.window.on_close = close
            self.app.window.close()
        close.assert_called_once()

    def test_pause_checkbox_mouse_click_stops_and_resumes_timer_tracking(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        self.app._toggle_settings()
        area = self.app.settings_page.checkboxes["tracking_paused"][0]
        point = QPoint((area[0] + area[2]) // 2, (area[1] + area[3]) // 2)
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True):
            QTest.mouseClick(self.app.settings_page, Qt.MouseButton.LeftButton, pos=point)
            self.assertTrue(self.app.settings["tracking_paused"])
            self.app.tick_timer.start()
            QTest.qWait(1150)
            self.assertEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 0)
            QTest.mouseClick(self.app.settings_page, Qt.MouseButton.LeftButton, pos=point)
            self.assertFalse(self.app.settings["tracking_paused"])
            # A coarse timer may fire just short of a whole credited second; allow the next tick.
            QTest.qWait(2300)
            self.assertGreaterEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)
            self.app.tick_timer.stop()
        self.app.focus_timer.stop()

    def test_reconnect_clears_expired_access_and_resumes_cloud_backup(self):
        from google_drive import GoogleAccountAccessRequired

        controller, client = self._fake_google()
        controller.connect()
        controller.poll()
        client.download_activity_backup.side_effect = GoogleAccountAccessRequired("Reconnect required")
        controller.backup()
        controller.poll()
        self.assertTrue(controller.reauthentication_required)
        self.assertTrue(self.app.settings_page.reconnect_button.enabled)
        client.download_activity_backup.side_effect = None
        self.app.settings_page.reconnect_button.command()
        controller.poll()
        self.assertFalse(controller.reauthentication_required)
        self.assertEqual(client.sign_in.call_count, 2)
        self.assertEqual(self.app.settings_page.google_buttons, "connected")
        self.assertEqual(self.app.settings_page.backup_status[1], "active_green")

    def test_invalid_restore_reopens_empty_store_and_tracking_remains_usable(self):
        controller, client = self._fake_google()
        client.download_activity_backup.return_value = b"invalid remote history"
        controller.connect()
        controller.poll()
        client.upload_activity_backup.assert_not_called()
        self.assertEqual(self.app.settings_page.backup_status[1], "red")
        for module in self.app.modules.values():
            self.assertIs(module.store, self.app.store)
        self.app.store.record_active_second(application="Photoshop")
        self.assertEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)
        client.download_activity_backup.return_value = None
        controller.backup()
        controller.poll()
        client.upload_activity_backup.assert_called_once()

    def test_manual_backup_does_not_start_cloud_work_when_local_snapshot_fails(self):
        controller, client = self._fake_google()
        controller.connect()
        controller.poll()
        client.download_activity_backup.reset_mock()
        client.upload_activity_backup.reset_mock()
        with patch.object(self.app.store, "create_local_backups", side_effect=OSError("Disk unavailable")):
            self.app.settings_page.backup_button.command()
            controller.poll()
        client.download_activity_backup.assert_not_called()
        client.upload_activity_backup.assert_not_called()
        self.assertEqual(self.app.settings_page.backup_status[1], "red")


    def _unlock_feedback(self):
        self.app._set_feedback_unlocked(True)
        self.assertTrue(self.app.header.level_clickable)
        self.assertTrue(self.app.settings_page.feedback_shown)

    def _open_feedback(self, reveal_prompt=False):
        from qt.feedback_dialog import FeedbackDialog

        self.app._open_feedback_dialog(reveal_prompt)
        dialog = next(
            widget for widget in self.application.topLevelWidgets()
            if isinstance(widget, FeedbackDialog) and widget.isVisible() and not getattr(widget, "_tested", False)
        )
        dialog._tested = True
        self.addCleanup(dialog.close)
        return dialog

    def test_feedback_needs_a_rating_or_message_and_reveals_the_level(self):
        self._unlock_feedback()
        dialog = self._open_feedback(reveal_prompt=True)
        self.assertEqual(dialog.title, "Rate us to reveal your level")
        dialog.submit()
        self.assertEqual(dialog.status[1], "red")
        self.assertEqual(self.app.feedback.pending(), [])
        dialog.stars.choose(4)
        dialog.message.setPlainText("  More charts  ")
        self.assertEqual(dialog.status[0], "")
        with patch.object(self.app, "_send_pending_feedback") as send:
            dialog.submit()
        send.assert_called_once()
        [entry] = self.app.feedback.pending()
        self.assertEqual((entry["rating"], entry["message"]), (4, "More charts"))
        self.assertEqual(dialog.status, ("Thank you for your feedback", "active_green"))
        self.assertFalse(dialog.submit_button.enabled)
        self.assertTrue(self.app.level_revealed)
        self.assertFalse(self.app.header.level_clickable)
        self.assertTrue(self.app.settings["feedback_submitted"])
        self.assertEqual(self.app.settings["feedback_count"], 1)
        self.assertIsNone(self.app._feedback_cooldown_remaining())

    def test_second_feedback_starts_a_cooldown(self):
        self._unlock_feedback()
        self.app.settings["feedback_submitted"] = True
        with patch.object(self.app, "_send_pending_feedback"):
            dialog = self._open_feedback()
            dialog.stars.choose(5)
            dialog.submit()
        self.assertEqual(self.app.settings["feedback_count"], 2)
        self.assertIsNotNone(self.app._feedback_cooldown_remaining())
        dialog = self._open_feedback()
        self.assertFalse(dialog.submit_button.enabled)
        self.assertEqual(dialog.status[1], "orange")
        self.assertEqual(len(self.app.feedback.pending()), 1)

    def test_choosing_the_same_star_again_clears_the_rating(self):
        dialog = self._open_feedback()
        dialog.stars.choose(3)
        dialog.stars.choose(3)
        self.assertEqual(dialog.stars.rating, 0)

    def test_level_click_opens_feedback_only_while_unlocked_and_unrevealed(self):
        with patch.object(self.app, "_open_feedback_dialog") as open_dialog:
            self.app._level_clicked()
            open_dialog.assert_not_called()
            self._unlock_feedback()
            self.app._level_clicked()
            open_dialog.assert_called_once_with(reveal_prompt=True)
            self.app.level_revealed = True
            self.app._level_clicked()
            open_dialog.assert_called_once()

    def test_goal_callback_sees_the_goal_as_already_reached(self):
        header = self.app.header
        seen: list[bool] = []
        header.progress_known, header.progress_reached = True, False
        header.on_goal_reached = lambda: seen.append(header.progress_reached)
        header.set_progress_reached(True)
        self.assertEqual(seen, [True])

    def test_reaching_the_daily_goal_pulses_the_dot_and_fills_today(self):
        header, calendar = self.app.header, self.app.calendar
        self.app.window.show()
        self.application.processEvents()
        # Found already reached at start: nothing plays. Reached later: the dot pulses and today's square fills
        header.progress_known, header.progress_reached = False, False
        header.set_progress_reached(True)
        self.assertFalse(header.pulsing())
        header.set_progress_reached(False)
        header.set_progress_reached(True)
        self.assertTrue(header.pulsing())
        self.assertEqual(calendar.filling(), calendar.view == "Month")
        header.pulse.setCurrentTime(300)
        header.grab()
        if calendar.filling():
            calendar.fill.setCurrentTime(200)
            calendar.grab()
            calendar.fill.setCurrentTime(calendar.fill.duration())
        header.pulse.setCurrentTime(header.pulse.duration())
        self.assertFalse(header.pulsing())
        self.assertFalse(calendar.filling())
        # Switching to the year mid-sweep stops it being drawn over the year's small squares
        calendar.view = "Month"
        calendar.refresh()
        calendar.fill_today()
        self.assertTrue(calendar.filling())
        calendar._toggle_view()
        self.assertEqual(calendar.fill.state(), calendar.fill.State.Running)
        self.assertFalse(calendar.filling())
        calendar.grab()
        calendar._toggle_view()
        self.app.window.hide()

    def test_level_up_plays_fireworks_and_sound_once(self):
        self.app.window.show()
        self.application.processEvents()
        with patch("qt.app.play_celebration_sound") as sound:
            self.app.celebrated_level = None
            self.app._celebrate_level_up(3)
            self.assertIsNone(self.app.fireworks)
            self.app._celebrate_level_up(4)
            fireworks = self.app.fireworks
            self.assertIsNotNone(fireworks)
            self.assertEqual(fireworks.geometry(), self.app.window.rect())
            # A second level-up while the show runs neither restarts it nor the sound
            self.app._celebrate_level_up(5)
            self.assertIs(self.app.fireworks, fireworks)
            sound.assert_called_once()
            fireworks.stop()

    def test_level_up_while_hidden_or_silenced(self):
        self.app.window.hide()
        self.app.settings["disable_fanfare_sound"] = True
        with patch("qt.app.play_celebration_sound") as sound:
            self.app.celebrated_level = None
            self.app._celebrate_level_up(1)
            self.app._celebrate_level_up(2)
        sound.assert_not_called()
        self.assertIsNone(self.app.fireworks)

    def test_fireworks_end_and_remove_themselves(self):
        from qt.celebration import Fireworks

        self.app.window.show()
        self.application.processEvents()
        fireworks = Fireworks(self.app.window, self.app.header.badge_center())
        fireworks.started -= 10
        fireworks._step()
        self.assertTrue(fireworks.finished)
        self.assertFalse(fireworks.timer.isActive())
        self.assertFalse(fireworks.isVisible())

    def test_available_update_turns_the_version_into_a_link(self):
        self.app.tray_icon = Mock()
        update = ("9.9.9", "https://github.com/giltyworks/ps-focus/releases/latest")
        with patch("qt.app.available_update", return_value=update):
            self.app._update_check_worker()
        self.app._poll_signals()
        self.assertEqual((self.app.header.version_text, self.app.header.version_is_link), ("Get version 9.9.9", True))
        # The tray says so only the first time
        self.app._show_available_update(update)
        self.app.tray_icon.showMessage.assert_called_once()
        with patch("qt.app.webbrowser.open") as browser, patch("qt.app.is_safe_download_url", return_value=True):
            self.app.header.on_version()
        browser.assert_called_once_with(update[1])
        # In Settings it is an Update button, the version it gets in its tooltip
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        self.app._toggle_settings()
        header = self.app.header
        header.repaint()
        left, top, right, bottom = header.version_area
        point = QPointF((left + right) / 2, (top + bottom) / 2)
        QApplication.sendEvent(header, QMouseEvent(QEvent.Type.MouseMove, point, QPointF(header.mapToGlobal(point)), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(header.toolTip(), "Get version 9.9.9")

    def test_offline_update_check_changes_nothing(self):
        with patch("qt.app.available_update", side_effect=RuntimeError("offline")):
            self.app._update_check_worker()
        self.app._poll_signals()
        self.assertFalse(self.app.header.version_is_link)


    def _connected_google(self):
        controller, client = self._fake_google()
        controller.connect()
        for _ in range(10):
            controller.poll()
            if not controller.busy:
                break
        self.assertEqual(controller.email, "test@example.com")
        return controller, client

    def test_display_name_is_edited_per_account(self):
        controller, client = self._connected_google()
        self.app.window.show()
        self.app.header.on_account_double()
        entry = self.app.header.name_entry
        self.assertTrue(entry.isVisible())
        self.assertEqual((entry.text(), entry.selectedText()), ("test@example.com", "test@example.com"))
        entry.setText("  Sam  ")
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        entry.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(entry.isVisible())
        self.assertEqual(self.app.settings["google_display_names"], {"test@example.com": "Sam"})
        self.assertEqual(self.app.header.account_text, "Sam")
        # Escape keeps the name as it was
        self.app.header.on_account_double()
        entry.setText("Someone else")
        entry.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.app.header.account_text, "Sam")
        # Typing the email back, or nothing, shows the email again; a long name is cut to 32 characters
        controller._renamed("x" * 40)
        self.assertEqual(controller.display_name(), "x" * 32)
        controller._renamed("test@example.com")
        self.assertEqual(self.app.settings["google_display_names"], {})
        self.assertEqual(self.app.header.account_text, "test@example.com")

    def test_display_name_cannot_be_edited_while_signed_out_or_busy(self):
        controller, client = self._fake_google()
        self.app.header.on_account_double()
        self.assertFalse(self.app.header.name_entry.isVisible())
        controller, client = self._connected_google()
        controller.busy = True
        self.app.header.on_account_double()
        self.assertFalse(self.app.header.name_entry.isVisible())

    def test_name_saved_by_old_versions_goes_to_the_connected_account(self):
        self.app.settings["google_display_name"] = "Old name"
        controller, client = self._connected_google()
        self.assertEqual(controller.display_name(), "Old name")
        self.assertEqual(self.app.settings["google_display_name"], "")
        self.assertEqual(self.app.header.account_text, "Old name")

    def test_start_with_windows_is_off_limits_from_source(self):
        self.assertIn("launch_on_startup", self.app.settings_page.disabled_settings)
        with patch("qt.app.set_startup") as set_startup:
            self.app._setting_toggled("launch_on_startup")
        set_startup.assert_not_called()

    def test_installed_app_updates_the_windows_startup_entry(self):
        self.app.settings_page.disabled_settings.clear()
        self.app.settings.update({"launch_on_startup": True, "start_minimized": True})
        with patch("qt.app.set_startup") as set_startup:
            self.app._setting_toggled("start_minimized")
            set_startup.assert_called_with(True, False)
            self.app._setting_toggled("launch_on_startup")
            set_startup.assert_called_with(False, False)
            # Off, start minimized changes nothing in Windows
            set_startup.reset_mock()
            self.app._setting_toggled("start_minimized")
            set_startup.assert_not_called()
        self.assertEqual((self.app.settings["launch_on_startup"], self.app.settings["start_minimized"]), (False, True))

    def test_failed_windows_startup_change_keeps_the_setting(self):
        self.app.settings_page.disabled_settings.clear()
        self.app.settings["launch_on_startup"] = False
        with patch("qt.app.set_startup", side_effect=OSError("denied")), patch("qt.app.QMessageBox.warning") as warning:
            self.app._setting_toggled("launch_on_startup")
        warning.assert_called_once()
        self.assertFalse(self.app.settings["launch_on_startup"])

    def test_uninstall_window_keeps_data_unless_asked(self):
        from qt.theme import Fonts
        from qt.uninstall_window import UninstallWindow

        run = Mock(return_value=[])
        window = UninstallWindow(Fonts(), run)
        with patch("qt.uninstall_window.QMessageBox") as box:
            self.assertTrue(window.confirm())
        run.assert_called_once_with(False)
        box.warning.assert_not_called()
        self.assertIn("were kept", box.information.call_args.args[2])

    def test_uninstall_window_warns_before_deleting_data(self):
        from PySide6.QtWidgets import QMessageBox
        from qt.theme import Fonts
        from qt.uninstall_window import UninstallWindow

        run = Mock(return_value=[])
        window = UninstallWindow(Fonts(), run)
        window.delete_data = True
        with patch("qt.uninstall_window.QMessageBox.warning", return_value=QMessageBox.StandardButton.No) as warning:
            self.assertFalse(window.confirm())
        warning.assert_called_once()
        run.assert_not_called()
        with patch("qt.uninstall_window.QMessageBox.warning", return_value=QMessageBox.StandardButton.Yes),                 patch("qt.uninstall_window.QMessageBox.information") as information:
            self.assertTrue(window.confirm())
        run.assert_called_once_with(True)
        self.assertIn("all of its data", information.call_args.args[2])

    def test_calendar_day_under_the_mouse_is_drawn_lighter(self):
        from datetime import date as day_type

        calendar = self.app.calendar
        calendar.refresh(force=True)
        before = calendar.picture.cacheKey()
        day = day_type.today().replace(day=1)
        self.assertEqual(calendar._day_fill(day, False).name(), "#151515")
        calendar._hover_day(day)
        self.assertEqual(calendar._day_fill(day, False).name(), "#222222")
        self.assertNotEqual(calendar.picture.cacheKey(), before)
        # A session day stays blue
        self.assertEqual(calendar._day_fill(day, True).name(), "#3d5ce6")
        calendar._toggle_view()
        calendar._hover_day(None)
        self.assertIsNone(calendar.hovered_day)


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class DevToolsTests(unittest.TestCase):
    """The developer version's menu, see qt/dev_tools.py; started as the settings tests start the app"""

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        QtSettingsTests.setUp(self)
        from qt.dev_tools import DevTools

        self.app.dev = True
        self.tools = DevTools(self.app)

    def test_level_up_adds_the_hours_for_the_next_level_and_celebrates(self):
        from app_config import user_level

        before = user_level(self.app.store.total_seconds())
        with patch.object(self.app, "celebrate") as celebrate:
            self.app._tick()
            self.tools.level_up()
        self.assertEqual(user_level(self.app.store.total_seconds()), before + 1)
        celebrate.assert_called_once()
        celebrate.assert_called_once_with(sound=True)
        self.assertFalse(self.app.dev_level_up_requested)
        # A failed write leaves no request behind for a later, real level-up to sound
        with patch.object(self.app.store, "record_activity", side_effect=sqlite3.OperationalError("locked")), self.assertRaises(sqlite3.OperationalError):
            self.tools.level_up()
        self.assertFalse(self.app.dev_level_up_requested)

    def test_added_hours_land_today_and_make_records(self):
        today = date.today()
        self.tools.hour()
        self.assertAlmostEqual(self.app.store.total_for_day(today), 3600, delta=1)
        self.app.store.record_activity([("2026-01-05", 10, 5 * 3600, "Krita", "10:00")])
        self.tools.longest()
        self.assertEqual(self.app.store.longest_session()[0], today)

    def test_feedback_can_be_tried_again_and_is_never_sent(self):
        from PySide6.QtWidgets import QApplication
        from qt.feedback_dialog import FeedbackDialog

        self.app.settings.update(feedback_submitted=True, feedback_count=2, feedback_cooldown_until="2999-01-01T00:00:00")
        self.app.level_revealed = True
        self.tools.feedback_reveal()
        self.assertFalse(self.app.level_revealed)
        self.assertNotIn("feedback_cooldown_until", self.app.settings)
        dialogs = [widget for widget in QApplication.topLevelWidgets() if isinstance(widget, FeedbackDialog) and widget.isVisible()]
        self.assertEqual(len(dialogs), 1)
        dialogs[0].close()
        with patch.object(self.app.feedback, "pending", return_value=True), patch("qt.app.threading.Thread") as thread:
            self.app._send_pending_feedback()
        thread.assert_not_called()

    def test_sample_friends_and_requests_show_signed_out_and_are_answered_here(self):
        friends = self.app.friends_sync
        friends.sample_friends = False
        self.assertNotEqual(friends.view().mode, "on")
        self.tools.sample_friends()
        view = friends.view()
        self.assertEqual(view.mode, "on")
        people = len(view.people)
        self.assertGreater(people, 0)
        self.tools.request()
        (code, _name), = friends.view().incoming
        with patch.object(friends.service, "accept") as accept:
            self.app.friends.actions.accept(code)
        accept.assert_not_called()
        view = friends.view()
        self.assertEqual(view.incoming, [])
        self.assertEqual(len(view.people), people + 1)

    def test_the_dev_badge_opens_the_menu(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        bar = self.app.window.title_bar
        opened = []
        bar.on_dev = opened.append
        point = QPointF(bar.button_rects()["dev"].center())
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(bar, QMouseEvent(kind, point, QPointF(bar.mapToGlobal(point)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(len(opened), 1)
        self.assertTrue(bar.interactive_at(point.toPoint()))

    def test_the_dev_menu_opens_beside_the_window_not_over_it(self):
        from PySide6.QtCore import QPoint, QRect
        from qt.status_menu import PopupMenu

        self.app.window.show()
        screen = self.app.window.screen().availableGeometry()
        self.app.window.move(screen.left(), screen.top() + 100)
        self.application.processEvents()
        PopupMenu.dismissed = None
        self.tools.open_menu(QPoint(screen.left() + 120, screen.top() + 120))
        menu = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, PopupMenu) and widget.isVisible())
        left, top, right, bottom = self.app.docking.main_bounds()
        self.assertFalse(menu.geometry().intersects(QRect(left, top, right - left, bottom - top)), (menu.geometry(), (left, top, right, bottom), screen))
        menu.close()

    def test_the_dev_menu_stays_open_until_the_badge_is_clicked_again(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        self.app.window.show()
        self.tools.open_menu(QPoint(0, 0))
        panel = self.tools.panel
        self.assertTrue(panel.isVisible())
        key, _name, _note, area = next(row for row in panel.rows if row[0] == "hour")
        point = QPointF(area.center())
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(panel, QMouseEvent(kind, point, QPointF(panel.mapToGlobal(point)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.assertAlmostEqual(self.app.store.total_for_day(date.today()), 3600, delta=1)
        self.assertTrue(panel.isVisible())
        # Turning sample friends on redraws it in place, still open
        self.tools.choose("sample_friends")
        self.assertTrue(self.tools.panel.isVisible())
        self.tools.open_menu(QPoint(0, 0))
        self.assertIsNone(self.tools.panel)

    def test_the_dev_menu_moves_with_the_window(self):
        from PySide6.QtCore import QPoint

        self.app.window.on_moved = lambda: (self.app.docking.main_moved(), self.tools.window_moved())
        self.app.window.show()
        self.tools.open_menu(QPoint(0, 0))
        before = self.tools.panel.pos()
        self.app.window.move(self.app.window.pos() + QPoint(30, 20))
        self.application.processEvents()
        self.assertEqual(self.tools.panel.pos(), before + QPoint(30, 20))
        self.tools.open_menu(QPoint(0, 0))

    def test_the_update_notice_toggles(self):
        self.app.tray_icon = Mock()
        self.tools.update()
        self.assertTrue(self.app.header.version_is_link)
        self.tools.update()
        self.assertFalse(self.app.header.version_is_link)
        self.assertIsNone(self.app.available_update)

    def test_tooltips_show_at_once(self):
        from PySide6.QtWidgets import QStyle
        from qt.app import InstantTips

        self.assertEqual(InstantTips().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay), 0)

    def test_the_dev_version_starts_with_sample_friends(self):
        from qt.app import PSFocusQt

        self.app.store.close()
        app = PSFocusQt(self.application, dev=True)
        self.addCleanup(app.store.close)
        self.addCleanup(app.window.hide)
        for timer in (app.tick_timer, app.focus_timer, app.poll_timer, app.backup_timer):
            timer.stop()
        self.assertTrue(app.friends_sync.sample_friends)

    def test_got_feedback_toggles_whatever_has_been_tracked(self):
        self.app._tick()
        self.assertFalse(self.app.feedback_unlocked)
        self.tools.feedback_unlock()
        self.app._tick()
        self.assertTrue(self.app.settings_page.feedback_shown)
        self.tools.feedback_unlock()
        self.app._tick()
        self.assertFalse(self.app.settings_page.feedback_shown)
