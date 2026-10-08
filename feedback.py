"""Local outbox that delivers queued app feedback to the PS Focus feedback endpoint"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from web import urlopen

# Web app URL of the deployed feedback_endpoint/Code.gs script; feedback stays queued locally while this is empty
FEEDBACK_ENDPOINT_URL = "https://script.google.com/macros/s/AKfycbwMRm9feeT_AHayJteW47y8_-AKgdXBEVb8P7G37XgdZcXHSrryCt_JUUbrqJBeRMO7ag/exec"
MAX_MESSAGE_LENGTH = 4000


class FeedbackOutbox:
    def __init__(self, outbox_path: Path, endpoint_url: str | None = None) -> None:
        self.outbox_path = outbox_path
        self.endpoint_url = FEEDBACK_ENDPOINT_URL if endpoint_url is None else endpoint_url
        self._lock = threading.RLock()

    @property
    def configured(self) -> bool:
        return bool(self.endpoint_url)

    def pending(self) -> list[dict]:
        with self._lock:
            try:
                entries = json.loads(self.outbox_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            return entries if isinstance(entries, list) else []

    def _write(self, entries: list[dict]) -> None:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.outbox_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        temporary.replace(self.outbox_path)

    def add(self, rating: int | None, message: str, submitted_at: datetime | None = None) -> dict:
        if rating is not None and not 1 <= rating <= 5:
            raise ValueError("Feedback rating must be between 1 and 5")
        entry = {
            "id": uuid.uuid4().hex,
            "submitted_at": (submitted_at or datetime.now()).strftime("%Y-%m-%d %H:%M"),
            "rating": rating,
            "message": message.strip()[:MAX_MESSAGE_LENGTH],
        }
        with self._lock:
            self._write(self.pending() + [entry])
        return entry

    def send_pending(self) -> int:
        """Deliver every queued entry in one request and return how many were sent"""
        entries = self.pending()
        if not self.configured or not entries:
            return 0
        request = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps({"entries": entries}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Feedback could not be delivered: {error}") from error
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError("The feedback endpoint did not accept the submission")

        sent_ids = {entry.get("id") for entry in entries}
        with self._lock:
            self._write([entry for entry in self.pending() if entry.get("id") not in sent_ids])
        return len(entries)
