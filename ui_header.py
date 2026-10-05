"""Header row: the level, the Google account with today's progress dot, and the settings button

The row is drawn on one canvas rather than built from labels and frames, because Tk repaints every widget
separately while the window is resized. Only the settings button and the name field, which need keyboard
focus, are real widgets, and they sit on the canvas
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from app_config import COLORS, EDGE_PADDING, LEVEL_BADGE_SIZE, SESSION_MINIMUM_SECONDS, TODAY_PANEL_WIDTH, WINDOW_MARGIN
from widgets import LABEL_TEXT_INSET

# The header is as wide as the panels below it; the window cannot be resized sideways
HEADER_WIDTH = TODAY_PANEL_WIDTH
# Side of the square the level badge and the settings button each occupy, and the least height of the row
HEADER_ICON_SIZE = 26
# Width of the space holding the progress dot, to the left of the account text
PROGRESS_DOT_SPACE = 18
# From the edge of the account's area to its text
ACCOUNT_TEXT_INSET_X = 5
ACCOUNT_TEXT_INSET_Y = 4
# Least space between the account text and the level badge or the settings button
HEADER_GROUP_GAP = 6
DRAWN_TAG = "drawn"


class HeaderAccountLabel:
    """The Google account text in the header, set and read the way the label it replaced was"""

    def __init__(self, redraw, font: tkfont.Font) -> None:
        self._redraw = redraw
        self._options = {"text": "", "fg": COLORS["muted"], "font": font, "state": "normal"}
        self.visible = True

    def configure(self, **options) -> None:
        self._options.update(options)
        self._redraw()

    def cget(self, option: str):
        return self._options[option]

    def grid_remove(self) -> None:
        self.visible = False
        self._redraw()

    def grid(self) -> None:
        self.visible = True
        self._redraw()


class HeaderNameEntry(tk.Entry):
    """The field for typing a display name, shown in place of the account text while a name is edited"""

    def __init__(self, canvas: tk.Canvas, redraw, **options) -> None:
        super().__init__(canvas, **options)
        self._redraw = redraw
        self.visible = False

    def grid(self, **_options) -> None:
        self.visible = True
        self._redraw()

    def grid_remove(self) -> None:
        self.visible = False
        self._redraw()


class HeaderLevelBadge:
    """Where the level badge is drawn, for the celebration that bursts from it and the cursor shown over it"""

    def __init__(self, canvas: tk.Canvas) -> None:
        self.canvas = canvas
        self.cursor = ""
        # Left and top of the badge on the canvas, set each time the header is drawn
        self.position = (0, 0)

    def configure(self, cursor: str) -> None:
        self.cursor = cursor

    def winfo_rootx(self) -> int:
        return self.canvas.winfo_rootx() + self.position[0]

    def winfo_rooty(self) -> int:
        return self.canvas.winfo_rooty() + self.position[1]

    def winfo_width(self) -> int:
        return LEVEL_BADGE_SIZE

    def winfo_height(self) -> int:
        return LEVEL_BADGE_SIZE


class HeaderMixin:
    def _build_header(self) -> None:
        canvas = tk.Canvas(self.root, width=HEADER_WIDTH, height=HEADER_ICON_SIZE, bg=COLORS["background"], highlightthickness=0)
        # Against the left edge, so in the landscape layout it stays above the program panels
        canvas.pack(anchor="w", padx=WINDOW_MARGIN, pady=(0, 2))
        self.header_canvas = canvas
        self.level_badge_image: tk.PhotoImage | None = None
        self.progress_reached = False
        # Areas that respond to the pointer, as (left, top, right, bottom); empty while not shown
        self.header_level_area = (0, 0, 0, 0)
        self.header_account_area = (0, 0, 0, 0)
        self.header_version_area = (0, 0, 0, 0)
        self.level_badge = HeaderLevelBadge(canvas)
        self.level_widgets = (self.level_badge,)
        self.account_label = HeaderAccountLabel(self._draw_header, self.font_small)
        self.account_name_entry = HeaderNameEntry(
            canvas,
            self._draw_header,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            bd=0,
            relief="flat",
            justify="center",
            font=self.font_account,
            width=20,
        )
        self.account_name_entry.bind("<Return>", lambda _event: self._finish_display_name_edit(save=True))
        self.account_name_entry.bind("<FocusOut>", lambda _event: self._finish_display_name_edit(save=True))
        self.account_name_entry.bind("<Escape>", lambda _event: self._finish_display_name_edit(save=False))

        settings_toggle = tk.Canvas(
            canvas, width=HEADER_ICON_SIZE, height=HEADER_ICON_SIZE, bg=COLORS["background"], highlightthickness=0, cursor="hand2", takefocus=True
        )
        dot_radius = 0.5
        dot_center_y = HEADER_ICON_SIZE / 2
        for dot_index in range(3):
            dot_center_x = 8 + dot_index * 5
            settings_toggle.create_oval(
                dot_center_x - dot_radius,
                dot_center_y - dot_radius,
                dot_center_x + dot_radius,
                dot_center_y + dot_radius,
                fill=COLORS["text"],
                outline="",
            )
        settings_toggle.bind("<Button-1>", lambda _event: self._toggle_settings())
        settings_toggle.bind("<Return>", lambda _event: self._toggle_settings())
        settings_toggle.bind("<space>", lambda _event: self._toggle_settings())
        self.settings_toggle_item = canvas.create_window(self._settings_button_left(), 0, anchor="nw", window=settings_toggle)
        self.name_entry_item = canvas.create_window(0, 0, anchor="nw", window=self.account_name_entry, state="hidden")

        canvas.bind("<Button-1>", self._header_clicked)
        canvas.bind("<Double-Button-1>", self._header_double_clicked)
        canvas.bind("<Motion>", self._header_pointer_moved)
        self._draw_header()

    @staticmethod
    def _settings_button_left() -> int:
        """Where the settings button starts, which leaves its three dots the usual distance from the header's edge"""
        return HEADER_WIDTH - HEADER_ICON_SIZE - 2

    def _header_height(self) -> int:
        """Height of the row, the same whatever it shows, so nothing below it moves when the account text changes"""
        return max(HEADER_ICON_SIZE, self.font_account.metrics("linespace") + 2 * ACCOUNT_TEXT_INSET_Y)

    def _draw_header(self) -> None:
        canvas = self.header_canvas
        canvas.delete(DRAWN_TAG)
        self.header_level_area = self.header_account_area = self.header_version_area = (0, 0, 0, 0)
        height = self._header_height()
        if self.view == "Settings":
            self._draw_header_credit(height)
        else:
            self._draw_header_account(height)
            self._draw_header_level(height)
        canvas.configure(height=height)
        canvas.coords(self.settings_toggle_item, self._settings_button_left(), (height - HEADER_ICON_SIZE) // 2)

    def _draw_header_credit(self, height: int) -> None:
        """Draw what the Settings page shows in place of the level and account: the version, and the credit"""
        font = self.font_account
        self.header_canvas.itemconfigure(self.name_entry_item, state="hidden")
        # The version sits where the level does on the overview. When a newer version has been published
        # it becomes a link to the download page
        version, is_link = self._version_text()
        self.header_canvas.create_text(
            EDGE_PADDING,
            (height - self.font_small.metrics("linespace")) // 2,
            anchor="nw",
            text=version,
            fill=COLORS["accent"] if is_link else COLORS["muted"],
            font=self.font_small,
            tags=DRAWN_TAG,
        )
        if is_link:
            self.header_version_area = (0, 0, EDGE_PADDING + self.font_small.measure(version) + 4, height)
        self.header_canvas.create_text(
            (HEADER_WIDTH - font.measure("by giltyworks")) // 2,
            (height - font.metrics("linespace")) // 2,
            anchor="nw",
            text="by giltyworks",
            fill=COLORS["active_green"],
            font=font,
            tags=DRAWN_TAG,
        )

    def _draw_header_account(self, height: int) -> None:
        """Draw the progress dot with the account text, or the name field while a name is edited, beside it

        The text is kept to one line. It is centred in the window when it fits there, moved towards the
        settings button when it only fits between the level and that button, and shortened when it fits neither
        """
        canvas = self.header_canvas
        label = self.account_label
        editing = self.account_name_entry.visible
        # The space between the level badge and the settings button's dots
        room_left = self._header_level_width() + HEADER_GROUP_GAP
        room_right = self._settings_button_left() + 8 - HEADER_GROUP_GAP
        text, font = "", label.cget("font")
        if editing:
            content_width = self.account_name_entry.winfo_reqwidth()
        elif label.visible:
            text = self._fit_header_text(label.cget("text"), font, room_right - room_left - PROGRESS_DOT_SPACE - 2 * ACCOUNT_TEXT_INSET_X)
            content_width = font.measure(text) + 2 * ACCOUNT_TEXT_INSET_X
        else:
            content_width = 0
        group_width = PROGRESS_DOT_SPACE + content_width
        group_left = max(room_left, min((HEADER_WIDTH - group_width) // 2, room_right - group_width))
        content_left = group_left + PROGRESS_DOT_SPACE

        dot_top = (height - HEADER_ICON_SIZE) // 2
        reached = self.progress_reached
        canvas.create_oval(
            group_left + 2,
            dot_top + 6,
            group_left + 16,
            dot_top + 20,
            fill=COLORS["calendar_blue"] if reached else COLORS["panel_alt"],
            outline=COLORS["calendar_blue"] if reached else COLORS["border"],
            tags=DRAWN_TAG,
        )
        canvas.itemconfigure(self.name_entry_item, state="normal" if editing else "hidden")
        if editing:
            canvas.coords(self.name_entry_item, content_left, (height - self.account_name_entry.winfo_reqheight()) // 2)
        elif label.visible:
            canvas.create_text(
                content_left + ACCOUNT_TEXT_INSET_X,
                (height - font.metrics("linespace")) // 2,
                anchor="nw",
                text=text,
                fill="SystemDisabledText" if label.cget("state") == "disabled" else label.cget("fg"),
                font=font,
                tags=DRAWN_TAG,
            )
            self.header_account_area = (content_left, 0, content_left + content_width, height)

    @staticmethod
    def _fit_header_text(text: str, font: tkfont.Font, width: int) -> str:
        """Return the text, cut short and ended with an ellipsis if it is wider than this many pixels"""
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def _draw_header_level(self, height: int) -> None:
        """Draw the word Level and the badge at the left, centred on a row of this height"""
        canvas = self.header_canvas
        top = (height - HEADER_ICON_SIZE) // 2
        line_height = self.font.metrics("linespace") + 2 * LABEL_TEXT_INSET
        canvas.create_text(
            EDGE_PADDING,
            top + (HEADER_ICON_SIZE - line_height) // 2 + LABEL_TEXT_INSET,
            anchor="nw",
            text="Level",
            fill=COLORS["text"],
            font=self.font,
            tags=DRAWN_TAG,
        )
        badge_left = self._header_level_width() - LEVEL_BADGE_SIZE
        self.level_badge.position = (badge_left, top)
        if self.level_badge_image is not None:
            canvas.create_image(badge_left, top, anchor="nw", image=self.level_badge_image, tags=DRAWN_TAG)
        self.header_level_area = (0, top, badge_left + LEVEL_BADGE_SIZE, top + HEADER_ICON_SIZE)

    def _header_level_width(self) -> int:
        """Width from the window's edge to the end of the badge: padding, the word Level, a gap, and the badge"""
        return EDGE_PADDING + self.font.measure("Level") + 4 + LEVEL_BADGE_SIZE

    @staticmethod
    def _inside(area: tuple[int, int, int, int], event: tk.Event) -> bool:
        left, top, right, bottom = area
        return left <= event.x < right and top <= event.y < bottom

    def _header_clicked(self, event: tk.Event) -> None:
        if self._inside(self.header_account_area, event):
            self._account_label_clicked()
        elif self._inside(self.header_level_area, event):
            self._level_clicked()
        elif self._inside(self.header_version_area, event):
            self._open_update_page()

    def _header_double_clicked(self, event: tk.Event) -> None:
        if self._inside(self.header_account_area, event):
            self._account_label_double_clicked()
        else:
            # Tk reports the second of two quick clicks only as a double-click; elsewhere it is just another click
            self._header_clicked(event)

    def _header_pointer_moved(self, event: tk.Event) -> None:
        if self._inside(self.header_account_area, event) or self._inside(self.header_version_area, event):
            cursor = "hand2"
        elif self._inside(self.header_level_area, event):
            cursor = self.level_badge.cursor
        else:
            cursor = ""
        self.header_canvas.configure(cursor=cursor)

    def _draw_progress_indicator(self, seconds: int) -> None:
        reached = seconds >= SESSION_MINIMUM_SECONDS
        if reached != self.progress_reached:
            self.progress_reached = reached
            self._draw_header()
