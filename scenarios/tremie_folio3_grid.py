"""
tremie_folio3_grid — layout constants + offline routing check for
tremie_folio3 (folio 3 "COMMANDE" of tremie_vibrante.qet).

Why this exists
---------------
Folio 3's 18 wires have a routing risk the other two folios never did:
three-terminal junctions. borne_2's terminals (n/s/e) let wires share a
borne without sharing a terminal, but the folio's own topology still has
two true junctions (two wires departing one con_simple terminal), plus
wires whose deterministic routes come within a few pixels of a
neighbour's body (con_simple bodies are only 40px apart in places). A
grid that "looks right" can silently produce overlapping conductors,
wires crossing element bodies, or a wire that snaps to the wrong
terminal. Folio 1's 9-extra-conductor run and folio 2's 4-extra run
are the precedent: grids are checked before they are trusted.

QET's conductor path is fully deterministic
(Conductor::generateConductorPath + extendTerminal in
sources/qetgraphicsitem/conductor.cpp), so it is implemented here as a
faithful port (including the C++ integer-division quirks) and every wire
is routed offline. The module then verifies, for the layout below:

  * no two wires overlap collinearly, except the shared stub of a
    terminal both wires depart from (the documented junction case,
    proven by the live Part-A probe: two wires sharing one borne_2
    terminal save as exactly 2 conductors);
  * no wire crosses another, except a T-meet at a shared terminal's
    extension point (the same junction case);
  * no wire segment passes through a foreign element's body (bodies
    measured from each stock .elmt's drawing primitives);
  * no two element bodies overlap;
  * all wire geometry stays inside the canvas scene
    (x -820..200, y -420..220).

tremie_folio3.py imports its constants from here, so the scenario cannot
drift from the checked grid. Re-run the check with:

    python3 scenarios/tremie_folio3_grid.py

Terminal offsets and orientations below are read from the stock .elmt
files (the same files QET ships inside the scenarios image); the
scenario's result_index values come from the live folio-3 pre-flight
probe (see tremie_folio3.py's docstring for the probe's output).
"""
from __future__ import annotations

import math

GRID = 10

# --------------------------------------------------------------------- #
# Router port — Conductor::generateConductorPath + extendTerminal.
# Coordinates are scene coords (the conductor sits at the scene origin,
# so mapFromScene is the identity).
# --------------------------------------------------------------------- #

def _cround(v: float) -> float:
    """std::round / qRound: round half away from zero."""
    return math.copysign(math.floor(abs(v) + 0.5), v)


def _cdiv(a: int, b: int) -> int:
    """C++ int division: truncates toward zero."""
    return math.trunc(a / b)


def _snap_to_grid(v: int) -> int:
    """C++ `while (v % xGrid) --v;` — decrement until divisible by 10."""
    while v % GRID:
        v -= 1
    return v


def extend_terminal(terminal: tuple[float, float], orientation: str) -> tuple[float, float]:
    """extendTerminal(): +10 along the orientation, then round THAT to the
    nearest multiple of 10 (the non-moving coordinate is untouched)."""
    x, y = terminal
    if orientation == "n":
        return (x, _cround((y - 10) / 10) * 10)
    if orientation == "s":
        return (x, _cround((y + 10) / 10) * 10)
    if orientation == "e":
        return (_cround((x + 10) / 10) * 10, y)
    if orientation == "w":
        return (_cround((x - 10) / 10) * 10, y)
    raise ValueError(orientation)


def route(
    p1: tuple[float, float], o1: str, p2: tuple[float, float], o2: str
) -> list[tuple[float, float]]:
    """Port of Conductor::generateConductorPath. Returns the path point
    list in terminal-1 -> terminal-2 order: dock1, ext1, [corners],
    ext2, dock2 (consecutive duplicates kept, as in the C++)."""
    sp1, sp2 = p1, p2
    d1, d2 = extend_terminal(sp1, o1), extend_terminal(sp2, o2)

    if d1[0] <= d2[0]:
        depart, arrivee = d1, d2
        depart0, arrivee0 = sp1, sp2
        od, oa = o1, o2
    else:
        depart, arrivee = d2, d1
        depart0, arrivee0 = sp2, sp1
        od, oa = o2, o1

    points = [depart0, depart]
    if depart[1] < arrivee[1]:
        # descending path
        if (od == "n" and oa in ("s", "w")) or (od == "e" and oa == "w"):
            mx = _snap_to_grid(_cdiv(_cround(depart[0] + arrivee[0]), 2))
            points += [(mx, depart[1]), (mx, arrivee[1])]
        elif (od == "s" and oa in ("n", "e")) or (od == "w" and oa == "e"):
            my = _snap_to_grid(_cdiv(_cround(depart[1] + arrivee[1]), 2))
            points += [(depart[0], my), (arrivee[0], my)]
        elif od in ("n", "e") and oa in ("n", "e"):
            points += [(arrivee[0], depart[1])]
        else:
            points += [(depart[0], arrivee[1])]
    else:
        # ascending (or equal-y) path
        if (od == "w" and oa in ("e", "s")) or (od == "n" and oa == "s"):
            my = _snap_to_grid(_cdiv(_cround(depart[1] + arrivee[1]), 2))
            points += [(depart[0], my), (arrivee[0], my)]
        elif (od == "e" and oa in ("w", "n")) or (od == "s" and oa == "n"):
            mx = _snap_to_grid(_cdiv(_cround(depart[0] + arrivee[0]), 2))
            points += [(mx, depart[1]), (mx, arrivee[1])]
        elif od in ("w", "n") and oa in ("w", "n"):
            points += [(depart[0], arrivee[1])]
        else:
            points += [(arrivee[0], depart[1])]
    points += [arrivee, arrivee0]

    if d1[0] > d2[0]:
        points = points[::-1]
    return points


def segments(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segs = []
    for a, b in zip(points, points[1:]):
        if a != b:
            segs.append((a, b))
    return segs


# --------------------------------------------------------------------- #
# Layout constants — single source of truth for tremie_folio3.py.
# --------------------------------------------------------------------- #

# key -> (Collections filter display name, saved-type fragment,
#         probed result_index). Display names and indexes verified live
# by the folio-3 pre-flight probe (contact_002's index fixed by the
# treefind text-left matching fix).
ELEMENTS = {
    "drive": ("Digidrive sk",       "digidrive_sk",        0),
    "A":     ("Terminal block",     "borne_2",             0),
    "B":     ("Terminal block",     "borne_2",             0),
    "C":     ("Terminal block",     "borne_2",             0),
    "D":     ("Terminal block",     "borne_2",             0),
    "E":     ("Terminal block",     "borne_2",             0),
    "S":     ("Optic sensor (NC)",  "capteur_opt_nc_4p",   1),
    "P":     ("Push-button",        "poussoir",            3),
    "K":     ("Switch 2 positions", "contact_002",         2),
    "CS1":   ("Simple contact",     "con_simple",          0),
    "CS2":   ("Simple contact",     "con_simple",          0),
    "CS3":   ("Simple contact",     "con_simple",          0),
    "CS4":   ("Simple contact",     "con_simple",          0),
    "CS5":   ("Simple contact",     "con_simple",          0),
    "CS6":   ("Simple contact",     "con_simple",          0),
    "B1":    ("Coil",               "bobine3",             0),
    "B2":    ("Coil",               "bobine3",             0),
    "L2":    ("Light",              "lampe2",              4),
}

# Scene-coord drop points (canvas centre + these = click position).
# Mirrors the real page's relative arrangement: drive top-left, the
# capteur/poussoir/contact/borne chain in a column below it, the two
# coils and their feed contacts in the middle, the indicator lamp chain
# on the right. Every coordinate is a multiple of 10; see the module
# docstring for why the spacing is what it is.
# Every y is shifted -30 from the first design so no route touches the
# folio's scene bounds: at y=+220 wire 5's top horizontal would run
# along scene y = 640, the page's bottom edge (canvas centre maps to
# scene (820, 420)).
_GRID = {
    "drive": (-520, -310),
    "A":     (-430, -190),
    "P":     (-490, 160),
    "S":     (-400, -130),
    "B":     (-400, -60),
    "K":     (-410, 0),
    "C":     (-400, 60),
    # CS1 sits 40px right of D (not 30): wire 6 (D.top -> CS1.bottom)
    # takes the cas3 mid-line at (D.top.ext.x + CS1.bottom.ext.x)/2,
    # and at 30px spacing the -385 mid snaps down to -390 -- 2px inside
    # D's body (D spans x -404..-388). At 40px the mid is -380, 8px
    # clear of D's edge and 11px clear of CS1's.
    "CS1":   (-360, 110),
    "D":     (-400, 130),
    "E":     (-320, -80),
    "CS2":   (-330, 70),
    "CS3":   (-190, 10),
    "CS4":   (-190, 70),
    "B1":    (-230, 130),
    "B2":    (-130, 130),
    "CS5":   (90, -210),
    "CS6":   (160, -210),
    "L2":    (90, 120),
}

# Local terminal offsets + orientation, read from each stock .elmt's
# <terminal .../> tags (orientation as the .elmt spells it: n/s/e/w).
TERMINALS = {
    "drive": {
        "n-160": ((-160, -30), "n"), "n-140": ((-140, -30), "n"),
        "n-40": ((-40, -30), "n"), "n-20": ((-20, -30), "n"),
        "n0": ((0, -30), "n"), "n20": ((20, -30), "n"),
        "n40": ((40, -30), "n"),
        "s-160": ((-160, 36), "s"), "s-140": ((-140, 36), "s"),
        "s-120": ((-120, 36), "s"), "s-100": ((-100, 36), "s"),
        "s-40": ((-40, 36), "s"), "s-20": ((-20, 36), "s"),
        "s0": ((0, 36), "s"), "s20": ((20, 36), "s"),
        "s40": ((40, 36), "s"), "s60": ((60, 36), "s"),
        "s80": ((80, 36), "s"), "s130": ((130, 36), "s"),
        "s150": ((150, 36), "s"),
    },
    "A": {"top": ((0, -10), "n"), "bottom": ((0, 10), "s"), "east": ((10, 0), "e")},
    "B": {"top": ((0, -10), "n"), "bottom": ((0, 10), "s")},
    "C": {"top": ((0, -10), "n"), "bottom": ((0, 10), "s")},
    "D": {"top": ((0, -10), "n"), "bottom": ((0, 10), "s"), "east": ((10, 0), "e")},
    "E": {"top": ((0, -10), "n"), "bottom": ((0, 10), "s")},
    "S": {"nw": ((-10, -30), "n"), "ne": ((10, -30), "n"),
          "sw": ((-10, 30), "s"), "se": ((10, 30), "s")},
    "P": {"top": ((0, -21), "n"), "bottom": ((0, 21), "s")},
    "K": {"top": ((10, -20), "n"), "bottom": ((10, 20), "s")},
    "CS1": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "CS2": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "CS3": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "CS4": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "CS5": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "CS6": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "B1": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "B2": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
    "L2": {"top": ((0, -20), "n"), "bottom": ((0, 20), "s")},
}

# The 18 real wires between electrical elements of folio 3, resolved
# from the original's <conductor> entries with the folio's own terminal
# coordinates (see the 29-conductor resolution in the transcript):
#
#   drive -> A (supply), A -> P, P -> D, D -> CS1, C -> CS1, K -> C,
#   B -> K, S -> B, S -> A (sensor return to the supply junction),
#   D -> CS2, CS2 -> E (continuation), drive -> CS3, CS3 -> CS4,
#   CS4 -> B1 and B2 -> CS4 (both coils off one contact, junction),
#   CS5 -> L2, CS6 -> CS5 top-top and CS5 -> CS6 bottom-bottom
#   (the folio's parallel double link), CS5's bottom is a junction.
#
# (from_key, from_terminal, to_key, to_terminal). Junction second wires
# (5, 15, 18) are ordered after the first wire of their shared terminal.
# Wire 5 uses D.bottom, not D.east: routing P.bottom -> D.east puts the
# cas1 vertical at D.east's extension (x=-380, y=160..220) straight
# through the horizontals of wires 4 (y=180) and 6 (y=170) no matter
# where CS1/CS2 sit. D.bottom shares a terminal with wire 4 instead --
# the same junction pattern the Part-A probe verified (two wires off one
# borne_2 terminal save as exactly 2 conductors, T-meet at the shared
# extension point).
WIRES = [
    ("drive", "s150", "A", "top"),      # 2
    ("drive", "n40", "CS3", "top"),     # 8
    ("CS2", "top", "E", "bottom"),      # 4
    ("D", "bottom", "CS2", "bottom"),   # 6
    ("P", "bottom", "D", "bottom"),     # 7   (junction at D.bottom)
    ("D", "top", "CS1", "bottom"),      # 10
    ("C", "bottom", "CS1", "top"),      # 11
    ("K", "bottom", "C", "top"),        # 12
    ("A", "bottom", "P", "top"),        # 13
    ("B", "bottom", "K", "top"),        # 14
    ("S", "se", "B", "top"),            # 15
    ("S", "nw", "A", "east"),           # 20
    ("CS3", "bottom", "CS4", "top"),    # 28
    ("CS4", "bottom", "B1", "top"),     # 27
    ("B2", "bottom", "CS4", "bottom"),  # 26  (junction at CS4.bottom)
    ("CS5", "bottom", "L2", "top"),     # 17
    ("CS6", "top", "CS5", "top"),       # 19
    ("CS5", "bottom", "CS6", "bottom"), # 21  (junction at CS5.bottom)
]

# Body rects relative to the element origin, measured from each stock
# .elmt's drawing primitives (lines/rects/polygons/ellipses -- text is
# excluded). Slightly padded toward the terminals where the stubs live.
BODIES = {
    "drive": (-170, -31, 185, 37),
    "A": (-4, -11, 12, 11),
    "B": (-4, -11, 4, 11),
    "C": (-4, -11, 4, 11),
    "D": (-4, -11, 12, 11),
    "E": (-4, -11, 4, 11),
    "S": (-21, -31, 21, 31),
    "P": (-11, -22, 11, 22),
    "K": (-16, -21, 17, 21),
    "CS1": (-9, -21, 9, 21),
    "CS2": (-9, -21, 9, 21),
    "CS3": (-9, -21, 9, 21),
    "CS4": (-9, -21, 9, 21),
    "CS5": (-9, -21, 9, 21),
    "CS6": (-9, -21, 9, 21),
    "B1": (-15, -21, 15, 21),
    "B2": (-15, -21, 15, 21),
    "L2": (-11, -21, 11, 21),
}

SCENE = (-820, -420, 200, 220)

# How close a segment endpoint may get to a dock before the segment is
# treated as "the stub of that dock" (dock->ext is 10px; the cas1/cas4
# backtrack corners sit 10px back from the dock, so 16 covers both).
_STUB_RADIUS = 16.0


def _dock_world(key: str, term: str) -> tuple[float, float]:
    (x, y) = _GRID[key]
    (ox, oy), _ori = TERMINALS[key][term]
    return (x + ox, y + oy)


def _wire_paths():
    paths = {}
    for a, ta, b, tb in WIRES:
        pa = _dock_world(a, ta)
        pb = _dock_world(b, tb)
        oa = TERMINALS[a][ta][1]
        ob = TERMINALS[b][tb][1]
        paths[(a, ta, b, tb)] = route(pa, oa, pb, ob)
    return paths


def _dist(p: tuple[float, float], q: tuple[float, float]) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _on_segment(p, a, b, eps=0.5) -> bool:
    return (min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
            and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps)


def _seg_intersection(s1, s2):
    """Intersection of two axis-aligned segments: None, a point, or the
    overlapping sub-segment (collinear)."""
    (a, b), (c, d) = s1, s2
    v1 = a[0] == b[0]   # s1 vertical?
    v2 = c[0] == d[0]
    if v1 and v2:
        if abs(a[0] - c[0]) > 1e-6:
            return None
        y0, y1 = sorted((a[1], b[1]))
        z0, z1 = sorted((c[1], d[1]))
        lo, hi = max(y0, z0), min(y1, z1)
        if lo > hi + 1e-6:
            return None
        if lo == hi:
            return (a[0], lo)
        return ((a[0], lo), (a[0], hi))
    if not v1 and not v2:
        if abs(a[1] - c[1]) > 1e-6:
            return None
        x0, x1 = sorted((a[0], b[0]))
        w0, w1 = sorted((c[0], d[0]))
        lo, hi = max(x0, w0), min(x1, w1)
        if lo > hi + 1e-6:
            return None
        if lo == hi:
            return (lo, a[1])
        return ((lo, a[1]), (hi, a[1]))
    (vert, horiz) = (s1, s2) if v1 else (s2, s1)
    (av, bv), (ah, bh) = vert, horiz
    if not (ah[0] - 1e-6 <= av[0] <= bh[0] + 1e-6):
        return None
    if not (min(av[1], bv[1]) - 1e-6 <= ah[1] <= max(av[1], bv[1]) + 1e-6):
        return None
    return (av[0], ah[1])


def check(verbose: bool = True) -> tuple[bool, list[str]]:
    """Route every wire and verify the module's own layout. Returns
    (ok, messages)."""
    problems: list[str] = []

    paths = _wire_paths()
    wire_keys = list(paths)

    # Map every wire's two docks to their owning elements.
    wire_docks = {}       # wire -> [dock0, dock1]
    dock_owner = {}       # (element, terminal) -> dock world pos
    for a, ta, b, tb in wire_keys:
        da = _dock_world(a, ta)
        db = _dock_world(b, tb)
        wire_docks[(a, ta, b, tb)] = [da, db]
        dock_owner[(a, ta)] = da
        dock_owner[(b, tb)] = db

    # Which wires share a dock (junction).
    shared = {}
    for key in wire_keys:
        for d in wire_docks[key]:
            shared.setdefault(d, []).append(key)
    shared = {d: ws for d, ws in shared.items() if len(ws) > 1}

    def is_own_stub(wire, seg, dock) -> bool:
        """Is `seg` a stub of `dock` in `wire`'s path (both endpoints
        within _STUB_RADIUS of the dock)?"""
        return (_dist(seg[0], dock) <= _STUB_RADIUS
                and _dist(seg[1], dock) <= _STUB_RADIUS)

    def shared_stub_pair(s1, w1, s2, w2) -> bool:
        for dock, ws in shared.items():
            if w1 in ws and w2 in ws:
                if (is_own_stub(w1, s1, dock) and is_own_stub(w2, s2, dock)):
                    return True
        return False

    def allowed_t_meet(p, w1, w2) -> bool:
        """Crossing/T-meet at point p allowed only at the extension
        point of a dock shared by both wires, with each involved
        segment touching p as an endpoint or being that dock's stub."""
        for dock, ws in shared.items():
            if w1 not in ws or w2 not in ws:
                continue
            ext = extend_terminal(dock, _dock_orientation(dock))
            if _dist(p, ext) > 1e-6:
                continue
            return True
        return False

    # dock -> orientation, for extension-point computation.
    dock_ori = {}
    for (el, term), d in dock_owner.items():
        dock_ori[d] = TERMINALS[el][term][1]

    def _dock_orientation(dock):
        return dock_ori[dock]

    if verbose:
        print("wire routes (scene coords):")
    for key in wire_keys:
        pts = paths[key]
        if verbose:
            print(f"  {key[0]}.{key[1]} -> {key[2]}.{key[3]}: "
                  + " -> ".join(f"({x:.0f},{y:.0f})" for x, y in pts))

    segs_of = {k: segments(paths[k]) for k in wire_keys}

    # 1. wire-vs-wire conflicts.
    for i, k1 in enumerate(wire_keys):
        for k2 in wire_keys[i + 1:]:
            for s1 in segs_of[k1]:
                for s2 in segs_of[k2]:
                    hit = _seg_intersection(s1, s2)
                    if hit is None:
                        continue
                    if isinstance(hit, tuple) and len(hit) == 2 and (
                            isinstance(hit[0], tuple)):
                        # collinear overlap
                        if shared_stub_pair(s1, k1, s2, k2):
                            continue
                        problems.append(
                            f"OVERLAP {k1[0]}.{k1[1]}-{k1[2]}.{k1[3]} "
                            f"x {k2[0]}.{k2[1]}-{k2[2]}.{k2[3]} at {hit}")
                    else:
                        # point hit: crossing or endpoint-on-segment
                        p = hit
                        if allowed_t_meet(p, k1, k2):
                            continue
                        problems.append(
                            f"CROSS  {k1[0]}.{k1[1]}-{k1[2]}.{k1[3]} "
                            f"x {k2[0]}.{k2[1]}-{k2[2]}.{k2[3]} at {p}")

    # 2. body collisions -- including the wire's OWN element's body. The
    # only exempt segments are the two terminal stubs (both endpoints
    # within _STUB_RADIUS of one of the wire's docks: the dock sits on
    # the body edge by stock design, so the stub grazes it by 0-2px).
    # A non-stub segment passing through its own element means the
    # router's mid-line landed inside the element -- visually a wire
    # drawn across the symbol -- which the deterministic router does
    # silently, so it must be caught here. (Wire 6 at CS1.x=-370 did
    # exactly this: mid-x -385 snapped to -390, 21px inside D's body.)
    for k in wire_keys:
        a, ta, b, tb = k
        docks = (wire_docks[k][0], wire_docks[k][1])
        for s in segs_of[k]:
            stub = any(
                _dist(s[0], d) <= _STUB_RADIUS and _dist(s[1], d) <= _STUB_RADIUS
                for d in docks
            )
            if stub:
                continue
            ax, ay, bx, by = s[0][0], s[0][1], s[1][0], s[1][1]
            # shrink by 1px so tangent grazes at a body edge count only
            # when they actually enter.
            if ax == bx:
                lo, hi = min(ay, by) + 1, max(ay, by) - 1
                x0, x1 = ax, ax
            else:
                lo, hi = min(ax, bx) + 1, max(ax, bx) - 1
                x0, x1 = lo, hi
                lo, hi = ay, ay
            if x1 < x0 or hi < lo:
                continue
            for el, (bx0, by0, bx1, by1) in BODIES.items():
                ex0 = _GRID[el][0] + bx0
                ey0 = _GRID[el][1] + by0
                ex1 = _GRID[el][0] + bx1
                ey1 = _GRID[el][1] + by1
                if x1 < ex0 or x0 > ex1 or hi < ey0 or lo > ey1:
                    continue
                problems.append(
                    f"BODY   {k[0]}.{k[1]}-{k[2]}.{k[3]} segment "
                    f"({s[0][0]:.0f},{s[0][1]:.0f})-({s[1][0]:.0f},{s[1][1]:.0f}) "
                    f"enters {el} body")

    # 3. element-body overlaps.
    keys = list(_GRID)
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            (a0, a1, a2, a3) = BODIES[k1]
            (b0, b1, b2, b3) = BODIES[k2]
            ra = (_GRID[k1][0] + a0, _GRID[k1][1] + a1,
                  _GRID[k1][0] + a2, _GRID[k1][1] + a3)
            rb = (_GRID[k2][0] + b0, _GRID[k2][1] + b1,
                  _GRID[k2][0] + b2, _GRID[k2][1] + b3)
            if ra[2] > rb[0] and rb[2] > ra[0] and ra[3] > rb[1] and rb[3] > ra[1]:
                problems.append(f"BODIES {k1} overlaps {k2}")

    # 4. scene bounds.
    for k in wire_keys:
        for x, y in paths[k]:
            if not (SCENE[0] <= x <= SCENE[2] and SCENE[1] <= y <= SCENE[3]):
                problems.append(f"BOUNDS {k[0]}.{k[1]}-{k[2]}.{k[3]} "
                                f"point ({x:.0f},{y:.0f}) outside scene")

    # 5. terminal usage: every wire's terminals exist; junction docks
    # are only on borne/con_simple terminals.
    for a, ta, b, tb in WIRES:
        assert a in TERMINALS and ta in TERMINALS[a], (a, ta)
        assert b in TERMINALS and tb in TERMINALS[b], (b, tb)

    ok = not problems
    if verbose:
        print()
        if ok:
            print("grid check PASS: no overlaps, crossings, body or "
                  "bounds violations")
        else:
            print(f"grid check FAIL ({len(problems)} problems):")
            for p in problems:
                print("  " + p)
    return ok, problems


if __name__ == "__main__":
    import sys
    ok, _problems = check(verbose=True)
    sys.exit(0 if ok else 1)
