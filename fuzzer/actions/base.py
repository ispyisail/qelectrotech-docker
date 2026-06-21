"""
xdotool wrapper and window-layout helpers for QElectroTech fuzzing.
"""
import logging
import os
import random
import subprocess
import time

log = logging.getLogger(__name__)


class XDo:
    """Thin, robust wrapper around xdotool."""

    def __init__(self, display: str = ":99"):
        self.display = display
        self.window_id: str | None = None

    # ------------------------------------------------------------------ #
    # internal                                                              #
    # ------------------------------------------------------------------ #
    def _env(self) -> dict:
        e = dict(os.environ)
        e["DISPLAY"] = self.display
        return e

    def _run(self, cmd: list, timeout: float = 5.0):
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._env(),
            )
        except subprocess.TimeoutExpired:
            log.warning("xdotool timeout: %s", " ".join(cmd))
            return None
        except FileNotFoundError:
            log.error("xdotool not found")
            return None

    # ------------------------------------------------------------------ #
    # window management                                                     #
    # ------------------------------------------------------------------ #
    def find_window(self, name: str = "QElectroTech", timeout: float = 20.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self._run(["xdotool", "search", "--name", name])
            if r and r.stdout.strip():
                ids = [x for x in r.stdout.strip().split("\n") if x]
                if ids:
                    self.window_id = ids[-1]
                    log.info("QET window found: %s", self.window_id)
                    # Give it a moment to finish drawing
                    time.sleep(1.0)
                    return True
            time.sleep(0.5)
        return False

    def window_alive(self) -> bool:
        if not self.window_id:
            return False
        r = self._run(["xdotool", "getwindowgeometry", self.window_id])
        return r is not None and r.returncode == 0

    def get_geometry(self) -> dict | None:
        if not self.window_id:
            return None
        r = self._run(["xdotool", "getwindowgeometry", "--shell", self.window_id])
        if not r or r.returncode != 0:
            return None
        geo: dict = {}
        for line in r.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                try:
                    geo[k.strip()] = int(v.strip())
                except ValueError:
                    pass
        if "X" in geo:
            return {
                "x": geo["X"],
                "y": geo["Y"],
                "w": geo["WIDTH"],
                "h": geo["HEIGHT"],
            }
        return None

    def focus(self):
        if self.window_id:
            self._run(["xdotool", "windowfocus", "--sync", self.window_id])
            time.sleep(0.08)

    def raise_window(self):
        if self.window_id:
            self._run(["xdotool", "windowraise", self.window_id])
            time.sleep(0.05)

    # ------------------------------------------------------------------ #
    # input                                                                 #
    # ------------------------------------------------------------------ #
    def move(self, x: int, y: int):
        self._run(["xdotool", "mousemove", str(x), str(y)])
        time.sleep(0.03)

    def click(self, x: int, y: int, button: int = 1, delay: float = 0.05):
        self.move(x, y)
        self._run(["xdotool", "click", str(button)])
        time.sleep(delay)

    def double_click(self, x: int, y: int):
        self.move(x, y)
        self._run(["xdotool", "click", "--repeat", "2", "--delay", "120", "1"])
        time.sleep(0.12)

    def right_click(self, x: int, y: int):
        self.click(x, y, button=3)

    def drag(self, x1: int, y1: int, x2: int, y2: int, steps: int = 20):
        self.move(x1, y1)
        time.sleep(0.08)
        self._run(["xdotool", "mousedown", "1"])
        time.sleep(0.12)
        for i in range(1, steps + 1):
            px = int(x1 + (x2 - x1) * i / steps)
            py = int(y1 + (y2 - y1) * i / steps)
            self._run(["xdotool", "mousemove", str(px), str(py)])
            time.sleep(0.02)
        time.sleep(0.06)
        self._run(["xdotool", "mouseup", "1"])
        time.sleep(0.12)

    def key(self, combo: str):
        self.focus()
        self._run(["xdotool", "key", combo])
        time.sleep(0.08)

    def keys(self, *combos: str):
        for c in combos:
            self.key(c)

    def type_text(self, text: str):
        self.focus()
        self._run(["xdotool", "type", "--delay", "60", "--", text])

    def scroll(self, x: int, y: int, up: bool = True, n: int = 3):
        self.move(x, y)
        btn = "4" if up else "5"
        for _ in range(n):
            self._run(["xdotool", "click", btn])
            time.sleep(0.02)

    # ------------------------------------------------------------------ #
    # dialog helpers                                                        #
    # ------------------------------------------------------------------ #
    def dismiss_dialogs(self, attempts: int = 3):
        """Best-effort dialog dismissal: Escape then Enter."""
        for _ in range(attempts):
            time.sleep(0.15)
            self.key("Escape")
        time.sleep(0.1)

    def confirm_dialog(self):
        """Press Enter to accept a dialog."""
        time.sleep(0.15)
        self.key("Return")
        time.sleep(0.15)


# ------------------------------------------------------------------ #
# Layout                                                               #
# ------------------------------------------------------------------ #
class QETLayout:
    """
    Models the approximate pixel layout of the QElectroTech main window.
    All coords are in absolute screen space (already offset by win_x/win_y).
    """

    MENU_H = 25
    TOOLBAR_H = 58   # combined main + diagram toolbars
    STATUS_H = 25
    PANEL_W = 265    # element collection panel
    PROP_W = 0       # properties panel width (collapsed by default)

    def __init__(self, win_x: int, win_y: int, win_w: int, win_h: int):
        self.wx = win_x
        self.wy = win_y
        self.ww = win_w
        self.wh = win_h

    # --- menu bar ---------------------------------------------------- #
    @property
    def menu_y(self) -> int:
        return self.wy + self.MENU_H // 2

    def menu_click(self, x_frac: float) -> tuple[int, int]:
        return (
            self.wx + int(self.ww * x_frac),
            self.wy + self.MENU_H // 2,
        )

    # --- canvas ------------------------------------------------------ #
    @property
    def canvas_x0(self) -> int:
        return self.wx + self.PANEL_W

    @property
    def canvas_y0(self) -> int:
        return self.wy + self.MENU_H + self.TOOLBAR_H

    @property
    def canvas_x1(self) -> int:
        return self.wx + self.ww - self.PROP_W - 5

    @property
    def canvas_y1(self) -> int:
        return self.wy + self.wh - self.STATUS_H

    @property
    def canvas_cx(self) -> int:
        return (self.canvas_x0 + self.canvas_x1) // 2

    @property
    def canvas_cy(self) -> int:
        return (self.canvas_y0 + self.canvas_y1) // 2

    def random_canvas(self, margin: int = 60) -> tuple[int, int]:
        x = random.randint(self.canvas_x0 + margin, self.canvas_x1 - margin)
        y = random.randint(self.canvas_y0 + margin, self.canvas_y1 - margin)
        return x, y

    def near_canvas(self, cx: int, cy: int, radius: int = 80) -> tuple[int, int]:
        angle = random.uniform(0, 6.28)
        r = random.randint(20, radius)
        import math
        x = int(cx + r * math.cos(angle))
        y = int(cy + r * math.sin(angle))
        x = max(self.canvas_x0 + 10, min(self.canvas_x1 - 10, x))
        y = max(self.canvas_y0 + 10, min(self.canvas_y1 - 10, y))
        return x, y

    # --- element panel ----------------------------------------------- #
    @property
    def panel_cx(self) -> int:
        return self.wx + self.PANEL_W // 2

    def random_panel(self, y_frac_lo: float = 0.3, y_frac_hi: float = 0.85) -> tuple[int, int]:
        x = random.randint(self.wx + 8, self.wx + self.PANEL_W - 8)
        y = random.randint(
            self.wy + int(self.wh * y_frac_lo),
            self.wy + int(self.wh * y_frac_hi),
        )
        return x, y

    # --- toolbar ---------------------------------------------------- #
    def toolbar_btn(self, x_frac: float) -> tuple[int, int]:
        return (
            self.wx + int(self.ww * x_frac),
            self.wy + self.MENU_H + self.TOOLBAR_H // 2,
        )
