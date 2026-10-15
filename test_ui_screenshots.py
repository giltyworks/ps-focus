"""The screenshot tool draws every block and both window layouts, and compares after with before, without touching real data."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtGui import QImage
except ImportError:
    QImage = None

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

# Imported after the path is set, as the script itself does
import ui_screenshots  # noqa: E402


def real_data_state() -> dict[str, float]:
    """Each file in the real data folder and when it last changed, to see that the tool left them all alone"""
    import app_config

    folder = app_config.APP_DATA
    if not folder.exists():
        return {}
    return {str(path): path.stat().st_mtime for path in folder.rglob("*") if path.is_file()}


@unittest.skipIf(QImage is None, "PySide6 is not installed")
class UiScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temporary.name)
        cls.state_before = real_data_state()
        for mode in ("before", "after"):
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "ui_screenshots.py"), mode, "--out", str(cls.out)],
                capture_output=True, text=True, timeout=180, cwd=ROOT,
            )
            if result.returncode != 0:
                raise AssertionError(f"{mode} failed:\n{result.stdout}\n{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_every_block_and_both_layouts_are_saved_in_both_folders(self):
        for folder in ("before", "after"):
            for name in ui_screenshots.PICTURE_NAMES:
                image = QImage(str(self.out / folder / f"{name}.png"))
                self.assertFalse(image.isNull(), f"{folder}/{name}.png is missing or not a picture")
                self.assertGreater(image.width(), 100, f"{folder}/{name}.png")
                self.assertGreater(image.height(), 50, f"{folder}/{name}.png")

    def test_after_makes_a_side_by_side_picture_of_each(self):
        for name in ui_screenshots.PICTURE_NAMES:
            single = QImage(str(self.out / "after" / f"{name}.png"))
            both = QImage(str(self.out / "compare" / f"{name}.png"))
            self.assertFalse(both.isNull(), f"compare/{name}.png is missing")
            self.assertGreater(both.width(), 2 * single.width())

    def test_real_data_is_left_alone(self):
        self.assertEqual(real_data_state(), self.state_before)


if __name__ == "__main__":
    unittest.main()
