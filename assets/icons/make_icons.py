"""Draw the PS Focus logo and write every icon file made from it

Two designs are kept, chosen by DESIGN below. Both are a soft white disc holding one thick black stroke with
rounded ends:
- "hidden p": the stroke rises from low on the left, turns a rounded corner, crosses the top and curves down
  the right to about 5:30, so the white it encloses reads as a lowercase p. The mark is turned 15 degrees
  anticlockwise and trimmed so the white rim is equally wide all the way round
- "arc": a plain arc from 12 o'clock clockwise to 8 o'clock, like a progress ring filling up

Each size is drawn from the measurements below, several times larger and then reduced, so small icons are
drawn rather than shrunk from the large one. Rerun after changing a measurement, then rebuild:

    py assets/icons/make_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

FOLDER = Path(__file__).resolve().parent
DESIGN = "hidden p"
# Near-black, as in the original logo, on a white dimmed slightly so it is not glaring
ARC_COLOR = (0x08, 0x08, 0x08)
DISC_COLOR = (0xF4, 0xF4, 0xF4)
# All measurements are on a 1024-pixel square. The white disc's radius
DISC_RADIUS = 482
# "hidden p": the stroke's centre line runs up the left side at x = -P_RADIUS from P_START below the middle,
# round a corner of radius P_CORNER, along the top at y = -P_RADIUS, then round a circle of radius P_RADIUS
# to P_END (Pillow's angles, clockwise from 3 o'clock: 90 is 6 o'clock). The stroke is P_HALF either side
P_RADIUS = 272
P_HALF = 128
P_CORNER = 160
P_START = 112
P_END = 81.5
# The whole mark is turned this many degrees anticlockwise, which brings the p's stem round towards the
# bottom so the p sits in the middle; the disc keeps the black centred however far it turns
P_TURN = 15
# After turning, the stroke is moved this far up and right, which lifts the bowl and brings it over the stem.
# The stroke is thicker than the gap to the trim needs, so the trim still keeps the rim even
P_LIFT = 30
P_SHIFT = 12
# The black is trimmed along a circle of this radius, which shaves the top-left corner where it would
# otherwise reach out further than the curves and pinch the white rim. It is the original curves' own reach
# (255 + 112), so the rim is equally wide all the way round
P_TRIM = 367
# How much the sharp point the trim leaves is rounded off
P_TRIM_ROUNDING = 24
# "arc": the arc's outer and inner radii, and where it runs: 270 is 12 o'clock, and 240 degrees on is 8 o'clock
ARC_OUTER = 420
ARC_INNER = 170
ARC_START = 270
ARC_SWEEP = 240
# How much larger each icon is drawn before being reduced, with the drawing kept to at most 4096 pixels
SUPERSAMPLE = 8
MAX_DRAWING = 4096
PNG_SIZES = (512, 256, 128, 64, 48, 32, 24, 20, 16)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def p_centre_line(steps: int = 90) -> list[tuple[float, float]]:
    """The 'hidden p' stroke's centre line, from its low left end to its end at P_END, from the disc's centre"""
    points = [(-P_RADIUS, P_START), (-P_RADIUS, -P_RADIUS + P_CORNER)]
    corner_x = corner_y = -P_RADIUS + P_CORNER
    for step in range(1, steps + 1):
        angle = math.radians(180 + 90 * step / steps)
        points.append((corner_x + P_CORNER * math.cos(angle), corner_y + P_CORNER * math.sin(angle)))
    sweep = (P_END - 270) % 360
    for step in range(steps * 3 + 1):
        angle = math.radians(270 + sweep * step / (steps * 3))
        points.append((P_RADIUS * math.cos(angle), P_RADIUS * math.sin(angle)))
    # Turned anticlockwise on screen, where y runs downwards
    turn = math.radians(-P_TURN)
    return [(x * math.cos(turn) - y * math.sin(turn) + P_SHIFT, x * math.sin(turn) + y * math.cos(turn) - P_LIFT) for x, y in points]


def render_logo(size: int) -> Image.Image:
    """Return the logo as a square RGBA image of this many pixels, transparent around the disc"""
    return (render_hidden_p if DESIGN == "hidden p" else render_arc)(size)


def render_hidden_p(size: int) -> Image.Image:
    supersample = max(1, min(SUPERSAMPLE, MAX_DRAWING // size))
    side = size * supersample
    scale = side / 1024
    centre = side / 2
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    disc = DISC_RADIUS * scale
    draw.ellipse((centre - disc, centre - disc, centre + disc, centre + disc), fill=DISC_COLOR)
    # The stroke is a round brush pressed at short, even steps along the centre line, which keeps its
    # thickness even and rounds both ends. It is drawn as a mask, then trimmed to P_TRIM
    stroke = Image.new("L", (side, side), 0)
    stroke_draw = ImageDraw.Draw(stroke)
    brush = P_HALF * scale
    points = [(centre + x * scale, centre + y * scale) for x, y in p_centre_line()]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        steps = max(1, int(math.dist((x0, y0), (x1, y1)) / max(1.0, brush / 12)))
        for step in range(steps + 1):
            x, y = x0 + (x1 - x0) * step / steps, y0 + (y1 - y0) * step / steps
            stroke_draw.ellipse((x - brush, y - brush, x + brush, y + brush), fill=255)
    trim = Image.new("L", (side, side), 0)
    reach = P_TRIM * scale
    ImageDraw.Draw(trim).ellipse((centre - reach, centre - reach, centre + reach, centre + reach), fill=255)
    stroke = ImageChops.multiply(stroke, trim)
    # Where the trim meets the rounded end on the left it leaves a sharp point; blurring and re-sharpening the
    # stroke rounds that point off, and changes nothing that was already smooth
    stroke = stroke.filter(ImageFilter.GaussianBlur(P_TRIM_ROUNDING * scale)).point(lambda value: 255 if value >= 128 else 0)
    image.paste(Image.new("RGBA", (side, side), ARC_COLOR + (255,)), (0, 0), stroke)
    return image.reduce(supersample)


def render_arc(size: int) -> Image.Image:
    side = size * SUPERSAMPLE
    scale = side / 1024
    centre = side / 2
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def disc(radius: float, fill) -> None:
        draw.ellipse((centre - radius, centre - radius, centre + radius, centre + radius), fill=fill)

    disc(DISC_RADIUS * scale, DISC_COLOR)
    outer = ARC_OUTER * scale
    draw.pieslice((centre - outer, centre - outer, centre + outer, centre + outer), ARC_START, ARC_START + ARC_SWEEP, fill=ARC_COLOR)
    disc(ARC_INNER * scale, DISC_COLOR)
    # Rounded ends: a disc as wide as the arc at each end
    middle, half = (ARC_OUTER + ARC_INNER) / 2 * scale, (ARC_OUTER - ARC_INNER) / 2 * scale
    for angle in (ARC_START, ARC_START + ARC_SWEEP):
        x = centre + middle * math.cos(math.radians(angle))
        y = centre + middle * math.sin(math.radians(angle))
        draw.ellipse((x - half, y - half, x + half, y + half), fill=ARC_COLOR)
    return image.reduce(SUPERSAMPLE)


def preview_on_backgrounds() -> Image.Image:
    """The logo at taskbar sizes on a dark and a light background, to check it reads on both"""
    sheet = Image.new("RGB", (360, 160), "#000000")
    sheet.paste(Image.new("RGB", (360, 80), "#f3f3f3"), (0, 80))
    for row in range(2):
        x = 16
        for size in (64, 48, 32, 16):
            icon = render_logo(size)
            sheet.paste(icon, (x, row * 80 + (80 - size) // 2), icon)
            x += size + 24
    return sheet


def preview_sizes() -> Image.Image:
    """Every size the icon is written at, side by side on the app's background"""
    sizes = (256, 128, 64, 48, 32, 24, 20, 16)
    sheet = Image.new("RGB", (sum(sizes) + 20 * (len(sizes) + 1), 296), "#121212")
    x = 20
    for size in sizes:
        icon = render_logo(size)
        sheet.paste(icon, (x, 20 + (256 - size) // 2), icon)
        x += size + 20
    return sheet


def main() -> None:
    render_logo(1024).save(FOLDER / "PSFocus_Master_1024.png")
    for size in PNG_SIZES:
        render_logo(size).save(FOLDER / f"PSFocus_{size}x{size}.png")
    # Shown by the app: the window and taskbar icons, and the tray icon
    render_logo(16).save(FOLDER / "PSFocus_AppWindow_16.png")
    render_logo(32).save(FOLDER / "PSFocus_AppWindow_32.png")
    render_logo(48).save(FOLDER / "PSFocus_Taskbar_48.png")
    render_logo(64).save(FOLDER / "PSFocus_Settings_64.png")
    # The Windows icon holds each size drawn separately, used for the program, shortcuts and installer
    largest = render_logo(max(ICO_SIZES))
    largest.save(FOLDER / "PSFocus.ico", sizes=[(size, size) for size in ICO_SIZES], append_images=[render_logo(size) for size in ICO_SIZES[:-1]])
    preview_on_backgrounds().save(FOLDER / "PSFocus_Preview_LightDark.png")
    preview_sizes().save(FOLDER / "PSFocus_Preview_Sizes.png")
    print(f"Icons written to {FOLDER}")


if __name__ == "__main__":
    main()
