"""Google account connection, display name, and account status shown in the header and settings"""

from __future__ import annotations

import threading

from app_config import COLORS
from google_drive import GoogleAccountAccessRequired


class GoogleMixin:
    def _display_names(self) -> dict:
        names = self.settings.get("google_display_names")
        return names if isinstance(names, dict) else {}

    def _display_name(self) -> str:
        """Return the name chosen for the connected Google account; each account keeps its own on this PC"""
        if not self.google_account_email:
            return ""
        name = self._display_names().get(self.google_account_email.casefold(), "")
        return name if isinstance(name, str) else ""

    def _set_display_name(self, name: str) -> None:
        names = dict(self._display_names())
        if name:
            names[self.google_account_email.casefold()] = name
        else:
            names.pop(self.google_account_email.casefold(), None)
        self.settings["google_display_names"] = names

    def _adopt_legacy_display_name(self) -> None:
        """Give the single name saved by earlier versions to the account that was connected when it was chosen"""
        legacy_name = self.settings.get("google_display_name")
        if not legacy_name or not self.google_account_email:
            return
        if isinstance(legacy_name, str) and not self._display_name():
            self._set_display_name(legacy_name[:32])
        self.settings["google_display_name"] = ""
        self._save_settings()

    def _can_rename_account(self) -> bool:
        return (
            self.google.connected
            and not self.google_reauthentication_required
            and str(self.account_label.cget("state")) != "disabled"
        )

    def _account_label_clicked(self) -> None:
        if not self.google.connected or self.google_reauthentication_required:
            self._connect_google()

    def _account_label_double_clicked(self) -> None:
        if self._can_rename_account():
            self._begin_display_name_edit()

    def _resync_google(self) -> None:
        if (
            not self.google.connected
            or self.settings_resync_in_progress
            or str(self.account_label.cget("state")) == "disabled"
        ):
            return
        if self.google_reauthentication_required:
            self._connect_google()
            return
        self.settings_resync_in_progress = True
        self._set_google_action_state("disabled")
        self.google_settings_status.configure(text="Syncing…", fg=COLORS["muted"])
        threading.Thread(target=self._resync_worker, daemon=True).start()

    def _resync_worker(self) -> None:
        try:
            self.google.upload_settings(self.settings.copy())
            self.results.put(("drive_backup", True, ""))
            self.results.put(("resync", True, "Settings backed up to Google Drive"))
        except Exception as error:
            self.results.put(("resync", False, str(error)))

    def _begin_display_name_edit(self) -> None:
        self.editing_display_name = True
        self.account_name_entry.delete(0, "end")
        self.account_name_entry.insert(0, self._display_name() or self.google_account_email or "")
        self.account_label.grid_remove()
        self.account_name_entry.grid(row=0, column=1, sticky="n", pady=2)
        self.account_name_entry.focus_set()
        self.account_name_entry.select_range(0, "end")

    def _finish_display_name_edit(self, save: bool) -> None:
        if not self.editing_display_name:
            return
        self.editing_display_name = False
        self.account_name_entry.grid_remove()
        self.account_label.grid()
        if save and self.google_account_email:
            name = self.account_name_entry.get().strip()
            name = "" if name == self.google_account_email else name[:32]
            if name != self._display_name():
                self._set_display_name(name)
                self._save_settings()
        self._update_google_status()

    def _connect_google(self) -> None:
        syncing = self.google.connected and not self.google_reauthentication_required
        self.account_label.configure(state="disabled", text="Syncing…" if syncing else "Connecting…")
        self._set_google_action_state("disabled")
        worker = self._sync_worker if syncing else self._connect_worker
        threading.Thread(target=worker, daemon=True).start()

    def _set_google_action_state(self, state: str) -> None:
        for button in (
            self.google_connect_button,
            self.google_reconnect_button,
            self.google_switch_button,
            self.google_logout_button,
        ):
            button.configure(state=state)

    def _sync_worker(self) -> None:
        try:
            self.google.upload_settings(self.settings.copy())
            self.results.put(("drive_backup", True, ""))
            self.results.put(("sync", True, "Settings backed up to Google Drive"))
        except Exception as error:
            self.results.put(("sync", False, str(error)))

    def _connect_worker(self) -> None:
        try:
            self.google.sign_in()
            self.google.upload_settings(self.settings.copy())
            self.results.put(("drive_backup", True, ""))
            self.results.put(("connect", True, self.google.account_email()))
        except Exception as error:
            self.results.put(("connect", False, str(error)))

    def _switch_google_account(self) -> None:
        if not self.google.connected:
            self._connect_google()
            return
        self.account_label.configure(state="disabled")
        self.account_label.configure(text="Switching account…")
        self._set_google_action_state("disabled")
        threading.Thread(target=self._switch_google_worker, daemon=True).start()

    def _switch_google_worker(self) -> None:
        try:
            self.google.sign_out()
            self.google.sign_in()
            self.google.upload_settings(self.settings.copy())
            self.results.put(("drive_backup", True, ""))
            self.results.put(("switch", True, self.google.account_email()))
        except Exception as error:
            self.results.put(("switch", False, str(error)))

    def _logout_google(self) -> None:
        if not self.google.connected:
            return
        self.account_label.configure(state="disabled", text="Logging out…")
        self._set_google_action_state("disabled")
        threading.Thread(target=self._logout_google_worker, daemon=True).start()

    def _logout_google_worker(self) -> None:
        try:
            revoked = self.google.sign_out()
            message = "Signed out of Google" if revoked else "Signed out locally; Google token revocation could not be confirmed"
            self.results.put(("logout", True, message))
        except Exception as error:
            self.results.put(("logout", False, f"Could not sign out of Google: {error}"))

    def _load_google_account(self) -> None:
        try:
            self.results.put(("account", True, self.google.account_email()))
        except GoogleAccountAccessRequired as error:
            self.results.put(("reauth", False, str(error)))
        except Exception as error:
            self.results.put(("account", False, str(error)))

    def _update_google_status(self, email: str | None = None) -> None:
        if email:
            self.google_account_email = email
            self._adopt_legacy_display_name()
        if self.google.connected:
            if self.google_reauthentication_required:
                account_status = "Google reconnect needed"
                header_status = account_status
                header_font = self.font_small
                account_color = COLORS["muted"]
            else:
                account_status = self.google_account_email or "Google connected"
                header_status = self._display_name() or account_status
                header_font = self.font_account
                account_color = COLORS["active_green"]
            self.account_label.configure(text=header_status, fg=account_color, font=header_font)
            self.google_settings_status.configure(text=account_status, fg=account_color, cursor="hand2")
        else:
            self.account_label.configure(text="Local only", fg=COLORS["muted"], font=self.font_small)
            self.google_settings_status.configure(text="Not connected", fg=COLORS["muted"], cursor="")
        self._arrange_google_buttons()

    def _arrange_google_buttons(self) -> None:
        """Lay out the Google buttons on the row they share with Back up now, which stays at its left end

        The row holds three buttons at most: one against the right edge and one in the middle. A sign-in that
        needs renewing shows Reconnect in the middle in place of Switch account, as four would not fit
        """
        for button in (self.google_connect_button, self.google_reconnect_button, self.google_switch_button, self.google_logout_button):
            button.pack_forget()
        if not self.google.connected:
            self.google_connect_button.pack(side="right")
            return
        self.google_logout_button.pack(side="right")
        middle = self.google_reconnect_button if self.google_reauthentication_required else self.google_switch_button
        middle.pack(side="left", expand=True)

    def _message(self, message: str, error: bool = False) -> None:
        color = COLORS["red"] if error else COLORS["active_green"] if self.google.connected and not self.google_reauthentication_required else COLORS["muted"]
        self.account_label.configure(text=message[:48], fg=color, font=self.font_small)
        if not error and self.google.connected:
            self.root.after(5000, self._update_google_status)
