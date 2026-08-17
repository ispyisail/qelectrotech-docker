"""
Parse QET SVG/PNG/PDF exports into a stable, comparison-ready inventory.

We deliberately never byte-compare SVG files. QSvgGenerator embeds ids,
coordinates, transform matrices and float precision that can churn between
runs and certainly between builds; those are noise. What an editing-state
decoration leaking into an export *changes* is structural and stable:

  - the multiset of element tag names (a halo adds a new <ellipse>/<path>/
    <rect>, or grows an existing shape tag);
  - the set of distinct stroke/fill colours (a coloured halo adds one);
  - any *partial* opacity -- fill-opacity/stroke-opacity/opacity < 1, or a
    colour carrying an alpha channel < 1 (halos are usually translucent).

The inventory records exactly those three things per folio. The diff
(tools/exportleak/compare.py) then reports anything the candidate has that
the baseline does not. Because ids / coordinates / generator metadata are
never part of the inventory, they are normalised away *by construction*,
not by a loose byte comparison.
"""
from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# Attribute names whose values are colours. Qt emits fill/stroke on the
# top-level <g> and on leaf shapes; stop-color covers gradients (which QET
# does not currently use, but costs nothing to cover).
_COLOUR_ATTRS = ("fill", "stroke", "color", "stop-color")
# Attributes that carry an opacity scalar.
_OPACITY_ATTRS = ("opacity", "fill-opacity", "stroke-opacity")
# The drawable shape tags (as opposed to structural <g>/<svg>/<defs>...).
_SHAPE_TAGS = {"rect", "circle", "ellipse", "path", "polyline", "polygon", "line"}


def norm_colour(value: str) -> str | None:
    """Normalise a colour token to a canonical form; None for 'none'/empty."""
    v = value.strip()
    if not v:
        return None
    low = v.lower()
    if low == "none":
        return None
    if low.startswith("#"):
        hexpart = low[1:]
        # Expand #rgb to #rrggbb so two spellings of the same colour collide.
        if re.fullmatch(r"[0-9a-f]{3}", hexpart):
            return "#" + "".join(ch * 2 for ch in hexpart)
        if re.fullmatch(r"[0-9a-f]{6}([0-9a-f]{2})?", hexpart):
            return "#" + hexpart
        return low  # malformed: keep verbatim so it can never silently collide
    m = re.fullmatch(r"rgba?\((.*)\)", low)
    if m:
        # Collapse whitespace: rgb(0, 0, 255) == rgb(0,0,255).
        return low[:3] + "(" + ",".join(p.strip() for p in m.group(1).split(",")) + ")"
    # Named colour ("black", "white", "red", ...) -- lowercase is canonical.
    return low


def _rgba_alpha(value: str) -> float | None:
    """Alpha channel of an rgba(...) colour, or None if not an rgba colour."""
    m = re.fullmatch(r"rgba\((.*)\)", value.strip().lower())
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(",")]
    if len(parts) != 4:
        return None
    a = parts[3]
    try:
        if a.endswith("%"):
            return float(a[:-1]) / 100.0
        fa = float(a)
        return fa if fa <= 1.0 else fa / 255.0  # tolerate 0..255 form
    except ValueError:
        return None


def svg_inventory(svg_path: Path) -> dict:
    """Tag counts, colour set and partial-opacity features for one SVG folio."""
    tags: Counter[str] = Counter()
    colours: set[str] = set()
    partial: set[str] = set()

    for _, el in ET.iterparse(svg_path, events=("start",)):
        tag = el.tag.rsplit("}", 1)[-1]  # strip any namespace prefix
        tags[tag] += 1
        attrs = el.attrib

        for a in _COLOUR_ATTRS:
            if a in attrs:
                c = norm_colour(attrs[a])
                if c:
                    colours.add(c)

        for a in _OPACITY_ATTRS:
            if a not in attrs:
                continue
            try:
                val = float(attrs[a])
            except ValueError:
                continue
            if 0.0 < val < 1.0:
                partial.add(f"{a}={attrs[a]}")

        # A colour may carry its alpha inline (rgba). Treat that as partial
        # opacity too, and keep the colour so a newly-introduced translucent
        # colour is visible in both inventories.
        for a in ("fill", "stroke"):
            if a in attrs:
                alpha = _rgba_alpha(attrs[a])
                if alpha is not None and 0.0 < alpha < 1.0:
                    partial.add(f"{a}.alpha={attrs[a]}")

    shape_count = sum(tags[t] for t in _SHAPE_TAGS)
    return {
        "tags": dict(sorted(tags.items())),
        "colours": sorted(colours),
        "partial_opacity": sorted(partial),
        "shape_count": shape_count,
    }


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Width/height from the PNG IHDR chunk (stdlib, no PIL)."""
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def empty_inventory() -> dict:
    return {"tags": {}, "colours": [], "partial_opacity": [], "shape_count": 0}
