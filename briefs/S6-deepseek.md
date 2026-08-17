# TASK BRIEF — S6: make QElectroTech's shortcut list browsable and searchable

Self-contained. Assume no skill files or plan documents are loaded.

---

## 0. HOW THIS TASK ENDS — read first

Seven of ten sessions on this project have failed the same way: they did the
work, then **ended their turn announcing they would wait** for a build or a
background command. That is the one way to fail this brief.

- **Never end your turn while waiting.** Poll in a loop — sleep, re-check,
  continue — until the thing finishes.
- **Never report a criterion done without pasting its real output.**
- If something genuinely cannot finish, say so and stop. "Criterion 3 blocked
  because X" is a good outcome. Silence while waiting is not.

---

## 1. Context

QElectroTech **already has** a configurable-shortcut system (merged upstream as
PR #574):

| Piece | Where (in the QET source tree) |
|---|---|
| `ShortcutManager` registry | `sources/shortcutmanager.{h,cpp}` |
| Config page UI | `sources/ui/configpage/shortcutsconfigpage.{h,cpp}` |

Today it holds **97** registered actions. A separate work item will register
roughly **130 more**, most deliberately with a **blank** default so users can
bind them but no key is taken by default. The page must cope with ~230 rows.

**Your job is only the browsing and search experience.** Do not register new
actions, and do not change `ShortcutManager`'s API.

### What the page has today

- A `QLineEdit` filter (placeholder *"Filtrer les raccourcis…"*), live on
  `textChanged` → `filterRows()`
- A flat 4-column `QTableWidget`: Catégorie | Action | Raccourci | reset button
- Rows sorted by category, then action name
- Per-row reset, "Tout réinitialiser", and `checkConflicts()` which highlights
  duplicate non-empty sequences

So a search box exists. It is the *quality* of search and the *flatness* of the
table that break at 230 rows.

---

## 2. Your verification harness — use it, it already exists

`tools/shortcut-harness/run.sh` in this repo compiles the **real**
`shortcutmanager.cpp` and `shortcutsconfigpage.cpp` standalone against Qt5,
runs them under `QT_QPA_PLATFORM=offscreen`, types into the actual filter box
and counts visible rows. **No QElectroTech build is required** and it takes
seconds.

```bash
tools/shortcut-harness/run.sh                 # defaults to /home/user/qet-fix
tools/shortcut-harness/run.sh /path/to/src    # a worktree you created
```

Baseline on current master:

```
total rows: 4  visible: 4
  query 'Ctrl+S'      ->   0 visible   [search by key sequence]
  query 'export pdf'  ->   0 visible   [multi-keyword, different word order]
  query 'general'     ->   0 visible   [accent-insensitive]
  query 'Profondeur'  ->   1 visible   [plain category match -- control]
```

Extend `tools/shortcut-harness/harness.cpp` as you add features. Keep the
control probe: it is what proves a zero is a real miss rather than a broken
harness.

**A probe that cannot fail proves nothing.** The accent check originally looked
like it passed because the harness registered the category unaccented
(`"General"` rather than `"Général"`). Check that each new probe actually fails
before your fix and passes after.

---

## 3. What to build

### S6a — group instead of sort

Replace the flat `QTableWidget` with a **`QTreeWidget`**: one collapsible
top-level node per category, actions as children. ~230 rows becomes ~15
collapsed groups.

The `QKeySequenceEdit` and reset `QToolButton` stay as item widgets on the child
rows — the existing per-row logic transfers; only the container changes.
`checkConflicts()`, `resetRow()`, `resetAllRows()` and the persistence path must
keep working.

### S6b — four search fixes

`filterRows()` (`shortcutsconfigpage.cpp:136`) currently matches **one
substring**, case-insensitively, against the category and action name only.

1. **Search by key.** Include the row's current sequence text, so `Ctrl+S`
   finds what is bound to it. This is the most useful query on the page — it is
   how a user finds a free key — and it is how conflicts get noticed.
2. **Multi-keyword.** Split the query on whitespace, require **all** terms to
   match somewhere in the row. `export pdf` must match *"Exporter en PDF"*.
3. **Accent-insensitive.** French is the `tr()` source language, so labels are
   `Général`, `Profondeur`, `Réinitialiser`. Typing `general` must match
   `Général`. Normalise both sides — `QString::normalized(QString::NormalizationForm_D)`
   then strip combining marks (`QChar::Mark_NonSpacing`) — and compare
   case-insensitively. Without this an English-keyboard user gets **no hits**
   for the largest category and concludes search is broken.
4. **Auto-expand + count.** A search must expand matching groups (otherwise
   matches hide inside collapsed nodes and the box looks broken) and show
   *"N actions"* somewhere visible.

### S6c — quick filters

A combo or segmented control above the tree: **All** (default) / **Bound only**
/ **Unbound only** / **Conflicts only**.

*Unbound only* is the important one: with most actions registered blank, it is
how a user browses what is available to bind instead of scrolling past 130 empty
rows. *Conflicts only* should reuse the existing `checkConflicts()` result
rather than recomputing.

Filters and the text query **combine** (AND), they do not replace each other.

---

## 4. Definition of done — paste real output for each

### Criterion 1 — the three search gaps close

Harness output must show non-zero for all three, with the control unchanged:

| Query | Before | Required after |
|---|---|---|
| `Ctrl+S` | 0 | ≥1 |
| `export pdf` | 0 | ≥1 |
| `general` | 0 | ≥1 |
| `Profondeur` | 1 | ≥1 (control — must not regress) |

### Criterion 2 — the tree groups correctly

Add a harness probe: register actions across ≥3 categories and assert the tree
has one top-level node per distinct category, with the right child counts.

### Criterion 3 — quick filters partition the set

With a mix of bound and blank registrations:
`count(Bound only) + count(Unbound only) == total rows`, and *Conflicts only*
shows exactly a deliberately planted duplicate pair — then nothing once removed.
**A conflict filter that has never caught a conflict is unproven.**

### Criterion 4 — nothing existing broke

Per-row reset, "Tout réinitialiser", conflict highlighting and persistence must
still work. Show a harness probe for reset and for conflict highlighting.

---

## 5. Traps

1. **Blank sequences must never count as conflicts.** `checkConflicts()` guards
   on `!sequence_text.isEmpty()` in both the index build and the flag — preserve
   that. With ~130 blank rows, losing the guard paints the entire page red.
2. **`filterRows()` currently indexes columns by number** (`item(row,0)`,
   `item(row,1)`). Moving to a tree changes that; do not leave a stale
   column-index assumption behind.
3. **Do not touch `ShortcutManager`'s API.** Another work item depends on
   `registerAction`'s current signature.
4. **French is the source language.** Any new user-visible string must be
   wrapped in `tr()` and written in French, matching surrounding style
   (`tr("Filtrer les raccourcis…")`). Do not introduce English UI text.
5. **Category strings are matched literally** for grouping — do not "tidy" the
   existing `tr("Général")` / `tr("Profondeur")` values, or groups will split.

---

## 6. Environment

| Thing | Value |
|---|---|
| QET source | `/home/user/qet-fix` |
| Harness | `tools/shortcut-harness/run.sh` (this repo) |
| Full build, only if you need one | `scripts/qet-fastbuild.sh` in the QET tree (~1.7 s incremental) |

**Never `git checkout`, `switch`, `stash` or `reset` in `/home/user/qet-fix`'s
main tree** — it holds ~30 uncommitted files on branch `cabinet-layout-editor`
that are not yours. Create your own worktree:

```bash
git -C /home/user/qet-fix worktree add /tmp/s6-src -b s6-shortcut-browsing master
tools/shortcut-harness/run.sh /tmp/s6-src
```

Remove the worktree when you are done.

---

## 7. Scope

**May modify:** `sources/ui/configpage/shortcutsconfigpage.{h,cpp}` in your
worktree, and `tools/shortcut-harness/harness.cpp` in this repo.

**Do NOT:** change `ShortcutManager`; register new actions; touch any other QET
source file; modify `simulator/`, `scenarios/`, `tools/refdiff/`, `tests/`, or
any `.md` plan file; push, open a PR, or post anywhere.

Commit on a new branch in each repo.

---

## 8. Report

All four criteria with **real pasted harness output**, the before/after table,
what you changed in `harness.cpp` and why, and anything in this brief that was
wrong or underspecified — say so plainly rather than working around it.
