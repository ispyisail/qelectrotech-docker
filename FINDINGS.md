# Findings

Verified defects and verification results. Each entry: what was claimed, what
was actually observed, the exact command, and what remains unproven.

---

## F001 — PR #707 / bugtracker #312: verification gap partially closed

**Date:** 2026-08-16
**Binary:** `/home/user/qet-fix/build-fast/qelectrotech`, built from
`cabinet-layout-editor` @ `3ba741ed9` (**pre-fix** — still calls
`forceMovedByUser`)
**Status:** **CLOSED 2026-08-16** — both halves proven. See F001-b below for the
A/B that closed it, and the refactor that made it possible. The sections that
follow describe the state before that work.

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

---

## F001-b — PR #707 / #312 verification gap CLOSED, and the refactor that closed it

**Date:** 2026-08-16
**Branch:** `fix/rotate-texts-dialog-out-of-command` in
`/home/user/qet-fix-wt/rotatetexts`, off `upstream/master` @ `610001a84`
**Commit:** `7b4fbfde6` — 3 files, +85/-17

### The blocker, removed

`RotateTextsCommand` called `QDialog::exec()` from inside its constructor, so
it could not be built without a human. The refactor takes the angle as a
constructor parameter and moves the asking into two statics:

```cpp
static bool hasSelectedTexts(Diagram *diagram);   // anything to rotate?
static bool askRotation(qreal &rotation);         // dialog; false if cancelled
```

The single call site (`qetdiagrameditor.cpp`, `"rotate_selected_text"`) asks
first, then builds the command. GUI behaviour is unchanged: same dialog, same
title, and still no dialog on an empty selection. `askRotation()` stays in this
class deliberately so the `QObject` `tr()` context is preserved and existing
translations of *"Orienter les textes sélectionnés"* are not invalidated.

### The A/B that closed the gap

Driven headlessly through a **scratch** `--test-ops` op (`rotate_texts`, kept
out of the PR) against `examples/741.qet` — 67 conductors, single folio, all
`rotation` attributes stripped first:

```bash
echo '[{"op":"rotate_texts","angle":45}]' > ops.json
QT_QPA_PLATFORM=offscreen qelectrotech --test-ops in.qet ops.json out.qet
grep -o '<conductor [^>]*\brotation="[^"]*"' out.qet | wc -l
```

| build | conductors with `rotation` | conductors with `userx` |
|---|---|---|
| PR #707 applied (`forceRotateByUser`) | **67** | 0 |
| PR #707 reverted (`forceMovedByUser`) | **0** | **67** |

- **Symptom reproduced:** the reverted build writes no rotation at all — the
  rotation is lost on reload. That is bugtracker #312.
- **Fix confirmed:** the fixed build writes all 67.
- **Second symptom confirmed:** the hypothesis recorded in F001 is now
  measured. The buggy build wrote `userx` on all 67 conductors, spuriously
  pinning text positions the user never moved. Projects saved by an affected
  build carry those pins, and the fix does not remove them. **Whether that
  needs a migration is still unassessed.**

### Latent null dereference, fixed in passing

When nothing is selected the constructor calls `setObsolete(true)` without ever
creating `m_anim_group`, and `QUndoStack::push()` calls `redo()` *before* it
discards an obsolete command — dereferencing a null pointer. Unreachable today
only because the action is disabled on an empty selection. `undo()`/`redo()`
now guard. This is exactly the shape W5's undo/redo oracle is meant to find.

### Known limitation of the headless path

The rotation *value* is applied through `QPropertyAnimation` via
`m_anim_group->start()`, which needs a spinning event loop. Headless, the flag
is set and the attribute is written, but the value stays at its pre-animation
figure (`rotation="0"` rather than `45`). Fine for testing the save gate, which
is what #312 was about; a scripted caller wanting the actual angle applied
would need the animation to complete or be bypassed. Not filed.

---

## F002 — L6 phase 2: audit of inferred claims across 136 PRs

**Date:** 2026-08-16
**Input:** `reports/pr-evidence.json` (phase 1, calibration verified:
#707 `inferred`, #682/#737 `observed`)

### Headline: no second #707 found

**136 PRs audited — 22 observed, 108 inferred, 6 unstated. No further
#707-class defect identified.** That is the honest result, and it is worth as
much as a list of suspects would have been.

The base rate matters: an inferred claim is *unverified*, not *wrong*. Most of
the 108 are small, self-contained bugtracker fixes whose mechanism is short
enough to read correctly. Elevating them wholesale would produce a worklist
nobody would action.

### Investigated and cleared: the dark-theme icon family

The strongest a-priori signal was **three PRs for one bug** — #620, #695
("two dialogs missed by the earlier fix"), #744 — the same shape as #707, where
parallel call sites got fixed inconsistently.

**It is resolved.** #620 and #695 patched individual consumers; #744 fixed the
*production* point in `elementpicturefactory.cpp`:

```cpp
-  pix.fill(QColor(255, 255, 255, 0));   // transparent
+  pix.fill(Qt::white);                  // opaque
```

Every consumer of that pixmap inherits the fix, including the untouched sites
in `elementslocation.cpp:862` and `fileelementcollectionitem.cpp:53`. The
progression is per-consumer patches converging on a root-cause fix — a good
outcome, not an open risk.

### The real finding: O4 cannot be evaluated on master yet

Attempting to test a *class* of merged undo/redo claims (#590, #645, #660 and
others) with the L2 lab binary produced this, on `examples/741.qet`:

| op sequence | result |
|---|---|
| `select_all` (no-op) | **FAIL** |
| `select_all, delete, undo` | FAIL |
| `select_all, move, undo` | FAIL |
| `select_all, rotate, undo` | FAIL |
| `select_all, rotate_texts, undo` | FAIL |

**The no-op baseline fails**, so this measures the harness, not the commands.
Two mistakes on the way there, both worth recording:

1. **First attempt compared un-warmed inputs** — two independent first-saves of
   a legacy project assign different conductor UUIDs (`TOOLING-PLAN.md` §2
   trap 2). Warming the corpus first removed that.
2. **Warming was not enough.** The residual diff is
   `conductors key-set differs`. Conductor identity in `canon.py` is the sorted
   `(terminal1, terminal2)` pair, and terminal indices are assigned by
   `Diagram::toXml`'s iteration over `QGraphicsScene::items()` — *stacking
   order, not content order*. This is the known non-idempotence documented in
   `tests/determinism/check.py`, and it shuffles conductor keys between saves
   of identical content.

**Consequence for `TOOLING-PLAN.md` W5:** the O4 undo/redo metamorphic oracle
is **blocked on save determinism**, not on op vocabulary. W5 assumed the lab
binary was the missing piece; it is necessary but not sufficient. Either fix
the `Diagram::toXml` ordering first, or give `canon.py` a conductor projection
that does not derive identity from terminal indices. **This should be settled
before W5 is scheduled** — otherwise every O4 result will be noise.

### Candidates that remain worth a check (not yet suspect)

Listed with the specific check, not elevated to suspect:

| PR | Claim | Check once O4 is unblocked |
|---|---|---|
| #645 | auto-numbering counter changes covered by undo/redo | O4 on a numbering op |
| #660 | rotate group rotates a selection as a whole | O4 + grid check; `as_group` is still rejected by `--test-ops` |
| #642 | user-defined custom properties on elements | `set_property` then O5 — `element_info` is PR #664's bug family |

`element_count == element_info_count` held at 65/65 across every op run during
this audit, so no orphan-row regression is visible today.

### Not re-flagged

**#707 is resolved** (F001, F001-b) and is the calibration case, not a finding.

---

## F003 — `Diagram::toXml` scrambles element *order*, not just terminal ids

**Date:** 2026-08-16
**Binary:** `build-ab/7307a59c101a/build/qelectrotech` (`nightly-388-g7307a59c1`,
current master)
**Status:** confirmed, reproducible, not filed upstream

### The measurement

`examples/ShellyParts.qet` contains **zero conductors**. Eight `--resave` runs of
the same warmed input produced **eight distinct outputs**:

```
8 runs -> 8 distinct md5s
```

Diffing two of them shows whole `<element>` blocks emitted in a different
sequence, with `<terminal id=...>` values shuffling along with them:

```
< <element type="...shelly_rgbw2.elmt" x="480" y="330" .../>
> <element type="...shelly1pm.elmt"    x="330" y="160" .../>
<     <terminal x="-13.5673" y="40.9602" id="12" orientation="2"/>
```

Control, same conditions: `examples/pinball_williams_em.qet` is **stable** —
8 runs, 8 identical outputs. So this is a property of certain documents, not of
the binary or the environment.

### Why it matters

F004 established that conductor `terminal1`/`terminal2` values are legacy
integers from a pointer-keyed `QHash` rebuilt each save, and therefore vary
between processes. **F003 shows that was the symptom, not the disease.**
`Diagram::toXml` iterates `QGraphicsScene::items()`, and that iteration
scrambles the *element serialization order itself*. Terminal ids shuffle
because the elements they belong to shuffle.

Consequences:

- A canonical projection that fixes only conductor identity **will still fail**,
  and will look like a conductor bug when it is not.
- Any projection must **sort every collection by a content-derived key** before
  comparing — elements by uuid, terminals by position or name — and never trust
  document order.
- `tests/determinism`'s I1 ("save is idempotent") cannot hold for affected
  documents until `Diagram::toXml` derives an order from content.

### Correction to W1's O2 split

The W1 session classified the warmed corpus as *0 uuid artifacts, 19
persistently non-idempotent, 1 probabilistic, 2 clean* — naming
`ShellyParts.qet` and `pinball_williams_em.qet` as the clean pair.

**`ShellyParts.qet` is not clean; it is the most non-deterministic file in the
corpus** (8/8 distinct). The corrected split is **1 clean**, not 2. W1's
*conclusion* is unaffected and in fact strengthened — the defect is real,
warming cannot fix it, and the fix belongs in QET rather than the harness.

### Known-good / known-bad pair for anyone building the projection

| File | Behaviour |
|---|---|
| `examples/pinball_williams_em.qet` | stable — 8/8 identical resaves |
| `examples/ShellyParts.qet` | unstable — 8/8 distinct resaves |

A projection that reports both as stable has gone blind and is worthless. Use
them as the calibration pair.

## F004 — `Diagram::toXml` terminal-id churn is non-deterministic run-to-run, so warming cannot fix it (W1 brief premise wrong)

> **Renumbered on merge** (was F002 on the W1 branch; that number was already
> taken). Chronologically this is the *root* finding — F003 later showed the
> same `items()` iteration also scrambles element order, of which terminal-id
> churn is a symptom. Read F004 then F003.

**Date:** 2026-08-16
**Binary:** `/home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech`
(`nightly-388-g7307a59c1` — current master)

### The claim under test

W1 brief §1: the simulator's O9 self-check fails because *"QET assigns a fresh
`uuid` to every `<conductor>` when loading a legacy project that lacks them"* —
67 of them on `741.qet` — *"and is stable only from the second save on."* The
prescribed fix is to warm the corpus once (`--resave` every seed) so the
migration is absorbed before the sweep runs, after which O9 should pass.

### What was actually observed

- `Conductor::toXml()` (`sources/qetgraphicsitem/conductor.cpp:1040`) has **no
  conductor-uuid code at all**. The only identifier it writes is `terminal1` /
  `terminal2`, which is either the terminal's *stable* uuid (when the terminal
  has one) or a **legacy integer id** looked up in `table_adr_id`.
- `Diagram::toXml()` (`sources/diagram.cpp:1039`) rebuilds
  `QHash<Terminal *, int> table_adr_id` **from scratch on every save**, assigning
  ids sequentially in `QGraphicsScene::items()` order (stacking order, not a
  content-derived order) via `Element::toXml()` (`element.cpp:953`).
- The churn is therefore **not a first-save migration**: it recurs on every save
  and is **non-deterministic run-to-run** (the pointer-keyed `QHash` + stacking
  order depend on ASLR). Measured with `simulator/oracles.py` O9:

```bash
python3 -m simulator warm-corpus --binary "$BIN" --corpus /home/user/qet-fix/examples --out /tmp/warm
python3 -m simulator sweep --binary "$BIN" --corpus /tmp/warm --iterations 50
#   "o9_deterministic": false
#   O9: "identical input produced different canonical output"
#       diagram order=1 conductors key-set differs: only_a=['0-97','1-10','10-8'] only_b=['0-48','1-5','10-19']
```

- A 5-probe idempotence sweep over the warmed corpus classifies the 22
  resavable seeds as: **0** uuid-migration artifacts, **19** persistently
  non-idempotent, **1** probabilistic (small file, coin-flip), **2** clean
  (`ShellyParts.qet`, `pinball_williams_em.qet`); `schema_indus.qet` hangs (PR
  #737).

### Conclusion

The brief's artifact does not exist in these binaries, and warming cannot make
O9 pass — the defect makes identical input produce different output across two
separate runs, which is exactly what O9 exists to detect. The fix is in QET
(`Diagram::toXml` must derive terminal ids from content, not `items()` order),
not in the harness. `tests/determinism/check.py` documents the same root cause
as its "I1 does not hold" note; the run-to-run non-determinism above is the
additional fact that makes the sweep's findings uninterpretable rather than
merely non-idempotent.
