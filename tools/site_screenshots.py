"""Capture the real app, title bar included, showing believable sample data, for the public download page

Nothing from the user's own history or account is used: the app runs against a throwaway data folder.
"""
import ctypes
import json
import random
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from datetime import date, timedelta
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app_config
import main

# The website folder's assets by default; run as `py tools/site_screenshots.py [folder]`, then commit and push the site
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "assets"
out.mkdir(parents=True, exist_ok=True)
data = Path(tempfile.mkdtemp(prefix="psfocus-site-"))
app_config.APP_DATA = data
app_config.LEGACY_APP_DATA = data / "legacy"
app_config.SETTINGS_PATH = data / "settings.json"
app_config.DATABASE_PATH = data / "activity.sqlite3"
app_config.BACKUP_DIRECTORIES = (data / "backups",)
app_config.SETTINGS_PATH.write_text(json.dumps({"feedback_submitted": True, "show_calendar": True, "show_stats": True, "period": "Week"}), encoding="utf-8")
main.PSFocusApp._start_tray_icon = lambda self: None
main.PSFocusApp._check_for_updates = lambda self: None
main.PSFocusApp._celebrate_level_up = lambda self, level: None
foreground = {"app": "Photoshop"}
main.foreground_application = lambda: foreground["app"]
main.user_is_active = lambda _seconds=300: True

root = tk.Tk()
app = main.PSFocusApp(root)
app._save_settings = lambda: None

# Ten weeks of plausible drawing sessions: most weekdays, some weekends, an hour or three at a time
rng = random.Random(11)
today = date.today()
with app.store.connection:
    for days_ago in range(1, 71):
        day = today - timedelta(days=days_ago)
        if rng.random() < (0.45 if day.weekday() >= 5 else 0.2):
            continue
        start_hour = rng.choice((9, 10, 13, 14, 19, 20))
        minutes = rng.choice((35, 50, 75, 90, 110, 140, 170, 205))
        hour, remaining = start_hour, minutes * 60
        while remaining > 0 and hour < 24:
            seconds = min(remaining, rng.randint(2400, 3600))
            app.store.connection.execute(
                "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (day.isoformat(), hour, seconds)
            )
            remaining -= seconds
            hour += 1
        app.store.connection.execute(
            "INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', ?)",
            (day.isoformat(), f"{start_hour:02d}:{rng.choice((5, 10, 20, 30, 40)):02d}"),
        )
        if rng.random() < 0.4:
            app.store.connection.execute("INSERT OR REPLACE INTO productivity_ratings (day, rating) VALUES (?, ?)", (day.isoformat(), rng.randint(5, 9)))
    # Today so far: a session in progress
    for hour, seconds in ((9, 2900), (10, 3400), (11, 1750)):
        app.store.connection.execute(
            "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (today.isoformat(), hour, seconds)
        )
    app.store.connection.execute("INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', '09:10')", (today.isoformat(),))


def settle(seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def show(**modules):
    for name, visible in modules.items():
        if app.module_vars[name].get() != visible:
            app.module_vars[name].set(visible)
            app._toggle_module(name)


def shoot(name):
    app._track_and_refresh()
    app.calendar_visual_state = None
    app._calendar_period_changed()
    app._draw_chart()
    app._resize_to_content(fit=True)
    settle()
    handle = ctypes.windll.user32.GetAncestor(ctypes.c_void_p(root.winfo_id()), 2)
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(handle), 9, ctypes.byref(rect), ctypes.sizeof(rect))
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).convert("RGB")
    image.save(out / f"{name}.png", optimize=True)
    print(f"{name}: {image.width}x{image.height}")


settle()
root.geometry("+300+60")
root.attributes("-topmost", True)
settle()
# Last month is shown, as a full month of sessions says more than the first days of a new one
app._shift_calendar_month(-1)
shoot("screenshot-calendar")
show(calendar=False, stats=False, graph=True)
app._set_period("Month")
shoot("screenshot-graph")
# The landscape orientation, every module open beside the program panel
show(calendar=True, stats=True, graph=True)
app._set_orientation(True)
shoot("screenshot-landscape")
root.destroy()
