"""
reference_circuit — extract wiring topology from a real, human-built .qet
project, to use as ground truth for a scenario's own wiring logic.

Why this exists
----------------
Computing "which terminal connects to which" from first principles (element
local coordinates + orientation + an inferred screen<->scene calibration) is
exactly the kind of geometry math that looks right and silently isn't --
the same category of bug as the five already found and fixed in
simple_motor_starter (wrong search terms, wrong click offset, wrong mouse
button, ...), just one layer deeper. Before trusting computed terminal
positions, this checks them against how a real project actually wired
the same or a similar element -- if one exists in QET's own examples/
folder, which several do (perceuse.qet and affuteuse_250h.qet both contain
real motor-starter circuits with a thermal relay, a contactor and a
three-phase motor).

Usage
-----
    python3 -m scenarios.reference_circuit /path/to/example.qet

    from scenarios.reference_circuit import extract_topology
    topo = extract_topology(Path("perceuse.qet"))
    for edge in topo.edges:
        print(edge.element1_type, edge.terminal1_id, "->",
              edge.element2_type, edge.terminal2_id)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


# NOTE ON THE REAL FORMAT -- there are TWO, not guessed, verified against
# real files:
#
# Format A (perceuse.qet, affuteuse_250h.qet -- older/other QET builds):
#   <element uuid="..." type="..." x=".." y="..">
#     <terminals>
#       <terminal id="245" x="0" y="4" orientation="0"/>   <!-- id is a
#         DIAGRAM-WIDE counter, NOT restarted per element: the next
#         element's first terminal continues from where this one left off. -->
#     </terminals>
#   <conductor terminal1="245" terminal2="308" .../>   <!-- these ARE those
#     global terminal ids, not element uuids. To find which element a
#     conductor touches, build id -> owning-element first. -->
#
# Format B (this repo's built qelectrotech binary, confirmed against a
# scenarios/simple_motor_starter.py save): <conductor> carries element1/
# element2 attributes DIRECTLY as the placed <element uuid="..."> values --
# no terminal-id lookup needed at all. Its terminal1/terminal2 are instead
# the STATIC per-elmt-definition terminal uuid (stable across every
# instance of that .elmt, e.g. every placed relais_mono.elmt shares the
# same four terminal uuids), which does NOT appear anywhere on the placed
# <element><terminals><terminal id=".."> tags (those only carry a fresh
# per-instance numeric id, no uuid) -- so format A's id-based resolution
# silently finds nothing on a format B file instead of erroring, which is
# exactly what happened the first time this ran against a real scenario
# save (topology checks all false despite 2 real conductors existing).
#
# extract_topology() below tries format B first (element1/element2 present
# on the <conductor> itself) and only falls back to the format A id-lookup
# when they're absent.


@dataclass
class ElementInfo:
    uuid: str
    type_path: str          # short name, e.g. "moteur_tri_1.elmt"
    x: float
    y: float
    orientation: str
    # global terminal id -> (local_x, local_y) for every terminal this
    # element has, straight from its own <terminals> block (present on
    # this instance because QET embeds the full element definition inside
    # the project, not just a reference to it).
    terminals: dict[str, tuple[float, float]]


@dataclass
class Edge:
    element1_uuid: str
    element1_type: str
    terminal1_id: str
    element2_uuid: str
    element2_type: str
    terminal2_id: str


@dataclass
class Topology:
    elements: dict[str, ElementInfo]   # uuid -> info
    edges: list[Edge]
    # Format B only: project-level collection terminal definitions,
    # static per-.elmt terminal uuid -> (local_x, local_y, orientation
    # letter n/e/s/w). These are what <conductor terminal1/terminal2>
    # uuids resolve through; empty on format-A files.
    terminal_defs: dict[str, tuple[float, float, str]] = field(default_factory=dict)

    def edges_for_type(self, type_fragment: str) -> list[Edge]:
        """Edges touching any element whose type path contains `type_fragment`."""
        return [
            e for e in self.edges
            if type_fragment in e.element1_type or type_fragment in e.element2_type
        ]


def _short_type(type_attr: str) -> str:
    return (type_attr or "").rsplit("/", 1)[-1]


def extract_topology(qet_path: str | Path) -> Topology:
    root = ET.parse(str(qet_path)).getroot()

    elements: dict[str, ElementInfo] = {}
    terminal_owner: dict[str, str] = {}   # global terminal id -> element uuid
    for el in root.iter("element"):
        uuid = el.get("uuid")
        if not uuid:
            continue
        terms = {}
        for t in el.iter("terminal"):
            tid = t.get("id")
            if tid is not None:
                terms[tid] = (float(t.get("x", 0)), float(t.get("y", 0)))
                terminal_owner[tid] = uuid
        elements[uuid] = ElementInfo(
            uuid=uuid,
            type_path=_short_type(el.get("type", "")),
            x=float(el.get("x", 0)),
            y=float(el.get("y", 0)),
            orientation=el.get("orientation", "0"),
            terminals=terms,
        )

    # Format B: project-level collection terminal definitions (static
    # per-.elmt uuids, orientation as letters). The placed elements'
    # own <terminals> use numeric ids, so uuid-carrying entries are the
    # collection defs -- skipped in the element loop above because they
    # don't live under an <element>.
    terminal_defs: dict[str, tuple[float, float, str]] = {}
    for t in root.iter("terminal"):
        tu = t.get("uuid")
        if tu is not None:
            terminal_defs[tu] = (float(t.get("x", 0)),
                                 float(t.get("y", 0)),
                                 t.get("orientation", "") or "n")

    edges: list[Edge] = []
    for c in root.iter("conductor"):
        t1id, t2id = c.get("terminal1"), c.get("terminal2")
        if t1id is None or t2id is None:
            continue

        # Format B: the conductor names its own elements directly.
        e1u = c.get("element1")
        e2u = c.get("element2")
        if e1u is None or e2u is None:
            # Format A: resolve through the diagram-wide terminal id map.
            e1u = terminal_owner.get(t1id)
            e2u = terminal_owner.get(t2id)

        e1 = elements.get(e1u) if e1u else None
        e2 = elements.get(e2u) if e2u else None
        edges.append(Edge(
            element1_uuid=e1u or "?",
            element1_type=e1.type_path if e1 else "?",
            terminal1_id=t1id,
            element2_uuid=e2u or "?",
            element2_type=e2.type_path if e2 else "?",
            terminal2_id=t2id,
        ))

    return Topology(elements=elements, edges=edges, terminal_defs=terminal_defs)


if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1] if len(sys.argv) > 1 else "perceuse.qet")
    topo = extract_topology(path)
    print(f"{len(topo.elements)} elements, {len(topo.edges)} conductor edges in {path.name}\n")
    print("Elements:")
    for info in topo.elements.values():
        print(f"  {info.type_path:35s} @ ({info.x:.0f},{info.y:.0f}) "
              f"orient={info.orientation} terminals={list(info.terminals.keys())}")
    print("\nEdges:")
    for e in topo.edges:
        print(f"  {e.element1_type} [term {e.terminal1_id}]  --wire-->  "
              f"{e.element2_type} [term {e.terminal2_id}]")
