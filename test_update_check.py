import json
import unittest
from unittest.mock import MagicMock, patch

from tools.version_resource import version_numbers
from update_check import available_update, is_safe_download_url, parse_version


class UpdateCheckTests(unittest.TestCase):
    def _respond(self, payload):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode("utf-8")
        return patch("update_check.urllib.request.urlopen", return_value=response)

    def test_versions_compare_numerically(self):
        self.assertGreater(parse_version("1.10.0"), parse_version("1.9.9"))
        self.assertEqual(parse_version("1.2"), parse_version("1.2.0.0"))
        for invalid in ("", "v1.0", "1..0", "1.0.0.0.0", None, 1):
            self.assertIsNone(parse_version(invalid))

    RELEASES_PAGE = "https://github.com/giltyworks/ps-focus/releases/latest"

    def test_newer_version_on_the_releases_page_is_offered(self):
        with self._respond({"ok": True, "latest_version": "1.0.1", "download_url": self.RELEASES_PAGE}):
            self.assertEqual(available_update("1.0.0", "https://endpoint.example"), ("1.0.1", self.RELEASES_PAGE))

    def test_same_or_older_version_is_not_offered(self):
        for latest in ("1.0.0", "0.9.9"):
            with self.subTest(latest=latest), self._respond({"ok": True, "latest_version": latest, "download_url": self.RELEASES_PAGE}):
                self.assertIsNone(available_update("1.0.0", "https://endpoint.example"))

    def test_only_the_projects_own_pages_are_accepted_as_download_links(self):
        rejected = (
            "",
            None,
            "http://github.com/giltyworks/ps-focus/releases/latest",
            "file:///C:/Windows/System32/calc.exe",
            "javascript:alert(1)",
            "https://example.com/ps-focus",
            "https://giltyworks.itch.io/ps-focus",
            "https://github.com/someone-else/ps-focus/releases/latest",
            "https://github.com/giltyworks/ps-focus-fake/releases",
            "https://github.com/giltyworks/ps-focus/../../someone-else/tool/releases",
            "https://github.com/giltyworks/ps-focus/%2e%2e/%2e%2e/someone-else/tool",
            "https://github.com.evil.example/giltyworks/ps-focus/",
            "https://evil.example/?https://github.com/giltyworks/ps-focus/",
            "https://user:pass@github.com/giltyworks/ps-focus/",
            "https://github.com:8443/giltyworks/ps-focus/",
            "https://github.com:port/giltyworks/ps-focus/",
        )
        for url in rejected:
            with self.subTest(url=url), self._respond({"ok": True, "latest_version": "9.0.0", "download_url": url}):
                self.assertFalse(is_safe_download_url(url))
                self.assertIsNone(available_update("1.0.0", "https://endpoint.example"))
        for url in (self.RELEASES_PAGE, "https://GitHub.com/giltyworks/ps-focus/releases/tag/v1.0.1", "https://giltyworks.github.io/ps-focus/"):
            with self.subTest(url=url):
                self.assertTrue(is_safe_download_url(url))

    def test_network_failures_are_reported_and_no_endpoint_means_no_check(self):
        with patch("update_check.urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaises(RuntimeError):
                available_update("1.0.0", "https://endpoint.example")
        with patch("update_check.urllib.request.urlopen") as urlopen:
            self.assertIsNone(available_update("1.0.0", ""))
        urlopen.assert_not_called()

    def test_executable_version_numbers_are_four_parts(self):
        self.assertEqual(version_numbers("1.0.0"), (1, 0, 0, 0))
        with self.assertRaises(ValueError):
            version_numbers("1.0.70000")


if __name__ == "__main__":
    unittest.main()
