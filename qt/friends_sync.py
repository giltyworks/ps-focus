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
from .request_popup import RequestPopup
from .header import NAME_MAX_LENGTH
from .status_menu import PopupMenu, StatusMenu

# How often the figures are handed over while nothing changes. Kept to every ten minutes, so the free server allowance
# covers well over a thousand people a day
SYNC_INTERVAL_MS = 10 * 60 * 1000
# Drawing counts as going on for this long after the last tracked second, so a moment in another window does not
# tell friends the user stopped
ACTIVE_LINGER_SECONDS = 120
# The least time between check-ins made for starting or stopping drawing, or for the mouse coming onto the module
MIN_SYNC_GAP_SECONDS = 60
# A friend not heard from in this long is not shown as drawing now, as their PC may have gone off mid-session
STALE_SECONDS = 15 * 60
# The statuses the user can choose, by the menu next to their name, and what friends are told of each
STATUSES = ("online", "away", "invisible", "offline")
STATUS_SENT = {"online": "online", "away": "away", "invisible": "offline", "offline": "offline"}


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
        # Whether friends have been told the user went offline, after which nothing more is sent
        self.offline_announced = False
        # Answers to requests waiting for a check-in to finish; the requests a popup has been shown for this session,
        # and the popups open, by the sender's code
        self.pending_actions: list = []
        self.seen_requests: set[str] = set()
        self.popups: dict[str, RequestPopup] = {}
        actions = module.actions
        actions.sign_in = app.google_sync.connect
        actions.delete_data = self.delete_data
        actions.add = lambda code: self._start("add", lambda: self.service.add(code))
        actions.accept = lambda code: self._start("accept", lambda: self.service.accept(code))
        actions.decline = lambda code: self._start("decline", lambda: self.service.decline(code))
        actions.cancel = lambda code: self._start("cancel", lambda: self.service.remove(code))
        actions.person_menu = self.person_menu
        actions.copy_code = lambda code: QGuiApplication.clipboard().setText(code)
        app.header.on_status = self.open_status_menu
        actions.looked_at = self.looked_at
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

    def enabled(self) -> bool:
        """Friends are on whenever a Google account is connected; the status menu sets what friends see"""
        return self.service.configured and bool(self.account())

    def account_changed(self) -> None:
        """Signed in, out, or to another account: forget the last account's friends and check in for the new one"""
        account = self.account()
        if self.state_account != account:
            self.state = None
            self.message = None
            self.pending_actions.clear()
            saved = self.app.settings.get("friends_seen_requests")
            seen = saved.get(account, []) if isinstance(saved, dict) else []
            self.seen_requests = {code for code in seen if isinstance(code, str)}
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
            "status": STATUS_SENT[self.status()],
            "active": self.shown_program(),
        }

    def status(self) -> str:
        status = self.app.settings.get("friends_status")
        return status if status in STATUSES else "online"

    def shown_program(self) -> str | None:
        """What friends are told the user is drawing in: nothing while away, invisible or offline"""
        return self.active_program if self.status() == "online" else None

    def set_status(self, status: str) -> None:
        """Chosen in the menu next to the user's name. Friends are told at once; offline then stops the check-ins, with
        that one telling friends the user went offline"""
        if status == self.status():
            return
        self.app.settings["friends_status"] = status
        self.app._save_settings()
        self.offline_announced = False
        self.refresh_view()
        self.sync()

    def tick(self, program: str | None) -> None:
        """Called every second with the program being drawn in, if any; a change in what friends would see as drawing
        now is sent once it has lasted, and no sooner than a minute after the last check-in"""
        now = time.monotonic()
        if program:
            self.last_active_time = now
            self.active_program = program
        elif self.active_program and now - self.last_active_time > ACTIVE_LINGER_SECONDS:
            self.active_program = None
        if self.enabled() and self.shown_program() != self.reported_active and now - self.last_sync >= MIN_SYNC_GAP_SECONDS:
            self.sync()

    def looked_at(self) -> None:
        """Friends are brought up to date when the mouse comes onto the module, if not checked a minute ago"""
        if time.monotonic() - self.last_sync >= MIN_SYNC_GAP_SECONDS:
            self.sync()

    def sync(self) -> None:
        if not self.enabled() or (self.status() == "offline" and self.offline_announced):
            return
        if self.busy:
            self.pending_sync = True
            return
        if self.status() == "offline":
            self.offline_announced = True
        name, stats = self.name(), self.stats()
        self.reported_active = stats["active"]
        self.asked_account = self.account()
        self.last_sync = time.monotonic()
        self._start("sync", lambda: self.service.sync(name, stats))

    def _start(self, kind: str, work) -> None:
        if self.app.closing:
            return
        if self.busy:
            # Something the user did, such as accepting from a popup, waits for the check-in under way
            if kind != "sync":
                self.pending_actions.append((kind, work))
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
                    self.message = ("Your friends list and code were deleted", "muted")
                else:
                    self.state, self.state_account = value, account
                    if kind == "add":
                        self.message = ("Request sent", "muted") if value.get("outgoing") else None
            elif isinstance(value, GoogleAccountAccessRequired):
                self.message = ("Reconnect Google in Settings to use friends", "orange")
            else:
                self.message = (str(value), "red" if kind != "sync" else "orange")
            self.refresh_view()
        if self.pending_actions and not self.busy:
            self._start(*self.pending_actions.pop(0))
        if self.pending_sync and not self.busy:
            self.pending_sync = False
            self.sync()

    # ----- What the user does -----

    def delete_data(self) -> None:
        """Offered while offline: delete everything the friends server keeps. Going online again starts afresh, with a
        new code"""
        answer = QMessageBox.question(
            self.app.window, APP_NAME,
            "Delete your friends data?\n\nYour friends list and friend code are deleted from the friends server. Going "
            "online again gives you a new code, and friends need it to add you again.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start("leave", self.service.leave)

    def _local(self, key: str):
        """What the user keeps about their friends on this PC alone, for the connected account: favourites, a list of
        codes, and nicknames, by code"""
        saved = self.app.settings.get(key)
        value = saved.get(self.account()) if isinstance(saved, dict) else None
        if key == "friends_favourites":
            return [code for code in value if isinstance(code, str)] if isinstance(value, list) else []
        return {code: name for code, name in value.items() if isinstance(name, str)} if isinstance(value, dict) else {}

    def _set_local(self, key: str, value) -> None:
        saved = self.app.settings.get(key)
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved[self.account()] = value
        self.app.settings[key] = saved
        self.app._save_settings()
        self.refresh_view()

    def person_menu(self, code: str, name: str, point) -> None:
        """The menu a friend's row opens: favourite or not, a nickname, and removing them"""
        favourite = code in self._local("friends_favourites")
        nickname = self._local("friends_nicknames").get(code)
        choices = [
            ("favourite", "Remove from favourites" if favourite else "Add to favourites", ""),
            ("nickname", "Change nickname" if nickname else "Set nickname", ""),
        ]
        if nickname:
            choices.append(("clear_nickname", "Clear nickname", ""))
        choices.append(("danger_remove", "Remove friend", ""))
        PopupMenu(self.app.window, self.app.fonts, choices, None, lambda key: self._person_chosen(key, code, name)).show_at(point)

    def _person_chosen(self, key: str, code: str, name: str) -> None:
        if key == "favourite":
            favourites = self._local("friends_favourites")
            self._set_local("friends_favourites", [other for other in favourites if other != code] if code in favourites else favourites + [code])
        elif key == "nickname":
            self.module.edit_nickname(code, name, lambda nickname: self._nickname_chosen(code, nickname))
        elif key == "clear_nickname":
            self._nickname_chosen(code, "")
        elif key == "danger_remove":
            self.remove(code, name)

    def _nickname_chosen(self, code: str, nickname: str | None) -> None:
        if nickname is None:
            return
        nicknames = self._local("friends_nicknames")
        nickname = nickname.strip()[:NAME_MAX_LENGTH]
        if nickname:
            nicknames[code] = nickname
        else:
            nicknames.pop(code, None)
        self._set_local("friends_nicknames", nicknames)

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
        if self.status() == "offline":
            return FriendsView("offline", message=self.message, busy=self.busy)
        state = self.state if self.state_account == self.account() else None
        if not state or not state.get("me"):
            return FriendsView("loading", message=self.message, busy=self.busy)
        now = state.get("now", 0)
        me = state["me"]
        people = []
        for friend in state.get("friends", []):
            stats = friend.get("stats") or {}
            # Someone not heard from lately, whose PC may have gone off, shows as offline
            fresh = now - friend.get("updated_at", 0) <= STALE_SECONDS
            status = stats.get("status", "online") if fresh else "offline"
            program = stats.get("active") if status == "online" else None
            presence = "drawing" if program else status
            code = friend.get("code", "")
            # A nickname the user gave them shows in place of their name
            name = self._local("friends_nicknames").get(code) or friend.get("name", "")
            people.append((name, stats, presence, program, code, code in self._local("friends_favourites")))
        # Favourites first, then by hours over the past two weeks
        people.sort(key=lambda person: (not person[5], -float(person[1].get("two_weeks", 0) or 0)))
        return FriendsView(
            "on", me.get("code", ""), people,
            [(request["code"], request["name"]) for request in state.get("incoming", [])],
            [(request["code"], request["name"]) for request in state.get("outgoing", [])],
            self.message, self.busy,
        )

    def refresh_view(self) -> None:
        self.module.show_view(self.view())
        self._update_popups()
        # The status menu is offered next to the account name while friends are on
        header = self.app.header
        if header.status_arrow_shown != self.enabled():
            header.status_arrow_shown = self.enabled()
            header.update()

    def _update_popups(self) -> None:
        """A popup for each friend request not yet shown, and none for requests answered or withdrawn since"""
        state = self.state if self.state_account == self.account() and self.enabled() and self.status() != "offline" else None
        incoming = {request["code"]: request["name"] for request in (state or {}).get("incoming", [])}
        for code in [code for code in self.popups if code not in incoming]:
            self.popups[code].close()
        if state is not None:
            self._remember_seen_requests(set(incoming))
        for code, name in incoming.items():
            if code in self.seen_requests:
                continue
            self.seen_requests.add(code)
            self._remember_seen_requests(set(incoming))
            popup = RequestPopup(
                self.app.window, self.app.fonts, code, name,
                lambda code=code: self.module.actions.accept(code), lambda code=code: self.module.actions.decline(code),
            )
            popup.on_closed = self._popup_closed
            self.popups[code] = popup
            popup.place(len(self.popups) - 1)
            popup.show()

    def _remember_seen_requests(self, waiting: set[str]) -> None:
        """Keep the requests popped up for, of those still waiting, so a restart does not show them again"""
        seen = sorted(self.seen_requests & waiting)
        saved = self.app.settings.get("friends_seen_requests")
        saved = dict(saved) if isinstance(saved, dict) else {}
        if saved.get(self.account()) != seen:
            saved[self.account()] = seen
            self.app.settings["friends_seen_requests"] = saved
            self.app._save_settings(upload=False)

    def close_popups(self) -> None:
        for popup in list(self.popups.values()):
            popup.close()

    def _popup_closed(self, popup: RequestPopup) -> None:
        self.popups.pop(popup.code, None)
        # Those left close up into the corner
        for index, other in enumerate(self.popups.values()):
            other.place(index)

    def open_status_menu(self, point) -> None:
        StatusMenu(self.app.window, self.app.fonts, self.status(), self.set_status).show_at(point)
