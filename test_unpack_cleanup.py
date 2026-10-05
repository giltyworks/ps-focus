import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import unpack_cleanup


class UnpackCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _unpack_folder(self, name, own=True, age_seconds=3600):
        folder = self.temp / name
        (folder / "PIL").mkdir(parents=True)
        (folder / "python314.dll").write_bytes(b"library")
        (folder / "PIL" / "_imaging.pyd").write_bytes(b"extension")
        if own:
            (folder / unpack_cleanup.OWN_FILE).parent.mkdir(parents=True)
            (folder / unpack_cleanup.OWN_FILE).write_bytes(b"icon")
        moment = time.time() - age_seconds
        os.utime(folder, (moment, moment))
        return folder

    def test_stale_folders_of_the_app_are_removed_and_everything_else_is_left(self):
        stale = [self._unpack_folder("_MEI000012342"), self._unpack_folder("_MEI000056782")]
        other_program = self._unpack_folder("_MEI000099992", own=False)
        unrelated = self.temp / "Photoshop Temp"
        unrelated.mkdir()
        (unrelated / unpack_cleanup.OWN_FILE).parent.mkdir(parents=True)
        (unrelated / unpack_cleanup.OWN_FILE).write_bytes(b"icon")

        self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp), 2)

        for folder in stale:
            self.assertFalse(folder.exists())
        self.assertTrue((other_program / "python314.dll").exists())
        self.assertTrue((unrelated / unpack_cleanup.OWN_FILE).exists())

    def test_folder_of_a_copy_that_is_still_starting_is_left_alone(self):
        starting = self._unpack_folder("_MEI000012342", age_seconds=5)

        self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp), 0)
        self.assertTrue((starting / "python314.dll").exists())
        # The uninstaller has already closed every other copy, so it does not wait
        self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp, minimum_age_seconds=0), 1)
        self.assertFalse(starting.exists())

    def test_folder_this_run_was_unpacked_into_is_left_alone(self):
        current = self._unpack_folder("_MEI000012342")
        with patch("unpack_cleanup.sys._MEIPASS", str(current), create=True):
            self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp), 0)
        self.assertTrue((current / "python314.dll").exists())

    @unittest.skipUnless(os.name == "nt", "relies on Windows refusing to delete a file that is open")
    def test_folder_a_running_copy_is_using_is_left_whole(self):
        in_use = self._unpack_folder("_MEI000012342")
        with (in_use / "python314.dll").open("rb"):
            self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp), 0)
            self.assertEqual(sum(1 for path in in_use.rglob("*") if path.is_file()), 3)

    def test_removal_that_was_interrupted_is_finished(self):
        interrupted = self._unpack_folder("_MEI000012342")
        (interrupted / "python314.dll").unlink()
        (interrupted / "PIL" / "_imaging.pyd").unlink()
        moment = time.time() - 3600
        os.utime(interrupted, (moment, moment))

        self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp), 1)
        self.assertFalse(interrupted.exists())

    def test_marker_outlives_everything_else_when_a_file_cannot_be_removed(self):
        folder = self._unpack_folder("_MEI000012342")
        real_unlink = Path.unlink

        def unlink(path, *arguments, **options):
            if path.name == "locked.pyd":
                raise PermissionError("in use")
            real_unlink(path, *arguments, **options)

        (folder / "locked.pyd").write_bytes(b"extension")
        moment = time.time() - 3600
        os.utime(folder, (moment, moment))
        with patch.object(Path, "unlink", unlink):
            self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(self.temp), 0)
        self.assertTrue((folder / unpack_cleanup.OWN_FILE).exists())

    def test_running_from_source_removes_nothing_from_the_real_temporary_folder(self):
        with patch("unpack_cleanup.tempfile.gettempdir") as temporary_folder:
            self.assertEqual(unpack_cleanup.remove_stale_unpack_folders(), 0)
        temporary_folder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
