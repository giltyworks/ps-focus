"""Record the website's demo reel: the real app in use, with believable sample data, as a short silent loop

Nothing from the user's own history or account is used: the app runs against a throwaway data folder, a made-up Google
account and a stand-in friends server. Nothing outside the app can get in either: the real mouse is never moved or
clicked, a pretend pointer handing its moves and clicks to the app's own widgets as events; and the screen is never
captured, each frame being painted from the app's own windows alone, over a plain
drawing of an art app's workspace with a painting on its canvas. The
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
    ' "period": "Week", "panel_transparency": 45, "disable_fanfare_sound": true, "google_display_names": {"demo@example.com": "gilty"}}',
    encoding="utf-8",
)

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QEnterEvent, QFont, QImage, QLinearGradient, QMouseEvent, QPainter, QPen, QPolygonF, QRadialGradient  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget  # noqa: E402
from shiboken6 import isValid  # noqa: E402

import google_drive  # noqa: E402
import qt.app as qt_app  # noqa: E402
from qt.app import PSFocusQt  # noqa: E402
from qt import docking, friends_sync  # noqa: E402
from qt.docking import FloatingPanel  # noqa: E402

FPS = 30
# Room for the window, a panel pulled out beside it, and landscape
WIDTH, HEIGHT = 720, 640


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
FOREGROUND = ["Photoshop"]
patches = [
    patch.object(PSFocusQt, "_start_tray_icon", lambda self: setattr(self, "tray_icon", QSystemTrayIcon())),
    patch.object(PSFocusQt, "_check_for_updates", lambda self: None),
    # Photoshop in front, until the script steps away from it
    patch.object(qt_app, "foreground_application", lambda: FOREGROUND[0]),
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
app.window.move(area.x() + 36, area.y() + 28)

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






def request_accept() -> QPoint:
    """Accept, on the request in the friends module's list of requests"""
    module = app.friends
    button = next(button for button in module.buttons if button.text == "Accept")
    return button_at(module, button)


def requests_icon() -> QPoint:
    return app.friends.mapToGlobal(app.friends.strip_controls()["requests"].center())






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


# What is said under each scene, and whether the pointer shows
caption = {"text": None, "since": 0.0}
pointer_shown = [False]


def say(text):
    return do(lambda: caption.update(text=text, since=NOW[0]))


def pointer(shown: bool):
    return do(lambda: pointer_shown.__setitem__(0, shown))


def step_away():
    FOREGROUND[0] = None


def come_back():
    FOREGROUND[0] = "Photoshop"


def show_modules(**modules):
    for name, visible in modules.items():
        if app.module_ticked[name] != visible:
            app.module_ticked[name] = visible
            app._module_toggled(name)
    app.module_controls.update()


def level_up():
    """Earlier hours enough to reach the next level, which the next tick notices and celebrates"""
    from app_config import LEVEL_HOURS, user_level

    store = app.store
    level = user_level(store.total_seconds())
    needed = LEVEL_HOURS[level] * 3600 - store.total_seconds() + 60
    day = (date.today() - timedelta(days=80)).isoformat()
    with store.connection:
        for slot in range(24):
            if needed <= 0:
                break
            seconds = min(3600, needed)
            store.connection.execute("INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (day, slot, seconds))
            needed -= seconds


def to_friends():
    app.docking.dock_all()
    show_modules(calendar=False, graph=False, friends=True)


def to_landscape():
    app._set_orientation(True)
    app._arrange_blocks()


def beside_window() -> QPoint:
    """Where the calendar's title goes for its panel to snap to the window's right edge, level with its top"""
    _left, top, right, _bottom = app.docking.main_bounds()
    return QPoint(right + 4 + 70, top + 14)


SCRIPT = [
    # It counts by itself while you draw, and stops when you stop
    say("Counts your drawing time by itself"), wait(2.4),
    do(step_away), say("and stops when you step away"), wait(1.8),
    do(come_back), wait(0.4),
    # Your habits at a glance
    say("See your habits at a glance"), pointer(True),
    move(lambda: period_button("1M"), 0.6), click(), wait(1.3),
    pointer(False), do(lambda: show_modules(graph=False, calendar=True)), wait(1.8),
    # Every hour counts towards a level
    say("Level up as the hours add up"), do(level_up), wait(2.8),
    # Beside your canvas, and out of the way
    say("Pull panels out beside your canvas"), pointer(True),
    move(lambda: title_of("calendar"), 0.5), press(),
    move(beside_window, 0.8), release(), wait(0.3),
    say("They fade while you draw"), move(lambda: QPoint(area.left() + 520, area.bottom() - 60), 0.5), wait(1.6),
    # Friends
    pointer(False), do(to_friends), say("Draw alongside your friends"), wait(1.0),
    do(request_arrives), wait(0.8), pointer(True),
    move(requests_icon, 0.6), click(), wait(0.4),
    move(request_accept, 0.5), click(), wait(1.4),
    # Or a slim strip, and where to get it
    pointer(False), do(to_landscape), say("Or keep it as a slim strip"), wait(1.9),
    say("Free for Windows"), wait(1.8),
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



def paint_workspace() -> QImage:
    """An art app's workspace, plain and unbranded: grey, with a painting on the canvas to the right, which the
    see-through panels show through"""
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB888)
    image.fill(QColor("#1e1e1e"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    canvas = QRect(372, 28, 320, 512)
    painter.fillRect(canvas.adjusted(-1, -1, 1, 1), QColor("#111111"))
    # A sunset over hills: the sky, the sun, three ridges, and a few strokes of light on the water
    sky = QLinearGradient(QPointF(canvas.topLeft()), QPointF(canvas.left(), canvas.top() + 300))
    for stop, tone in ((0.0, "#2b1e5c"), (0.45, "#b24a7a"), (0.8, "#f08a4b"), (1.0, "#ffc76b")):
        sky.setColorAt(stop, QColor(tone))
    painter.fillRect(canvas, sky)
    painter.setPen(Qt.PenStyle.NoPen)
    sun = QRadialGradient(QPointF(canvas.left() + 205, canvas.top() + 270), 70)
    sun.setColorAt(0.0, QColor(255, 236, 170, 255))
    sun.setColorAt(0.45, QColor(255, 200, 120, 230))
    sun.setColorAt(1.0, QColor(255, 160, 90, 0))
    painter.setBrush(sun)
    painter.drawEllipse(QPointF(canvas.left() + 205, canvas.top() + 270), 70, 70)
    for depth, tone, heights in (
        (300, "#6b3a6e", (40, 10, 55, 25, 60, 20)),
        (340, "#43275a", (20, 50, 15, 45, 10, 35)),
        (390, "#24183d", (35, 15, 45, 5, 40, 20)),
    ):
        ridge = QPolygonF([QPointF(canvas.left(), canvas.bottom() + 1)])
        for index, height in enumerate(heights):
            ridge.append(QPointF(canvas.left() + index * canvas.width() / (len(heights) - 1), canvas.top() + depth - height))
        ridge.append(QPointF(canvas.right() + 1, canvas.bottom() + 1))
        painter.setBrush(QColor(tone))
        painter.drawPolygon(ridge)
    painter.setBrush(QColor("#141026"))
    painter.drawRect(QRect(canvas.left(), canvas.top() + 420, canvas.width(), canvas.height() - 420))
    painter.setPen(QPen(QColor(255, 190, 120, 150), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for y, x1, x2 in ((440, 150, 260), (458, 170, 240), (476, 185, 225), (494, 195, 215)):
        painter.drawLine(QPointF(canvas.left() + x1, canvas.top() + y), QPointF(canvas.left() + x2, canvas.top() + y))
    painter.end()
    return image


WORKSPACE = paint_workspace()


def paint_frame() -> QImage:
    image = WORKSPACE.copy()
    painter = QPainter(image)
    painter.translate(-area.x(), -area.y())
    for window in stacked_windows():
        painter.setOpacity(window.windowOpacity())
        painter.drawPixmap(window.geometry().topLeft(), window.grab())
    painter.end()
    return image


NOW = [0.0]
CAPTION_FONT = QFont("Segoe UI Semibold")
CAPTION_FONT.setPixelSize(22)


def draw_caption(image: QImage, now: float):
    """The scene's caption, centred under the window, fading in as it changes"""
    text = caption["text"]
    if not text:
        return
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(CAPTION_FONT)
    painter.setOpacity(min(1.0, (now - caption["since"]) / 0.25))
    painter.setPen(QColor("#eef3f1"))
    painter.drawText(QRect(0, HEIGHT - 64, WIDTH, 40), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()


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
        NOW[0] = now
        image = paint_frame()
        if not poster_saved and now >= 0.5:
            image.save(str(out / "demo-reel-poster.png"))
            poster_saved = True
        ripple = (now - ripple_start) / 0.35 if ripple_start is not None and now - ripple_start < 0.35 else None
        if pointer_shown[0]:
            draw_pointer(image, pointer, ripple)
        draw_caption(image, now)
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
