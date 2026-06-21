"""
Project / file operations: new, save, close, export PDF, print.
"""
import logging
import random
import time

log = logging.getLogger(__name__)


def new_project(xdo, layout):
    log.info("action: new_project")
    xdo.key("ctrl+n")
    time.sleep(1.2)
    # May open a 'new element wizard' or project dialog — press Escape if so
    xdo.dismiss_dialogs(2)


def save_project(xdo, layout):
    log.info("action: save_project")
    xdo.key("ctrl+s")
    time.sleep(0.6)
    # Handle "save as" dialog on first save (type a name, hit Enter)
    xdo.type_text("fuzz_test")
    time.sleep(0.1)
    xdo.key("Return")
    time.sleep(0.4)


def save_as(xdo, layout):
    log.info("action: save_as")
    xdo.key("ctrl+shift+s")
    time.sleep(0.8)
    xdo.type_text("fuzz_saveas")
    time.sleep(0.1)
    xdo.key("Return")
    time.sleep(0.5)


def export_pdf(xdo, layout):
    log.info("action: export_pdf")
    # File menu → Export
    xdo.key("alt+F2")        # open File menu  (QET uses Alt+F)
    time.sleep(0.3)
    xdo.key("alt+f")
    time.sleep(0.3)
    # Navigate down to Export
    for _ in range(6):
        xdo.key("Down")
        time.sleep(0.05)
    xdo.key("Return")
    time.sleep(0.8)
    # In the export dialog, accept defaults and click OK/Export
    xdo.key("Return")
    time.sleep(1.0)
    xdo.dismiss_dialogs(2)


def export_pdf_shortcut(xdo, layout):
    """Try Ctrl+Shift+P if the menu approach is flaky."""
    log.info("action: export_pdf_shortcut")
    xdo.key("ctrl+shift+p")
    time.sleep(1.0)
    xdo.key("Return")
    time.sleep(0.8)
    xdo.dismiss_dialogs(2)


def close_project(xdo, layout):
    log.info("action: close_project")
    xdo.key("ctrl+w")
    time.sleep(0.5)
    # "Save changes?" dialog — choose No to discard
    xdo.key("alt+n")
    time.sleep(0.3)


def open_preferences(xdo, layout):
    log.info("action: open_preferences")
    xdo.key("ctrl+comma")
    time.sleep(0.6)
    xdo.dismiss_dialogs(2)


def print_diagram(xdo, layout):
    log.info("action: print_diagram")
    xdo.key("ctrl+p")
    time.sleep(0.8)
    xdo.dismiss_dialogs(3)
