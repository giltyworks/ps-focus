"""Preview the level-up celebrations by stepping PS Focus through its first levels

The app runs against a throwaway data folder, so real settings, history, backups, and the Windows startup entry
are never touched. Tracked hours are raised to each level's threshold in turn, and the app reacts exactly as it
would when that level is reached for real.

Run with: py tools/simulate_level_ups.py [number of level-ups, default 15]
"""

from __future__ import annotations

import json
import sys
import tempfile
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app_config  # noqa: E402
import main  # noqa: E402

SECONDS_BETWEEN_LEVELS = 4.0
SECONDS_BEFORE_FIRST = 2.5
SECONDS_AFTER_LAST = 3.5


def run(level_ups: int) -> None:
    data = Path(tempfile.mkdtemp(prefix="psfocus-simulation-"))
    app_config.APP_DATA = data
    app_config.LEGACY_APP_DATA = data / "legacy"
    app_config.SETTINGS_PATH = data / "settings.json"
    app_config.DATABASE_PATH = data / "activity.sqlite3"
    app_config.BACKUP_DIRECTORIES = (data / "backups",)
    # Feedback is marked as given so the level number is shown rather than blurred
    app_config.SETTINGS_PATH.write_text(json.dumps({"feedback_submitted": True}), encoding="utf-8")
    main.PSFocusApp._start_tray_icon = lambda self: None
    main.foreground_application = lambda: None

    root = tk.Tk()
    app = main.PSFocusApp(root)
    if app.store.database_path.parent != data or app.google.token_file.parent != data:
        raise SystemExit("The simulation is not isolated from real PS Focus data, so it has stopped")
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.update_idletasks()
    # Placed away from the corner the real app opens in, so the two windows are not mistaken for each other
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry(f"+{x}+{y}")
    root.title("PS Focus simulation")
    root.attributes("-topmost", True)

    def reach(level: int) -> None:
        if level > level_ups + 1:
            root.after(int(SECONDS_AFTER_LAST * 1000), root.destroy)
            return
        hours = app_config.LEVEL_HOURS[level - 1]
        with app.store.connection:
            app.store.connection.execute("DELETE FROM activity")
            app.store.connection.execute(
                "INSERT INTO activity (day, slot, seconds, application) VALUES ('2026-01-01', 9, ?, 'Photoshop')",
                (hours * 3600,),
            )
        app._track_and_refresh()
        root.title(f"PS Focus simulation · level {level} at {hours:.1f} h tracked")
        print(f"Level {level} reached at {hours:.1f} hours tracked", flush=True)
        root.after(int(SECONDS_BETWEEN_LEVELS * 1000), reach, level + 1)

    print("Starting at level 1 with 0 hours tracked", flush=True)
    root.after(int(SECONDS_BEFORE_FIRST * 1000), reach, 2)
    root.mainloop()


if __name__ == "__main__":
    run(min(app_config.LEVEL_CAP - 1, int(sys.argv[1])) if len(sys.argv) > 1 else 15)
