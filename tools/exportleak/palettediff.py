"""
Light-vs-dark palette diff of two SVG exports of the same folio.

The exportleak sweep runs one clean binary twice -- once with Qt's default
(light) palette and once with a forced dark palette -- and this module finds
every element whose colour changed between the two. A colour that changes
with the QApplication palette is, by definition, not document content: a
printed/exported page must not change with the theme. That is the sweep's
strongest signal, and it needs no judgement call to detect -- only to name.

Both SVGs come from the *same* binary and the *same* input, so their element
tree (count, order, non-colour attributes) is expected to be identical; only
colour/opacity values can differ. We walk the two trees in lock-step and
compare a per-element "colour signature" (the colour + opacity attributes
only). Ids, coordinates, transforms and generator metadata are never part of
the signature, so they cannot produce a false diff -- the normalisation is
by construction, matching tools/exportleak/inventory.py.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tools.exportleak.inventory import norm_colour

_COLOUR_ATTRS = ("fill", "stroke", "color", "stop-color")
_OPACITY_ATTRS = ("opacity", "fill-opacity", "stroke-opacity")
_ATTRS = _COLOUR_ATTRS + _OPACITY_ATTRS


def _tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _walk(el: ET.Element):
    yield el
    for child in el:
        yield from _walk(child)


def _sig(el: ET.Element) -> tuple[tuple[str, str], ...]:
    """The comparison-relevant (attr, value) pairs of one SVG element."""
    return tuple(
        sorted((a, el.attrib[a]) for a in _ATTRS if a in el.attrib)
    )


def _changed_attrs(light: ET.Element, dark: ET.Element) -> dict[str, tuple[str, str]]:
    """Attributes whose value differs between the two palettes."""
    out: dict[str, tuple[str, str]] = {}
    for a in _ATTRS:
        lv = light.attrib.get(a)
        dv = dark.attrib.get(a)
        if lv != dv:
            out[a] = (lv or "", dv or "")
    return out


def _frag(el: ET.Element) -> str:
    """A compact, self-contained SVG fragment naming the element and its paint."""
    tag = _tag(el)
    text = "".join(t or "" for t in el.itertext()).strip()
    paint = " ".join(
        f'{a}="{el.attrib[a]}"' for a in sorted(el.attrib) if a in _ATTRS
    )
    inner = (" " + paint) if paint else ""
    if tag in ("text", "tspan") and text:
        return f"<{tag}{inner}>{text}</{tag}>"
    return f"<{tag}{inner}/>"


def palette_diff_folio(light_svg: Path, dark_svg: Path) -> dict:
    """Compare two SVG exports of one folio; return changed elements + meta."""
    lt = ET.parse(light_svg).getroot()
    dk = ET.parse(dark_svg).getroot()
    light_elems = list(_walk(lt))
    dark_elems = list(_walk(dk))

    aligned = len(light_elems) == len(dark_elems)
    changes: list[dict] = []

    if aligned:
        for le, de in zip(light_elems, dark_elems):
            if _sig(le) != _sig(de):
                changed = _changed_attrs(le, de)
                changes.append({
                    "tag": _tag(de),
                    "text": "".join(t or "" for t in de.itertext()).strip(),
                    "changed": changed,
                    "light_frag": _frag(le),
                    "dark_frag": _frag(de),
                })

    return {
        "light_elements": len(light_elems),
        "dark_elements": len(dark_elems),
        "aligned": aligned,
        "changed_elements": len(changes),
        "changes": changes,
    }
