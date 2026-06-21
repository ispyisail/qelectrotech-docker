"""
Diagram-level operations: add/remove pages, change properties,
navigate between tabs, zoom, scroll.
"""
import logging
import random
import time

log = logging.getLogger(__name__)


def add_diagram_page(xdo, layout):
    log.info("action: add_diagram_page")
    # Diagram menu → New diagram
    xdo.key("alt+d")
    time.sleep(0.3)
    xdo.key("n")
    time.sleep(0.6)
    # A properties dialog may appear — accept it
    xdo.key("Return")
    time.sleep(0.4)


def diagram_properties(xdo, layout):
    log.info("action: diagram_properties")
    xdo.key("alt+d")
    time.sleep(0.3)
    xdo.key("p")
    time.sleep(0.6)
    xdo.key("Return")
    time.sleep(0.3)


def next_diagram_tab(xdo, layout):
    log.info("action: next_diagram_tab")
    xdo.key("ctrl+Tab")
    time.sleep(0.2)


def prev_diagram_tab(xdo, layout):
    log.info("action: prev_diagram_tab")
    xdo.key("ctrl+shift+Tab")
    time.sleep(0.2)


def zoom_in(xdo, layout):
    n = random.randint(1, 4)
    log.info("action: zoom_in x%d", n)
    cx, cy = layout.canvas_cx, layout.canvas_cy
    xdo.scroll(cx, cy, up=True, n=n)


def zoom_out(xdo, layout):
    n = random.randint(1, 4)
    log.info("action: zoom_out x%d", n)
    cx, cy = layout.canvas_cx, layout.canvas_cy
    xdo.scroll(cx, cy, up=False, n=n)


def zoom_fit(xdo, layout):
    log.info("action: zoom_fit")
    xdo.key("ctrl+0")
    time.sleep(0.2)


def zoom_reset(xdo, layout):
    log.info("action: zoom_reset")
    xdo.key("ctrl+9")
    time.sleep(0.2)


def scroll_canvas(xdo, layout):
    log.info("action: scroll_canvas")
    cx, cy = layout.random_canvas()
    # Random scroll direction
    for _ in range(random.randint(1, 5)):
        direction = random.choice(["up", "down"])
        xdo.scroll(cx, cy, up=(direction == "up"), n=random.randint(1, 3))
        time.sleep(0.05)


def pan_canvas(xdo, layout):
    """Middle-click drag to pan the canvas."""
    log.info("action: pan_canvas")
    x1, y1 = layout.random_canvas()
    x2, y2 = layout.random_canvas()
    xdo.move(x1, y1)
    time.sleep(0.05)
    # Middle button drag
    xdo._run(["xdotool", "mousedown", "2"])
    time.sleep(0.08)
    xdo.move(x2, y2)
    time.sleep(0.1)
    xdo._run(["xdotool", "mouseup", "2"])
    time.sleep(0.1)


def click_canvas_empty(xdo, layout):
    """Click on an empty spot to deselect."""
    log.info("action: click_canvas_empty")
    x, y = layout.random_canvas()
    xdo.click(x, y)


def right_click_canvas(xdo, layout):
    """Right-click canvas to open context menu, then dismiss."""
    log.info("action: right_click_canvas")
    x, y = layout.random_canvas()
    xdo.right_click(x, y)
    time.sleep(0.4)
    xdo.dismiss_dialogs(1)


def delete_diagram_page(xdo, layout):
    log.info("action: delete_diagram_page")
    xdo.key("alt+d")
    time.sleep(0.3)
    xdo.key("d")
    time.sleep(0.4)
    # Confirmation dialog — confirm
    xdo.key("Return")
    time.sleep(0.3)
