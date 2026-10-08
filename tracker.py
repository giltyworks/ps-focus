"""Local foreground-time detection and storage for supported art applications"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re
import shutil
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

# The snapshots each backup folder keeps: the newest few, for a damaged history file, and the newest of each
# of the last few weeks' days, for a mistake noticed later. Snapshots are made only when the history has
# changed, so after a break from drawing the newest ones are kept however old they are
RECENT_SNAPSHOTS = 10
DAILY_SNAPSHOT_DAYS = 30
# Damaged history files that restore_backup_bytes set aside, of which the newest are kept
SET_ASIDE_FILES_KEPT = 3
SNAPSHOT_NAME = re.compile(r"activity-(\d{8})-\d{6}-\d{6}\.sqlite3")


def snapshots_to_delete(names: list[str], today: date) -> list[str]:
    """Return which files in a backup folder are no longer kept, given the names of everything in it

    Snapshot names hold the time they were made, in a fixed-width form, so sorting the names sorts by time
    """
    snapshot_days = {}
    for name in names:
        match = SNAPSHOT_NAME.fullmatch(name)
        if match:
            try:
                snapshot_days[name] = datetime.strptime(match.group(1), "%Y%m%d").date()
            except ValueError:
                continue
    newest_first = sorted(snapshot_days, reverse=True)
    kept = set(newest_first[:RECENT_SNAPSHOTS])
    first_day = today - timedelta(days=DAILY_SNAPSHOT_DAYS - 1)
    newest_of_day: dict[date, str] = {}
    for name in newest_first:
        if snapshot_days[name] >= first_day:
            newest_of_day.setdefault(snapshot_days[name], name)
    kept.update(newest_of_day.values())
    set_aside = sorted((name for name in names if name.startswith("activity-corrupt-")), reverse=True)
    return [name for name in newest_first if name not in kept] + set_aside[SET_ASIDE_FILES_KEPT:]


class ActivityStore:
    def __init__(self, database_path: Path, backup_directories: tuple[Path, ...] | None = None) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self.backup_directories = tuple(dict.fromkeys(
            path.resolve() for path in (backup_directories or (database_path.parent / "backups",))
        ))
        self.recovered_from_backup = False
        self.installation_id = self._load_installation_id()
        if not self.database_is_usable(database_path):
            self.recovered_from_backup = self._restore_latest_backup()
        self.connection = sqlite3.connect(database_path)
        try:
            # A second is recorded every second. With a write-ahead log a commit is a short append rather than a
            # journal file made, flushed to disk and deleted each time, about a hundredth of the work. A power cut
            # can lose the last few seconds, never the database, which stays consistent
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=NORMAL")
            self._initialize_schema()
        except BaseException:
            self.connection.close()
            raise
        self.backup_error: str | None = None
        # The change count the newest snapshots were taken at, and where they are, see create_local_backups
        self._backed_up_changes: int | None = None
        self._last_backups: list[Path] = []
        try:
            self.create_local_backup()
        except (OSError, sqlite3.Error) as error:
            self.backup_error = str(error)

    def _load_installation_id(self) -> str:
        """Return the identifier that marks which installation last wrote a database"""
        id_path = self.database_path.parent / "installation-id"
        try:
            installation_id = id_path.read_text(encoding="utf-8").strip()
        except OSError:
            installation_id = ""
        if not installation_id:
            installation_id = uuid.uuid4().hex
            id_path.write_text(installation_id, encoding="utf-8")
        return installation_id

    def _initialize_schema(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS activity (
                    day TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    seconds REAL NOT NULL DEFAULT 0,
                    application TEXT NOT NULL DEFAULT 'Photoshop',
                    PRIMARY KEY (day, slot, application)
                )"""
            )
            activity_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(activity)")}
            if "application" not in activity_columns:
                self.connection.execute("ALTER TABLE activity RENAME TO activity_legacy")
                self.connection.execute(
                    """CREATE TABLE activity (
                        day TEXT NOT NULL,
                        slot INTEGER NOT NULL,
                        seconds REAL NOT NULL DEFAULT 0,
                        application TEXT NOT NULL DEFAULT 'Photoshop',
                        PRIMARY KEY (day, slot, application)
                    )"""
                )
                self.connection.execute(
                    "INSERT INTO activity (day, slot, seconds, application) SELECT day, slot, seconds, 'Photoshop' FROM activity_legacy"
                )
                self.connection.execute("DROP TABLE activity_legacy")
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS productivity_ratings (
                    day TEXT PRIMARY KEY,
                    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 10)
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS session_starts (
                    day TEXT NOT NULL,
                    application TEXT NOT NULL DEFAULT 'Photoshop',
                    started_at TEXT NOT NULL,
                    PRIMARY KEY (day, application)
                )"""
            )
            session_start_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(session_starts)")}
            if "application" not in session_start_columns:
                self.connection.execute("ALTER TABLE session_starts RENAME TO session_starts_legacy")
                self.connection.execute(
                    """CREATE TABLE session_starts (
                        day TEXT NOT NULL,
                        application TEXT NOT NULL DEFAULT 'Photoshop',
                        started_at TEXT NOT NULL,
                        PRIMARY KEY (day, application)
                    )"""
                )
                self.connection.execute(
                    "INSERT INTO session_starts (day, application, started_at) SELECT day, 'Photoshop', started_at FROM session_starts_legacy"
                )
                self.connection.execute("DROP TABLE session_starts_legacy")
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS activity_app_day_seconds_idx ON activity (application, day, seconds)"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            self.connection.execute(
                "INSERT INTO metadata (key, value) VALUES ('last_writer', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (self.installation_id,),
            )
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    @staticmethod
    def database_is_usable(database_path: Path) -> bool:
        if not database_path.is_file():
            return False
        connection = None
        try:
            connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            return integrity == ("ok",) and "activity" in tables
        except (OSError, sqlite3.Error):
            return False
        finally:
            if connection is not None:
                connection.close()

    @classmethod
    def database_has_user_data(cls, database_path: Path) -> bool:
        if not cls.database_is_usable(database_path):
            return False
        connection = None
        try:
            connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "activity" in tables and connection.execute("SELECT 1 FROM activity WHERE seconds > 0 LIMIT 1").fetchone():
                return True
            return "productivity_ratings" in tables and bool(
                connection.execute("SELECT 1 FROM productivity_ratings LIMIT 1").fetchone()
            )
        except (OSError, sqlite3.Error):
            return False
        finally:
            if connection is not None:
                connection.close()

    @classmethod
    def latest_valid_backup(cls, backup_directories: tuple[Path, ...]) -> Path | None:
        candidates = sorted(
            (
                path
                for directory in backup_directories
                for path in directory.glob("activity-*.sqlite3")
                # Databases set aside by restore_backup_bytes are not backups, even when they still open
                if not path.name.startswith("activity-corrupt-")
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        # Newest first, so only as many files are integrity-checked as it takes to find a good one
        return next((path for path in candidates if cls.database_is_usable(path)), None)

    def _restore_latest_backup(self) -> bool:
        latest_backup = self.latest_valid_backup(self.backup_directories)
        if latest_backup is None:
            return False

        try:
            backup_content = latest_backup.read_bytes()
        except OSError:
            return False
        return self.restore_backup_bytes(self.database_path, backup_content, self.backup_directories[0])

    @classmethod
    def restore_backup_bytes(cls, database_path: Path, content: bytes, quarantine_directory: Path) -> bool:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = database_path.with_suffix(".restore.tmp")
        temporary_path.write_bytes(content)
        if not cls.database_is_usable(temporary_path):
            temporary_path.unlink(missing_ok=True)
            return False
        if database_path.exists():
            quarantine_directory.mkdir(parents=True, exist_ok=True)
            corrupted_path = quarantine_directory / f"activity-corrupt-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3"
            os.replace(database_path, corrupted_path)
        os.replace(temporary_path, database_path)
        return True

    def merge_backup_bytes(self, content: bytes) -> int | None:
        """Merge a backup written by another installation, returning changed rows or None when it is unusable"""
        temporary_path = self.database_path.with_suffix(".merge.tmp")
        temporary_path.write_bytes(content)
        try:
            if not self.database_is_usable(temporary_path):
                return None
            source = sqlite3.connect(f"{temporary_path.resolve().as_uri()}?mode=ro", uri=True)
            try:
                tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                if "metadata" in tables:
                    last_writer = source.execute("SELECT value FROM metadata WHERE key = 'last_writer'").fetchone()
                    if last_writer and last_writer[0] == self.installation_id:
                        # An earlier snapshot of this database holds nothing new and would undo cleared ratings
                        return 0
                activity_columns = {row[1] for row in source.execute("PRAGMA table_info(activity)")}
                application = "application" if "application" in activity_columns else "'Photoshop'"
                activity = source.execute(f"SELECT day, slot, seconds, {application} FROM activity").fetchall()
                ratings = []
                if "productivity_ratings" in tables:
                    ratings = source.execute("SELECT day, rating FROM productivity_ratings").fetchall()
                session_starts = []
                if "session_starts" in tables:
                    start_columns = {row[1] for row in source.execute("PRAGMA table_info(session_starts)")}
                    application = "application" if "application" in start_columns else "'Photoshop'"
                    session_starts = source.execute(f"SELECT day, {application}, started_at FROM session_starts").fetchall()
            finally:
                source.close()
        finally:
            temporary_path.unlink(missing_ok=True)

        changes_before = self.connection.total_changes
        with self.connection:
            self.connection.executemany(
                """INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)
                   ON CONFLICT(day, slot, application) DO UPDATE SET seconds = excluded.seconds
                   WHERE excluded.seconds > activity.seconds""",
                activity,
            )
            self.connection.executemany(
                "INSERT OR IGNORE INTO productivity_ratings (day, rating) VALUES (?, ?)",
                ratings,
            )
            self.connection.executemany(
                """INSERT INTO session_starts (day, application, started_at) VALUES (?, ?, ?)
                   ON CONFLICT(day, application) DO UPDATE SET started_at = excluded.started_at
                   WHERE excluded.started_at < session_starts.started_at""",
                session_starts,
            )
        return self.connection.total_changes - changes_before

    def create_local_backups(self, force: bool = False) -> list[Path]:
        """Write a dated snapshot to every backup folder and return the snapshots that now hold the history

        When nothing has been recorded since the last snapshot and that snapshot is still in every folder,
        no new copies are written, so idle hours do not fill the folders with identical files. Each folder is
        then thinned to the snapshots that snapshots_to_delete keeps
        """
        if (
            not force
            and self._backed_up_changes == self.connection.total_changes
            and len(self._last_backups) == len(self.backup_directories)
            and all(path.is_file() for path in self._last_backups)
        ):
            return list(self._last_backups)
        backed_up_changes = self.connection.total_changes
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        created_backups = []
        failures = []
        for backup_directory in self.backup_directories:
            backup_path = backup_directory / f"activity-{timestamp}.sqlite3"
            temporary_path = backup_path.with_suffix(".tmp")
            try:
                backup_directory.mkdir(parents=True, exist_ok=True)
                destination = sqlite3.connect(temporary_path)
                try:
                    self.connection.backup(destination)
                    # A backup is one plain file, whatever mode the live database is in: read, copied or uploaded, it
                    # leaves no log files beside it, and every version of the app can open it
                    destination.execute("PRAGMA journal_mode=DELETE")
                    destination.commit()
                finally:
                    destination.close()
                if not self.database_is_usable(temporary_path):
                    raise sqlite3.DatabaseError("The activity backup did not pass its integrity check")
                os.replace(temporary_path, backup_path)
                latest_path = backup_directory / "activity-latest.sqlite3"
                latest_temporary_path = latest_path.with_suffix(".tmp")
                try:
                    shutil.copy2(backup_path, latest_temporary_path)
                    if not self.database_is_usable(latest_temporary_path):
                        raise sqlite3.DatabaseError("The latest activity backup did not pass its integrity check")
                    os.replace(latest_temporary_path, latest_path)
                except (OSError, sqlite3.Error):
                    latest_temporary_path.unlink(missing_ok=True)
                for name in snapshots_to_delete([path.name for path in backup_directory.iterdir()], date.today()):
                    (backup_directory / name).unlink(missing_ok=True)
                created_backups.append(backup_path)
            except (OSError, sqlite3.Error) as error:
                temporary_path.unlink(missing_ok=True)
                failures.append(error)
        if not created_backups:
            raise OSError("Could not create an activity backup in any configured location") from failures[-1]
        # A folder that could not be written leaves the lists unequal, so the next call tries it again
        self._last_backups = created_backups
        self._backed_up_changes = backed_up_changes
        return created_backups

    def create_local_backup(self, force: bool = False) -> Path:
        return self.create_local_backups(force)[0]

    def record_active_second(self, moment: datetime | None = None, application: str = "Photoshop") -> None:
        moment = moment or datetime.now()
        with self.connection:
            self.connection.execute(
                """INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, 1, ?)
                   ON CONFLICT(day, slot, application) DO UPDATE SET seconds = seconds + 1""",
                (moment.strftime("%Y-%m-%d"), moment.hour, application),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, ?, ?)",
                (moment.strftime("%Y-%m-%d"), application, moment.strftime("%H:%M")),
            )

    def total_for_day(self, day: date | None = None, application: str | None = None) -> int:
        day = day or date.today()
        query = "SELECT COALESCE(SUM(seconds), 0) FROM activity WHERE day = ?"
        parameters: tuple = (day.strftime("%Y-%m-%d"),)
        if application is not None:
            query += " AND application = ?"
            parameters += (application,)
        row = self.connection.execute(
            query,
            parameters,
        ).fetchone()
        return int(row[0])

    def total_seconds(self, application: str | None = None) -> int:
        query = "SELECT COALESCE(SUM(seconds), 0) FROM activity"
        parameters: tuple = ()
        if application is not None:
            query += " WHERE application = ?"
            parameters = (application,)
        row = self.connection.execute(query, parameters).fetchone()
        return int(row[0])

    def total_for_range(self, start: date, end: date, application: str | None = None) -> int:
        query = "SELECT COALESCE(SUM(seconds), 0) FROM activity WHERE day BETWEEN ? AND ?"
        parameters: tuple = (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if application is not None:
            query += " AND application = ?"
            parameters += (application,)
        row = self.connection.execute(
            query,
            parameters,
        ).fetchone()
        return int(row[0])

    def rolling_daily_average(self, days: int = 7, today: date | None = None) -> float:
        """Return average tracked seconds per day over the given number of days ending today, rest days included"""
        today = today or date.today()
        return self.total_for_range(today - timedelta(days=days - 1), today) / days

    def best_weekday_average(self, today: date | None = None) -> tuple[int, float] | None:
        """Return the weekday (Monday is 0) with the highest average tracked seconds, and that average

        Each weekday is averaged over every time it has come round since the first recorded day, rest days included
        """
        today = today or date.today()
        rows = self.connection.execute(
            "SELECT day, SUM(seconds) FROM activity WHERE day <= ? GROUP BY day HAVING SUM(seconds) > 0",
            (today.strftime("%Y-%m-%d"),),
        ).fetchall()
        if not rows:
            return None
        totals = [0.0] * 7
        for day, seconds in rows:
            totals[date.fromisoformat(day).weekday()] += seconds
        first_day = date.fromisoformat(min(day for day, _ in rows))
        full_weeks, extra_days = divmod((today - first_day).days + 1, 7)
        occurrences = [full_weeks] * 7
        for offset in range(extra_days):
            occurrences[(first_day.weekday() + offset) % 7] += 1
        averages = [total / count if count else 0.0 for total, count in zip(totals, occurrences)]
        best = max(range(7), key=lambda weekday: averages[weekday])
        return best, averages[best]

    def week_rank(self, today: date | None = None, minimum_weeks: int = 4, window_weeks: int = 52) -> int | None:
        """Return how this week ranks among past weeks, as 'top N percent', or None with too little history

        This week so far is compared with the same days of each past week, Monday up to today's weekday, so
        a week in progress is not measured against finished ones. Only the past year's weeks count, so a busy
        stretch long ago does not keep the medals out of reach; within it, weeks with nothing recorded count,
        back to the week of the first recorded day. Ties are not counted against this week
        """
        today = today or date.today()
        this_monday = today - timedelta(days=today.weekday())
        first = self.connection.execute("SELECT MIN(day) FROM activity WHERE seconds > 0").fetchone()[0]
        if first is None:
            return None
        first_monday = date.fromisoformat(first) - timedelta(days=date.fromisoformat(first).weekday())
        first_monday = max(first_monday, this_monday - timedelta(weeks=window_weeks))
        past_weeks = (this_monday - first_monday).days // 7
        if past_weeks < minimum_weeks:
            return None
        rows = self.connection.execute(
            "SELECT day, SUM(seconds) FROM activity WHERE day >= ? AND day <= ? GROUP BY day",
            (first_monday.isoformat(), today.isoformat()),
        ).fetchall()
        # Each past week's total over the same days of the week as this one has had so far
        totals = [0.0] * (past_weeks + 1)
        for day, seconds in rows:
            moment = date.fromisoformat(day)
            if moment.weekday() <= today.weekday():
                totals[(moment - first_monday).days // 7] += seconds
        this_week, earlier = totals[-1], totals[:-1]
        busier = sum(1 for total in earlier if total > this_week)
        return max(1, -(-100 * (busier + 1) // (len(earlier) + 1)))

    def longest_session(self, minimum_seconds: int = 15 * 60) -> tuple[date, int] | None:
        """Return the day with the most tracked time of all, across every program, and that time in seconds

        A day needs the session minimum to count. When days tie, the earlier one keeps the record: it has to be
        beaten, not just matched
        """
        row = self.connection.execute(
            """SELECT day, SUM(seconds) AS total FROM activity
               GROUP BY day HAVING total >= ?
               ORDER BY total DESC, day ASC LIMIT 1""",
            (minimum_seconds,),
        ).fetchone()
        return (date.fromisoformat(row[0]), int(row[1])) if row else None

    def best_start_time(self) -> tuple[str, int] | None:
        """Return the start time (HH:MM) of the highest-rated day and that rating, or None when no day is rated

        A day's start is when its first session of any program began. When several days share the top rating,
        their start times are averaged. Rated days with no tracked activity have no start time and are left out
        """
        rows = self.connection.execute(
            """SELECT productivity_ratings.rating,
                      COALESCE(
                          (SELECT MIN(started_at) FROM session_starts WHERE session_starts.day = productivity_ratings.day),
                          (SELECT printf('%02d:00', MIN(slot)) FROM activity
                           WHERE activity.day = productivity_ratings.day AND activity.seconds > 0
                           HAVING COUNT(*) > 0)
                      ) AS started_at
               FROM productivity_ratings"""
        ).fetchall()
        starts = [(int(rating), started_at) for rating, started_at in rows if started_at]
        if not starts:
            return None
        top_rating = max(rating for rating, _ in starts)
        minutes = [int(started_at[:2]) * 60 + int(started_at[3:5]) for rating, started_at in starts if rating == top_rating]
        average = round(sum(minutes) / len(minutes))
        return f"{average // 60:02d}:{average % 60:02d}", top_rating

    def last_recorded_day(self, application: str | None = None) -> date | None:
        query = "SELECT MAX(day) FROM activity WHERE seconds > 0"
        parameters: tuple = ()
        if application is not None:
            query += " AND application = ?"
            parameters = (application,)
        row = self.connection.execute(query, parameters).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def month_ratings(self, year: int, month: int) -> dict[int, int]:
        start = date(year, month, 1)
        end = date(year + month // 12, month % 12 + 1, 1)
        rows = self.connection.execute(
            "SELECT day, rating FROM productivity_ratings WHERE day >= ? AND day < ?",
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()
        return {date.fromisoformat(day).day: int(rating) for day, rating in rows}

    def productivity_rating(self, day: date) -> int | None:
        row = self.connection.execute(
            "SELECT rating FROM productivity_ratings WHERE day = ?",
            (day.strftime("%Y-%m-%d"),),
        ).fetchone()
        return int(row[0]) if row else None

    def set_productivity_rating(self, day: date, rating: int) -> None:
        if not 1 <= rating <= 10:
            raise ValueError("Productivity rating must be between 1 and 10")
        with self.connection:
            self.connection.execute(
                "INSERT INTO productivity_ratings (day, rating) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET rating = excluded.rating",
                (day.strftime("%Y-%m-%d"), rating),
            )

    def clear_productivity_rating(self, day: date) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM productivity_ratings WHERE day = ?",
                (day.strftime("%Y-%m-%d"),),
            )

    def calendar_streaks(self, today: date | None = None, blue_day_threshold: int = 15 * 60) -> tuple[int, int]:
        today = today or date.today()
        rows = self.connection.execute(
            "SELECT day FROM activity WHERE day <= ? GROUP BY day HAVING SUM(seconds) >= ?",
            (today.strftime("%Y-%m-%d"), blue_day_threshold),
        ).fetchall()
        blue_days = {date.fromisoformat(row[0]) for row in rows}
        blue_weeks = {day - timedelta(days=day.weekday()) for day in blue_days}

        week_streak = 0
        week_start = today - timedelta(days=today.weekday())
        while week_start in blue_weeks:
            week_streak += 1
            week_start -= timedelta(days=7)

        rest_day_streak = (today - max(blue_days)).days if blue_days else 0
        return week_streak, rest_day_streak

    def lifetime_sessions(self, minimum_seconds: int = 15 * 60, application: str | None = None) -> int:
        application_clause = " AND application = ?" if application is not None else ""
        parameters: tuple = ()
        if application is not None:
            parameters += (application,)
        parameters += (minimum_seconds,)
        row = self.connection.execute(
            f"SELECT COUNT(*) FROM (SELECT day FROM activity WHERE seconds > 0{application_clause} GROUP BY day HAVING SUM(seconds) >= ?)",
            parameters,
        ).fetchone()
        return int(row[0])

    def month_totals(self, year: int, month: int, application: str | None = None) -> dict[int, int]:
        start = date(year, month, 1)
        end = date(year + month // 12, month % 12 + 1, 1)
        application_clause = " AND application = ?" if application is not None else ""
        parameters: tuple = (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if application is not None:
            parameters += (application,)
        rows = self.connection.execute(
            f"SELECT day, SUM(seconds) FROM activity WHERE day >= ? AND day < ?{application_clause} GROUP BY day",
            parameters,
        ).fetchall()
        return {date.fromisoformat(day).day: int(seconds) for day, seconds in rows}

    def day_application_totals(self, day: date) -> list[tuple[str, int, str | None]]:
        rows = self.connection.execute(
            """SELECT activity.application, SUM(activity.seconds),
                      COALESCE(
                          MIN(session_starts.started_at),
                          printf('%02d:00', MIN(CASE WHEN activity.seconds > 0 THEN activity.slot END))
                      )
               FROM activity
               LEFT JOIN session_starts
                 ON session_starts.day = activity.day AND session_starts.application = activity.application
               WHERE activity.day = ?
               GROUP BY activity.application
               HAVING SUM(activity.seconds) > 0
               ORDER BY SUM(activity.seconds) DESC""",
            (day.strftime("%Y-%m-%d"),),
        ).fetchall()
        return [(application, int(seconds), started_at) for application, seconds, started_at in rows]

    def qualifying_sessions(self, start: date, end: date, minimum_seconds: int = 15 * 60, application: str | None = None) -> list[tuple[date, str, int]]:
        application_clause = " AND activity.application = ?" if application is not None else ""
        session_start_join = (
            "LEFT JOIN session_starts ON session_starts.day = activity.day AND session_starts.application = activity.application"
            if application is not None
            else "LEFT JOIN (SELECT day, MIN(started_at) AS started_at FROM session_starts GROUP BY day) session_starts ON session_starts.day = activity.day"
        )
        parameters: tuple = (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if application is not None:
            parameters += (application,)
        parameters += (minimum_seconds,)
        rows = self.connection.execute(
            """SELECT activity.day,
                      COALESCE(session_starts.started_at, printf('%02d:00', MIN(activity.slot))),
                      SUM(activity.seconds)
               FROM activity
             """ + session_start_join + """
             WHERE activity.day BETWEEN ? AND ?""" + application_clause + """
             GROUP BY activity.day""" + (", activity.application" if application is not None else "") + """
               HAVING SUM(activity.seconds) >= ?
               ORDER BY activity.day DESC""",
            parameters,
        ).fetchall()
        return [(date.fromisoformat(day), started_at, int(seconds)) for day, started_at, seconds in rows]

    def period_data(self, period: str, today: date | None = None, application: str | None = None) -> tuple[list[float], list[str]]:
        today = today or date.today()
        application_clause = " AND application = ?" if application is not None else ""
        if period == "Day":
            parameters: tuple = (today.strftime("%Y-%m-%d"),)
            if application is not None:
                parameters += (application,)
            rows = self.connection.execute(
                "SELECT slot, SUM(seconds) FROM activity WHERE day = ?" + application_clause + " GROUP BY slot",
                parameters,
            ).fetchall()
            values = [0.0] * 24
            for slot, seconds in rows:
                values[int(slot)] = float(seconds) / 60
            labels = ["12a", "", "", "", "4a", "", "", "", "8a", "", "", "", "12p", "", "", "", "4p", "", "", "", "8p", "", "", ""]
            return values, labels

        if period == "Week":
            days = 7
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=days - 1)
        elif period == "Month":
            days = 30
            start = today - timedelta(days=days - 1)
            end = today
        elif period == "3 Months":
            days = 90
            start = today - timedelta(days=days - 1)
            end = today
        elif period == "6 Months":
            days = 180
            start = today - timedelta(days=days - 1)
            end = today
        else:
            start = date(today.year, 1, 1)
            end = date(today.year, 12, 31)
            days = (end - start).days + 1
        parameters = (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if application is not None:
            parameters += (application,)
        rows = self.connection.execute(
            "SELECT day, SUM(seconds) FROM activity WHERE day BETWEEN ? AND ?" + application_clause + " GROUP BY day",
            parameters,
        ).fetchall()
        by_day = {day: float(seconds) / 60 for day, seconds in rows}
        values = []
        labels = []
        for offset in range(days):
            current = start + timedelta(days=offset)
            values.append(by_day.get(current.strftime("%Y-%m-%d"), 0.0))
            if period == "Week":
                labels.append(current.strftime("%a"))
            elif period == "Month":
                labels.append(str(current.day) if offset % 2 == 0 else "")
            elif period == "3 Months":
                labels.append(current.strftime("%b %d") if offset % 14 == 0 else "")
            elif period == "6 Months":
                labels.append(current.strftime("%b %d") if offset % 28 == 0 else "")
            else:
                labels.append(current.strftime("%b") if current.day == 1 and current.month % 2 == 0 else "")
        return values, labels

    def close(self) -> None:
        self.connection.close()


APPLICATION_EXECUTABLES = {
    "Photoshop": "photoshop.exe",
    "Krita": "krita.exe",
    "Clip Studio Paint": "clipstudiopaint.exe",
}


def foreground_application() -> str | None:
    """Return the supported art application owning the visible foreground window"""
    if not hasattr(ctypes, "windll"):
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    window = user32.GetForegroundWindow()
    if not window or not user32.IsWindowVisible(window):
        return None

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    if not process_id.value:
        return None

    process = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process:
        return None
    try:
        image_path = ctypes.create_unicode_buffer(32768)
        path_length = wintypes.DWORD(len(image_path))
        if not kernel32.QueryFullProcessImageNameW(process, 0, image_path, ctypes.byref(path_length)):
            return None
        executable = Path(image_path.value).name.casefold()
        return next((name for name, expected in APPLICATION_EXECUTABLES.items() if executable == expected), None)
    finally:
        kernel32.CloseHandle(process)


def user_is_active(max_idle_seconds: int = 300) -> bool:
    """Return true when Windows has received user input recently"""
    if not hasattr(ctypes, "windll"):
        return True

    class LastInputInfo(ctypes.Structure):
        _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_last_input_info = user32.GetLastInputInfo
    get_last_input_info.argtypes = [ctypes.POINTER(LastInputInfo)]
    get_last_input_info.restype = wintypes.BOOL
    get_tick_count = kernel32.GetTickCount
    get_tick_count.restype = wintypes.DWORD
    info = LastInputInfo(ctypes.sizeof(LastInputInfo), 0)
    if not get_last_input_info(ctypes.byref(info)):
        return True
    elapsed_ms = (get_tick_count() - info.dwTime) & 0xFFFFFFFF
    return elapsed_ms <= max(0, max_idle_seconds) * 1000
