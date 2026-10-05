"""Build every release file for the version in app_config: the app, the installer, and checksums

Run from the project folder with `py tools/build_release.py`. Each step must pass before the next one runs.
"""
from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app_config import APP_VERSION  # noqa: E402

# Bundled into the executables; each package's own licence files go into the notices
BUNDLED_PACKAGES = ("pystray", "pillow", "six")
NOTICES_PATH = ROOT / "build" / "release" / "Third-Party Notices.txt"
INSTALLER_FOLDER = ROOT / "dist" / "installer"


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


def write_third_party_notices() -> Path:
    sections = [
        "PS Focus includes the following third-party software. Each is provided under its own licence, reproduced below.\n"
        "Source code for these components is available from https://pypi.org (packages) and https://www.python.org (Python and Tcl/Tk).\n"
    ]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    sections.append(f"===== Python {sys.version.split()[0]}, including Tcl/Tk and its other bundled libraries =====\n\n{python_license.read_text(encoding='utf-8', errors='replace')}")
    for package in BUNDLED_PACKAGES:
        distribution = importlib.metadata.distribution(package)
        license_files = [file for file in distribution.files or [] if any(word in file.name.upper() for word in ("LICENSE", "COPYING", "NOTICE"))]
        if not license_files:
            raise SystemExit(f"No licence file found for bundled package {package}")
        header = f"===== {distribution.metadata['Name']} {distribution.version} ====="
        texts = [Path(distribution.locate_file(file)).read_text(encoding="utf-8", errors="replace") for file in license_files]
        sections.append(header + "\n\n" + "\n\n".join(texts))
    NOTICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTICES_PATH.write_text("\n\n".join(sections), encoding="utf-8")
    return NOTICES_PATH


def main() -> int:
    python = sys.executable
    run(python, "-m", "unittest", "discover")
    run(python, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN", "PS Focus.spec")
    run(python, "tools/check_credentials.py", "--archive", "dist/PS Focus.exe")
    notices = write_third_party_notices()
    run(find_inno_setup(), "/Q", f"/DAppVersion={APP_VERSION}", f"/DNoticesFile={notices}", r"installer\PS Focus.iss")
    installer = INSTALLER_FOLDER / f"PS-Focus-Setup-{APP_VERSION}.exe"
    checksums = INSTALLER_FOLDER / f"PS-Focus-{APP_VERSION}-SHA256SUMS.txt"
    run(python, "tools/write_checksums.py", str(installer), "--output", str(checksums))
    # The installer is the one file that is published. The app it was packed from is removed, so a loose copy
    # is not started by mistake: a packaged copy points the Windows startup entry at itself. Installers of
    # earlier versions go too; published ones can be downloaded again from the release page
    (ROOT / "dist" / "PS Focus.exe").unlink(missing_ok=True)
    for leftover in list(INSTALLER_FOLDER.glob("PS-Focus-Setup-*.exe")) + list(INSTALLER_FOLDER.glob("PS-Focus-*-SHA256SUMS.txt")):
        if leftover not in (installer, checksums):
            leftover.unlink(missing_ok=True)
    # The build folder is only a cache, and it holds a copy of the sign-in client configuration
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    print(f"Release {APP_VERSION} is ready in dist/installer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
