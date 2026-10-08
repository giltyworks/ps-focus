"""Capture the real app, title bar included, showing believable sample data, for the public download page

Nothing from the user's own history or account is used: the app runs against a throwaway data folder. A plain window
in the page's own black stands behind the app while it is captured, so nothing else on the screen can show in the
pictures, not even in the rounded corners.

Run as `py tools/site_screenshots.py [folder]` (the website's assets by default), then commit and push the site.
"""
import os
import random
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
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

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget  # noqa: E402

import qt.app as qt_app  # noqa: E402
from qt.app import PSFocusQt  # noqa: E402

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
app._save_settings = lambda: None
app.tick_timer.stop()

# Ten weeks of plausible drawing sessions: most weekdays, some weekends, an hour or three at a time
rng = random.Random(11)
today = date.today()
store = app.store
with store.connection:
    for days_ago in range(1, 71):
        day = today - timedelta(days=days_ago)
        if rng.random() < (0.45 if day.weekday() >= 5 else 0.2):
            continue
        start_hour = rng.choice((9, 10, 13, 14, 19, 20))
        minutes = rng.choice((35, 50, 75, 90, 110, 140, 170, 205))
        hour, remaining = start_hour, minutes * 60
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
    # Today so far: a session in progress
    for hour, seconds in ((9, 2900), (10, 3400), (11, 1750)):
        store.connection.execute(
            "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (today.isoformat(), hour, seconds)
        )
    store.connection.execute("INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', '09:10')", (today.isoformat(),))


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
# Last month is shown, as a full month of sessions says more than the first days of a new one
app.calendar._step(-1)
shoot("screenshot-calendar", app.window)
show(calendar=False, stats=False, graph=True)
app.chart._set_period("Month")
shoot("screenshot-graph", app.window)
# Floating panels: the calendar and stats taken out of the window and snapped beside it, one above the other
show(calendar=True, stats=True, graph=True)
app.docking.float_module("calendar", QPoint(0, 0))
app.docking.float_module("stats", QPoint(0, 0))
settle()
left, top, _right, _bottom = app.docking.main_bounds()
calendar_panel, stats_panel = app.docking.floating["calendar"], app.docking.floating["stats"]
calendar_panel.move(left - calendar_panel.width(), top)
stats_panel.move(left - stats_panel.width(), top + calendar_panel.height())
for panel in (calendar_panel, stats_panel):
    panel.raise_()
shoot("screenshot-floating", app.window, calendar_panel, stats_panel)
# The landscape orientation, every module back in the window beside the program panel
app.docking.dock_all()
app.landscape = True
app.landscape_width = None
app._arrange_blocks()
app.window.move(screen.x() + 40, screen.y() + 40)
shoot("screenshot-landscape", app.window)
sys.stdout.flush()
os._exit(0)
