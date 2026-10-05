"""Local activity backups and their Google Drive upload, merge, and restore cycle"""

from __future__ import annotations

import threading
from pathlib import Path

import app_config
from app_config import BACKUP_INTERVAL_MS, COLORS
from tracker import ActivityStore


class BackupMixin:
    def _periodic_activity_backup(self) -> None:
        try:
            self._backup_activity_now()
            self._send_pending_feedback()
        finally:
            self.root.after(BACKUP_INTERVAL_MS, self._periodic_activity_backup)

    def _backup_activity_now(self, force: bool = False) -> None:
        """Snapshot the history and sync it with Google Drive; `force` writes a snapshot even when nothing changed"""
        try:
            backup_paths = self.store.create_local_backups(force=force)
        except Exception as error:
            self.activity_backup_status.configure(text=f"Local backup failed: {error}", fg=COLORS["red"])
            return

        if not self.google.connected:
            self.activity_backup_status.configure(
                text="Local backups saved in Documents and OneDrive folders when available",
                fg=COLORS["muted"],
            )
            return
        if self.backup_in_progress:
            self.activity_backup_status.configure(
                text="Local backups saved, Google Drive backup is already in progress",
                fg=COLORS["muted"],
            )
            return

        self.backup_in_progress = True
        self.drive_backup_path = backup_paths[0]
        self.activity_backup_status.configure(text="Local backups saved, updating Google Drive backup", fg=COLORS["muted"])
        threading.Thread(target=self._drive_backup_worker, args=(backup_paths[0],), daemon=True).start()

    def _upload_activity_backup(self, backup_path: Path) -> None:
        try:
            self.google.upload_activity_backup(backup_path.read_bytes())
            self.results.put(("backup", True, "Activity backup saved to Google Drive"))
        except Exception as error:
            self.results.put(("backup", False, f"Local copies saved; Google Drive backup failed: {error}"))

    def _drive_backup_worker(self, backup_path: Path) -> None:
        try:
            remote_backup = self.google.download_activity_backup()
        except Exception as error:
            self.results.put(("backup", False, f"Local copies saved; Google Drive backup failed: {error}"))
            return
        if remote_backup is None:
            self._upload_activity_backup(backup_path)
            return
        # The database connection belongs to the UI thread, so it applies the downloaded history
        self.remote_backup_payloads.put(remote_backup)
        if ActivityStore.database_has_user_data(app_config.DATABASE_PATH):
            self.results.put(("merge_backup", True, ""))
        else:
            self.results.put(("restore_backup", True, ""))

    def _merge_downloaded_activity_backup(self, content: bytes) -> None:
        backup_path = self.drive_backup_path
        try:
            changed_rows = self.store.merge_backup_bytes(content)
            if changed_rows:
                backup_path = self.store.create_local_backups()[0]
        except Exception as error:
            self.backup_in_progress = False
            self.activity_backup_status.configure(text=f"Could not merge Google Drive backup: {error}", fg=COLORS["red"])
            return
        if changed_rows:
            self._refresh_activity_views()
        threading.Thread(target=self._upload_activity_backup, args=(backup_path,), daemon=True).start()

    def _restore_downloaded_activity_backup(self, content: bytes) -> None:
        if ActivityStore.database_has_user_data(app_config.DATABASE_PATH):
            self._merge_downloaded_activity_backup(content)
            return
        self.backup_in_progress = False
        self.store.close()
        try:
            restored = ActivityStore.restore_backup_bytes(app_config.DATABASE_PATH, content, app_config.BACKUP_DIRECTORIES[0])
        except Exception as error:
            self.activity_backup_status.configure(text=f"Could not restore Google Drive backup: {error}", fg=COLORS["red"])
            restored = False
        finally:
            self.store = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
        if not restored:
            self.activity_backup_status.configure(text="Google Drive backup was invalid; local history was kept", fg=COLORS["red"])
            return
        self.activity_backup_status.configure(text="Activity history restored from Google Drive", fg=COLORS["active_green"])
        self._refresh_activity_views()
