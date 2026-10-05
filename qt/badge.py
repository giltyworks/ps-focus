"""The level badge: the level in a red ring, blurred until the user has sent feedback"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

from app_config import COLORS, LEVEL_BADGE_SIZE, LEVEL_BLUR_OPACITY, LEVEL_BLUR_RADIUS

# Qt's blur radius that matches Pillow's Gaussian blur of LEVEL_BLUR_RADIUS, the Tk badge's, found by comparing the two
QT_BLUR_PER_PILLOW_RADIUS = 2.6


def _sharp_badge(level: int, ratio: float) -> QImage:
    side = round(LEVEL_BADGE_SIZE * ratio)
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(COLORS["background"]))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(ratio, ratio)
    # A two-pixel ring two pixels in from the badge's edge, as the Tk badge
    painter.setPen(QPen(QColor(COLORS["red"]), 2))
    painter.drawEllipse(QRectF(3, 3, LEVEL_BADGE_SIZE - 6, LEVEL_BADGE_SIZE - 6))
    font = QFont("Segoe UI")
    font.setPixelSize(13)
    metrics = QFontMetricsF(font)
    text = str(level)
    # Centred across, and down on the middle between the font's ascent and descent, as Pillow's "mm" anchor
    middle = LEVEL_BADGE_SIZE / 2
    # Drawn as a filled outline, which has plain grey edges as Pillow draws them. Text drawn as text gets ClearType's
    # coloured edges on Windows, which would also smear into the blur
    outline = QPainterPath()
    outline.addText(QPointF(middle - metrics.horizontalAdvance(text) / 2, middle + (metrics.ascent() - metrics.descent()) / 2), font, text)
    painter.fillPath(outline, QColor(COLORS["text"]))
    painter.end()
    return image


def render_level_badge(level: int, revealed: bool, ratio: float = 1.0) -> QImage:
    """The badge at this device pixel ratio, ready to draw at LEVEL_BADGE_SIZE logical pixels"""
    image = _sharp_badge(level, ratio)
    if not revealed:
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem()
        item.setPixmap(QPixmap.fromImage(image))
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(LEVEL_BLUR_RADIUS * QT_BLUR_PER_PILLOW_RADIUS * ratio)
        blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        blurred = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
        blurred.fill(QColor(COLORS["background"]))
        painter = QPainter(blurred)
        # Faded towards the background, as the Tk badge
        painter.setOpacity(LEVEL_BLUR_OPACITY)
        scene.render(painter, QRectF(blurred.rect()), QRectF(image.rect()))
        painter.end()
        image = blurred
    image.setDevicePixelRatio(ratio)
    return image
