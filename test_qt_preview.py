"""The Qt preview copies history without sharing installed-app backup destinations."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from qt.preview import PREVIEW_FOLDER_NAME, use_preview_data


class QtPreviewTests(unittest.TestCase):
    def test_source_connection_closes_when_preview_database_cannot_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "PS Focus"
            real.mkdir()
            (real / "activity.sqlite3").touch()
            source = Mock()
            with patch.dict(os.environ, {"APPDATA": str(root)}), patch("qt.preview.sqlite3.connect", side_effect=[source, sqlite3.OperationalError("readonly database")]):
                with self.assertRaises(sqlite3.OperationalError):
                    use_preview_data()
            source.close.assert_called_once()

    def test_preview_copies_history_and_settings_but_keeps_backups_and_identity_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "PS Focus"
            real.mkdir()
            database = real / "activity.sqlite3"
            source = sqlite3.connect(database)
            source.execute("CREATE TABLE sample (seconds INTEGER)")
            source.execute("INSERT INTO sample VALUES (123)")
            source.commit()
            source.close()
            settings = real / "settings.json"
            settings.write_text('{"tracking_paused": true}', encoding="utf-8")
            (real / "google-token.json").write_text("test-token", encoding="utf-8")
            (real / "installation-id").write_text("real-installation", encoding="utf-8")
            before_database = database.read_bytes()
            before_settings = settings.read_bytes()
            with patch.dict(os.environ, {"APPDATA": str(root)}):
                preview = use_preview_data()
                environment = os.environ.copy()
            self.assertEqual(preview, root / PREVIEW_FOLDER_NAME)
            self.assertEqual((preview / "settings.json").read_bytes(), before_settings)
            self.assertFalse((preview / "google-token.json").exists())
            self.assertFalse((preview / "installation-id").exists())
            connection = sqlite3.connect(preview / "activity.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT seconds FROM sample").fetchone()[0], 123)
                connection.execute("UPDATE sample SET seconds = 456")
                connection.commit()
            finally:
                connection.close()
            # Fresh import: app_config reads the environment once, just as qt.__main__ does.
            result = subprocess.run(
                [sys.executable, "-c", "import app_config, json; print(json.dumps([str(p) for p in app_config.BACKUP_DIRECTORIES]))"],
                cwd=Path(__file__).parent, env=environment, capture_output=True, text=True, check=True,
            )
            self.assertEqual(json.loads(result.stdout), [str((preview / "backups").resolve())])
            self.assertEqual(database.read_bytes(), before_database)
            self.assertEqual(settings.read_bytes(), before_settings)


if __name__ == "__main__":
    unittest.main()
