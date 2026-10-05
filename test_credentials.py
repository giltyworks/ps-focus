import unittest

from tools.check_credentials import inspect


class CredentialCheckTests(unittest.TestCase):
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
