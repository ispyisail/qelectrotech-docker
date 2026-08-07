"""
Element operations: drag from panel to canvas, move, rotate,
double-click to edit properties, delete.
"""
import logging
import random
import time

log = logging.getLogger(__name__)

# Panel tree rows that are likely to be actual elements (not headers).
# We use randomised vertical position in the lower 60% of the panel,
# where leaf elements typically appear after the tree is expanded.
_PANEL_ELEM_Y_LO = 0.35
_PANEL_ELEM_Y_HI = 0.90


def expand_panel_tree(xdo, layout):
    """Click a random spot in the panel and press * to expand all children."""
    log.info("action: expand_panel_tree")
    x, y = layout.random_panel(y_frac_lo=0.15, y_frac_hi=0.45)
    xdo.click(x, y)
    time.sleep(0.2)
    xdo.key("asterisk")     # Qt tree: * expands all children
    time.sleep(0.4)


def drag_element_to_canvas(xdo, layout):
    """
    Drag a random item from the element panel onto the canvas.
    Returns the approximate drop position (x, y) or None if nothing was dragged.
    """
    log.info("action: drag_element_to_canvas")
    src_x, src_y = layout.random_panel(
        y_frac_lo=_PANEL_ELEM_Y_LO,
        y_frac_hi=_PANEL_ELEM_Y_HI,
    )
    dst_x, dst_y = layout.random_canvas(margin=80)
    xdo.drag(src_x, src_y, dst_x, dst_y, steps=25)
    time.sleep(0.3)
    # QET may open an element properties dialog after drop — dismiss it
    xdo.dismiss_dialogs(1)
    return dst_x, dst_y


def move_element(xdo, layout, positions):
    """
    Move an already-placed element.  `positions` is the fuzzer's tracked
    list of (x, y) canvas positions; we pick one and drag it nearby.
    """
    if not positions:
        log.debug("move_element: no tracked positions")
        return
    log.info("action: move_element")
    src_x, src_y = random.choice(positions)
    # Click to focus + select
    xdo.click(src_x, src_y)
    time.sleep(0.1)
    dst_x, dst_y = layout.near_canvas(src_x, src_y, radius=120)
    xdo.drag(src_x, src_y, dst_x, dst_y, steps=20)
    time.sleep(0.2)


def rotate_selected(xdo, layout):
    """Press Space to rotate a selected element (QET default shortcut)."""
    log.info("action: rotate_selected")
    xdo.key("space")
    time.sleep(0.1)


def rotate_element(xdo, layout, positions):
    """Click an element then rotate it."""
    if not positions:
        return
    log.info("action: rotate_element")
    x, y = random.choice(positions)
    xdo.click(x, y)
    time.sleep(0.15)
    for _ in range(random.randint(1, 4)):
        xdo.key("space")
        time.sleep(0.08)


def edit_element_properties(xdo, layout, positions):
    """Double-click an element to open its properties dialog, then close."""
    if not positions:
        return
    log.info("action: edit_element_properties")
    x, y = random.choice(positions)
    xdo.double_click(x, y)
    time.sleep(0.7)
    # Fill in a random comment field if one is active
    xdo.type_text("fuzz_%d" % random.randint(1000, 9999))
    time.sleep(0.2)
    xdo.key("Return")
    time.sleep(0.3)
    xdo.dismiss_dialogs(1)


def delete_element(xdo, layout, positions):
    """Click an element and press Delete."""
    if not positions:
        return
    log.info("action: delete_element")
    x, y = random.choice(positions)
    xdo.click(x, y)
    time.sleep(0.1)
    xdo.key("Delete")
    time.sleep(0.2)


def right_click_element(xdo, layout, positions):
    """Right-click an element to open context menu, then dismiss."""
    if not positions:
        return
    log.info("action: right_click_element")
    x, y = random.choice(positions)
    xdo.right_click(x, y)
    time.sleep(0.4)
    xdo.dismiss_dialogs(1)


def click_random_element(xdo, layout, positions):
    """Click a tracked element to select it."""
    if not positions:
        return
    log.info("action: click_random_element")
    x, y = random.choice(positions)
    xdo.click(x, y)
    time.sleep(0.1)


def flood_elements(xdo, layout):
    """Drag 15-25 elements to the canvas in rapid succession."""
    n = random.randint(15, 25)
    log.info("action: flood_elements x%d", n)
    new_positions = []
    for _ in range(n):
        src_x, src_y = layout.random_panel(
            y_frac_lo=_PANEL_ELEM_Y_LO,
            y_frac_hi=_PANEL_ELEM_Y_HI,
        )
        dst_x, dst_y = layout.random_canvas(margin=40)
        xdo.drag(src_x, src_y, dst_x, dst_y, steps=8)
        time.sleep(0.05)
        xdo.dismiss_dialogs(1)
        new_positions.append((dst_x, dst_y))
    return new_positions
