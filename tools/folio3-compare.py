#!/usr/bin/env python3
"""
folio3-compare — compare the tremie_folio3 rebuild against the original
folio 3 ("COMMANDE") of tremie_vibrante.qet, wire by wire.

The user's rule for this tool: "Where possible go and compare with the
original. It's the wires that are the worst — wires over top of each
other, wires missing, just compare."

Three drawings are brought together here:

  * DESIGN   — the checked grid in scenarios/tremie_folio3_grid.py
               (18 elements, 18 wires, every route pre-verified offline).
  * ORIGINAL — folio 3 of the real tremie_vibrante.qet project (29
               conductors; 18 between real electrical elements, the rest
               touching ref_folio markers / decorative items).
  * REBUILD  — a scenario save produced by tremie_folio3.py.

For each design wire the script prints one row showing which original
conductor and which rebuild conductor correspond to it, with both
endpoints resolved to a TERMINAL (not just an element pair), then routes
both real drawings through the same deterministic QET router port and
checks every segment against every other: collinear overlaps, crossings,
passes through element bodies, and scene bounds.

The terminal resolution is the heart of it. Two saved-file formats:

  * REBUILD (format B): <conductor element1= element2=> carries element
    uuids; terminal1/terminal2 are STATIC per-.elmt-definition uuids
    that resolve through the project-level <collection> definitions
    (orientation stored as letters n/e/s/w).
  * ORIGINAL (format A): terminal1/terminal2 are diagram-wide terminal
    ids; each placed <element> carries its own <terminals> table
    (id -> x/y/orientation, orientation stored as numbers 0=N 1=E 2=S 3=W).

Matching design<->original uses the substituted type pair (borne_continuite
-> borne_2, con_simple-2011 -> con_simple, bobine -> bobine3) in four
rounds: unique type pair, known-endpoint propagation, terminal-name pair,
and left-right position for symmetric pairs. The original's own terminal
orientation attributes are NOT used — they come from old .elmt
definitions and rotated placements and disagree with current stock.
Matching design<->rebuild uses element position (grid keys) plus a TIGHT
offset match against the terminal tables, so a wire on the wrong borne
terminal FAILS instead of passing under a 20px element-pair tolerance
(that tolerance is exactly what let borne top/east swaps through before).

Exit code: 0 = every wire matches at terminal level in both drawings and
both geometry checks are clean; 1 otherwise.

Usage:
    tools/folio3-compare.py [--rebuild /path/to/save.qet]
                            [--original /path/to/tremie_vibrante.qet]
                            [--folio 3]
"""
from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenarios.tremie_folio3_grid import (  # noqa: E402
    BODIES, ELEMENTS, SCENE, TERMINALS, WIRES, _GRID,
    extend_terminal, route, segments, _seg_intersection, _cround, _cdiv,
)

_ORI_NUM = {"0": "n", "1": "e", "2": "s", "3": "w"}


# --------------------------------------------------------------------- #
# Saved-file parsing
# --------------------------------------------------------------------- #

def _short_type(type_attr: str) -> str:
    return (type_attr or "").rsplit("/", 1)[-1]


def parse_rebuild(path: Path) -> dict:
    """Rebuild (format B): {element uuid: (x, y)} + conductors as
    (e1_uuid, t1_uuid, e2_uuid, t2_uuid), and the collection's
    terminal-uuid -> (x, y, orientation-letter) definitions."""
    root = ET.parse(str(path)).getroot()
    elements = {}
    for el in root.iter("element"):
        uuid = el.get("uuid")
        if uuid:
            elements[uuid] = (float(el.get("x", 0)), float(el.get("y", 0)))
    defs = {}
    for t in root.iter("terminal"):
        tu = t.get("uuid")
        if tu is not None:
            defs[tu] = (float(t.get("x", 0)), float(t.get("y", 0)),
                        t.get("orientation", "") or "n")
    conductors = []
    for c in root.iter("conductor"):
        e1, e2 = c.get("element1"), c.get("element2")
        t1, t2 = c.get("terminal1"), c.get("terminal2")
        if e1 and e2 and t1 and t2:
            conductors.append((e1, t1, e2, t2))
    return {"elements": elements, "defs": defs, "conductors": conductors}


def parse_original_folio3(path: Path, folio_index: int) -> dict:
    """Original (format A): pick diagram `folio_index`, return
    {element uuid: (x, y, type, {term id: (x, y, ori-letter)})} and
    conductors as (t1_id, t2_id)."""
    root = ET.parse(str(path)).getroot()
    diagrams = [d for d in root.iter("diagram")]
    if folio_index >= len(diagrams):
        raise SystemExit(
            f"{path}: has {len(diagrams)} diagrams, no index {folio_index}")
    diagram = diagrams[folio_index]

    elements = {}
    for el in diagram.iter("element"):
        uuid = el.get("uuid")
        if not uuid:
            continue
        terms = {}
        for t in el.iter("terminal"):
            tid = t.get("id")
            if tid is not None:
                terms[tid] = (float(t.get("x", 0)), float(t.get("y", 0)),
                              _ORI_NUM.get(t.get("orientation", "0"), "n"))
        elements[uuid] = {
            "pos": (float(el.get("x", 0)), float(el.get("y", 0))),
            "type": _short_type(el.get("type", "")),
            "terminals": terms,
        }
    conductors = []
    for c in diagram.iter("conductor"):
        t1, t2 = c.get("terminal1"), c.get("terminal2")
        if t1 and t2:
            segments_attr = []
            for s in c.iter("segment"):
                segments_attr.append((float(s.get("length1", 0)),
                                      float(s.get("length2", 0))))
            conductors.append((t1, t2, segments_attr))
    return {"elements": elements, "conductors": conductors}


# --------------------------------------------------------------------- #
# Terminal resolution
# --------------------------------------------------------------------- #

def rebuild_wire_terms(rebuild, c):
    """Conductor -> ((dock1, ori1), (dock2, ori2)) via collection defs."""
    e1, t1, e2, t2 = c
    p1 = rebuild["elements"][e1]
    p2 = rebuild["elements"][e2]
    d1 = rebuild["defs"][t1]
    d2 = rebuild["defs"][t2]
    return ((p1[0] + d1[0], p1[1] + d1[1]), d1[2]), \
           ((p2[0] + d2[0], p2[1] + d2[1]), d2[2])


def original_wire_terms(orig, c):
    """Conductor -> ((dock1, ori1), (dock2, ori2)) via per-element tables."""
    t1, t2, _segs = c
    for uuid, info in orig["elements"].items():
        if t1 in info["terminals"]:
            e1 = info
            break
    else:
        raise KeyError(f"terminal id {t1} not owned by any element")
    for uuid, info in orig["elements"].items():
        if t2 in info["terminals"]:
            e2 = info
            break
    else:
        raise KeyError(f"terminal id {t2} not owned by any element")
    (x1, y1, o1) = e1["terminals"][t1]
    (x2, y2, o2) = e2["terminals"][t2]
    return ((e1["pos"][0] + x1, e1["pos"][1] + y1), o1), \
           ((e2["pos"][0] + x2, e2["pos"][1] + y2), o2)


# --------------------------------------------------------------------- #
# Type substitution + design matching
# --------------------------------------------------------------------- #

def substituted_type(type_name: str) -> str | None:
    """Map an original folio-3 element type to its rebuild ELEMENTS key
    family. Returns the fragment used in ELEMENTS, or None for
    decorative/non-electrical types."""
    if "borne_continuite" in type_name:
        return "borne_2"
    if "con_simple" in type_name:
        return "con_simple"
    if type_name.startswith("bobine"):
        return "bobine3"
    if "digidrive" in type_name:
        return "digidrive_sk"
    if "capteur_opt" in type_name:
        return "capteur_opt_nc_4p"
    if type_name.startswith("poussoir"):
        return "poussoir"
    if "contact_002" in type_name:
        return "contact_002"
    if type_name.startswith("lampe2"):
        return "lampe2"
    return None


def grid_key_of(pos, tol=20):
    """Saved scene position -> grid key (scene coords), nearest within tol."""
    best, best_d = None, None
    for k, (gx, gy) in _GRID.items():
        d = abs((820 + gx) - pos[0]) + abs((420 + gy) - pos[1])
        if best_d is None or d < best_d:
            best, best_d = k, d
    return best if best_d is not None and best_d <= 2 * tol else None


# --------------------------------------------------------------------- #
# Geometry check (parameterized port of the grid module's check)
# --------------------------------------------------------------------- #

def check_wires(wires, elem_pos=None, label=""):
    """wires: list of (name, key1, dock1, ori1, key2, dock2, ori2) when
    elem_pos is given (rebuild), else (name, dock1, ori1, dock2, ori2)
    for a key-less wire set (original). Returns problem strings.

    Ports the grid module's exemptions: collinear overlap and T-meet
    crossing are allowed only at a dock shared by both wires (a true
    junction), and a segment whose both endpoints lie within 16px of one
    of the wire's own docks is a terminal stub (grazes the element body
    by design)."""
    problems = []
    keyed = elem_pos is not None
    names = []
    paths = {}
    docks_of = {}
    for i, w in enumerate(wires):
        if keyed:
            k1, p1, o1, k2, p2, o2 = w
            name = f"w{i+1}"
        else:
            name, p1, o1, p2, o2 = w
        names.append(name)
        paths[name] = route(p1, o1, p2, o2)
        docks_of[name] = [(p1, o1), (p2, o2)]

    segs_of = {n: segments(pts) for n, pts in paths.items()}

    # dock -> wires sharing it (junction detection, 0.5px tolerance)
    shared = {}
    dock_owner = {}
    for n in names:
        for d, o in docks_of[n]:
            key = (round(d[0] * 2) / 2, round(d[1] * 2) / 2)
            shared.setdefault(key, []).append(n)
            dock_owner.setdefault(key, o)
    shared = {k: ws for k, ws in shared.items() if len(ws) > 1}

    def _dist(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1])

    def is_own_stub(name, seg, dock):
        return (_dist(seg[0], dock) <= 16 and _dist(seg[1], dock) <= 16)

    def shared_stub_pair(s1, n1, s2, n2):
        for dock, ws in shared.items():
            if n1 in ws and n2 in ws:
                if is_own_stub(n1, s1, dock) and is_own_stub(n2, s2, dock):
                    return True
        return False

    def allowed_t_meet(p, n1, n2):
        for dock, ws in shared.items():
            if n1 not in ws or n2 not in ws:
                continue
            ext = extend_terminal(dock, dock_owner[dock])
            if _dist(p, ext) <= 1e-6:
                return True
        return False

    # 1. wire-vs-wire
    for i, n1 in enumerate(names):
        for n2 in names[i + 1:]:
            for s1 in segs_of[n1]:
                for s2 in segs_of[n2]:
                    hit = _seg_intersection(s1, s2)
                    if hit is None:
                        continue
                    if isinstance(hit, tuple) and len(hit) == 2 and \
                            isinstance(hit[0], tuple):
                        if not shared_stub_pair(s1, n1, s2, n2):
                            problems.append(
                                f"{label}OVERLAP {n1} x {n2} at {hit}")
                    elif not allowed_t_meet(hit, n1, n2):
                        problems.append(
                            f"{label}CROSS  {n1} x {n2} at {hit}")

    # 2. body collisions (rebuild only: the original's element bodies are
    # not measured here -- different stock types, and it is the reference)
    if keyed:
        bodies = {(elem_pos[k][0], elem_pos[k][1], k): v
                  for k, v in BODIES.items()}
        for name in names:
            for s in segs_of[name]:
                stub = any(is_own_stub(name, s, d)
                           for d, _o in docks_of[name])
                if stub:
                    continue
                (ax, ay), (bx, by) = s
                if ax == bx:
                    x0 = x1 = ax
                    lo, hi = min(ay, by) + 1, max(ay, by) - 1
                else:
                    lo, hi = min(ax, bx) + 1, max(ax, bx) - 1
                    x0, x1 = lo, hi
                    lo, hi = ay, ay
                if x1 < x0 or hi < lo:
                    continue
                for el, (bx0, by0, bx1, by1) in bodies.items():
                    ex0 = el[0] + bx0
                    ey0 = el[1] + by0
                    ex1 = el[0] + bx1
                    ey1 = el[1] + by1
                    if x1 < ex0 or x0 > ex1 or hi < ey0 or lo > ey1:
                        continue
                    problems.append(
                        f"{label}BODY   {name} segment "
                        f"({ax:.0f},{ay:.0f})-({bx:.0f},{by:.0f}) "
                        f"enters {el[2]}")
    return problems


# --------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", default="/tmp/folio3_run.qet")
    ap.add_argument("--original",
                    default="/home/user/qet-fix/examples/tremie_vibrante.qet")
    ap.add_argument("--folio", type=int, default=3,
                    help="1-based folio index in the original project")
    args = ap.parse_args()

    rebuild = parse_rebuild(Path(args.rebuild))
    orig = parse_original_folio3(Path(args.original), args.folio - 1)

    # Rebuild: element uuid -> grid key (position-based).
    rebuild_keys = {}
    for uuid, pos in rebuild["elements"].items():
        k = grid_key_of(pos)
        if k:
            rebuild_keys[uuid] = k

    # Rebuild conductors resolved to terminals.
    rebuild_wires = []
    for c in rebuild["conductors"]:
        e1, _t1, e2, _t2 = c
        k1, k2 = rebuild_keys.get(e1), rebuild_keys.get(e2)
        if not k1 or not k2:
            continue
        (p1, o1), (p2, o2) = rebuild_wire_terms(rebuild, c)
        rebuild_wires.append((k1, p1, o1, k2, p2, o2))

    # Original conductors, excluding marker/decorative ends. Each wire is
    # a dict carrying both endpoints' substituted type, raw type, dock,
    # element-local terminal offset (format-A tables) and element uuid.
    owner = {}
    for uuid, info in orig["elements"].items():
        for tid in info["terminals"]:
            owner[tid] = (uuid, info)
    orig_wires = []
    for c in orig["conductors"]:
        t1, t2, _ = c
        if t1 not in owner or t2 not in owner:
            continue
        i1, i2 = owner[t1][1], owner[t2][1]
        s1, s2 = substituted_type(i1["type"]), substituted_type(i2["type"])
        if not s1 or not s2:
            continue  # marker / cadre / texte6 ends
        (p1, o1), (p2, o2) = original_wire_terms(orig, c)
        orig_wires.append({
            "sub1": s1, "sub2": s2,
            "type1": i1["type"], "type2": i2["type"],
            "dock1": p1, "dock2": p2, "ori1": o1, "ori2": o2,
            "rel1": i1["terminals"][t1][:2],
            "rel2": i2["terminals"][t2][:2],
            "uuid1": owner[t1][0], "uuid2": owner[t2][0],
        })

    # Name an original element's terminal by nearest design-terminal
    # stock offset. The original's own tables come from OLD .elmt
    # definitions (drive terminals at y=4/62 instead of -30/36), so the
    # tolerance must absorb that drift where the nearest stock terminal
    # is still the right one; the drive's far-off terminals then simply
    # fail to resolve ("drive.?").
    _NAME_TOL = {"drive": 30}

    def orig_term_name(key, rel):
        tol = _NAME_TOL.get(key, 6)
        best, best_d = None, None
        for tname, ((ox, oy), _ori) in TERMINALS[key].items():
            d = math.hypot(rel[0] - ox, rel[1] - oy)
            if best_d is None or d < best_d:
                best, best_d = tname, d
        return best if best_d <= tol else None

    # Match design wires <-> original wires. Orientation pairing is NOT
    # used: the original's format-A orientation attributes come from old
    # .elmt definitions and rotated placements and disagree with current
    # stock (e.g. both original bobine wires use a 'top' terminal where
    # the design uses B2.bottom). Matching goes in rounds:
    #
    #   A. type-pair (substituted) occurs exactly once in the original.
    #   B. one endpoint maps to a design key established by earlier
    #      rounds, and no endpoint maps outside the wire's key pair.
    #   C. both endpoints resolve to design terminal names and the
    #      name-pair is unique among the remaining candidates.
    #   D. positional: for symmetric pairs (the two coils), the original
    #      elements keep the design grid's left-right order.
    design_to_orig = {}
    used = set()
    key_of_uuid = {}  # original element uuid -> design key

    def _key_of_endpoint(w, side, key_a, key_b):
        """Design key of an original wire endpoint, inferred when the
        element itself is not yet mapped."""
        uuid = w["uuid1"] if side == 1 else w["uuid2"]
        sub = w["sub1"] if side == 1 else w["sub2"]
        k = key_of_uuid.get(uuid)
        if k:
            return k
        other_uuid = w["uuid2"] if side == 1 else w["uuid1"]
        taken = key_of_uuid.get(other_uuid)
        return next((k for k in (key_a, key_b)
                     if ELEMENTS[k][1] == sub and k != taken), None)

    def _note_wire(wi, oi, key_a, key_b, ta, tb):
        design_to_orig[wi] = oi
        used.add(oi)
        w = orig_wires[oi]
        if w["sub1"] == w["sub2"] == ELEMENTS[key_a][1] == ELEMENTS[key_b][1]:
            # con_simple -- con_simple: endpoints indistinguishable by
            # type; assign by terminal-name match against the design
            # wire's own terminals (they always differ here).
            n1 = orig_term_name(key_a, w["rel1"])
            n2 = orig_term_name(key_b, w["rel2"])
            if n1 == ta and n2 == tb:
                key_of_uuid[w["uuid1"]] = key_a
                key_of_uuid[w["uuid2"]] = key_b
            elif n1 == tb and n2 == ta:
                key_of_uuid[w["uuid1"]] = key_b
                key_of_uuid[w["uuid2"]] = key_a
        elif w["sub1"] == ELEMENTS[key_a][1]:
            key_of_uuid[w["uuid1"]] = key_a
            key_of_uuid[w["uuid2"]] = key_b
        else:
            key_of_uuid[w["uuid1"]] = key_b
            key_of_uuid[w["uuid2"]] = key_a

    # Round A: unique type pair.
    for wi, (a, ta, b, tb) in enumerate(WIRES):
        fa, fb = ELEMENTS[a][1], ELEMENTS[b][1]
        cands = [i for i, w in enumerate(orig_wires)
                 if i not in used and {w["sub1"], w["sub2"]} == {fa, fb}]
        if len(cands) == 1:
            _note_wire(wi, cands[0], a, b, ta, tb)

    # Rounds B..D to fixpoint.
    progress = True
    while progress:
        progress = False
        for wi, (a, ta, b, tb) in enumerate(WIRES):
            if wi in design_to_orig:
                continue
            fa, fb = ELEMENTS[a][1], ELEMENTS[b][1]
            cands = [i for i, w in enumerate(orig_wires)
                     if i not in used and {w["sub1"], w["sub2"]} == {fa, fb}]

            # Round B: candidates with a known endpoint among {a, b}
            # and no known endpoint outside {a, b}.
            kept = []
            for i in cands:
                w = orig_wires[i]
                hit, bad = False, False
                for uuid in (w["uuid1"], w["uuid2"]):
                    k = key_of_uuid.get(uuid)
                    if k is not None:
                        hit = True
                        bad |= k not in (a, b)
                if hit and not bad:
                    kept.append(i)
            if len(kept) == 1:
                _note_wire(wi, kept[0], a, b, ta, tb)
                progress = True
                continue

            # Round C: unique resolved name-pair.
            named = []
            for i in (kept or cands):
                w = orig_wires[i]
                k1 = _key_of_endpoint(w, 1, a, b)
                k2 = _key_of_endpoint(w, 2, a, b)
                if not k1 or not k2:
                    continue
                n1 = orig_term_name(k1, w["rel1"])
                n2 = orig_term_name(k2, w["rel2"])
                if n1 and n2 and {n1, n2} == {ta, tb}:
                    named.append(i)
            if len(named) == 1:
                _note_wire(wi, named[0], a, b, ta, tb)
                progress = True
                continue

            # Round D: positional left-right for symmetric pairs. Every
            # candidate must have exactly one unmapped endpoint, all of
            # the same substituted fragment; the design's unclaimed key
            # of that fragment picks the candidate by x-order.
            if len(cands) >= 2:
                ranked, sub, ok = [], None, True
                for i in cands:
                    w = orig_wires[i]
                    unmapped = [(uuid, s) for uuid, s in
                                ((w["uuid1"], w["sub1"]),
                                 (w["uuid2"], w["sub2"]))
                                if uuid not in key_of_uuid]
                    if len(unmapped) != 1:
                        ok = False
                        break
                    uuid, s = unmapped[0]
                    if sub is None:
                        sub = s
                    ok &= s == sub
                    ranked.append((orig["elements"][uuid]["pos"][0], i))
                if ok and len({r[0] for r in ranked}) == len(ranked):
                    frag_keys = sorted(
                        [k for k in ELEMENTS if ELEMENTS[k][1] == sub],
                        key=lambda k: _GRID[k][0])
                    cand_key = [k for k in (a, b) if ELEMENTS[k][1] == sub]
                    if len(cand_key) == 1 and len(ranked) == len(frag_keys):
                        idx = frag_keys.index(cand_key[0])
                        _note_wire(wi, sorted(ranked)[idx][1], a, b, ta, tb)
                        progress = True

    # Match rebuild wires <-> design wires: element keys by position, then
    # TERMINAL identification by exact offset match. The collection
    # definitions carry the STOCK offsets (verified: borne top (0,-10) 'n',
    # east (10,0) 'e'; drive s150 (150,36) 's'), so for a conductor of a
    # given saved element, dock - element_pos == TERMINALS[key][term]
    # stock offset EXACTLY (1px float tolerance). Orientation must agree
    # too -- that alone separates borne top ('n') from east ('e') no
    # matter how close the marks sit on screen.
    design_to_rebuild = {}
    rebuild_used = set()
    problems = []

    def _identify_terminal(key, dock, ori, elem_pos):
        """Name the terminal of element `key` whose stock offset +
        orientation the resolved (dock, ori) matches exactly."""
        for tname, ((ox, oy), tori) in TERMINALS[key].items():
            if (abs(dock[0] - elem_pos[0] - ox) <= 1.5
                    and abs(dock[1] - elem_pos[1] - oy) <= 1.5
                    and ori == tori):
                return tname
        return None

    rebuild_elem_pos = {}
    for uuid, pos in rebuild["elements"].items():
        if uuid in rebuild_keys:
            rebuild_elem_pos[rebuild_keys[uuid]] = pos

    for wi, (a, ta, b, tb) in enumerate(WIRES):
        for ri, (k1, p1, o1, k2, p2, o2) in enumerate(rebuild_wires):
            if ri in rebuild_used:
                continue
            if {k1, k2} != {a, b}:
                continue
            if k1 == a:
                n1 = _identify_terminal(k1, p1, o1, rebuild_elem_pos[k1])
                n2 = _identify_terminal(k2, p2, o2, rebuild_elem_pos[k2])
                ok = {n1, n2} == {ta, tb}
            else:
                n1 = _identify_terminal(k2, p2, o2, rebuild_elem_pos[k2])
                n2 = _identify_terminal(k1, p1, o1, rebuild_elem_pos[k1])
                ok = {n1, n2} == {ta, tb}
            if ok:
                design_to_rebuild[wi] = ri
                rebuild_used.add(ri)
                break

    # Geometry self-check on the rebuild (actual saved positions, stub +
    # junction exemptions as in the grid module's own check). This gates
    # the exit code: the rebuild must be a clean drawing.
    problems = check_wires(rebuild_wires, rebuild_elem_pos, label="REBUILD ")

    # The original's own geometry is informational only: its layout is
    # not the checked grid, so its routes may legitimately cross.
    ow = [(f"o{i}", w["dock1"], w["ori1"], w["dock2"], w["ori2"])
          for i, w in enumerate(orig_wires)]
    orig_problems = check_wires(ow, None, label="ORIGINAL ")

    # ------------------------------------------------------------------ #
    # Report
    # ------------------------------------------------------------------ #
    print(f"rebuild: {len(rebuild_wires)} wires resolved to grid keys "
          f"(of {len(rebuild['conductors'])} conductors)")
    print(f"original folio {args.folio}: {len(orig_wires)} electrical wires "
          f"(marker/decorative ends excluded)")
    print()

    hdr = (f"{'wire':>4}  {'design':30}  {'rebuild':34}  {'original':28}  verdict")
    print(hdr)
    print("-" * len(hdr))
    matched = 0
    for wi, (a, ta, b, tb) in enumerate(WIRES):
        design = f"{a}.{ta} -> {b}.{tb}"
        ri = design_to_rebuild.get(wi)
        if ri is None:
            # The conductor may still exist, just on wrong terminals --
            # show what was actually drawn (this is the "wires on the
            # wrong borne terminal" defect the tight match exists for).
            wrong = [j for j, (k1, _p1, _o1, k2, _p2, _o2)
                     in enumerate(rebuild_wires)
                     if j not in rebuild_used and {k1, k2} == {a, b}]
            rb, verdict = "-", "REBUILD MISSING"
            if wrong:
                k1, p1, o1, k2, p2, o2 = rebuild_wires[wrong[0]]
                n1 = _identify_terminal(k1, p1, o1, rebuild_elem_pos[k1])
                n2 = _identify_terminal(k2, p2, o2, rebuild_elem_pos[k2])
                rb = f"{k1}.{n1 or '?'} -> {k2}.{n2 or '?'}"
                verdict = "WRONG TERMINAL"
        else:
            k1, p1, o1, k2, p2, o2 = rebuild_wires[ri]
            n1 = _identify_terminal(k1, p1, o1, rebuild_elem_pos[k1])
            n2 = _identify_terminal(k2, p2, o2, rebuild_elem_pos[k2])
            rb = f"{k1}.{n1 or '?'} -> {k2}.{n2 or '?'}"
            verdict = "ok" if {n1, n2} == {ta, tb} else "WRONG TERMINAL"
        oi = design_to_orig.get(wi)
        if oi is None:
            og = "-"
        else:
            w = orig_wires[oi]
            parts = []
            for uuid, sub, rel in ((w["uuid1"], w["sub1"], w["rel1"]),
                                   (w["uuid2"], w["sub2"], w["rel2"])):
                k = key_of_uuid.get(uuid)
                n = orig_term_name(k, rel) if k else None
                parts.append(f"{k or '?'}.{n or '?'}")
            og = " -- ".join(parts)
        if verdict == "ok":
            matched += 1
        print(f"{wi+1:4d}  {design:30}  {rb:34}  {og:28}  {verdict}")

    print()
    print(f"rebuild wires terminal-exact vs design: {matched}/{len(WIRES)}")
    print(f"original wires matched to design: {len(design_to_orig)}/{len(WIRES)}")
    unreb = set(range(len(rebuild_wires))) - rebuild_used
    if unreb:
        print("rebuild conductors with no design match:",
              [f"w{i+1}" for i in sorted(unreb)])
    if problems:
        print("\nGEOMETRY PROBLEMS:")
        for p in problems:
            print(f"  {p}")
    if orig_problems:
        print("\nORIGINAL GEOMETRY (informational -- the original layout "
              "is not the checked grid, so crossings there do not fail "
              "the compare):")
        for p in orig_problems:
            print(f"  {p}")
    ok = (matched == len(WIRES)
          and len(design_to_orig) == len(WIRES)
          and not unreb
          and not problems)
    print(f"\nCOMPARE: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
