"""Level-up celebration: a fanfare and fireworks over the window, as the Tk ui_celebration"""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from app_config import resource_path

FIREWORK_COLORS = ("#f94144", "#f8961e", "#f9c74f", "#90be6d", "#43aa8b", "#4d96ff", "#b388eb")
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


def play_celebration_sound() -> None:
    try:
        import winsound

        winsound.PlaySound(
            str(resource_path("assets/sounds/celebration.wav")),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except (ImportError, RuntimeError):
        # No sound device, or not on Windows: the fireworks still play
        pass


class Fireworks(QWidget):
    """Laid over the whole window, letting clicks through to it, and gone once the last spark has faded. It follows
    the window as it is moved or resized, since it is part of it"""

    def __init__(self, window: QWidget, origin: QPointF) -> None:
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(window.rect())
        width, height = self.width(), self.height()
        # Bursts are sized to the window, so they fit a compact window as well as a tall one
        radius = max(16.0, min(FIREWORK_MAX_RADIUS, FIREWORK_SPREAD * min(width, height)))
        centers = [(origin.x(), origin.y())]
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
        self.sparks = []
        for (center_x, center_y), delay, spark_color in zip(centers, FIREWORK_BURST_TIMES, colors):
            for spark in range(FIREWORK_SPARKS):
                angle = math.tau * (spark + random.uniform(-0.3, 0.3)) / FIREWORK_SPARKS
                speed = radius * FIREWORK_DRAG * random.uniform(0.55, 1.0)
                self.sparks.append({
                    "born": delay, "x": center_x, "y": center_y,
                    "vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed, "color": QColor(spark_color),
                })
        self.started = self.previous = time.monotonic()
        self.elapsed = 0.0
        self.timer = QTimer(self, interval=FIREWORK_FRAME_MS, timeout=self._step)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.start()
        self.raise_()
        self.show()

    @property
    def finished(self) -> bool:
        return self.elapsed >= FIREWORK_BURST_TIMES[-1] + FIREWORK_SPARK_SECONDS

    def _step(self) -> None:
        now = time.monotonic()
        self.elapsed = now - self.started
        step = min(now - self.previous, 0.05)
        self.previous = now
        for spark in self.sparks:
            age = self.elapsed - spark["born"]
            if 0 <= age < FIREWORK_SPARK_SECONDS:
                spark["vx"] *= max(0.0, 1 - FIREWORK_DRAG * step)
                spark["vy"] = spark["vy"] * max(0.0, 1 - FIREWORK_DRAG * step) + FIREWORK_GRAVITY * step
                spark["x"] += spark["vx"] * step
                spark["y"] += spark["vy"] * step
        # The show also ends early if the window is minimized or hidden, as there is then nothing to draw over
        window = self.parentWidget()
        if self.finished or not window.isVisible() or window.isMinimized():
            self.stop()
            return
        if self.geometry() != window.rect():
            self.setGeometry(window.rect())
        self.raise_()
        self.update()

    def stop(self) -> None:
        self.timer.stop()
        self.hide()
        self.deleteLater()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for spark in self.sparks:
            age = self.elapsed - spark["born"]
            if not 0 <= age < FIREWORK_SPARK_SECONDS:
                continue
            # Each spark is a short streak along its path; near the end of its life it thins and glitters white
            fading = age > FIREWORK_SPARK_SECONDS * 0.6
            glitter = fading and int(age / 0.06) % 2 == 0
            pen = QPen(QColor("#ffffff") if glitter else spark["color"], 1 if fading else 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(spark["x"] - spark["vx"] * FIREWORK_TRAIL_SECONDS, spark["y"] - spark["vy"] * FIREWORK_TRAIL_SECONDS),
                QPointF(spark["x"], spark["y"]),
            )
        painter.end()
