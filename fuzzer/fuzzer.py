#!/usr/bin/env python3
"""
QElectroTech GUI fuzzer — main orchestrator.

Starts QET as a subprocess, drives it via xdotool on the virtual display,
runs a weighted-random action loop for the configured duration, and logs
all crashes.

Usage:
    python3 fuzzer.py [--hours N] [--speed {slow,normal,fast}] [--seed S]
    python3 fuzzer.py --self-test      # verify the fuzzer itself works
"""
import argparse
import logging
import os
import random
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

from monitor import ProcessMonitor, take_screenshot
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

SPEED_PROFILES = {
    "slow":   (0.8, 2.5),
    "normal": (0.2, 1.0),
    "fast":   (0.05, 0.3),
    "ultra":  (0.0, 0.02),
}

_ACTIONS_REGISTRY = [
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
    (1,  "fuzz_editor",        False),
    (1,  "export_pdf",         False),
    (1,  "print_diagram",      False),
    (1,  "delete_all",         False),
    (1,  "expand_panel",       False),
    (1,  "open_prefs",         False),
    (1,  "new_project",        False),
    # heavy-stress actions
    (3,  "flood_elements",     False),
    (3,  "flood_wires",        False),
    (2,  "paste_bomb",         False),
    (2,  "undo_storm",         False),
    # previously defined but unwired
    (2,  "right_click_wire",   False),
    (2,  "edit_wire_props",    False),
    (2,  "prev_diagram_tab",   False),
    (1,  "zoom_reset",         False),
    (1,  "delete_diagram_page",False),
    (1,  "save_as",            False),
    (1,  "close_project",      False),
]

_WEIGHTS = [r[0] for r in _ACTIONS_REGISTRY]
_NAMES   = [r[1] for r in _ACTIONS_REGISTRY]
_NEEDS   = [r[2] for r in _ACTIONS_REGISTRY]


# ------------------------------------------------------------------ #
# Periodic screenshot thread                                           #
# ------------------------------------------------------------------ #
class ScreenshotThread(threading.Thread):
    """Takes a screenshot every `interval` seconds into the screenshots dir."""

    def __init__(self, display: str, screenshot_dir: str, interval: int = 60):
        super().__init__(daemon=True, name="screenshot-thread")
        self.display = display
        self.screenshot_dir = screenshot_dir
        self.interval = interval
        self._stop = threading.Event()
        self._count = 0
        self.log = logging.getLogger("screenshot")

    def run(self):
        while not self._stop.wait(self.interval):
            self._count += 1
            ts = int(time.time())
            path = os.path.join(
                self.screenshot_dir,
                f"periodic_{ts:010d}_{self._count:04d}.png",
            )
            ok = take_screenshot(self.display, path)
            if ok:
                size = os.path.getsize(path)
                self.log.info("screenshot #%d saved: %s (%d KB)", self._count, path, size // 1024)
            else:
                self.log.warning("screenshot #%d failed", self._count)

    def stop(self):
        self._stop.set()


# ------------------------------------------------------------------ #
# Self-test                                                            #
# ------------------------------------------------------------------ #
def run_self_test() -> bool:
    """
    Verify that the fuzzer infrastructure actually works:
      1. xdotool is installed and runnable
      2. scrot can take a screenshot
      3. QET starts and its window appears on the virtual display
      4. The screenshot of the live window is non-trivial (>10 KB)
      5. xdotool can send a real click to QET's canvas
      6. Killing QET with SIGABRT is detected as a crash
      7. The crash is written to the crash log

    Prints PASS/FAIL for each check and exits 0 on all-pass, 1 on any failure.
    """
    log = logging.getLogger("self-test")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = ""):
        status = "PASS" if ok else "FAIL"
        results.append((name, ok, detail))
        marker = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        log.info("[%s] %s  %s", marker, name, detail)
        return ok

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # 1. xdotool available
    r = subprocess.run(["xdotool", "version"], capture_output=True, text=True)
    check("xdotool installed", r.returncode == 0, r.stdout.strip()[:60])

    # 2. scrot available
    r2 = subprocess.run(["scrot", "--version"], capture_output=True, text=True)
    check("scrot installed", r2.returncode in (0, 1),
          (r2.stdout or r2.stderr).strip()[:60])

    # 3. QET starts and window appears
    #
    # QT_XCB_NO_XI2=1: without this, Qt5's xcb plugin receives both XInput2
    # and core X11 pointer events for a single physical click, so every
    # xdo.click()/drag() is silently delivered TWICE (same millisecond).
    # A menu click opens then instantly closes; a canvas click can register
    # as an unintended double-click. Diagnosed empirically 2026-08-15 with a
    # minimal Qt widget counting press events (3 clicks -> 6 presses without
    # this, 3 -> 3 with it). Keyboard-driven actions were never affected,
    # which is why key()-heavy action files always looked reliable while
    # click()-heavy ones didn't.
    env = dict(os.environ, DISPLAY=DISPLAY, QT_XCB_NO_XI2="1")
    proc = subprocess.Popen(
        [QET_BINARY], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    xdo = XDo(DISPLAY)
    found = xdo.find_window(timeout=25, pid=proc.pid)
    check("QET window appears on virtual display", found,
          f"window_id={xdo.window_id}")

    if not found:
        proc.kill()
        _print_summary(results)
        return False

    # 4. Screenshot is non-trivial
    ss_path = os.path.join(SCREENSHOT_DIR, "selftest_window.png")
    took = take_screenshot(DISPLAY, ss_path)
    if took:
        size = os.path.getsize(ss_path)
        check(
            "screenshot captures real GUI content (>10 KB)",
            size > 10_000,
            f"{size // 1024} KB at {ss_path}",
        )
    else:
        check("screenshot taken", False, "scrot/import failed")

    # 5. xdotool click reaches QET canvas
    geo = xdo.get_geometry()
    if geo:
        layout = QETLayout(geo["x"], geo["y"], geo["w"], geo["h"])
        cx, cy = layout.canvas_cx, layout.canvas_cy
        xdo.click(cx, cy)
        time.sleep(0.3)
        # Take a second screenshot — if xdotool works, mouse cursor should have moved
        ss2 = os.path.join(SCREENSHOT_DIR, "selftest_after_click.png")
        take_screenshot(DISPLAY, ss2)
        check(
            "xdotool click sent to canvas",
            True,
            f"clicked ({cx}, {cy}) — see {ss2}",
        )
    else:
        check("xdotool click sent to canvas", False, "could not get window geometry")

    # 6. Crash detection: kill QET with SIGABRT, monitor must notice
    monitor = ProcessMonitor(proc, CRASH_LOG, SCREENSHOT_DIR, DISPLAY)
    log.info("Sending SIGABRT to QET (pid %d) to simulate a crash...", proc.pid)
    try:
        proc.send_signal(signal.SIGABRT)
    except ProcessLookupError:
        pass
    time.sleep(1.5)
    detected = monitor.check("self-test-deliberate-crash")
    check("crash detection triggers on process death", detected,
          "monitor.check() returned True")

    # 7. Crash log written to disk
    if os.path.exists(CRASH_LOG):
        size = os.path.getsize(CRASH_LOG)
        check("crash event written to crashes.jsonl", size > 0,
              f"{size} bytes at {CRASH_LOG}")
    else:
        check("crash event written to crashes.jsonl", False,
              "file not created")

    _print_summary(results)
    return all(ok for _, ok, _ in results)


def _print_summary(results: list[tuple[str, bool, str]]):
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print("\n" + "=" * 60)
    print(f"SELF-TEST SUMMARY: {passed} passed, {failed} failed")
    if failed:
        print("FAILED checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  ✗ {name}: {detail}")
    else:
        print("All checks passed — fuzzer infrastructure is working.")
    print("=" * 60)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #
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
            positions = []
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
        elif name == "flood_elements":
            new_pos = elem.flood_elements(xdo, layout)
            if new_pos:
                positions.extend(new_pos)
        elif name == "flood_wires":
            wire.flood_wires(xdo, layout)
        elif name == "paste_bomb":
            sel.paste_bomb(xdo, layout)
        elif name == "undo_storm":
            sel.undo_storm(xdo, layout)
        elif name == "right_click_wire":
            wire.right_click_wire(xdo, layout)
        elif name == "edit_wire_props":
            wire.edit_wire_properties(xdo, layout)
        elif name == "prev_diagram_tab":
            diag.prev_diagram_tab(xdo, layout)
        elif name == "zoom_reset":
            diag.zoom_reset(xdo, layout)
        elif name == "delete_diagram_page":
            diag.delete_diagram_page(xdo, layout)
        elif name == "save_as":
            proj.save_as(xdo, layout)
        elif name == "close_project":
            proj.close_project(xdo, layout)
            positions = []
        else:
            log.warning("unknown action: %s", name)
    except Exception as exc:
        log.exception("action %s raised exception: %s", name, exc)
    return positions


# ------------------------------------------------------------------ #
# Fuzzer session                                                        #
# ------------------------------------------------------------------ #
class FuzzerSession:
    def __init__(self, duration_s: float, speed: str, seed: int | None,
                 screenshot_interval: int = 60):
        self.duration_s = duration_s
        self.speed = speed
        self.seed = seed
        self.screenshot_interval = screenshot_interval
        self.log = logging.getLogger(self.__class__.__name__)

    def _pick_action(self, positions: list) -> tuple[str, int]:
        while True:
            idx = random.choices(range(len(_NAMES)), weights=_WEIGHTS, k=1)[0]
            need = _NEEDS[idx]
            if need is False:
                return _NAMES[idx], idx
            if need is True and len(positions) >= 1:
                return _NAMES[idx], idx
            if need == 2 and len(positions) >= 2:
                return _NAMES[idx], idx

    def run_one_session(self):
        env = dict(os.environ, DISPLAY=DISPLAY, QT_XCB_NO_XI2="1")  # see self-test note above: fixes click-doubling
        proc = start_qet(env)
        monitor = ProcessMonitor(proc, CRASH_LOG, SCREENSHOT_DIR, DISPLAY)

        xdo = XDo(DISPLAY)
        if not xdo.find_window(timeout=25, pid=proc.pid):
            self.log.error("QET window never appeared")
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

        # Start periodic screenshot thread
        ss_thread = ScreenshotThread(DISPLAY, SCREENSHOT_DIR, self.screenshot_interval)
        ss_thread.start()
        self.log.info("Periodic screenshots every %ds → %s", self.screenshot_interval, SCREENSHOT_DIR)

        proj.new_project(xdo, layout)
        positions: list = []
        delay_range = SPEED_PROFILES[self.speed]
        action_count = 0
        deadline = time.time() + self.duration_s

        try:
            while time.time() < deadline:
                if not monitor.is_alive():
                    self.log.warning("QET process died")
                    monitor.check("idle")
                    return False, monitor._crash_count

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
                time.sleep(random.uniform(*delay_range))
        finally:
            ss_thread.stop()

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
            if time.time() < end_time:
                time.sleep(3)

        self.log.info("Fuzzing complete.  sessions=%d  total_crashes=%d", session, total_crashes)
        self.log.info("Crash log: %s", CRASH_LOG)
        self.log.info("To analyse: python3 analyze.py %s", CRASH_LOG)


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #
def main():
    ap = argparse.ArgumentParser(description="QElectroTech GUI Fuzzer")
    ap.add_argument("--hours", type=float, default=1.0)
    ap.add_argument("--speed", choices=list(SPEED_PROFILES), default="normal")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--screenshot-interval", type=int, default=60,
                    help="Seconds between periodic screenshots (default 60)")
    ap.add_argument("--self-test", action="store_true",
                    help="Verify fuzzer infrastructure works, then exit")
    args = ap.parse_args()

    setup_logging()
    log = logging.getLogger("main")

    if args.self_test:
        log.info("Running self-test...")
        ok = run_self_test()
        sys.exit(0 if ok else 1)

    log.info("QET Fuzzer starting: hours=%.1f  speed=%s  seed=%s  screenshot_interval=%ds",
             args.hours, args.speed, args.seed, args.screenshot_interval)

    fs = FuzzerSession(
        duration_s=args.hours * 3600,
        speed=args.speed,
        seed=args.seed,
        screenshot_interval=args.screenshot_interval,
    )

    def _sigint(sig, frame):
        log.info("Interrupted — stopping fuzzer")
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint)
    signal.signal(signal.SIGTERM, _sigint)

    fs.run()


if __name__ == "__main__":
    main()
