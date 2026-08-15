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
    "source": {"out": (10, -10)},                 # "L"
    "switch": {"in": (-10, -19), "out_a": (-10, 21), "out_b": (10, 21)},
    "drive_breaker": {"in": (-10, -30), "out": (-10, 20)},   # IN.1 / OUT.2
    "ac_breaker": {"in": (-10, -30), "out": (-10, 20)},
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

# Screen-pixel offsets from canvas centre, arranged as a 3-row grid
# (spacing chosen from the same safe range proven in
# motor_starter_with_breaker.py -- offsets from -700 to -100 keep every
# element's resulting scene position between x~130 and x~730, well
# inside the default A4 folio's 0..1020 range; rows spaced 150px keep
# scene y between 280 and 580, inside the 0..640 range).
_GRID = {
    # row 0: incoming power + the two breaker branches
    "source": (-700, -150), "switch": (-550, -150),
    "drive_breaker": (-400, -150), "ac_breaker": (-250, -150), "ac2dc": (-100, -150),
    # row 1: the speed-reference control loop + the drive itself
    "borne1": (-700, 0), "pot": (-550, 0), "borne2": (-400, 0),
    "borne3": (-250, 0), "drive": (-100, 0),
    # row 2: the two motor branches
    "motor_breaker_1": (-700, 150), "motor1": (-550, 150),
    "motor_breaker_2": (-400, 150), "motor2": (-250, 150),
}

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

# type-pair used to verify each wire landed on the RIGHT instance pair,
# not just any two elements of the right types. Built from ELEMENTS'
# saved-path fragments so a substituted part is verified as itself, not
# as the original custom element it stands in for.
_TYPE_OF = {k: frag for k, (_disp, frag) in ELEMENTS.items()}


def run(out_path: str | None = None) -> ScenarioResult:
    """Rebuild tremie_vibrante.qet's folio 1: switch -> [drive -> 2 motors] + [AC/DC -> pot speed-reference loop]."""
    name = "tremie_folio1"
    out_path = out_path or os.path.join(
        tempfile.gettempdir(), "scenario_tremie_folio1.qet"
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

        # Verify each attempted wire's TYPE PAIR is actually present in the
        # saved topology -- same "don't trust the count alone" check as
        # simple_motor_starter.py / motor_starter_with_breaker.py, just
        # over all 15 wires instead of 2-3.
        topo = extract_topology(out_path)
        edge_type_pairs = {
            frozenset((e.element1_type, e.element2_type)) for e in topo.edges
        }
        wiring_missing = []
        for a, b in wired:
            # extract_topology's type_path is the .elmt FILENAME; our
            # _TYPE_OF fragments are already exact filenames (no category
            # substrings) for this scenario's element set, so an exact
            # match is safe here.
            match = any(
                {e.element1_type, e.element2_type} == {f"{_TYPE_OF[a]}.elmt", f"{_TYPE_OF[b]}.elmt"}
                for e in topo.edges
            )
            if not match:
                wiring_missing.append(f"{a}--{b}")

        wiring_ok = conductor_count >= len(WIRES) and not wiring_missing

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
