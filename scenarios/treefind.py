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


def first_element_row(bands: list[Band]) -> Band | None:
    """
    The first band that looks like an element rather than a category.

    Stops at the bottom of the tree widget: once any indented content has
    been seen, a row back at the far-left margin means we have run into
    the docks below the tree, and anything past that point must not be
    treated as a candidate no matter how element-like it looks.
    """
    seen_indented = False
    for i, b in enumerate(bands):
        if b.left <= _TREE_EXIT_INDENT and seen_indented:
            return None          # scanned past the tree; no element found
        if b.left > _TREE_EXIT_INDENT:
            seen_indented = True
        if b.left < _MIN_ELEMENT_INDENT:
            continue
        if i == 0:
            return b
        if b.y0 - bands[i - 1].y0 > _MIN_ELEMENT_GAP:
            return b
    return None


def locate_first_element(
    display: str,
    region: tuple[int, int, int, int],
    screenshot_path: str | Path | None = None,
) -> tuple[int, int] | None:
    """
    Screenshot the display and return absolute (x, y) to click for the
    first element in the filtered tree, or None if no element row is
    visible (i.e. the filter matched nothing).

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
    row = first_element_row(bands)
    if row is None:
        return None
    # Click into the label, to the right of the thumbnail: the thumbnail
    # column starts at `left`, the text a little further right.
    return (x0 + row.left + 90, row.cy)


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
        row = first_element_row(bands)
        if row is None:
            print(f"FAIL  {shot.name}: no element row found ({len(bands)} bands)")
            ok = False
        else:
            print(f"ok    {shot.name}: first element row y={row.cy} "
                  f"indent={row.left} -> click ({REGION[0]+row.left+90}, {row.cy})")
    raise SystemExit(0 if ok else 1)
