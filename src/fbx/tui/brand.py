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

# The app's own look: Freebox OS is dark greys with the red doing the talking.
FREEBOX_THEME = Theme(
    name="freebox",
    primary=FREE_RED,
    secondary="#8B8B8B",
    accent=FREE_RED,
    foreground="#E8E8E8",
    background="#121212",
    surface="#1B1B1B",
    panel="#2A2A2A",
    warning="#F9A825",
    # Not the brand red: errors must still stand apart from the accent.
    error="#FF5252",
    success="#4CAF50",
    dark=True,
)

# Pixel grid: WIDTH columns × HEIGHT half-rows (2 per text row).
_W, _H = 34, 32
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


# The italic f, as thick strokes in pixel space (tuned by eye against the
# real logo: gently slanted stem, a hook curving off the top, a crossbar).
def _strokes() -> list[tuple[float, float, float, float, float]]:
    cx, cy = _CX, _CY
    return [
        # stem, gently slanted (italic): top-right to bottom-left
        (cx + 2.6, cy - 9.2, cx - 2.4, cy + 10.5, 3.6),
        # top hook: curves right off the stem's top, tip dipping outward
        (cx + 2.4, cy - 9.4, cx + 5.4, cy - 9.6, 3.0),
        (cx + 5.2, cy - 9.6, cx + 7.0, cy - 8.2, 2.4),
        # crossbar
        (cx - 5.4, cy - 1.4, cx + 5.6, cy - 1.4, 3.2),
        # bottom curl, trailing left like the italic descender
        (cx - 2.4, cy + 10.3, cx - 4.8, cy + 9.2, 2.6),
    ]


def _sample(x: float, y: float) -> str | None:
    dx, dy = x - _CX, y - _CY
    if dx * dx + dy * dy > _R * _R:
        return None
    for ax, ay, bx, by, width in _strokes():
        if _seg(x, y, ax, ay, bx, by) <= width / 2:
            return "W"
    return "R"


_SUB = (-1 / 3, 0.0, 1 / 3)


def _pixel(x: int, y: int) -> str | None:
    """Colour of pixel (x, y) by 3×3 supersampling: majority of W/R/outside."""
    votes = {"W": 0, "R": 0, None: 0}
    for ox in _SUB:
        for oy in _SUB:
            votes[_sample(x + ox, y + oy)] += 1
    if votes[None] >= 5:
        return None
    return "W" if votes["W"] >= votes["R"] else "R"


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
