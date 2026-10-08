"""Build every release file for the version in app_config: the Qt app, the installer, and checksums

Run from the project folder with `py tools/build_release.py`. Each step must pass before the next one runs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app_config import APP_VERSION  # noqa: E402

NOTICES_PATH = ROOT / "build" / "release" / "Third-Party Notices.txt"
INSTALLER_FOLDER = ROOT / "dist" / "installer"
# The program folder PyInstaller makes: the program and its _internal runtime
APP_FOLDER = ROOT / "dist" / "PS Focus"


def run(*arguments: str) -> None:
    print(">", " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=ROOT, check=True)


def find_inno_setup() -> str:
    candidates = [shutil.which("ISCC.exe")] + [
        str(Path(base) / "Inno Setup 6" / "ISCC.exe")
        for base in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs", os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""))
        if base
    ]
    found = next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)
    if found is None:
        raise SystemExit("Inno Setup 6 is required: winget install --id JRSoftware.InnoSetup -e --scope user")
    return found


def smoke_test(executable: Path) -> None:
    """Start the built app with throwaway data, on Windows' own display and an invisible one, and have it draw every
    module, switch layouts and Settings, and close. It leaves Windows startup and any running PS Focus alone"""
    for platform in ("windows", "offscreen"):
        with tempfile.TemporaryDirectory(prefix="smoke-", dir=ROOT / "build") as folder:
            # Its data folder, backups included, is the temporary one: never the real Documents or OneDrive backups
            environment = {**os.environ, "APPDATA": folder, "PSFOCUS_DATA_DIR": folder, "QT_QPA_PLATFORM": platform}
            subprocess.run([str(executable), "--smoke-test"], cwd=ROOT, env=environment, check=True, timeout=60)


def main() -> int:
    python = sys.executable
    run(python, "-m", "unittest", "discover")
    sys.path.insert(0, str(ROOT / "tools"))
    from write_qt_notices import RELEASE_HEADER, write_notices

    notices = write_notices(RELEASE_HEADER, NOTICES_PATH)
    # The archive inside the program is compressed as far as zlib goes, rebuilt each time at that level
    os.environ["PYINSTALLER_ZLIB_COMPRESSION_LEVEL"] = "9"
    run(python, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN", "PS Focus.spec")
    executable = APP_FOLDER / "PS Focus.exe"
    run(python, "tools/check_credentials.py", "--archive", str(executable), "--verify-qt-binaries")
    run(python, "tools/check_credentials.py", "--directory", str(APP_FOLDER / "_internal"), "--verify-qt-binaries")
    smoke_test(executable)
    run(find_inno_setup(), "/Q", f"/DAppVersion={APP_VERSION}", f"/DNoticesFile={notices}", f"/DAppFolder={APP_FOLDER}", r"installer\PS Focus.iss")
    installer = INSTALLER_FOLDER / f"PS-Focus-Setup-{APP_VERSION}.exe"
    checksums = INSTALLER_FOLDER / f"PS-Focus-{APP_VERSION}-SHA256SUMS.txt"
    run(python, "tools/write_checksums.py", str(installer), "--output", str(checksums))
    # The installer is the one file that is published. The app it was packed from is removed, so a loose copy
    # is not started by mistake: a packaged copy points the Windows startup entry at itself. Installers of
    # earlier versions go too; published ones can be downloaded again from the release page
    shutil.rmtree(APP_FOLDER, ignore_errors=True)
    (ROOT / "dist" / "PS Focus.exe").unlink(missing_ok=True)
    for leftover in list(INSTALLER_FOLDER.glob("PS-Focus-Setup-*.exe")) + list(INSTALLER_FOLDER.glob("PS-Focus-*-SHA256SUMS.txt")):
        if leftover not in (installer, checksums):
            leftover.unlink(missing_ok=True)
    # The build folder is only a cache, and it holds a copy of the sign-in client configuration. The Qt packages
    # downloaded for their licence notices stay, see tools/write_qt_notices.py
    for item in (ROOT / "build").iterdir():
        if item.name != "qt-preview":
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
    for item in (ROOT / "build" / "qt-preview").glob("*"):
        if item.name != "wheels":
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
    print(f"Release {APP_VERSION} is ready in dist/installer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
