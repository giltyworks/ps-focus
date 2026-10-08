import unittest

from tools.check_credentials import inspect


class CredentialCheckTests(unittest.TestCase):
    def test_qt_marker_exception_does_not_allow_other_secrets(self):
        marker = b'-----BEGIN ' + b'PRIVATE KEY-----'
        self.assertTrue(inspect('qt.dll', marker))
        self.assertFalse(inspect('qt.dll', marker, allow_verified_qt_pem_markers=True))
        self.assertTrue(inspect('qt.dll', b'GOCSPX-' + b'a' * 24, allow_verified_qt_pem_markers=True))

    def test_qt_binary_exception_requires_known_name_and_exact_contents(self):
        from tools.check_credentials import verified_qt_binary
        self.assertFalse(verified_qt_binary('other.dll', b'-----BEGIN ' + b'PRIVATE KEY-----'))
        try:
            import PySide6
        except ImportError:
            return
        from pathlib import Path
        source = Path(PySide6.__file__).parent / 'Qt6Network.dll'
        if source.exists():
            data = source.read_bytes()
            self.assertTrue(verified_qt_binary('PySide6/Qt6Network.dll', data))
            self.assertFalse(verified_qt_binary('PySide6/Qt6Network.dll', data + b'changed'))

    def test_credential_files_are_rejected_even_without_signature(self):
        for name in ("credentials.json", "release/credentials.json", ".env.production", "keys/signing.pfx", "google-token.json"):
            with self.subTest(name=name):
                self.assertTrue(inspect(name, b"{}"))

    def test_secret_is_reported_without_printing_its_value(self):
        value = b"GOCSPX-" + b"a" * 24
        findings = inspect("settings.py", value)
        self.assertTrue(findings)
        self.assertNotIn(value.decode(), " ".join(findings))

    def test_dummy_test_tokens_are_allowed(self):
        self.assertFalse(inspect("test_google_drive.py", b'{"client_secret": "test-secret", "access_token": "test-token"}'))

    def test_only_minimal_desktop_config_is_allowed_in_release_exception(self):
        import json
        config = {"installed": {"client_id": "test.apps.googleusercontent.com", "client_secret": "GOCSPX-" + "a" * 24}}
        self.assertFalse(inspect("assets/oauth/desktop-client.json", json.dumps(config).encode(), allow_desktop_client=True))
        self.assertTrue(inspect("source.json", json.dumps(config).encode()))
        config["installed"]["refresh_token"] = "user-token"
        self.assertTrue(inspect("assets/oauth/desktop-client.json", json.dumps(config).encode(), allow_desktop_client=True))


if __name__ == "__main__":
    unittest.main()
