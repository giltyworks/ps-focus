"""Paths, constants, colours, and default settings shared across PS Focus"""

from __future__ import annotations

import bisect
import json
import math
import os
import sys
from datetime import timedelta
from pathlib import Path


APP_NAME = "PS Focus"
# Raise for every published build; the installer, the executable's file properties, and the update check all use it
APP_VERSION = "1.1.27"
APP_PUBLISHER = "Giltyworks"
APP_USER_MODEL_ID = "PSFocus.PSFocus"
LEGACY_APP_NAME = "FocusTrace"
APP_DATA_ROOT = Path(os.environ.get("APPDATA", Path.home()))
# A folder to keep everything in instead of the usual one, so a test copy of the app never touches the real history
DATA_DIRECTORY_OVERRIDE = os.environ.get("PSFOCUS_DATA_DIR")
APP_DATA = Path(DATA_DIRECTORY_OVERRIDE) if DATA_DIRECTORY_OVERRIDE else APP_DATA_ROOT / APP_NAME
LEGACY_APP_DATA = APP_DATA_ROOT / LEGACY_APP_NAME
SETTINGS_PATH = APP_DATA / "settings.json"
DATABASE_PATH = APP_DATA / "activity.sqlite3"
_backup_directories = [
    APP_DATA / "backups",
    Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "PS Focus Backups",
]
if DATA_DIRECTORY_OVERRIDE:
    _backup_directories = [APP_DATA / "backups"]
elif os.environ.get("OneDrive"):
    _backup_directories.append(Path(os.environ["OneDrive"]) / "PS Focus Backups")
BACKUP_DIRECTORIES = tuple(dict.fromkeys(path.resolve() for path in _backup_directories))
BACKUP_INTERVAL_MS = 15 * 60 * 1000
# The window is laid out compactly. Its boxes, the program panels and the modules, run from one edge of
# the window to the other, and a module's contents run from one side of its box to the other.
# All measurements are in pixels.
# Width of the window and so of every box, and the space kept around the window's contents
TODAY_PANEL_WIDTH = 300
WINDOW_MARGIN = 0
# Space between an edge of the window, or of a box, and the text beside it
EDGE_PADDING = 8
# Space inside a module beside its title, and beside its contents, which draw their own padding
MODULE_MARGIN = EDGE_PADDING
MODULE_CONTENT_MARGIN = 0
# Width a module's contents ask for: what is left inside its box. Asked for, so that modules side by side
# in the landscape layout keep the same width as when they are stacked
MODULE_CANVAS_WIDTH = TODAY_PANEL_WIDTH - 2 - 2 * MODULE_CONTENT_MARGIN
# Space below each program panel and above each module
PANEL_GAP = 4
MODULE_GAP = 4
# Space above and below a line of text in the closely packed rows
LINE_PADDING = 2
# Space left under the checkbox row when the window is at its smallest, and when no module is open
COMPACT_BOTTOM_SPACE = 4
# Sizes, in points, of the day's big time figure and of the program names and calendar title,
# and the height of the graph
METRIC_FONT_SIZE = 30
HEADING_FONT_SIZE = 12
CHART_HEIGHT = 210
IDLE_TIMEOUT_SECONDS = 300
# Tracked time in a day that makes it a session, a blue calendar day, and lights the header indicator
SESSION_MINIMUM_SECONDS = 15 * 60
ROLLING_AVERAGE_DAYS = 7
MONTHLY_AVERAGE_DAYS = 30
# Longest unobserved gap one tick may count; longer UI stalls cannot prove continuous foreground activity
MAX_TICK_CREDIT_SECONDS = 2.0
# Cumulative tracked hours needed to reach a level; the levels in between are interpolated, see LEVEL_HOURS.
# The curve is fixed here in code and is never read from settings, so it cannot be changed from a settings file
LEVEL_ANCHORS = (
    (1, 0),
    (10, 40),
    (25, 180),
    (50, 650),
    (75, 1350),
    (80, 1790),
    (85, 2345),
    (90, 3010),
    (92, 3340),
    (95, 3895),
    (97, 4390),
    (98, 4670),
    (99, 5000),
)
LEVEL_CAP = LEVEL_ANCHORS[-1][0]
LEVEL_BADGE_SIZE = 26
LEVEL_BLUR_RADIUS = 2.2
LEVEL_BLUR_OPACITY = 0.8
CHART_FILL_OPACITY = 0.45
CHART_PERIODS = ("Day", "Week", "Month", "3 Months", "6 Months", "1 Year")
CHART_PERIOD_CAPTIONS = {
    "Day": "Today",
    "Week": "This week",
    "Month": "Past 30 days",
    "3 Months": "Past 90 days",
    "6 Months": "Past 180 days",
}
# The programs PS Focus counts time in, every one always; the one panel shows whichever is in front
PROGRAMS = ("Photoshop", "Krita", "Clip Studio Paint", "PhotoCraft")
COLORS = {
    # A near-black background, the logo's own, under panels only a little lighter, so the two do not contrast
    # harshly; the title bar takes the background colour too
    "background": "#080808",
    "panel": "#0c0c0c",
    "panel_alt": "#151515",
    "border": "#222222",
    "text": "#eef3f1",
    "muted": "#8d9a98",
    "accent": "#79d6bd",
    "accent_dark": "#284e45",
    "active_green": "#22c55e",
    # Session days, checkboxes, the graph, and the progress dot. A royal blue (hue 229°) rather than the
    # earlier #3478c9, which leaned towards green; white day numbers on it read at 4.8:1
    "calendar_blue": "#3d5ce6",
    "calendar_cell": "#151515",
    # The empty places before the 1st: between the panel and a day's cell, so they read as part of the month
    "calendar_blank": "#101010",
    "orange": "#efad71",
    "gold": "#f0c33c",
    "silver": "#c3cbd1",
    "bronze": "#d0874a",
    "red": "#e07e75",
    # The boxes of the Accept and Decline buttons of friend requests
    "accept_fill": "#1b4a2d",
    "decline_fill": "#5a211d",
    # The badge counting friend requests waiting, as a phone's notification badge
    "notification": "#e5484d",
    # A friend's name while they are online: the app's blue, lightened to read on the dark panel
    "friend_online": "#7d95f5",
    # A friend away: the same blue, dimmed towards the panel, as Steam dims its away friends
    "friend_away": "#56659f",
    # Names, a lighter shade of the colour of the line under them, so a name reads first, as Steam does: drawing,
    # online, away and offline
    "name_drawing": "#86e3a6",
    "name_online": "#aebdfa",
    "name_away": "#8993bc",
    "name_offline": "#b0b9b7",
}
DEFAULT_SETTINGS = {
    "tracking_paused": False,
    "launch_on_startup": True,
    "start_minimized": True,
    "disable_fanfare_sound": False,
    "always_on_top": False,
    "show_graph": False,
    "show_calendar": False,
    "show_stats": False,
    "show_friends": False,
    # online, away, invisible or offline, chosen in the menu next to the account name
    "friends_status": "online",
    # Program panels and modules side by side instead of one under another, see PSFocusQt._arrange_blocks
    "landscape": False,
    # The program the panel last showed, kept while none of them is in front
    "today_program": "Photoshop",
    "period": "Day",
    # Names chosen for each Google account, keyed by its email; google_display_name is the single name of earlier versions
    "google_display_names": {},
    "google_display_name": "",
    "feedback_submitted": False,
    "feedback_count": 0,
    "feedback_cooldown_until": "",
    # How see-through the window and floating panels are while the mouse is elsewhere, from 0 (solid) to 100, see
    # qt/docking.py. A new install starts solid; see-through is the user's choice, from the transparency icon
    "panel_transparency": 0,
}
FEEDBACK_COOLDOWN = timedelta(minutes=30)
FEEDBACK_UNLOCK_SECONDS = 2 * 60 * 60
FEEDBACK_PLACEHOLDER = "Write your feedback and submit it. All suggestions are read personally by me :)"
FEEDBACK_PLACEHOLDER_PROMPT = "Want a feature added?\n"


def resource_path(relative_path: str) -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / relative_path


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()
    # A file that holds valid JSON but not a set of settings, such as a list, is treated like a damaged one
    if not isinstance(data, dict):
        return DEFAULT_SETTINGS.copy()
    return {**DEFAULT_SETTINGS, **data}


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _level_thresholds() -> list[float]:
    """Return the cumulative hours needed for each level, indexed by level - 1

    Levels between the anchors follow a monotonic cubic (PCHIP) curve through them, so the hours rise smoothly
    and never dip
    """
    levels = [level for level, _hours in LEVEL_ANCHORS]
    hours = [float(anchor_hours) for _level, anchor_hours in LEVEL_ANCHORS]
    widths = [levels[index + 1] - levels[index] for index in range(len(levels) - 1)]
    slopes = [(hours[index + 1] - hours[index]) / widths[index] for index in range(len(widths))]

    def end_tangent(width: float, next_width: float, slope: float, next_slope: float) -> float:
        tangent = ((2 * width + next_width) * slope - width * next_slope) / (width + next_width)
        if tangent * slope <= 0:
            return 0.0
        if slope * next_slope <= 0 and abs(tangent) > 3 * abs(slope):
            return 3 * slope
        return tangent

    tangents = [end_tangent(widths[0], widths[1], slopes[0], slopes[1])]
    for index in range(1, len(levels) - 1):
        before, after = slopes[index - 1], slopes[index]
        if before * after <= 0:
            tangents.append(0.0)
        else:
            weight_before = 2 * widths[index] + widths[index - 1]
            weight_after = widths[index] + 2 * widths[index - 1]
            tangents.append((weight_before + weight_after) / (weight_before / before + weight_after / after))
    tangents.append(end_tangent(widths[-1], widths[-2], slopes[-1], slopes[-2]))

    thresholds = []
    for index, width in enumerate(widths):
        for level in range(levels[index], levels[index + 1]):
            t = (level - levels[index]) / width
            thresholds.append(
                (2 * t**3 - 3 * t**2 + 1) * hours[index]
                + (t**3 - 2 * t**2 + t) * width * tangents[index]
                + (-2 * t**3 + 3 * t**2) * hours[index + 1]
                + (t**3 - t**2) * width * tangents[index + 1]
            )
    thresholds.append(hours[-1])
    return thresholds


LEVEL_HOURS = tuple(_level_thresholds())


def user_level(total_seconds: float) -> int:
    hours = max(0.0, total_seconds) / 3600
    return bisect.bisect_right(LEVEL_HOURS, hours)


def level_xp_text(total_seconds: float) -> str:
    """What the level shows on hover, as RuneScape does, with one XP for each second tracked: the XP the next level
    starts at and how much is still to earn under the total, which shows alone once the last level is reached. A table,
    so the numbers line up at the right"""
    xp = int(max(0.0, total_seconds))
    rows = [("Total XP:", xp)]
    level = user_level(total_seconds)
    if level < LEVEL_CAP:
        # Rounded up, as the level only rises once the exact threshold is reached
        next_xp = math.ceil(LEVEL_HOURS[level] * 3600)
        rows += [("Next level at:", next_xp), ("Remaining XP:", max(0, next_xp - xp))]
    cells = "".join(f"<tr><td>{label}</td><td align='right' style='padding-left: 12px'>{value:,}</td></tr>" for label, value in rows)
    return f"<table cellspacing='0' cellpadding='0'>{cells}</table>"
