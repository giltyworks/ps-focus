"""Windows integration: taskbar identity, the startup registry entry, and migration from the earlier app name"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import app_config
from app_config import APP_NAME, APP_USER_MODEL_ID, LEGACY_APP_NAME


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> None:
    if os.name != "nt":
        return
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
    set_app_id.argtypes = [ctypes.c_wchar_p]
    set_app_id.restype = ctypes.c_long
    result = set_app_id(app_id)
    if result != 0:
        raise OSError(f"Could not set Windows AppUserModelID: HRESULT {result:#x}")


def system_directory() -> Path:
    """Return the Windows system folder as reported by Windows itself, not by an environment variable"""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    kernel32.GetSystemDirectoryW.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise OSError("Could not locate the Windows system folder")
    return Path(buffer.value)


def system_executable(relative_path: str) -> str:
    """Return the full path of a Windows system program, so a same-named file beside the app is never run instead"""
    return str(system_directory() / relative_path)


def set_title_bar_colors_for_handle(window_handle: int | None) -> None:
    """Colour the title bar of the top-level window with this handle, see set_title_bar_colors"""
    if os.name != "nt" or not window_handle:
        return
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    set_attribute = dwmapi.DwmSetWindowAttribute
    set_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    set_attribute.restype = ctypes.c_long

    def color_ref(color: str) -> ctypes.c_uint:
        red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
        return ctypes.c_uint(red | green << 8 | blue << 16)

    dark_mode = ctypes.c_int(1)
    background_color = color_ref(app_config.COLORS["background"])
    text_color = color_ref(app_config.COLORS["text"])
    for attribute, value in (
        (20, dark_mode),
        (35, background_color),
        (34, background_color),
        (36, text_color),
    ):
        set_attribute(window_handle, attribute, ctypes.byref(value), ctypes.sizeof(value))


def set_startup(enabled: bool, minimized: bool) -> None:
    if os.name != "nt":
        raise OSError("Windows startup integration is available only on Windows")
    import winreg

    executable = sys.executable
    if not getattr(sys, "frozen", False):
        pythonw = Path(executable).with_name("pythonw.exe")
        if pythonw.exists():
            executable = str(pythonw)
    arguments = [executable]
    if not getattr(sys, "frozen", False):
        arguments.append(str(Path(__file__).resolve()))
    if minimized:
        arguments.append("--minimized")
    command = subprocess.list2cmdline(arguments)
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, LEGACY_APP_NAME)
        except FileNotFoundError:
            pass
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def refresh_startup_entry(settings: dict) -> None:
    """Point an enabled startup entry at this executable, so a moved or reinstalled app still starts with Windows

    Only packaged builds do this; running from source must not take over the installed app's entry
    """
    if not getattr(sys, "frozen", False) or not settings.get("launch_on_startup"):
        return
    try:
        set_startup(True, bool(settings.get("start_minimized")))
    except (OSError, ImportError):
        pass


def shell_folder(csidl: int) -> Path | None:
    """Return a per-user shell folder such as the Start menu Programs folder, wherever Windows has placed it"""
    if os.name != "nt":
        return None
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SHGetFolderPathW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p]
    shell32.SHGetFolderPathW.restype = ctypes.c_long
    buffer = ctypes.create_unicode_buffer(32768)
    if shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) != 0:
        return None
    return Path(buffer.value)


class SingleInstance:
    """The claim to be the one running copy of the app, and the signals other programs send it

    Two copies would each count the same seconds into the one activity database, doubling the recorded time.
    Windows releases the claim when the process holding it ends, however it ends. A later copy signals the
    running one to bring its window up, and the installer signals it to exit before replacing its files
    """

    # Local names are per signed-in Windows user session, so each user of a shared PC runs their own copy.
    # The claim and exit names must match installer/PS Focus.iss
    CLAIM_NAME = "Local\\PSFocus.RunningCopy"
    SHOW_NAME = "Local\\PSFocus.ShowWindow"
    EXIT_NAME = "Local\\PSFocus.ExitRequest"
    ERROR_ALREADY_EXISTS = 183

    def __init__(self) -> None:
        self.already_running = False
        self._show_event = None
        self._exit_event = None
        if os.name != "nt":
            return
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self._kernel32.CreateMutexW.restype = ctypes.c_void_p
        self._kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        self._kernel32.CreateEventW.restype = ctypes.c_void_p
        self._kernel32.SetEvent.argtypes = [ctypes.c_void_p]
        self._kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._kernel32.WaitForSingleObject.restype = ctypes.c_uint
        # Kept for as long as this object lives; the claim is the handle staying open
        self._claim = self._kernel32.CreateMutexW(None, False, self.CLAIM_NAME)
        self.already_running = bool(self._claim) and ctypes.get_last_error() == self.ERROR_ALREADY_EXISTS
        # An event that resets itself once it has been noticed; a later copy opens the same one by name
        self._show_event = self._kernel32.CreateEventW(None, False, False, self.SHOW_NAME)
        self._exit_event = self._kernel32.CreateEventW(None, False, False, self.EXIT_NAME)

    def _signal(self, event) -> None:
        if event:
            self._kernel32.SetEvent(event)

    def _signalled(self, event) -> bool:
        return bool(event) and self._kernel32.WaitForSingleObject(event, 0) == 0

    def ask_running_copy_to_show(self) -> None:
        self._signal(self._show_event)

    def show_requested(self) -> bool:
        """Return true once for each time a later copy has asked for the window"""
        return self._signalled(self._show_event)

    def ask_running_copy_to_exit(self) -> None:
        """Signal as the installer does; used by the tests"""
        self._signal(self._exit_event)

    def exit_requested(self) -> bool:
        """Return true once the installer has asked the running copy to close, so it can replace its files

        Without this an installer closes the app through Windows' Restart Manager, and the launcher at the front
        of the packaged app then waits about 30 seconds to be ended by force
        """
        return self._signalled(self._exit_event)


def migrate_legacy_app_data() -> None:
    """Carry settings, history and sign-in over from the app's earlier name, the first time this name is used

    Done only before the new data folder exists. Copying whenever a file was missing would bring back a Google
    sign-in after the user had signed out, since signing out deletes that file
    """
    if not app_config.LEGACY_APP_DATA.is_dir() or app_config.APP_DATA.exists():
        return
    app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
    for filename in ("settings.json", "activity.sqlite3", "google-token.json"):
        source = app_config.LEGACY_APP_DATA / filename
        destination = app_config.APP_DATA / filename
        if source.is_file() and not destination.exists():
            shutil.copy2(source, destination)


def migrate_legacy_startup(settings: dict) -> None:
    if os.name != "nt":
        return
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE) as key:
            winreg.QueryValueEx(key, LEGACY_APP_NAME)
    except FileNotFoundError:
        return
    set_startup(bool(settings.get("launch_on_startup")), bool(settings.get("start_minimized")))


def apply_first_run_startup(settings: dict) -> None:
    """Register the default Windows startup entry for a new installation and save its settings"""
    try:
        set_startup(bool(settings.get("launch_on_startup")), bool(settings.get("start_minimized")))
    except (OSError, ImportError):
        settings["launch_on_startup"] = False
    app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
    app_config.SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
