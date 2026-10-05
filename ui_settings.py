"""Settings page and saving of preferences"""

from __future__ import annotations

import json
import threading
import tkinter as tk

import app_config
from app_config import (
    COLORS,
    COMPACT_BOTTOM_SPACE,
    DEFAULT_SETTINGS,
    EDGE_PADDING,
    PANEL_GAP,
    TODAY_PANEL_WIDTH,
    PROGRAM_PANEL_SETTINGS,
)
from rendering import render_rounded_box, to_photo_image
from windows_startup import set_startup

# The page follows the overview's layout: boxes run from one edge of the window to the other with PANEL_GAP
# between them, text starts EDGE_PADDING from the edge, and labels carry no padding of their own.
# Widths text wraps at: on the page and inside a box, and beside a toggle's checkbox
PAGE_TEXT_WIDTH = TODAY_PANEL_WIDTH - 2 * EDGE_PADDING
TOGGLE_TEXT_WIDTH = PAGE_TEXT_WIDTH - 40
# Space above and below the contents of a box, matching a module's title bar
BOX_PADDING = 5
# The orientation choice's shapes: their long and short sides, corner radius, and the space between them
ORIENTATION_ICON_SIZE = (26, 18)
ORIENTATION_ICON_RADIUS = 4
ORIENTATION_ICON_GAP = 10
# The backups box holds several short paragraphs, so it is given more room: above its first line and below
# its buttons, and between one paragraph and the next
BACKUP_BOX_PADDING = 9
BACKUP_LINE_GAP = 7
# Space between a checkbox's name and its box, and between one checkbox and the next in a row,
# both matching the module checkboxes on the overview
CHECKBOX_LABEL_GAP = 6
CHECKBOX_GAP = 8
CHECKBOX_SIZE = 18
# Space above the page title, between it and the description, and between the description and the
# checkboxes that follow. This opening text is given more room than the rest of the page so it reads easily
TITLE_PADDING = 8
TITLE_GAP = 6
DESCRIPTION_GAP = 14


class SettingsMixin:
    def _settings_text(self, parent: tk.Widget, text: str, color: str, font, wraplength: int = 0) -> tk.Label:
        """A label with no border or padding of its own, so its text starts exactly where it is placed"""
        return tk.Label(
            parent, text=text, bg=parent.cget("bg"), fg=COLORS[color], font=font, wraplength=wraplength, justify="left", bd=0, padx=0, pady=0
        )

    def _build_settings(self) -> None:
        page = self.settings_page
        self._build_settings_title(page)
        self._settings_text(
            page,
            "PS Focus counts time in Photoshop, Krita and CSP while they are in front and pauses when you're inactive",
            "muted",
            self.font,
            PAGE_TEXT_WIDTH,
        ).pack(anchor="w", padx=EDGE_PADDING, pady=(0, DESCRIPTION_GAP))
        self.setting_vars = {}
        self.checkbox_indicators: dict[str, tk.Canvas] = {}
        # Both rows of checkboxes sit against the right edge, mirroring the module checkboxes on the overview
        program_checks = tk.Frame(page, bg=COLORS["background"])
        program_checks.pack(anchor="e", padx=EDGE_PADDING, pady=(0, PANEL_GAP))
        self._setting_checkbox(program_checks, "tracking_enabled", "Photoshop")
        self._setting_checkbox(program_checks, "tracking_clip_studio_paint", "CSP")
        self._setting_checkbox(program_checks, "tracking_krita", "Krita")
        self._setting_toggle("launch_on_startup", "Start with Windows", "Launch PS Focus when you sign in to Windows")
        self._setting_toggle("start_minimized", "Start minimized", "Open PS Focus minimized when launched at sign-in")
        self._orientation_setting()
        option_checks = tk.Frame(page, bg=COLORS["background"])
        option_checks.pack(anchor="e", padx=EDGE_PADDING, pady=(0, PANEL_GAP))
        self._setting_checkbox(option_checks, "tracking_paused", "Pause tracking")
        self._setting_checkbox(option_checks, "disable_fanfare_sound", "Disable fanfare sound")

        help_panel = tk.Frame(page, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        help_panel.pack(fill="x")
        self._settings_text(help_panel, "Settings and activity backups", "text", self.font_bold).pack(
            anchor="w", padx=EDGE_PADDING, pady=(BACKUP_BOX_PADDING, BACKUP_LINE_GAP)
        )
        self._settings_text(
            help_panel, "Activity is saved locally on this PC and backed up to Google Drive when connected", "muted", self.font, TOGGLE_TEXT_WIDTH + 40 - 2
        ).pack(anchor="w", padx=EDGE_PADDING, pady=(0, BACKUP_LINE_GAP + 2))
        self.google_settings_status = self._settings_text(help_panel, "Not connected", "muted", self.font_small)
        self.google_settings_status.pack(anchor="w", padx=EDGE_PADDING, pady=(0, BACKUP_LINE_GAP))
        self.google_settings_status.bind("<Button-1>", lambda _event: self._resync_google())
        self.activity_backup_status = self._settings_text(help_panel, "Creating local backups", "muted", self.font_small, PAGE_TEXT_WIDTH - 2)
        self.activity_backup_status.pack(anchor="w", padx=EDGE_PADDING, pady=(0, BACKUP_LINE_GAP + 3))
        # One row of buttons across the box: Back up now at the left, and the Google buttons that apply
        # in the middle and at the right, see _arrange_google_buttons
        actions = tk.Frame(help_panel, bg=COLORS["panel"])
        actions.pack(fill="x", padx=EDGE_PADDING, pady=(0, BACKUP_BOX_PADDING))
        self._button(actions, "Back up now", lambda: self._backup_activity_now(force=True), accent=True).pack(side="left")
        self.google_connect_button = self._button(actions, "Connect Google", self._connect_google, accent=True)
        self.google_reconnect_button = self._button(actions, "Reconnect", self._connect_google, accent=True)
        self.google_switch_button = self._button(actions, "Switch account", self._switch_google_account)
        self.google_logout_button = self._button(actions, "Log out", self._logout_google)

        restart_actions = tk.Frame(page, bg=COLORS["background"])
        restart_actions.pack(fill="x", padx=EDGE_PADDING, pady=(PANEL_GAP, COMPACT_BOTTOM_SPACE))
        self._button(restart_actions, "Exit", self._exit).pack(side="left")
        # Shown once enough art application time has been tracked, see _set_feedback_unlocked
        self.feedback_button = self._button(restart_actions, "Got feedback?", self._open_feedback_dialog)

    def _build_settings_title(self, page: tk.Widget) -> None:
        """Draw the page title on a canvas just tall enough for its letters

        A label would add the empty space the large font reserves above its capitals, as the program panels'
        big time figure would, see _create_today_panel
        """
        font = self.font_title
        ascent, descent = font.metrics("ascent"), font.metrics("descent")
        capital_height = round(ascent * 0.66)
        title = tk.Canvas(
            page, width=PAGE_TEXT_WIDTH, height=TITLE_PADDING + capital_height + descent + 2, bg=COLORS["background"], highlightthickness=0
        )
        title.pack(anchor="w", padx=EDGE_PADDING, pady=(0, TITLE_GAP))
        title.create_text(0, TITLE_PADDING - (ascent - capital_height), anchor="nw", text="Settings", fill=COLORS["text"], font=font)

    def _setting_toggle(self, key: str, title: str, description: str) -> None:
        row = tk.Frame(self.settings_page, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        row.pack(fill="x", pady=(0, PANEL_GAP))
        text = tk.Frame(row, bg=COLORS["panel"])
        text.pack(side="left", fill="both", expand=True, padx=EDGE_PADDING, pady=BOX_PADDING)
        self._settings_text(text, title, "text", self.font_bold, TOGGLE_TEXT_WIDTH).pack(anchor="w")
        self._settings_text(text, description, "muted", self.font_small, TOGGLE_TEXT_WIDTH).pack(anchor="w", pady=(2, 0))
        variable = tk.BooleanVar(value=bool(self.settings.get(key, DEFAULT_SETTINGS[key])))
        self.setting_vars[key] = variable
        indicator = tk.Canvas(
            row, width=CHECKBOX_SIZE, height=CHECKBOX_SIZE, bg=COLORS["panel"], highlightthickness=0, cursor="hand2", takefocus=True
        )
        # The drawn box is two pixels inside its canvas, which puts its right side EDGE_PADDING from the edge
        indicator.pack(side="right", padx=(0, EDGE_PADDING - 2))
        self._draw_square_indicator(indicator, variable.get())

        def toggle(_event: tk.Event | None = None) -> None:
            variable.set(not variable.get())
            self._setting_changed(key)
            self._draw_square_indicator(indicator, variable.get())

        indicator.bind("<Button-1>", toggle)
        indicator.bind("<Return>", toggle)
        indicator.bind("<space>", toggle)

    def _orientation_setting(self) -> None:
        """A row like the toggles', with a choice of Portrait or Landscape at its right; the chosen one is outlined"""
        row = tk.Frame(self.settings_page, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        row.pack(fill="x", pady=(0, PANEL_GAP))
        # Two outline shapes, a tall one for portrait and a wide one for landscape, the chosen one filled
        choice = tk.Canvas(row, bg=COLORS["panel"], highlightthickness=0, cursor="hand2")
        long_side, short_side = ORIENTATION_ICON_SIZE
        self.orientation_icons = {
            (landscape, chosen): to_photo_image(
                render_rounded_box(
                    *((long_side, short_side) if landscape else (short_side, long_side)),
                    ORIENTATION_ICON_RADIUS,
                    COLORS["text"] if chosen else COLORS["panel"],
                    COLORS["text"] if chosen else COLORS["muted"],
                    COLORS["panel"],
                    outline_width=2,
                )
            )
            for landscape in (False, True)
            for chosen in (False, True)
        }
        # Where each shape sits on the canvas, as its left and right edges
        self.orientation_areas = {False: (0, short_side), True: (short_side + ORIENTATION_ICON_GAP, short_side + ORIENTATION_ICON_GAP + long_side)}
        choice_width = short_side + ORIENTATION_ICON_GAP + long_side
        choice.configure(width=choice_width, height=long_side)
        choice.pack(side="right", padx=(0, EDGE_PADDING))
        self.orientation_canvas = choice

        def clicked(event: tk.Event) -> None:
            for landscape, (left, right) in self.orientation_areas.items():
                if left - 3 <= event.x <= right + 3:
                    self._set_orientation(landscape)

        choice.bind("<Button-1>", clicked)
        # The text wraps short of the choice, as the other rows' text wraps short of their checkbox
        text_width = PAGE_TEXT_WIDTH - choice_width - EDGE_PADDING
        text = tk.Frame(row, bg=COLORS["panel"])
        text.pack(side="left", fill="both", expand=True, padx=EDGE_PADDING, pady=BOX_PADDING)
        self._settings_text(text, "Orientation", "text", self.font_bold, text_width).pack(anchor="w")
        self._settings_text(
            text, "Modules below or beside the program panels", "muted", self.font_small, text_width
        ).pack(anchor="w", pady=(2, 0))
        self._show_orientation()

    def _show_orientation(self) -> None:
        canvas = self.orientation_canvas
        canvas.delete("all")
        long_side = ORIENTATION_ICON_SIZE[0]
        for landscape, (left, _right) in self.orientation_areas.items():
            image = self.orientation_icons[(landscape, landscape == self._landscape())]
            canvas.create_image(left, long_side // 2, anchor="w", image=image)

    def _set_orientation(self, landscape: bool) -> None:
        if landscape == self._landscape():
            return
        self.settings["landscape"] = landscape
        self._save_settings()
        self._show_orientation()
        self._apply_layout()

    def _setting_checkbox(self, parent: tk.Widget, key: str, label: str) -> None:
        """Add a named checkbox to the end of a row"""
        variable = tk.BooleanVar(value=bool(self.settings.get(key, DEFAULT_SETTINGS[key])))
        self.setting_vars[key] = variable
        control = tk.Frame(parent, bg=COLORS["background"], cursor="hand2")
        # The space goes before every checkbox but the first, so the row's last box reaches the right edge
        control.pack(side="left", padx=(CHECKBOX_GAP if parent.pack_slaves() else 0, 0))
        text = self._settings_text(control, label, "muted", self.font_small)
        text.configure(cursor="hand2")
        text.pack(side="left", padx=(0, CHECKBOX_LABEL_GAP))
        indicator = tk.Canvas(
            control, width=CHECKBOX_SIZE, height=CHECKBOX_SIZE, bg=COLORS["background"], highlightthickness=0, cursor="hand2", takefocus=True
        )
        indicator.pack(side="left")
        self.checkbox_indicators[key] = indicator
        self._draw_square_indicator(indicator, variable.get())

        def toggle(_event: tk.Event | None = None) -> None:
            variable.set(not variable.get())
            self._setting_changed(key)
            self._draw_square_indicator(indicator, variable.get())

        for widget in (control, text, indicator):
            widget.bind("<Button-1>", toggle)
        indicator.bind("<Return>", toggle)
        indicator.bind("<space>", toggle)

    def _setting_changed(self, key: str) -> None:
        previous = bool(self.settings.get(key, DEFAULT_SETTINGS[key]))
        value = self.setting_vars[key].get()
        if key in PROGRAM_PANEL_SETTINGS.values() and not value and not any(
            self.settings.get(other) for other in PROGRAM_PANEL_SETTINGS.values() if other != key
        ):
            # One program panel is always shown: it holds the header in landscape and today's time everywhere
            self.setting_vars[key].set(True)
            return
        self.settings[key] = value
        if key == "launch_on_startup":
            try:
                set_startup(value, bool(self.settings.get("start_minimized")))
            except (OSError, ImportError) as error:
                self.settings[key] = previous
                self.setting_vars[key].set(previous)
                self._message(f"Could not update Windows startup: {error}", error=True)
                return
        if key == "start_minimized" and self.settings.get("launch_on_startup"):
            try:
                set_startup(True, value)
            except (OSError, ImportError) as error:
                self._message(f"Could not update Windows startup: {error}", error=True)
        if key in PROGRAM_PANEL_SETTINGS.values():
            # A panel shown or hidden by hand is left that way, see _reveal_panel_on_first_use
            application = next(name for name, setting in PROGRAM_PANEL_SETTINGS.items() if setting == key)
            self._note_panel_chosen(application)
        self._save_settings()
        if key in PROGRAM_PANEL_SETTINGS.values():
            self._update_application_panels()

    def _save_settings(self) -> None:
        app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
        temporary = app_config.SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        temporary.replace(app_config.SETTINGS_PATH)
        if self.google.connected:
            snapshot = self.settings.copy()
            threading.Thread(target=self._upload_settings, args=(snapshot,), daemon=True).start()

    def _upload_settings(self, settings: dict) -> None:
        try:
            self.google.upload_settings(settings)
            self.results.put(("sync", True, "Settings backed up to Google Drive"))
        except Exception as error:
            self.results.put(("sync", False, str(error)))
