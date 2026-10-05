"""Removal of the unpack folders that earlier runs of the packaged app left in the temporary folder

The packaged app unpacks itself into a folder named _MEI... each time it starts, and its launcher deletes that
folder when the app ends. A run that is ended by force (the uninstaller, Task Manager, a crash, a power cut)
leaves its folder behind, and nothing else ever removes it
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

UNPACK_FOLDER_PATTERN = "_MEI*"
# Present in every PS Focus unpack folder and in no other program's, so only the app's own folders are removed
OWN_FILE = Path("assets") / "icons" / "PSFocus.ico"
# The Python library, which every running copy has loaded from its unpack folder
PYTHON_LIBRARY_PATTERN = "python3*.dll"
# A copy that is still starting has not loaded its files yet, so a folder this new is left alone
MINIMUM_AGE_SECONDS = 600


def current_unpack_folder() -> Path | None:
    """Return the folder this run was unpacked into, or None when running from source"""
    bundle_root = getattr(sys, "_MEIPASS", None)
    return Path(bundle_root).resolve() if bundle_root else None


def _remove_if_stale(folder: Path, current: Path | None, minimum_age_seconds: float) -> bool:
    if folder.is_symlink() or not folder.is_dir() or folder.resolve() == current:
        return False
    if not (folder / OWN_FILE).is_file() or time.time() - folder.stat().st_mtime < minimum_age_seconds:
        return False
    # Windows refuses to delete a library that a running program has loaded, so a folder still in use fails
    # here with nothing removed. Renaming the folder would not show this: Windows allows that while it is in use
    for library in folder.glob(PYTHON_LIBRARY_PATTERN):
        library.unlink()
    # The file that marks the folder as the app's goes last, so an interrupted removal is finished next time
    for entry in folder.iterdir():
        if entry.name == OWN_FILE.parts[0]:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    shutil.rmtree(folder)
    return True


def remove_stale_unpack_folders(temp_directory: Path | None = None, minimum_age_seconds: float = MINIMUM_AGE_SECONDS) -> int:
    """Delete the unpack folders that ended runs left behind, and return how many were removed

    Only the packaged app does this, unless a folder to search is given. A folder that cannot be removed is
    left for the next attempt
    """
    current = current_unpack_folder()
    if temp_directory is None:
        if current is None:
            return 0
        temp_directory = Path(tempfile.gettempdir())
    removed = 0
    try:
        folders = list(temp_directory.glob(UNPACK_FOLDER_PATTERN))
    except OSError:
        return 0
    for folder in folders:
        try:
            removed += _remove_if_stale(folder, current, minimum_age_seconds)
        except OSError:
            continue
    return removed
