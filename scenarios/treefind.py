"""
treefind — locate the first *element* row in QET's filtered Collections tree.

Why this is needed
------------------
After typing into the Collections filter box, QET expands the tree to reveal
matches. The matches are NOT at a fixed offset below the filter box: the tree
first shows however many nested *category* rows lead to them, and that depth
varies per search term:

    QET Collection            <- category
      Electric                <- category
        All-pole              <- category
          Fuses and ...       <- category
            Thermal relays    <- category
              [Thermal relay] <- first ELEMENT, the thing we want

A fixed pixel offset lands on a category folder, which selects/expands
something instead of inserting an element -- and does so silently, which is
exactly the failure that made an earlier version of this harness report
"placed" for elements it never placed.

How rows are told apart
-----------------------
Measured from real screenshots of the filtered tree (see the module
self-test at the bottom, which runs against checked-in captures):

  * category rows indent progressively in ~20px steps -- leftmost dark
    pixel at x = 9, 29, 49, 69, 89, ... -- and are ~13-21px apart vertically.
  * element rows carry a thumbnail, so they are ~31-57px apart vertically.

The *vertical gap* is the reliable signal; absolute indent is not, because
it depends on how deeply the match happens to be nested. Measured first-
element rows across three real searches:

    "Thermal relay"       y=298  indent=126  gap=31   (5 categories deep)
    "Contactor CRM"       y=286  indent=116  gap=37   (4 categories deep)
    "Three-phase engine"  y=302  indent=136  gap=33   (5 categories deep)

An earlier version required indent >= 120 and silently failed on
"Contactor CRM" (indent 116, one level shallower), falling through to a
row 370px lower -- in the *Auto numbering* panel below the tree, because
the scan region also ran past the tree's bottom edge. Hence both the
lower indent threshold and the tree-boundary detection below.

This works on pixels rather than any Qt introspection because xdotool gives
us no access to the widget tree -- but it is validated offline against
saved captures rather than only live, so a regression here is catchable
without a running GUI.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# A pixel darker than this counts as content rather than background.
_DARK = 140
# Minimum dark pixels in a scanline for it to be part of a row.
_MIN_ROW_PIXELS = 3
# A row must be at least this tall to be considered (filters out 1-2px
# separator artefacts).
_MIN_BAND_HEIGHT = 6
# Element rows are indented at least this far. Deliberately loose: the
# real discriminator is _MIN_ELEMENT_GAP. Deepest observed *category*
# indent is 109, shallowest observed *element* indent is 116.
_MIN_ELEMENT_INDENT = 100
# Element rows are separated from the row above by more than this; category
# rows are 13-21px apart, element rows 31-57px.
_MIN_ELEMENT_GAP = 25
# A row at or left of this, appearing *after* tree content, means we have
# scanned past the bottom of the tree widget into the docks below it
# ("Selection properties" / "Auto numbering selection"). Those panels
# contain deeply-indented, widely-spaced rows that otherwise look exactly
# like element rows.
_TREE_EXIT_INDENT = 10
# The primary element signal: an element's label starts this much further
# right than the previous row's. Category rows nest in ~20px steps; an
# element row adds a thumbnail column on top, so its label jumps >=27px
# (measured: 38, 44, 43, 93 across two runs; category steps 20). The old
# vertical-gap heuristic is NOT reliable -- element gaps measure 18-48px
# and category gaps 13-21px, overlapping ("Digidrive sk" sits 18px below
# its parent and a 25px gap threshold misses it by design).
_ELEMENT_INDENT_JUMP = 25
# Dock-panel title bars below the tree are full-width tinted bars ~11px
# tall; they mark "scanned past the tree" when no element matched.
_PANEL_TITLE_MAX_HEIGHT = 20
# Backgrounds brighter than this read as plain white; panel title bars are
# visibly tinted and read below it. (The tree's own header row can be
# grey-tinted in some styles, so this rule also requires the band to not
# be the first one -- the header is always the first band.)
_NEAR_WHITE = 250
# A SELECTED row renders as a full-width highlight band: the highlight
# background (~134 grey) counts as dark, so the band spans the whole row
# width and has neither the element indent (~116+) nor the element gap
# (~25+) signal. Selected *element* rows are still told apart by height:
# they carry a thumbnail, so the highlight band is ~42px tall, while a
# selected category's is ~19-21px. Measured from the 2026-08-15
# shift-override run (03/05 = unselected text bands at indent 163/183,
# 07/09 = selected element bands y282-324).
_MIN_ELEMENT_ROW_HEIGHT = 35
# Sibling match rows (same directory, same depth) share their label
# indent; text antialiasing wobbles the text left edge by up to 8px
# (measured: 163/171 alternating across four "Switch 2 positions"
# siblings). Category rows nest in ~20px steps, so 10 still separates
# them. Anything further left is a category (parents of a further
# match group) and must not be taken for a sibling.
_SIBLING_INDENT_TOL = 10
# How wide a full-row highlight band is. Text bands never get this wide
# (observed max 201px); the tree header and panel rows below the tree do
# span this wide but are far shorter than _MIN_ELEMENT_ROW_HEIGHT.
_FULL_ROW_SPAN = 300


@dataclass
class Band:
    y0: int          # absolute screen y, top of the row's content
    y1: int          # absolute screen y, bottom
    left: int        # leftmost dark pixel, relative to the region's x0
    right: int

    @property
    def cy(self) -> int:
        return (self.y0 + self.y1) // 2


def find_bands(image_path: str | Path, x0: int, y0: int, x1: int, y1: int) -> list[Band]:
    """Horizontal content bands (candidate tree rows) inside the region."""
    im = Image.open(str(image_path)).convert("L")
    reg = im.crop((x0, y0, x1, y1))
    w, h = reg.size
    px = reg.load()

    per_row: list[list[int]] = []
    for y in range(h):
        per_row.append([x for x in range(w) if px[x, y] < _DARK])

    bands: list[Band] = []
    in_run = False
    start = 0
    for i, xs in enumerate(per_row):
        if len(xs) > _MIN_ROW_PIXELS and not in_run:
            in_run, start = True, i
        elif len(xs) <= _MIN_ROW_PIXELS and in_run:
            in_run = False
            if i - start >= _MIN_BAND_HEIGHT:
                allx = [x for j in range(start, i) for x in per_row[j]]
                bands.append(Band(y0 + start, y0 + i, min(allx), max(allx)))
    return bands


def _band_bg(reg: Image.Image, b: Band, y0: int) -> int:
    """Grayscale of the pixel just right of the band's left edge."""
    px = reg.load()
    x = b.left + 5
    y = b.cy - y0
    w, h = reg.size
    if not (0 <= x < w and 0 <= y < h):
        return 255
    return px[x, y]


# How many dark pixels a column needs before it counts as glyph text
# rather than the tree's sparse branch-guide dots (a dot column holds at
# most 2-4 dark pixels; a 1px-wide glyph stem in a >=10px band holds 6+).
_TEXT_MIN_COLUMN_PIXELS = 5


def _text_left(reg: Image.Image, b: Band, y0: int) -> int:
    """
    Left edge of the band's *text*, ignoring the tree's branch-guide
    dots. The raw band `left` is the leftmost dark pixel of anything in
    the band -- for deep rows that is often a 1-2px guide dot, whose x
    position jitters per row (measured 128-149 across four sibling rows
    whose text all starts at the same x). Comparing raw lefts with an 8px
    sibling tolerance therefore skipped rows: the "Switch 2 positions"
    family has four same-name matches and element_rows returned three,
    silently dropping contact_002. The first column dense enough to be a
    glyph stem is stable across siblings (wobble <= 8px from
    antialiasing). Falls back to `b.left` when the region image is not
    available or nothing is dense enough.
    """
    if reg is None:
        return b.left
    px = reg.load()
    by0 = max(0, b.y0 - y0)
    by1 = min(reg.size[1] - 1, b.y1 - y0)
    if by1 <= by0:
        return b.left
    for x in range(b.left, b.right + 1):
        n = sum(1 for y in range(by0, by1) if px[x, y] < _DARK)
        if n >= _TEXT_MIN_COLUMN_PIXELS:
            return x
    return b.left


def first_element_row(
    bands: list[Band], reg: Image.Image | None = None, y0: int = 0
) -> Band | None:
    """
    The first band that looks like an element rather than a category.

    Signals, strongest first:
      - a selected row's full-width, thumbnail-height highlight band,
      - an indent jump: the label starts >= _ELEMENT_INDENT_JUMP further
        right than the previous row's (category rows nest in ~20px steps;
        an element row adds a thumbnail column on top),
      - (fallback) the original indent + vertical-gap heuristics.

    Stops at the bottom of the tree widget: a tinted full-width bar no
    taller than a title (the docks below the tree) means the scan has run
    past the tree, and anything past that point must not be treated as a
    candidate no matter how element-like it looks. This also covers the
    "filter matched nothing" case, where the tree body is empty and the
    first content rows belong to the panels below.
    """
    seen_indented = False
    for i, b in enumerate(bands):
        span = b.right - b.left
        height = b.y1 - b.y0
        # Selected element row: full-width highlight band, tall enough to
        # carry a thumbnail. Check before every other rule -- its left edge
        # is the highlight background (which can reach the region's very
        # left edge, left=0, in the Docker geometry), not the text, so the
        # indent and tree-exit signals are gone. A selected *category* row
        # fails the height test and falls through.
        if span >= _FULL_ROW_SPAN and height >= _MIN_ELEMENT_ROW_HEIGHT:
            return b
        if b.left <= _TREE_EXIT_INDENT and seen_indented:
            return None          # scanned past the tree; no element found
        if b.left > _TREE_EXIT_INDENT:
            seen_indented = True
        # Dock-panel title bar below the tree: full-width, tinted, short,
        # not the first band (the tree header is also grey-tinted in some
        # styles, but it is always the first band).
        if (i > 0 and span >= _FULL_ROW_SPAN and b.left < _MIN_ELEMENT_INDENT
                and height < _PANEL_TITLE_MAX_HEIGHT
                and reg is not None and _band_bg(reg, b, y0) < _NEAR_WHITE):
            return None
        # Indent jump: the element signal proper. Checked after the
        # panel-title rule so that, with an empty filter result, the
        # panels below the tree read as "no match" instead of an element.
        if i > 0 and b.left - bands[i - 1].left >= _ELEMENT_INDENT_JUMP:
            return b
        if b.left < _MIN_ELEMENT_INDENT:
            continue
        if i == 0:
            return b
        if b.y0 - bands[i - 1].y0 > _MIN_ELEMENT_GAP:
            return b
    return None


def element_rows(
    bands: list[Band], reg: Image.Image | None = None, y0: int = 0
) -> list[Band]:
    """
    All element rows in the filtered tree, top to bottom.

    After the first element row (located with first_element_row's full
    signal set), sibling matches continue as consecutive bands with the
    same label indent (all matches of one search live in one directory,
    so no category row separates them); a selected row renders as a
    full-width highlight band instead and is recognised by its span +
    height. Sibling indent is compared on the text left edge
    (_text_left), not the raw band edge, which carries the tree's
    jittering branch-guide dots. When the indent drops (a category
    chain of a further match group), the scan falls back to
    first_element_row's indent-jump signal from that point.
    """
    rows: list[Band] = []
    i = 0
    while i < len(bands):
        found: Band | None = None
        if rows:
            # Sibling continuation: same-indent band, or selected
            # full-width band, before any indent drop. Indent is compared
            # on the *text* left edge -- the raw band left edge picks up
            # the tree's branch-guide dots, which jitter per row and made
            # same-name siblings look 13px apart (see _text_left).
            prev_left = _text_left(reg, rows[-1], y0) if reg is not None else rows[-1].left
            for j in range(i, len(bands)):
                b = bands[j]
                span = b.right - b.left
                if span >= _FULL_ROW_SPAN and b.y1 - b.y0 >= _MIN_ELEMENT_ROW_HEIGHT:
                    found, i = b, j + 1
                    break
                # Full-width short band at the region's left edge: the scan
                # has run past the tree into the docks below it (panel title
                # bars and their content rows are full-width, ~10-14px tall,
                # and reach the region's left edge -- a selected element row
                # also spans full width but is thumbnail-height, caught by
                # the rule above). Without this, the sibling-indent test
                # takes every panel row for a sibling of a selected row
                # (both have left ~2), inflating the element count.
                if (b.left <= _TREE_EXIT_INDENT and span >= _FULL_ROW_SPAN
                        and b.y1 - b.y0 < _MIN_ELEMENT_ROW_HEIGHT):
                    break
                b_left = _text_left(reg, b, y0) if reg is not None else b.left
                if abs(b_left - prev_left) <= _SIBLING_INDENT_TOL:
                    found, i = b, j + 1
                    break
                if b_left < prev_left - _SIBLING_INDENT_TOL:
                    break
        if found is None:
            row = first_element_row(bands[i:], reg, y0)
            if row is None:
                break
            found = row
            while i < len(bands) and bands[i] is not row:
                i += 1
            i += 1
        rows.append(found)
    return rows


def locate_nth_element(
    display: str,
    region: tuple[int, int, int, int],
    index: int,
    screenshot_path: str | Path | None = None,
) -> tuple[int, int] | None:
    """
    Screenshot the display and return absolute (x, y) to click for the
    index-th (0-based) element row in the filtered tree, or None if
    fewer than index+1 element rows are visible (filter matched nothing,
    or matched fewer rows).

    `region` is (x0, y0, x1, y1) in absolute screen coords, covering the
    Collections tree below its tabs.
    """
    x0, y0, x1, y1 = region
    tmp = screenshot_path or Path(tempfile.gettempdir()) / "qet_tree_probe.png"
    subprocess.run(
        ["scrot", "-o", str(tmp)],
        env={"DISPLAY": display, "PATH": "/usr/bin:/bin"},
        timeout=10, capture_output=True,
    )
    bands = find_bands(tmp, x0, y0, x1, y1)
    reg = Image.open(tmp).convert("L").crop((x0, y0, x1, y1))
    rows = element_rows(bands, reg, y0)
    if index >= len(rows):
        return None
    row = rows[index]
    # Click into the label, to the right of the thumbnail. For a normal
    # row `left` is the text's own left edge; for a selected row `left` is
    # the highlight background's edge, so the thumbnail column comes first
    # and the click must go further right to land on the text.
    dx = 130 if (row.right - row.left) >= _FULL_ROW_SPAN else 90
    return (x0 + row.left + dx, row.cy)


def locate_first_element(
    display: str,
    region: tuple[int, int, int, int],
    screenshot_path: str | Path | None = None,
) -> tuple[int, int] | None:
    """locate_nth_element(..., index=0) — kept under its old name for
    the existing callers."""
    return locate_nth_element(display, region, 0, screenshot_path)


# --------------------------------------------------------------------- #
# Self-test against checked-in captures -- run with:
#     python3 -m scenarios.treefind <dir-of-checkpoint-pngs>
# --------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    shots_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    REGION = (1495, 185, 1915, 1000)
    ok = True
    for shot in sorted(shots_dir.glob("*filter_*.png")):
        bands = find_bands(shot, *REGION)
        reg = Image.open(shot).convert("L").crop(REGION)
        row = first_element_row(bands, reg, REGION[1])
        if row is None:
            print(f"FAIL  {shot.name}: no element row found ({len(bands)} bands)")
            ok = False
        else:
            print(f"ok    {shot.name}: first element row y={row.cy} "
                  f"indent={row.left} -> click ({REGION[0]+row.left+90}, {row.cy})")
    raise SystemExit(0 if ok else 1)
