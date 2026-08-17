#!/usr/bin/env python3
"""Cross-check the S2 runtime action dump against the S1 static audit.

Usage:
  scripts/action-dump-crosscheck.py \
      reports/actions-runtime.json reports/actions.json

For every dumped action carrying a non-empty shortcut, decide whether it
"appears in the static list with registered=true", is a Qt built-in, or
neither.  Prints the three counts and the lists.

Matching is by normalised text (mnemonics stripped, whitespace collapsed).
Two factory-created undo/redo actions in QETTitleBlockTemplateEditor are
matched specially: the static audit records them registered=true but with
text=None (createUndoAction/createRedoAction take no tr() label), so they
never match on text.
"""
import json
import re
import sys


def norm(s):
    if s is None:
        return ""
    s = s.replace("&", "")
    s = re.sub(r"\s+", " ", s).strip()
    while s.endswith("..."):
        s = s[:-3].rstrip()
    return s


def main(runtime_path, static_path):
    static = json.load(open(static_path))
    runtime = json.load(open(runtime_path))

    registered_by_text = {}
    factory_undo_redo = []  # (owner, constructor) for createUndo/RedoAction
    for a in static["actions"]:
        if not a.get("registered"):
            continue
        ctor = a.get("constructor")
        if ctor in ("createUndoAction", "createRedoAction"):
            factory_undo_redo.append((a.get("owner"), ctor))
        t = norm(a.get("text"))
        if t:
            registered_by_text.setdefault(t, []).append(a)

    all_actions = []
    for w in runtime["windows"]:
        for a in w["actions"]:
            a = dict(a)
            a["window"] = w["window_class"]
            all_actions.append(a)

    shortcut_actions = [a for a in all_actions if a["shortcut"].strip()]

    matched = []
    qt_builtin = []
    neither = []

    for a in shortcut_actions:
        t = norm(a["text"])
        if t in registered_by_text:
            matched.append(a)
            continue
        # Factory undo/redo: registered in static, but text is None there.
        if t in ("Undo", "Redo") and (
            a["owner_class"],
            "create%sAction" % ("Undo" if t == "Undo" else "Redo"),
        ) in factory_undo_redo:
            matched.append(a)
            continue
        # Qt built-in: QWhatsThis is the one QMainWindow adds out of the box.
        if t == "What's This?":
            qt_builtin.append(a)
            continue
        neither.append(a)

    print("shortcut actions (non-empty shortcut): %d" % len(shortcut_actions))
    print("matched (registered=true in static) : %d" % len(matched))
    print("Qt built-in                         : %d" % len(qt_builtin))
    print("neither                             : %d" % len(neither))
    print()
    print("=== Qt built-in ===")
    for a in qt_builtin:
        print("  %-26s | %-12s | %r" % (a["window"], a["shortcut"], a["text"]))
    print()
    print("=== neither (genuine findings) ===")
    for a in neither:
        print("  %-26s | %-12s | %r | obj=%r owner=%s" %
              (a["window"], a["shortcut"], a["text"], a["objectName"],
               a["owner_class"]))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: %s <actions-runtime.json> <actions.json>" % sys.argv[0])
    main(sys.argv[1], sys.argv[2])
