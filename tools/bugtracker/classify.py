"""
repro_class heuristic: ``headless`` / ``gui`` / ``unclear``.

A guess from the bug text -- nothing more. ``headless`` means the text
implies an operation that maps to one of QET's headless CLI verbs (load /
export / resave / info / titleblock), i.e. something auto_repro could
exercise without a human at the mouse. ``gui`` means the text implies an
interaction (click / drag / menu / display / editor). ``unclear`` is the
honest answer when neither set of signals dominates.

This is the only classification done in stage 1. It deliberately does NOT
guess source files (that is stage 2's code_paths), does NOT rank bugs, and
does NOT decide staleness.
"""
from __future__ import annotations

# Signals that the bug is about loading/saving/exporting a file or the CLI.
HEADLESS_TERMS = [
    "command line",
    "command-line",
    "commandline",
    " cli",
    "cli ",
    "headless",
    "batch",
    "startup",
    "launch",
    "autosave",
    "auto-save",
    "resave",
    "re-save",
    "save as",
    "save project",
    "saving",
    "open project",
    "opening project",
    "open a project",
    "open file",
    "opening file",
    "open the project",
    "open .qet",
    "load project",
    "loading project",
    "load a project",
    "load file",
    "loading file",
    "load the project",
    "import",
    "export",
    "exported",
    "print",
    "pdf",
    "png",
    "svg",
    "csv",
    "bom",
    "bill of material",
    "nomenclature",
    "cross reference",
    "cross-reference",
    "title block",
    "titleblock",
    "conductor list",
    "cable list",
    "wire list",
    "check-elements",
    "check elements",
    "element collection",
    ".qet",
    ".elmt",
    ".edz",
    "crash on open",
    "crash on load",
    "crash on start",
    "crash on launch",
    "crash at startup",
    "freeze on open",
    "freeze on load",
    "hang on open",
    "hang on load",
    "hang at startup",
    "segfault",
    "segfaults",
    "crash when opening",
    "crash when loading",
    "crash while opening",
    "crash while loading",
]

# Signals that the bug needs a human at the GUI.
GUI_TERMS = [
    "click",
    "double-click",
    "drag",
    "drop",
    "menu",
    "toolbar",
    "button",
    "dialog",
    "window",
    "panel",
    "editor",
    "element editor",
    "diagram editor",
    "draw",
    "drawing",
    "wire",
    "conductor",
    "zoom",
    "scroll",
    "select",
    "selection",
    "right-click",
    "right click",
    "mouse",
    "cursor",
    "keyboard",
    "shortcut",
    "display",
    "render",
    "rendering",
    "icon",
    "thumbnail",
    "thumbnail",
    "ui ",
    "interface",
    "tab",
    "align",
    "alignment",
    "overlap",
    "overlapped",
    "composite text",
    "text label",
    "label",
    "color",
    "colour",
    "dark theme",
    "theme",
    "grid",
    "snap",
    "layout",
    "visual",
    "visible",
    "invisible",
    "black",
    "font",
    "pixel",
    "screen",
    "size",
]


def classify(text: str) -> str:
    """Return 'headless', 'gui', or 'unclear' for a blob of bug text."""
    t = " " + (text or "").lower() + " "
    headless_hits = [term for term in HEADLESS_TERMS if term in t]
    gui_hits = [term for term in GUI_TERMS if term in t]
    hs, gs = len(headless_hits), len(gui_hits)
    if hs > gs:
        return "headless"
    if gs > hs:
        return "gui"
    return "unclear"


def classify_bug(record: dict) -> str:
    """Classify a bug record from its summary + description + steps."""
    text = " ".join(
        [
            record.get("summary") or "",
            record.get("description") or "",
            record.get("steps_to_reproduce") or "",
        ]
    )
    return classify(text)
