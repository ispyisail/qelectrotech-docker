# TASK BRIEF — S1: enumerate every QElectroTech action and whether it is bindable

Self-contained. Assume no skill files or plan documents are loaded.

---

## 0. HOW THIS TASK ENDS — read first

Seven of eleven sessions on this project have failed the same way: they did the
work, then **ended their turn announcing they would wait** for a command. That
is the one way to fail this brief.

- **Never end your turn while waiting.** Poll in a loop — sleep, re-check,
  continue — until the thing finishes.
- **Never report a criterion done without pasting its real output.**
- If something cannot finish, say so and stop. "Criterion 3 blocked because X"
  is a good outcome. Silence while waiting is not.

**Progress logging.** A previous session on this project crashed mid-run and
left no trace of how far it got. After each meaningful step append one line:

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/s1-progress.log
```

---

## 1. Why this exists

QElectroTech has a configurable-shortcut system (`ShortcutManager` +
a Shortcuts config page). An action registered with it can be bound to any key
by the user. **An action that is not registered cannot be bound at all** — it
never appears in the config page.

Today **97 registration call sites** exist, concentrated in three files, while
the source constructs on the order of 227 actions. Nobody knows which of the
remainder are real, user-triggerable actions versus separators, dynamic
menu entries, or duplicates.

**Your job is to produce that list, accurately.** You are not deciding what
deserves a shortcut — that is a later, human step. An inventory that stays an
inventory is exactly what is wanted.

---

## 2. What to build

`tools/actionaudit/` in this repo — a static analyser over the QElectroTech
source. **Python 3, stdlib only. No build, no QET launch.** It should run over
the whole source tree in seconds.

One record per action:

| Field | Meaning |
|---|---|
| `id` | the `registerAction` id if registered, else `null` |
| `text` | the `tr("…")` label as written |
| `file`, `line` | where the action is constructed |
| `registered` | is it passed to `ShortcutManager::registerAction`? |
| `default_sequence` | the sequence given at registration, **verbatim source text** |
| `connected` | is it wired to a slot/signal — i.e. **does it do something**? |
| `kind` | `action` / `separator` / `dynamic` / `checkable` |
| `owner` | the class or file that constructs it |

Parse: `new QAction`, `addAction(`, `registerAction(`, `connect(`, and
`<action name=` in `.ui` files.

Output `reports/actions.json` plus a readable `reports/actions.md` summarising
counts by `registered` / `connected` / `kind` / `owner`.

---

## 3. Definition of done — paste real output

### Criterion 1 — reproduce the registration count independently

Your parser must find **97 `registerAction` call sites** across **95 distinct
ids**.

The gap is real and is itself a fixture: `"elementeditor.delete"` and
`"elementeditor.quit"` are each registered **twice** (two different targets
share one id — `ShortcutManager` appends the second target to the same entry).
Report both numbers separately. **95 is the number of rows the config page
shows; 97 is the number of call sites.** Conflating them is a bug.

If you get different numbers, **say so and show your working** — do not tune the
parser until it hits 97. A disagreement is either a bug in your parser or a
mistake in this brief, and both are worth knowing.

### Criterion 2 — the two anchor actions resolve correctly

| Anchor | Expected |
|---|---|
| `sources/qetmainwindow.cpp:232` | `id="mainwindow.fullscreen"`, `registered=true`, category `Général`, sequence `Qt::CTRL \| Qt::SHIFT \| Qt::Key_F` |
| `sources/qet.cpp:789` | `id="depth.raise"`, `registered=true`, category `Profondeur`, sequence `Qt::CTRL \| Qt::SHIFT \| Qt::Key_Up` |

### Criterion 3 — a `.ui` action is found and correctly marked unregistered

`.ui` files declare 56 actions and **none carry a `shortcut` property**. Show at
least one from `sources/editor/ui/qetelementeditor.ui` in your output with
`registered=false`.

### Criterion 4 — the honest gap list

Report the count of actions with `connected=true` **and** `registered=false` —
things that do something but cannot be bound. Break it down by `owner`.

Also report `connected=false` separately: an action that exists but is wired to
nothing is a **possible bug**, not a shortcut gap. Do not merge the two.

---

## 4. Traps

1. **Sequences are Qt enum expressions, not strings.** The dominant form is
   `Qt::CTRL | Qt::SHIFT | Qt::Key_F`, not `QKeySequence("Ctrl+Shift+F")`. Both
   appear. Capture the **verbatim source text** — do not try to evaluate it into
   a key string; that is guesswork and nothing downstream needs it yet.
2. **`registerAction`'s first argument is a `QObject*`, not always a `QAction`.**
   `autonumberingdockwidget.cpp:164` registers a `QPushButton`. Do not assume
   the target is an action.
3. **Multi-line calls.** Registration calls wrap across lines. A line-by-line
   regex will miss them; join logical statements before matching.
4. **`new QAction` overcounts.** Some are separators, some are dynamic
   (recent-files entries built in a loop), some are constructed in a helper
   called many times. Classify via `kind` rather than inflating the gap.
5. **Do not "fix" anything.** No source edits to QElectroTech at all.

---

## 5. Environment

| Thing | Value |
|---|---|
| QET source | `/home/user/qet-fix` — **read only** |
| Python | 3.14, stdlib only |

**Never `git checkout`, `switch`, `stash` or `reset` in `/home/user/qet-fix`.**
It holds ~30 uncommitted files on branch `cabinet-layout-editor` that are not
yours. You only need to *read* that tree — do not create a worktree, do not
modify it.

---

## 6. Scope

**May create:** `tools/actionaudit/**`, `reports/actions.{json,md}`.

**Do NOT:** modify any QElectroTech source; change `ShortcutManager`; decide
which actions deserve shortcuts (that is a later human step); touch
`simulator/`, `scenarios/`, `tools/refdiff/`, `tools/shortcut-harness/`,
`tests/`, or any `.md` plan file; push, open a PR, or post anywhere.

**Work on a new branch** in this repo.

---

## 7. Report

Commit on a new branch. All four criteria with real pasted output, the counts
by category, and anything in this brief that was wrong or underspecified — in
particular if the 97/95 split does not match what your parser finds.
