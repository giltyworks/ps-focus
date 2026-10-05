import unittest
from pathlib import Path

from tools.sync_site import privacy_page, terms_page

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


if __name__ == "__main__":
    unittest.main()
