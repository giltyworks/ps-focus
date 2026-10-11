"""Record the website's demo reel: the real app in use, with believable sample data, as a short silent loop

Nothing from the user's own history or account is used: the app runs against a throwaway data folder, a made-up Google
account and a stand-in friends server. Nothing outside the app can get in either: the real mouse is never moved or
clicked, a pretend pointer handing its moves and clicks to the app's own widgets as events; and the screen is never
captured, each frame being painted from the app's own windows alone, on black, with their title bar drawn in. The
computer can be used as normal while it records, about half a minute.

Needs FFmpeg (`winget install --id Gyan.FFmpeg -e --scope user`). Run as `py tools/demo_reel.py [folder]` (the
website's assets by default), which writes demo-reel.mp4 and demo-reel-poster.png; then commit and push the site.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import PropertyMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "assets"
out.mkdir(parents=True, exist_ok=True)
data = Path(tempfile.mkdtemp(prefix="psfocus-reel-"))
# Before app_config is imported, which reads the data folder once
os.environ["PSFOCUS_DATA_DIR"] = str(data)
os.environ["QT_QPA_PLATFORM"] = "windows"
EMAIL = "demo@example.com"
(data / "settings.json").write_text(
    '{"feedback_submitted": true, "show_graph": true, "show_calendar": false, "show_stats": false, "show_friends": false,'
    ' "period": "Week", "panel_transparency": 45, "google_display_names": {"demo@example.com": "gilty"}}',
    encoding="utf-8",
)

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QEnterEvent, QFont, QImage, QMouseEvent, QPainter, QPen, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget  # noqa: E402
from shiboken6 import isValid  # noqa: E402

import google_drive  # noqa: E402
import qt.app as qt_app  # noqa: E402
from qt.app import PSFocusQt  # noqa: E402
from qt import docking, friends_sync, request_popup  # noqa: E402
from qt.docking import FloatingPanel  # noqa: E402

FPS = 30
# Room for the window, a panel pulled out beside it, and landscape
WIDTH, HEIGHT = 720, 640
# The window starts in the middle of the picture, and is moved this far aside when a panel or landscape needs the room
SIDEWAYS = 174


class DemoFriends:
    """The friends server, played by a script: a few friends, and a request that arrives during the reel"""

    configured = True

    def __init__(self):
        now = int(time.time())
        self.friends = [
            {"code": "MIAA2222", "name": "Mia", "updated_at": now,
             "stats": {"two_weeks": 41.6, "total": 1288.4, "today": 2.4, "level": 47, "status": "online", "active": "Krita"}},
            {"code": "LEOO3333", "name": "Leo", "updated_at": now,
             "stats": {"two_weeks": 27.9, "total": 655.0, "today": 1.1, "level": 33, "status": "online"}},
            {"code": "AVAA4444", "name": "Ava", "updated_at": now,
             "stats": {"two_weeks": 18.3, "total": 402.7, "today": 0.0, "level": 26, "status": "away"}},
            {"code": "NOAH5555", "name": "Noah", "updated_at": now - 3600,
             "stats": {"two_weeks": 9.4, "total": 210.2, "today": 0.0, "level": 17, "status": "online"}},
        ]
        self.incoming = []

    def _state(self):
        return {"now": int(time.time()), "me": {"code": "GLTY7K2Q", "name": "gilty"}, "friends": self.friends,
                "incoming": self.incoming, "outgoing": []}

    def sync(self, _name, _stats):
        return self._state()

    def accept(self, code):
        self.incoming = [request for request in self.incoming if request["code"] != code]
        self.friends = self.friends + [{"code": code, "name": "Sam", "updated_at": int(time.time()),
                                        "stats": {"two_weeks": 33.0, "total": 870.5, "today": 1.6, "level": 39, "status": "online", "active": "Photoshop"}}]
        return self._state()

    def decline(self, code):
        self.incoming = [request for request in self.incoming if request["code"] != code]
        return self._state()

    add = remove = lambda self, _code: self._state()
    leave = lambda self: {"left": True}


service = DemoFriends()
patches = [
    patch.object(PSFocusQt, "_start_tray_icon", lambda self: setattr(self, "tray_icon", QSystemTrayIcon())),
    patch.object(PSFocusQt, "_celebrate_level_up", lambda self, level: None),
    patch.object(PSFocusQt, "_check_for_updates", lambda self: None),
    patch.object(qt_app, "foreground_application", lambda: "Photoshop"),
    patch.object(qt_app, "user_is_active", lambda _seconds=300: True),
    patch.object(qt_app, "FriendsService", lambda _token: service),
    # A Google account that is connected but never reached
    patch.object(google_drive.GoogleDriveSync, "connected", new_callable=PropertyMock, return_value=True),
    patch.object(google_drive.GoogleDriveSync, "account_email", lambda self: EMAIL),
    patch.object(google_drive.GoogleDriveSync, "upload_settings", lambda self, settings: None),
    patch.object(google_drive.GoogleDriveSync, "download_activity_backup", lambda self: None),
    patch.object(google_drive.GoogleDriveSync, "upload_activity_backup", lambda self, content: None),
    patch.object(friends_sync.FriendsSync, "account", lambda self: EMAIL),
]
for item in patches:
    item.start()

application = QApplication(sys.argv)
screen = application.primaryScreen().availableGeometry()
# Where on the screen the recorded picture's windows stand
area = QRect(screen.x() + 200, screen.y() + 80, WIDTH, HEIGHT)
# A friend request pops up in the recorded area's corner rather than the screen's
request_popup.RequestPopup.place = lambda self, index: self.move(area.right() - 24 - self.width(), area.bottom() - 24 - self.height())
app = PSFocusQt(application)


def add_sample_history():
    """Ten weeks of plausible drawing sessions, as for the screenshots, and a session going on today"""
    rng = random.Random(11)
    today = date.today()
    store = app.store
    with store.connection:
        for days_ago in range(1, 71):
            day = today - timedelta(days=days_ago)
            if rng.random() < (0.45 if day.weekday() >= 5 else 0.2):
                continue
            start_hour = rng.choice((9, 10, 13, 14, 19, 20))
            hour, remaining = start_hour, rng.choice((35, 50, 75, 90, 110, 140, 170, 205)) * 60
            while remaining > 0 and hour < 24:
                seconds = min(remaining, rng.randint(2400, 3600))
                store.connection.execute(
                    "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (day.isoformat(), hour, seconds)
                )
                remaining -= seconds
                hour += 1
            store.connection.execute(
                "INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', ?)",
                (day.isoformat(), f"{start_hour:02d}:{rng.choice((5, 10, 20, 30, 40)):02d}"),
            )
            if rng.random() < 0.4:
                store.connection.execute("INSERT OR REPLACE INTO productivity_ratings (day, rating) VALUES (?, ?)", (day.isoformat(), rng.randint(5, 9)))
        for hour, seconds in ((9, 2900), (10, 3400), (11, 1750)):
            store.connection.execute(
                "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (today.isoformat(), hour, seconds)
            )
        store.connection.execute("INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', '09:10')", (today.isoformat(),))


add_sample_history()
app._track_and_refresh()
app._arrange_blocks()
app.window.move(area.x() + 36 + SIDEWAYS, area.y() + 36)

# ----- Where things are on the screen -----


def centre(widget, rect) -> QPoint:
    return widget.mapToGlobal(QPoint(*rect) if isinstance(rect, tuple) else rect)


def button_at(widget, button) -> QPoint:
    return widget.mapToGlobal(QPoint(button.left + button.width // 2, button.top + button.height // 2))


def period_button(label) -> QPoint:
    button = next(button for button in app.chart.buttons if button.text == label)
    return button_at(app.chart, button)


def module_icon(name) -> QPoint:
    return app.module_controls.mapToGlobal(app.module_controls.areas[name].center())


def title_of(name) -> QPoint:
    block = app.modules[name]
    rect = block.title_rect()
    return block.mapToGlobal(QPoint(rect.left() + 70, rect.center().y()))


def header_area(name) -> QPoint:
    left, top, right, bottom = getattr(app.header, name)
    return app.header.mapToGlobal(QPoint((left + right) // 2, (top + bottom) // 2))


def landscape_choice() -> QPoint:
    left, top, right, bottom = app.settings_page.orientation_areas[True]
    return app.settings_page.mapToGlobal(QPoint((left + right) // 2, (top + bottom) // 2))


def popup_accept() -> QPoint:
    popup = next(iter(app.friends_sync.popups.values()))
    return button_at(popup, popup.accept_button)


def status_choice(key) -> QPoint:
    menu = next(widget for widget in application.topLevelWidgets() if widget.isVisible() and type(widget).__name__ == "StatusMenu")
    rect = next(row for row_key, _name, _note, row in menu.rows if row_key == key)
    return menu.mapToGlobal(rect.center())


def below_window() -> QPoint:
    """Just past the window's bottom edge, where a panel dropped goes back in under the others"""
    left, _top, right, bottom = app.docking.main_bounds()
    return QPoint((left + right) // 2, bottom + 24)


# ----- The script: where the pointer goes, what it clicks, and the pauses between -----

def move(target, seconds=0.6):
    return ("move", target, seconds)


def wait(seconds):
    return ("wait", seconds)


def click():
    return ("click",)


def press():
    return ("press",)


def release():
    return ("release",)


def do(function):
    return ("do", function)


def request_arrives():
    service.incoming = [{"code": "SAMM6666", "name": "Sam"}]
    app.friends_sync.sync()


def window_grip() -> QPoint:
    """An empty spot on the row of module icons, which the window is moved by"""
    row = app.module_controls
    return row.mapToGlobal(QPoint(40, row.height() // 2))


def drag_window(by: int) -> list:
    """Move the window sideways by its top, as a user would to make room"""
    return [move(window_grip, 0.5), press(), move(lambda: pointer_device.pos + QPoint(by, 0), 0.6), release(), wait(0.2)]


SCRIPT = [
    wait(0.8),
    # The day's time counting up, then the graph over longer periods
    move(lambda: period_button("1M"), 0.7), click(), wait(0.9),
    move(lambda: period_button("1Y"), 0.4), click(), wait(1.0),
    # Modules come and go from the icons at the top
    move(lambda: module_icon("graph"), 0.6), click(), wait(0.3),
    move(lambda: module_icon("calendar"), 0.3), click(), wait(0.7),
    move(lambda: button_at(app.calendar, app.calendar.toggle), 0.5), click(), wait(1.2),
    click(), wait(0.4),
    # A module pulled out into a panel of its own, then left alone, which turns everything see-through
    *drag_window(-SIDEWAYS),
    move(lambda: title_of("calendar"), 0.5), press(),
    move(lambda: title_of("calendar") + QPoint(330, 30), 0.8), release(), wait(0.4),
    move(lambda: QPoint(area.left() + 520, area.bottom() - 70), 0.6), wait(1.2),
    # And snapped back into the window
    move(lambda: title_of("calendar"), 0.6), press(),
    move(below_window, 0.8), wait(0.4), release(), wait(0.4),
    *drag_window(SIDEWAYS),
    # Friends: who is drawing now, and a request that pops up and is accepted
    move(lambda: module_icon("calendar"), 0.5), click(), wait(0.2),
    move(lambda: module_icon("friends"), 0.3), click(), wait(1.0),
    do(request_arrives), wait(0.9),
    move(popup_accept, 0.8), click(), wait(1.2),
    # Going invisible from the menu by your name
    move(lambda: header_area("status_area"), 0.7), click(), wait(0.4),
    move(lambda: status_choice("invisible"), 0.5), click(), wait(0.9),
    # Landscape, from Settings
    *drag_window(-SIDEWAYS),
    move(lambda: header_area("settings_area"), 0.6), click(), wait(0.5),
    move(landscape_choice, 0.6), click(), wait(2.0),
]

# ----- The pretend pointer -----


class Pointer:
    """Hands moves and clicks to the app's widgets as Qt events, as the system would for a real mouse: to the widget
    under it, or while a button is held, to the one pressed, or to whichever has grabbed the mouse; with enter and
    leave events as it crosses from one widget to another. The real mouse is never touched"""

    def __init__(self, point: QPoint):
        self.pos = point
        self.held: QWidget | None = None
        self.under: list[QWidget] = []

    def windows(self) -> list[QWidget]:
        """The app's windows, bottom to top"""
        return stacked_windows()

    def widget_at(self, point: QPoint) -> QWidget | None:
        for window in reversed(self.windows()):
            if window.geometry().contains(point):
                child = window.childAt(window.mapFromGlobal(point))
                return child or window
        return None

    def _target(self) -> QWidget | None:
        if self.held is not None and not isValid(self.held):
            self.held = None
        return QWidget.mouseGrabber() or self.held or self.widget_at(self.pos)

    def _send(self, kind, widget: QWidget, button, buttons):
        local = QPointF(widget.mapFromGlobal(self.pos))
        QApplication.sendEvent(widget, QMouseEvent(kind, local, QPointF(self.pos), button, buttons, Qt.KeyboardModifier.NoModifier))

    def _hover(self):
        """Leave events for the widgets the pointer has left, enter events for those it has come onto"""
        widget = self.widget_at(self.pos)
        chain = []
        while widget is not None:
            chain.append(widget)
            widget = widget.parentWidget()
        # A panel docked back into the window is gone, and its widgets with it
        self.under = [widget for widget in self.under if isValid(widget)]
        for left in [widget for widget in self.under if widget not in chain]:
            QApplication.sendEvent(left, QEvent(QEvent.Type.Leave))
        for entered in reversed([widget for widget in chain if widget not in self.under]):
            local = QPointF(entered.mapFromGlobal(self.pos))
            QApplication.sendEvent(entered, QEnterEvent(local, local, QPointF(self.pos)))
        self.under = chain

    def move(self, point: QPoint):
        self.pos = point
        if self.held is None and QWidget.mouseGrabber() is None:
            self._hover()
        target = self._target()
        if target is not None:
            buttons = Qt.MouseButton.LeftButton if self.held is not None else Qt.MouseButton.NoButton
            self._send(QEvent.Type.MouseMove, target, Qt.MouseButton.NoButton, buttons)

    def press(self):
        target = self._target()
        if target is not None:
            self.held = target
            self._send(QEvent.Type.MouseButtonPress, target, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)

    def release(self):
        target = QWidget.mouseGrabber() or (self.held if self.held is not None and isValid(self.held) else None)
        self.held = None
        if target is not None:
            self._send(QEvent.Type.MouseButtonRelease, target, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        self._hover()


def stacked_windows() -> list[QWidget]:
    """The app's visible windows, bottom to top: the main window, its floating panels, then popups and menus"""
    others = [widget for widget in application.topLevelWidgets() if widget.isVisible() and widget is not app.window]
    panels = [widget for widget in others if isinstance(widget, FloatingPanel)]
    rest = [widget for widget in others if not isinstance(widget, FloatingPanel)]
    return ([app.window] if app.window.isVisible() else []) + panels + rest


pointer_device = Pointer(QPoint(area.left() + 520, area.bottom() - 120))
# The see-through panels follow the pretend pointer, not the real one
docking.QCursor = type("PretendCursor", (), {"pos": staticmethod(lambda: pointer_device.pos)})


def set_pointer(point: QPoint):
    pointer_device.move(point)


def mouse_button(down: bool):
    if down:
        pointer_device.press()
    elif pointer_device.held is not None:
        pointer_device.release()


# ----- Painting a frame from the app's own windows -----

ICON_FONT = QFont("Segoe Fluent Icons")
ICON_FONT.setPixelSize(10)
TITLE_FONT = QFont("Segoe UI")
TITLE_FONT.setPixelSize(12)


def paint_title_bar(painter: QPainter, window: QWidget):
    """The main window's title bar as Windows draws it in the dark: the icon, the name, and minimise, maximise (not
    available) and close at the right"""
    frame, inner = window.frameGeometry(), window.geometry()
    bar = QRect(frame.left(), frame.top(), frame.width(), inner.top() - frame.top())
    painter.fillRect(bar, QColor("#080808"))
    icon = window.windowIcon().pixmap(16, 16)
    painter.drawPixmap(bar.left() + 10, bar.center().y() - 7, icon)
    painter.setFont(TITLE_FONT)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRect(bar.left() + 34, bar.top(), 200, bar.height()), Qt.AlignmentFlag.AlignVCenter, window.windowTitle())
    painter.setFont(ICON_FONT)
    for index, (glyph, tone) in enumerate((("\ue8bb", "#ffffff"), ("\ue922", "#5c5c5c"), ("\ue921", "#ffffff"))):
        button = QRect(bar.right() + 1 - 46 * (index + 1), bar.top(), 46, bar.height())
        painter.setPen(QColor(tone))
        painter.drawText(button, Qt.AlignmentFlag.AlignCenter, glyph)


def paint_frame() -> QImage:
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB888)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    painter.translate(-area.x(), -area.y())
    for window in stacked_windows():
        painter.setOpacity(window.windowOpacity())
        if window is app.window:
            paint_title_bar(painter, window)
            frame = window.frameGeometry()
            painter.setPen(QColor("#2b2b2b"))
            painter.drawRect(frame.adjusted(0, 0, -1, -1))
        painter.drawPixmap(window.geometry().topLeft(), window.grab())
    painter.end()
    return image


ARROW = QPolygonF([QPointF(x, y) for x, y in ((0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12), (12.5, 12))])


def draw_pointer(image: QImage, point: QPoint, ripple: float | None):
    """The pointer, and a ring spreading from it just after a click"""
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    local = QPointF(point.x() - area.x(), point.y() - area.y())
    if ripple is not None:
        painter.setPen(QPen(QColor(255, 255, 255, round(150 * (1 - ripple))), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = 6 + 16 * ripple
        painter.drawEllipse(local, radius, radius)
    painter.translate(local)
    painter.setPen(QPen(QColor(0, 0, 0), 1.2))
    painter.setBrush(QColor(255, 255, 255))
    painter.drawPolygon(ARROW)
    painter.end()


ffmpeg = shutil.which("ffmpeg") or next(
    (str(path) for path in Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe")), None
)
if ffmpeg is None:
    sys.exit("FFmpeg is needed: winget install --id Gyan.FFmpeg -e --scope user")
raw = data / "reel.mp4"
encoder = subprocess.Popen(
    [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-",
     "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", str(raw)],
    stdin=subprocess.PIPE,
)

# Settle the window in place before the first frame
end = time.time() + 1.5
while time.time() < end:
    application.processEvents()
    time.sleep(0.02)
pointer = pointer_device.pos


def length(step) -> float:
    return step[-1] if step[0] in ("move", "wait") else 0.0


def begin(step):
    """Start a step: a click happens at once; a move sets off towards its target"""
    global start_point, target, ripple_start
    kind = step[0]
    if kind == "move":
        start_point, target = pointer, step[1]()
    elif kind in ("click", "press"):
        mouse_button(True)
        if kind == "click":
            mouse_button(False)
        ripple_start = now
    elif kind == "release":
        mouse_button(False)
    elif kind == "do":
        step[1]()


steps = iter(SCRIPT)
start_point = target = pointer
ripple_start = None
frame_index, now = 0, 0.0
step, step_start = next(steps), 0.0
begin(step)
start = time.perf_counter()
poster_saved = False
try:
    while step is not None:
        now = frame_index / FPS
        # Steps whose time has run out give way to the next
        while step is not None and now >= step_start + length(step):
            if step[0] == "move":
                pointer = target
                set_pointer(pointer)
            step_start += length(step)
            step = next(steps, None)
            if step is not None:
                begin(step)
        if step is not None and step[0] == "move":
            # Eased in and out, as a hand moves
            t = min(1.0, (now - step_start) / step[2])
            eased = t * t * (3 - 2 * t)
            pointer = QPoint(round(start_point.x() + (target.x() - start_point.x()) * eased),
                             round(start_point.y() + (target.y() - start_point.y()) * eased))
            set_pointer(pointer)
        # Real time passes between frames, so the app's own timers and animations run as they would
        while time.perf_counter() - start < now:
            application.processEvents()
            time.sleep(0.002)
        application.processEvents()
        image = paint_frame()
        if not poster_saved and now >= 0.5:
            image.save(str(out / "demo-reel-poster.png"))
            poster_saved = True
        ripple = (now - ripple_start) / 0.35 if ripple_start is not None and now - ripple_start < 0.35 else None
        draw_pointer(image, pointer, ripple)
        # Rows of exactly three bytes a pixel, as the width is a multiple of four, so the picture goes as it is
        encoder.stdin.write(bytes(image.constBits()))
        frame_index += 1
finally:
    mouse_button(False)

encoder.stdin.close()
encoder.wait()
# Faded in from black and out to black, so the loop joins without a jump; small enough for the web
duration = frame_index / FPS
subprocess.run(
    [ffmpeg, "-y", "-loglevel", "error", "-i", str(raw),
     "-vf", f"fade=t=in:st=0:d=0.4,fade=t=out:st={duration - 0.6:.2f}:d=0.6",
     "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
     str(out / "demo-reel.mp4")],
    check=True,
)
print(f"demo-reel.mp4: {duration:.1f} s, {(out / 'demo-reel.mp4').stat().st_size // 1024} KB")
sys.stdout.flush()
os._exit(0)
