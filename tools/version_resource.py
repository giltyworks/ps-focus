"""Windows file-properties version information for the PyInstaller builds, taken from app_config"""
from __future__ import annotations

from pathlib import Path

from app_config import APP_NAME, APP_PUBLISHER, APP_VERSION


def version_numbers(version: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in version.split(".")]
    if not 1 <= len(parts) <= 4 or any(not 0 <= part <= 65535 for part in parts):
        raise ValueError(f"Version must be up to four numbers from 0 to 65535: {version}")
    return tuple(parts + [0] * (4 - len(parts)))


def write_version_file(path: Path, description: str, original_filename: str) -> str:
    """Write a PyInstaller version file and return its path for the EXE version= option"""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numbers = version_numbers(APP_VERSION)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([
                StringTable("040904B0", [
                    StringStruct("CompanyName", APP_PUBLISHER),
                    StringStruct("FileDescription", description),
                    StringStruct("FileVersion", APP_VERSION),
                    StringStruct("InternalName", APP_NAME),
                    StringStruct("LegalCopyright", f"Copyright (c) {APP_PUBLISHER}"),
                    StringStruct("OriginalFilename", original_filename),
                    StringStruct("ProductName", APP_NAME),
                    StringStruct("ProductVersion", APP_VERSION),
                ])
            ]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(info), encoding="utf-8")
    return str(path)
