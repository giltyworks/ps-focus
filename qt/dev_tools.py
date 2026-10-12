"""The developer version's menu, opened from the DEV badge in the title bar of `PS Focus.exe --dev`: ways to bring up
what normally takes days of drawing or someone else's doing, the level going up, the feedback form, the update
notice, records and friends. It runs on a copy of the data made at each start, see preview.use_preview_data, so
hours added here never reach the real history, backups or Google Drive, and feedback stays on the PC"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from app_config import APP_NAME, LEVEL_HOURS, user_level
from tracker import activity_slices

from .status_menu import PopupMenu

# The program added time is credited to
PROGRAM = "Photoshop"
# The best a week can rank, in the top percent of past weeks, for the gold medal; see stat_lines.MEDAL_TIERS
GOLD_RANK = 10


class DevPanel(PopupMenu):
    """The menu kept open beside the window, rather than closing at the first click elsewhere: a tool window that
    stays until the DEV badge is clicked again, choosing as often as wanted"""

    def __init__(self, parent, fonts, choices, on_chosen) -> None:
        super().__init__(parent, fonts, choices, None, on_chosen, min_width=220)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.pressed = self.rect().contains(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        key = self._row_at(event.position().toPoint())
        if self.pressed and event.button() == Qt.MouseButton.LeftButton and key is not None:
            self.on_chosen(key)
        self.pressed = False

    def leaveEvent(self, _event) -> None:
        if self.hovered is not None:
            self.hovered = None
            self.update()


class DevTools:
    def __init__(self, app) -> None:
        self.app = app
        self.requests_made = 0
        self.panel: DevPanel | None = None

    def open_menu(self, point: QPoint) -> None:
        """The DEV badge opens the panel, and closes it again"""
        if self.panel is not None:
            self.panel.close()
            self.panel = None
            return
        self._show_panel(point)

    def _show_panel(self, point: QPoint) -> None:
        friends = self.app.friends_sync
        choices = [
            ("level_up", "Level up", "Adds the hours to reach the next level"),
            ("celebrate", "Replay the level-up celebration", ""),
            ("feedback_reveal", "Feedback: reveal-your-level form", "Hides the level again first"),
            ("feedback", "Feedback: regular form", ""),
            ("feedback_reset", "Reset feedback", "Clears the wait and hides the level"),
            ("update", "Show the update notice", ""),
            ("hour", "Add an hour today", ""),
            ("longest", "Make today the longest session", ""),
            ("best_week", "Make this week a gold-medal week", ""),
            ("sample_friends", f"Sample friends: {'on' if friends.sample_friends else 'off'}", "Shown signed out too"),
            ("request", "Get a friend request", "Accept or decline it in Friends"),
        ]
        self.panel = panel = DevPanel(self.app.window, self.app.fonts, choices, self.choose)
        panel.destroyed.connect(lambda: setattr(self, "panel", None) if self.panel is panel else None)
        # Beside the window rather than over it, so what a tool changes stays in view: to its right, or its left when
        # the screen has no room there; with room on neither side, the roomier one
        left, top, right, _bottom = self.app.docking.main_bounds()
        screen = (QApplication.screenAt(point) or self.app.window.screen()).availableGeometry()
        room_right, room_left = screen.right() + 1 - right, left - screen.left()
        fits_right = room_right >= panel.width() + 4
        x = right + 4 if fits_right or (room_left < panel.width() + 4 and room_right >= room_left) else left - 4 - panel.width()
        panel.show_at(QPoint(x, top))

    def choose(self, key: str) -> None:
        getattr(self, key)()

    # ----- The level and feedback -----

    def level_up(self) -> None:
        level = user_level(self.app.store.total_seconds())
        if level > len(LEVEL_HOURS) - 1:
            self._tell("Already at the top level")
            return
        # A minute past the next level's hours; the next tick sees the level rise and celebrates
        self.add_today(LEVEL_HOURS[level] * 3600 - self.app.store.total_seconds() + 60)

    def celebrate(self) -> None:
        self.app.celebrate()

    def feedback_reveal(self) -> None:
        self.feedback_reset()
        self.app._open_feedback_dialog(reveal_prompt=True)

    def feedback(self) -> None:
        self.app._open_feedback_dialog()

    def feedback_reset(self) -> None:
        app = self.app
        for key in ("feedback_submitted", "feedback_count", "feedback_cooldown_until"):
            app.settings.pop(key, None)
        app._save_settings()
        app.level_revealed = False
        app._set_feedback_unlocked(app.feedback_unlocked)
        if app.header.badge_state is not None:
            app.header.set_level(app.header.badge_state[0], False)

    def update(self) -> None:
        self.app.update_announced = False
        self.app._show_available_update(("9.9.9", "https://github.com/giltyworks/ps-focus/releases/latest"))

    # ----- Hours and records -----

    def hour(self) -> None:
        self.add_today(3600)

    def longest(self) -> None:
        store, today = self.app.store, date.today()
        longest = store.longest_session()
        record = longest[1] if longest is not None and longest[0] != today else 0
        # Half an hour past the record, and at least a session's worth
        self.add_today(max(record - store.total_for_day(today), 0) + 1800)

    def best_week(self) -> None:
        store = self.app.store
        if store.week_rank() is None:
            self._tell("Medals need four weeks of history")
            return
        # An hour at a time until this week ranks among the best past weeks
        for _ in range(24 * 7):
            if store.week_rank() <= GOLD_RANK:
                break
            self.add_today(3600, refresh=False)
        self._refresh()

    def add_today(self, seconds: float, refresh: bool = True) -> None:
        """Credit this much time today, ending now; what does not fit since midnight goes in this hour"""
        now = datetime.now()
        start = max(datetime.combine(now.date(), time()), now - timedelta(seconds=seconds))
        fitted = (now - start).total_seconds()
        rows = list(activity_slices(start, fitted, PROGRAM))
        if seconds > fitted:
            rows.append((now.strftime("%Y-%m-%d"), now.hour, seconds - fitted, PROGRAM, start.strftime("%H:%M")))
        self.app.store.record_activity(rows)
        if refresh:
            self._refresh()

    # ----- Friends -----

    def sample_friends(self) -> None:
        friends = self.app.friends_sync
        friends.sample_friends = not friends.sample_friends
        friends.refresh_view()
        if self.panel is not None:
            # Its row says on or off, so the panel is made again where it stood
            where = self.panel.pos()
            self.panel.close()
            self._show_panel(where)
            self.panel.move(where)

    def request(self) -> None:
        self.requests_made += 1
        friends = self.app.friends_sync
        friends.sample_requests.append((f"DEVREQ{self.requests_made:02d}", f"Sample request {self.requests_made}"))
        friends.refresh_view()

    # -----

    def _refresh(self) -> None:
        self.app._tick()
        self.app._refresh_visible_modules()

    def _tell(self, message: str) -> None:
        self.app.tray_icon.showMessage(f"{APP_NAME} Dev", message)
