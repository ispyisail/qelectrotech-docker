"""
simple_motor_starter — the first scenario: open QET, build a minimal
three-phase motor starter (thermal overload relay + contactor + motor,
wired in series), save it, and verify the saved file actually contains
what was placed.

This is the template for future scenarios: launch via ScenarioContext,
place elements by searching the collection (not by hardcoded tree
position -- category structure has moved before, see #672 in this
project's own history), wire/save, then assert on simulator.canon's
parsed structure rather than a screenshot.
"""
from __future__ import annotations

import logging
import os
import tempfile

from scenarios.base import ScenarioContext, ScenarioError, ScenarioResult

log = logging.getLogger(__name__)

# Element search terms -- matched against the Collections filter box, not
# a hardcoded category path. See ScenarioContext.find_element_in_collection.
#
# CRITICAL: these must be the element's DISPLAY NAME in the running UI
# language, NOT its .elmt filename. QET's collection filter matches what
# the tree displays, and the tree displays <name lang="..."> from inside
# the .elmt when one exists for the current language, falling back to the
# filename only when it doesn't.
#
# This cost real debugging time: searching "relais_therm1" (the filename)
# returns zero matches because that element carries <name lang="en">
# Thermal relay</name>. Confusingly, searching "moteur_tri" DID return
# hits -- but only the two 500_home_installation copies, which happen to
# have names for ca/cs/fr/pt_BR/zh and no "en", so those alone fall back
# to showing their filename. Matching on filenames is therefore not just
# wrong, it's inconsistently wrong, which is worse.
#
# The second value is what the saved <element type="..."> path is asserted
# to contain. It is deliberately a CATEGORY fragment, not an exact
# filename, for the overload relay: several distinct .elmt files share the
# display name "Thermal relay" (relais_mono, relais_therm1, relais_therm4,
# ...), so the filter's first hit is whichever the tree happens to order
# first -- observed to be relais_mono.elmt. Asserting an exact filename
# there fails even though the scenario did exactly the right thing.
# Asserting the category says what we actually care about: "an element
# from the thermal-relays family was placed".
ELEMENTS = {
    #  key              display name (typed)     saved-path fragment (asserted)
    "overload_relay": ("Thermal relay",      "30_thermal_relays"),
    "contactor":      ("Contactor CRM",      "contacteur_crm"),
    "motor":          ("Three-phase engine", "moteur_tri"),
}


def run(out_path: str | None = None) -> ScenarioResult:
    """Build: thermal overload relay -> contactor -> three-phase motor."""
    name = "simple_motor_starter"
    out_path = out_path or os.path.join(
        tempfile.gettempdir(), "scenario_simple_motor_starter.qet"
    )

    try:
        with ScenarioContext(name) as ctx:
            ctx.new_project()

            cx, cy = ctx.layout.canvas_cx, ctx.layout.canvas_cy
            # NB: `attempted`, not `placed`. Driving the GUI can only
            # confirm the interaction was performed, never that QET
            # actually inserted anything -- an earlier version of this
            # returned True here regardless and reported "placed" for
            # elements that were never inserted, which hid the real bug
            # (wrong search terms) behind a false success signal for a
            # long time. The saved file, read back through canon below,
            # is the only source of truth about what really landed.
            # Screen-pixel offsets from the canvas centre. These are biased
            # LEFT because the folio does not fill the canvas widget: with
            # the default A4 folio (cols=17 x colsize=60 => 1020 units wide,
            # rows=8 x rowsize=80 => 640 tall) a drop at the canvas centre
            # lands at scene x~840, so a symmetric -200/0/+200 spread put
            # the third element at x=1040 -- past the 1020 right edge, i.e.
            # outside the drawn frame. Verified against the saved file, and
            # now guarded by the in-folio assertion below so this cannot
            # regress unnoticed.
            attempted = {}
            for key, x_off in (("overload_relay", -540), ("contactor", -340), ("motor", -140)):
                display_name, _path_fragment = ELEMENTS[key]
                attempted[key] = ctx.place_element(display_name, cx + x_off, cy)

            ctx.save_as(out_path)
            canon = ctx.verify(out_path)

        counts = canon.counts

        # Which of our target elements actually made it into the file,
        # matched on the saved <element type="..."> path (which is the
        # .elmt filename) -- so a failure names exactly what's missing
        # rather than just "counts didn't match".
        found = set()
        for diagram in canon.diagrams:
            for el in diagram["elements"].values():
                type_path = el.get("type") or ""
                for key, (_display, path_fragment) in ELEMENTS.items():
                    if path_fragment in type_path:
                        found.add(key)

        missing = sorted(set(ELEMENTS) - found)

        # Every placed element must sit inside the folio's drawable area.
        # Dropping just outside the frame still produces a valid saved
        # project with the right element count, so without this check the
        # scenario passes while the drawing is visibly wrong -- it was
        # caught by eye, not by the assertions, which is exactly the gap
        # this closes.
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

        passed = not missing and not outside

        if counts.get("elements", 0) == 0:
            detail = (
                "saved project contains no elements at all. Most likely the "
                "collection filter matched nothing: search terms must be the "
                "element's DISPLAY NAME in the current UI language, not its "
                ".elmt filename (see the ELEMENTS comment in this file). "
                f"attempted={attempted}"
            )
        else:
            detail = (
                f"attempted={attempted} found_in_saved_file={sorted(found)} "
                f"missing={missing}"
            )

        return ScenarioResult(
            name=name, passed=passed, detail=detail,
            saved_project=out_path, counts=counts,
        )

    except ScenarioError as e:
        return ScenarioResult(name=name, passed=False, detail=str(e))
