"""
Selection, clipboard and undo/redo operations.
"""
import logging
import random
import time

log = logging.getLogger(__name__)


def select_all(xdo, layout):
    log.info("action: select_all")
    xdo.key("ctrl+a")
    time.sleep(0.1)


def deselect_all(xdo, layout):
    log.info("action: deselect_all")
    xdo.key("Escape")
    time.sleep(0.1)


def rubber_band_select(xdo, layout):
    """Drag a rubber-band selection box on the canvas."""
    log.info("action: rubber_band_select")
    x1, y1 = layout.random_canvas(margin=100)
    x2, y2 = layout.random_canvas(margin=100)
    xdo.drag(x1, y1, x2, y2, steps=15)
    time.sleep(0.2)


def copy_selection(xdo, layout):
    log.info("action: copy_selection")
    xdo.key("ctrl+c")
    time.sleep(0.1)


def cut_selection(xdo, layout):
    log.info("action: cut_selection")
    xdo.key("ctrl+x")
    time.sleep(0.1)


def paste(xdo, layout):
    log.info("action: paste")
    xdo.key("ctrl+v")
    time.sleep(0.3)
    # Pasted items appear on cursor; click canvas to anchor them
    x, y = layout.random_canvas(margin=80)
    xdo.click(x, y)
    time.sleep(0.15)


def delete_selection(xdo, layout):
    log.info("action: delete_selection")
    xdo.key("Delete")
    time.sleep(0.15)


def undo(xdo, layout):
    n = random.randint(1, 4)
    log.info("action: undo x%d", n)
    for _ in range(n):
        xdo.key("ctrl+z")
        time.sleep(0.08)


def redo(xdo, layout):
    n = random.randint(1, 3)
    log.info("action: redo x%d", n)
    for _ in range(n):
        xdo.key("ctrl+y")
        time.sleep(0.08)


def select_all_then_delete(xdo, layout):
    log.info("action: select_all_then_delete")
    xdo.key("ctrl+a")
    time.sleep(0.15)
    xdo.key("Delete")
    time.sleep(0.2)


def select_copy_paste(xdo, layout):
    """Select all, copy, paste — stresses clipboard + duplicate-element path."""
    log.info("action: select_copy_paste")
    xdo.key("ctrl+a")
    time.sleep(0.1)
    xdo.key("ctrl+c")
    time.sleep(0.1)
    xdo.key("ctrl+v")
    time.sleep(0.3)
    # Click to place
    x, y = layout.random_canvas(margin=60)
    xdo.click(x, y)
    time.sleep(0.2)


def move_selection_arrow(xdo, layout):
    """Nudge selected items with arrow keys."""
    log.info("action: move_selection_arrow")
    keys = ["Up", "Down", "Left", "Right"]
    for _ in range(random.randint(3, 12)):
        xdo.key(random.choice(keys))
        time.sleep(0.04)


def paste_bomb(xdo, layout):
    """Select all, copy, then paste many times — exponentially grows the diagram."""
    n = random.randint(5, 10)
    log.info("action: paste_bomb x%d", n)
    xdo.key("ctrl+a")
    time.sleep(0.1)
    xdo.key("ctrl+c")
    time.sleep(0.1)
    for _ in range(n):
        xdo.key("ctrl+v")
        time.sleep(0.15)
        x, y = layout.random_canvas(margin=60)
        xdo.click(x, y)
        time.sleep(0.1)


def undo_storm(xdo, layout):
    """Hammer undo 40 times then redo 20 — stresses the undo stack hard."""
    log.info("action: undo_storm")
    xdo.click(layout.canvas_cx, layout.canvas_cy)
    time.sleep(0.1)
    for _ in range(40):
        xdo.key("ctrl+z")
        time.sleep(0.02)
    for _ in range(20):
        xdo.key("ctrl+y")
        time.sleep(0.02)
