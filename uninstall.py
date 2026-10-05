"""Uninstall mode of the app, run as `PS Focus.exe --uninstall`

Removes PS Focus and, when asked, its settings, activity history, and backups
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox

from google_drive import GoogleDriveSync
from app_config import COLORS
from unpack_cleanup import remove_stale_unpack_folders
from widgets import OutlinedButton, checkbox_image
from windows_startup import set_title_bar_colors, shell_folder, system_directory, system_executable

APP_NAME = "PS Focus"
LEGACY_APP_NAME = "FocusTrace"
APP_EXECUTABLE = "PS Focus.exe"
BACKUP_FOLDER_NAME = "PS Focus Backups"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
SELF_DELETE_VARIABLE = "PSFOCUS_UNINSTALLER"
INSTALL_DIRECTORY_VARIABLE = "PSFOCUS_INSTALL_DIRECTORY"
# Must match installer/PS Focus.iss
UNINSTALL_KEY_PATH = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
# Files the installer places beside the app, under names that differ from the source files they are made from,
# and the separate uninstaller that versions before 1.0.1 installed
INSTALLED_FILES = ("Terms of Use.txt", "Privacy Policy.txt", "Third-Party Notices.txt", "Uninstall PS Focus.exe")
CSIDL_PROGRAMS = 0x0002
CSIDL_DESKTOPDIRECTORY = 0x0010
WINDOW_TITLE = f"Uninstall {APP_NAME}"
WARNING_MESSAGE = "This will permanently delete all user data. Continue?"
# Space around the uninstall window's contents, and the width its text wraps at
DIALOG_PADDING = 14
DIALOG_TEXT_WIDTH = 300


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
    if program_directory.name == APP_NAME:
        # Only the installer's own folder is removed, and rd without /s leaves it alone unless it is empty
        environment[INSTALL_DIRECTORY_VARIABLE] = str(program_directory)
    # Windows will not delete a running program, so a helper retries each second, for up to a minute, until
    # this process has exited; the closing message can stay open in the meantime. Paths reach cmd through
    # environment variables, so nothing in them is read as part of the command, and starting in the system
    # folder makes cmd run the real ping rather than one beside the app
    target, folder = f'"%{SELF_DELETE_VARIABLE}%"', f'"%{INSTALL_DIRECTORY_VARIABLE}%"'
    subprocess.Popen(
        f'"{system_executable("cmd.exe")}" /d /s /c "for /L %i in (1,1,60) do @(del /f /q {target} >nul 2>&1'
        f' & if not exist {target} ((if defined {INSTALL_DIRECTORY_VARIABLE} rd {folder}) & exit)'
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


def confirm_and_uninstall(delete_data: bool, parent: tk.Misc | None = None) -> bool:
    """Run the uninstall, asking first when user data would be deleted; return whether it ran"""
    if delete_data and not messagebox.askyesno(WINDOW_TITLE, WARNING_MESSAGE, icon="warning", default="no", parent=parent):
        return False
    if parent is not None:
        parent.withdraw()
    failed = uninstall(delete_data)
    if failed:
        remaining = "\n".join(str(path) for path in failed)
        messagebox.showwarning(WINDOW_TITLE, f"{APP_NAME} was removed, but these items could not be deleted:\n\n{remaining}")
    elif delete_data:
        messagebox.showinfo(WINDOW_TITLE, f"{APP_NAME} and all of its data have been removed")
    else:
        messagebox.showinfo(WINDOW_TITLE, f"{APP_NAME} has been removed. Your activity history, settings, and backups were kept")
    return True


class UninstallDialog:
    """The uninstall window, styled like the app: dark title bar, rounded buttons, and the app's checkbox"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(WINDOW_TITLE)
        root.configure(bg=COLORS["background"])
        root.resizable(False, False)
        icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "icons" / "PSFocus.ico"
        try:
            root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass
        set_title_bar_colors(root)
        font_bold = tkfont.Font(root=root, family="Segoe UI Semibold", size=10)
        font_small = tkfont.Font(root=root, family="Segoe UI", size=9)

        def text(parent: tk.Widget, content: str, color: str, font: tkfont.Font, wraplength: int = 0) -> tk.Label:
            return tk.Label(
                parent, text=content, bg=COLORS["background"], fg=COLORS[color], font=font, wraplength=wraplength, justify="left", bd=0, padx=0, pady=0
            )

        text(root, f"Remove {APP_NAME} from this PC?", "text", font_bold).pack(padx=DIALOG_PADDING, pady=(DIALOG_PADDING, 4), anchor="w")
        text(
            root,
            "Your activity history, settings, and backups are kept unless you choose to delete them below",
            "muted",
            font_small,
            DIALOG_TEXT_WIDTH,
        ).pack(padx=DIALOG_PADDING, pady=(0, 12), anchor="w")

        # The app's own checkbox: its name, then the rounded box; clicking either ticks it
        self.delete_data = tk.BooleanVar(root, value=False)
        option = tk.Frame(root, bg=COLORS["background"], cursor="hand2")
        option.pack(padx=DIALOG_PADDING, pady=(0, 14), anchor="w")
        label = text(option, "Also delete all user data", "text", font_small)
        label.configure(cursor="hand2")
        label.pack(side="left", padx=(0, 6))
        self.checkbox = tk.Canvas(option, width=18, height=18, bg=COLORS["background"], highlightthickness=0, cursor="hand2", takefocus=True)
        self.checkbox.pack(side="left")
        self.checkbox_images = {checked: checkbox_image(checked, COLORS["background"]) for checked in (False, True)}
        for widget in (option, label, self.checkbox):
            widget.bind("<Button-1>", self._toggle_delete_data)
        self.checkbox.bind("<Return>", self._toggle_delete_data)
        self.checkbox.bind("<space>", self._toggle_delete_data)
        self._draw_checkbox()

        actions = tk.Frame(root, bg=COLORS["background"])
        actions.pack(padx=DIALOG_PADDING, pady=(0, DIALOG_PADDING), anchor="e")
        self._button(actions, "Cancel", root.destroy, font_small).pack(side="left", padx=(0, 6))
        self._button(actions, "Uninstall", self._uninstall, font_small, accent=True).pack(side="left")

        root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_width()) // 2
        y = (root.winfo_screenheight() - root.winfo_height()) // 2
        root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _toggle_delete_data(self, _event: tk.Event | None = None) -> None:
        self.delete_data.set(not self.delete_data.get())
        self._draw_checkbox()

    def _draw_checkbox(self) -> None:
        self.checkbox.delete("all")
        self.checkbox.create_image(9, 9, image=self.checkbox_images[self.delete_data.get()])

    def _button(self, parent: tk.Widget, label: str, command, font: tkfont.Font, accent: bool = False) -> OutlinedButton:
        bg = COLORS["accent_dark"] if accent else COLORS["panel_alt"]
        fg = COLORS["accent"] if accent else COLORS["text"]
        return OutlinedButton(parent, text=label, command=command, bg=bg, fg=fg, padx=17, pady=6, font=font)

    def _uninstall(self) -> None:
        if confirm_and_uninstall(self.delete_data.get(), self.root):
            self.root.destroy()


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The PS Focus uninstaller runs only on Windows")
    # Everything removed belongs to the current user, so the uninstaller runs without administrator rights
    root = tk.Tk()
    UninstallDialog(root)
    root.mainloop()


if __name__ == "__main__":
    main()
