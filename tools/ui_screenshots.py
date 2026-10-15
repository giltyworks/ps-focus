"""Draw each block and the main window offscreen from made-up data and save them as PNG pictures, so a change to the
look can be seen before and after without opening the app

    py tools/ui_screenshots.py before     pictures go in screenshots/before/
    py tools/ui_screenshots.py after      pictures go in screenshots/after/, plus screenshots/compare/ with each
                                          picture beside its "before" one
    --out FOLDER   keep the pictures somewhere else (the folder holding before/, after/ and compare/)
    --scale 1.5    draw as a scaled Windows display would; 1 by default

The app runs against a throwaway data folder with the same sample history as the website pictures
(tools/sample_data.py), never the real data, and the script stops if the data folder is not that throwaway one.

How these differ from the real app:
- No Windows frame: no window shadow, rounded corners or border, only what the app paints itself
- Panel transparency shows against a plain background, not the desktop behind
- Text smoothing and emoji can differ a little, as offscreen Qt does not use Windows' own text drawing
- Drawn at 100% unless --scale is given, where a real screen is often 125% or 150%
- A still picture: no hovering, clicking, animation or live ticking
- Made-up numbers and friends; today is still the real date, so calendar pictures change from day to day
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# The names the pictures are saved under, which the test checks for
PICTURE_NAMES = ("today", "chart", "calendar", "stats", "friends", "main-portrait", "main-landscape")
COMPARE_MARGIN = 16
COMPARE_LABEL_HEIGHT = 28
COMPARE_BACKGROUND = "#303030"
COMPARE_TEXT = "#f0f0f0"
SETTLE_SECONDS = 0.4


def read_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=("before", "after"))
    parser.add_argument("--out", type=Path, default=ROOT / "screenshots")
    parser.add_argument("--scale", type=float, default=1.0)
    return parser.parse_args(argv)


def main(argv: list[str]) -> None:
    arguments = read_arguments(argv)
    data = Path(tempfile.mkdtemp(prefix="psfocus-shots-"))
    # Before app_config is imported, which reads the data folder once
    os.environ["PSFOCUS_DATA_DIR"] = str(data)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # Offscreen Qt knows no fonts of its own, so every letter would come out as an empty box; Windows' own folder fixes it
    os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"))
    if arguments.scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(arguments.scale)
    (data / "settings.json").write_text(
        '{"feedback_submitted": true, "show_graph": true, "show_calendar": true, "show_stats": true, "show_friends": true, '
        '"period": "Week", "panel_transparency": 0, "today_program": "Photoshop"}',
        encoding="utf-8",
    )

    import app_config

    for path in (app_config.APP_DATA, app_config.DATABASE_PATH, app_config.SETTINGS_PATH, *app_config.BACKUP_DIRECTORIES):
        if not Path(path).resolve().is_relative_to(data.resolve()):
            raise SystemExit(f"Refusing to run: {path} is outside the throwaway data folder")

    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    import qt.app as qt_app
    import qt.window
    from qt.app import PSFocusQt
    from sample_data import fill_sample_history

    # No tray icon, update check, celebration or window placement; Photoshop in front the whole time
    PSFocusQt._start_tray_icon = lambda self: setattr(self, "tray_icon", QSystemTrayIcon())
    PSFocusQt._check_for_updates = lambda self: None
    PSFocusQt._celebrate_level_up = lambda self, level: None
    qt.window.MainWindow.place_top_right = lambda self: None
    qt_app.foreground_application = lambda: "Photoshop"
    qt_app.user_is_active = lambda _seconds=300: True

    application = QApplication.instance() or QApplication([])
    app = PSFocusQt(application)
    app._save_settings = lambda upload=True: None
    for timer in (app.tick_timer, app.focus_timer, app.poll_timer, app.backup_timer):
        timer.stop()
    fill_sample_history(app.store)

    def settle() -> None:
        end = time.time() + SETTLE_SECONDS
        while time.time() < end:
            application.processEvents()
            time.sleep(0.02)

    def refresh() -> None:
        app._track_and_refresh()
        for name in ("graph", "calendar", "stats"):
            if app.module_ticked[name]:
                app._refresh_module(name)
        app._arrange_blocks()
        settle()

    for name, visible in {"graph": True, "calendar": True, "stats": True, "friends": True}.items():
        if not app.module_ticked[name]:
            app.module_ticked[name] = True
            app._module_toggled(name)
    # Made-up friends, shown on their own while signed out, and the header as it looks signed in
    app.friends_sync.sample_friends = True
    app.friends_sync.refresh_view()
    header = app.header
    header.account_text, header.account_font, header.account_color, header.status_arrow_shown = "gilty", app.fonts.account, "active_green", True
    header.update()
    app.docking.dock_all()
    app.window.show()

    folder = arguments.out / arguments.mode
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)

    def save(name: str, widget) -> None:
        image = widget.grab().toImage()
        image.save(str(folder / f"{name}.png"))
        print(f"{name}.png: {image.width()}x{image.height()}")

    app.landscape = False
    refresh()
    for name, widget in (("today", app.today), ("chart", app.chart), ("calendar", app.calendar), ("stats", app.stats), ("friends", app.friends)):
        save(name, widget)
    save("main-portrait", app.window)
    app.landscape = True
    app.landscape_width = None
    refresh()
    save("main-landscape", app.window)

    if arguments.mode == "after":
        write_comparisons(arguments.out, QImage, QPainter, QColor)

    app.store.close()
    shutil.rmtree(data, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)


def write_comparisons(out: Path, QImage, QPainter, QColor) -> None:
    """Each picture in after/ that also exists in before/, drawn side by side with a label over each"""
    compare = out / "compare"
    shutil.rmtree(compare, ignore_errors=True)
    compare.mkdir(parents=True)
    for name in PICTURE_NAMES:
        before = QImage(str(out / "before" / f"{name}.png"))
        after = QImage(str(out / "after" / f"{name}.png"))
        if before.isNull() or after.isNull():
            continue
        width = COMPARE_MARGIN * 3 + before.width() + after.width()
        height = COMPARE_MARGIN * 2 + COMPARE_LABEL_HEIGHT + max(before.height(), after.height())
        canvas = QImage(width, height, QImage.Format.Format_ARGB32)
        canvas.fill(QColor(COMPARE_BACKGROUND))
        painter = QPainter(canvas)
        painter.setPen(QColor(COMPARE_TEXT))
        top = COMPARE_MARGIN + COMPARE_LABEL_HEIGHT
        painter.drawText(COMPARE_MARGIN, COMPARE_MARGIN + 18, "before")
        painter.drawImage(COMPARE_MARGIN, top, before)
        left = COMPARE_MARGIN * 2 + before.width()
        painter.drawText(left, COMPARE_MARGIN + 18, "after")
        painter.drawImage(left, top, after)
        painter.end()
        canvas.save(str(compare / f"{name}.png"))
        print(f"compare/{name}.png: {width}x{height}")


if __name__ == "__main__":
    main(sys.argv[1:])
