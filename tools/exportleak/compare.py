"""
Diff two export inventories (baseline vs candidate) and report the leaks.

A *leak* is anything present in the candidate's export that is absent from
the baseline's, at the folio level:

  - a gained element tag, or a tag whose count grew (a new decoration shape);
  - a gained colour (a new stroke/fill colour);
  - a gained partial-opacity feature (a translucent decoration).

Any of the three, on any folio of any project, is a finding. For a
rendering change the natural shape is "gained"; "lost" tag/colour is
reported alongside for legibility but a pure loss (candidate draws *less*)
is still recorded as a difference so a real regression is not silently
swallowed.
"""
from __future__ import annotations

from tools.exportleak.inventory import empty_inventory


def _empty() -> dict:
    return empty_inventory()


def diff_folio(base: dict, cand: dict) -> dict:
    b_tags = base.get("tags", {})
    c_tags = cand.get("tags", {})
    all_tags = sorted(set(b_tags) | set(c_tags))

    tags_gained = {
        t: c_tags.get(t, 0) - b_tags.get(t, 0)
        for t in all_tags
        if c_tags.get(t, 0) > b_tags.get(t, 0)
    }
    tags_lost = {
        t: b_tags.get(t, 0) - c_tags.get(t, 0)
        for t in all_tags
        if b_tags.get(t, 0) > c_tags.get(t, 0)
    }

    b_colours = set(base.get("colours", []))
    c_colours = set(cand.get("colours", []))
    colours_gained = sorted(c_colours - b_colours)
    colours_lost = sorted(b_colours - c_colours)

    b_opacity = set(base.get("partial_opacity", []))
    c_opacity = set(cand.get("partial_opacity", []))
    opacity_gained = sorted(c_opacity - b_opacity)
    opacity_lost = sorted(b_opacity - c_opacity)

    is_leak = bool(tags_gained or colours_gained or opacity_gained)
    is_change = bool(tags_gained or tags_lost or colours_gained or colours_lost or opacity_gained or opacity_lost)

    return {
        "tags_gained": tags_gained,
        "tags_lost": tags_lost,
        "colours_gained": colours_gained,
        "colours_lost": colours_lost,
        "opacity_gained": opacity_gained,
        "opacity_lost": opacity_lost,
        "leak": is_leak,
        "changed": is_change,
    }


def diff_project(base: dict, cand: dict) -> dict:
    b_folios = base.get("folios", {})
    c_folios = cand.get("folios", {})
    names = sorted(set(b_folios) | set(c_folios))

    folio_diffs = {}
    leak = False
    for name in names:
        d = diff_folio(b_folios.get(name, _empty()), c_folios.get(name, _empty()))
        folio_diffs[name] = d
        if d["leak"]:
            leak = True

    png_delta = cand.get("png", {}).get("bytes", 0) - base.get("png", {}).get("bytes", 0)
    png_pixel_delta = cand.get("png", {}).get("pixels", 0) - base.get("png", {}).get("pixels", 0)
    pdf_delta = cand.get("pdf", {}).get("bytes", 0) - base.get("pdf", {}).get("bytes", 0)

    return {
        "project": cand.get("project"),
        "leak": leak,
        "folio_diffs": folio_diffs,
        "png_bytes_delta": png_delta,
        "png_pixel_delta": png_pixel_delta,
        "pdf_bytes_delta": pdf_delta,
    }


def diff(base_inventories: dict[str, dict], cand_inventories: dict[str, dict]) -> list[dict]:
    """base/cand map project stem -> project inventory (from export_one)."""
    names = sorted(set(base_inventories) | set(cand_inventories))
    out = []
    for name in names:
        b = base_inventories.get(name)
        c = cand_inventories.get(name)
        if b is None or c is None:
            # A project that exists on one side only (e.g. failed to export
            # on the other) -- surface it as a structural difference.
            out.append({
                "project": name,
                "leak": False,
                "missing_on": "candidate" if c is None else "baseline",
                "folio_diffs": {},
                "png_bytes_delta": 0,
                "png_pixel_delta": 0,
                "pdf_bytes_delta": 0,
            })
            continue
        out.append(diff_project(b, c))
    return out
