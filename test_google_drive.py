import base64
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

from google_drive import (
    GoogleAccountAccessRequired,
    GoogleDriveSync,
    REVOKE_URL,
    USERINFO_API,
    USERINFO_SCOPE,
)


class GoogleAccountTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.credentials = self.root / "credentials.json"
        self.credentials.write_text(
            json.dumps({"installed": {"client_id": "test-client", "client_secret": "test-secret"}}),
            encoding="utf-8",
        )
        self.sync = GoogleDriveSync(self.root / "app-data", self.credentials)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _save_token(self, scope):
        self.sync._save_token({
            "access_token": "test-token",
            "expires_at": time.time() + 3600,
            "scope": scope,
        })

    def test_web_credentials_are_rejected(self):
        self.credentials.write_text(json.dumps({"web": {"client_id": "test-client", "client_secret": "test-secret"}}))
        with self.assertRaisesRegex(RuntimeError, "Desktop app"):
            self.sync._client()

    def test_app_data_credentials_take_precedence_over_other_locations(self):
        app_credentials = self.sync.token_file.parent / "credentials.json"
        app_credentials.parent.mkdir(parents=True)
        app_credentials.write_text(json.dumps({"installed": {"client_id": "replacement-client", "client_secret": "test-replacement-secret"}}))
        self.assertEqual(self.sync._client(), ("replacement-client", "test-replacement-secret"))

    def test_packaged_app_uses_bundled_config_without_external_credentials(self):
        self.credentials.unlink()
        bundled = self.root / "bundle" / "assets" / "oauth" / "desktop-client.json"
        bundled.parent.mkdir(parents=True)
        bundled.write_text(json.dumps({"installed": {"client_id": "bundled-client", "client_secret": "test-secret"}}))
        with patch("google_drive.sys.frozen", True, create=True), patch("google_drive.sys._MEIPASS", str(self.root / "bundle"), create=True), patch("google_drive.sys.executable", str(self.root / "PS Focus.exe")):
            self.assertEqual(self.sync._client(), ("bundled-client", "test-secret"))

    def test_sign_in_sends_pkce_challenge_and_matching_verifier(self):
        browser_urls = []
        server = MagicMock()
        server.server_port = 12345

        def make_server(address, handler_class):
            def callback():
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(browser_urls[0]).query)
                handler = object.__new__(handler_class)
                handler.path = "/?" + urllib.parse.urlencode({"state": query["state"][0], "code": "test-code"})
                handler.wfile = io.BytesIO()
                handler.send_response = MagicMock()
                handler.send_header = MagicMock()
                handler.end_headers = MagicMock()
                handler.do_GET()
            server.handle_request.side_effect = callback
            return server

        with patch("google_drive.http.server.HTTPServer", side_effect=make_server), patch(
            "google_drive.webbrowser.open", side_effect=browser_urls.append
        ), patch.object(self.sync, "_request_token", return_value={"access_token": "test-token"}) as exchange:
            self.sync.sign_in()

        query = urllib.parse.parse_qs(urllib.parse.urlsplit(browser_urls[0]).query)
        form = exchange.call_args.args[0]
        verifier = form["code_verifier"]
        self.assertTrue(43 <= len(verifier) <= 128)
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], [expected])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)
        self.assertNotIn("client_secret", query)
        self.assertEqual(form["code"], "test-code")
        server.server_close.assert_called_once()

    def test_sign_in_ignores_requests_without_the_matching_state(self):
        browser_urls = []
        server = MagicMock()
        server.server_port = 12345
        rejected = []

        def make_server(address, handler_class):
            self.assertEqual(address[0], "127.0.0.1")

            def request():
                # The first request carries a forged state and the second is Google's real redirect
                expected_state = urllib.parse.parse_qs(urllib.parse.urlsplit(browser_urls[0]).query)["state"][0]
                handler = object.__new__(handler_class)
                state = expected_state if rejected else "forged-state"
                handler.path = "/?" + urllib.parse.urlencode({"state": state, "code": "test-code"})
                handler.wfile = io.BytesIO()
                handler.send_response = MagicMock()
                handler.send_header = MagicMock()
                handler.end_headers = MagicMock()
                handler.send_error = rejected.append
                handler.do_GET()

            server.handle_request.side_effect = request
            return server

        with patch("google_drive.http.server.HTTPServer", side_effect=make_server), patch(
            "google_drive.webbrowser.open", side_effect=browser_urls.append
        ), patch.object(self.sync, "_request_token", return_value={"access_token": "test-token"}) as exchange:
            self.sync.sign_in()

        self.assertEqual(rejected, [400])
        self.assertEqual(server.handle_request.call_count, 2)
        self.assertEqual(exchange.call_args.args[0]["code"], "test-code")
        self.assertTrue(exchange.call_args.args[0]["redirect_uri"].startswith("http://127.0.0.1:"))

    @unittest.skipUnless(os.name == "nt", "Token protection uses Windows DPAPI")
    def test_saved_token_is_encrypted_and_plain_tokens_are_upgraded(self):
        self._save_token(USERINFO_SCOPE)
        self.assertNotIn("test-token", self.sync.token_file.read_text(encoding="utf-8"))
        self.assertEqual(self.sync._read_token()["access_token"], "test-token")

        self.sync.token_file.write_text(json.dumps({"access_token": "test-token", "refresh_token": "test-refresh"}), encoding="utf-8")
        self.assertEqual(self.sync._read_token()["refresh_token"], "test-refresh")
        self.assertNotIn("test-refresh", self.sync.token_file.read_text(encoding="utf-8"))
        self.assertEqual(self.sync._read_token()["refresh_token"], "test-refresh")

    def test_unreadable_token_asks_for_reconnection(self):
        self.sync.token_file.parent.mkdir(parents=True)
        self.sync.token_file.write_text(json.dumps({"protected": "bm90IGEgdG9rZW4="}), encoding="utf-8")
        with self.assertRaises(GoogleAccountAccessRequired):
            self.sync._read_token()

    def test_account_email_uses_google_userinfo(self):
        self._save_token(USERINFO_SCOPE)
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"email": "artist@example.com"}).encode("utf-8")

        with patch("google_drive.urllib.request.urlopen", return_value=response) as urlopen_mock:
            self.assertEqual(self.sync.account_email(), "artist@example.com")

        self.assertEqual(urlopen_mock.call_args.args[0].full_url, USERINFO_API)

    def test_account_email_requires_email_scope(self):
        self._save_token("https://www.googleapis.com/auth/drive.appdata")

        with self.assertRaises(GoogleAccountAccessRequired):
            self.sync.account_email()

    def test_sign_out_revokes_google_token_and_removes_local_token(self):
        self._save_token(USERINFO_SCOPE)
        response = MagicMock()
        response.__enter__.return_value = response

        with patch("google_drive.urllib.request.urlopen", return_value=response) as urlopen_mock:
            self.assertTrue(self.sync.sign_out())

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, REVOKE_URL)
        self.assertIn("test-token", request.data.decode("utf-8"))
        self.assertFalse(self.sync.token_file.exists())

    def test_sign_out_removes_local_token_when_google_is_unreachable(self):
        self._save_token(USERINFO_SCOPE)

        with patch("google_drive.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(self.sync.sign_out())

        self.assertFalse(self.sync.token_file.exists())

    def test_upload_activity_backup_updates_private_drive_file(self):
        content = b"sqlite backup bytes"
        with patch.object(self.sync, "_api", side_effect=[{"files": [{"id": "backup-id"}]}, {}]) as api_mock:
            self.sync.upload_activity_backup(content)

        upload = api_mock.call_args_list[1]
        self.assertIn("/files/backup-id?uploadType=media", upload.args[0])
        self.assertEqual(upload.kwargs["method"], "PATCH")
        self.assertEqual(upload.kwargs["body"], content)
        self.assertEqual(upload.kwargs["content_type"], "application/x-sqlite3")

    def test_first_upload_creates_the_file_in_the_private_drive_area(self):
        cases = (
            (lambda: self.sync.upload_settings({"period": "Week"}), "settings.json", b'"period": "Week"', b"Content-Type: application/json\r\n\r\n{"),
            (lambda: self.sync.upload_activity_backup(b"sqlite bytes"), "activity.sqlite3", b"sqlite bytes", b"Content-Type: application/x-sqlite3\r\n\r\nsqlite bytes"),
        )
        for upload, name, content, part_header in cases:
            with self.subTest(name=name), patch.object(self.sync, "_api", side_effect=[{"files": []}, {}]) as api_mock:
                upload()

                lookup, create = api_mock.call_args_list
                self.assertIn(f"name%3D%27{name}%27", lookup.args[0])
                self.assertIn("/upload/drive/v3/files?uploadType=multipart", create.args[0])
                self.assertEqual(create.kwargs["method"], "POST")
                boundary = create.kwargs["content_type"].split("boundary=")[1]
                body = create.kwargs["body"]
                self.assertTrue(body.startswith(f"--{boundary}\r\n".encode()))
                self.assertTrue(body.endswith(f"\r\n--{boundary}--".encode()))
                self.assertIn(json.dumps({"name": name, "parents": ["appDataFolder"]}).encode(), body)
                self.assertIn(part_header, body)
                self.assertIn(content, body)

    def test_settings_upload_replaces_the_existing_drive_file(self):
        with patch.object(self.sync, "_api", side_effect=[{"files": [{"id": "settings-id"}]}, {}]) as api_mock:
            self.sync.upload_settings({"period": "Week"})

        replace = api_mock.call_args_list[1]
        self.assertIn("/upload/drive/v3/files/settings-id?uploadType=media", replace.args[0])
        self.assertEqual(replace.kwargs["method"], "PATCH")
        self.assertEqual(json.loads(replace.kwargs["body"]), {"period": "Week"})
        self.assertEqual(replace.kwargs["content_type"], "application/json")

    def test_download_activity_backup_returns_private_drive_file(self):
        content = b"sqlite backup bytes"
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = content

        with patch.object(self.sync, "_api", return_value={"files": [{"id": "backup-id"}]}), patch.object(
            self.sync, "_access_token", return_value="test-token"
        ), patch("google_drive.urllib.request.urlopen", return_value=response) as urlopen_mock:
            self.assertEqual(self.sync.download_activity_backup(), content)

        request = urlopen_mock.call_args.args[0]
        self.assertIn("/files/backup-id?alt=media", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")


if __name__ == "__main__":
    unittest.main()
