"""Settings navigation and tracking while the Qt dashboard is out of view."""

from __future__ import annotations

import os
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
            patch("qt.window.MainWindow.place_top_right"),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temporary.cleanup)
        for item in self.patches:
            self.addCleanup(item.stop)
        self.app = PSFocusQt(self.application)
        self.app.tick_timer.stop()
        self.app.poll_timer.stop()
        self.app.backup_timer.stop()
        self.addCleanup(lambda: self.app.store.close())
        self.addCleanup(self.app.window.hide)
        self.application.processEvents()

    def test_settings_returns_to_both_dashboard_layouts(self):
        for landscape in (False, True):
            self.app._toggle_settings()
            self.app._set_orientation(landscape)
            self.assertTrue(self.app.settings_page.isVisible())
            self.assertFalse(self.app.window.viewport.isVisible())
            self.assertFalse(self.app.module_controls.isVisible())
            self.assertEqual(self.app.window.minimumSize(), self.app.window.maximumSize())
            self.app._toggle_settings()
            self.assertEqual(self.app.window.landscape, landscape)
            self.assertTrue(self.app.window.viewport.isVisible())
            self.assertTrue(self.app.module_controls.isVisible())
            self.assertFalse(self.app.settings_page.isVisible())

    def test_last_panel_is_kept_and_manual_choices_persist(self):
        self.app._setting_toggled("tracking_enabled")
        self.assertTrue(self.app.settings["tracking_enabled"])
        self.app._setting_toggled("tracking_krita")
        self.app._setting_toggled("tracking_enabled")
        self.assertFalse(self.app.settings["tracking_enabled"])
        self.assertIn("Photoshop", self.app.settings["program_panels_chosen"])
        self.app._setting_toggled("tracking_krita")
        self.assertTrue(self.app.settings["tracking_krita"])

    def test_startup_controls_do_not_change_settings(self):
        before = self.app.settings.copy()
        self.app._setting_toggled("launch_on_startup")
        self.app._setting_toggled("start_minimized")
        self.assertEqual(self.app.settings, before)

    def test_hidden_dashboard_tracks_without_refreshing_chart(self):
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True), patch.object(self.app.chart, "refresh") as refresh:
            self.app.window.hide()
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
        self.assertEqual(self.app._read_block_order(), ["stats", "Photoshop", "Krita", "Clip Studio Paint", "graph", "calendar"])

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
            self.app.last_tick_time -= 2
            self.app._track_and_refresh()
            self.assertEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 0)
            self.app._setting_toggled("tracking_paused")
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
        self.assertEqual(self.app.window.height(), self.app.header.height() + 2 + self.app.settings_page.height())
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

    def test_close_event_hides_to_tray_and_tray_action_restores_tracking_window(self):
        from qt.app import PSFocusQt

        self.start_tray_icon(self.app)
        self.addCleanup(self.app.tray_icon.hide)
        if self.application.platformName() == "windows":
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            self.assertTrue(user32.PostMessageW(int(self.app.window.winId()), 0x0010, 0, 0))  # WM_CLOSE
            from PySide6.QtTest import QTest
            QTest.qWait(100)
        else:
            self.app.window.close()
        self.application.processEvents()
        self.assertFalse(self.app.window.isVisible())
        self.assertFalse(self.app.closing)
        with patch("qt.app.foreground_application", return_value="Photoshop"), patch("qt.app.user_is_active", return_value=True):
            self.app.last_tick_time -= 2
            self.app._track_and_refresh()
        self.assertGreaterEqual(self.app.store.total_for_day(date.today(), "Photoshop"), 1)
        self.app.tray_menu.actions()[0].trigger()
        self.application.processEvents()
        self.assertTrue(self.app.window.isVisible())
        self.assertFalse(self.app.window.isMinimized())

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


if __name__ == "__main__":
    unittest.main()
