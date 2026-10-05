"""User level badge and the feedback dialog that reveals it"""

from __future__ import annotations

import base64
import io
import math
import threading
import tkinter as tk
from datetime import datetime, timedelta

from app_config import COLORS, FEEDBACK_COOLDOWN, FEEDBACK_PLACEHOLDER, FEEDBACK_PLACEHOLDER_PROMPT
from rendering import render_level_badge


class FeedbackMixin:
    def _draw_level_badge(self, level: int) -> None:
        badge_state = (level, self.level_revealed)
        if badge_state == self.displayed_level:
            return
        self.displayed_level = badge_state
        buffer = io.BytesIO()
        render_level_badge(level, self.level_revealed).save(buffer, format="PNG")
        self.level_badge_image = tk.PhotoImage(data=base64.b64encode(buffer.getvalue()))
        self._draw_header()

    def _level_clicked(self) -> None:
        if self.feedback_unlocked and not self.level_revealed:
            self._open_feedback_dialog(reveal_prompt=True)

    def _set_feedback_unlocked(self, unlocked: bool) -> None:
        if unlocked == self.feedback_unlocked:
            return
        self.feedback_unlocked = unlocked
        if unlocked:
            self.feedback_button.pack(side="right")
        else:
            self.feedback_button.pack_forget()
        self._update_level_cursor()

    def _update_level_cursor(self) -> None:
        cursor = "hand2" if self.feedback_unlocked and not self.level_revealed else ""
        for widget in self.level_widgets:
            widget.configure(cursor=cursor)

    def _reveal_level(self) -> None:
        self.level_revealed = True
        self._update_level_cursor()
        if self.displayed_level is not None:
            self._draw_level_badge(self.displayed_level[0])

    def _send_pending_feedback(self) -> None:
        if self.feedback_send_in_progress or not self.feedback.configured or not self.feedback.pending():
            return
        self.feedback_send_in_progress = True
        threading.Thread(target=self._feedback_worker, daemon=True).start()

    def _feedback_worker(self) -> None:
        try:
            self.feedback.send_pending()
        except Exception:
            # Undelivered feedback stays in the outbox and is retried with the next periodic backup
            pass
        finally:
            self.feedback_send_in_progress = False

    def _open_feedback_dialog(self, reveal_prompt: bool = False) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Feedback")
        dialog.configure(bg=COLORS["background"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self._set_title_bar_colors(dialog)

        tk.Label(
            dialog,
            text="Rate us to reveal your level" if reveal_prompt else "Rate your experience",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=self.font_bold,
        ).pack(padx=16, pady=(14, 2), anchor="w")

        rating = tk.IntVar(dialog, value=0)
        star_row = tk.Frame(dialog, bg=COLORS["background"])
        star_row.pack(padx=14, pady=(0, 6), anchor="w")
        stars: list[tk.Label] = []

        def set_rating(value: int) -> None:
            # Clicking the selected star again clears the rating
            value = 0 if rating.get() == value else value
            rating.set(value)
            status.configure(text="")
            for index, star in enumerate(stars, start=1):
                filled = index <= value
                star.configure(text="\U00002605" if filled else "\U00002606", fg=COLORS["gold"] if filled else COLORS["muted"])

        for value in range(1, 6):
            star = tk.Label(
                star_row,
                text="\U00002606",
                bg=COLORS["background"],
                fg=COLORS["muted"],
                font=("Segoe UI Symbol", 18),
                cursor="hand2",
                takefocus=True,
            )
            star.pack(side="left", padx=1)
            star.bind("<Button-1>", lambda _event, selected=value: set_rating(selected))
            star.bind("<Return>", lambda _event, selected=value: set_rating(selected))
            star.bind("<space>", lambda _event, selected=value: set_rating(selected))
            stars.append(star)

        message_frame = tk.Frame(dialog, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        message_frame.pack(padx=16, pady=(0, 8))
        message_box = tk.Text(
            message_frame,
            width=44,
            height=7,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            bd=0,
            relief="flat",
            font=self.font_small,
            wrap="word",
            padx=8,
            pady=6,
        )
        message_box.pack()
        message_box.tag_configure("ghost", foreground=COLORS["muted"])
        message_box.tag_configure("ghost_prompt", foreground=COLORS["text"])

        def typed_message() -> str:
            ghost_range = message_box.tag_ranges("ghost")
            return message_box.get("1.0", ghost_range[0] if ghost_range else "end-1c")

        def update_ghost_text() -> None:
            # Placeholder text lives in the box as a tagged range that is shown only while nothing is typed
            ghost_range = message_box.tag_ranges("ghost")
            if ghost_range:
                if message_box.compare("insert", ">", ghost_range[0]):
                    message_box.mark_set("insert", ghost_range[0])
                message_box.delete(ghost_range[0], ghost_range[-1])
            message = message_box.get("1.0", "end-1c")
            if message:
                status.configure(text="")
            if not message:
                message_box.insert("1.0", FEEDBACK_PLACEHOLDER, "ghost")
                message_box.insert("1.0", FEEDBACK_PLACEHOLDER_PROMPT, ("ghost", "ghost_prompt"))
                message_box.mark_set("insert", "1.0")

        for sequence in ("<Key>", "<ButtonRelease-1>", "<<Paste>>", "<<Cut>>"):
            message_box.bind(sequence, lambda _event: dialog.after_idle(update_ghost_text), add="+")

        status = tk.Label(dialog, text="", bg=COLORS["background"], fg=COLORS["muted"], font=self.font_small)
        status.pack(padx=16, anchor="w")
        update_ghost_text()

        def show_cooldown() -> bool:
            remaining = self._feedback_cooldown_remaining()
            if remaining is None:
                return False
            minutes = math.ceil(remaining.total_seconds() / 60)
            status.configure(
                text=f"You can send more feedback in {minutes} minute{'' if minutes == 1 else 's'}",
                fg=COLORS["orange"],
            )
            return True

        def submit() -> None:
            if show_cooldown():
                return
            message = typed_message().strip()
            if not rating.get() and not message:
                status.configure(text="Add a star rating or a message first", fg=COLORS["red"])
                return
            try:
                self.feedback.add(rating.get() or None, message)
            except OSError as error:
                status.configure(text=f"Could not save feedback: {error}", fg=COLORS["red"])
                return
            self._feedback_submitted()
            submit_button.configure(state="disabled")
            status.configure(text="Thank you for your feedback", fg=COLORS["active_green"])
            dialog.after(1200, dialog.destroy)

        actions = tk.Frame(dialog, bg=COLORS["background"])
        actions.pack(padx=16, pady=(6, 14), anchor="e")
        self._button(actions, "Not now", dialog.destroy).pack(side="left", padx=(0, 6))
        submit_button = self._button(actions, "Submit", submit, accent=True)
        submit_button.pack(side="left")
        if show_cooldown():
            submit_button.configure(state="disabled")

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        dialog.focus_set()

    def _feedback_cooldown_remaining(self) -> timedelta | None:
        try:
            cooldown_until = datetime.fromisoformat(self.settings.get("feedback_cooldown_until") or "")
        except (TypeError, ValueError):
            return None
        remaining = cooldown_until - datetime.now()
        return remaining if remaining > timedelta(0) else None

    def _feedback_submitted(self) -> None:
        self._send_pending_feedback()
        count = int(self.settings.get("feedback_count") or 0)
        if count == 0 and self.settings.get("feedback_submitted"):
            # Feedback sent before submissions were counted was the first one
            count = 1
        count += 1
        self.settings["feedback_count"] = count
        if count >= 2:
            self.settings["feedback_cooldown_until"] = (datetime.now() + FEEDBACK_COOLDOWN).isoformat(timespec="seconds")
        self.settings["feedback_submitted"] = True
        self._save_settings()
        self._reveal_level()
