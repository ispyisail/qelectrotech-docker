"""
motor_starter_with_breaker — a more complex scenario built on top of
simple_motor_starter's pattern: a standard direct-online motor starter
with FOUR elements instead of three, in the conventional real-world
order --

    line -> Motor circuit breaker -> Contactor -> Thermal relay -> Motor

(protection switch, then the switching contactor, then the current-
sensing overload relay placed right before the motor, which is the usual
textbook DOL starter arrangement and the same relative ordering visible
around perceuse.qet's fa4202_disjoncteur_moteur_3p / KM_tetra / moteur_tri
elements in scenarios/reference_circuit.py's output).

Same harness, same verification approach as simple_motor_starter.py:
GUI-driven placement + drag-based wiring (ScenarioContext.place_element /
connect_terminals), then assert on the saved file via simulator.canon and
reference_circuit's topology extractor -- not on screenshots.
"""
from __future__ import annotations

import logging
import os
import tempfile

from scenarios.base import ScenarioContext, ScenarioError, ScenarioResult
from scenarios.reference_circuit import extract_topology

log = logging.getLogger(__name__)

# Same DISPLAY NAME requirement as simple_motor_starter.py's ELEMENTS --
# QET's collection filter matches <name lang="en"> when present, not the
# .elmt filename. Verified via grep on the built image, not guessed.
ELEMENTS = {
    #  key         display name (typed)        saved-path fragment (asserted)
    "breaker":     ("Motor circuit breaker", "fa4202_disjoncteur_moteur_3p"),
    "contactor":   ("Contactor CRM",         "contacteur_crm"),
    "overload_relay": ("Thermal relay",      "30_thermal_relays"),
    "motor":       ("Three-phase engine",    "moteur_tri"),
}

# Local terminal offsets (x, y), read directly from each .elmt's own
# <terminal .../> tags in the built image -- see simple_motor_starter.py's
# TERMINALS comment for why these are close-but-not-exact and why that's
# fine (ScenarioContext.connect_terminals refines against the real pixel
# position via termfind before every drag).
#
# fa4202_disjoncteur_moteur_3p has 3 poles (x=0/20/40); the x=40 pole is
# used here, matching the pattern of using one pole for the demo the
# other two-terminal elements already establish.
TERMINALS = {
    "breaker": {"in": (40, 0), "out": (40, 60)},
    "contactor": {"in": (10, -20), "out": (10, 90)},
    "overload_relay": {"in": (10, -20), "out": (10, 20)},
    "motor": {"in": (-20, -30)},
}

# Screen-pixel offsets from canvas centre for 4 elements, 200px apart,
# left-biased like simple_motor_starter.py's -- verified to keep every
# element's scene position inside the default A4 folio's 0..1020 x-range
# (offset -640 -> scene x~190 ... offset -40 -> scene x~790, all clear of
# both edges with margin, unlike a naive symmetric spread would be).
_ORDER = (("breaker", -640), ("contactor", -440), ("overload_relay", -240), ("motor", -40))


def run(out_path: str | None = None) -> ScenarioResult:
    """Build: motor circuit breaker -> contactor -> thermal relay -> motor."""
    name = "motor_starter_with_breaker"
    out_path = out_path or os.path.join(
        tempfile.gettempdir(), "scenario_motor_starter_with_breaker.qet"
    )

    try:
        with ScenarioContext(name) as ctx:
            ctx.new_project()

            cx, cy = ctx.layout.canvas_cx, ctx.layout.canvas_cy
            attempted = {}
            drop_points = {}
            for key, x_off in _ORDER:
                display_name, _path_fragment = ELEMENTS[key]
                drop_points[key] = (cx + x_off, cy)
                attempted[key] = ctx.place_element(display_name, cx + x_off, cy)

            def _term_screen(key, which):
                dx, dy = drop_points[key]
                ox, oy = TERMINALS[key][which]
                return (dx + ox, dy + oy)

            # breaker -> contactor -> overload_relay -> motor, each wire
            # skipped if either endpoint's placement wasn't even attempted
            # successfully (place_element already only reports the
            # interaction was performed, not that insertion happened --
            # this just avoids wiring from/to a drop that clearly failed).
            chain = ("breaker", "contactor", "overload_relay", "motor")
            for a, b in zip(chain, chain[1:]):
                if attempted.get(a) and attempted.get(b):
                    ctx.connect_terminals(
                        _term_screen(a, "out"), _term_screen(b, "in")
                    )

            ctx.save_as(out_path)
            canon = ctx.verify(out_path)

        counts = canon.counts

        found = set()
        for diagram in canon.diagrams:
            for el in diagram["elements"].values():
                type_path = el.get("type") or ""
                for key, (_display, path_fragment) in ELEMENTS.items():
                    if path_fragment in type_path:
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

        # Three wires attempted (breaker->contactor, contactor->relay,
        # relay->motor); check the real chain via topology, same "don't
        # trust the count alone" logic as simple_motor_starter.py.
        topo = extract_topology(out_path)

        def _edge_exists(type_a: str, type_b: str) -> bool:
            return any(
                {e.element1_type, e.element2_type} == {type_a, type_b}
                for e in topo.edges
            )

        breaker_to_contactor = _edge_exists(
            "fa4202_disjoncteur_moteur_3p.elmt", "contacteur_crm.elmt"
        )
        contactor_to_relay = _edge_exists("contacteur_crm.elmt", "relais_mono.elmt")
        relay_to_motor = _edge_exists("relais_mono.elmt", "moteur_tri.elmt")

        wiring_ok = (
            conductor_count >= 3
            and breaker_to_contactor
            and contactor_to_relay
            and relay_to_motor
        )

        passed = not missing and not outside and wiring_ok

        if counts.get("elements", 0) == 0:
            detail = (
                "saved project contains no elements at all -- most likely "
                "the collection filter matched nothing (search terms must "
                f"be display names, not filenames). attempted={attempted}"
            )
        else:
            detail = (
                f"attempted={attempted} found_in_saved_file={sorted(found)} "
                f"missing={missing} conductors={conductor_count} "
                f"breaker_to_contactor={breaker_to_contactor} "
                f"contactor_to_relay={contactor_to_relay} "
                f"relay_to_motor={relay_to_motor}"
            )

        return ScenarioResult(
            name=name, passed=passed, detail=detail,
            saved_project=out_path, counts=counts,
        )

    except ScenarioError as e:
        return ScenarioResult(name=name, passed=False, detail=str(e))
