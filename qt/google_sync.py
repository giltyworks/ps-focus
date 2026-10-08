"""Google workers and UI-thread results for the Qt app, using the shared Drive client."""

from __future__ import annotations

import queue
import threading
from copy import deepcopy

import app_config
from tracker import ActivityStore

from google_drive import GoogleAccountAccessRequired


class GoogleSync:
    def __init__(self, app, client) -> None:
        self.app = app
        self.client = client
        self.results = queue.Queue()
        self.busy = False
        self.email = ""
        self.reauthentication_required = False
        self.pending_settings = False
        self.pending_backup = False
        page = app.settings_page
        page.connect_button.command = self.connect
        page.reconnect_button.command = self.connect
        page.switch_button.command = self.switch
        page.logout_button.command = self.logout
        page.on_google_status = self.sync
        app.header.on_account = self.account_clicked
        self.update_status()
        if client.connected:
            self._start("account", client.account_email)

    def update_status(self) -> None:
        app = self.app
        if not self.client.connected:
            status, tone, buttons = "Not connected", "muted", "connect"
            app.header.account_text = "Local only"
        elif self.reauthentication_required:
            status, tone, buttons = "Google reconnect needed", "muted", "reconnect"
            app.header.account_text = status
        else:
            status, tone, buttons = self.email or "Google connected", "active_green", "connected"
            names = app.settings.get("google_display_names", {})
            name = names.get(self.email.casefold(), "") if isinstance(names, dict) else ""
            app.header.account_text = name if isinstance(name, str) and name else status
        app.header.account_color = tone
        app.header.account_font = app.fonts.account if self.client.connected and not self.reauthentication_required else app.fonts.small
        app.header.account_disabled = self.busy
        app.header.update()
        app.settings_page.set_google((status, tone), self.client.connected and not self.busy, buttons)
        app.settings_page.set_google_buttons_enabled(not self.busy)

    def _start(self, kind, work) -> bool:
        if self.busy or self.app.closing:
            return False
        self.busy = True
        self.update_status()
        status = {
            "account": "Loading Google account...", "connect": "Connecting...",
            "switch": "Switching account...", "logout": "Logging out...",
            "sync": "Syncing...", "settings": "Backing up settings...",
            "download": "Checking Google Drive backup...", "upload": "Uploading activity backup...",
        }[kind]
        self.app.settings_page.set_google((status, "muted"), False, self.app.settings_page.google_buttons)

        def worker():
            try:
                self.results.put((kind, True, work()))
            except Exception as error:
                self.results.put((kind, False, error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def account_clicked(self) -> None:
        if not self.client.connected or self.reauthentication_required:
            self.connect()

    def connect(self) -> None:
        if self.busy:
            return
        if self.client.connected and not self.reauthentication_required:
            self.sync()
            return
        def work():
            self.client.sign_in()
            return self.client.account_email()

        self._start("connect", work)

    def switch(self) -> None:
        if self.busy:
            return
        # Once switching begins, the previous email must not label a new token if lookup fails.
        self.email = ""
        def work():
            self.client.sign_out()
            self.client.sign_in()
            return self.client.account_email()

        self._start("switch", work)

    def logout(self) -> None:
        if self.client.connected:
            self._start("logout", self.client.sign_out)

    def settings_changed(self) -> None:
        if self.busy:
            self.pending_settings = True
        elif self.client.connected and not self.reauthentication_required:
            settings = deepcopy(self.app.settings)
            self._start("settings", lambda: self.client.upload_settings(settings))

    def sync(self) -> None:
        if self.busy or not self.client.connected:
            return
        if self.reauthentication_required:
            self.connect()
            return
        settings = deepcopy(self.app.settings)
        self._start("sync", lambda: self.client.upload_settings(settings))

    def backup(self) -> None:
        if not self.client.connected or self.reauthentication_required:
            return
        if self.busy:
            self.pending_backup = True
            return
        self._start("download", self.client.download_activity_backup)

    def _apply_download(self, content: bytes) -> None:
        app = self.app
        if ActivityStore.database_has_user_data(app_config.DATABASE_PATH):
            if app.store.merge_backup_bytes(content) is None:
                raise ValueError("Google Drive backup was invalid; local history was kept")
        else:
            app.store.close()
            try:
                restored = ActivityStore.restore_backup_bytes(app_config.DATABASE_PATH, content, app_config.BACKUP_DIRECTORIES[0])
                if not restored:
                    raise ValueError("Google Drive backup was invalid; local history was kept")
            finally:
                app.store = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
                for module in app.modules.values():
                    module.store = app.store
        app._refresh_visible_modules()

    def poll(self) -> None:
        if self.app.closing:
            return
        while True:
            try:
                kind, success, value = self.results.get_nowait()
            except queue.Empty:
                return
            self.busy = False
            if not success:
                if not self.client.connected:
                    self.email = ""
                if isinstance(value, GoogleAccountAccessRequired):
                    self.reauthentication_required = True
                self.update_status()
                self.app.settings_page.set_google((str(value), "red"), self.client.connected, self.app.settings_page.google_buttons)
                if kind in ("download", "upload"):
                    self.app.settings_page.set_backup_status(f"Local copies saved; Google Drive backup failed: {value}", "red")
            else:
                if kind in ("account", "connect", "switch"):
                    self.email = value
                    self.reauthentication_required = False
                elif kind == "logout":
                    self.email = ""
                    self.reauthentication_required = False
                    self.pending_settings = self.pending_backup = False
                self.update_status()
                if kind == "logout" and not value:
                    self.app.settings_page.set_google(("Signed out locally; Google token revocation could not be confirmed", "orange"), False, "connect")
                if kind in ("connect", "switch"):
                    # Sign-in has succeeded even if the subsequent settings upload fails.
                    # Take the latest settings on the UI thread after the browser flow completes.
                    self.pending_settings = False
                    self.sync()
                elif kind == "sync":
                    self.app._backup_activity_now()
                elif kind == "download":
                    try:
                        # SQLite belongs to the UI thread, including restore and module rebinding.
                        if value is not None:
                            self._apply_download(value)
                        path = self.app.store.create_local_backups()[0]
                        content = path.read_bytes()
                    except Exception as error:
                        self.app.settings_page.set_backup_status(f"Could not merge Google Drive backup: {error}", "red")
                    else:
                        self._start("upload", lambda payload=content: self.client.upload_activity_backup(payload))
                elif kind == "upload":
                    self.app.settings_page.set_backup_status("Activity backup saved to Google Drive", "active_green")
            if self.pending_settings and not self.busy:
                self.pending_settings = False
                self.settings_changed()
            if self.pending_backup and not self.busy:
                self.pending_backup = False
                self.backup()
