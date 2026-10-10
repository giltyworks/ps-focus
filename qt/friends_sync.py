"""Friends for the Qt app: checks in with the friends server on a background thread every few minutes, and sooner
when the user starts or stops drawing, and hands what comes back to the friends module"""

from __future__ import annotations

import queue
import threading
import time
from datetime import date, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from app_config import APP_NAME, user_level
from friends import FriendsService
from google_drive import GoogleAccountAccessRequired

from .friends_module import FriendsModule, FriendsView

# How often the figures are handed over while nothing changes. Kept to every ten minutes, so the free server allowance
# covers well over a thousand people a day
SYNC_INTERVAL_MS = 10 * 60 * 1000
# Drawing counts as going on for this long after the last tracked second, so a moment in another window does not
# tell friends the user stopped
ACTIVE_LINGER_SECONDS = 120
# The least time between check-ins made for starting or stopping drawing
MIN_SYNC_GAP_SECONDS = 60
# A friend not heard from in this long is not shown as drawing now, as their PC may have gone off mid-session
STALE_SECONDS = 15 * 60


class FriendsSync:
    def __init__(self, app, module: FriendsModule, service: FriendsService) -> None:
        self.app = app
        self.module = module
        self.service = service
        self.results: queue.Queue = queue.Queue()
        self.busy = False
        # The server's last answer for the account it was asked about, and a message to show under the list
        self.state: dict | None = None
        self.state_account = ""
        # The account last checked in for
        self.asked_account = ""
        self.message: tuple[str, str] | None = None
        self.last_sync = 0.0
        self.pending_sync = False
        self.last_active_time = 0.0
        self.active_program: str | None = None
        self.reported_active: str | None = None
        actions = module.actions
        actions.sign_in = app.google_sync.connect
        actions.turn_on = self.turn_on
        actions.turn_off = self.turn_off
        actions.add = lambda code: self._start("add", lambda: self.service.add(code))
        actions.accept = lambda code: self._start("accept", lambda: self.service.accept(code))
        actions.decline = lambda code: self._start("decline", lambda: self.service.decline(code))
        actions.cancel = lambda code: self._start("cancel", lambda: self.service.remove(code))
        actions.remove = self.remove
        actions.copy_code = lambda code: QGuiApplication.clipboard().setText(code)
        self.timer = QTimer(interval=SYNC_INTERVAL_MS, timeout=self.sync)
        self.timer.start()
        self.refresh_view()

    # ----- Who, and whether friends are on -----

    def account(self) -> str:
        """The connected Google account friends are kept for, or none"""
        google = self.app.google_sync
        if not self.app.google_sync.client.connected or google.reauthentication_required or not google.email:
            return ""
        return google.email.casefold()

    def _enabled_accounts(self) -> list[str]:
        accounts = self.app.settings.get("friends_accounts")
        return [account for account in accounts if isinstance(account, str)] if isinstance(accounts, list) else []

    def enabled(self) -> bool:
        return self.service.configured and bool(self.account()) and self.account() in self._enabled_accounts()

    def _set_enabled(self, on: bool) -> None:
        accounts = [account for account in self._enabled_accounts() if account != self.account()]
        self.app.settings["friends_accounts"] = accounts + ([self.account()] if on else [])
        self.app._save_settings()

    def account_changed(self) -> None:
        """Signed in, out, or to another account: forget the last account's friends and check in for the new one"""
        account = self.account()
        if self.state_account != account:
            self.state = None
            self.message = None
        self.refresh_view()
        # Called after every Google result, backups included, so it checks in only for an account not yet asked about
        if self.enabled() and self.asked_account != account:
            self.sync()

    # ----- Check-ins -----

    def name(self) -> str:
        """The name friends see: the one chosen for the account, or the start of its email"""
        google = self.app.google_sync
        return google.display_name() or google.email.split("@")[0]

    def stats(self) -> dict:
        store, today = self.app.store, date.today()
        total = store.total_seconds()
        return {
            "two_weeks": store.total_for_range(today - timedelta(days=13), today) / 3600,
            "total": total / 3600,
            "today": store.total_for_day(today) / 3600,
            "week": store.total_for_range(today - timedelta(days=today.weekday()), today) / 3600,
            "level": user_level(total),
            "streak": store.calendar_streaks(today)[0],
            "active": self.active_program,
        }

    def tick(self, program: str | None) -> None:
        """Called every second with the program being drawn in, if any; a change in what friends would see as drawing
        now is sent once it has lasted, and no sooner than a minute after the last check-in"""
        now = time.monotonic()
        if program:
            self.last_active_time = now
            self.active_program = program
        elif self.active_program and now - self.last_active_time > ACTIVE_LINGER_SECONDS:
            self.active_program = None
        if self.enabled() and self.active_program != self.reported_active and now - self.last_sync >= MIN_SYNC_GAP_SECONDS:
            self.sync()

    def sync(self) -> None:
        if not self.enabled():
            return
        if self.busy:
            self.pending_sync = True
            return
        name, stats = self.name(), self.stats()
        self.reported_active = stats["active"]
        self.asked_account = self.account()
        self.last_sync = time.monotonic()
        self._start("sync", lambda: self.service.sync(name, stats))

    def _start(self, kind: str, work) -> None:
        if self.busy or self.app.closing:
            return
        self.busy = True
        account = self.account()
        self.refresh_view()

        def worker():
            try:
                self.results.put((kind, account, True, work()))
            except Exception as error:
                self.results.put((kind, account, False, error))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self) -> None:
        while True:
            try:
                kind, account, success, value = self.results.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            # An answer for an account since signed out of is dropped
            if account != self.account():
                continue
            if success:
                self.message = None
                if kind == "leave":
                    self.state = None
                    self._set_enabled(False)
                else:
                    self.state, self.state_account = value, account
                    if kind == "add":
                        self.message = ("Request sent", "muted") if value.get("outgoing") else None
            elif isinstance(value, GoogleAccountAccessRequired):
                self.message = ("Reconnect Google in Settings to use friends", "orange")
            else:
                self.message = (str(value), "red" if kind != "sync" else "orange")
            self.refresh_view()
        if self.pending_sync and not self.busy:
            self.pending_sync = False
            self.sync()

    # ----- What the user does -----

    def turn_on(self) -> None:
        if not self.account():
            return
        self._set_enabled(True)
        self.refresh_view()
        self.sync()

    def turn_off(self) -> None:
        answer = QMessageBox.question(
            self.app.window, APP_NAME,
            "Turn off friends?\n\nYour friends list and friend code are deleted. Friends need your new code to add you again.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start("leave", self.service.leave)

    def remove(self, code: str, name: str) -> None:
        answer = QMessageBox.question(self.app.window, APP_NAME, f"Remove {name} from your friends?")
        if answer == QMessageBox.StandardButton.Yes:
            self._start("remove", lambda: self.service.remove(code))

    # ----- Showing it -----

    def view(self) -> FriendsView:
        if not self.service.configured:
            return FriendsView("unavailable")
        if not self.account():
            return FriendsView("signed_out", message=self.message, busy=self.app.google_sync.busy)
        if not self.enabled():
            return FriendsView("off", message=self.message, busy=self.busy)
        state = self.state if self.state_account == self.account() else None
        if not state or not state.get("me"):
            return FriendsView("loading", message=self.message, busy=self.busy)
        now = state.get("now", 0)
        me = state["me"]
        people = [(me.get("name", ""), self.stats(), True, self.active_program, me.get("code", ""))]
        for friend in state.get("friends", []):
            stats = friend.get("stats") or {}
            fresh = now - friend.get("updated_at", 0) <= STALE_SECONDS
            people.append((friend.get("name", ""), stats, False, stats.get("active") if fresh else None, friend.get("code", "")))
        people.sort(key=lambda person: -float(person[1].get("two_weeks", 0) or 0))
        return FriendsView(
            "on", me.get("code", ""), people,
            [(request["code"], request["name"]) for request in state.get("incoming", [])],
            [(request["code"], request["name"]) for request in state.get("outgoing", [])],
            self.message, self.busy,
        )

    def refresh_view(self) -> None:
        self.module.show_view(self.view())
