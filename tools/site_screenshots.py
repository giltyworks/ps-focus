"""Capture the real app in landscape, title bar included, showing believable sample data, for the public download page

Nothing from the user's own history or account is used: the app runs against a throwaway data folder. A plain window
in the page's own black stands behind the app while it is captured, so nothing else on the screen can show in the
pictures, not even in the rounded corners.

Run as `py tools/site_screenshots.py [folder]` (the website's assets by default), then commit and push the site.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "assets"
out.mkdir(parents=True, exist_ok=True)
data = Path(tempfile.mkdtemp(prefix="psfocus-site-"))
# Before app_config is imported, which reads the data folder once
os.environ["PSFOCUS_DATA_DIR"] = str(data)
os.environ["QT_QPA_PLATFORM"] = "windows"
(data / "settings.json").write_text(
    '{"feedback_submitted": true, "show_graph": false, "show_calendar": true, "show_stats": true, "period": "Week", '
    '"panel_transparency": 0}',
    encoding="utf-8",
)

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget  # noqa: E402

import qt.app as qt_app  # noqa: E402
from qt.app import PSFocusQt  # noqa: E402
from sample_data import fill_sample_history  # noqa: E402

# No tray icon, update check, celebration or tip; Photoshop in front the whole time
PSFocusQt._start_tray_icon = lambda self: setattr(self, "tray_icon", QSystemTrayIcon())
PSFocusQt._celebrate_level_up = lambda self, level: None
qt_app.foreground_application = lambda: "Photoshop"
qt_app.user_is_active = lambda _seconds=300: True

application = QApplication(sys.argv)
backdrop = QWidget(None, Qt.WindowType.FramelessWindowHint)
backdrop.setStyleSheet("background: #000000;")
screen = application.primaryScreen().availableGeometry()
backdrop.setGeometry(screen)
backdrop.show()
app = PSFocusQt(application)
app._save_settings = lambda upload=True: None
app.tick_timer.stop()
app.focus_timer.stop()

fill_sample_history(app.store)


def settle(seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        application.processEvents()
        time.sleep(0.02)


def show(**modules):
    for name, visible in modules.items():
        if app.module_ticked[name] != visible:
            app.module_ticked[name] = visible
            app._module_toggled(name)
    app.module_controls.update()


def refresh():
    app._track_and_refresh()
    for name in ("graph", "calendar", "stats"):
        if app.module_ticked[name]:
            app._refresh_module(name)
    app._arrange_blocks()
    settle()


def frame(widget) -> QRect:
    """A window's frame as drawn, without Windows' invisible resize border"""
    if widget is app.window:
        left, top, right, bottom = app.docking.main_bounds()
        return QRect(left, top, right - left, bottom - top)
    return widget.frameGeometry()


def shoot(name, *windows):
    refresh()
    area = frame(windows[0])
    for window in windows[1:]:
        area = area.united(frame(window))
    image = application.primaryScreen().grabWindow(0, area.x(), area.y(), area.width(), area.height()).toImage()
    image.save(str(out / f"{name}.png"))
    print(f"{name}: {image.width()}x{image.height()}")


settle()
app.window.move(screen.x() + 400, screen.y() + 40)
app.window.raise_()
settle()
# The landscape orientation, the one view the website's demo leaves out: every module beside the program panel
show(calendar=True, stats=False, graph=True, friends=True)
# Made-up friends, next to the program panel as by default, since the capture signs in to nothing
from qt.friends_module import FriendsView  # noqa: E402

SAMPLE_FRIENDS = [
    ("Mia", {"two_weeks": 16.4, "today": 1.4, "total": 121.6, "level": 19}, "drawing", "Krita", "MIA00001", False),
    ("Leo", {"two_weeks": 10.2, "today": 0.6, "total": 71.3, "level": 14}, "online", None, "LEO00002", False),
    ("Ava", {"two_weeks": 6.8, "today": 0.0, "total": 47.9, "level": 11}, "away", None, "AVA00003", False),
    ("Noah", {"two_weeks": 3.1, "today": 0.0, "total": 28.4, "level": 8}, "offline", None, "NOAH0004", False),
]
app.friends_sync.view = lambda: FriendsView("on", "GILTY001", SAMPLE_FRIENDS)
app.friends_sync.refresh_view()
# Signed in, as Friends needs: a name in green with the status arrow beside it
header = app.header
header.account_text, header.account_font, header.account_color, header.status_arrow_shown = "gilty", app.fonts.account, "active_green", True
header.update()
app.docking.dock_all()
app.landscape = True
app.landscape_width = None
app._arrange_blocks()
app.window.move(screen.x() + 40, screen.y() + 40)
shoot("screenshot-landscape", app.window)
sys.stdout.flush()
os._exit(0)
