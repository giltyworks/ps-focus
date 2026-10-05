import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.write_checksums import checksum_lines


class ChecksumTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_lines_use_sha256sum_format_with_file_names_only(self):
        (self.root / "dist").mkdir()
        app = self.root / "dist" / "PS Focus.exe"
        uninstaller = self.root / "Uninstall PS Focus.exe"
        app.write_bytes(b"app build")
        uninstaller.write_bytes(b"uninstaller build")

        self.assertEqual(checksum_lines([app, uninstaller]), [
            f"{hashlib.sha256(b'app build').hexdigest()} *PS Focus.exe",
            f"{hashlib.sha256(b'uninstaller build').hexdigest()} *Uninstall PS Focus.exe",
        ])

    def test_files_with_the_same_name_are_rejected(self):
        for folder in ("a", "b"):
            (self.root / folder).mkdir()
            (self.root / folder / "PS Focus.exe").write_bytes(folder.encode())

        with self.assertRaises(ValueError):
            checksum_lines([self.root / "a" / "PS Focus.exe", self.root / "b" / "PS Focus.exe"])


if __name__ == "__main__":
    unittest.main()
