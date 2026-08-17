# S3 — orphan analysis: static actions absent from the runtime dump

Joins `reports/actions.json` (static, 320 records) against
`reports/actions-runtime.json` (runtime, 260 actions across 3 windows).
Matching is by normalised label (`&` stripped, whitespace collapsed, lowercased).

## Result

| | Count |
|---|---|
| Static records that are real actions (`kind` = action/checkable, has text) | 267 |
| Matched in the runtime dump | 196 |
| **Not found at runtime** | **71** |
| — explained: owner window never constructed by the dump | 67 |
| — **candidates worth investigating** (owner window *was* dumped) | **4** |
| **Confirmed orphans** | **0** |

## The 67 expected absences

The dump constructs only `QETDiagramEditor`, `QETElementEditor` and
`QETTitleBlockTemplateEditor`. Anything owned elsewhere cannot appear:

| Owner | Count | Why absent |
|---|---|---|
| ProjectPrintWindow | 12 | separate window, built only when printing |
| RichTextEditorToolBar | 12 | toolbar inside a rich-text dialog |
| QETApp | 10 | tray / application menu, not a window menu |
| MasterPropertiesWidget | 6 | dialog widget |
| DiagramView | 4 | **context menu**, built on demand (`Coller ici`, …) |
| ProjectView | 4 | dock/tab context actions |
| LinkSingleElementWidget | 4 | dialog widget |
| others | 15 | dialogs, shape context menus, terminal-strip window |

These are **not** findings. A context-menu action is perfectly reachable; it
simply does not exist until the user right-clicks.

## The 4 candidates, resolved

1. **`:/ico/22x22/guides.png`** — not an action. The static parser took an icon
   path as a label. A known `actionaudit` misparse; already excluded from the
   S4 gap count.
2. **`Pivoter le groupe`** — present at runtime as **`Pivoter`**. The label is
   rewritten depending on the selection, so exact-text matching missed it. A
   matching artifact, not an orphan.
3. **`Exporter la base de donnée interne du projet`** — guarded by
   `#ifdef QET_EXPORT_PROJECT_DB` (`qetdiagrameditor.cpp:549`, and again around
   its menu insertion at :941). Not defined in a default build, so correctly
   absent. **Static analysis cannot see preprocessor conditionals** — worth
   remembering before trusting any static count.
4. **`Coupure automatique de conducteur(s)`** — **unexplained.** See below.

## RESOLVED 2026-08-17: the open question was a branch mismatch, not a defect

The "unexplained" entry below is explained, and the explanation is a flaw in
this analysis rather than in QElectroTech or in the dump.

**`m_auto_break_conductor` does not exist on `master`.** It is part of the
`cabinet-layout-editor` feature branch — 9 occurrences there, **0 on master**.

The static audit was run against `/home/user/qet-fix`, whose working tree is
checked out on `cabinet-layout-editor`. The runtime dump was built from a
worktree branched off `master`. So this compared a scan of one branch against a
dump of another, and the only surprise is that just one action differed.

Instrumenting the dump proved the action genuinely does not exist at runtime:
the `diagram` toolbar reports 3 actions (not 4), and a `findChildren<QAction*>`
sweep logging every action containing "oupure" printed nothing. Neither the
toolbar walk nor the sweep was at fault.

**Correction to the numbers above.** The static side of this analysis was
measured on `cabinet-layout-editor`:

| Audit target | total actions | registerAction sites | gap |
|---|---|---|---|
| `cabinet-layout-editor` (what was scanned) | 320 | 97 | 176 |
| `master` (what the dump ran) | 312 | 96 | 171 |

The 8-action difference is the feature branch's own work. The conclusion —
**no confirmed orphan actions** — is unaffected, and is now stronger: the last
outstanding candidate is accounted for.

**Method rule this establishes:** pin the ref. An audit of "the source tree" is
meaningless when that tree sits on a feature branch; both sides of a
static/runtime comparison must name the same commit.

The S5 session avoided this without being told: it re-derived its own baseline
(gap 171) from its own master-based worktree instead of trusting the 176 in its
brief.

## Original open question (now resolved above)

`m_auto_break_conductor` (`qetdiagrameditor.cpp:397`) is:

- constructed unconditionally, parented to the window (`new QAction(..., this)`),
- added unconditionally to the diagram toolbar (`:854`),
- never removed; only enabled/disabled (`:1955`–`:1961`),
- not behind any `#ifdef`.

Yet no action with that text appears anywhere in the dump, while its immediate
toolbar neighbour `Création automatique de conducteur(s)` (`:853`) does, tagged
`toolbar: diagram`. The `diagram` toolbar reports **3** actions at runtime where
the source adds **4**.

Ruled out: conditional compilation, later removal, the toolbar not being walked,
and a changed label (no dump entry contains "oupure", and only two actions
contain "automatique").

The dump collects into a `QHash<QAction *, Record>` from menus, then toolbars,
then a `findChildren<QAction *>` sweep — an action parented to the window should
be caught by the sweep even if both earlier passes missed it.

**This is recorded as a discrepancy, not a bug in either component.** It is
either a gap in the dump or something at runtime that the source reading does
not predict. Resolving it needs instrumentation (log every action the sweep
sees) rather than more static reading.

## What this says about the action inventory

**No confirmed orphan actions in the three main editors.** Every static action
whose window was actually constructed is either present at runtime or explained.
The dead code found earlier (upstream #756, `diagramselection`) was dead at the
*class* level — an entire widget never instantiated — not at the action level.

## Method notes for anyone repeating this

- **Match on more than the label.** Labels are rewritten at runtime
  (`Pivoter le groupe` → `Pivoter`); an exact-text join reports false orphans.
- **`#ifdef` is invisible to the static pass**, so it will always list actions a
  default build does not contain.
- **Scope the comparison to windows the dump actually constructed.** Comparing
  all 320 static records against 260 runtime records yields a 60-action
  "discrepancy" that is almost entirely an artifact of which windows were open.
