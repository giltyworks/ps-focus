"""The small flat icons: the award, which in a medal's colour also marks a top week, the flame of the week streak and
the moon of the rest days. Drawn the same as the Tk app's Pillow ones in rendering.py, with Qt's own smoothing"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

from app_config import COLORS

# The award's proportions, as fractions of its size: where the disc sits, how big it is, and the gap under it
AWARD_DISC_Y = 0.34
AWARD_DISC_RADIUS = 0.32
AWARD_GAP = 0.075
AWARD_TAIL = ((0.03, 0.50), (0.25, 0.50), (0.37, 0.96), (0.26, 0.89), (0.15, 1.0))
FLAME_COLOR = "#f28c28"
# Points the flame's outline curves through, as fractions of its size, clockwise from the tip
FLAME_OUTLINE = (
    (0.58, 0.03), (0.70, 0.24), (0.84, 0.48), (0.85, 0.70), (0.72, 0.90), (0.50, 0.97), (0.28, 0.90),
    (0.15, 0.70), (0.18, 0.50), (0.29, 0.34), (0.37, 0.50), (0.45, 0.30), (0.50, 0.14),
)


def _flame_outline() -> QPolygonF:
    """A smooth closed curve through the outline points, traced as many short straight edges"""
    points = []
    count = len(FLAME_OUTLINE)
    for index in range(count):
        before, start, end, after = (FLAME_OUTLINE[(index + offset) % count] for offset in (-1, 0, 1, 2))
        for step in range(12):
            t = step / 12
            x, y = (
                0.5 * (
                    2 * start[axis]
                    + (end[axis] - before[axis]) * t
                    + (2 * before[axis] - 5 * start[axis] + 4 * end[axis] - after[axis]) * t**2
                    + (3 * start[axis] - before[axis] - 3 * end[axis] + after[axis]) * t**3
                )
                for axis in (0, 1)
            )
            points.append(QPointF(x, y))
    return QPolygonF(points)


@lru_cache(maxsize=None)
def icon(kind: str, size: int, background: str, color_name: str = "gold", ratio: float = 1.0) -> QImage:
    """The icon "award", "flame" or "moon" on a square of the background colour, ready to draw at `size` logical
    pixels. The award takes its colour by name, gold unless it is a medal"""
    side = round(size * ratio)
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    # Drawn in fractions of the icon's size
    painter.scale(side, side)

    def disc(x: float, y: float, radius: float, fill: str) -> None:
        painter.setBrush(QColor(fill))
        painter.drawEllipse(QPointF(x, y), radius, radius)

    if kind == "award":
        color = COLORS[color_name]
        painter.setBrush(QColor(color))
        # The tails start behind the disc and fan out below it; each ends in a swallowtail notch
        for mirror in (1, -1):
            painter.drawPolygon(QPolygonF([QPointF(0.5 - mirror * x, y) for x, y in AWARD_TAIL]))
        # A slightly larger disc in the background colour cuts the gap that separates the disc from the tails
        disc(0.5, AWARD_DISC_Y, AWARD_DISC_RADIUS + AWARD_GAP, background)
        disc(0.5, AWARD_DISC_Y, AWARD_DISC_RADIUS, color)
    elif kind == "flame":
        painter.setBrush(QColor(FLAME_COLOR))
        painter.drawPolygon(_flame_outline())
    else:
        # A disc with a second, offset disc of background colour taken out of it leaves the crescent
        disc(0.5, 0.5, 0.44, COLORS["calendar_blue"])
        disc(0.66, 0.40, 0.36, background)
    painter.end()
    image.setDevicePixelRatio(ratio)
    return image
