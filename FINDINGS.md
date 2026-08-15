# Findings

Verified defects and verification results. Each entry: what was claimed, what
was actually observed, the exact command, and what remains unproven.

---

## F001 — PR #707 / bugtracker #312: verification gap partially closed

**Date:** 2026-08-16
**Binary:** `/home/user/qet-fix/build-fast/qelectrotech`, built from
`cabinet-layout-editor` @ `3ba741ed9` (**pre-fix** — still calls
`forceMovedByUser`)
**Status:** persistence half **proven**; command half **still unproven**

### The claim under test

PR #707 (merged 2026-08-15, commit `6c76b1f6a`) fixes bugtracker #312 by
swapping two calls in `RotateTextsCommand::undo()/redo()` from
`forceMovedByUser()` to `forceRotateByUser()`. Its own commit message states:

> A full save/close/reopen round-trip on a from-scratch two-element wire was
> attempted but not completed due to unreliable terminal-to-terminal wire
> drawing via synthetic mouse events in the window-manager-less Xvfb sandbox;
> confidence in the fix instead rests on tracing the exact save-gate code path.

So the user-visible symptom was never observed to disappear.

### The defect chain

1. `RotateTextsCommand::redo()` sets a user-override flag on each
   `ConductorTextItem` — **the buggy line set the wrong flag**
2. `Conductor::toXml()` (`sources/qetgraphicsitem/conductor.cpp:1108`)
   writes `rotation` **only if** `m_text_item->wasRotatedByUser()`
3. `ConductorTextItem::fromXml()` (`conductortextitem.cpp:77-80`) restores
   both the rotation and the flag when the attribute is present

### PROVEN — links 2 and 3, headlessly, on real data

`examples/Habitat-Schemas_developpes.qet` contains 40 conductors carrying a
`rotation` attribute. Two consecutive resaves preserve all 40:

```bash
export HOME=<sandbox> XDG_CONFIG_HOME=<sandbox> XDG_DATA_HOME=<sandbox>
export QT_QPA_PLATFORM=offscreen
timeout 120 qelectrotech --resave examples/Habitat-Schemas_developpes.qet r1.qet
timeout 120 qelectrotech --resave r1.qet r2.qet
grep -o '<conductor [^>]*\brotation="[^"]*"' <file> | wc -l
```

| File | conductors with `rotation` |
|---|---|
| input | 40 |
| after resave 1 | 40 |
| after resave 2 | 40 |

The save gate fires and the load path restores the flag. **This was the half
that had never been observed.** It is now observed, on real user data.

### NOT PROVEN — link 1

That `RotateTextsCommand::redo()` actually sets `rotate_by_user_` remains
verified only by inspection. The inspection is unambiguous —
`ConductorTextItem::forceRotateByUser(bool)` at `conductortextitem.cpp:122-125`
assigns `rotate_by_user_` and nothing else — but it is not an observation.

### Why it could not be observed (the real finding)

**`RotateTextsCommand` opens a blocking modal dialog inside its constructor.**
`rotatetextscommand.cpp:107-136` — `openDialog()` builds a `QDialog` and calls
`ori_text_dialog.exec()`. The command cannot be constructed without a human
answering a dialog, so it is:

- untestable headlessly
- undrivable from `--test-ops` or any future scripting API (`SCRIPTING-RFC.md`)
- the reason this verification gap exists, and will keep existing

This is the same defect class as PR #737 (a modal on a headless path). **Fix
worth proposing:** give `RotateTextsCommand` an angle parameter and move
`openDialog()` to the caller (`qetdiagrameditor.cpp:1663`). Small,
self-contained, and it makes the command testable — the category that merges
upstream in ~1.7 days.

### Second, unreported symptom of the original bug

The buggy code called `forceMovedByUser(true)`. That did not merely fail to
save the rotation — it **spuriously marked the text as manually positioned**,
so `Conductor::toXml()` wrote `userx`/`usery` (gate at `conductor.cpp:1103`).
Projects saved by an affected build therefore carry position pins the user
never set, and those survive the fix. Whether that needs a migration or is
harmless is **not yet assessed**. Not filed.

### GUI automation notes (cost 6 attempts; recorded so nobody repeats them)

Attempting the end-to-end GUI round-trip failed for four separate reasons,
none of which is the bug:

1. **No window manager is installed natively**, so `xdotool windowactivate`
   fails with "your windowmanager claims not to support _NET_ACTIVE_WINDOW".
   `xdotool windowfocus` (XSetInputFocus) works instead.
2. **The startup backup prompt** ("Souhaitez-vous créer une copie de
   sauvegarde ?") is modal and **ignores Escape** — it must be answered
   Oui/Non. Until then it swallows every keystroke.
3. **Double-clicking a folio in the project tree opens folio properties**
   rather than switching to that folio — another modal, swallowing input again.
4. `perceuse.qet` opens on folio 1 ("Descriptif"), a photo page with no
   conductors. The schematic is folio 3.

Consistent with `TOOLING-PLAN.md` and the `qet-bughunt` skill: the file layer
answered in one command what the GUI could not answer in six attempts. Script
kept at `scratchpad/verify312.sh`; **not** promoted into the repo.
