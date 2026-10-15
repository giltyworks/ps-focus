import re
import unittest
from pathlib import Path

from tools.sync_site import DEMO_SCRIPT, demo_level_hours, demo_with_levels, privacy_page, terms_page

ROOT = Path(__file__).resolve().parent


class SitePageTests(unittest.TestCase):
    def test_terms_become_markdown_with_numbered_headings_and_lists(self):
        page = terms_page((ROOT / "TERMS.md").read_text(encoding="utf-8"))

        self.assertTrue(page.startswith("---\ntitle: Terms of Use\npermalink: /terms/\n---\n\n# PS Focus Terms of Use\n"))
        self.assertIn("\n## 1\\. Licence\n", page)
        self.assertIn("\n## 3\\. Third-party components\n", page)
        self.assertIn("\n## 10\\. Changes to these terms\n", page)
        self.assertNotIn("LIMITATION OF LIABILITY", page)

        listed = terms_page("TERMS\n\n1. SAMPLE\nYou may:\n- copy it;\n- share it.")
        self.assertIn("You may:\n\n- copy it;\n- share it.", listed)

    def test_privacy_policy_is_published_unchanged_under_its_address(self):
        source = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        page = privacy_page(source)

        self.assertTrue(page.startswith("---\ntitle: Privacy Policy\npermalink: /privacy/\n---\n\n# PS Focus Privacy Policy"))
        self.assertIn(source.strip(), page)

    def test_demo_levels_follow_the_app_curve(self):
        import json

        from app_config import LEVEL_HOURS, user_level

        source = (ROOT / "docs" / DEMO_SCRIPT).read_text(encoding="utf-8")
        # Fails when the level curve changes without `py tools/sync_site.py` being run
        self.assertEqual(demo_with_levels(source), source)
        demo_hours = json.loads(re.search(r"const LEVEL_HOURS = (\[.*\]);", source).group(1))
        self.assertEqual(len(demo_hours), len(LEVEL_HOURS))
        for hours in (0, 1, 50, 700, 1400, 3000, 4999, 5000, 9000):
            self.assertEqual(sum(needed <= hours for needed in demo_hours), user_level(hours * 3600), hours)

        replaced = demo_with_levels("  let a = 1;\n  const LEVEL_HOURS = [1, 2];\n  let b = 2;\n")
        self.assertEqual(replaced, f"  let a = 1;\n  const LEVEL_HOURS = {demo_level_hours()};\n  let b = 2;\n")

    def test_download_button_finds_the_latest_installer_by_itself(self):
        page = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
        link = re.search(r'id="download" href="([^"]+)"', page)
        self.assertIsNotNone(link, 'The Download button in docs/index.md no longer has id="download" before its href')
        # The button must not name a version, so a release never leaves the website behind
        self.assertEqual(link.group(1), "https://github.com/giltyworks/ps-focus/releases/latest")
        self.assertIn("https://api.github.com/repos/giltyworks/ps-focus/releases/latest", page)
        # The script picks the installer by file name, so the name the build produces must still fit
        pattern = re.search(r"test\(asset\.name\)", page) and re.search(r"return (/\^PS-Focus-Setup-.*?\$/)\.test", page)
        self.assertIsNotNone(pattern, "The Download button's file name check is missing from docs/index.md")
        installer = (ROOT / "installer" / "PS Focus.iss").read_text(encoding="utf-8")
        self.assertIn("OutputBaseFilename=PS-Focus-Setup-{#AppVersion}", installer)
        from app_config import APP_VERSION

        self.assertIsNotNone(re.fullmatch(pattern.group(1)[2:-2], f"PS-Focus-Setup-{APP_VERSION}.exe"))


if __name__ == "__main__":
    unittest.main()
