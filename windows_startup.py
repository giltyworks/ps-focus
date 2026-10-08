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


def set_title_bar_colors(window) -> None:
    """Colour a window's title bar to match the app: dark, with the app's background and text colours"""
    if os.name != "nt":
        return
    window.update_idletasks()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_ancestor = user32.GetAncestor
    get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    get_ancestor.restype = ctypes.c_void_p
    set_title_bar_colors_for_handle(get_ancestor(ctypes.c_void_p(window.winfo_id()), 2))


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


class SizeLimits:
    """Hold a window's size between limits while the user drags its edges, moving only the edge being dragged

    Tk enforces its own size limits by changing the size it is given while keeping the window's top left corner.
    Dragging the top or left edge past a limit then pulls the opposite edge along, and the whole window slides.
    Windows asks a window, while an edge is dragged, whether to change the proposed outline (WM_SIZING); the
    window's handler is wrapped here to bring back the dragged edge itself, as other Windows programs do. It
    also keeps the window from being maximized
    """

    WM_SIZING = 0x0214
    WM_WINDOWPOSCHANGING = 0x0046
    WM_NCLBUTTONDBLCLK = 0x00A3
    WM_SYSCOMMAND = 0x0112
    SC_MAXIMIZE = 0xF030
    # The window's edges and corners as Windows names the spot clicked, from the left edge to the bottom right
    EDGE_HITS = range(10, 18)
    CAPTION_HIT = 2
    GWL_STYLE = -16
    WS_MAXIMIZEBOX = 0x00010000
    WM_ENTERSIZEMOVE = 0x0231
    WM_EXITSIZEMOVE = 0x0232
    SWP_NOSIZE = 0x0001
    GWLP_WNDPROC = -4
    # Which edges the WM_SIZING message says are being dragged, numbered by Windows
    LEFT_EDGES = (1, 4, 7)
    RIGHT_EDGES = (2, 5, 8)
    TOP_EDGES = (3, 4, 5)
    BOTTOM_EDGES = (6, 7, 8)

    def __init__(self, window) -> None:
        self._window = window
        # Sizes of the window's contents, as Tk's minsize and maxsize take them
        self.minimum = (1, 1)
        self.maximum = (100000, 100000)
        self._handle = None
        self._procedure = None
        # Set when a drag of an edge or the title bar ends, for the app to notice and clear. Nothing calls back into
        # the app from here: this runs inside Windows' handling of the window, where calling Tk crashes Python
        self.drag_ended = False

    def set(self, minimum: tuple[int, int], maximum: tuple[int, int]) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self._attach()

    def _attach(self) -> None:
        """Wrap the window's handler, once Windows has made the frame around it, which happens when it is shown"""
        if self._procedure is not None or os.name != "nt":
            return
        window_id = self._window.winfo_id()
        if not isinstance(window_id, int) or not self._window.winfo_ismapped():
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32 = user32
        long_pointer = ctypes.c_ssize_t
        procedure_type = ctypes.WINFUNCTYPE(long_pointer, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.CallWindowProcW.restype = long_pointer
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        handle = user32.GetAncestor(ctypes.c_void_p(window_id), 2)
        if not handle:
            return
        self._handle = handle
        # Kept on the object, as Windows calls it for as long as the window lives
        self._procedure = procedure_type(self._handle_message)
        self._previous = user32.SetWindowLongPtrW(handle, self.GWLP_WNDPROC, ctypes.cast(self._procedure, ctypes.c_void_p))
        self.remove_maximize_button()

    def remove_maximize_button(self) -> None:
        """Grey out the window's maximize button; Tk puts it back whenever it changes the window's resizability"""
        if self._handle is None:
            return
        user32 = self._user32
        user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        style = user32.GetWindowLongPtrW(self._handle, self.GWL_STYLE)
        if style & self.WS_MAXIMIZEBOX:
            user32.SetWindowLongPtrW(self._handle, self.GWL_STYLE, ctypes.c_void_p(style & ~self.WS_MAXIMIZEBOX))
            # Not moved, sized or reordered: only the frame is drawn again with the button greyed
            user32.SetWindowPos(self._handle, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)

    def _handle_message(self, handle, message, w_param, l_param):
        try:
            # The window's size follows what it shows, so it is never maximized, nor stretched to the screen's full
            # height by double-clicking an edge; either would only leave the limits to shove the window aside
            if message == self.WM_NCLBUTTONDBLCLK and (w_param in self.EDGE_HITS or w_param == self.CAPTION_HIT):
                return 0
            if message == self.WM_SYSCOMMAND and (w_param & 0xFFF0) == self.SC_MAXIMIZE:
                return 0
            if message == self.WM_ENTERSIZEMOVE:
                # A drag of an edge or the title bar begins; nothing is corrected outside one
                self._dragging = True
                self._dragged_edge = None
            elif message == self.WM_SIZING and l_param and getattr(self, "_dragging", False):
                # Remembered for the final move Windows makes when the edge is let go, see below
                self._dragged_edge = w_param
                self._limit_outline(w_param, ctypes.cast(l_param, ctypes.POINTER(_Rect)).contents)
            elif message == self.WM_WINDOWPOSCHANGING and l_param and getattr(self, "_dragged_edge", None):
                position = ctypes.cast(l_param, ctypes.POINTER(_WindowPosition)).contents
                # Letting go, Windows moves the window to its own outline, not the one corrected above; it is
                # corrected the same way
                if not position.flags & self.SWP_NOSIZE:
                    outline = _Rect(position.x, position.y, position.x + position.cx, position.y + position.cy)
                    self._limit_outline(self._dragged_edge, outline)
                    position.x, position.y = outline.left, outline.top
                    position.cx, position.cy = outline.right - outline.left, outline.bottom - outline.top
            elif message == self.WM_EXITSIZEMOVE:
                self._dragging = False
                self._dragged_edge = None
                self.drag_ended = True
        except Exception:
            # A failure here must never stop the window working; the drag simply goes unlimited
            pass
        return self._user32.CallWindowProcW(self._previous, handle, message, w_param, l_param)

    @property
    def dragging_left_or_top(self) -> bool:
        """Whether the window's left or top edge, or a corner of either, is being dragged"""
        edge = getattr(self, "_dragged_edge", None)
        return edge in self.LEFT_EDGES or edge in self.TOP_EDGES

    def _limit_outline(self, edge: int, outline: "_Rect") -> None:
        # The outline includes the window's frame, which the limits do not; the frame's size is added to them
        window, contents = _Rect(), _Rect()
        self._user32.GetWindowRect(self._handle, ctypes.byref(window))
        self._user32.GetClientRect(self._handle, ctypes.byref(contents))
        frame = ((window.right - window.left) - (contents.right - contents.left), (window.bottom - window.top) - (contents.bottom - contents.top))
        limited = self.limited_outline(
            edge,
            (outline.left, outline.top, outline.right, outline.bottom),
            (window.left, window.top, window.right, window.bottom),
            self.minimum,
            self.maximum,
            frame,
        )
        outline.left, outline.top, outline.right, outline.bottom = limited

    @classmethod
    def limited_outline(
        cls,
        edge: int,
        outline: tuple[int, int, int, int],
        window: tuple[int, int, int, int],
        minimum: tuple[int, int],
        maximum: tuple[int, int],
        frame: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        """Return the outline brought within the limits, only the dragged edges moved from where the window is

        Windows itself holds the outline to the limits as an edge is dragged past them, but does so by moving the
        opposite edge; so every edge not being dragged is put back where the window has it
        """
        left, top, right, bottom = outline
        if edge in cls.LEFT_EDGES:
            right = window[2]
        elif edge in cls.RIGHT_EDGES:
            left = window[0]
        else:
            left, right = window[0], window[2]
        if edge in cls.TOP_EDGES:
            bottom = window[3]
        elif edge in cls.BOTTOM_EDGES:
            top = window[1]
        else:
            top, bottom = window[1], window[3]
        # A least size above the most is taken as the most, so there is always a size to give
        least = (min(minimum[0], maximum[0]), min(minimum[1], maximum[1]))
        width = min(max(right - left, least[0] + frame[0]), maximum[0] + frame[0])
        height = min(max(bottom - top, least[1] + frame[1]), maximum[1] + frame[1])
        if edge in cls.LEFT_EDGES:
            left = right - width
        else:
            right = left + width
        if edge in cls.TOP_EDGES:
            top = bottom - height
        else:
            bottom = top + height
        return left, top, right, bottom


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _WindowPosition(ctypes.Structure):
    _fields_ = [
        ("window", ctypes.c_void_p),
        ("after", ctypes.c_void_p),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("cy", ctypes.c_int),
        ("flags", ctypes.c_uint),
    ]


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
