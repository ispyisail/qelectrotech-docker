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


def _in_direction(p: tuple[int, int], ref: tuple[int, int], ori: str) -> bool:
    """Is mark `p` in the expected terminal direction from `ref`?

    The terminal's orientation says which way its item rect extends from
    the terminal position, so the true mark must sit mainly along that
    axis from the approx point. Without this filter, plain
    nearest-mark anchoring snaps a close-but-off computed click onto the
    WRONG terminal whenever a neighbour terminal's mark sits nearer:
    borne_2's drawn marks sit ~5px off their saved positions, so a click
    computed for the top terminal (stock offset (0,-10), measured
    landing ~(3,-6) relative) sat nearer the east mark (~(5,-3)) than
    the top mark, and QET's itemAt() then connected the wire to east --
    three folio-3 wires came out on borne east terminals because of it.
    """
    dx, dy = p[0] - ref[0], p[1] - ref[1]
    if ori == "n":
        return dy < -2 and abs(dy) > abs(dx)
    if ori == "s":
        return dy > 2 and abs(dy) > abs(dx)
    if ori == "e":
        return dx > 2 and abs(dx) > abs(dy)
    if ori == "w":
        return dx < -2 and abs(dx) > abs(dy)
    return False


# A terminal's real mark can sit up to ~10px from the computed click
# (measured-origin error ~5px + drawn-mark offset error ~5px, borne
# B's top mark measured 9.9px off). Marks farther than this in the
# expected direction belong to a DIFFERENT element's terminal (K.bottom
# sits 30px from C.top's mark), so the direction filter must not reach
# them. Below ~4px a mark is essentially AT the click -- the direction
# test can fail there (the mark straddles the click), but such a mark
# is unambiguously the intended one.
_DIR_RADIUS = 12
_AT_CLICK_RADIUS = 4


def find_terminal_near(
    screenshot_path: str | Path, approx_x: int, approx_y: int,
    search_radius: int = 40, orientation: str | None = None,
) -> tuple[int, int] | None:
    """
    Search a `search_radius`-px box around (approx_x, approx_y) in the
    screenshot for a red terminal mark, and return the centroid of the
    chosen cluster of red pixels.

    With `orientation` None (the old behaviour), the cluster nearest the
    approx point wins -- fine when the box holds only one real mark, but
    wrong for close-neighbour terminals (borne top/east are ~9px apart,
    and a computed click can land nearer the other one's mark). With an
    orientation letter, selection is two-tier: marks in the expected
    direction WITHIN _DIR_RADIUS of the approx point win (the radius
    gate stops the filter from leaping to a different element's mark
    when the true mark is not in the expected direction -- e.g. a click
    computed 4px past the terminal jitters the true mark to the "wrong"
    side, and without the gate the filter grabs the next element's
    mark 30px away); if none qualify, marks within _AT_CLICK_RADIUS
    win (a mark essentially AT the click is the intended one even
    though the direction test fails on it); otherwise the plain
    nearest-mark behaviour is kept as a last resort rather than
    returning nothing.

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

    # Direction filter: keep only marks in the expected terminal
    # direction (see _in_direction for the borne top/east case that
    # motivated it), but only among marks within _DIR_RADIUS of the
    # approx point -- farther marks in the same direction belong to a
    # different element's terminal (measured: 29-30px away). A mark
    # exactly on or beside the approx point in the wrong axis can
    # never be the target terminal.
    if orientation is not None:
        click = (approx_x, approx_y)
        directed = [
            p for p in matches
            if _in_direction(p, click, orientation)
            and (p[0] - click[0]) ** 2 + (p[1] - click[1]) ** 2 <= _DIR_RADIUS ** 2
        ]
        if directed:
            matches = directed
        else:
            # No mark in the expected direction within the gate: the
            # computed click can overshoot a terminal by a few px and
            # jitter its mark to the "wrong" side of the click (the
            # true mark's direction test then fails). A mark essentially
            # AT the click is unambiguously the intended one -- pick
            # from those before falling back to plain nearest-mark.
            at_click = [
                p for p in matches
                if (p[0] - click[0]) ** 2 + (p[1] - click[1]) ** 2 <= _AT_CLICK_RADIUS ** 2
            ]
            if at_click:
                matches = at_click

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


def find_red_clusters(
    screenshot_path: str | Path,
    x0: int, y0: int, x1: int, y1: int,
    merge_radius: int = 8,
) -> list[tuple[int, int]]:
    """
    All red terminal-mark clusters inside the box, as centroids.

    Every pixel is sampled (no step): QET's free-terminal marks can be a
    single pixel wide (borne_2's top/bottom marks measured 1px wide at an
    odd x), and step-2 sampling only ever saw even coordinates -- such a
    mark produced zero sampled pixels and was silently dropped, which is
    how tremie_folio3's first run "verified" borne A 62px from where it
    actually sat: with its two narrow marks gone, A's pattern degenerated
    to its east mark and lost the score contest to the Digidrive's
    bottom-row marks 75px away. Greedy clustering: one cluster per
    terminal mark. `merge_radius` must stay below the smallest
    terminal-to-terminal spacing (10px in every element this project
    wires) so adjacent terminals stay distinct clusters -- the whole
    point versus find_terminal_near(), which returns only one mark.
    """
    if Image is None:
        return []
    im = Image.open(screenshot_path).convert("RGB")
    w, h = im.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    px = im.load()
    points = [
        (x, y)
        for y in range(y0, y1)
        for x in range(x0, x1)
        if _is_terminal_red(px[x, y])
    ]
    clusters: list[list[int]] = []   # [sum_x, sum_y, count]
    for px_, py_ in points:
        for c in clusters:
            cx_, cy_, n = c
            if abs(cx_ / n - px_) <= merge_radius and abs(cy_ / n - py_) <= merge_radius:
                c[0] += px_
                c[1] += py_
                c[2] += 1
                break
        else:
            clusters.append([px_, py_, 1])
    return [(round(sx / n), round(sy / n)) for sx, sy, n in clusters if n >= 2]


def locate_element_origin(
    screenshot_path: str | Path,
    approx_origin: tuple[int, int],
    term_offsets: list[tuple[int, int]],
    search_radius: int = 120,
    tol: int = 14,
) -> tuple[int, int] | None:
    """
    Locate an element's real origin by matching its red terminal-offset
    pattern against the red clusters in a `search_radius` box around
    `approx_origin`.

    For every (cluster, offset) pair the implied origin is
    cluster - offset; each candidate scores by how many of the element's
    offsets have an as-yet-unused cluster within `tol` of
    candidate+offset. Best score wins; ties go to the candidate nearest
    approx_origin (placement is at least approximately right, and this
    breaks the tie against a neighbor with the same offset pattern
    inside the box). The origin is then refined to the per-axis median
    of the matched pairs' implied origins -- accurate even when drawn
    marks sit a few px off their .elmt offsets.

    Returns None if fewer than 2 offsets matched, i.e. the element's red
    pattern is not there (terminals that don't render red, or a
    placement that landed far outside the box).
    """
    if Image is None or not term_offsets:
        return None
    ax, ay = approx_origin
    if search_radius is None:
        # Whole screenshot: for elements whose placement offset can be
        # arbitrarily large. The pattern score (number of matched
        # offsets) is what keeps this safe -- a wrong candidate built
        # from noise or another element's marks scores far below the
        # element's own full pattern.
        clusters = find_red_clusters(screenshot_path, 0, 0, 10**9, 10**9)
    else:
        clusters = find_red_clusters(
            screenshot_path,
            ax - search_radius, ay - search_radius,
            ax + search_radius, ay + search_radius,
        )
    if len(clusters) < 2:
        return None

    def _matched_origins(origin: tuple[int, int]) -> list[tuple[int, int]]:
        used: set[int] = set()
        pairs = []
        for ox, oy in term_offsets:
            tx, ty = origin[0] + ox, origin[1] + oy
            for i, (cx, cy) in enumerate(clusters):
                if i in used:
                    continue
                if abs(cx - tx) <= tol and abs(cy - ty) <= tol:
                    used.add(i)
                    pairs.append((cx - ox, cy - oy))
                    break
        return pairs

    best_score, best_dist, best_origin = -1, 0, None
    for cx, cy in clusters:
        for ox, oy in term_offsets:
            origin = (cx - ox, cy - oy)
            score = len(_matched_origins(origin))
            dist = (origin[0] - ax) ** 2 + (origin[1] - ay) ** 2
            if (score, -dist) > (best_score, -best_dist):
                best_score, best_dist, best_origin = score, dist, origin

    if best_origin is None or best_score < 2:
        return None
    pairs = _matched_origins(best_origin)
    xs = sorted(p[0] for p in pairs)
    ys = sorted(p[1] for p in pairs)
    mid = len(xs) // 2
    return (xs[mid], ys[mid])


def screenshot(display: str, out_path: str | Path) -> Path:
    """Take a full screenshot via scrot -- same tool checkpoint() already uses."""
    out_path = Path(out_path)
    subprocess.run(["scrot", "-o", str(out_path)], env={"DISPLAY": display}, check=True)
    return out_path
