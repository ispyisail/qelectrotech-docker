#!/usr/bin/env python3
"""
QElectroTech GUI fuzzer — main orchestrator.

Starts QET as a subprocess, drives it via xdotool on the virtual display,
runs a weighted-random action loop for the configured duration, and logs
all crashes.

Usage (inside the container, after run.sh starts Xvfb):
    python3 fuzzer.py [--hours N] [--speed {slow,normal,fast}] [--seed S]
"""
import argparse
import logging
import os
import random
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from monitor import ProcessMonitor
from actions.base import XDo, QETLayout
import actions.project_ops as proj
import actions.diagram_ops as diag
import actions.element_ops as elem
import actions.selection_ops as sel
import actions.wire_ops as wire
import actions.editor_ops as editor

# ------------------------------------------------------------------ #
# Configuration defaults                                               #
# ------------------------------------------------------------------ #
DISPLAY = os.environ.get("DISPLAY", ":99")
QET_BINARY = os.environ.get("QET_BINARY", "/usr/local/bin/qelectrotech")
LOG_DIR = os.environ.get("FUZZER_LOG_DIR", "/fuzzer/logs")
CRASH_LOG = os.path.join(LOG_DIR, "crashes.jsonl")
SCREENSHOT_DIR = os.path.join(LOG_DIR, "screenshots")
ACTION_LOG = os.path.join(LOG_DIR, "actions.log")

# Speed modes: (min_delay, max_delay) between actions in seconds
SPEED_PROFILES = {
    "slow":   (0.8, 2.5),
    "normal": (0.2, 1.0),
    "fast":   (0.05, 0.3),
}

# Weighted action table.
# Format: (weight, callable, needs_positions)
#   needs_positions=True  → only schedule if we have ≥1 tracked element
#   needs_positions=2     → only schedule if we have ≥2 tracked elements
_ACTIONS_REGISTRY = [
    # ---- high-frequency everyday actions ----
    (20, "add_element",        False),
    (15, "draw_wire",          2),
    (10, "click_canvas_empty", False),
    (8,  "undo",               False),
    (6,  "redo",               False),
    (8,  "select_all",         False),
    (5,  "copy_paste",         True),
    (5,  "rubber_band_select", False),
    (5,  "move_element",       True),
    (4,  "rotate_element",     True),
    (4,  "zoom_in",            False),
    (3,  "zoom_out",           False),
    (3,  "zoom_fit",           False),
    (3,  "scroll_canvas",      False),
    # ---- medium frequency ----
    (4,  "save_project",       False),
    (3,  "next_diagram_tab",   False),
    (2,  "add_diagram_page",   False),
    (2,  "diagram_properties", False),
    (2,  "edit_element_props", True),
    (2,  "right_click_canvas", False),
    (2,  "draw_wire_random",   False),
    (2,  "delete_wire",        False),
    (2,  "right_click_element",True),
    (2,  "delete_element",     True),
    (2,  "pan_canvas",         False),
    (2,  "move_selection_arr", False),
    (2,  "select_cut",         True),
    # ---- low frequency heavy operations ----
    (1,  "fuzz_editor",        False),
    (1,  "export_pdf",         False),
    (1,  "print_diagram",      False),
    (1,  "delete_all",         False),
    (1,  "expand_panel",       False),
    (1,  "open_prefs",         False),
    (1,  "new_project",        False),
]

_WEIGHTS = [r[0] for r in _ACTIONS_REGISTRY]
_NAMES   = [r[1] for r in _ACTIONS_REGISTRY]
_NEEDS   = [r[2] for r in _ACTIONS_REGISTRY]


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s %(message)s"
    handlers = [
        logging.FileHandler(ACTION_LOG),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def start_qet(env: dict) -> subprocess.Popen:
    log = logging.getLogger(__name__)
    log.info("Starting QET: %s", QET_BINARY)
    return subprocess.Popen(
        [QET_BINARY],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_action(name: str, xdo: XDo, layout: QETLayout, positions: list) -> list:
    """
    Execute the named action.  Returns the (possibly updated) positions list.
    """
    log = logging.getLogger(__name__)
    try:
        if name == "add_element":
            result = elem.drag_element_to_canvas(xdo, layout)
            if result:
                positions.append(result)

        elif name == "draw_wire":
            wire.draw_wire(xdo, layout, positions)

        elif name == "draw_wire_random":
            wire.draw_wire_random(xdo, layout)

        elif name == "delete_wire":
            wire.delete_wire(xdo, layout)

        elif name == "click_canvas_empty":
            diag.click_canvas_empty(xdo, layout)

        elif name == "undo":
            sel.undo(xdo, layout)

        elif name == "redo":
            sel.redo(xdo, layout)

        elif name == "select_all":
            sel.select_all(xdo, layout)

        elif name == "copy_paste":
            sel.select_copy_paste(xdo, layout)

        elif name == "rubber_band_select":
            sel.rubber_band_select(xdo, layout)

        elif name == "move_element":
            elem.move_element(xdo, layout, positions)

        elif name == "rotate_element":
            elem.rotate_element(xdo, layout, positions)

        elif name == "zoom_in":
            diag.zoom_in(xdo, layout)

        elif name == "zoom_out":
            diag.zoom_out(xdo, layout)

        elif name == "zoom_fit":
            diag.zoom_fit(xdo, layout)

        elif name == "scroll_canvas":
            diag.scroll_canvas(xdo, layout)

        elif name == "pan_canvas":
            diag.pan_canvas(xdo, layout)

        elif name == "save_project":
            proj.save_project(xdo, layout)

        elif name == "next_diagram_tab":
            diag.next_diagram_tab(xdo, layout)

        elif name == "add_diagram_page":
            diag.add_diagram_page(xdo, layout)

        elif name == "diagram_properties":
            diag.diagram_properties(xdo, layout)

        elif name == "edit_element_props":
            elem.edit_element_properties(xdo, layout, positions)

        elif name == "right_click_canvas":
            diag.right_click_canvas(xdo, layout)

        elif name == "right_click_element":
            elem.right_click_element(xdo, layout, positions)

        elif name == "delete_element":
            if positions:
                pos = random.choice(positions)
                positions = [p for p in positions if p != pos]
                elem.delete_element(xdo, layout, [pos])

        elif name == "move_selection_arr":
            sel.move_selection_arrow(xdo, layout)

        elif name == "select_cut":
            sel.cut_selection(xdo, layout)
            positions = []     # can't track cut items

        elif name == "fuzz_editor":
            editor.fuzz_element_editor(xdo, layout, positions)

        elif name == "export_pdf":
            proj.export_pdf(xdo, layout)

        elif name == "print_diagram":
            proj.print_diagram(xdo, layout)

        elif name == "delete_all":
            sel.select_all_then_delete(xdo, layout)
            positions = []

        elif name == "expand_panel":
            elem.expand_panel_tree(xdo, layout)

        elif name == "open_prefs":
            proj.open_preferences(xdo, layout)

        elif name == "new_project":
            proj.new_project(xdo, layout)
            positions = []

        else:
            log.warning("unknown action: %s", name)

    except Exception as exc:
        log.exception("action %s raised exception: %s", name, exc)

    return positions


class FuzzerSession:
    def __init__(self, duration_s: float, speed: str, seed: int | None):
        self.duration_s = duration_s
        self.speed = speed
        self.seed = seed
        self.log = logging.getLogger(self.__class__.__name__)

    def _pick_action(self, positions: list) -> tuple[str, int]:
        """Return (action_name, index) chosen by weighted random, filtered by state."""
        while True:
            idx = random.choices(range(len(_NAMES)), weights=_WEIGHTS, k=1)[0]
            need = _NEEDS[idx]
            if need is False:
                return _NAMES[idx], idx
            if need is True and len(positions) >= 1:
                return _NAMES[idx], idx
            if need == 2 and len(positions) >= 2:
                return _NAMES[idx], idx
            # not applicable yet — try another

    def run_one_session(self):
        """Start QET, fuzz it until crash or user interrupt, return (ok, crash_count)."""
        env = dict(os.environ, DISPLAY=DISPLAY)
        proc = start_qet(env)
        monitor = ProcessMonitor(proc, CRASH_LOG, SCREENSHOT_DIR, DISPLAY)

        xdo = XDo(DISPLAY)
        if not xdo.find_window(timeout=25):
            self.log.error("QET window never appeared — process may have crashed at startup")
            monitor.check("startup")
            monitor.kill()
            return False, 1

        geo = xdo.get_geometry()
        if not geo:
            self.log.error("Could not get window geometry")
            monitor.kill()
            return False, 1

        layout = QETLayout(geo["x"], geo["y"], geo["w"], geo["h"])
        self.log.info("Window geometry: %s", geo)

        # Start with a new project
        proj.new_project(xdo, layout)
        positions: list = []
        delay_range = SPEED_PROFILES[self.speed]
        action_count = 0

        deadline = time.time() + self.duration_s

        while time.time() < deadline:
            if not monitor.is_alive():
                self.log.warning("QET process died")
                monitor.check("idle")
                return False, monitor._crash_count

            # Re-read geometry occasionally (window may have been resized)
            if action_count % 50 == 0:
                geo = xdo.get_geometry()
                if geo:
                    layout = QETLayout(geo["x"], geo["y"], geo["w"], geo["h"])

            action_name, _ = self._pick_action(positions)
            self.log.info("[%d] action: %s  elements_tracked=%d",
                          action_count, action_name, len(positions))

            positions = run_action(action_name, xdo, layout, positions)
            monitor.check(action_name)

            action_count += 1
            delay = random.uniform(*delay_range)
            time.sleep(delay)

        self.log.info("Session complete after %d actions", action_count)
        monitor.kill()
        return True, monitor._crash_count

    def run(self):
        if self.seed is not None:
            random.seed(self.seed)

        total_crashes = 0
        session = 0
        end_time = time.time() + self.duration_s

        while time.time() < end_time:
            session += 1
            remaining = end_time - time.time()
            self.log.info("=== Session %d  (%.0f s remaining) ===", session, remaining)
            _ok, crashes = self.run_one_session()
            total_crashes += crashes
            self.log.info("Session %d ended.  crashes_so_far=%d", session, total_crashes)

            # Brief pause between sessions
            if time.time() < end_time:
                time.sleep(3)

        self.log.info("Fuzzing complete.  sessions=%d  total_crashes=%d", session, total_crashes)
        self.log.info("Crash log: %s", CRASH_LOG)
        self.log.info("To analyse: python3 analyze.py %s", CRASH_LOG)


def main():
    ap = argparse.ArgumentParser(description="QElectroTech GUI Fuzzer")
    ap.add_argument("--hours", type=float, default=1.0,
                    help="Total fuzzing duration in hours (default: 1)")
    ap.add_argument("--speed", choices=list(SPEED_PROFILES), default="normal",
                    help="Action speed (default: normal)")
    ap.add_argument("--seed", type=int, default=None,
                    help="Random seed for reproducibility")
    args = ap.parse_args()

    setup_logging()
    log = logging.getLogger("main")
    log.info("QET Fuzzer starting: hours=%.1f  speed=%s  seed=%s",
             args.hours, args.speed, args.seed)

    fs = FuzzerSession(
        duration_s=args.hours * 3600,
        speed=args.speed,
        seed=args.seed,
    )

    def _sigint(sig, frame):
        log.info("Interrupted — stopping fuzzer")
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint)
    signal.signal(signal.SIGTERM, _sigint)

    fs.run()


if __name__ == "__main__":
    main()
