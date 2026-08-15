"""
Shared harness for scenarios: launch QET, drive it, save, verify.

Reuses fuzzer.actions.base.XDo/QETLayout for GUI driving and
simulator.canon for verification -- see the package docstring in
__init__.py for why.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "fuzzer"))
sys.path.insert(0, str(_REPO_ROOT))

from actions.base import XDo, QETLayout          # noqa: E402
from scenarios import treefind, termfind         # noqa: E402
from simulator import canon as _canon            # noqa: E402

log = logging.getLogger(__name__)


class ScenarioError(RuntimeError):
    """Raised when a scenario cannot proceed or its assertions fail."""


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    detail: str = ""
    saved_project: Path | None = None
    counts: dict = field(default_factory=dict)


class ScenarioContext:
    """
    One QET process + one XDo/QETLayout, wired up with the reliability
    fixes, for the duration of a single scenario.

    Usage:
        with ScenarioContext("simple_motor_starter") as ctx:
            ctx.new_project()
            ctx.place_element("moteur_tri", 400, 300)
            ...
            ctx.save_as("/tmp/out.qet")
            canon = ctx.verify()
    """

    def __init__(
        self,
        name: str,
        binary: str | None = None,
        display: str | None = None,
        common_elements_dir: str | None = None,
        config_dir: str | None = None,
        data_dir: str | None = None,
        window_timeout: float = 25.0,
    ):
        self.name = name
        self.binary = binary or os.environ.get(
            "QET_BINARY", "/usr/local/bin/qelectrotech"
        )
        self.display = display or os.environ.get("DISPLAY", ":99")
        # No env-var default here on purpose: the megatest-derived image's
        # compiled-in default already points at the installed collection
        # (verified working interactively earlier) and passing
        # --common-elements-dir explicitly at that same path was observed
        # to leave the Collections panel empty instead -- something about
        # how QET resolves that flag doesn't match just re-stating its own
        # default. Only set this if a scenario explicitly needs a
        # *different* collection than the one built into the image.
        self.common_elements_dir = common_elements_dir
        self.config_dir = config_dir
        self.data_dir = data_dir
        self.window_timeout = window_timeout

        self.proc: subprocess.Popen | None = None
        self.xdo: XDo | None = None
        self.layout: QETLayout | None = None

        # Debug screenshots, one per checkpoint, so a failed run can be
        # diagnosed after the fact instead of only by watching it live.
        self.debug_dir = Path(os.environ.get("SCENARIO_DEBUG_DIR", "/home/qet/scenario-debug"))
        self._step = 0

    # ------------------------------------------------------------------ #
    def __enter__(self) -> "ScenarioContext":
        self._launch()
        self._dismiss_startup_dialogs()
        # The Collections panel populates asynchronously after the main
        # window appears (~0.4s for the stock collection per QET's own
        # startup log, more with a large custom/company collection) --
        # empirically, typing into the filter box before this finishes
        # accepts the text but the tree never shows results, which looks
        # identical to "wrong coordinates" from a screenshot. Give it a
        # fixed settle window rather than guessing exactly when it's done.
        time.sleep(8.0)
        self.checkpoint("startup")
        return self

    def __exit__(self, exc_type, exc, tb):
        self._quit()
        return False

    # ------------------------------------------------------------------ #
    def _launch(self):
        env = dict(os.environ)
        env["DISPLAY"] = self.display
        # Click-doubling fix -- see fuzzer/actions/base.py's docstring and
        # fuzzer.py's self-test for the full diagnosis. Every mouse action
        # in a scenario needs this or it silently double-fires.
        env["QT_XCB_NO_XI2"] = "1"

        args = [self.binary]
        if self.common_elements_dir:
            args += ["--common-elements-dir", self.common_elements_dir]
        if self.config_dir:
            args += ["--config-dir", self.config_dir]
        if self.data_dir:
            args += ["--data-dir", self.data_dir]

        log.info("launching: %s", " ".join(args))
        self.proc = subprocess.Popen(
            args, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )

        self.xdo = XDo(self.display)
        found = self.xdo.find_window(timeout=self.window_timeout, pid=self.proc.pid)
        if not found:
            self._quit()
            raise ScenarioError(
                f"QET window never appeared (pid={self.proc.pid}, "
                f"display={self.display})"
            )

        # Cross-monitor placement, so a run stays watchable rather than
        # fighting the CLI terminal for the screen. Verified-and-retried
        # internally (see _try_move_to_monitor) rather than trusted
        # blindly -- self.layout below is always built from a geometry
        # read taken AFTER this call, so even a failed/partial move can't
        # poison the click coordinates the rest of the run depends on; it
        # just means the window stayed wherever it actually ended up.
        self._place_away_from_terminal()

        geo = self.xdo.get_geometry()
        if not geo:
            raise ScenarioError("could not read QET window geometry")
        self.layout = QETLayout(geo["x"], geo["y"], geo["w"], geo["h"])

    def _monitors(self) -> list[tuple[int, int, int, int]]:
        """[(x, y, w, h), ...] from `xrandr --listmonitors`."""
        try:
            out = subprocess.run(
                ["xrandr", "--listmonitors"],
                env={**os.environ, "DISPLAY": self.display},
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            return []
        mons = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 3:
                continue
            geo = parts[2]  # e.g. 1920/508x1080/286+1920+0
            m = re.match(r"(\d+)/\d+x(\d+)/\d+\+(\d+)\+(\d+)", geo)
            if m:
                w, h, x, y = map(int, m.groups())
                mons.append((x, y, w, h))
        return mons

    # WM_CLASS (class part) names of terminal emulators that can plausibly
    # host the Claude CLI prompt. A whitelist rather than a browser
    # blacklist: browsers proliferate, terminal emulators are a small set.
    # Keep in sync with scripts/guiauto.sh's term_monitor().
    _TERMINAL_WM_CLASSES = {
        "ptyxis", "xfce4-terminal", "xterm", "uxterm", "gnome-terminal",
        "konsole", "kitty", "alacritty", "wezterm", "tilix", "rxvt", "urxvt",
        "lxterminal", "qterminal", "foot", "st", "terminator", "tabby",
        "x-terminal-emulator",
    }

    def _xprop_wm_class(self, wid: str) -> str:
        """Class part of a window's WM_CLASS (lowercased), '' if unknown."""
        try:
            out = subprocess.run(
                ["xprop", "-id", wid, "WM_CLASS"],
                env={**os.environ, "DISPLAY": self.display},
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            return ""
        quoted = re.findall(r'"([^"]*)"', out)
        return quoted[-1].lower() if quoted else ""

    def _window_viewable(self, wid: str) -> bool:
        try:
            out = subprocess.run(
                ["xwininfo", "-id", wid],
                env={**os.environ, "DISPLAY": self.display},
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            return False
        return "IsViewable" in out

    def _terminal_monitor(self, mons: list[tuple[int, int, int, int]]) -> int:
        """
        Index into `mons` of the monitor showing the Claude CLI terminal,
        so the scenario window can be placed on the OTHER one and stay
        visible/watchable rather than fighting the terminal for the screen.

        DISAMBIGUATION (real bug, fixed 2026-08-15): `xdotool search
        --name claude` is a substring match across ALL clients, so it also
        returns browser tabs whose page title contains "Claude Code"
        (observed: an unviewable Google Chrome tab on the wrong monitor).
        Taking the first id blindly parked QET on the terminal's OWN
        monitor -- exactly the opposite of the intent. Candidates are now
        ranked: (1) viewable + terminal-emulator WM_CLASS, (2) the focused
        window if it is one of the matches, (3) any viewable match,
        (4) the focused window's monitor even without a name match,
        (5) monitor 0.
        """
        def monitor_of(geo) -> int:
            if not geo:
                return -1
            cx = geo["x"] + geo["w"] // 2
            cy = geo["y"] + geo["h"] // 2
            for i, (mx, my, mw, mh) in enumerate(mons):
                if mx <= cx < mx + mw and my <= cy < my + mh:
                    return i
            return -1

        try:
            ids = subprocess.run(
                ["xdotool", "search", "--name", "claude"],
                env={**os.environ, "DISPLAY": self.display},
                capture_output=True, text=True, timeout=5,
            ).stdout.split()
        except Exception:
            ids = []
        try:
            active = subprocess.run(
                ["xdotool", "getactivewindow"],
                env={**os.environ, "DISPLAY": self.display},
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except Exception:
            active = ""

        # Rank 1: a real terminal that matches the name.
        for wid in ids:
            if (self._window_viewable(wid)
                    and self._xprop_wm_class(wid) in self._TERMINAL_WM_CLASSES):
                m = monitor_of(self.xdo._geometry_of(wid) if self.xdo else None)
                if m >= 0:
                    return m
        # Rank 2: the focused window, if it is one of the matches.
        if active and active in ids:
            m = monitor_of(self.xdo._geometry_of(active) if self.xdo else None)
            if m >= 0:
                return m
        # Rank 3: any viewable match.
        for wid in ids:
            if self._window_viewable(wid):
                m = monitor_of(self.xdo._geometry_of(wid) if self.xdo else None)
                if m >= 0:
                    return m
        # Rank 4: the focused window, name match or not -- right after the
        # user ran this, focus is on the prompt that ran it.
        if active:
            m = monitor_of(self.xdo._geometry_of(active) if self.xdo else None)
            if m >= 0:
                return m
        return 0

    def _try_move_to_monitor(self, mx: int, my: int, mw: int, mh: int) -> bool:
        """One move+resize attempt, verified by re-reading real geometry
        afterward -- never trust the command's exit code alone, xdotool
        reports success whether or not the window manager actually
        complied. Returns whether the window ended up convincingly on
        that monitor at a reasonable size."""
        env = {**os.environ, "DISPLAY": self.display}
        # xfwm4 silently ignores windowmove/windowsize on a maximized
        # window -- QET launches maximized, and this must run BEFORE the
        # move, not after: it was missing here entirely until a real
        # tremie_folio1 run (14 elements, much slower to reach this point
        # than the earlier 3-4 element scenarios) exposed it. The earlier
        # scenarios only "worked" because their runs happened to reach
        # this code before QET's own auto-maximize won a startup race --
        # not because this was actually handled. wmstate is the same
        # minimal libX11 EWMH _NET_WM_STATE sender built for the host
        # session's guiauto.sh (xdotool 3.2016 in this image has no
        # `windowstate` subcommand, and wmctrl isn't installed).
        subprocess.run(
            ["wmstate", self.xdo.window_id, "remove", "maximized_vert", "maximized_horz"],
            env=env, timeout=5,
        )
        time.sleep(0.3)
        subprocess.run(
            ["xdotool", "windowmove", self.xdo.window_id, str(mx + 8), str(my + 38)],
            env=env, timeout=5,
        )
        subprocess.run(
            ["xdotool", "windowsize", self.xdo.window_id, str(mw - 16), str(mh - 46)],
            env=env, timeout=5,
        )
        time.sleep(0.6)

        got = self.xdo._geometry_of(self.xdo.window_id)
        if not got:
            return False
        # Sanity thresholds, not exact-pixel matching: WM decoration and
        # panel reservations vary, so demand "clearly on this monitor and
        # not absurdly small" rather than an exact fit. The 22x22 phantom
        # window bug earlier this session is exactly the failure mode
        # "not absurdly small" exists to catch.
        cx, cy = got["x"] + got["w"] // 2, got["y"] + got["h"] // 2
        on_target_monitor = (mx <= cx < mx + mw) and (my <= cy < my + mh)
        reasonable_size = got["w"] >= mw * 0.5 and got["h"] >= mh * 0.5
        return on_target_monitor and reasonable_size

    def _place_away_from_terminal(self):
        """
        Move+resize the QET window onto the monitor the terminal isn't on.

        Verified, not assumed: an earlier version trusted the move
        unconditionally, which sometimes left the window small and on the
        wrong monitor while claiming success. Every attempt here is
        checked by re-reading real geometry afterward. self.layout is
        always built from a fresh read taken after this returns (success
        or not), so a failed move degrades to "window stayed where it
        spawned" rather than "coordinates computed from a lie".
        """
        mons = self._monitors()
        if len(mons) < 2:
            log.info("single monitor detected, nothing to move away from")
            return
        term_mon = self._terminal_monitor(mons)
        target = 1 if term_mon == 0 else 0
        mx, my, mw, mh = mons[target]

        for attempt in (1, 2):
            try:
                if self._try_move_to_monitor(mx, my, mw, mh):
                    log.info(
                        "placed QET window on monitor %d (terminal is on %d), attempt %d",
                        target, term_mon, attempt,
                    )
                    return
                log.warning(
                    "move to monitor %d did not verify on attempt %d, %s",
                    target, attempt, "retrying" if attempt == 1 else "giving up",
                )
            except Exception as e:
                log.warning("move to monitor %d raised on attempt %d: %s", target, attempt, e)
            time.sleep(1.0)

        log.warning(
            "could not confirm window on monitor %d after 2 attempts -- "
            "continuing with wherever it actually is", target,
        )

    def checkpoint(self, label: str):
        """
        Save a full-screen screenshot tagged with a step number and label.
        Cheap, always-on flight recorder: when a scenario fails, the debug
        dir shows exactly which step it got to and what the screen looked
        like, instead of needing to reproduce the failure live.
        """
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self._step += 1
        path = self.debug_dir / f"{self._step:02d}_{label}.png"
        try:
            subprocess.run(
                ["scrot", "-o", str(path)],
                env={**os.environ, "DISPLAY": self.display},
                timeout=5, capture_output=True,
            )
            log.info("checkpoint[%d] %s -> %s", self._step, label, path)
        except Exception as e:
            log.warning("checkpoint screenshot failed: %s", e)

    def _dismiss_startup_dialogs(self, attempts: int = 4):
        """
        A previous run's crash report, a stale "reopen last project"
        failure, etc. can appear before the main window is usable.
        Escape, not a button click: some dialogs (observed: the crash
        report dialog) do not respond to a synthetic click on their own
        Close button even at verified-correct coordinates, but always
        respond to Escape. Keyboard over mouse here isn't a style
        preference, it's the only thing confirmed to work.
        """
        for _ in range(attempts):
            time.sleep(0.3)
            self.xdo.key("Escape")

    def _quit(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None

    # ------------------------------------------------------------------ #
    # High-level actions, all keyboard-first per the project's own finding
    # that keyboard input is reliable while mouse clicks need the XI2
    # workaround to not double-fire. Mouse is used only where the action is
    # inherently spatial (placing/dragging something to a canvas position).
    # ------------------------------------------------------------------ #

    def new_project(self):
        self.xdo.key("ctrl+n")
        time.sleep(1.0)
        self.checkpoint("new_project")

    def find_element_in_collection(self, search_term: str, timeout: float = 2.0) -> tuple[int, int] | None:
        """
        Type into the Collections panel's filter box and return the screen
        position of the first filtered result, or None if nothing matched.

        Uses the filter box rather than expanding tree categories by
        clicking: category structure changes over time (see #672 in this
        project's own history -- prefix/category lookups already broke
        once when the collection was reorganised), but the filter box's
        position and behaviour is stable UI, and it collapses "find this
        element" from a multi-level tree navigation into one type + one
        click.
        """
        # Filter box sits in the top-right "Collections" dock, near the
        # right edge and just below the menu bar.
        fx = self.layout.wx + self.layout.ww - 180
        fy = self.layout.wy + 104
        self.xdo.click(fx, fy)
        self.xdo.key("ctrl+a")
        self.xdo.type_text(search_term)
        time.sleep(timeout)
        self.checkpoint(f"filter_{search_term}")

        # The first match is NOT at a fixed offset below the filter box:
        # the tree first renders however many nested category rows lead to
        # it, and that depth varies per search term. Locate the first
        # actual element row from the pixels instead. See treefind.py.
        region = (
            self.layout.wx + int(self.layout.ww * 0.778),   # left edge of the dock
            self.layout.wy + 134,                           # below the Collections tabs
            self.layout.wx + self.layout.ww - 5,
            self.layout.wy + 544,                           # above "Selection properties"
        )
        pos = treefind.locate_first_element(self.display, region)
        if pos is None:
            log.warning(
                "collection filter %r matched no element rows -- check the "
                "search term is the element's DISPLAY NAME in the current UI "
                "language, not its .elmt filename", search_term,
            )
        return pos

    def place_element(self, search_term: str, canvas_x: int, canvas_y: int) -> bool:
        """
        Find `search_term` in the Collections filter, double-click it
        (inserts at a default position per QET's double-click-inserts
        setting), then drag it to (canvas_x, canvas_y).

        `search_term` must be the element's DISPLAY NAME in the running
        UI language, not its .elmt filename -- QET's filter matches the
        text the tree shows. See the ELEMENTS comment in
        simple_motor_starter.py for why that distinction is load-bearing.

        Returns True if the interaction was performed, which is NOT the
        same as "an element was inserted": nothing observable from
        xdotool can confirm insertion. Verify with canon on the saved
        file instead of trusting this return value.
        """
        pos = self.find_element_in_collection(search_term)
        if pos is None:
            return False

        # Drag-and-drop from the tree onto the canvas -- NOT double-click.
        # Double-clicking a collection item opens it in the Element Editor
        # (and for a read-only stock element, pops a modal "Read only
        # edition" warning that then covers the tree and makes every
        # subsequent search silently find nothing). Drag-and-drop is the
        # interaction that actually inserts an element into the diagram.
        self.xdo.drag(pos[0], pos[1], canvas_x, canvas_y)
        time.sleep(0.6)

        # After the drop, QET stays in element-placing mode with the item
        # following the cursor, and a click is what commits it. It must be
        # a LEFT click: DiagramEventAddElement::mouseReleaseEvent calls
        # addElement() on Qt::LeftButton but removeItem()+deleteLater() on
        # Qt::RightButton -- i.e. right-click actively *deletes* the
        # element being placed. Using right-click here produced a project
        # whose embedded <collection> gained all three element definitions
        # (19 uuids) while <diagram> held nothing but <defaultconductor>.
        self.xdo.click(canvas_x, canvas_y)
        time.sleep(0.4)
        self.checkpoint(f"placed_{search_term}")

        # Belt and braces: if anything modal did appear, clear it now so it
        # cannot poison the next step the way the editor dialog did.
        self.xdo.key("Escape")
        time.sleep(0.2)
        return True

    def connect_terminals(self, p1: tuple[int, int], p2: tuple[int, int]):
        """
        Draw a wire between two terminal screen positions.

        Contradicts fuzzer/actions/wire_ops.py's docstring (click-click,
        no drag): that was tried here first -- with click points refined
        to land exactly on the terminal's red pixel mark via termfind --
        and still produced 0 saved conductors every time. What actually
        works, confirmed by direct user correction and then verified
        against the saved file's conductor count, is a real press-move-
        release drag identical to the one place_element already uses to
        drop an element from the Collections tree: mousedown on the first
        terminal, move, mouseup on the second.

        Callers are responsible for computing (p1, p2) as real terminal
        positions (element drop point + that element's local terminal
        offset -- see TERMINALS in simple_motor_starter.py, read directly
        from the .elmt XML rather than guessed). This method does not
        verify a wire was actually created; as with place_element, only
        the saved file's conductor count is ground truth.
        """
        # Refine both points against the real pixels before dragging:
        # computed (drop point + local XML offset) geometry lands close
        # but not exact -- see termfind.py's docstring for why exactness
        # matters here (missing the terminal at drag-start means no wire
        # is even begun). Falls back to the computed point if no red
        # terminal mark is found nearby.
        shot = self.debug_dir / "_termfind_scan.png"
        termfind.screenshot(self.display, shot)
        r1 = termfind.find_terminal_near(shot, *p1) or p1
        r2 = termfind.find_terminal_near(shot, *p2) or p2
        log.info(
            "connect_terminals: p1=%s -> %s, p2=%s -> %s", p1, r1, p2, r2
        )
        self.xdo.drag(*r1, *r2)
        time.sleep(0.3)
        self.checkpoint("after_wire")
        # Clear anything left in "drawing" state (e.g. a miss that left
        # the conductor tool armed) so it can't poison the next action.
        self.xdo.key("Escape")
        time.sleep(0.2)

    def save_as(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.xdo.key("ctrl+shift+s")
        time.sleep(1.0)
        self.checkpoint("save_dialog")
        self.xdo.type_text(path)
        time.sleep(0.3)
        self.xdo.key("Return")
        time.sleep(1.0)
        # Confirm any "replace existing file" prompt.
        self.xdo.key("Return")
        time.sleep(0.5)
        self.checkpoint("after_save")

    def verify(self, saved_path: str) -> _canon.Canon:
        p = Path(saved_path)
        if not p.exists():
            raise ScenarioError(f"expected saved project at {p}, nothing there")
        return _canon.canonicalize(p)
