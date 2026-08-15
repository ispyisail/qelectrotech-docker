"""
tremie_folio1 — rebuild folio 1 ("COULOIR VIBRANT") of the real
tremie_vibrante.qet example project, element by element, using this
project's own automation, with the original file as the structural
reference check.

Reference: /home/user/qet-fix/examples/tremie_vibrante.qet, folio 1 of 3.
It's a VFD-driven dual-motor circuit: a main switch feeds two branches --
one through a breaker straight into a Digidrive SK variable-frequency
drive (which powers two motors, each through its own motor breaker), the
other through a second breaker into an AC/DC supply that, together with a
potentiometer and three terminal blocks, forms the drive's external speed
reference loop.

Scope of this rebuild (see the tremie_folio1 conversation for why): the
real folio has 29 placed elements, but 15 of those are decorative --
text labels (texte6.elmt), next-folio cross-reference markers
(ref_folio_suivant.elmt), and a page frame (cadre-*.elmt) -- carrying no
electrical connections. This rebuilds the 14 real electrical components
and all 15 real per-instance wires between them, verified against the
original file's own topology, not just against a plausible-looking
circuit. Wire numbering/labels are a separate follow-up, not attempted
here.

Two of the original's 14 real components -- disjoncteur_sectionneur_
magnetothermique.elmt (used for both motor breakers) and
inter-sect_tetra.elmt (the main switch) -- are NOT in QET's stock
collection: they only exist embedded inside tremie_vibrante.qet itself
(that project's own "Imported elements" -- confirmed by grepping the
built image's whole element tree and finding nothing). A fresh project
can't search for them. Substituted with the closest stock equivalents,
found and verified the same "read the real file, don't guess" way as
every other element in this project:
  - inter-sect_tetra.elmt      -> inter-sectionneur_tetra.elmt
      ("Four pole switch disconnector" -- same function, stock part)
  - disjoncteur_sectionneur_magnetothermique.elmt -> fa4202_disjoncteur_
      moteur_3p.elmt ("Motor circuit breaker" -- already used in
      motor_starter_with_breaker.py, terminal offsets already known)
"""
from __future__ import annotations

import logging
import os
import tempfile

from scenarios.base import ScenarioContext, ScenarioError, ScenarioResult
from scenarios.reference_circuit import extract_topology

log = logging.getLogger(__name__)

# key -> (display name to type into the Collections filter, saved-path
# fragment asserted against the saved <element type="..."> path).
# Display names verified via grep of <name lang="en"> on the built image,
# same requirement as every other scenario here -- QET's filter matches
# what the tree shows, not the .elmt filename.
ELEMENTS = {
    "source":         ("Single-pole source + neutral", "src_1p_pe_n"),
    "switch":         ("Four pole switch disconnector", "inter-sectionneur_tetra"),
    "drive_breaker":  ("Circuit-breaker",               "disjonct-m_1f"),
    "ac_breaker":     ("Circuit-breaker",                "disjonct-m_1f"),
    "ac2dc":          ("One-phase alternating > Direct", "ac2_dc"),
    "pot":            ("Potentiometer",                 "potentio_trimmer"),
    "borne1":         ("Terminal block",                "borne_2"),
    "borne2":         ("Terminal block",                "borne_2"),
    "borne3":         ("Terminal block",                "borne_2"),
    "drive":          ("Digidrive sk",                  "digidrive_sk"),
    "motor_breaker_1": ("Motor circuit breaker",         "fa4202_disjoncteur_moteur_3p"),
    "motor_breaker_2": ("Motor circuit breaker",         "fa4202_disjoncteur_moteur_3p"),
    "motor1":         ("Three-phase engine",             "moteur_tri"),
    "motor2":         ("Three-phase engine",              "moteur_tri"),
}

# Local terminal offsets (x, y), read directly from each .elmt's own
# <terminal .../> tags -- see individual scenario files' TERMINALS
# comments elsewhere in this module for why "read the file, don't guess"
# matters and why exactness isn't required (ScenarioContext.connect_
# terminals refines against the real pixel position via termfind before
# every drag). Multi-terminal parts (digidrive_sk, the disconnector, the
# breakers) pick ONE representative pole/terminal per real connection --
# this rebuild wires one conductor per real edge, not a full multi-phase
# bus, matching the same simplification already used in
# motor_starter_with_breaker.py.
TERMINALS = {
    "source": {"out": (10, -20)},                 # "L" (bottom pole)
    # out_a is the switch's RIGHT lower pole and feeds the drive breaker;
    # out_b is the LEFT lower pole and feeds ac_breaker. This assignment
    # (the reverse of the original's) keeps the out_b -> ac_breaker wire
    # clear of the drive breaker sitting between them (see the _GRID
    # comment below).
    "switch": {"in": (-10, -19), "out_a": (10, 21), "out_b": (-10, 21)},
    "drive_breaker": {"in": (0, -30), "out": (0, 20)},   # IN.1 / OUT.2
    "ac_breaker": {"in": (0, -30), "out": (0, 20)},
    "ac2dc": {"in": (-20, -10), "out": (20, -10)},            # "L" / "L+"
    "pot": {"a1": (0, -20), "a2": (0, 20), "s": (-10, 0)},
    "borne1": {"top": (0, -10), "bottom": (0, 10)},
    "borne2": {"top": (0, -10), "bottom": (0, 10)},
    "borne3": {"top": (0, -10), "bottom": (0, 10)},
    "drive": {
        "power_in": (-160, -30),
        "aux1": (-140, -30),
        "aux2": (-40, -30),
        "aux3": (-20, -30),
        "motor_out_a": (-160, 36),
        "motor_out_b": (-140, 36),
    },
    "motor_breaker_1": {"in": (0, 0), "out": (0, 60)},
    "motor_breaker_2": {"in": (0, 0), "out": (0, 60)},
    "motor1": {"in": (-20, -30)},                              # "U1"
    "motor2": {"in": (-20, -30)},
}

# Screen-pixel offsets from canvas centre (scene = screen - k, k chosen
# by QETLayout; offsets from -720 to +110 keep every element inside the
# default A4 folio's 0..1020 x 0..640 scene bounds).
#
# Layout rules, learned the hard way on this scenario's first runs:
#
#  1. The scenario calls ctx.disable_auto_conductor() after new_project
#     -- QET's placement auto-connect (AlignedFreeTerminals(), gated by
#     project()->autoConductor(), fires between terminal columns sharing
#     an x or y coordinate at ANY distance, ~10px tolerance) added 9
#     spurious conductors to the first runs of this exact grid. With the
#     toggle OFF the saved file must contain EXACTLY len(WIRES)
#     conductors, and that count is the per-run proof the toggle held.
#     (An alignment-free grid is impossible here anyway: the Digidrive
#     alone has 13 terminal columns.)
#  2. No element body overlaps another (the original grid sat borne3
#     INSIDE the drive's bbox, and termfind then grabbed the drive's
#     aux terminals for borne3's wires). The drive starts 15px right of
#     borne3 here.
#  3. Wires must not cross each other (QET splits conductors at
#     crossings, inflating the count) or pass through another element's
#     terminals/body. Every WIRES entry was checked against this grid
#     coordinate-by-coordinate; the three quirks that follow from it:
#     ac_breaker sits ABOVE the row so the switch's out_b feed climbs
#     over the drive breaker without touching it; pot/motor1/borne3 sit
#     on non-row ys so the drive's aux1 feed and pot's a2 feed clear
#     the pot and borne2 terminals they pass; motor1 is dropped 30px
#     below its row so the drive's motor_out_a feed passes above it.
_GRID = {
    # row 0: incoming power + the two breaker branches
    "source": (-700, -150), "switch": (-550, -150),
    "drive_breaker": (-400, -150), "ac_breaker": (-300, -260), "ac2dc": (-100, -150),
    # row 1: the speed-reference control loop + the drive itself
    "borne1": (-700, 0), "pot": (-550, 30), "borne2": (-400, 0),
    "borne3": (-250, 20), "drive": (-40, 0),
    # row 2: the two motor branches
    "motor_breaker_1": (-700, 150), "motor1": (-550, 180),
    "motor_breaker_2": (-400, 150), "motor2": (-250, 150),
}

# Placement verification search radius, per element: how far from the
# drop point the element's real red terminal pattern may sit. 120 covers
# every element's observed jitter without ever reaching a neighbour
# (grid spacing 150); the Digidrive's drag-and-drop commit lands with a
# nondeterministic hotspot offset (observed exact, +10px, -140/-130 and
# +224 across runs -- the mechanism is not understood, only measured),
# so it gets a whole-screenshot search: at placement time no other
# element on the canvas has its 6-terminal pattern, so the pattern
# score alone rejects everything else.
_SEARCH_RADIUS = {"drive": None}

# The 15 real per-instance wires, extracted directly from tremie_vibrante
# .qet's own <conductor> elements (element1/element2 resolved to which
# physical instance, not just which type -- see the "why" note at the top
# of this file: with 2 motors and 2 of each breaker type, a type-only
# match could wire the wrong breaker to the wrong motor and still look
# right). (from_key, from_terminal, to_key, to_terminal).
WIRES = [
    ("drive", "motor_out_b", "motor_breaker_2", "in"),
    ("drive", "motor_out_a", "motor_breaker_1", "in"),
    ("ac_breaker", "out", "ac2dc", "in"),
    ("drive", "aux3", "borne3", "top"),
    ("drive", "aux2", "borne2", "top"),
    ("drive", "aux1", "borne1", "top"),
    ("drive", "power_in", "drive_breaker", "out"),
    ("motor_breaker_2", "out", "motor2", "in"),
    ("motor_breaker_1", "out", "motor1", "in"),
    ("source", "out", "switch", "in"),
    ("switch", "out_a", "drive_breaker", "in"),
    ("borne2", "bottom", "pot", "s"),
    ("switch", "out_b", "ac_breaker", "in"),
    ("pot", "a2", "borne3", "bottom"),
    ("pot", "a1", "borne1", "bottom"),
]

def run(out_path: str | None = None) -> ScenarioResult:
    """Rebuild tremie_vibrante.qet's folio 1: switch -> [drive -> 2 motors] + [AC/DC -> pot speed-reference loop]."""
    name = "tremie_folio1"
    out_path = out_path or os.path.join(
        tempfile.gettempdir(), "scenario_tremie_folio1.qet"
    )

    try:
        with ScenarioContext(name) as ctx:
            ctx.new_project()
            ctx.disable_auto_conductor()

            cx, cy = ctx.layout.canvas_cx, ctx.layout.canvas_cy
            attempted = {}
            verified = {}
            for key, (x_off, y_off) in _GRID.items():
                display_name, _frag = ELEMENTS[key]
                drop = (cx + x_off, cy + y_off)
                attempted[key] = ctx.place_element(display_name, *drop)
                # Measure where the element ACTUALLY landed, don't trust
                # the drop point: the Digidrive's DND commit carries a
                # nondeterministic hotspot offset (see _SEARCH_RADIUS),
                # and a wire computed from the wrong origin can grab a
                # neighbour's terminal. Elements whose terminals don't
                # render red (source, breakers, ac2dc) return None and
                # fall back to the drop point -- their placement has
                # been exact in every run.
                origin = ctx.locate_element(
                    drop, list(TERMINALS[key].values()),
                    search_radius=_SEARCH_RADIUS.get(key, 120),
                )
                verified[key] = origin or drop
                log.info("placed %s: drop=%s verified=%s", key, drop, verified[key])

            def _term_screen(key, which):
                dx, dy = verified[key]
                ox, oy = TERMINALS[key][which]
                return (dx + ox, dy + oy)

            wired = []
            for a, ta, b, tb in WIRES:
                if attempted.get(a) and attempted.get(b):
                    ctx.connect_terminals(_term_screen(a, ta), _term_screen(b, tb))
                    wired.append((a, b))

            ctx.save_as(out_path)
            canon = ctx.verify(out_path)

        counts = canon.counts

        found = set()
        for diagram in canon.diagrams:
            for el in diagram["elements"].values():
                type_path = el.get("type") or ""
                for key, (_display, path_fragment) in ELEMENTS.items():
                    if path_fragment in type_path and key not in found:
                        found.add(key)
        missing = sorted(set(ELEMENTS) - found)

        outside = []
        for diagram in canon.diagrams:
            raw = diagram.get("raw_attrs", {})
            width = int(raw.get("cols", 17)) * int(raw.get("colsize", 60))
            height = int(raw.get("rows", 8)) * int(raw.get("rowsize", 80))
            for el in diagram["elements"].values():
                x, y = el.get("x"), el.get("y")
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    continue
                if not (0 <= x <= width and 0 <= y <= height):
                    outside.append(
                        f"{(el.get('type') or '').rsplit('/', 1)[-1]}@({x:.0f},{y:.0f})"
                    )

        conductor_count = counts.get("conductors", 0)

        # Verify each wire landed on the RIGHT INSTANCE PAIR. The old
        # type-pair check was instance-blind: with three bornes (and two
        # breakers, two motors) a missing drive->borne3 conductor was
        # silently "satisfied" by drive->borne2/borne1. This matches
        # every conductor's endpoint element POSITIONS against the
        # verified placement origins of the two intended elements
        # (verified[] is in screen coords, saved positions are scene
        # coords: scene = screen - k, k = (cx - 820, cy - 420) -- the
        # canvas centre maps to scene (820, 420)).
        topo = extract_topology(out_path)

        def _saved_pos(uuid):
            el = topo.elements.get(uuid)
            return (el.x, el.y) if el else None

        def _near(p, q, tol=80):
            return (p is not None and q is not None
                    and abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol)

        kx, ky = cx - 820, cy - 420
        verified_scene = {
            k: (sx - kx, sy - ky) for k, (sx, sy) in verified.items()
        }
        wiring_missing = []
        for a, b in wired:
            pa, pb = verified_scene[a], verified_scene[b]
            match = any(
                (_near(_saved_pos(e.element1_uuid), pa)
                 and _near(_saved_pos(e.element2_uuid), pb))
                or (_near(_saved_pos(e.element1_uuid), pb)
                    and _near(_saved_pos(e.element2_uuid), pa))
                for e in topo.edges
            )
            if not match:
                wiring_missing.append(f"{a}--{b}")

        # EXACT count, not >=: with auto-conductor off and a crossing-free
        # grid (see the _GRID comment), QET must save exactly len(WIRES)
        # conductors. Any extra would be a spurious auto-connect (toggle
        # failed) or a split at a wire crossing -- both of which this
        # scenario exists to detect; >= would silently pass them, which
        # is exactly how the first runs' 9 extras went unnoticed.
        wiring_ok = conductor_count == len(WIRES) and not wiring_missing

        passed = not missing and not outside and wiring_ok

        if counts.get("elements", 0) == 0:
            detail = (
                "saved project contains no elements at all -- most likely "
                "the collection filter matched nothing. "
                f"attempted={attempted}"
            )
        else:
            detail = (
                f"found={sorted(found)} missing={missing} "
                f"conductors={conductor_count}/{len(WIRES)} "
                f"wiring_missing={wiring_missing}"
            )

        return ScenarioResult(
            name=name, passed=passed, detail=detail,
            saved_project=out_path, counts=counts,
        )

    except ScenarioError as e:
        return ScenarioResult(name=name, passed=False, detail=str(e))
