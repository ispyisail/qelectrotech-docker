"""
tremie_folio2 — rebuild folio 2 ("SECURITE") of the real
tremie_vibrante.qet example project, element by element, using this
project's own automation, with the original file as the structural
reference check.

Reference: /home/user/qet-fix/examples/tremie_vibrante.qet, folio 2 of 3.
It's the safety page: a Pilz-style safety module (the original embeds a
Preventa XPS-AC), two pushbutton contact blocks, and four continuity
terminal blocks, wired into the classic two-channel E-stop loop
(AU block -> safety module channel -> AU block -> terminal).

Scope of this rebuild (same method as tremie_folio1.py): the real folio
has 23 placed elements, but 16 are decorative or cross-folio --
texte6 text labels (8), ref_folio_suivant (3) and ref_folio_precedent
(2) markers, plus 3 of the 17 conductors are purely between those
markers (8 of the 17 conductors touch a marker at least once). This
rebuilds the 7 real electrical components and the 9 real per-instance
wires that connect only electrical elements, verified against the
original file's own topology.

All three original types are embed://import elements that only exist
inside tremie_vibrante.qet itself (grepped the built image's whole
element tree -- same situation as folio 1's inter-sect_tetra). Stock
substitutes, chosen by function and verified with a live pre-flight
probe (each filter term placed into a scratch project and the saved
type path read back):

  - xps_ac.elmt -> pnoz_s3.elmt ("PNOZS3", Pilz PNOZ S3 safety module
      -- same device class; note its English display name has NO space)
  - a-u_004.elmt -> contattiausiliari.elmt ("Foot Switch (NO/NC)" --
      4-terminal 2NO+2NC contact block, the stock element that carries
      that display name; the filter matches the first row, and the
      probe confirmed that row is contattiausiliari, not foot_no_nc)
  - borne_continuite.elmt -> borne_2.elmt ("Terminal block" -- same
      terminal geometry: (0,-6)/(0,6) original vs (0,-10)/(0,10) stock;
      borne_continuite2's English display name is the generic "Terminal
      block" too and its first match is borne_2)

Search-language lesson from the probe (why these exact terms): QET's
filter matches the UI-language (English) display name ONLY -- not
filenames, not other-language names ("PNOZ S3" with a space matches
nothing; "continuite" matches nothing).

The real folio's xps_ac self-jumper (conductor between its terminals 4
and 5) is kept: it is a real conductor in the original and QET happily
connects two terminals of the same element.
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
# Display names verified live by the folio-2 pre-flight probe
# (/tmp/probe_folio2.py, run in the scenarios container) -- the probe
# placed each term and read the saved type back, so these are proven
# selectable, not just grepped.
ELEMENTS = {
    "xps":    ("PNOZS3",              "pnoz_s3"),
    "au1":    ("Foot Switch (NO/NC)", "contattiausiliari"),
    "au2":    ("Foot Switch (NO/NC)", "contattiausiliari"),
    "borne1": ("Terminal block",      "borne_2"),
    "borne2": ("Terminal block",      "borne_2"),
    "borne3": ("Terminal block",      "borne_2"),
    "borne4": ("Terminal block",      "borne_2"),
}

# Local terminal offsets (x, y), read directly from each substitute
# .elmt's own <terminal .../> tags. QET places the element with its
# definition origin at the drop point (DiagramEventAddElement sets
# setPos(scenePos), the hotspot is not applied -- consistent with
# folio 1's sub-15px termfind corrections), so no hotspot adjustment
# is needed. termfind refines against the real terminal pixels before
# every drag anyway (see tremie_folio1.py's TERMINALS note).
TERMINALS = {
    "xps": {"t_top_left": (-40, -31), "t_top_mid": (70, -31),
            "t_top_right": (90, -31), "t_bot_left": (-40, 61)},
    "au1": {"tLt": (-22, -20), "tRt": (25, -20), "tLb": (-22, 20), "tRb": (25, 20)},
    "au2": {"tLt": (-22, -20), "tRt": (25, -20), "tLb": (-22, 20), "tRb": (25, 20)},
    "borne1": {"top": (0, -10), "bottom": (0, 10)},
    "borne2": {"top": (0, -10), "bottom": (0, 10)},
    "borne3": {"top": (0, -10), "bottom": (0, 10)},
    "borne4": {"top": (0, -10), "bottom": (0, 10)},
}

# Screen-pixel offsets from canvas centre, mirroring the real page's
# relative layout (AUs stacked on the left, bornes to their right,
# safety module right of that).
#
# CRITICAL layout constraint, learned the hard way (first folio-2 run
# saved 13 conductors for 9 wires): QET's placement auto-connect fires
# between terminal COLUMNS that share an x (or y) coordinate, at ANY
# distance -- folio 2's first grid had same-x stacks (au1/au2, borne1/
# borne3, borne2/borne4) and QET auto-wired 4 spurious conductors.
# The same mechanism explains folio 1's 9 extra conductors: its grid
# had exactly 9 same-x column pairs (that scenario's "splits"
# explanation was wrong; it passes only because it checks >=).
# So: every element gets a unique x, and no two terminal x or y
# coordinates coincide anywhere in the grid. Terminals: au = x+{-22,25},
# borne = x, xps = x+{-40,70,90}. The ys (rows) are also all distinct.
# Verified with a wire-by-wire crossing check: no wire passes through
# another element's body (only proper terminal entries) and no two
# wires intersect, so the saved file must contain exactly 9 conductors.
_GRID = {
    "au1": (-700, -200), "au2": (-690, 100),
    "borne1": (-625, -100), "borne2": (-595, -110),
    "borne3": (-700, 160), "borne4": (-585, 60),
    "xps": (-350, -25),
}

# The 9 real per-instance wires between electrical elements, extracted
# from the original's own <conductor> entries with diagram-scoped
# terminal-id resolution (terminal ids are per-diagram in this file's
# format A). The xps entries map to the substitute's terminals:
# original t3(-50,-26)->(-40,-31), t4(70,-26)->(70,-31),
# t5(110,-26)->(90,-31), t10(-50,86)->(-40,61).
# (from_key, from_terminal, to_key, to_terminal).
WIRES = [
    ("xps", "t_top_mid", "xps", "t_top_right"),     # original 4 <-> 5 jumper
    ("borne1", "bottom", "au2", "tLt"),             # 27 <-> 21
    ("au1", "tLb", "borne1", "top"),                # 19 <-> 26
    ("borne2", "bottom", "au2", "tRt"),             # 29 <-> 22
    ("borne2", "top", "au1", "tRb"),                # 28 <-> 20
    ("borne3", "top", "au2", "tLb"),                # 31 <-> 23
    ("borne3", "bottom", "xps", "t_bot_left"),      # 32 <-> 10
    ("au2", "tRb", "borne4", "top"),                # 24 <-> 33
    ("borne4", "bottom", "xps", "t_top_left"),      # 34 <-> 3
]

# type-pair used to verify each wire landed on the RIGHT instance pair,
# not just any two elements of the right types. Built from ELEMENTS'
# saved-path fragments so a substituted part is verified as itself, not
# as the original custom element it stands in for.
_TYPE_OF = {k: frag for k, (_disp, frag) in ELEMENTS.items()}


def run(out_path: str | None = None) -> ScenarioResult:
    """Rebuild tremie_vibrante.qet's folio 2: two-channel safety loop (AU blocks -> safety module -> terminals)."""
    name = "tremie_folio2"
    out_path = out_path or os.path.join(
        tempfile.gettempdir(), "scenario_tremie_folio2.qet"
    )

    try:
        with ScenarioContext(name) as ctx:
            ctx.new_project()

            cx, cy = ctx.layout.canvas_cx, ctx.layout.canvas_cy
            attempted = {}
            drop_points = {}
            for key, (x_off, y_off) in _GRID.items():
                display_name, _frag = ELEMENTS[key]
                drop_points[key] = (cx + x_off, cy + y_off)
                attempted[key] = ctx.place_element(display_name, cx + x_off, cy + y_off)

            def _term_screen(key, which):
                dx, dy = drop_points[key]
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

        # Verify each attempted wire's TYPE PAIR is actually present in
        # the saved topology -- same "don't trust the count alone" check
        # as tremie_folio1.py, over all 9 wires. The xps self-jumper is
        # the degenerate pair {pnoz_s3, pnoz_s3}, which the frozenset
        # comparison handles naturally.
        topo = extract_topology(out_path)
        wiring_missing = []
        for a, b in wired:
            match = any(
                {e.element1_type, e.element2_type} == {f"{_TYPE_OF[a]}.elmt", f"{_TYPE_OF[b]}.elmt"}
                for e in topo.edges
            )
            if not match:
                wiring_missing.append(f"{a}--{b}")

        # Stricter than folio 1's >=: the grid above is alignment-free by
        # construction (no two terminal x or y coordinates coincide) and
        # no wire crosses another, so QET must save EXACTLY len(WIRES)
        # conductors. Any extra would be a spurious auto-connect, which
        # this scenario exists to detect -- >= would silently pass it.
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
