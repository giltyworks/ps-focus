"""A separate data folder for the Qt version while it is built, so it never touches the real activity history

The installed app and a copy run from source would otherwise both count the same seconds into one database. Each
start copies the real history and settings into the preview folder, so the preview shows real figures. The Google
sign-in is not copied; an explicit preview sign-in uses separate cloud files. Must run before app_config is imported, which
reads the folder once
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path

PREVIEW_FOLDER_NAME = "PS Focus Qt Preview"


def use_preview_data() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    real, preview = appdata / "PS Focus", appdata / PREVIEW_FOLDER_NAME
    preview.mkdir(parents=True, exist_ok=True)
    database = real / "activity.sqlite3"
    if database.exists():
        # SQLite's own copy, which stays consistent while the installed app is writing to the database
        with ExitStack() as connections:
            source = connections.enter_context(closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)))
            target = connections.enter_context(closing(sqlite3.connect(preview / "activity.sqlite3")))
            source.backup(target)
    if (real / "settings.json").exists():
        shutil.copyfile(real / "settings.json", preview / "settings.json")
    os.environ["PSFOCUS_DATA_DIR"] = str(preview)
    return preview
