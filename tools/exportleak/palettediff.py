"""
Light-vs-dark palette diff of two SVG exports of the same folio.

The exportleak sweep runs one clean binary twice -- once with Qt's default
(light) palette and once with a forced dark palette -- and this module finds
every element whose colour changed between the two. A colour that changes
with the QApplication palette is, by definition, not document content: a
printed/exported page must not change with the theme. That is the sweep's
strongest signal, and it needs no judgement call to detect -- only to name.

Both SVGs come from the *same* binary and the *same* input, so their element
tree is expected to be identical except for colour/opacity values. But a
palette change can also make QSvgGenerator emit or drop a wrapping <g> (the
pen-state grouping changes), which shifts element counts. A naive positional
zip therefore silently misses exactly the change it exists to find. Instead
this module compares the *multiset* of colour signatures per structural key
(tag + text content), so an inserted/removed <g> cannot desynchronise it and
a colour that merely moves from one spelling to another is still caught.
Ids, coordinates and transforms are never part of the key or signature, so
they cannot produce a false diff -- the normalisation is by construction,
matching tools/exportleak/inventory.py.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

_COLOUR_ATTRS = ("fill", "stroke", "color", "stop-color")
_OPACITY_ATTRS = ("opacity", "fill-opacity", "stroke-opacity")
_ATTRS = _COLOUR_ATTRS + _OPACITY_ATTRS


def _tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _walk(el: ET.Element):
    yield el
    for child in el:
        yield from _walk(child)


def _key(el: ET.Element) -> tuple[str, str]:
    """Structural identity: tag + text content, stable across palettes."""
    text = "".join(t or "" for t in el.itertext()).strip()
    return (_tag(el), text)


def _sig(el: ET.Element) -> tuple[tuple[str, str], ...]:
    """The comparison-relevant (attr, value) pairs of one SVG element."""
    return tuple(sorted((a, el.attrib[a]) for a in _ATTRS if a in el.attrib))


def _frag(el: ET.Element) -> str:
    """A compact SVG fragment naming the element and its paint."""
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
    """Compare two SVG exports of one folio; return palette-dependent elements."""
    lt = ET.parse(light_svg).getroot()
    dk = ET.parse(dark_svg).getroot()
    light_elems = list(_walk(lt))
    dark_elems = list(_walk(dk))

    # structural key -> representative elements, so a change can be quoted.
    light_repr: dict[tuple, list[ET.Element]] = defaultdict(list)
    dark_repr: dict[tuple, list[ET.Element]] = defaultdict(list)
    light_sigs: dict[tuple, Counter] = defaultdict(Counter)
    dark_sigs: dict[tuple, Counter] = defaultdict(Counter)
    for e in light_elems:
        k = _key(e)
        light_repr[k].append(e)
        light_sigs[k][_sig(e)] += 1
    for e in dark_elems:
        k = _key(e)
        dark_repr[k].append(e)
        dark_sigs[k][_sig(e)] += 1

    changes: list[dict] = []
    all_keys = set(light_sigs) | set(dark_sigs)
    for k in sorted(all_keys):
        lc = light_sigs.get(k, Counter())
        dc = dark_sigs.get(k, Counter())
        if lc == dc:
            continue
        lost = lc - dc      # signatures present more in light
        gained = dc - lc    # signatures present more in dark
        # Pair losses with gains in a stable order: a palette change moves a
        # colour from one signature to another, so lost and gained counts
        # balance (the difference is element-count churn, reported separately).
        for old_sig, new_sig in zip(sorted(lost.elements()), sorted(gained.elements())):
            old = dict(old_sig)
            new = dict(new_sig)
            changed = {
                a: (old.get(a, ""), new.get(a, ""))
                for a in sorted(set(old) | set(new))
                if old.get(a) != new.get(a)
            }
            # Quote the actual element: the light side for the old colour, the
            # dark side for the new one.
            lfrag = next(
                (_frag(e) for e in light_repr.get(k, []) if _sig(e) == old_sig),
                None,
            )
            dfrag = next(
                (_frag(e) for e in dark_repr.get(k, []) if _sig(e) == new_sig),
                None,
            )
            changes.append({
                "tag": k[0],
                "text": k[1],
                "changed": changed,
                "light_frag": lfrag,
                "dark_frag": dfrag,
            })

    return {
        "light_elements": len(light_elems),
        "dark_elements": len(dark_elems),
        "aligned": len(light_elems) == len(dark_elems),
        "changed_elements": len(changes),
        "changes": changes,
    }
