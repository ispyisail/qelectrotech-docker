"""
termfind — locate a QET terminal's exact screen pixel from a screenshot.

Why this exists
----------------
Computing a terminal's screen position from (element drop point + local
XML offset) is close but not exact: QET's embedded terminal coordinates
in a saved file don't quite match the .elmt source's raw values (e.g.
relais_mono.elmt's XML said y=-20/20, the saved project had -16/16), and
being off by even ~10px was enough for connect_terminals's first click to
miss the terminal entirely -- which matters more than it sounds, because
missing the FIRST click means no wire is even started, so the second
click just silently reselects whatever it lands on instead of failing
loudly.

QET draws an unconnected terminal as a small pure-red mark. Rather than
trust computed geometry, take a screenshot after placement and search a
window around the coarse computed point for that red mark, exactly the
same "verify with pixels, don't trust the math" fix already applied to
Collections-tree row detection (see scenarios/treefind.py).
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

_RED = (255, 0, 0)
_RED_TOLERANCE = 40  # generous: anti-aliased edges aren't pure (255,0,0)


def _is_terminal_red(px: tuple[int, int, int]) -> bool:
    r, g, b = px[:3]
    return r > 255 - _RED_TOLERANCE and g < _RED_TOLERANCE and b < _RED_TOLERANCE


def find_terminal_near(
    screenshot_path: str | Path, approx_x: int, approx_y: int, search_radius: int = 40
) -> tuple[int, int] | None:
    """
    Search a `search_radius`-px box around (approx_x, approx_y) in the
    screenshot for a red terminal mark, and return the centroid of
    whichever cluster of red pixels sits closest to the approx point.

    Returns None if no red pixel is found in the box at all -- callers
    should fall back to the computed point rather than clicking blind.
    """
    if Image is None:
        log.warning("termfind: PIL not available, cannot refine terminal position")
        return None

    im = Image.open(screenshot_path).convert("RGB")
    w, h = im.size
    x0 = max(0, approx_x - search_radius)
    x1 = min(w, approx_x + search_radius)
    y0 = max(0, approx_y - search_radius)
    y1 = min(h, approx_y + search_radius)

    px = im.load()
    matches = []
    for x in range(x0, x1):
        for y in range(y0, y1):
            if _is_terminal_red(px[x, y]):
                matches.append((x, y))

    if not matches:
        return None

    # Anchor on whichever matching pixel is nearest the approx point --
    # this disambiguates between two real terminal marks both inside the
    # search box (e.g. an element's top and bottom terminal columns).
    anchor = min(matches, key=lambda p: (p[0] - approx_x) ** 2 + (p[1] - approx_y) ** 2)

    # Average every matching pixel within a tight radius of the anchor to
    # get a stable centroid instead of a single edge pixel.
    cluster = [p for p in matches if abs(p[0] - anchor[0]) <= 6 and abs(p[1] - anchor[1]) <= 6]
    cx = sum(p[0] for p in cluster) / len(cluster)
    cy = sum(p[1] for p in cluster) / len(cluster)
    return (round(cx), round(cy))


def screenshot(display: str, out_path: str | Path) -> Path:
    """Take a full screenshot via scrot -- same tool checkpoint() already uses."""
    out_path = Path(out_path)
    subprocess.run(["scrot", "-o", str(out_path)], env={"DISPLAY": display}, check=True)
    return out_path
