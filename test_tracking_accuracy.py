"""Boundary and recovery tests for the core activity ledger."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime
from pathlib import Path

from tracker import ActivityStore, activity_slices, tracking_clock


class TrackingAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "activity.sqlite3"
        self.store = ActivityStore(self.path)

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def raw_total(self):
        return self.store.connection.execute("SELECT COALESCE(SUM(seconds), 0) FROM activity").fetchone()[0]

    def test_midnight_keeps_time_on_both_days(self):
        rows = list(activity_slices(datetime(2026, 10, 12, 23, 59, 59, 500000), 1, "Photoshop"))
        self.store.record_activity(rows)
        self.assertEqual(self.store.connection.execute("SELECT day, slot, seconds FROM activity ORDER BY day").fetchall(),
                         [("2026-10-12", 23, .5), ("2026-10-13", 0, .5)])

    def test_hour_boundary_and_first_session_time(self):
        self.store.record_activity(activity_slices(datetime(2026, 10, 12, 9, 59, 59), 2, "Krita"))
        self.assertEqual(self.store.connection.execute("SELECT slot, seconds FROM activity ORDER BY slot").fetchall(), [(9, 1), (10, 1)])
        self.store.record_active_second(datetime(2026, 10, 12, 8, 0), "Krita")
        self.assertEqual(self.store.connection.execute("SELECT started_at FROM session_starts").fetchone()[0], "08:00")

    def test_subsecond_time_survives_database_reopen(self):
        self.store.record_activity(activity_slices(datetime(2026, 10, 12, 9), .375, "Photoshop"))
        self.store.close()
        self.store = ActivityStore(self.path)
        self.assertAlmostEqual(self.raw_total(), .375)

    def test_transaction_failure_retries_without_duplicates(self):
        rows = [*activity_slices(datetime(2026, 10, 12, 9), 1, "Photoshop"),
                *activity_slices(datetime(2026, 10, 12, 10), 1, "Krita")]
        self.store.connection.execute("CREATE TRIGGER fail_krita BEFORE INSERT ON activity WHEN NEW.application='Krita' BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_activity(rows)
        self.assertEqual(self.raw_total(), 0)
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM session_starts").fetchone()[0], 0)
        self.store.connection.execute("DROP TRIGGER fail_krita")
        self.store.record_activity(rows)
        self.assertEqual(self.raw_total(), 2)

    def test_locked_database_can_retry_same_interval(self):
        other = sqlite3.connect(self.path)
        try:
            other.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.store.record_active_second(datetime(2026, 10, 12, 9), "Krita")
            other.rollback()
            self.store.record_active_second(datetime(2026, 10, 12, 9), "Krita")
            self.assertEqual(self.raw_total(), 1)
        finally:
            other.close()

    def test_shutdown_journal_replays_once_even_after_interrupted_cleanup(self):
        self.store.save_pending_activity(activity_slices(datetime(2026, 10, 12, 9), .75, "Krita"))
        pending = self.path.with_suffix(".pending.json")
        content = pending.read_text()
        self.store.close()
        self.store = ActivityStore(self.path)
        self.assertAlmostEqual(self.raw_total(), .75)
        self.assertFalse(pending.exists())
        # Simulate a crash after SQLite commit, before deleting the recovery file.
        pending.write_text(content)
        self.store.recover_pending_activity()
        self.assertAlmostEqual(self.raw_total(), .75)

    def test_a_second_failed_shutdown_keeps_both_lots_of_unsaved_time(self):
        self.store.save_pending_activity(activity_slices(datetime(2026, 10, 12, 9), .75, "Krita"))
        other = sqlite3.connect(self.path)
        try:
            other.execute("BEGIN IMMEDIATE")
            self.store.connection.execute("PRAGMA busy_timeout = 0")
            self.store.save_pending_activity(activity_slices(datetime(2026, 10, 12, 10), .5, "Photoshop"))
        finally:
            other.rollback()
            other.close()
        self.store.recover_pending_activity()
        self.assertAlmostEqual(self.raw_total(), 1.25)
        self.assertFalse(self.path.with_suffix(".pending.json").exists())

    def test_replayed_file_that_cannot_be_deleted_does_not_swallow_the_next_save(self):
        self.store.save_pending_activity(activity_slices(datetime(2026, 10, 12, 9), .75, "Krita"))
        with patch("pathlib.Path.unlink", side_effect=OSError("in use")):
            self.store.recover_pending_activity()
        self.assertAlmostEqual(self.raw_total(), .75)
        # The leftover file was already replayed, so the new time is saved under its own receipt
        self.store.save_pending_activity(activity_slices(datetime(2026, 10, 12, 10), .5, "Photoshop"))
        self.store.recover_pending_activity()
        self.assertAlmostEqual(self.raw_total(), 1.25)

    def test_invalid_recovery_is_preserved(self):
        pending = self.path.with_suffix(".pending.json")
        pending.write_text(json.dumps({"receipt": "bad", "rows": [["2026-10-12", 25, 1, "Krita", "09:00"]]}))
        with self.assertRaises(OSError):
            self.store.recover_pending_activity()
        self.assertTrue(pending.exists())
        self.assertEqual(self.raw_total(), 0)

    def test_invalid_durations_rejected(self):
        for duration in (-1, float("nan"), float("inf")):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                list(activity_slices(datetime(2026, 10, 12), duration, "Krita"))
        self.assertEqual(list(activity_slices(datetime(2026, 10, 12), 0, "Krita")), [])

    def test_secure_or_locked_desktop_is_not_interactive(self):
        from tracker import _desktop_receives_input
        user32, kernel32 = Mock(), Mock()
        user32.GetThreadDesktop.return_value = 123
        def info(_desktop, _kind, value, _size, _needed):
            value._obj.value = 0
            return True
        user32.GetUserObjectInformationW.side_effect = info
        self.assertFalse(_desktop_receives_input(user32, kernel32))
        def unlocked(_desktop, _kind, value, _size, _needed):
            value._obj.value = 1
            return True
        user32.GetUserObjectInformationW.side_effect = unlocked
        self.assertTrue(_desktop_receives_input(user32, kernel32))
        user32.GetUserObjectInformationW.side_effect = None
        user32.GetUserObjectInformationW.return_value = False
        self.assertFalse(_desktop_receives_input(user32, kernel32))

    def test_committed_activity_uses_full_durability(self):
        self.assertEqual(self.store.connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.store.connection.execute("PRAGMA synchronous").fetchone()[0], 2)

    @unittest.skipUnless(os.name == "nt", "Windows foreground APIs")
    def test_foreground_detects_executable_not_window_title_and_closes_handles(self):
        from tracker import foreground_application
        user32, kernel32 = Mock(), Mock()
        user32.GetForegroundWindow.return_value = 123
        user32.IsWindowVisible.return_value = True
        def process_id(_window, value):
            value._obj.value = 456
        user32.GetWindowThreadProcessId.side_effect = process_id
        kernel32.OpenProcess.return_value = 789
        with patch("tracker.ctypes.WinDLL", side_effect=lambda name, **_kw: user32 if name == "user32" else kernel32), patch("tracker._desktop_receives_input", return_value=True):
            for executable, expected in (("Photoshop.EXE", "Photoshop"), ("krita.exe", "Krita"), ("CLIPStudioPaint.exe", "Clip Studio Paint"), ("PhotoCraft.EXE", "PhotoCraft"), ("explorer.exe", None)):
                def image(_process, _flags, buffer, _length):
                    buffer.value = "C:/apps/" + executable
                    return True
                kernel32.QueryFullProcessImageNameW.side_effect = image
                kernel32.CloseHandle.reset_mock()
                self.assertEqual(foreground_application(), expected)
                kernel32.CloseHandle.assert_called_once_with(789)
            kernel32.QueryFullProcessImageNameW.side_effect = None
            kernel32.QueryFullProcessImageNameW.return_value = False
            kernel32.CloseHandle.reset_mock()
            self.assertIsNone(foreground_application())
            kernel32.CloseHandle.assert_called_once_with(789)
            kernel32.OpenProcess.return_value = None
            self.assertIsNone(foreground_application())
            user32.GetForegroundWindow.return_value = None
            self.assertIsNone(foreground_application())

    @unittest.skipUnless(os.name == "nt", "Windows input APIs")
    def test_idle_timer_wrap_and_input_api_failure(self):
        from tracker import user_is_active
        user32, kernel32 = Mock(), Mock()
        def last_input(value):
            value._obj.dwTime = 0xfffffff0
            return True
        user32.GetLastInputInfo.side_effect = last_input
        kernel32.GetTickCount.return_value = 0x10
        with patch("tracker.ctypes.WinDLL", side_effect=lambda name, **_kw: user32 if name == "user32" else kernel32):
            self.assertTrue(user_is_active(1))
            kernel32.GetTickCount.return_value = 5000
            self.assertFalse(user_is_active(1))
            user32.GetLastInputInfo.side_effect = None
            user32.GetLastInputInfo.return_value = False
            self.assertFalse(user_is_active(300))

    def test_awake_clock_moves_forward(self):
        first = tracking_clock()
        self.assertGreaterEqual(tracking_clock(), first)
