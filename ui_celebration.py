"""Level-up celebration: a fanfare and fireworks over the window"""

from __future__ import annotations

import math
import random
import time
import tkinter as tk

from app_config import resource_path

FIREWORK_COLORS = ("#f94144", "#f8961e", "#f9c74f", "#90be6d", "#43aa8b", "#4d96ff", "#b388eb")
# Painted where the overlay should be see-through; Windows also lets clicks pass through this colour
FIREWORK_TRANSPARENT = "#010203"
# Seconds into the celebration at which each burst goes off; the first comes from the level badge
FIREWORK_BURST_TIMES = (0.0, 0.3, 0.55, 0.85, 1.1, 1.35, 1.6)
FIREWORK_SPARKS = 30
FIREWORK_SPARK_SECONDS = 0.9
# Sparks slow quickly, as real ones do, so a burst opens fast and then hangs; drag sets how far it spreads
FIREWORK_DRAG = 3.0
FIREWORK_GRAVITY = 160.0
FIREWORK_TRAIL_SECONDS = 0.03
# How far a burst spreads, as a share of the window's shorter side, and the widest it may get in pixels
FIREWORK_SPREAD = 0.5
FIREWORK_MAX_RADIUS = 170.0
# How close to the window edge a burst may be centred, as a share of its spread
FIREWORK_EDGE_MARGIN = 0.45
FIREWORK_PLACEMENT_TRIES = 12
FIREWORK_FRAME_MS = 20


class CelebrationMixin:
    def _prepare_celebration(self) -> None:
        self.fireworks_window: tk.Toplevel | None = None
        self.fireworks_geometry = ""
        self.celebrated_level: int | None = None
        # Moving or resizing the window repositions the overlay at once, without waiting for the next frame
        self.root.bind("<Configure>", lambda _event: self._fit_fireworks_to_window(), add="+")

    def _celebrate(self) -> None:
        if self.fireworks_window is not None:
            # A show is already running; restarting the sound alone would knock it out of step with the bursts
            return
        # The sound starts once the fireworks are ready to draw, so each crackle lands on its burst.
        # With the window hidden in the tray or minimized there is nowhere to draw them, so only the sound plays
        if self.root.winfo_viewable():
            self._launch_fireworks()
        self._play_celebration_sound()

    def _celebrate_level_up(self, level: int) -> None:
        """Celebrate when the level has risen since the last check; the first check only sets the starting point"""
        previous, self.celebrated_level = self.celebrated_level, level
        if previous is not None and level > previous:
            self._celebrate()

    def _play_celebration_sound(self) -> None:
        if self.settings.get("disable_fanfare_sound"):
            return
        try:
            import winsound

            winsound.PlaySound(
                str(resource_path("assets/sounds/celebration.wav")),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except (ImportError, RuntimeError):
            # No sound device, or not on Windows: the fireworks still play
            pass

    def _launch_fireworks(self) -> None:
        if self.fireworks_window is not None:
            return
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-transparentcolor", FIREWORK_TRANSPARENT)
        self.fireworks_window = overlay
        self.fireworks_geometry = ""
        self._fit_fireworks_to_window()
        canvas = tk.Canvas(overlay, bg=FIREWORK_TRANSPARENT, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        badge_x = self.level_badge.winfo_rootx() - self.root.winfo_rootx() + self.level_badge.winfo_width() / 2
        badge_y = self.level_badge.winfo_rooty() - self.root.winfo_rooty() + self.level_badge.winfo_height() / 2
        # Bursts are sized to the window, so they fit a compact window as well as a tall one
        radius = max(16.0, min(FIREWORK_MAX_RADIUS, FIREWORK_SPREAD * min(width, height)))
        sparks = []
        centers = [(badge_x, badge_y)]
        # Bursts may run a little past the edge, so their centres can sit across the whole window, not one band
        margin_x = min(radius * FIREWORK_EDGE_MARGIN, width / 2)
        margin_y = min(radius * FIREWORK_EDGE_MARGIN, height / 2)
        for _ in FIREWORK_BURST_TIMES[1:]:
            # Of several random spots, take the one furthest from the bursts already placed, to spread them out
            candidates = [
                (random.uniform(margin_x, width - margin_x), random.uniform(margin_y, height - margin_y))
                for _ in range(FIREWORK_PLACEMENT_TRIES)
            ]
            centers.append(max(candidates, key=lambda spot: min(math.dist(spot, placed) for placed in centers)))
        # Each burst gets its own colour, so neighbouring bursts stay easy to tell apart
        colors = random.sample(FIREWORK_COLORS, len(FIREWORK_BURST_TIMES))
        for (center_x, center_y), delay, color in zip(centers, FIREWORK_BURST_TIMES, colors):
            for spark in range(FIREWORK_SPARKS):
                angle = math.tau * (spark + random.uniform(-0.3, 0.3)) / FIREWORK_SPARKS
                speed = radius * FIREWORK_DRAG * random.uniform(0.55, 1.0)
                sparks.append({
                    "born": delay,
                    "x": center_x,
                    "y": center_y,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed,
                    "color": color,
                    "item": canvas.create_line(0, 0, 0, 0, fill=color, width=2, capstyle="round", state="hidden"),
                })
        self._animate_fireworks(canvas, sparks, time.monotonic(), time.monotonic())

    def _fit_fireworks_to_window(self) -> None:
        """Keep the overlay exactly over the window, so nothing is drawn outside it even while it is being moved"""
        if self.fireworks_window is None:
            return
        geometry = f"{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}"
        if geometry != self.fireworks_geometry:
            self.fireworks_geometry = geometry
            self.fireworks_window.geometry(geometry)

    def _animate_fireworks(self, canvas: tk.Canvas, sparks: list[dict], started: float, previous: float) -> None:
        now = time.monotonic()
        elapsed = now - started
        step = min(now - previous, 0.05)
        for spark in sparks:
            age = elapsed - spark["born"]
            if age < 0:
                continue
            if age >= FIREWORK_SPARK_SECONDS:
                canvas.itemconfigure(spark["item"], state="hidden")
                continue
            spark["vx"] *= max(0.0, 1 - FIREWORK_DRAG * step)
            spark["vy"] = spark["vy"] * max(0.0, 1 - FIREWORK_DRAG * step) + FIREWORK_GRAVITY * step
            spark["x"] += spark["vx"] * step
            spark["y"] += spark["vy"] * step
            # Each spark is a short streak along its path; near the end of its life it thins and glitters white
            fading = age > FIREWORK_SPARK_SECONDS * 0.6
            glitter = fading and int(age / 0.06) % 2 == 0
            canvas.coords(
                spark["item"],
                spark["x"] - spark["vx"] * FIREWORK_TRAIL_SECONDS,
                spark["y"] - spark["vy"] * FIREWORK_TRAIL_SECONDS,
                spark["x"],
                spark["y"],
            )
            canvas.itemconfigure(
                spark["item"],
                state="normal",
                width=1 if fading else 2,
                fill="#ffffff" if glitter else spark["color"],
            )
        self._fit_fireworks_to_window()
        # The show also ends early if the window is minimized or hidden, as there is then nothing to draw over
        if elapsed >= FIREWORK_BURST_TIMES[-1] + FIREWORK_SPARK_SECONDS or not self.root.winfo_viewable():
            self.fireworks_window.destroy()
            self.fireworks_window = None
            return
        self.root.after(FIREWORK_FRAME_MS, self._animate_fireworks, canvas, sparks, started, now)
