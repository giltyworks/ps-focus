"""The session story card, painted to an image for sharing: the session's text over a photo the person picks, and the
1080x1920 story that sets the card over a blurred copy of the same photo. Follows design/session-story/README.md;
every measurement there is a share of the card's width, so the card paints the same at any size"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap,
)
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

from app_config import resource_path
from session_story import StoryText

from .icons import icon

STORY_SIZE = QSize(1080, 1920)
# The card is shaped as Runna's shared card is, about 1 wide to 1.58 tall; in the story it takes this share of the
# width, centred, with rounded corners
CARD_ASPECT = 1.58
STORY_CARD_SHARE = 0.81
STORY_CARD_RADIUS = 0.05
# Around the card in the story: the photo enlarged so its blurred edges fall outside the frame, blurred, then darkened
STORY_PHOTO_ZOOM = 1.25
STORY_BLUR = 54
STORY_DARKEN = 0.28
# The card's diffuse shadow in the story, in story pixels: how soft it is and how dark. It sits straight behind the
# card, not dropped below it; and the faint light edge around the card
SHADOW_BLUR = 100
SHADOW_ALPHA = 0.12
EDGE_WIDTH = 3
EDGE_ALPHA = 0.05
# With no photo picked, the card shows the app's own near-black, lifted a little at the top
NO_PHOTO_TOP = "#2b2f2e"
NO_PHOTO_BOTTOM = "#0c0c0c"

# The card's typeface, the same as the rest of PS Focus
FAMILY = "Segoe UI"

# Measurements below are percent of the card's width, as the mock-up's cqw units
PADDING = 7.0
# Over the photo: a little black everywhere, then a fade that darkens the top behind the title and the bottom evenly
# behind every stat, as (position down the card, black's strength)
DIM = 0.11
SCRIM = ((0.0, 0.405), (0.24, 0.095), (0.40, 0.02), (0.54, 0.285), (1.0, 0.3525))
TEXT_COLOR = "#e6e8eb"
# The program line and the stat labels: white, half see-through, so the photo shows through them
SOFT_TEXT_COLOR = "#ffffff"
NUMBER_COLOR = "#ffffff"
LOGO_SIZE = 8.0
LOGO_OPACITY = 0.35
LOGO_GAP = 3.0
# Each kind of text: size, weight (one Segoe UI has: 400, 600 or 700), letter spacing (in ems) and opacity
DATE_FONT = (2.5, 600, 0.12, 1.0)
TITLE_FONT = (5.3, 700, -0.01, 1.0)
PROGRAM_FONT = (4.25, 600, 0.0, 0.5)
LABEL_FONT = (3.8, 600, 0.0, 0.5)
NUMBER_FONT = (12.4, 700, -0.045, 1.0)
# How much heavier the small text (not the title or the big numbers, which are heavy enough) is drawn than Qt's plain
# drawing, as the width of an added outline in ems of the text
EMBOLDEN = 0.03
NUMBER_EMBOLDEN = 0.0
# The date's frosted pill: its padding in ems of the date, the white over the blurred photo, and how soft the blur is
PILL_PADDING = (1.1, 0.4)
# How much shorter the pill is than the box the text is laid out in, trimmed from its top and bottom, in ems of the date
PILL_TRIM = 0.1
PILL_WHITE = 0.28
PILL_BLUR = 3.0
# Gaps: under the pill, under the title, between a label and its number, and between stats
PILL_GAP = 3.0
TITLE_GAP = 1.1
LABEL_GAP = 0.0
STAT_GAP = 4.5
# Line heights in ems, as the mock-up's CSS gave them
TITLE_LINE = 1.1
NUMBER_LINE = 0.95
# The award beside the records count: its size, and the gap before it, in ems of the number
AWARD_SIZE = 0.66
AWARD_GAP = 0.18


def story_font(unit: float, spec: tuple, scale: float = 1.0, tabular: bool = False) -> QFont:
    size, weight, spacing, _opacity = spec
    pixels = size * unit * scale
    result = QFont(FAMILY)
    result.setPixelSize(max(1, round(pixels)))
    result.setWeight(QFont.Weight(weight))
    result.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing * pixels)
    # Large text drawn to an image to be scaled again by the phone, so no snapping to the pixel grid
    result.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if tabular:
        result.setFeature(QFont.Tag("tnum"), 1)
    return result


def blurred(image: QImage, radius: float) -> QImage:
    """A smooth Gaussian blur, done by Qt's own blur effect. The image is first padded by stretching its edges, so the
    blur does not fade to see-through at the borders, and the padding is cut off again afterwards"""
    width, height = image.width(), image.height()
    margin = round(radius * 2)
    padded = QImage(width + 2 * margin, height + 2 * margin, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(padded)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(padded.rect(), image)
    painter.drawImage(margin, margin, image)
    painter.end()
    item = QGraphicsPixmapItem(QPixmap.fromImage(padded))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene = QGraphicsScene()
    scene.addItem(item)
    result = QImage(padded.size(), QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(result.rect()), QRectF(padded.rect()))
    painter.end()
    return result.copy(margin, margin, width, height)


def covered(photo: QImage, size: QSize, zoom: float = 1.0) -> QImage:
    """The photo scaled to fill the size, enlarged by the zoom, and cut to it from the middle"""
    scale = max(size.width() / photo.width(), size.height() / photo.height()) * zoom
    scaled = photo.scaled(max(1, round(photo.width() * scale)), max(1, round(photo.height() * scale)),
                          Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    left = (scaled.width() - size.width()) // 2
    top = (scaled.height() - size.height()) // 2
    return scaled.copy(left, top, size.width(), size.height())


def _background(photo: QImage | None, size: QSize) -> QImage:
    if photo is not None and not photo.isNull():
        return covered(photo, size).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 0, size.height())
    gradient.setColorAt(0, QColor(NO_PHOTO_TOP))
    gradient.setColorAt(1, QColor(NO_PHOTO_BOTTOM))
    painter.fillRect(image.rect(), gradient)
    painter.end()
    return image


def _text_color(name: str, opacity: float) -> QColor:
    result = QColor(name)
    result.setAlphaF(opacity)
    return result


def _fitted_font(unit: float, spec: tuple, text: str, room: float) -> QFont:
    """The font at its size, or smaller if the text would not otherwise fit on one line"""
    font = story_font(unit, spec)
    width = QFontMetricsF(font).horizontalAdvance(text)
    return font if width <= room or width <= 0 else story_font(unit, spec, room / width)


def _baseline(top: float, line: float, metrics: QFontMetricsF) -> float:
    """Where text sits in a line box of the given height, as CSS centres it"""
    return top + (line - metrics.ascent() - metrics.descent()) / 2 + metrics.ascent()


def draw_heavy_text(painter: QPainter, point: QPointF, text: str, font: QFont, color: QColor, embolden: float = EMBOLDEN) -> None:
    """Text drawn a touch heavier than Qt's plain drawing, which leaves light text on a photo thinner than a browser
    shows it. The letters' outline is thickened and filled once, so a see-through colour does not darken where the
    two overlap"""
    letters = QPainterPath()
    letters.addText(point, font, text)
    if embolden <= 0:
        painter.fillPath(letters, color)
        return
    stroker = QPainterPathStroker()
    stroker.setWidth(embolden * font.pixelSize())
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.fillPath(letters.united(stroker.createStroke(letters)), color)


@lru_cache(maxsize=1)
def hollow_logo() -> QImage:
    """The app's logo as white only: its black stroke and the space around the disc become see-through, so the photo
    shows through them. A null image if the logo cannot be read. Made once, and only drawn from"""
    logo = QImage(str(resource_path("assets/icons/PSFocus_256x256.png")))
    if logo.isNull():
        return logo
    # On black, the logo's brightness is how much white to keep
    flat = QImage(logo.size(), QImage.Format.Format_ARGB32_Premultiplied)
    flat.fill(Qt.GlobalColor.black)
    painter = QPainter(flat)
    painter.drawImage(0, 0, logo)
    painter.end()
    result = QImage(logo.size(), QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.white)
    result.setAlphaChannel(flat.convertToFormat(QImage.Format.Format_Grayscale8))
    return result


def render_card(width: int, photo: QImage | None, text: StoryText) -> QImage:
    """The card on its own, as wide as asked, in the story card's shape"""
    height = round(width * CARD_ASPECT)
    unit = width / 100
    padding = PADDING * unit
    image = _background(photo, QSize(width, height))
    painter = QPainter(image)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    painter.fillRect(image.rect(), QColor(0, 0, 0, round(DIM * 255)))
    scrim = QLinearGradient(0, 0, 0, height)
    for position, strength in SCRIM:
        scrim.setColorAt(position, QColor(0, 0, 0, round(strength * 255)))
    painter.fillRect(image.rect(), scrim)

    # Top right: the logo, faint, as Runna's
    logo = hollow_logo()
    logo_size = LOGO_SIZE * unit
    if not logo.isNull():
        painter.setOpacity(LOGO_OPACITY)
        painter.drawImage(QRectF(width - padding - logo_size, padding, logo_size, logo_size), logo)
        painter.setOpacity(1)
    room = width - 2 * padding - logo_size - LOGO_GAP * unit

    # Top left: the date in its frosted pill, the title, then the programs
    top = padding
    if text.date:
        date_font = story_font(unit, DATE_FONT)
        metrics = QFontMetricsF(date_font)
        em = date_font.pixelSize()
        box = QRectF(padding, top, metrics.horizontalAdvance(text.date) + 2 * PILL_PADDING[0] * em,
                     metrics.ascent() + metrics.descent() + 2 * PILL_PADDING[1] * em)
        # The pill is a little shorter than the box the text and the rest of the card are laid out by
        pill = box.adjusted(0, PILL_TRIM * em, 0, -PILL_TRIM * em)
        path = QPainterPath()
        path.addRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        # Frosted: what is behind the pill, blurred, then lightened
        margin = round(PILL_BLUR * unit * 2)
        behind = pill.toAlignedRect().adjusted(-margin, -margin, margin, margin).intersected(image.rect())
        frost = blurred(image.copy(behind), PILL_BLUR * unit)
        painter.save()
        painter.setClipPath(path)
        painter.drawImage(behind.topLeft(), frost)
        painter.fillPath(path, QColor(255, 255, 255, round(PILL_WHITE * 255)))
        painter.restore()
        draw_heavy_text(painter, QPointF(box.left() + PILL_PADDING[0] * em, box.top() + PILL_PADDING[1] * em + metrics.ascent()),
                        text.date, date_font, _text_color(TEXT_COLOR, DATE_FONT[3]))
        top = box.bottom() + PILL_GAP * unit
    title_font = _fitted_font(unit, TITLE_FONT, text.title, room)
    title_line = TITLE_LINE * TITLE_FONT[0] * unit
    draw_heavy_text(painter, QPointF(padding, _baseline(top, title_line, QFontMetricsF(title_font))), text.title,
                    title_font, _text_color(TEXT_COLOR, TITLE_FONT[3]), 0.0)
    top += title_line + TITLE_GAP * unit
    program_font = story_font(unit, PROGRAM_FONT)
    program_metrics = QFontMetricsF(program_font)
    programs = program_metrics.elidedText(text.programs, Qt.TextElideMode.ElideRight, width - 2 * padding)
    draw_heavy_text(painter, QPointF(padding, top + program_metrics.ascent()), programs, program_font,
                    _text_color(SOFT_TEXT_COLOR, PROGRAM_FONT[3]))

    # Bottom left, one column: Records when earned, Focus time, Started
    stats = []
    if text.record_count:
        stats.append(("Records", str(text.record_count), True))
    stats.append(("Time", text.focus_time, False))
    if text.started:
        stats.append(("Started", text.started, False))
    label_font = story_font(unit, LABEL_FONT)
    label_metrics = QFontMetricsF(label_font)
    number_font = story_font(unit, NUMBER_FONT, tabular=True)
    number_metrics = QFontMetricsF(number_font)
    number_size = NUMBER_FONT[0] * unit
    number_line = NUMBER_LINE * number_size
    label_line = label_metrics.ascent() + label_metrics.descent()
    stat_height = label_line + LABEL_GAP * unit + number_line
    top = height - padding - len(stats) * stat_height - (len(stats) - 1) * STAT_GAP * unit
    for label, value, with_award in stats:
        draw_heavy_text(painter, QPointF(padding, top + label_metrics.ascent()), label, label_font,
                        _text_color(SOFT_TEXT_COLOR, LABEL_FONT[3]))
        number_top = top + label_line + LABEL_GAP * unit
        draw_heavy_text(painter, QPointF(padding, _baseline(number_top, number_line, number_metrics)), value, number_font,
                        QColor(NUMBER_COLOR), NUMBER_EMBOLDEN)
        if with_award:
            # The app's own award, as the Stats block and the day overview show it, beside the count
            award_size = max(1, round(AWARD_SIZE * number_size))
            award = icon("award", award_size, "", "gold")
            left = padding + number_metrics.horizontalAdvance(value) + AWARD_GAP * number_size
            painter.drawImage(QPointF(left, number_top + (number_line - award_size) / 2), award)
        top += stat_height + STAT_GAP * unit
    painter.end()
    return image


def render_story(photo: QImage | None, text: StoryText) -> QImage:
    """The 1080x1920 story: the card sits in the middle over a blurred, darkened copy of its photo, as Runna's shared
    cards do"""
    story = QImage(STORY_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(story)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    if photo is not None and not photo.isNull():
        painter.drawImage(0, 0, blurred(covered(photo, STORY_SIZE, STORY_PHOTO_ZOOM), STORY_BLUR))
        painter.fillRect(story.rect(), QColor(0, 0, 0, round(STORY_DARKEN * 255)))
    else:
        painter.drawImage(0, 0, _background(None, STORY_SIZE))
    card_width = round(STORY_SIZE.width() * STORY_CARD_SHARE / 2) * 2
    card = render_card(card_width, photo, text)
    frame = QRectF((STORY_SIZE.width() - card.width()) / 2, (STORY_SIZE.height() - card.height()) // 2, card.width(), card.height())
    radius = STORY_CARD_RADIUS * STORY_SIZE.width()

    # The shadow: a dark rounded box the card's size, blurred soft
    shadow = QImage(STORY_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    shadow.fill(Qt.GlobalColor.transparent)
    shadow_painter = QPainter(shadow)
    shadow_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shadow_painter.setPen(Qt.PenStyle.NoPen)
    shadow_painter.setBrush(QColor(0, 0, 0, round(SHADOW_ALPHA * 255)))
    shadow_painter.drawRoundedRect(frame, radius, radius)
    shadow_painter.end()
    painter.drawImage(0, 0, blurred(shadow, SHADOW_BLUR / 2))

    path = QPainterPath()
    path.addRoundedRect(frame, radius, radius)
    painter.save()
    painter.setClipPath(path)
    painter.drawImage(frame.topLeft(), card)
    painter.restore()
    painter.setPen(QPen(QColor(255, 255, 255, round(EDGE_ALPHA * 255)), EDGE_WIDTH))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    edge = EDGE_WIDTH / 2
    painter.drawRoundedRect(frame.adjusted(-edge, -edge, edge, edge), radius + edge, radius + edge)
    painter.end()
    return story
