"""The fbx brand: Free's red, and a terminal rendering of the « f » disc.

The logo is generated, not hand-drawn: a filled disc with an italic f carved
in white, rasterized onto a half-block grid (each cell holds two vertically
stacked "pixels", so the disc comes out round despite terminal cell aspect).
"""

from __future__ import annotations

from rich.text import Text
from textual.theme import Theme

FREE_RED = "#CC0000"
_WHITE = "#F5F5F5"

# The app's own look, in both moods. The primary IS the highlight color
# (textual derives $block-cursor-background from it), so both stay red.
# Light is the default — Freebox OS itself is a light UI, red on white.
FREEBOX_LIGHT = Theme(
    name="freebox-light",
    primary=FREE_RED,
    secondary="#8B1A1A",
    accent=FREE_RED,
    # textual-light's neutrals (Kevin's favourite), red doing the talking.
    surface="#D8D8D8",
    panel="#D0D0D0",
    background="#E0E0E0",
    warning="#B26A00",
    # Not the brand red: errors must still stand apart from the accent.
    error="#B3395B",
    success="#2E7D32",
    dark=False,
    variables={
        "footer-key-foreground": FREE_RED,
    },
)

FREEBOX_DARK = Theme(
    name="freebox-dark",
    primary=FREE_RED,
    secondary="#8B8B8B",
    accent=FREE_RED,
    foreground="#E8E8E8",
    background="#121212",
    surface="#1B1B1B",
    panel="#2A2A2A",
    warning="#F9A825",
    error="#FF5252",
    success="#4CAF50",
    dark=True,
    variables={
        "footer-key-foreground": FREE_RED,
    },
)

# Pixel grid: WIDTH columns × HEIGHT half-rows (2 per text row).
_W, _H = 46, 40
_CX, _CY = _W / 2 - 0.5, _H / 2 - 0.5
_R = _H / 2 - 0.5


def _seg(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distance from point P to segment AB."""
    vx, vy = bx - ax, by - ay
    length2 = vx * vx + vy * vy
    if length2 == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length2))
    qx, qy = ax + t * vx, ay + t * vy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


# The mark is « fbx »: Free's italic f, then our own b and x, smaller.
# Strokes are segments; the b's bowl is a ring. All tuned by eye.
def _segments() -> list[tuple[float, float, float, float, float]]:
    cy = _CY
    fx = _CX - 7.0  # the f sits left of centre to make room for bx
    return [
        # f: stem, gently slanted (italic), top-right to bottom-left
        (fx + 2.8, cy - 11.0, fx - 2.6, cy + 12.0, 3.8),
        # f: top hook, curving right off the stem's top
        (fx + 2.6, cy - 11.2, fx + 6.0, cy - 11.4, 3.2),
        (fx + 5.8, cy - 11.4, fx + 7.8, cy - 9.8, 2.6),
        # f: crossbar
        (fx - 5.6, cy - 1.8, fx + 6.0, cy - 1.8, 3.2),
        # f: bottom curl, trailing left like the italic descender
        (fx - 2.6, cy + 11.8, fx - 5.2, cy + 10.6, 2.8),
    ]


# The b and x are too small for rasterized strokes (they erode into
# speckle): hand-placed pixel-font bitmaps, 2 px stems, shared baseline.
_B_GLYPH = (
    "XX.....",
    "XX.....",
    "XX.....",
    "XX.....",
    "XX.....",
    "XXXXXX.",
    "XXXXXXX",
    "XX...XX",
    "XX...XX",
    "XX...XX",
    "XXXXXXX",
    "XXXXXX.",
)
_X_GLYPH = (
    "XX...XX",
    "XXX.XXX",
    ".XXXXX.",
    "..XXX..",
    "..XXX..",
    ".XXXXX.",
    "XXX.XXX",
    "XX...XX",
)


def _bitmaps() -> list[tuple[int, int, tuple[str, ...]]]:
    # Baseline picked so the small letters' x-height meets the f's crossbar.
    baseline = int(_CY + 6.5)  # integer rows: bitmaps must not straddle pixels
    return [
        (int(_CX + 2.5), baseline - len(_B_GLYPH) + 1, _B_GLYPH),
        (int(_CX + 11.5), baseline - len(_X_GLYPH) + 1, _X_GLYPH),
    ]


def _on_glyph(x: float, y: float) -> bool:
    for ax, ay, bx, by, width in _segments():
        if _seg(x, y, ax, ay, bx, by) <= width / 2:
            return True
    col, row = int(x), int(y)
    for x0, y0, glyph in _bitmaps():
        if 0 <= row - y0 < len(glyph) and 0 <= col - x0 < len(glyph[0]):
            if glyph[row - y0][col - x0] == "X":
                return True
    return False


_SUB = (-1 / 3, 0.0, 1 / 3)


def _pixel(x: int, y: int) -> str | None:
    """Colour of pixel (x, y).

    The disc edge is 3×3-supersampled so the circle comes out round; the
    glyphs are sampled at the pixel centre only — majority-voting thin
    strokes erodes them into speckle, crisp stairs read better.
    """
    inside = sum(
        1
        for ox in _SUB
        for oy in _SUB
        if (x + ox - _CX) ** 2 + (y + oy - _CY) ** 2 <= _R * _R
    )
    if inside < 5:
        return None
    return "W" if _on_glyph(x, y) else "R"


def logo() -> Text:
    """The « f » disc as a Rich Text of half-blocks."""
    colors = {"R": FREE_RED, "W": _WHITE}
    art = Text()
    for row in range(0, _H, 2):
        if row:
            art.append("\n")
        for col in range(_W):
            top, bottom = _pixel(col, row), _pixel(col, row + 1)
            if top is None and bottom is None:
                art.append(" ")
            elif top == bottom:
                art.append("█", style=colors[top])
            elif top is None:
                art.append("▄", style=colors[bottom])
            elif bottom is None:
                art.append("▀", style=colors[top])
            else:
                art.append("▀", style=f"{colors[top]} on {colors[bottom]}")
    return art
