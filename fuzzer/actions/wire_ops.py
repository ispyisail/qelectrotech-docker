"""
Wire / conductor drawing operations.

QET wire-drawing workflow:
  1. Hover over a terminal (small yellow square on element edge).
  2. Click to start the conductor.
  3. Move and click intermediate points.
  4. Click a second terminal to complete, or press Escape to cancel.

Because we can't reliably detect terminal positions from a headless
screenshot, we approximate them by clicking *near* known element
positions on the canvas and trusting that random hits will eventually
land on terminals.
"""
import logging
import random
import time

log = logging.getLogger(__name__)

# Distance from element centre to search for a terminal (px)
_TERMINAL_RADIUS = 22


def _terminal_near(layout, cx, cy):
    """Return a point near (cx, cy) where a terminal might be."""
    x = cx + random.randint(-_TERMINAL_RADIUS, _TERMINAL_RADIUS)
    y = cy + random.randint(-_TERMINAL_RADIUS, _TERMINAL_RADIUS)
    x = max(layout.canvas_x0 + 5, min(layout.canvas_x1 - 5, x))
    y = max(layout.canvas_y0 + 5, min(layout.canvas_y1 - 5, y))
    return x, y


def draw_wire(xdo, layout, positions):
    """
    Attempt to draw a wire between two element positions.
    `positions` — list of (x, y) canvas positions of placed elements.
    Returns True if a wire attempt was made.
    """
    if len(positions) < 2:
        log.debug("draw_wire: need ≥2 elements")
        return False

    log.info("action: draw_wire")
    a, b = random.sample(positions, 2)

    # Start point near element A
    sx, sy = _terminal_near(layout, a[0], a[1])
    # End point near element B
    ex, ey = _terminal_near(layout, b[0], b[1])

    # Click start terminal
    xdo.click(sx, sy)
    time.sleep(0.2)

    # Add 0–2 intermediate waypoints for more realistic routing
    n_mid = random.randint(0, 2)
    for _ in range(n_mid):
        mx = random.randint(
            min(sx, ex) - 40, max(sx, ex) + 40
        )
        my = random.randint(
            min(sy, ey) - 40, max(sy, ey) + 40
        )
        mx = max(layout.canvas_x0 + 5, min(layout.canvas_x1 - 5, mx))
        my = max(layout.canvas_y0 + 5, min(layout.canvas_y1 - 5, my))
        xdo.click(mx, my)
        time.sleep(0.1)

    # End terminal
    xdo.click(ex, ey)
    time.sleep(0.2)

    # If the wire was started but not connected, cancel
    xdo.key("Escape")
    time.sleep(0.1)
    return True


def draw_wire_random(xdo, layout):
    """Draw a wire between two random canvas points (no element tracking)."""
    log.info("action: draw_wire_random")
    sx, sy = layout.random_canvas(margin=80)
    ex, ey = layout.random_canvas(margin=80)
    xdo.click(sx, sy)
    time.sleep(0.15)
    xdo.click(ex, ey)
    time.sleep(0.15)
    xdo.key("Escape")
    time.sleep(0.1)


def delete_wire(xdo, layout):
    """Click a random canvas point hoping to hit a wire, then delete."""
    log.info("action: delete_wire")
    x, y = layout.random_canvas(margin=40)
    xdo.click(x, y)
    time.sleep(0.1)
    xdo.key("Delete")
    time.sleep(0.15)


def right_click_wire(xdo, layout):
    """Right-click a point hoping to get a wire context menu."""
    log.info("action: right_click_wire")
    x, y = layout.random_canvas(margin=40)
    xdo.right_click(x, y)
    time.sleep(0.4)
    xdo.dismiss_dialogs(1)


def edit_wire_properties(xdo, layout):
    """Double-click hoping to open a conductor properties dialog."""
    log.info("action: edit_wire_properties")
    x, y = layout.random_canvas(margin=40)
    xdo.double_click(x, y)
    time.sleep(0.5)
    xdo.key("Return")
    time.sleep(0.2)
    xdo.dismiss_dialogs(1)


def flood_wires(xdo, layout):
    """Draw 15-20 random wires in rapid succession."""
    n = random.randint(15, 20)
    log.info("action: flood_wires x%d", n)
    for _ in range(n):
        sx, sy = layout.random_canvas(margin=40)
        ex, ey = layout.random_canvas(margin=40)
        xdo.click(sx, sy)
        time.sleep(0.05)
        xdo.click(ex, ey)
        time.sleep(0.05)
        xdo.key("Escape")
        time.sleep(0.02)
