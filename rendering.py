"""Pillow rendering of the level badge, the small flat icons, and the usage line chart"""

from __future__ import annotations

import base64
import io
import tkinter as tk

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from app_config import CHART_FILL_OPACITY, COLORS, LEVEL_BADGE_SIZE, LEVEL_BLUR_OPACITY, LEVEL_BLUR_RADIUS

# Award badge proportions, as fractions of its size: where the disc sits, how big it is, and the gap under it
AWARD_DISC_Y = 0.34
AWARD_DISC_RADIUS = 0.32
AWARD_GAP = 0.075
# The whole badge is one flat gold; the gap alone separates the disc from the ribbons
AWARD_COLOR = COLORS["gold"]
FLAME_COLOR = "#f28c28"
CRESCENT_COLOR = COLORS["calendar_blue"]
# Points the flame's outline curves through, as fractions of its size, clockwise from the tip
FLAME_OUTLINE = (
    (0.58, 0.03), (0.70, 0.24), (0.84, 0.48), (0.85, 0.70), (0.72, 0.90), (0.50, 0.97), (0.28, 0.90),
    (0.15, 0.70), (0.18, 0.50), (0.29, 0.34), (0.37, 0.50), (0.45, 0.30), (0.50, 0.14),
)


def render_level_badge(level: int, revealed: bool) -> Image.Image:
    scale = 4
    size = LEVEL_BADGE_SIZE * scale
    image = Image.new("RGB", (size, size), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.ellipse((2 * scale, 2 * scale, size - 2 * scale, size - 2 * scale), outline=COLORS["red"], width=2 * scale)
    # 10 point text is about 13 pixels tall on a standard display
    font_size = 13 * scale
    try:
        font = ImageFont.truetype("segoeui.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(font_size)
    draw.text((size / 2, size / 2), str(level), fill=COLORS["text"], font=font, anchor="mm")
    if not revealed:
        image = image.filter(ImageFilter.GaussianBlur(LEVEL_BLUR_RADIUS * scale))
        image = Image.blend(Image.new("RGB", image.size, COLORS["background"]), image, LEVEL_BLUR_OPACITY)
    return image.resize((LEVEL_BADGE_SIZE, LEVEL_BADGE_SIZE), Image.LANCZOS)


def render_award_badge(size: int, background: str, color: str = AWARD_COLOR) -> Image.Image:
    """Draw a simple award in one flat colour: a plain disc, a thin gap, then two ribbon tails beneath it"""
    scale = 8
    side = size * scale

    def at(x: float, y: float) -> tuple[float, float]:
        return x * side, y * side

    def disc(radius: float, fill: str) -> None:
        draw.ellipse((*at(0.5 - radius, AWARD_DISC_Y - radius), *at(0.5 + radius, AWARD_DISC_Y + radius)), fill=fill)

    image = Image.new("RGB", (side, side), background)
    draw = ImageDraw.Draw(image)
    # The tails start behind the disc and fan out below it; each ends in a swallowtail notch
    for mirror in (1, -1):
        tail = ((0.03, 0.50), (0.25, 0.50), (0.37, 0.96), (0.26, 0.89), (0.15, 1.0))
        draw.polygon([at(0.5 - mirror * x, y) for x, y in tail], fill=color)
    # A slightly larger disc in the background colour cuts the gap that separates the disc from the tails
    disc(AWARD_DISC_RADIUS + AWARD_GAP, background)
    disc(AWARD_DISC_RADIUS, color)
    # Shrunk by plain averaging: sharper methods overshoot at edges, which would tint the flat colour
    return image.reduce(scale)


def render_flame_icon(size: int, background: str) -> Image.Image:
    """Draw a flat orange flame in the same plain style as the award badge"""
    scale = 8
    side = size * scale
    # A smooth closed curve through the outline points, traced as many short straight edges
    outline = []
    count = len(FLAME_OUTLINE)
    for index in range(count):
        before, start, end, after = (FLAME_OUTLINE[(index + offset) % count] for offset in (-1, 0, 1, 2))
        for step in range(12):
            t = step / 12
            outline.append(tuple(
                side * 0.5 * (
                    2 * start[axis]
                    + (end[axis] - before[axis]) * t
                    + (2 * before[axis] - 5 * start[axis] + 4 * end[axis] - after[axis]) * t**2
                    + (3 * start[axis] - before[axis] - 3 * end[axis] + after[axis]) * t**3
                )
                for axis in (0, 1)
            ))
    image = Image.new("RGB", (side, side), background)
    ImageDraw.Draw(image).polygon(outline, fill=FLAME_COLOR)
    return image.reduce(scale)


def render_crescent_icon(size: int, background: str) -> Image.Image:
    """Draw a flat blue crescent moon in the same plain style as the award badge"""
    scale = 8
    side = size * scale
    image = Image.new("RGB", (side, side), background)
    draw = ImageDraw.Draw(image)
    # A disc with a second, offset disc of background colour taken out of it leaves the crescent
    for center_x, center_y, radius, color in ((0.5, 0.5, 0.44, CRESCENT_COLOR), (0.66, 0.40, 0.36, background)):
        draw.ellipse(
            ((center_x - radius) * side, (center_y - radius) * side, (center_x + radius) * side, (center_y + radius) * side),
            fill=color,
        )
    return image.reduce(scale)


def render_rounded_box(
    width: int, height: int, radius: int, fill: str, outline: str, background: str, outline_width: int = 1
) -> Image.Image:
    """Draw a flat rounded rectangle with an outline, on the colour of the surface it sits on"""
    scale = 8
    image = Image.new("RGB", (width * scale, height * scale), background)
    draw = ImageDraw.Draw(image)
    # The outline is the whole shape in the outline colour with a smaller shape in the fill colour on top
    for inset, color in ((0, outline), (outline_width, fill)):
        draw.rounded_rectangle(
            (inset * scale, inset * scale, (width - inset) * scale - 1, (height - inset) * scale - 1),
            radius=(radius - inset) * scale,
            fill=color,
        )
    return image.reduce(scale)


def to_photo_image(image: Image.Image) -> tk.PhotoImage:
    """Convert a rendered image for use in a Tk label; the caller must keep a reference to it"""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return tk.PhotoImage(data=base64.b64encode(buffer.getvalue()))


def render_line_chart(
    width: int,
    height: int,
    points: list[tuple[float, float]],
    baseline: float,
    gridlines: list[tuple[float, float, float]],
) -> Image.Image:
    scale = 2
    size = (width * scale, height * scale)
    image = Image.new("RGB", size, COLORS["panel"])
    draw = ImageDraw.Draw(image)
    for left, right, y in gridlines:
        draw.line((left * scale, y * scale, right * scale, y * scale), fill=COLORS["border"], width=scale)
    scaled = [(x * scale, y * scale) for x, y in points]
    if len(scaled) >= 2:
        base = baseline * scale
        peak = min(y for _, y in scaled)
        span = max(1.0, base - peak)
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).polygon(scaled + [(scaled[-1][0], base), (scaled[0][0], base)], fill=255)
        # The fill fades from the line colour at the highest point to nothing at the baseline
        fade = bytes(int(255 * CHART_FILL_OPACITY * max(0.0, min(1.0, (base - y) / span))) for y in range(size[1]))
        alpha = ImageChops.multiply(mask, Image.frombytes("L", (1, size[1]), fade).resize(size))
        image.paste(Image.new("RGB", size, COLORS["calendar_blue"]), mask=alpha)
        draw.line(scaled, fill=COLORS["calendar_blue"], width=2 * scale, joint="curve")
    if scaled:
        x, y = scaled[-1]
        for radius, color in ((4.5 * scale, COLORS["panel"]), (3 * scale, COLORS["calendar_blue"])):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    return image.resize((width, height), Image.LANCZOS)
