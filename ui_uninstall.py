"""The Tk app's uninstall window, styled like the app; the removal itself is in uninstall.py"""

from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox

from app_config import COLORS
from uninstall import APP_NAME, DONE_MESSAGE_DELETED, DONE_MESSAGE_KEPT, WARNING_MESSAGE, WINDOW_TITLE, uninstall
from widgets import OutlinedButton, checkbox_image
from windows_startup import set_title_bar_colors

# Space around the uninstall window's contents, and the width its text wraps at
DIALOG_PADDING = 14
DIALOG_TEXT_WIDTH = 300


def confirm_and_uninstall(delete_data: bool, parent: tk.Misc | None = None) -> bool:
    """Run the uninstall, asking first when user data would be deleted; return whether it ran"""
    if delete_data and not messagebox.askyesno(WINDOW_TITLE, WARNING_MESSAGE, icon="warning", default="no", parent=parent):
        return False
    if parent is not None:
        parent.withdraw()
    failed = uninstall(delete_data)
    if failed:
        remaining = "\n".join(str(path) for path in failed)
        messagebox.showwarning(WINDOW_TITLE, f"{APP_NAME} was removed, but these items could not be deleted:\n\n{remaining}")
    elif delete_data:
        messagebox.showinfo(WINDOW_TITLE, DONE_MESSAGE_DELETED)
    else:
        messagebox.showinfo(WINDOW_TITLE, DONE_MESSAGE_KEPT)
    return True


class UninstallDialog:
    """The uninstall window, styled like the app: dark title bar, rounded buttons, and the app's checkbox"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(WINDOW_TITLE)
        root.configure(bg=COLORS["background"])
        root.resizable(False, False)
        icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "icons" / "PSFocus.ico"
        try:
            root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass
        set_title_bar_colors(root)
        font_bold = tkfont.Font(root=root, family="Segoe UI Semibold", size=10)
        font_small = tkfont.Font(root=root, family="Segoe UI", size=9)

        def text(parent: tk.Widget, content: str, color: str, font: tkfont.Font, wraplength: int = 0) -> tk.Label:
            return tk.Label(
                parent, text=content, bg=COLORS["background"], fg=COLORS[color], font=font, wraplength=wraplength, justify="left", bd=0, padx=0, pady=0
            )

        text(root, f"Remove {APP_NAME} from this PC?", "text", font_bold).pack(padx=DIALOG_PADDING, pady=(DIALOG_PADDING, 4), anchor="w")
        text(
            root,
            "Your activity history, settings, and backups are kept unless you choose to delete them below",
            "muted",
            font_small,
            DIALOG_TEXT_WIDTH,
        ).pack(padx=DIALOG_PADDING, pady=(0, 12), anchor="w")

        # The app's own checkbox: its name, then the rounded box; clicking either ticks it
        self.delete_data = tk.BooleanVar(root, value=False)
        option = tk.Frame(root, bg=COLORS["background"], cursor="hand2")
        option.pack(padx=DIALOG_PADDING, pady=(0, 14), anchor="w")
        label = text(option, "Also delete all user data", "text", font_small)
        label.configure(cursor="hand2")
        label.pack(side="left", padx=(0, 6))
        self.checkbox = tk.Canvas(option, width=18, height=18, bg=COLORS["background"], highlightthickness=0, cursor="hand2", takefocus=True)
        self.checkbox.pack(side="left")
        self.checkbox_images = {checked: checkbox_image(checked, COLORS["background"]) for checked in (False, True)}
        for widget in (option, label, self.checkbox):
            widget.bind("<Button-1>", self._toggle_delete_data)
        self.checkbox.bind("<Return>", self._toggle_delete_data)
        self.checkbox.bind("<space>", self._toggle_delete_data)
        self._draw_checkbox()

        actions = tk.Frame(root, bg=COLORS["background"])
        actions.pack(padx=DIALOG_PADDING, pady=(0, DIALOG_PADDING), anchor="e")
        self._button(actions, "Cancel", root.destroy, font_small).pack(side="left", padx=(0, 6))
        self._button(actions, "Uninstall", self._uninstall, font_small, accent=True).pack(side="left")

        root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_width()) // 2
        y = (root.winfo_screenheight() - root.winfo_height()) // 2
        root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _toggle_delete_data(self, _event: tk.Event | None = None) -> None:
        self.delete_data.set(not self.delete_data.get())
        self._draw_checkbox()

    def _draw_checkbox(self) -> None:
        self.checkbox.delete("all")
        self.checkbox.create_image(9, 9, image=self.checkbox_images[self.delete_data.get()])

    def _button(self, parent: tk.Widget, label: str, command, font: tkfont.Font, accent: bool = False) -> OutlinedButton:
        bg = COLORS["accent_dark"] if accent else COLORS["panel_alt"]
        fg = COLORS["accent"] if accent else COLORS["text"]
        return OutlinedButton(parent, text=label, command=command, bg=bg, fg=fg, padx=17, pady=6, font=font)

    def _uninstall(self) -> None:
        if confirm_and_uninstall(self.delete_data.get(), self.root):
            self.root.destroy()


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The PS Focus uninstaller runs only on Windows")
    # Everything removed belongs to the current user, so the uninstaller runs without administrator rights
    root = tk.Tk()
    UninstallDialog(root)
    root.mainloop()


if __name__ == "__main__":
    main()
