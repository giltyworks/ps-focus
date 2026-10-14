"""A separate data folder for a copy run from source, so it never touches the real activity history

The installed app and a copy run from source would otherwise both count the same seconds into one database. Each
start copies the real history and settings into the copy's folder, so the copy shows real figures. The Google
sign-in is not copied; an explicit sign-in there uses separate cloud files. Must run before app_config is imported, which
reads the folder once
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path

# Still named for the "Qt preview" it began as, because the folder, its Drive files and the window title persist
COPY_FOLDER_NAME = "PS Focus Qt Preview"
# The developer version's, `PS Focus.exe --dev`: the installed app on a copy of the data, with the developer menu
DEV_FOLDER_NAME = "PS Focus Dev"


def use_data_copy(folder_name: str = COPY_FOLDER_NAME) -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    real, copy = appdata / "PS Focus", appdata / folder_name
    copy.mkdir(parents=True, exist_ok=True)
    database = real / "activity.sqlite3"
    if database.exists():
        # SQLite's own copy, which stays consistent while the installed app is writing to the database
        with ExitStack() as connections:
            source = connections.enter_context(closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)))
            target = connections.enter_context(closing(sqlite3.connect(copy / "activity.sqlite3")))
            source.backup(target)
    if (real / "settings.json").exists():
        shutil.copyfile(real / "settings.json", copy / "settings.json")
    os.environ["PSFOCUS_DATA_DIR"] = str(copy)
    return copy
