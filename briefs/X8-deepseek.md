# TASK BRIEF — X8: audit what every graphics item does on double-click, right-click and hover

Self-contained. Read `CROSSPAGE-PLAN.md` in this repo first for context.

---

## 0. HOW THIS TASK ENDS — read first

Seven of fifteen sessions on this project ended by **announcing they would
wait** instead of waiting. Two more **crashed and lost everything** because
nothing was on disk.

- **Never end your turn waiting.** Poll in a loop.
- **Commit early and often.**
- **Never report a criterion done without pasting its real output.**

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/x8-progress.log
```

---

## 1. Why this exists

Upstream PR #701 tried to make double-clicking a folio-reference arrow jump to
its linked folio. It was rejected, and the discussion revealed that **nobody has
a complete picture of what double-click currently means across QElectroTech's
graphics items.**

A hand survey found a strong existing convention:

| Item | Double-click |
|---|---|
| `QetGraphicsItem` (base: elements, arrows, images, shapes, tables) | `editProperty()` |
| `Conductor` | `editProperty()` |
| `DiagramTextItem` / `DynamicElementTextItem` / `PartText` | enter text editing |
| `HelperCell` (titleblock) | emits `doubleClicked` |
| `TerminalStripItem` | opens the hovered xref |
| `CrossRefItem` | **navigates** to the linked element |
| `ElementTextItemGroup` (slave only) | **navigates** to the linked master |

That survey was manual and may be wrong or incomplete. **Your job is to produce
the complete, verified version** — and to do the same for right-click and hover,
which nobody has surveyed at all.

**This is an inventory. Do not propose or implement UI changes.**

---

## 2. What to build

`tools/interactionaudit/` — Python 3, stdlib only, static analysis. No build,
no QET launch.

For every class deriving (directly or transitively) from `QGraphicsItem`,
`QGraphicsObject`, `QGraphicsTextItem` or `QetGraphicsItem`, produce a record:

| Field | Meaning |
|---|---|
| `class`, `header`, `source` | identity |
| `base` | its immediate base class |
| `dblclick` | `own` / `inherited(<class>)` / `none` |
| `dblclick_effect` | short classification — see below |
| `context_menu` | `own` / `inherited(...)` / `none` |
| `hover` | does it implement `hoverEnterEvent`/`hoverLeaveEvent`? |
| `press` | does it implement `mousePressEvent`? |
| `accepts_hover` | does it call `setAcceptHoverEvents(true)`? |

**`dblclick_effect`** — classify by what the handler body actually calls:

- `edit-properties` — calls `editProperty()` or opens a properties dialog
- `edit-text` — enters inline text editing
- `navigate` — calls `showMe()` / `setSelected()` on another item, or
  `centerOn`
- `delegate` — forwards to an event interface or a base class only
- `signal` — emits a signal and nothing else
- `other` — anything else; say what it does

Output `reports/interactions.{json,md}`, with the markdown containing a table
sorted by `dblclick_effect` so the outliers are obvious.

**Record the ref you scanned** — `tools/actionaudit/actionaudit.py` has a
`source_ref()` helper. This project has already lost time comparing a feature
branch against master.

---

## 3. Definition of done — paste real output

### Criterion 1 — the hand survey is confirmed or corrected

Reproduce the table in §1. Every row must come out with the stated effect, **or
you must show why the hand survey was wrong.** A correction is a good outcome —
say so plainly and show the code.

### Criterion 2 — the population is complete

Report how many item classes were found. As a cross-check, the following counts
were measured on `upstream/master`:

```
files implementing mouseDoubleClickEvent : 20
files implementing contextMenuEvent      :  6
files implementing hoverEnterEvent       : 13
files implementing mousePressEvent       : 30
headers declaring item subclasses        : 19
```

If your numbers differ, **say so and explain** — do not tune to match. These
were crude `git grep -c` counts and may themselves be wrong.

### Criterion 3 — the outliers, named

List every class whose `dblclick_effect` is **not** `edit-properties` or
`edit-text`, with its effect and source location. This is the deliverable that
answers "is double-click consistent?".

### Criterion 4 — inheritance is resolved, not guessed

For at least three classes that do **not** implement `mouseDoubleClickEvent`
themselves, show which ancestor's handler they actually get. `ReportElement`
must be one of them — it is the case that started this, and the expected answer
is `inherited(QetGraphicsItem)` → `edit-properties`.

---

## 4. Traps

1. **Scan `upstream/master`, not the working tree.** `/home/user/qet-fix` is
   checked out on `cabinet-layout-editor` and is **195 commits behind**
   upstream. Use a worktree or `git show upstream/master:<path>`; record which
   you used.
2. **Multi-level inheritance is the whole point.** `ReportElement` → `Element` →
   `QetGraphicsItem`. Resolve the chain; do not stop at the immediate base.
3. **A handler that only calls its base is `delegate`, not `own`** — e.g.
   `DynamicElementTextItem::mouseDoubleClickEvent` forwards to
   `DiagramTextItem`. Classify by what the body does.
4. **Some classes live in the element editor** (`sources/editor/`), a separate
   scene from the diagram editor. Record which subsystem each belongs to;
   consistency within a subsystem matters more than across them.
5. **Do not modify QElectroTech source.** Read-only.

---

## 5. Scope

**May create:** `tools/interactionaudit/**`, `reports/interactions.{json,md}`.

**Do NOT:** modify QET source; propose or implement any UI change; touch
`simulator/`, `tools/refdiff/`, `tools/crosspage/`, `tools/actionaudit/`,
`tools/exportleak/`, `tools/labelstability/`, or any `.md` plan file; push or
open a PR.

**Work on a new branch** in this repo.

---

## 6. Report

All four criteria with real pasted output, the full outlier list, and anything
in this brief that was wrong or underspecified — especially if the §1 hand
survey turns out to be inaccurate.
