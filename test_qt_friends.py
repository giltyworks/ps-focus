"""The friends module and its check-ins with the friends server, which a stand-in replaces here"""

from __future__ import annotations

import http.server
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError:
    QApplication = None

from friends import FriendsError, FriendsService, format_code


def server_state(friends=(), incoming=(), outgoing=(), now=1000):
    return {"now": now, "me": {"code": "ABCD2345", "name": "Amy"}, "friends": list(friends), "incoming": list(incoming), "outgoing": list(outgoing)}


class FakeService:
    configured = True

    def __init__(self):
        self.calls = []
        self.answer = server_state()
        self.error: Exception | None = None

    def _call(self, *call):
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        return self.answer

    def sync(self, name, stats):
        return self._call("sync", name, stats)

    def add(self, code):
        return self._call("add", code)

    def accept(self, code):
        return self._call("accept", code)

    def decline(self, code):
        return self._call("decline", code)

    def remove(self, code):
        return self._call("remove", code)

    def leave(self):
        self._call("leave")
        return {"left": True}


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtFriendsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        import app_config
        from qt.app import PSFocusQt

        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        self.account = "amy@example.com"
        self.patches = [
            patch.object(app_config, "APP_DATA", folder),
            patch.object(app_config, "DATABASE_PATH", folder / "activity.sqlite3"),
            patch.object(app_config, "SETTINGS_PATH", folder / "settings.json"),
            patch.object(app_config, "BACKUP_DIRECTORIES", [folder / "backups"]),
            patch("qt.app.load_settings", return_value={**app_config.DEFAULT_SETTINGS, "show_friends": True}),
            patch("qt.app.foreground_application", return_value=None),
            patch.object(PSFocusQt, "_start_tray_icon"),
            patch.object(PSFocusQt, "_check_for_updates"),
            patch("qt.window.MainWindow.place_top_right"),
            patch("qt.friends_sync.FriendsSync.account", lambda _self: self.account),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temporary.cleanup)
        for item in self.patches:
            self.addCleanup(item.stop)
        self.app = PSFocusQt(self.application)
        for timer in (self.app.tick_timer, self.app.poll_timer, self.app.backup_timer, self.app.friends_sync.timer):
            timer.stop()
        self.addCleanup(lambda: self.app.store.close())
        self.addCleanup(self.app.window.hide)
        self.service = FakeService()
        self.sync = self.app.friends_sync
        self.sync.service = self.service
        self.app.google_sync.email = self.account

    def _settle(self):
        deadline = time.monotonic() + 5
        while (self.sync.busy or not self.sync.results.empty()) and time.monotonic() < deadline:
            time.sleep(0.01)
            self.sync.poll()
        self.application.processEvents()

    def _turn_on(self):
        self.sync.turn_on()
        self._settle()

    def test_starts_in_landscape(self):
        import app_config
        from qt.app import PSFocusQt

        with patch("qt.app.load_settings", return_value={**app_config.DEFAULT_SETTINGS, "show_friends": True, "landscape": True}):
            app = PSFocusQt(self.application)
        for timer in (app.tick_timer, app.poll_timer, app.backup_timer, app.friends_sync.timer):
            timer.stop()
        self.addCleanup(app.store.close)
        self.addCleanup(app.window.hide)
        self.assertTrue(app.landscape)

    def test_needs_a_server_and_a_google_account(self):
        self.service.configured = False
        self.assertEqual(self.sync.view().mode, "unavailable")
        self.service.configured = True
        self.account = ""
        self.assertEqual(self.sync.view().mode, "signed_out")
        self.account = "amy@example.com"
        self.assertEqual(self.sync.view().mode, "off")
        # Nothing is sent before friends are turned on
        self.sync.sync()
        self.sync.tick("Krita")
        self.assertEqual(self.service.calls, [])

    def test_turning_on_sends_the_name_and_figures(self):
        self.app.store.record_active_second(application="Krita")
        self._turn_on()
        self.assertEqual(self.app.settings["friends_accounts"], ["amy@example.com"])
        (kind, name, stats), = self.service.calls
        self.assertEqual((kind, name), ("sync", "amy"))
        self.assertEqual(set(stats), {"two_weeks", "total", "today", "week", "level", "streak", "status", "active"})
        self.assertAlmostEqual(stats["total"], 1 / 3600)
        self.assertEqual(self.sync.view().mode, "on")
        self.assertEqual(self.app.friends.view.code, "ABCD2345")

    def test_friends_are_ranked_by_hours_past_two_weeks_and_stale_ones_are_offline(self):
        self.service.answer = server_state(friends=[
            {"code": "BBBB2222", "name": "Bo", "stats": {"two_weeks": 3, "active": "Krita", "status": "online"}, "updated_at": 1000 - 60},
            {"code": "CCCC3333", "name": "Cy", "stats": {"two_weeks": 9, "active": "Photoshop"}, "updated_at": 1000 - 3600},
            {"code": "DDDD4444", "name": "Dee", "stats": {"two_weeks": 5, "status": "away"}, "updated_at": 1000},
            {"code": "EEEE5555", "name": "Ev", "stats": {"two_weeks": 1}, "updated_at": 1000},
        ])
        self._turn_on()
        people = self.app.friends.view.people
        # The user is not among them
        self.assertEqual([person[0] for person in people], ["Cy", "Dee", "Bo", "Ev"])
        self.assertEqual([person[2] for person in people], ["offline", "away", "drawing", "online"])
        self.assertEqual([person[3] for person in people], [None, None, "Krita", None])

    def test_status_menu_sets_what_friends_see(self):
        from qt import friends_sync

        self._turn_on()
        self.assertTrue(self.app.header.status_arrow_shown)
        self.sync.active_program = "Krita"
        for status, sent, active in (("away", "away", None), ("invisible", "offline", None), ("online", "online", "Krita")):
            self.sync.set_status(status)
            self._settle()
            self.assertEqual((self.service.calls[-1][2]["status"], self.service.calls[-1][2]["active"]), (sent, active))
        # Offline tells friends once, then sends nothing more
        self.sync.set_status("offline")
        self._settle()
        self.assertEqual(self.service.calls[-1][2]["status"], "offline")
        count = len(self.service.calls)
        self.sync.last_sync -= friends_sync.MIN_SYNC_GAP_SECONDS
        self.sync.sync()
        self.sync.tick("Krita")
        self._settle()
        self.assertEqual(len(self.service.calls), count)
        self.assertEqual(self.sync.view().mode, "offline")
        self.sync.set_status("online")
        self._settle()
        self.assertEqual(len(self.service.calls), count + 1)
        # Choosing in the menu
        from qt.status_menu import StatusMenu

        menu = StatusMenu(self.app.window, self.app.fonts, "online", self.sync.set_status)
        self.assertGreater(menu.height(), 60)
        menu.on_chosen("away")
        self.assertEqual(self.app.settings["friends_status"], "away")

    def test_starting_and_stopping_drawing_is_sent_once_it_has_lasted(self):
        from qt import friends_sync

        self._turn_on()
        self.sync.last_sync -= friends_sync.MIN_SYNC_GAP_SECONDS
        self.sync.tick("Krita")
        self._settle()
        self.assertEqual(self.service.calls[-1][2]["active"], "Krita")
        # A moment in another window is not a stop
        self.sync.last_sync -= friends_sync.MIN_SYNC_GAP_SECONDS
        self.sync.tick(None)
        self.assertEqual(len(self.service.calls), 2)
        self.sync.last_active_time -= friends_sync.ACTIVE_LINGER_SECONDS + 1
        self.sync.tick(None)
        self._settle()
        self.assertIsNone(self.service.calls[-1][2]["active"])
        self.assertEqual(len(self.service.calls), 3)

    def test_looking_at_friends_brings_them_up_to_date_once_a_minute(self):
        from qt import friends_sync

        self._turn_on()
        self.app.friends.actions.looked_at()
        self._settle()
        self.assertEqual(len(self.service.calls), 1)
        self.sync.last_sync -= friends_sync.MIN_SYNC_GAP_SECONDS
        self.app.friends.actions.looked_at()
        self._settle()
        self.assertEqual(len(self.service.calls), 2)

    def test_a_refused_request_is_explained(self):
        self._turn_on()
        self.service.error = FriendsError("No one has that friend code")
        self.app.friends.actions.add("ZZZZ-ZZZZ")
        self._settle()
        self.assertEqual(self.service.calls[-1], ("add", "ZZZZ-ZZZZ"))
        self.assertEqual(self.app.friends.view.message, ("No one has that friend code", "red"))
        # A failed check-in keeps the friends last seen
        self.assertEqual(self.app.friends.view.mode, "on")

    def test_an_answer_for_another_account_is_dropped(self):
        self._turn_on()
        self.service.answer = server_state(friends=[{"code": "BBBB2222", "name": "Bo", "stats": {}, "updated_at": 1000}])
        self.sync.sync()
        self.account = "someone@example.com"
        self._settle()
        self.app.settings["friends_accounts"].append(self.account)
        self.assertEqual(self.sync.view().mode, "loading")

    def test_turning_off_deletes_and_forgets(self):
        self._turn_on()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.app.friends.actions.turn_off()
        self._settle()
        self.assertEqual(self.service.calls[-1], ("leave",))
        self.assertEqual(self.app.settings["friends_accounts"], [])
        self.assertEqual(self.sync.view().mode, "off")

    def test_removing_a_friend_asks_first(self):
        self._turn_on()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.sync.remove("BBBB2222", "Bo")
        self.assertEqual(len(self.service.calls), 1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.sync.remove("BBBB2222", "Bo")
        self._settle()
        self.assertEqual(self.service.calls[-1], ("remove", "BBBB2222"))

    def test_every_view_fits_and_draws(self):
        long_name = "A very long display name indeed"
        self.service.answer = server_state(
            friends=[{"code": f"BBBB222{index}", "name": long_name, "stats": {"two_weeks": 335.9, "total": 99999.9, "today": 23.9, "level": 99, "streak": 52, "active": "Clip Studio Paint"}, "updated_at": 1000} for index in range(3)],
            incoming=[{"code": "DDDD4444", "name": long_name}],
            outgoing=[{"code": "EEEE5555", "name": long_name}],
        )
        module = self.app.friends
        for mode in ("unavailable", "signed_out", "off", "loading"):
            from qt.friends_module import FriendsView

            module.show_view(FriendsView(mode, message=("Could not reach the friends server", "orange")))
            self.assertFalse(module.grab().isNull())
        self._turn_on()
        heights = module.height()
        self.assertFalse(module.grab().isNull())
        for _kind, *item in module.items:
            if _kind == "anchored":
                x, _y, anchor, text, _tone, font = item
                from qt.theme import text_width

                left = x - text_width(font, text) if anchor == "e" else x
                self.assertGreaterEqual(left, 0, text)
                self.assertLessEqual(left + text_width(font, text), module.width(), text)
        # Three friends, a request each way, and the code row
        self.assertGreater(heights, 150)
        for landscape in (True, False):
            self.app.landscape = landscape
            self.app._arrange_blocks()
            self.application.processEvents()

    def test_a_long_list_scrolls_and_stays_level_in_landscape(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from qt.friends_module import PORTRAIT_LIST_ROWS, FriendsView

        module = self.app.friends
        people = [(f"Friend {index}", {"two_weeks": 10}, "online", None, f"AAAA22{index:02d}") for index in range(12)]
        module.show_view(FriendsView("on", "ABCD2345", people))
        self.assertGreater(module.max_scroll, 0)
        self.assertEqual(len(module.person_areas), PORTRAIT_LIST_ROWS)
        tall = module.height()
        wheel = QWheelEvent(QPointF(50, 80), QPointF(50, 80), QPoint(), QPoint(0, -120 * 50), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        module.wheelEvent(wheel)
        self.assertEqual(module.scroll, module.max_scroll)
        # Scrolled to the end, the last friend's row can be clicked
        self.assertEqual(module.person_areas[-1][1], "AAAA2211")
        self.assertEqual(module.height(), tall)
        self.app.landscape = True
        self.app._arrange_blocks()
        # As tall as the columns beside it, inside their borders
        self.assertEqual(module.height(), self.app._landscape_height(self.app._anchor_panel()) + 2)

    def test_the_code_is_copied_and_typed_codes_are_added(self):
        self._turn_on()
        module = self.app.friends
        self.assertFalse(module.code_area.isEmpty())
        module.actions.copy_code("ABCD2345")
        self.assertEqual(QApplication.clipboard().text(), "ABCD2345")
        module._toggle_entry()
        self.assertTrue(module.entry.isVisible())
        module.entry.setText("bbbb-2222")
        module.entry._finish(module.entry.text())
        self._settle()
        self.assertEqual(self.service.calls[-1], ("add", "bbbb-2222"))


class FriendsServiceTests(unittest.TestCase):
    def setUp(self):
        self.answers = []
        self.requests = []
        test = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.requests.append((self.path, self.headers["Authorization"], body))
                status, answer = test.answers.pop(0)
                payload = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.service = FriendsService(lambda: "token", f"http://127.0.0.1:{self.server.server_port}/")

    def test_calls_carry_the_identity_and_return_the_answer(self):
        self.answers.append((200, {"me": {"code": "ABCD2345"}}))
        self.assertEqual(self.service.sync("Amy", {"two_weeks": 1}), {"me": {"code": "ABCD2345"}})
        self.assertEqual(self.requests, [("/v1/sync", "Bearer token", {"name": "Amy", "stats": {"two_weeks": 1}})])

    def test_a_refusal_carries_the_server_explanation(self):
        self.answers.append((404, {"error": "No one has that friend code"}))
        with self.assertRaisesRegex(FriendsError, "No one has that friend code"):
            self.service.add("ZZZZZZZZ")
        self.answers.append((500, ["not an object"]))
        with self.assertRaisesRegex(FriendsError, "answered 500"):
            self.service.leave()

    def test_an_unreachable_server_is_said_plainly(self):
        service = FriendsService(lambda: "token", "http://127.0.0.1:9/")
        with self.assertRaisesRegex(FriendsError, "Could not reach"):
            service.sync("Amy", {})

    def test_codes_show_in_two_groups(self):
        self.assertEqual(format_code("ABCD2345"), "ABCD-2345")
        self.assertEqual(format_code(""), "")
        self.assertFalse(FriendsService(lambda: "", "").configured)


if __name__ == "__main__":
    unittest.main()
