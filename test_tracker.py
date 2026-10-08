import os
import tempfile
import sqlite3
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from tracker import DAILY_SNAPSHOT_DAYS, RECENT_SNAPSHOTS, ActivityStore, snapshots_to_delete


def snapshot(moment: datetime) -> str:
    return f"activity-{moment:%Y%m%d-%H%M%S}-000000.sqlite3"


class WeekRankTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        # The full folder name: a runner's temp folder can be named in Windows' short form (RUNNER~1), which the app resolves
        self.folder = Path(self.temporary_directory.name).resolve()
        self.store = ActivityStore(self.folder / "activity.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def _record(self, day: date, seconds: int) -> None:
        with self.store.connection:
            self.store.connection.execute(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, 10, ?, 'Photoshop')", (day.isoformat(), seconds)
            )

    def test_too_little_history_gives_no_rank(self):
        today = date(2026, 10, 7)
        self.assertIsNone(self.store.week_rank(today))
        self._record(today - timedelta(weeks=3), 3600)
        self.assertIsNone(self.store.week_rank(today))

    def test_this_week_so_far_is_compared_with_the_same_days_of_past_weeks(self):
        # Wednesday. Every past week had an hour on Monday and ten on Saturday, after the point this week has reached
        today = date(2026, 10, 7)
        monday = today - timedelta(days=today.weekday())
        for weeks_ago in range(1, 10):
            self._record(monday - timedelta(weeks=weeks_ago), 3600)
            self._record(monday - timedelta(weeks=weeks_ago) + timedelta(days=5), 36000)
        self._record(monday, 2 * 3600)

        # Two hours by Wednesday beats every past week's Monday-to-Wednesday, though not their whole weeks
        self.assertEqual(self.store.week_rank(today), 10)

    def test_only_the_past_year_of_weeks_is_compared(self):
        today = date(2026, 10, 11)
        monday = today - timedelta(days=today.weekday())
        # A very busy stretch more than a year ago, then a steady past year
        for weeks_ago in range(53, 80):
            self._record(monday - timedelta(weeks=weeks_ago), 40 * 3600)
        for weeks_ago in range(1, 53):
            self._record(monday - timedelta(weeks=weeks_ago), 3600)
        self._record(monday, 2 * 3600)

        self.assertEqual(self.store.week_rank(today), 2)

    def test_a_quiet_week_ranks_low_and_ties_do_not_count_against_it(self):
        today = date(2026, 10, 11)
        monday = today - timedelta(days=today.weekday())
        for weeks_ago in range(1, 5):
            self._record(monday - timedelta(weeks=weeks_ago), 3600)
        self._record(monday, 600)
        self.assertEqual(self.store.week_rank(today), 100)
        # An equal week is not counted as busier, so matching every past week ranks as the best
        self._record(monday + timedelta(days=1), 3000)
        self.assertEqual(self.store.week_rank(today), 20)


class SnapshotRetentionTests(unittest.TestCase):
    TODAY = date(2026, 10, 3)

    def test_a_busy_day_keeps_only_the_newest_snapshots(self):
        # A long session makes a snapshot every 15 minutes
        names = [snapshot(datetime(2026, 10, 3, 9) + timedelta(minutes=15 * index)) for index in range(40)]

        deleted = snapshots_to_delete(names, self.TODAY)

        self.assertEqual(sorted(set(names) - set(deleted)), sorted(names)[-RECENT_SNAPSHOTS:])

    def test_the_last_snapshot_of_each_of_the_last_thirty_days_is_kept(self):
        names = [
            snapshot(datetime(2026, 10, 3, 20) - timedelta(days=days_ago, hours=hour))
            for days_ago in range(60)
            for hour in (0, 2, 4)
        ]

        kept = set(names) - set(snapshots_to_delete(names, self.TODAY))

        newest_of_each_day = {snapshot(datetime(2026, 10, 3, 20) - timedelta(days=days_ago)) for days_ago in range(DAILY_SNAPSHOT_DAYS)}
        self.assertLessEqual(newest_of_each_day, kept)
        self.assertEqual(len(kept), len(newest_of_each_day | set(sorted(names)[-RECENT_SNAPSHOTS:])))
        self.assertEqual(min(kept), snapshot(datetime(2026, 10, 3, 20) - timedelta(days=DAILY_SNAPSHOT_DAYS - 1)))

    def test_after_a_long_break_the_newest_snapshots_are_kept_however_old(self):
        names = [snapshot(datetime(2026, 5, 1, 10) + timedelta(minutes=15 * index)) for index in range(25)]

        deleted = snapshots_to_delete(names, self.TODAY)

        self.assertEqual(len(names) - len(deleted), RECENT_SNAPSHOTS)

    def test_other_files_are_left_and_only_the_newest_set_aside_files_kept(self):
        set_aside = [f"activity-corrupt-2026090{day}-120000-000000.sqlite3" for day in range(1, 6)]
        others = ["activity-latest.sqlite3", "activity-20261003-120000-000000.tmp", "notes.txt", "activity-20261399-120000-000000.sqlite3"]

        deleted = snapshots_to_delete(set_aside + others, self.TODAY)

        self.assertEqual(sorted(deleted), set_aside[:2])

    def test_an_existing_folder_of_193_snapshots_is_thinned_on_the_next_backup(self):
        folder = Path(tempfile.mkdtemp())
        try:
            store = ActivityStore(folder / "activity.sqlite3", (folder / "backups",))
            try:
                for index in range(193):
                    (folder / "backups" / snapshot(datetime(2026, 10, 1, 8) + timedelta(minutes=15 * index))).write_bytes(b"old copy")
                store.record_active_second(datetime(2026, 10, 3, 14, 0))
                store.create_local_backups()
            finally:
                store.close()
            remaining = sorted(path.name for path in (folder / "backups").glob("activity-2*.sqlite3"))
            # The newest ten, which include the one just made, and one for each earlier day of the three
            self.assertLessEqual(len(remaining), RECENT_SNAPSHOTS + 3)
            self.assertIn("activity-latest.sqlite3", [path.name for path in (folder / "backups").iterdir()])
        finally:
            for path in sorted(folder.rglob("*"), reverse=True):
                path.rmdir() if path.is_dir() else path.unlink()
            folder.rmdir()


class ActivityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        # The full folder name: a runner's temp folder can be named in Windows' short form (RUNNER~1), which the app resolves
        self.folder = Path(self.temporary_directory.name).resolve()
        self.store = ActivityStore(self.folder / "activity.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_active_seconds_are_persisted_and_aggregated_by_hour(self):
        moment = datetime(2026, 9, 30, 14, 0)
        self.store.record_active_second(moment)
        self.store.record_active_second(moment)

        values, _ = self.store.period_data("Day", date(2026, 9, 30))
        self.assertEqual(values[14], 2 / 60)
        self.assertEqual(self.store.total_for_day(date(2026, 9, 30)), 2)

    def test_dashboard_activity_index_covers_application_date_and_seconds(self):
        index_columns = [
            row[2]
            for row in self.store.connection.execute("PRAGMA index_info(activity_app_day_seconds_idx)")
        ]
        self.assertEqual(index_columns, ["application", "day", "seconds"])

    def test_database_user_data_detection_includes_activity_and_ratings(self):
        self.assertFalse(ActivityStore.database_has_user_data(self.store.database_path))
        self.store.record_active_second(datetime(2026, 9, 30, 14, 0))
        self.assertTrue(ActivityStore.database_has_user_data(self.store.database_path))
        self.store.clear_productivity_rating(date(2026, 9, 30))
        with self.store.connection:
            self.store.connection.execute("DELETE FROM activity")
            self.store.connection.execute(
                "INSERT INTO productivity_ratings (day, rating) VALUES (?, ?)",
                ("2026-09-30", 8),
            )
        self.assertTrue(ActivityStore.database_has_user_data(self.store.database_path))

    def test_activity_is_separated_by_application(self):
        session_day = date(2026, 9, 30)
        self.store.record_active_second(datetime(2026, 9, 30, 9, 17), "Photoshop")
        self.store.record_active_second(datetime(2026, 9, 30, 10, 20), "Krita")
        with self.store.connection:
            self.store.connection.execute(
                "UPDATE activity SET seconds = 900 WHERE day = ? AND application = ?",
                (session_day.strftime("%Y-%m-%d"), "Photoshop"),
            )
            self.store.connection.execute(
                "UPDATE activity SET seconds = 1200 WHERE day = ? AND application = ?",
                (session_day.strftime("%Y-%m-%d"), "Krita"),
            )

        self.assertEqual(self.store.total_for_day(session_day, "Photoshop"), 900)
        self.assertEqual(self.store.total_for_day(session_day, "Krita"), 1200)
        self.assertEqual(self.store.total_for_day(session_day), 2100)
        self.assertEqual(
            self.store.qualifying_sessions(session_day, session_day, application="Krita"),
            [(session_day, "10:20", 1200)],
        )
        self.assertEqual(len(self.store.qualifying_sessions(session_day, session_day)), 1)

    def test_day_application_totals_breaks_down_seconds_and_start_time_per_app(self):
        session_day = date(2026, 9, 30)
        self.store.record_active_second(datetime(2026, 9, 30, 9, 17), "Photoshop")
        self.store.record_active_second(datetime(2026, 9, 30, 10, 20), "Krita")
        with self.store.connection:
            self.store.connection.execute(
                "UPDATE activity SET seconds = 1200 WHERE day = ? AND application = ?",
                (session_day.strftime("%Y-%m-%d"), "Krita"),
            )

        self.assertEqual(
            self.store.day_application_totals(session_day),
            [("Krita", 1200, "10:20"), ("Photoshop", 1, "09:17")],
        )
        self.assertEqual(self.store.day_application_totals(date(2026, 10, 1)), [])

    def test_day_without_a_recorded_start_shows_the_hour_it_was_first_tracked(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)",
                [("2026-09-30", 16, 600, "Photoshop"), ("2026-09-30", 14, 375, "Photoshop")],
            )

        self.assertEqual(self.store.day_application_totals(date(2026, 9, 30)), [("Photoshop", 975, "14:00")])

    def test_legacy_activity_and_session_starts_migrate_to_photoshop(self):
        database_path = self.folder / "legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.execute("CREATE TABLE activity (day TEXT NOT NULL, slot INTEGER NOT NULL, seconds REAL NOT NULL DEFAULT 0, PRIMARY KEY (day, slot))")
        connection.execute("INSERT INTO activity VALUES ('2026-09-30', 9, 900)")
        connection.execute("CREATE TABLE session_starts (day TEXT PRIMARY KEY, started_at TEXT NOT NULL)")
        connection.execute("INSERT INTO session_starts VALUES ('2026-09-30', '09:17')")
        connection.commit()
        connection.close()

        migrated_store = ActivityStore(database_path)
        try:
            session_day = date(2026, 9, 30)
            self.assertEqual(migrated_store.total_for_day(session_day, "Photoshop"), 900)
            self.assertEqual(migrated_store.total_for_day(session_day, "Krita"), 0)
            self.assertEqual(
                migrated_store.qualifying_sessions(session_day, session_day, application="Photoshop"),
                [(session_day, "09:17", 900)],
            )
        finally:
            migrated_store.close()

    def test_failed_legacy_schema_migration_rolls_back_without_stranding_data(self):
        database_path = self.folder / "invalid-legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.execute("CREATE TABLE activity (day TEXT NOT NULL, slot INTEGER NOT NULL)")
        connection.execute("INSERT INTO activity VALUES ('2026-09-30', 9)")
        connection.commit()
        connection.close()

        with self.assertRaises(sqlite3.OperationalError):
            ActivityStore(database_path)

        connection = sqlite3.connect(database_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(tables, {"activity"})
            self.assertEqual(connection.execute("SELECT day, slot FROM activity").fetchall(), [("2026-09-30", 9)])
        finally:
            connection.close()

    def test_corrupt_database_recovers_from_latest_local_backup(self):
        database_path = self.folder / "recoverable.sqlite3"
        backup_directories = (
            self.folder / "primary-backups",
            self.folder / "secondary-backups",
        )
        original_store = ActivityStore(database_path, backup_directories)
        try:
            original_store.record_active_second(datetime(2026, 9, 30, 14, 0))
            original_store.record_active_second(datetime(2026, 9, 30, 14, 0))
            backups = original_store.create_local_backups()
            self.assertEqual(len(backups), 2)
            for backup_directory in backup_directories:
                latest_backup = backup_directory / "activity-latest.sqlite3"
                self.assertTrue(ActivityStore.database_is_usable(latest_backup))
        finally:
            original_store.close()
        database_path.write_bytes(b"damaged database")

        restored_store = ActivityStore(database_path, backup_directories)
        try:
            self.assertTrue(restored_store.recovered_from_backup)
            self.assertEqual(restored_store.total_for_day(date(2026, 9, 30), "Photoshop"), 2)
        finally:
            restored_store.close()

    def test_snapshots_are_written_only_when_history_changed(self):
        backup_directories = (
            self.folder / "idle-primary",
            self.folder / "idle-secondary",
        )
        store = ActivityStore(self.folder / "idle.sqlite3", backup_directories)

        def snapshots():
            return sorted(path for directory in backup_directories for path in directory.glob("activity-2*.sqlite3"))

        try:
            at_launch = snapshots()
            self.assertEqual(len(at_launch), 2)
            # Nothing recorded since launch: the existing snapshots are returned and no files are added
            self.assertEqual(sorted(store.create_local_backups()), at_launch)
            self.assertEqual(snapshots(), at_launch)

            store.record_active_second(datetime(2026, 9, 30, 14, 0))
            after_activity = store.create_local_backups()
            self.assertEqual(len(snapshots()), 4)
            self.assertEqual(store.create_local_backups(), after_activity)
            self.assertEqual(len(snapshots()), 4)

            # A snapshot missing from one folder, or an explicit request, writes new copies
            after_activity[1].unlink()
            self.assertEqual(len(store.create_local_backups()), 2)
            self.assertEqual(len(snapshots()), 5)
            store.create_local_backups(force=True)
            self.assertEqual(len(snapshots()), 7)
        finally:
            store.close()

    def test_latest_valid_backup_skips_damaged_and_set_aside_databases(self):
        backup_directory = self.folder / "ordered-backups"
        store = ActivityStore(self.folder / "ordered.sqlite3", (backup_directory,))
        try:
            good_backup = store.create_local_backup()
        finally:
            store.close()
        for name in ("activity-latest.sqlite3",):
            (backup_directory / name).unlink()
        newer_time = good_backup.stat().st_mtime + 60
        damaged = backup_directory / "activity-29991231-000000-000000.sqlite3"
        damaged.write_bytes(b"damaged backup")
        set_aside = backup_directory / "activity-corrupt-29991231-000000-000000.sqlite3"
        set_aside.write_bytes(good_backup.read_bytes())
        for path in (damaged, set_aside):
            os.utime(path, (newer_time, newer_time))

        self.assertEqual(ActivityStore.latest_valid_backup((backup_directory,)), good_backup)
        self.assertIsNone(ActivityStore.latest_valid_backup((self.folder / "missing",)))

    def test_valid_backup_bytes_restore_database_and_quarantine_corrupt_file(self):
        database_path = self.folder / "downloaded.sqlite3"
        source_path = self.folder / "source.sqlite3"
        source_store = ActivityStore(source_path)
        try:
            source_store.record_active_second(datetime(2026, 9, 30, 14, 0))
            backup_content = source_store.create_local_backup().read_bytes()
        finally:
            source_store.close()
        database_path.write_bytes(b"corrupt local database")

        self.assertTrue(ActivityStore.restore_backup_bytes(database_path, backup_content, self.folder / "quarantine"))
        self.assertTrue(list((self.folder / "quarantine").glob("activity-corrupt-*.sqlite3")))
        restored_store = ActivityStore(database_path)
        try:
            self.assertEqual(restored_store.total_for_day(date(2026, 9, 30), "Photoshop"), 1)
        finally:
            restored_store.close()

    def test_merge_keeps_larger_totals_from_another_installation(self):
        other_directory = self.folder / "other-installation"
        other_store = ActivityStore(other_directory / "activity.sqlite3")
        try:
            other_store.record_active_second(datetime(2026, 9, 29, 8, 5), "Krita")
            other_store.record_active_second(datetime(2026, 9, 30, 9, 2), "Photoshop")
            with other_store.connection:
                other_store.connection.execute("UPDATE activity SET seconds = 600 WHERE day = '2026-09-30'")
            other_store.set_productivity_rating(date(2026, 9, 29), 6)
            other_store.set_productivity_rating(date(2026, 9, 30), 4)
            backup_content = other_store.create_local_backup().read_bytes()
        finally:
            other_store.close()

        self.store.record_active_second(datetime(2026, 9, 30, 9, 17), "Photoshop")
        self.store.record_active_second(datetime(2026, 9, 30, 14, 0), "Photoshop")
        self.store.set_productivity_rating(date(2026, 9, 30), 8)

        self.assertGreater(self.store.merge_backup_bytes(backup_content), 0)
        self.assertEqual(self.store.total_for_day(date(2026, 9, 29), "Krita"), 1)
        self.assertEqual(self.store.total_for_day(date(2026, 9, 30), "Photoshop"), 601)
        self.assertEqual(self.store.productivity_rating(date(2026, 9, 29)), 6)
        self.assertEqual(self.store.productivity_rating(date(2026, 9, 30)), 8)
        self.assertEqual(
            self.store.day_application_totals(date(2026, 9, 30)),
            [("Photoshop", 601, "09:02")],
        )
        self.assertEqual(self.store.merge_backup_bytes(backup_content), 0)

    def test_merge_skips_own_earlier_snapshot_so_cleared_ratings_stay_cleared(self):
        session_day = date(2026, 9, 30)
        self.store.record_active_second(datetime(2026, 9, 30, 9, 17))
        self.store.set_productivity_rating(session_day, 7)
        backup_content = self.store.create_local_backup().read_bytes()
        self.store.clear_productivity_rating(session_day)

        self.assertEqual(self.store.merge_backup_bytes(backup_content), 0)
        self.assertIsNone(self.store.productivity_rating(session_day))

    def test_merge_rejects_unusable_backup_without_changing_history(self):
        self.store.record_active_second(datetime(2026, 9, 30, 9, 17))

        self.assertIsNone(self.store.merge_backup_bytes(b"not a database"))
        self.assertEqual(self.store.total_for_day(date(2026, 9, 30)), 1)

    def test_record_metrics_count_threshold_days_and_total_hours(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds) VALUES (?, ?, ?)",
                [
                    ("2026-09-08", 10, 900),
                    ("2026-09-09", 10, 899),
                    ("2026-10-01", 10, 3600),
                ],
            )

        self.assertEqual(self.store.total_seconds(), 5399)
        self.assertEqual(self.store.total_for_range(date(2026, 9, 8), date(2026, 9, 9)), 1799)
        self.assertEqual(self.store.last_recorded_day(), date(2026, 10, 1))

    def test_rolling_average_spreads_the_last_seven_days_over_every_day_and_program(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)",
                [
                    ("2026-09-24", 10, 9000, "Photoshop"),
                    ("2026-09-25", 10, 3600, "Photoshop"),
                    ("2026-09-28", 10, 1800, "Krita"),
                    ("2026-10-01", 9, 1200, "Photoshop"),
                    ("2026-10-01", 14, 700, "Clip Studio Paint"),
                    ("2026-10-02", 10, 5000, "Photoshop"),
                ],
            )

        # Seven days ending 1 October run from 25 September, so the 24th and the 2nd are left out
        self.assertEqual(self.store.rolling_daily_average(7, date(2026, 10, 1)), (3600 + 1800 + 1200 + 700) / 7)
        self.assertEqual(self.store.rolling_daily_average(7, date(2026, 8, 1)), 0)

    def test_best_weekday_is_the_highest_average_over_every_time_that_day_came_round(self):
        self.assertIsNone(self.store.best_weekday_average(date(2026, 10, 1)))
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)",
                [
                    # Tuesdays: 15, 22 and 29 September, with nothing recorded on the 22nd
                    ("2026-09-15", 10, 7200, "Photoshop"),
                    ("2026-09-29", 10, 3600, "Photoshop"),
                    ("2026-09-29", 14, 3600, "Krita"),
                    # Wednesdays: 16, 23 and 30 September
                    ("2026-09-16", 10, 6000, "Photoshop"),
                    ("2026-09-23", 10, 6000, "Photoshop"),
                    # Thursday 1 October has come round three times since the first record (17th, 24th, 1st)
                    ("2026-10-01", 10, 9000, "Photoshop"),
                    ("2026-10-02", 10, 99999, "Photoshop"),
                ],
            )

        # Tuesday averages 14400 / 3 = 4800, ahead of Wednesday's 4000 and Thursday's 3000
        self.assertEqual(self.store.best_weekday_average(date(2026, 10, 1)), (1, 4800.0))

    def test_longest_session_is_the_day_with_the_most_time_across_programs(self):
        self.assertIsNone(self.store.longest_session())
        with self.store.connection:
            self.store.connection.execute("INSERT INTO activity (day, slot, seconds, application) VALUES ('2026-09-20', 10, 899, 'Photoshop')")
        # A day under fifteen minutes is not a session, so it holds no record
        self.assertIsNone(self.store.longest_session())

        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)",
                [
                    ("2026-09-24", 10, 3000, "Photoshop"),
                    ("2026-09-28", 9, 2000, "Photoshop"),
                    ("2026-09-28", 14, 1500, "Krita"),
                    ("2026-09-29", 10, 3600, "Photoshop"),
                ],
            )
        self.assertEqual(self.store.longest_session(), (date(2026, 9, 29), 3600))

        # Matching the record does not take it; beating it does, and time in two programs counts together
        with self.store.connection:
            self.store.connection.execute("UPDATE activity SET seconds = 2100 WHERE day = '2026-09-28' AND application = 'Photoshop'")
        self.assertEqual(self.store.longest_session(), (date(2026, 9, 28), 3600))
        with self.store.connection:
            self.store.connection.execute("UPDATE activity SET seconds = 3601 WHERE day = '2026-09-29'")
        self.assertEqual(self.store.longest_session(), (date(2026, 9, 29), 3601))

    def test_best_start_time_is_the_start_of_the_highest_rated_day(self):
        self.assertIsNone(self.store.best_start_time())
        self.store.record_active_second(datetime(2026, 9, 28, 14, 30), "Photoshop")
        self.store.record_active_second(datetime(2026, 9, 29, 11, 0), "Krita")
        self.store.record_active_second(datetime(2026, 9, 29, 9, 10), "Photoshop")
        self.store.record_active_second(datetime(2026, 9, 30, 20, 45), "Photoshop")
        # Tracked days alone are not enough: the stat needs a rating
        self.assertIsNone(self.store.best_start_time())

        self.store.set_productivity_rating(date(2026, 9, 28), 6)
        self.assertEqual(self.store.best_start_time(), ("14:30", 6))

        # The 29th is rated higher; its day began with the first program used, at 9:10
        self.store.set_productivity_rating(date(2026, 9, 29), 9)
        self.assertEqual(self.store.best_start_time(), ("09:10", 9))

        # A second day with the same top rating is averaged in: 9:10 and 20:45 give 14:58
        self.store.set_productivity_rating(date(2026, 9, 30), 9)
        self.assertEqual(self.store.best_start_time(), ("14:58", 9))

        # A top rating on a day with nothing tracked has no start time, so it is passed over
        self.store.set_productivity_rating(date(2026, 10, 1), 10)
        self.assertEqual(self.store.best_start_time(), ("14:58", 9))

        self.store.clear_productivity_rating(date(2026, 9, 29))
        self.store.clear_productivity_rating(date(2026, 9, 30))
        self.assertEqual(self.store.best_start_time(), ("14:30", 6))

    def test_best_start_time_falls_back_to_the_first_tracked_hour_for_older_history(self):
        with self.store.connection:
            self.store.connection.execute("INSERT INTO activity (day, slot, seconds, application) VALUES ('2026-09-20', 13, 1800, 'Photoshop')")
        self.store.set_productivity_rating(date(2026, 9, 20), 8)

        self.assertEqual(self.store.best_start_time(), ("13:00", 8))

    def test_lifetime_session_count_is_qualified_and_separated_by_application(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)",
                [
                    ("2024-01-01", 9, 900, "Photoshop"),
                    ("2025-06-10", 9, 899, "Photoshop"),
                    ("2025-06-10", 10, 901, "Krita"),
                    ("2026-09-30", 9, 1200, "Photoshop"),
                    ("2026-09-30", 10, 900, "Krita"),
                ],
            )

        self.assertEqual(self.store.lifetime_sessions(application="Photoshop"), 2)
        self.assertEqual(self.store.lifetime_sessions(application="Krita"), 2)
        self.assertEqual(self.store.lifetime_sessions(), 3)

    def test_calendar_streaks_count_consecutive_blue_weeks_across_programs(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)",
                [
                    ("2026-09-17", 10, 901, "Photoshop"),
                    ("2026-09-24", 10, 901, "Krita"),
                    ("2026-09-29", 10, 901, "Clip Studio Paint"),
                    ("2026-10-02", 10, 1800, "Photoshop"),
                ],
            )

        self.assertEqual(self.store.calendar_streaks(date(2026, 10, 1)), (3, 2))

    def test_calendar_streaks_require_fifteen_minutes_and_reset_by_week(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds) VALUES (?, ?, ?)",
                [
                    ("2026-09-24", 10, 900),
                    ("2026-09-29", 10, 899),
                ],
            )

        self.assertEqual(self.store.calendar_streaks(date(2026, 10, 1)), (0, 7))

    def test_productivity_rating_is_saved_and_updated_per_day(self):
        session_day = date(2026, 9, 30)
        self.assertIsNone(self.store.productivity_rating(session_day))
        self.store.set_productivity_rating(session_day, 7)
        self.assertEqual(self.store.productivity_rating(session_day), 7)
        self.store.set_productivity_rating(session_day, 9)
        self.assertEqual(self.store.productivity_rating(session_day), 9)
        self.store.clear_productivity_rating(session_day)
        self.assertIsNone(self.store.productivity_rating(session_day))
        self.store.set_productivity_rating(session_day, 9)
        self.store.set_productivity_rating(date(2026, 10, 1), 5)
        self.assertEqual(self.store.month_ratings(2026, 9), {30: 9})
        with self.assertRaises(ValueError):
            self.store.set_productivity_rating(session_day, 11)

    def test_session_stats_keep_first_tracked_time_and_require_fifteen_minutes(self):
        session_day = date(2026, 9, 30)
        self.store.record_active_second(datetime(2026, 9, 30, 9, 17))
        self.store.record_active_second(datetime(2026, 9, 30, 15, 42))
        self.assertEqual(self.store.qualifying_sessions(session_day, session_day), [])

        with self.store.connection:
            self.store.connection.execute(
                "UPDATE activity SET seconds = 899 WHERE day = ? AND slot = ?",
                (session_day.strftime("%Y-%m-%d"), 9),
            )

        self.assertEqual(
            self.store.qualifying_sessions(session_day, session_day),
            [(session_day, "09:17", 900)],
        )

    def test_qualifying_session_uses_first_tracked_time_of_day(self):
        session_day = date(2026, 9, 30)
        self.store.record_active_second(datetime(2026, 9, 30, 9, 17))
        with self.store.connection:
            self.store.connection.execute(
                "UPDATE activity SET seconds = seconds + 899 WHERE day = ? AND slot = ?",
                (session_day.strftime("%Y-%m-%d"), 9),
            )
        self.store.record_active_second(datetime(2026, 9, 30, 15, 42))

        sessions = self.store.qualifying_sessions(session_day, session_day)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0], (session_day, "09:17", 901))

    def test_week_and_month_have_expected_number_of_daily_buckets(self):
        today = date(2026, 9, 30)
        self.store.record_active_second(datetime.combine(today - timedelta(days=2), datetime.min.time()))

        week, week_labels = self.store.period_data("Week", today)
        month, month_labels = self.store.period_data("Month", today)
        quarter, quarter_labels = self.store.period_data("3 Months", today)
        self.assertEqual(len(week), 7)
        self.assertEqual(len(month), 30)
        self.assertEqual(len(quarter), 90)
        self.assertEqual(quarter_labels[0], "Jul 03")
        self.assertEqual(week_labels, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertEqual(month_labels, [str(day) if day % 2 == 1 else "" for day in range(1, 31)])
        self.assertEqual(week[0], 1 / 60)
        self.assertEqual(sum(week), 1 / 60)
        self.assertEqual(sum(month), 1 / 60)

    def test_six_month_and_one_year_periods_have_expected_buckets_and_labels(self):
        today = date(2026, 9, 30)
        self.store.record_active_second(datetime.combine(today - timedelta(days=2), datetime.min.time()))

        half_year, half_year_labels = self.store.period_data("6 Months", today)
        year, year_labels = self.store.period_data("1 Year", today)
        self.assertEqual(len(half_year), 180)
        self.assertEqual(len(year), 365)
        self.assertEqual(half_year_labels[0], (today - timedelta(days=179)).strftime("%b %d"))
        self.assertEqual(sum(half_year), 1 / 60)
        self.assertEqual(sum(year), 1 / 60)
        self.assertEqual(
            [label for label in year_labels if label],
            ["Feb", "Apr", "Jun", "Aug", "Oct", "Dec"],
        )
        self.assertEqual(year_labels[date(2026, 2, 1).toordinal() - date(2026, 1, 1).toordinal()], "Feb")
        self.assertEqual(year_labels[date(2026, 1, 1).toordinal() - date(2026, 1, 1).toordinal()], "")

    def test_month_totals_include_all_days_and_exclude_adjacent_months(self):
        with self.store.connection:
            self.store.connection.executemany(
                "INSERT INTO activity (day, slot, seconds) VALUES (?, ?, ?)",
                [
                    ("2026-09-08", 10, 901),
                    ("2026-09-09", 10, 900),
                    ("2026-10-01", 10, 1800),
                ],
            )

        self.assertEqual(self.store.month_totals(2026, 9), {8: 901, 9: 900})



class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name).resolve()
        self.store = ActivityStore(self.folder / "activity.sqlite3", [self.folder / "backups"])

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_the_live_database_keeps_a_write_ahead_log(self):
        self.assertEqual(self.store.connection.execute("PRAGMA journal_mode").fetchone(), ("wal",))

    def test_backups_are_plain_single_files(self):
        self.store.record_active_second()
        path = self.store.create_local_backups(force=True)[0]
        # Bytes 18 and 19 of an SQLite file are 1 for the rollback journal, 2 for a write-ahead log
        self.assertEqual(path.read_bytes()[18:20], b"")
        self.assertTrue(ActivityStore.database_is_usable(path))
        names = {item.name for item in path.parent.iterdir()}
        self.assertFalse([name for name in names if name.endswith(("-wal", "-shm", ".tmp"))])

    def test_restoring_moves_the_old_log_aside_with_the_old_database(self):
        self.store.record_active_second()
        content = self.store.create_local_backups(force=True)[0].read_bytes()
        self.store.close()
        database = self.folder / "activity.sqlite3"
        wal = database.with_name(database.name + "-wal")
        wal.write_bytes(b"a log left by a crash")
        database.with_name(database.name + "-shm").write_bytes(b"shared memory")
        self.assertTrue(ActivityStore.restore_backup_bytes(database, content, self.folder / "backups"))
        self.assertFalse(wal.exists())
        self.assertFalse(database.with_name(database.name + "-shm").exists())
        moved = [path.name for path in (self.folder / "backups").glob("activity-corrupt-*-wal")]
        self.assertEqual(len(moved), 1)
        self.store = ActivityStore(database, [self.folder / "backups"])
        self.assertEqual(self.store.connection.execute("PRAGMA quick_check").fetchone(), ("ok",))


if __name__ == "__main__":
    unittest.main()
