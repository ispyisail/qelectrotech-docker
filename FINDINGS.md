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

---

## F005 — `QPropertyUndoCommand::undo()` never applies without an event loop

**Date:** 2026-08-16
**Binary:** `build-lab/qelectrotech` (branch `lab/test-ops-extended`)
**Status:** confirmed, reproducible, **not filed upstream**

### The symptom

With the F003/F004 canonical projection in place, three of four op
round-trips are clean and one is not:

| op sequence | canon diffs |
|---|---|
| `select_all` (no-op) | 0 |
| `select_all, delete, undo` | 0 |
| `select_all, move, undo` | 0 |
| **`select_all, rotate(90), undo`** | **2** |

After the undo, all 65 elements keep `orientation` = original+1 (mod 4) and all
53 dynamic texts keep `rotation` = 270. The rotation is applied and never
reversed.

### Root cause — an asymmetry between redo and undo

`sources/undocommand/qpropertyundocommand.cpp`:

```cpp
redo():   if (m_animate && m_first_time)   // after the first time, writes directly
undo():   if (m_animate)                   // no m_first_time guard -- ALWAYS animates
```

`RotateSelectionCommand` builds per-item `QPropertyUndoCommand`s with
`setAnimated(true, false)`. `redo()` writes the property directly once
`m_first_time` is false, so the rotation lands. `undo()` has no equivalent
guard and always defers to a `QPropertyAnimation` — which never runs in a
synchronous headless CLI, because nothing pumps an event loop.

`delete` and `move` use `DeleteQGraphicsItemCommand` / `MoveGraphicsItemCommand`,
whose `undo()` writes state directly. That is why only rotate fails.

### Why it matters

- **For the GUI:** unproven either way. A real session pumps an event loop, so
  the animation probably completes. This has not been tested interactively and
  should not be assumed benign.
- **For automation:** any headless caller — `--test-ops`, a future scripting
  API, W5's O4 oracle — sees rotate-undo silently do nothing. No error, no
  warning, wrong state.
- It is the same class as the `RotateTextsCommand` modal (PR #752): a command
  that only works inside an interactive session, with nothing saying so.

### Suggested fix

Mirror redo's guard in undo — `if (m_animate && m_first_time)` — or have the
animation path fall back to a direct write when no event loop is running.
Needs GUI verification before proposing upstream.

### Two side-consequences flagged by the same session

1. `simulator/fixtures/fixture_determinism.py` now reports **UNEXPECTED PASS**.
   Its premise was "O2 rediscovers the byte-level I1 bug", but O2 is now
   content-level by design. The fixture's expectation needs updating; it was
   outside that task's modify-scope.
2. `photovoltaique.qet` shows an intermittent dynamic-text position drift
   between consecutive resaves (a `UserText` at `(10.0, 20.0)` → `(5.33, 26.53)`),
   on roughly 2 of 8 trials. Pre-existing and unrelated to the projection
   change, but relevant to O4.

## F006 — `canon.py` collides duplicate dynamic-text uuids, producing phantom diffs (resolves the F005 side-note)

**Status:** tool defect in this repo, not a QET defect. Found by W3's refdiff
sweep on its first clean run.

### Repro

```
cd <repo> && python3 -m tools.refdiff --base master --head master
  -> 114 same, 0 regression, 0 improvement, 1 change (115 comparisons), exit 0
  photovoltaique --resave: CHANGE
    diagram order=1 dynamic_texts value differs for ['{93c0008c-...}']
```

Same binary, same input, both variants exit 0 in 0.4s — yet the projection
reports a semantic difference.

### Cause

`dynamic_elmt_text` uuids are **not unique within a project**. Element-embedded
texts inherit their uuid from the element *definition* in the library, so every
placement of that element carries the same text uuid. In
`examples/photovoltaique.qet` one uuid appears twice and others appear up to
**four** times.

`simulator/canon.py:141` keys them in a flat dict at *diagram* scope:

```python
dtexts[u] = {k: ... for k in _DTEXT_KEYS}      # last writer wins
```

`d.iter()` walks document order, which follows element serialization order —
and that order is unstable run-to-run (F003). So which duplicate wins the key
changes between runs, and its `x`/`y`/value land in the projection.

Confirmed by a second observation: across two runs `photovoltaique` reported
**different uuids** as the differing one (`{93c0008c-...}` vs `{1a69228d-...}`).
A stable difference would name the same uuid every time; a collision does not.

### This resolves the open question in F005's side-note 2

That note recorded `photovoltaique.qet` dynamic-text drift `(10.0, 20.0)` ->
`(5.33, 26.53)` on ~2 of 8 trials, "pre-existing... relevant to O4". It is this
bug. The two colliding texts sit at `x=-10,y=-20` and `x=10,y=-10`; whichever
wins the key flips the recorded coordinates, which is exactly the drift seen.
It is **not** a QET save-path defect and does not belong to O4.

### Why it matters

- It is a **false positive in the oracle itself** — the failure mode most likely
  to train people to ignore the tool. It fired on run one of the first clean
  sweep.
- Every sweep will carry >=1 phantom `change` until fixed. Harmless for exit
  codes (only `regression` is fatal) but it pollutes every report.

### Fix — DONE

Dynamic texts are now keyed by `(parent element uuid, text uuid)`, gathered by
walking down from each `<element>` (ElementTree has no parent pointers, so the
owner is only knowable top-down). Texts belonging to a uuid-less element, or to
no element at all, are still recorded rather than dropped. A same-uuid collision
*within one element* — not present anywhere in the corpus, max observed 1 — is
kept as a content-sorted list instead of letting document order pick a winner,
which would be this same bug one level down.

### It was worse than a phantom diff: 41% of dynamic texts were never compared

The phantom `change` was the visible symptom. The real damage was silent: on
`photovoltaique.qet` folio 1 the file holds **51** dynamic texts but only **30**
distinct text uuids, so the old flat dict kept 30 and **21 were overwritten and
never compared at all**. Any real corruption to those 21 was invisible to every
oracle built on this projection. A false positive is annoying; this was a blind
spot.

### Verification

- `photovoltaique --resave`, master vs master: `5 same, 0 change` on **6
  consecutive runs** (the bug was intermittent — ~2 of 8 trials — so a single
  clean run would not have been evidence).
- Still detects real change, i.e. the fix is not merely looser: moving one of
  the two previously-colliding texts to `x="-999"` is reported as
  `dynamic_texts value differs for
  ['{635a6585-...}/{93c0008c-...}']` — and the key now names the owning element,
  which the old projection could not do.
- 4 regression tests in `simulator/tests/test_canon.py`
  (`TestDynamicTextUuidCollision`), including one asserting projected text count
  equals the count in the file, which fails on the old keying by construction.
- All 11 simulator test modules and the 10 refdiff classifier tests pass.

### Cross-item check: W2's P003 — already handled, no action needed

W2 stage 1 defines **P003 = duplicate uuid within one project = error**, and the
brief pointed it at `canon.canonicalize()`'s `uuid_universe`. That universe
contains every uuid attribute in the document, so the rule as briefed would have
inherited exactly this collision.

**It does not.** `tools/qet-lint/rules_project.py:63` scopes P003 to `<element>`
uuids only, and its docstring records the reason: the same uuid legitimately
recurs on `terminal` / `dynamic_elmt_text` / `link_uuid` because QET copies a
sub-item's uuid when instantiating an element or duplicating a folio.

Measured on the 23 example projects:

| Scope | Duplicate uuids flagged |
|---|---|
| every `uuid` attribute (as briefed) | **912** |
| `<element>` only (as implemented) | **0** |

`python3 -m tools.qet-lint /home/user/qet-fix/examples/*.qet` reports no
violations of any rule. So W2's session caught this independently and deviated
from its brief for a documented, correct reason — the scoping is load-bearing,
not incidental, and P003's counts can be trusted.

The two findings share one root cause: **a uuid in a `.qet` file is only unique
within its owning scope.** Only `<element>` uuids are project-unique. Any future
rule or projection keyed on a bare uuid should state which scope makes it
unique, or repeat this bug.

## F007 — `uuid_universe` recorded one tag per uuid, so cross-folio links flipped it

**Status:** fixed. Same root cause as F006, one level up. Found by re-running
the full sweep after the F006 fix — the fix worked, and uncovered this.

### Repro

```
master vs pr-721, full corpus, AFTER the F006 fix:
  114 same, 0 regression, 0 improvement, 1 change (115 comparisons), exit 0
  affuteuse_250h --resave: CHANGE
    1 uuid(s) changed tag type: ['{110ddbed-e690-4e31-bfd3-14822f25ac37}']
```

The tell was that the finding **moved projects**. Before the F006 fix the same
sweep flagged `industrial` and `photovoltaique`; after it, neither — but
`affuteuse_250h` appeared instead. A real PR effect does not wander between
projects between runs; remaining non-determinism does.

### Cause

`canon.py` built the universe as `uuid_universe[u] = el.tag` — last writer wins.
But a uuid is **not owned by one tag**: a cross-folio master/slave link writes
the target element's uuid into a `<link_uuid>` node, so the same uuid appears on
both `<element>` and `<link_uuid>`. In `affuteuse_250h.qet` **66 uuids** are
carried by both tags.

`root.iter()` walks document order, which `Diagram::toXml` scrambles (F003), so
which tag was recorded last flipped between resaves and `diff()`'s
`common_tag_mismatch` check reported a phantom difference.

### Fix

`uuid_universe` now maps each uuid to the **sorted tuple of every tag carrying
it**. Order-independent, JSON-serialisable through `to_dict()`, and strictly
more informative than the old single tag. Consumers were checked first:
`oracles.py:75` and `diff()`'s uuid-set comparison use only the keys, so only
the `common_tag_mismatch` value comparison was affected.

### Verification

Full corpus, 115 comparisons each (23 projects x 5 verbs), run 2026-08-16 after
the fix:

| Sweep | Before F007 | After F007 | Exit |
|---|---|---|---|
| `master` vs `master` | 115 same, 0 change | **115 same, 0 change** | 0 |
| `master` vs `pr-721` | 114 same, **1 change** | **115 same, 0 change** | 0 |

`affuteuse_250h` no longer appears in the `pr-721` report at all. Reports:
`refdiff-reports/f007-mvm/`, `refdiff-reports/f007-pr721/`.

That makes `master` vs `pr-721` the first fully clean cross-ref sweep: a UI-only
PR (Information tab for Slave/Terminal basetypes) provably does not perturb
saved output anywhere in the corpus. The projection now has **no known false
positives**, which is what makes an unattended nightly run worth acting on.

- 3 regression tests, including one that reverses element order within each
  folio — exactly what F003 does — and asserts the tag sets are unchanged.
- Still detects a genuine tag change rather than merely being looser.
- All 11 simulator modules, 10 refdiff tests, and qet-lint pass.

### The pattern, now twice

F006 and F007 are the same mistake at two levels: **a uuid in a `.qet` is unique
only within its owning scope**, and a flat dict keyed on a bare uuid silently
resolves collisions by document order — which is unstable. Only `<element>`
uuids are project-unique. Any future projection or rule keyed on a bare uuid
must state the scope that makes it unique, or it will reproduce this.

## F008 — a legacy-version project hangs every CLI verb forever on an undismissable modal

**Status:** real QET defect. **Already proposed upstream as PR #661**
("Fix command-line tools hanging forever on a modal message box"), open and
unmerged as of 2026-08-17. This entry records the concrete instance and its
measured cost; it is not a new bug report.

### Repro

```
binary: /home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech
        sha256 def8b1f8fb959a47...   (master 7307a59c1)

HOME=$(mktemp -d) XDG_CONFIG_HOME=$(mktemp -d) XDG_DATA_HOME=$(mktemp -d) \
  timeout 30 qelectrotech -platform offscreen \
    --resave examples/schema_indus.qet /tmp/out.qet
```

**Expected:** resave completes, or exits non-zero with a diagnostic.
**Actual:** hangs until killed externally — `exit=124` at the timeout, no output,
no error. Not slow: it never terminates on its own.

Control, same binary and flags:

| Project | Declared version | Result |
|---|---|---|
| `741.qet` | `0.90` | **exit 0, <1s** |
| `schema_indus.qet` | `0.3` | **exit 124, hangs** |

So it is the version gate, not file size or content.

### Mechanism

`QETProject::readProjectXml()` (`sources/qetproject.cpp:1494`) raises a modal for
any project at version <= 0.6:

```cpp
if (m_project_qet_version <= QetVersion::versionZeroDotSix()) {
    auto ret = QET::QetMessageBox::warning(nullptr, tr("Avertissement "), ...,
                                           QMessageBox::Open | QMessageBox::Cancel);
```

`QET::QetMessageBox` (`sources/qetmessagebox.h`) is a thin wrapper over
`QMessageBox` whose only added behaviour is MacOS window-modality — it has **no
non-interactive path**. Under `-platform offscreen` there is no one to click
Open or Cancel, so `exec()` blocks forever.

A **second** modal at `sources/qetproject.cpp:1476` is the same trap in the
other direction: a project saved by a *newer* QET than the running one. Nothing
in the corpus triggers it today, but any file from a future release will.

### Why it matters

- Every CLI verb is affected, not just `--resave`: the modal is in the shared
  load path, so `--info`, `--export-bom`, `--export-nets` and `--export-links`
  all hang on the same file.
- It fails in the worst possible way for automation — no error, no exit, no
  output. Only an external timeout ends it, so any caller without one hangs
  indefinitely.
- Legacy files are exactly what a compatibility sweep most wants to test, and
  they are precisely the ones that cannot be tested.
- Measured cost before mitigation: **1202s** for this single project (5 verbs x
  2 refs x 120s), roughly 20 of every 23-minute corpus sweep.

Corpus scope: **1 of 23** example projects (`schema_indus.qet`). Small today,
but it is the only pre-0.6 file available — the blind spot is the whole legacy
class, not one file.

### Relationship to the refdiff mitigation

`48ff4e2` makes the sweep skip a project's remaining verbs once the first times
out on both refs, cutting that 1202s to 240s. That is a **harness mitigation,
not a fix** — the project still cannot be swept at all, and the 240s is still
two dead timeouts. PR #661 is the actual fix.

### Fix

PR #661. Any `QetMessageBox` call reachable from a CLI verb needs a
non-interactive path that picks the safe default (here: `Open`, matching what a
user pressing the obvious button gets) and reports the choice on stderr rather
than blocking.
