"""The version shown on the Settings page and the daily check for a newer published version"""

from __future__ import annotations

import threading
import webbrowser

from app_config import APP_VERSION
from update_check import UPDATE_CHECK_INTERVAL_MS, available_update, is_safe_download_url


class UpdateMixin:
    def _version_text(self) -> tuple[str, bool]:
        """Return the text for the top left of the Settings page, and whether it is a link to a newer version"""
        if self.available_update is not None:
            return f"Get version {self.available_update[0]}", True
        return f"Version {APP_VERSION}", False

    def _check_for_updates(self) -> None:
        try:
            threading.Thread(target=self._update_check_worker, daemon=True).start()
        finally:
            self.root.after(UPDATE_CHECK_INTERVAL_MS, self._check_for_updates)

    def _update_check_worker(self) -> None:
        try:
            update = available_update(APP_VERSION)
        except RuntimeError:
            # Offline or the endpoint is unavailable; the next daily check tries again
            return
        if update is not None:
            self.available_update = update
            self.results.put(("update", True, update[0]))

    def _show_available_update(self, version: str) -> None:
        announced = self.update_announced
        self.update_announced = True
        # The version text in the header becomes the link to the new version
        self._draw_header()
        if not announced and self.tray_icon is not None:
            try:
                self.tray_icon.notify(f"Version {version} is available. Open Settings to download it", "PS Focus update")
            except Exception:
                pass

    def _open_update_page(self) -> None:
        if self.available_update is not None and is_safe_download_url(self.available_update[1]):
            webbrowser.open(self.available_update[1])
