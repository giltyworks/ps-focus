"""Uninstall mode of the app, run as `PS Focus.exe --uninstall`: what is removed and how

Removes PS Focus and, when asked, its settings, activity history, and backups. The window asking is the app's own:
qt/uninstall_window.py, or ui_uninstall.py in the Tk app
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from google_drive import GoogleDriveSync
from unpack_cleanup import remove_stale_unpack_folders
from windows_startup import shell_folder, system_directory, system_executable

APP_NAME = "PS Focus"
LEGACY_APP_NAME = "FocusTrace"
APP_EXECUTABLE = "PS Focus.exe"
BACKUP_FOLDER_NAME = "PS Focus Backups"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
SELF_DELETE_VARIABLE = "PSFOCUS_UNINSTALLER"
INSTALL_DIRECTORY_VARIABLE = "PSFOCUS_INSTALL_DIRECTORY"
RUNTIME_DIRECTORY_VARIABLE = "PSFOCUS_RUNTIME_DIRECTORY"
# The folder beside the app holding its libraries, which the running app keeps in use until it exits
RUNTIME_FOLDER_NAME = "_internal"
# Must match installer/PS Focus.iss
UNINSTALL_KEY_PATH = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
# Files the installer places beside the app, under names that differ from the source files they are made from,
# and the separate uninstaller that versions before 1.0.1 installed
INSTALLED_FILES = ("Terms of Use.txt", "Privacy Policy.txt", "License.txt", "Third-Party Notices.txt", "Uninstall PS Focus.exe")
CSIDL_PROGRAMS = 0x0002
CSIDL_DESKTOPDIRECTORY = 0x0010
WINDOW_TITLE = f"Uninstall {APP_NAME}"
WARNING_MESSAGE = "This will permanently delete all user data. Continue?"
DONE_MESSAGE_KEPT = f"{APP_NAME} has been removed. Your activity history, settings, and backups were kept"
DONE_MESSAGE_DELETED = f"{APP_NAME} and all of its data have been removed"


def data_directories() -> list[Path]:
    """Return every folder PS Focus writes user data to, matching the locations used by main.py"""
    app_data_root = Path(os.environ.get("APPDATA", Path.home()))
    directories = [
        app_data_root / APP_NAME,
        app_data_root / LEGACY_APP_NAME,
        Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / BACKUP_FOLDER_NAME,
    ]
    if os.environ.get("OneDrive"):
        directories.append(Path(os.environ["OneDrive"]) / BACKUP_FOLDER_NAME)
    return list(dict.fromkeys(directories))


def stop_running_app() -> None:
    command = [system_executable("taskkill.exe"), "/F", "/IM", APP_EXECUTABLE]
    # The uninstaller is PS Focus.exe itself, so this process and the launcher that started it are spared
    for process_id in (os.getpid(), os.getppid()):
        command += ["/FI", f"PID ne {process_id}"]
    subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1.5)


def revoke_google_access(app_data: Path) -> None:
    """Withdraw the saved Google sign-in before its token file is deleted"""
    sync = GoogleDriveSync(app_data, app_data / "credentials.json")
    if sync.connected:
        try:
            sync.sign_out()
        except Exception:
            pass


def remove_startup_entries() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            for value_name in (APP_NAME, LEGACY_APP_NAME):
                try:
                    winreg.DeleteValue(key, value_name)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def remove_installation_entries() -> None:
    """Remove the Installed apps entry and the shortcuts that the installer created"""
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY_PATH)
    except OSError:
        pass
    for csidl in (CSIDL_PROGRAMS, CSIDL_DESKTOPDIRECTORY):
        folder = shell_folder(csidl)
        if folder is not None:
            try:
                (folder / f"{APP_NAME}.lnk").unlink(missing_ok=True)
            except OSError:
                pass


def _clear_read_only_and_retry(function, path, _error) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def remove_directories(directories: list[Path]) -> list[Path]:
    """Delete each folder and return the ones that could not be removed"""
    failed = []
    for directory in directories:
        if not directory.exists():
            continue
        try:
            shutil.rmtree(directory, onerror=_clear_read_only_and_retry)
        except OSError:
            failed.append(directory)
    return failed


def remove_program_files(program_directory: Path, running_executable: Path) -> list[Path]:
    """Delete the files installed beside the app now, and the running executable once it has exited"""
    failed = []
    for name in INSTALLED_FILES:
        try:
            (program_directory / name).unlink(missing_ok=True)
        except OSError:
            failed.append(program_directory / name)
    environment = {**os.environ, SELF_DELETE_VARIABLE: str(running_executable)}
    environment.pop(INSTALL_DIRECTORY_VARIABLE, None)
    environment.pop(RUNTIME_DIRECTORY_VARIABLE, None)
    if program_directory.name == APP_NAME:
        # Only the installer's own folder is removed, and rd without /s leaves it alone unless it is empty
        environment[INSTALL_DIRECTORY_VARIABLE] = str(program_directory)
        # The libraries beside the app go with it; only in the installer's folder, where they are the app's alone
        if (program_directory / RUNTIME_FOLDER_NAME).is_dir():
            environment[RUNTIME_DIRECTORY_VARIABLE] = str(program_directory / RUNTIME_FOLDER_NAME)
    # Windows will not delete a running program, so a helper retries each second, for up to a minute, until
    # this process has exited; the closing message can stay open in the meantime. Paths reach cmd through
    # environment variables, so nothing in them is read as part of the command, and starting in the system
    # folder makes cmd run the real ping rather than one beside the app
    target, folder = f'"%{SELF_DELETE_VARIABLE}%"', f'"%{INSTALL_DIRECTORY_VARIABLE}%"'
    runtime = f'"%{RUNTIME_DIRECTORY_VARIABLE}%"'
    subprocess.Popen(
        f'"{system_executable("cmd.exe")}" /d /s /c "for /L %i in (1,1,60) do @(del /f /q {target} >nul 2>&1'
        f' & if not exist {target} ((if defined {RUNTIME_DIRECTORY_VARIABLE} rd /s /q {runtime})'
        f' & (if defined {INSTALL_DIRECTORY_VARIABLE} rd {folder}) & exit)'
        f' else ping -n 2 127.0.0.1 >nul)"',
        cwd=system_directory(),
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
    return failed


def uninstall(delete_data: bool) -> list[Path]:
    """Remove the app, and its user data when requested, returning anything left behind"""
    failed = []
    stop_running_app()
    remove_startup_entries()
    if delete_data:
        directories = data_directories()
        revoke_google_access(directories[0])
        failed += remove_directories(directories)
    # Program files are removed only by the packaged app, never when run from the source folder
    if getattr(sys, "frozen", False):
        # The app closed above had no chance to delete its unpack folder, and no other copy is still starting
        remove_stale_unpack_folders(minimum_age_seconds=0)
        running_executable = Path(sys.executable).resolve()
        remove_installation_entries()
        failed += remove_program_files(running_executable.parent, running_executable)
    return failed
