import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from feedback import MAX_MESSAGE_LENGTH, FeedbackOutbox


class FeedbackOutboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.outbox_path = Path(self.temporary_directory.name) / "app-data" / "feedback-outbox.json"
        self.outbox = FeedbackOutbox(self.outbox_path, "https://example.com/feedback")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _response(self, body):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = body
        return response

    def test_feedback_is_queued_with_rating_message_and_time(self):
        self.outbox.add(4, "  Love the calendar  ", datetime(2026, 10, 1, 21, 5))
        self.outbox.add(None, "x" * (MAX_MESSAGE_LENGTH + 50))

        first, second = self.outbox.pending()
        self.assertEqual((first["rating"], first["message"], first["submitted_at"]), (4, "Love the calendar", "2026-10-01 21:05"))
        self.assertIsNone(second["rating"])
        self.assertEqual(len(second["message"]), MAX_MESSAGE_LENGTH)
        self.assertNotEqual(first["id"], second["id"])
        with self.assertRaises(ValueError):
            self.outbox.add(6, "too many stars")

    def test_all_pending_feedback_is_sent_in_one_request_and_cleared(self):
        self.outbox.add(5, "First")
        self.outbox.add(2, "Second")

        with patch("feedback.urllib.request.urlopen", return_value=self._response(b'{"ok": true}')) as urlopen_mock:
            self.assertEqual(self.outbox.send_pending(), 2)

        urlopen_mock.assert_called_once()
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/feedback")
        self.assertEqual([entry["message"] for entry in json.loads(request.data)["entries"]], ["First", "Second"])
        self.assertEqual(self.outbox.pending(), [])

    def test_feedback_stays_queued_when_delivery_fails(self):
        self.outbox.add(3, "Keep me")

        for outcome in (
            {"side_effect": OSError("offline")},
            {"return_value": self._response(b"<html>Sign in</html>")},
            {"return_value": self._response(b'{"ok": false}')},
        ):
            with self.subTest(outcome=outcome), patch("feedback.urllib.request.urlopen", **outcome):
                with self.assertRaises(RuntimeError):
                    self.outbox.send_pending()
                self.assertEqual(len(self.outbox.pending()), 1)

    def test_feedback_is_not_sent_until_an_endpoint_is_configured(self):
        outbox = FeedbackOutbox(self.outbox_path, "")
        outbox.add(5, "Waiting")

        with patch("feedback.urllib.request.urlopen") as urlopen_mock:
            self.assertEqual(outbox.send_pending(), 0)

        urlopen_mock.assert_not_called()
        self.assertFalse(outbox.configured)
        self.assertEqual(len(outbox.pending()), 1)


if __name__ == "__main__":
    unittest.main()
