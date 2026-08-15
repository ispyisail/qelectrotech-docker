"""
tremie_folio3 — rebuild folio 3 ("COMMANDE") of the real
tremie_vibrante.qet example project, element by element, using this
project's own automation, with the original file as the structural
reference check.

Reference: /home/user/qet-fix/examples/tremie_vibrante.qet, folio 3 of 3.
The control page: the Digidrive's control block fed through a pushbutton
chain (capteur -> poussoir -> contact_002 -> 6 aux contacts -> 2 coils)
plus an indicator lamp branch, distributed over five terminal blocks.

Scope of this rebuild (same method as tremie_folio1/2.py): the real
folio has 46 placed elements, but 28 are decorative or cross-folio --
18 texte6 text labels, 3 cadres, 6 ref_folio markers, and 1 indicator
lamp (lampe590) whose only wires run to markers. Of the 29 conductors,
11 touch only ref_folio markers. This rebuilds the 18 real electrical
elements and all 18 real per-instance wires between them, verified
against the original file's own topology (re-resolved with this file's
format-A terminal-id table: 18 non-marker conductors, and their type
pairs tally one-to-one with the WIRES list below).

Substitutes, verified with a live pre-flight probe (each filter term
placed into a scratch project and the saved type path read back -- see
the ELEMENTS table in tremie_folio3_grid.py for the probed
result_index per term):

  - borne_continuite-2011* (5 embed-only variants) -> borne_2
      ("Terminal block", index 0 -- borne_2 is the first match)
  - con_simple-2011* (2 embed-only variants) -> con_simple
      ("Simple contact", index 0)
  - bobine -> bobine3 ("Coil", index 0)

The other five types are stock in the original already: digidrive_sk,
capteur_opt_nc_4p ("Optic sensor (NC)", index 1), poussoir
("Push-button", index 3), contact_002 ("Switch 2 positions", index 2),
lampe2 ("Light", index 4).

Grid and routing are the checked design in tremie_folio3_grid.py: that
module ports QET's deterministic Conductor::generateConductorPath
(including the C++ integer-division and snap-down quirks) and verifies
every wire of this grid offline -- no overlaps, no crossings, no
segment through any element body (own element included), no body
overlaps, inside the scene. Run `python3 scenarios/tremie_folio3_grid.py`
to re-check. Three folio-3 features fall out of that check:

  * Three true junctions (two wires sharing one terminal), matching the
    original's own topology: D.bottom (wires 4+5), CS4.bottom (14+15),
    CS5.bottom (16+18). The live Part-A probe verified this exact
    pattern saves as exactly 2 conductors with no split, and connected
    terminals keep rendering red, so termfind refinement stays safe.
    Junction second-wires are ordered after the first wire of their
    terminal, and each is dragged with at most its START on the shared
    terminal (the probed configuration).
  * Wire 5 feeds P -> D.bottom, not D.east: routed to D.east the cas1
    vertical at D.east's extension (x=-380) crosses the horizontals of
    wires 4 and 6 no matter where CS1/CS2 sit; D.bottom shares a
    terminal with wire 4 instead.
  * CS1 sits 40px right of D (not 30): at 30px, wire 6's cas3 midline
    (-385) snaps down to -390, drawing the wire 2px inside D's own body.

Verification (what "verified" means here):

  * Element presence by saved type-path fragment, as in folio 1/2.
  * Each wire TERMINAL-exact: the conductor's element1/element2 uuids
    are mapped to grid keys by saved position vs the measured placement
    origin (per-axis tolerance 20px -- no two elements of this grid are
    within (20,20) of each other, so every pair is unique), and its
    terminal1/terminal2 ids (format B: static per-.elmt-definition
    uuids) resolve through the project-level <collection> definitions
    in the save; the definition's offset + orientation letter identify
    the terminal NAME against TERMINALS with a 1.5px exact match. A
    wire drawn on borne's east terminal instead of top therefore FAILS
    -- borne top/east are ~9px apart, far inside the 20px instance-pair
    tolerance that let exactly such swaps pass when this scenario only
    checked element pairs.
  * EXACT conductor count == len(WIRES). Two of the 18 wires (17 and
    18) share the same instance pair CS5<->CS6, so pair matching alone
    cannot tell a single CS5--CS6 edge from the required two; the exact
    count is what catches a missing one (17 != 18).
  * The drawing side is terminal-exact too: wire endpoints are computed
    from the measured origin + the .elmt terminal offsets and refined
    by termfind WITH the terminal's orientation, so the refinement
    anchors on the red mark lying in that terminal's direction rather
    than whichever mark is nearest. The plain nearest-mark refinement
    is what once snapped the borne top clicks onto the east marks and
    saved three wires on the wrong terminals (see termfind.py).
"""
from __future__ import annotations

import logging
import os
import tempfile

from scenarios.base import ScenarioContext, ScenarioError, ScenarioResult
from scenarios.reference_circuit import extract_topology
from scenarios.tremie_folio3_grid import ELEMENTS, TERMINALS, WIRES, _GRID

log = logging.getLogger(__name__)

# Placement verification search radius, per element (see tremie_folio1.py
# for the mechanism). The Digidrive's drag-and-drop commit lands with a
# nondeterministic hotspot offset (observed exact, +10px, -140/-130 and
# +224 across runs), so it gets a whole-screenshot search: it is placed
# FIRST, when no other element with red terminals exists on the canvas,
# so its 20-terminal pattern is the only thing the matcher can find.
_SEARCH_RADIUS = {"drive": None}

# Wire-pair verification tolerance in saved scene pixels per axis -- see
# the docstring's verification section for why 20 and not folio 1's 80.
_VERIFY_TOL = 20


def run(out_path: str | None = None) -> ScenarioResult:
    """Rebuild tremie_vibrante.qet's folio 3: capteur/poussoir/contact chain -> 6 aux contacts -> 2 coils + lamp branch."""
    name = "tremie_folio3"
    out_path = out_path or os.path.join(
        tempfile.gettempdir(), "scenario_tremie_folio3.qet"
    )

    try:
        with ScenarioContext(name) as ctx:
            ctx.new_project()
            ctx.disable_auto_conductor()

            cx, cy = ctx.layout.canvas_cx, ctx.layout.canvas_cy
            attempted = {}
            verified = {}
            for key, (x_off, y_off) in _GRID.items():
                display_name, _frag, result_index = ELEMENTS[key]
                drop = (cx + x_off, cy + y_off)
                attempted[key] = ctx.place_element(
                    display_name, *drop, result_index=result_index
                )
                # Measure where the element ACTUALLY landed, don't trust
                # the drop point (see _SEARCH_RADIUS / tremie_folio1.py).
                # TERMINALS values are ((x, y), orientation) pairs -- the
                # grid checker needs the orientation, the pattern matcher
                # and the wire math need only the offset.
                origin = ctx.locate_element(
                    drop, [t[0] for t in TERMINALS[key].values()],
                    search_radius=_SEARCH_RADIUS.get(key, 120),
                )
                verified[key] = origin or drop
                log.info("placed %s: drop=%s verified=%s", key, drop, verified[key])

            def _term_screen(key, which):
                dx, dy = verified[key]
                (ox, oy), _ori = TERMINALS[key][which]
                return (dx + ox, dy + oy)

            wired = []
            for a, ta, b, tb in WIRES:
                if attempted.get(a) and attempted.get(b):
                    # Pass each terminal's orientation so termfind's
                    # pixel refinement anchors on the mark in that
                    # terminal's direction (borne top/east are ~9px
                    # apart and plain nearest-mark snapping puts the
                    # wire on east -- see termfind._in_direction).
                    ctx.connect_terminals(
                        _term_screen(a, ta), _term_screen(b, tb),
                        TERMINALS[a][ta][1], TERMINALS[b][tb][1],
                    )
                    wired.append((a, b))

            ctx.save_as(out_path)
            canon = ctx.verify(out_path)

        counts = canon.counts

        found = set()
        for diagram in canon.diagrams:
            for el in diagram["elements"].values():
                type_path = el.get("type") or ""
                for key, (_display, path_fragment, _idx) in ELEMENTS.items():
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

        # Terminal-exact wiring verification (see the docstring's
        # verification section). Resolve each conductor's terminal ids
        # through the save's project-level collection definitions and
        # identify the terminal NAME by exact offset + orientation
        # against TERMINALS; a wire saved on borne east instead of top
        # fails here instead of passing under an instance-pair tolerance.
        topo = extract_topology(out_path)

        def _saved_pos(uuid):
            el = topo.elements.get(uuid)
            return (el.x, el.y) if el else None

        def _near(p, q):
            return (p is not None and q is not None
                    and abs(p[0] - q[0]) <= _VERIFY_TOL
                    and abs(p[1] - q[1]) <= _VERIFY_TOL)

        kx, ky = cx - 820, cy - 420
        verified_scene = {
            k: (sx - kx, sy - ky) for k, (sx, sy) in verified.items()
        }

        def _key_of(uuid):
            p = _saved_pos(uuid)
            if p is None:
                return None
            for k, vp in verified_scene.items():
                if _near(p, vp):
                    return k
            return None

        def _identify(key, dock, ori):
            if key is None:
                return None
            for tname, ((ox, oy), tori) in TERMINALS[key].items():
                if (abs(dock[0] - ox) <= 1.5 and abs(dock[1] - oy) <= 1.5
                        and ori == tori):
                    return tname
            return None

        wiring_missing = []
        edge_used = set()
        for a, ta, b, tb in WIRES:
            if not attempted.get(a) or not attempted.get(b):
                continue
            match = None
            for i, e in enumerate(topo.edges):
                if i in edge_used:
                    continue
                k1, k2 = _key_of(e.element1_uuid), _key_of(e.element2_uuid)
                if {k1, k2} != {a, b}:
                    continue
                d1 = topo.terminal_defs.get(e.terminal1_id)
                d2 = topo.terminal_defs.get(e.terminal2_id)
                if d1 is None or d2 is None:
                    continue
                n1 = _identify(k1, (d1[0], d1[1]), d1[2])
                n2 = _identify(k2, (d2[0], d2[1]), d2[2])
                if {n1, n2} == {ta, tb}:
                    match = i
                    break
            if match is None:
                wiring_missing.append(f"{a}.{ta}--{b}.{tb}")
            else:
                edge_used.add(match)

        # EXACT count, not >=: with auto-conductor off and the
        # checked grid (no alignments, no crossings), QET must save
        # exactly len(WIRES) conductors. This is also the only check
        # that separates the CS5<->CS6 double wire from a single one.
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
