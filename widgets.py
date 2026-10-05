"""Shared widgets for the PS Focus window"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from app_config import COLORS
from rendering import render_rounded_box, to_photo_image

BUTTON_CORNER_RADIUS = 6
# The rounded square drawn in the middle of every checkbox
CHECKBOX_BOX_SIZE = 14
CHECKBOX_CORNER_RADIUS = 4
# How far a Tk label keeps its text from its own edge: a two-pixel border and one pixel of padding.
# Text drawn on a canvas is inset by the same amount so it sits where the label it replaced put it
LABEL_TEXT_INSET = 3
# Marks canvas items that act as controls, so a press on one is not taken as the start of a module drag
CONTROL_TAG = "control"


def checkbox_image(checked: bool, surface: str) -> tk.PhotoImage:
    """Return the rounded square of a checkbox, filled when ticked, to be shown on a surface of this colour"""
    fill = COLORS["calendar_blue"] if checked else COLORS["panel"]
    outline = COLORS["calendar_blue"] if checked else COLORS["border"]
    return to_photo_image(
        render_rounded_box(CHECKBOX_BOX_SIZE, CHECKBOX_BOX_SIZE, CHECKBOX_CORNER_RADIUS, fill, outline, surface, outline_width=2)
    )


def drawing_surface(canvas: tk.Canvas) -> tk.Canvas:
    """Return the canvas to draw on for content that `canvas` will show as a single picture

    Drawn text is by far the costliest thing for Tk to repaint while the window is resized, and a picture
    costs almost nothing. So text and shapes are drawn on a hidden twin of the canvas, and show_drawing puts a
    picture of the twin on the canvas. Tk takes the picture itself, so it is identical to what was drawn.
    Controls such as CanvasButton stay on the visible canvas. Tk before 9.0 cannot take the picture; there the
    canvas itself is returned and drawn on directly
    """
    for item in canvas.find_all():
        if CONTROL_TAG not in canvas.gettags(item):
            canvas.delete(item)
    if tk.TkVersion < 9:
        return canvas
    if not hasattr(canvas, "drawing_twin"):
        canvas.drawing_twin = tk.Canvas(canvas.master, bg=canvas.cget("bg"), highlightthickness=0)
    canvas.drawing_twin.delete("all")
    return canvas.drawing_twin


def show_drawing(canvas: tk.Canvas, surface: tk.Canvas, width: int, height: int) -> None:
    """Show what was drawn on the surface from drawing_surface, as one picture beneath the canvas's controls"""
    if surface is canvas:
        return
    # The twin is never shown. Its scroll region is what sets the area Tk takes the picture of; without one
    # the picture is cut to the space currently around the twin, which lags behind content that has just grown
    surface.configure(width=width, height=height, scrollregion=(0, 0, width, height))
    picture = tk.PhotoImage(master=canvas, width=width, height=height)
    canvas.tk.call(surface, "image", picture)
    canvas.tag_lower(canvas.create_image(0, 0, anchor="nw", image=picture))
    # Kept on the canvas so the picture lives as long as the canvas shows it
    canvas.shown_picture = picture


class CanvasText:
    """A line of text on a canvas that is updated the way a label is

    Tk repaints every widget separately while the window is resized, which made the window slow to drag.
    Text that shares one canvas costs a single widget however many lines there are
    """

    def __init__(self, canvas: tk.Canvas, x: float, y: float, anchor: str, text: str, fg: str, font) -> None:
        self.canvas = canvas
        self.item = canvas.create_text(x, y, anchor=anchor, text=text, fill=fg, font=font)

    def configure(self, text: str | None = None, fg: str | None = None) -> None:
        options = {}
        if text is not None:
            options["text"] = text
        if fg is not None:
            options["fill"] = fg
        self.canvas.itemconfigure(self.item, **options)


class CanvasButton:
    """A rounded button drawn on a canvas, looking and behaving like OutlinedButton without being a widget

    It is created once and placed each time its canvas is redrawn. Unlike OutlinedButton it cannot take
    keyboard focus
    """

    def __init__(
        self, canvas: tk.Canvas, text: str, command, bg: str, fg: str, font: tkfont.Font, padx: int, pady: int, width: int = 0
    ) -> None:
        text_width = font.measure("0" * width) if width else font.measure(text)
        self.width = text_width + 2 * padx
        self.height = font.metrics("linespace") + 2 * pady
        surface = canvas.cget("bg")
        self.shapes = {
            outlined: to_photo_image(
                render_rounded_box(self.width, self.height, BUTTON_CORNER_RADIUS, bg, COLORS["text"] if outlined else bg, surface)
            )
            for outlined in (False, True)
        }
        self.canvas = canvas
        self.text = text
        self.command = command
        self.font = font
        self.text_color = fg
        self.selected = False
        self.tag = f"button-{id(self)}"
        self.box = (0, 0, 0, 0)
        self.image_item: int | None = None
        self.text_item: int | None = None

    def place(self, x: int, y: int) -> None:
        """Draw the button with its top-left corner at this point; call again after the canvas has been cleared"""
        self.box = (x, y, x + self.width, y + self.height)
        tags = (self.tag, CONTROL_TAG)
        self.image_item = self.canvas.create_image(x, y, anchor="nw", image=self.shapes[self.selected], tags=tags)
        # Centred in whole pixels, as a label centres its text
        self.text_item = self.canvas.create_text(
            x + (self.width - self.font.measure(self.text)) // 2,
            y + (self.height - self.font.metrics("linespace")) // 2,
            anchor="nw",
            text=self.text,
            fill=self.text_color,
            font=self.font,
            tags=tags,
        )
        self.canvas.tag_bind(self.tag, "<ButtonPress-1>", self._pressed)
        self.canvas.tag_bind(self.tag, "<ButtonRelease-1>", self._released)
        self.canvas.tag_bind(self.tag, "<Enter>", lambda _event: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind(self.tag, "<Leave>", lambda _event: self.canvas.configure(cursor=""))

    def set_selected(self, selected: bool) -> None:
        """Show the white outline for as long as this button is the selected one"""
        self.selected = selected
        self._show_shape(selected)

    def configure(self, text: str | None = None, fg: str | None = None) -> None:
        if text is not None:
            self.text = text
        if fg is not None:
            self.text_color = fg
        if self.text_item is not None:
            self.canvas.itemconfigure(self.text_item, text=self.text, fill=self.text_color)
            # New text has a new width, so it is centred again
            left, top = self.box[:2]
            self.canvas.coords(
                self.text_item,
                left + (self.width - self.font.measure(self.text)) // 2,
                top + (self.height - self.font.metrics("linespace")) // 2,
            )

    def _show_shape(self, outlined: bool) -> None:
        if self.image_item is not None:
            self.canvas.itemconfigure(self.image_item, image=self.shapes[outlined])

    def _pressed(self, _event: tk.Event) -> None:
        self._show_shape(True)

    def _released(self, event: tk.Event) -> None:
        self._show_shape(self.selected)
        # Letting go outside the button cancels the click, as it does for a standard button
        left, top, right, bottom = self.box
        if left <= event.x < right and top <= event.y < bottom:
            self.command()


class OutlinedButton(tk.Label):
    """A flat rounded button with a one-pixel outline that turns white while it is pressed or marked as selected

    Tk cannot round the corners of a button, so this is a label showing a drawn rounded shape with the text
    on top of it. The shape is drawn twice, with and without the white outline, and the label swaps between them.
    `width` fixes the button's width in characters, for buttons that sit in a row or whose text changes
    """

    def __init__(
        self, parent: tk.Widget, text: str, command, bg: str, fg: str, font: tkfont.Font, padx: int, pady: int, width: int = 0
    ) -> None:
        text_width = font.measure("0" * width) if width else font.measure(text)
        size = (text_width + 2 * padx, font.metrics("linespace") + 2 * pady)
        surface = parent.cget("bg")
        self.shapes = {
            outlined: to_photo_image(
                render_rounded_box(*size, BUTTON_CORNER_RADIUS, bg, COLORS["text"] if outlined else bg, surface)
            )
            for outlined in (False, True)
        }
        super().__init__(
            parent,
            text=text,
            image=self.shapes[False],
            compound="center",
            bg=surface,
            fg=fg,
            font=font,
            bd=0,
            padx=0,
            pady=0,
            cursor="hand2",
            takefocus=True,
        )
        self.command = command
        self.text_color = fg
        self.enabled = True
        self.selected = False
        self.bind("<ButtonPress-1>", self._pressed)
        self.bind("<ButtonRelease-1>", self._released)
        self.bind("<Return>", lambda _event: self._run_command())
        self.bind("<space>", lambda _event: self._run_command())

    def set_selected(self, selected: bool) -> None:
        """Show the white outline for as long as this button is the selected one"""
        self.selected = selected
        self.configure(image=self.shapes[selected])

    def configure(self, cnf=None, **options):
        # Tk greys out a disabled label by speckling its image, which roughens the rounded shape,
        # so the disabled state is kept here and shown by dimming the text instead
        if "state" in options:
            self.enabled = options.pop("state") != "disabled"
            options["fg"] = self.text_color if self.enabled else COLORS["muted"]
        elif "fg" in options:
            self.text_color = options["fg"]
        return super().configure(cnf, **options)

    def _pressed(self, _event: tk.Event) -> None:
        if self.enabled:
            self.configure(image=self.shapes[True])

    def _released(self, event: tk.Event) -> None:
        self.configure(image=self.shapes[self.selected])
        # Letting go outside the button cancels the click, as it does for a standard button
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self._run_command()

    def _run_command(self) -> None:
        if self.enabled:
            self.command()
