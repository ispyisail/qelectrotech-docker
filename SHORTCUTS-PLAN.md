# SHORTCUTS-PLAN.md — action coverage and keyboard shortcuts

Goal as stated: *"shortcut keys for all selectable features"*, plus a tool that
finds every clickable/selectable feature that does something.

**Read §1 before building anything.** The premise the request assumed is only
half true, and the half that is false changes what should be built.

---

## 1. What already exists (measured 2026-08-17, master `7307a59c1`)

QElectroTech **already has a full configurable-shortcut system**, merged via
PR #574:

| Piece | Where |
|---|---|
| `ShortcutManager` singleton registry | `sources/shortcutmanager.{h,cpp}` |
| `registerAction(target, id, category, default_sequence)` | `shortcutmanager.cpp:65` |
| Config UI with `QKeySequenceEdit` + conflict checking | `sources/ui/configpage/shortcutsconfigpage.cpp` |

So "let users bind keys to things" is **done**. Do not rebuild it.

What is *not* done is coverage:

| Measure | Count |
|---|---|
| Actions registered with `ShortcutManager` | **97** |
| `new QAction` constructions in `sources/` | 171 |
| `<action name=` declared in `.ui` files | 56 |
| `.ui` actions carrying a `shortcut` property | **0** |

Registration is concentrated in three files — `qetdiagrameditor.cpp` (32),
`qetelementeditor.cpp` (28), `qettemplateeditor.cpp` (19) — which is 79 of the
97. Dock widgets, context menus, dialogs and the terminal-strip / print /
polygon editors are largely unregistered.

**Roughly 130 action definitions are outside the system**: no default shortcut,
and — more importantly — *not bindable by the user at all*, because the config
page only lists what was registered.

Those counts are crude greps and will overcount: some `new QAction` are
separators, some are dynamic (recent-files entries), some are duplicates across
constructors. Producing the honest number is exactly work item **S1**.

## 2. The reframing

"A shortcut for every selectable feature" is the wrong target, for three
reasons:

1. **The key space runs out.** ~230 actions cannot all have memorable,
   non-conflicting bindings. Forcing it produces `Ctrl+Alt+Shift+K`-class
   bindings nobody uses.
2. **Defaults have a cost.** Every default is a key taken away from the user's
   own binding, and a conflict risk against the platform and against QET's own
   existing 97.
3. **The system is already configurable.** A user who wants a key for a rare
   action can bind it — *provided the action was registered*.

So the deliverable that actually serves the request is:

> **Register every user-triggerable action** so anything can be bound, and
> **assign defaults only where they are earned** by frequency and convention.

### Verified viable against the existing code (2026-08-17)

The approach — *register everything, leave most bindings blank, predefine only
the important ones* — was checked against `ShortcutManager` and the config page
rather than assumed. All four links hold, with **no changes needed** to the
existing system:

| Link | Evidence |
|---|---|
| A blank default can be registered | `registerAction` (`shortcutmanager.cpp:65`) never inspects `default_sequence`; it stores it and calls `setProperty("shortcut", …)`, which with an empty sequence simply sets no shortcut |
| Blank entries still reach the UI | `allShortcuts()` iterates `m_order` unconditionally — no empty-filter |
| They render as bindable rows | `shortcutsconfigpage.cpp:115` builds a `QKeySequenceEdit` per row regardless of whether the sequence is empty; the user types into it |
| **Blank entries do not collide** | `checkConflicts()` guards both the index build and the flag with `!sequence_text.isEmpty()` — so N blank rows produce **zero** false conflicts |

That last one was the real risk: had conflict detection compared sequences
naively, registering ~130 blank actions would have painted the whole config page
red. It does not.

The page also already has a category grouping and a search filter
(`filterRows`), which is what makes a ~230-row table usable — so scale is
handled too.

**One ergonomic change is worth making (S5a):** give `default_sequence` a
default argument of `QKeySequence()` in `shortcutmanager.h:64`, so the ~130 new
call sites read

```cpp
ShortcutManager::instance().registerAction(action, "id", tr("Catégorie"));
```

instead of passing an explicit empty sequence every time. One line in a header,
and it makes the bulk patch markedly easier to review.

That splits cleanly along the model rule in `LAB-PLAN.md`:

> Construction with a mechanical proof fixture → DeepSeek.
> Judgment with no mechanical check → Claude/human.

Registration is mechanical and verifiable. Choosing *which* keys is taste, and
must not be delegated to a model with no way to check itself.

---

## 3. Work items

### S1 — `tools/actionaudit`: enumerate every action (DeepSeek)

A static analyser over `sources/`, no build required, producing one record per
action:

| Field | Meaning |
|---|---|
| `id` | `registerAction` id if present, else `file:line` |
| `text` | the `tr("...")` label |
| `file`, `line` | where it is constructed |
| `registered` | is it passed to `ShortcutManager::registerAction`? |
| `default_sequence` | the sequence given at registration, if any |
| `connected` | is it wired to a slot/signal (**does it do something**)? |
| `kind` | `action` / `separator` / `dynamic` / `checkable` |
| `owner` | the class that constructs it |

Parse `new QAction`, `addAction(`, `registerAction(`, `connect(`, and `<action
name=` in `.ui`. Stdlib only, no build, seconds to run.

**Proof fixtures (must pass before the output is trusted):**
- `mainwindow.fullscreen` (`qetmainwindow.cpp:232`) → `registered=true`,
  `default_sequence="Ctrl+Shift+F"`.
- `depth.raise` (`qet.cpp:789`) → `registered=true`, `Ctrl+Shift+Up`.
- At least one known `.ui` action (`qetelementeditor.ui`) → `registered=false`.
- Total `registered=true` count must equal **97**, the independently grepped
  figure. A different number means the parser is wrong — report it, do not tune
  to match.

**Do not** classify anything as "needs a shortcut". That is S4.

### S2 — runtime action dump (DeepSeek)

Static analysis cannot see which actions are actually *reachable*, nor
menu placement. Add a debug-only dump that walks the live app and writes JSON:
every `QAction` under each top-level window, with `text`, `shortcut`,
`isEnabled`, `isVisible`, and its menu path (`File > Export > ...`).

Run under `-platform offscreen`. Because a modal blocks a headless run
(FINDINGS F008), the dump must be triggered by a CLI flag that fires **after**
the main window is constructed and **without** opening a project.

**Proof fixtures:**
- The dump contains a menu path for a known menu action (`File > New`).
- Every action the dump reports with a non-empty shortcut also appears in S1's
  output with `registered=true`, *or* is a Qt built-in — any third case is a
  finding.

### S3 — cross-check + gap report (DeepSeek)

Join S1 and S2 into `reports/actions.{json,md}`:

- **Gap list**: `connected=true` and `registered=false` — actions that do
  something but cannot be bound. This is the deliverable that answers the
  original request.
- **Conflicts**: one sequence on two actions in the same window.
- **Orphans**: `connected=false` — actions that exist but do nothing. A real
  bug class worth reporting separately.
- **Unreachable**: in S1 but never in S2's dump — dead code, or only reachable
  through a path the dump did not open.

**Proof fixture:** plant a duplicate binding (give two actions `Ctrl+Shift+F`),
confirm the conflict is reported, then remove it. A conflict detector that has
never caught a conflict is unproven.

### S4 — decide the defaults (**Claude / human — not DeepSeek**)

Take S3's gap list and decide, per action:

- register with **no** default (bindable, no key taken) — **the default answer,
  and expected to be the large majority**;
- register **with** a default, where the action is frequent and a conventional
  key exists.

The bar for a default is deliberately high: a predefined key is one the user
cannot get back without going to the config page, so it must earn its place.
Anything where the honest answer is "someone might want this" gets a blank
registration, not a guessed binding.

Rules: never collide with the existing 97 or with platform standards; prefer
`QKeySequence::StandardKey` where one applies; French is the `tr()` source
language, so category strings must match existing ones
(`tr("Général")`, `tr("Profondeur")`, …) or the config page grows duplicate
groups.

This step has **no mechanical proof fixture** — that is precisely why it is not
a DeepSeek item.

### S5 — the patch (DeepSeek, from S4's decided table)

Mechanically apply S4's table: add `registerAction(...)` calls with the agreed
ids, categories and sequences. Split by owning file so each is a reviewable
change; `qetdiagrameditor.cpp` and the terminal-strip editor should not be one
PR.

**Proof fixtures:**
- Re-running S1 shows `registered=true` for every action in S4's table.
- S3 reports **zero** new conflicts.
- The app builds and the config page lists the new entries under existing
  categories, not new near-duplicate ones.

---

## 4. Sequencing and risk

S1 → S2 → S3 can run back to back. S4 gates S5, and S4 is the only step needing
judgment, so the honest critical path is: *build the audit, look at the real
gap list, then decide*. Do not pre-commit to binding all ~130.

Risks worth stating up front:

- **The 130 is not 130.** Expect a large fraction to be separators, dynamic
  entries, or duplicates. S1's real output may show the true gap is far smaller
   — which would be good news, and is why S4 must not start before S1 lands.
- **Upstream appetite is unknown.** A patch registering 100+ actions is a large
  diff against a project whose infra PRs already stall (see PR #661, open 12
  days with no review). Land S1–S3 as harness tooling first, share the gap
  report upstream, and let a maintainer signal appetite before writing S5.
- **`.ui` actions need a different mechanism** — they are constructed by
  `setupUi`, so registration must happen after that call, not at declaration.

## 5. What this does not cover

Mouse-reachable features that are **not** `QAction`s — toolbar widgets, dock
buttons, direct canvas interactions — will not appear in S1 or S2. The
`autonumberingdockwidget.cpp:164` registration shows QET already registers a
`QPushButton` with the manager, so the pattern exists. Enumerating non-action
widgets is a possible S6; it is deliberately out of scope until S1–S3 show
whether the action-level gap alone accounts for what the request was after.

---

## S6 — make ~230 shortcuts findable (browsing + search)

Once S5 lands, the config page holds roughly 230 rows instead of 97. What is
there today (verified 2026-08-17):

| Present | Detail |
|---|---|
| Search box | `QLineEdit`, placeholder *"Filtrer les raccourcis…"*, live on `textChanged` |
| Categories | a **column**, rows sorted by category then action name |
| Per-row reset + reset-all | `QToolButton` per row, `Tout réinitialiser` button |
| Conflict highlight | red background + tooltip naming the other action |

So a search bar already exists. What breaks at 230 rows is **navigation** and
**search quality**.

### S6a — browsing: group instead of sort

Today a category is a repeated cell value in a flat table; finding "everything
under Profondeur" means scrolling. Replace the flat `QTableWidget` with a
**`QTreeWidget`: one collapsible top-level node per category, actions as
children.** Standard pattern (Qt Creator, VS Code), and it turns ~230 rows into
~15 collapsed groups.

Keep the shortcut editor and reset button as item widgets on the child rows —
the existing per-row logic transfers, only the container changes.

### S6b — search: what you would actually type

`filterRows` currently matches a **single substring**, case-insensitively,
against the category and action name only (`shortcutsconfigpage.cpp:140-142`).
Four gaps, each worth fixing:

1. **You cannot search by key.** Typing `Ctrl+S` finds nothing, because the
   sequence column is not searched. This is the single most useful query —
   *"what is already on this key?"* — and it is how a user finds a free binding.
   Match against the current sequence text too.
2. **Multi-keyword.** `export pdf` should match *"Exporter en PDF"* regardless
   of word order. Split the query on whitespace and require **all** terms to
   match somewhere in the row (AND), rather than one substring.
3. **Accent-insensitivity.** French is the `tr()` source language, so labels
   carry accents: `Général`, `Profondeur`, `Réinitialiser`. Typing `general`
   must match `Général`. Normalise both sides (`QString::normalized` +
   diacritic strip) before comparing — without this, an English-keyboard user
   silently gets no hits for the largest category.
4. **Auto-expand + count.** With the tree, a search must expand matching groups
   and report *"N actions matched"*, otherwise matches hide inside collapsed
   nodes and the box looks broken.

### S6c — quick filters

With most actions deliberately registered blank (§2), the useful views are:

- **All** (default)
- **Bound only** — what the user has actually set
- **Unbound only** — the pool of actions available to bind
- **Conflicts only** — reuses the existing `checkConflicts` result

A small combo or segmented control above the tree. *Unbound only* is what makes
the blank-registration design usable: it is how a user browses what is
available to bind rather than scrolling past 130 empty rows.

### Proof fixtures

- Typing `Ctrl+Shift+F` finds `mainwindow.fullscreen`.
- Typing `export pdf` matches *"Exporter en PDF"* (word order differs).
- Typing `general` matches the `Général` category.
- Plant a duplicate binding → *Conflicts only* shows exactly those two rows;
  remove it → the view is empty.
- With every action registered, *Unbound only* count + *Bound only* count equals
  the total row count.

### Model

**DeepSeek**, with one caveat: every fixture above is mechanical, but this is
GUI code and the fixtures need a running widget. Either drive it through a small
`QTest`-style harness, or verify by launching the config page under
`-platform offscreen` and dumping the visible row set. Decide that before
starting — a GUI item with no way to check itself is the one shape that
reliably fails.

### Sequencing

S6 is independent of S4/S5 and can be built first. Doing so is arguably better:
it makes the 97 existing shortcuts easier to browse immediately, and it means
the ~130 new ones arrive into a page that can already cope with them.
