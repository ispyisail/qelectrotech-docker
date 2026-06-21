"""
Element editor operations: open built-in editor, draw primitive parts,
save element to user collection, close editor.

The element editor is a separate window launched from:
  Edit menu → Edit element  (if an element is selected), OR
  Double-clicking an element in the collection panel.
"""
import logging
import random
import time

log = logging.getLogger(__name__)

# Approximate editor canvas centre fraction (relative to editor window)
_EC_X_FRAC = 0.55
_EC_Y_FRAC = 0.50


def _editor_canvas(geo: dict):
    """Return approximate canvas centre of the element editor window."""
    x = geo["x"] + int(geo["w"] * _EC_X_FRAC)
    y = geo["y"] + int(geo["h"] * _EC_Y_FRAC)
    return x, y


def _editor_random(geo: dict, margin: int = 60):
    w, h = geo["w"], geo["h"]
    x = geo["x"] + random.randint(
        int(w * 0.35) + margin, int(w * 0.95) - margin
    )
    y = geo["y"] + random.randint(
        int(h * 0.12) + margin, int(h * 0.88) - margin
    )
    return x, y


def open_new_element_editor(xdo, layout):
    """
    Open the built-in element editor via Edit menu → Create a new element.
    Returns True if we think the editor opened.
    """
    log.info("action: open_new_element_editor")
    xdo.key("alt+e")        # Edit menu
    time.sleep(0.3)
    # Navigate to "Create a new element" (usually 3rd item under Edit)
    for _ in range(3):
        xdo.key("Down")
        time.sleep(0.06)
    xdo.key("Return")
    time.sleep(1.2)
    # The editor asks for a name — type one and accept
    xdo.type_text("fuzz_elem_%d" % random.randint(100, 9999))
    time.sleep(0.1)
    xdo.key("Return")
    time.sleep(0.8)
    return True


def open_edit_selected_element(xdo, layout, positions):
    """Open the element editor for the currently selected element."""
    if not positions:
        return False
    log.info("action: open_edit_selected_element")
    x, y = random.choice(positions)
    xdo.click(x, y)
    time.sleep(0.12)
    xdo.key("alt+e")
    time.sleep(0.3)
    # "Edit selected element" is usually the first or second item
    xdo.key("Down")
    time.sleep(0.06)
    xdo.key("Return")
    time.sleep(1.2)
    return True


def _draw_line(xdo, geo):
    """Draw a line in the element editor."""
    # Toolbar: line tool is typically 2nd drawing button (very rough estimate)
    xdo.key("l")            # QET editor shortcut for line
    time.sleep(0.15)
    x1, y1 = _editor_random(geo)
    x2, y2 = _editor_random(geo)
    xdo.drag(x1, y1, x2, y2, steps=12)
    time.sleep(0.2)


def _draw_rect(xdo, geo):
    xdo.key("r")
    time.sleep(0.15)
    x1, y1 = _editor_random(geo)
    x2, y2 = _editor_random(geo)
    xdo.drag(x1, y1, x2, y2, steps=12)
    time.sleep(0.2)


def _draw_ellipse(xdo, geo):
    xdo.key("e")
    time.sleep(0.15)
    x1, y1 = _editor_random(geo)
    x2, y2 = _editor_random(geo)
    xdo.drag(x1, y1, x2, y2, steps=12)
    time.sleep(0.2)


def _add_text(xdo, geo):
    xdo.key("t")
    time.sleep(0.15)
    cx, cy = _editor_canvas(geo)
    xdo.click(cx + random.randint(-40, 40), cy + random.randint(-20, 20))
    time.sleep(0.2)
    xdo.type_text("txt%d" % random.randint(1, 999))
    time.sleep(0.1)
    xdo.key("Return")
    time.sleep(0.15)


def _add_terminal(xdo, geo):
    """Add a terminal pin to the element."""
    xdo.key("p")            # QET editor shortcut for terminal
    time.sleep(0.15)
    x, y = _editor_random(geo)
    xdo.click(x, y)
    time.sleep(0.2)


def do_editor_actions(xdo, geo, n: int = 5):
    """
    Perform random drawing actions inside the element editor.
    `geo` is the dict returned by xdo.get_geometry() for the editor window.
    """
    ops = [_draw_line, _draw_rect, _draw_ellipse, _add_text, _add_terminal]
    weights = [4, 3, 2, 2, 3]
    for _ in range(n):
        fn = random.choices(ops, weights=weights, k=1)[0]
        try:
            fn(xdo, geo)
        except Exception as exc:
            log.warning("editor action %s failed: %s", fn.__name__, exc)
        time.sleep(random.uniform(0.1, 0.4))


def save_element_editor(xdo):
    """Save element in the editor (Ctrl+S)."""
    log.info("action: save_element_editor")
    xdo.key("ctrl+s")
    time.sleep(0.5)
    # "Save as" dialog may appear
    xdo.type_text("fuzz_elem")
    time.sleep(0.1)
    xdo.key("Return")
    time.sleep(0.5)
    xdo.dismiss_dialogs(2)


def save_element_to_user_collection(xdo):
    """
    Save element to user collection via File → Save to user collection.
    QET may show a collection browser dialog.
    """
    log.info("action: save_element_to_user_collection")
    xdo.key("ctrl+shift+s")
    time.sleep(0.8)
    xdo.key("Return")
    time.sleep(0.4)
    xdo.dismiss_dialogs(2)


def close_element_editor(xdo):
    """Close the element editor window."""
    log.info("action: close_element_editor")
    xdo.key("ctrl+w")
    time.sleep(0.4)
    # Discard unsaved changes prompt
    xdo.key("alt+n")
    time.sleep(0.3)
    xdo.dismiss_dialogs(1)


def fuzz_element_editor(xdo, layout, positions=None):
    """
    Full element-editor fuzz cycle:
      open new editor → draw random shapes → save → close.
    """
    log.info("action: fuzz_element_editor (full cycle)")
    if not open_new_element_editor(xdo, layout):
        return

    geo = xdo.get_geometry()
    if not geo or geo["w"] < 400:
        log.warning("editor window not found or too small, skipping")
        xdo.dismiss_dialogs(3)
        return

    do_editor_actions(xdo, geo, n=random.randint(3, 8))
    save_element_editor(xdo)
    time.sleep(0.3)
    close_element_editor(xdo)
    time.sleep(0.5)
