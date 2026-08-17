# S4 — which actions get a default key

Input: `reports/actions.json` (S1). Gap = **176** actions that are connected but
unregistered; **172** after removing 4 noise records (an icon path misparsed as
text, two null-text records, and one in `diagramselection`, which is dead code —
upstream issue #756).

> **Ref correction (2026-08-17).** The 176/172 figures here were measured on
> `/home/user/qet-fix`, which is checked out on the `cabinet-layout-editor`
> feature branch. Against `master` the gap is **171**, of which 166 were
> registrable and 5 skipped — those are the numbers S5 actually applied. The
> decisions (5 defaults, everything else blank) are unaffected; only the counts
> shift. See `reports/orphan-analysis.md` for how this surfaced.

This is the judgment step. It has no mechanical proof fixture, which is why it
was not delegated.

---

## 0. BLOCKER — fix conflict scoping before registering anything

**60 of the 95 currently registered rows would display as conflicts today.**

`ShortcutManager` ids are per-window, and QET deliberately reuses one key across
editors — the same sequence is registered three times, once each for the
diagram, element and titleblock editors:

| Sequence | Registered on |
|---|---|
| `QKeySequence::Undo` | 3 ids |
| `QKeySequence::Redo` | 3 ids |
| `QKeySequence::New` | 3 ids |
| `QKeySequence::Open` | 3 ids |
| `QKeySequence::Save` | 3 ids |
| `Qt::CTRL \| Qt::SHIFT \| Qt::Key_S` | 3 ids (`elementeditor.save_as_file`, `diagrameditor.save_file_as`, `titleblockeditor.save_as_file`) |

23 sequences are shared by more than one action, covering 60 rows.

But `ShortcutsConfigPage::checkConflicts()` builds one global
`QHash<QString, QList<int>>` of sequence → rows and flags every sequence used by
more than one row. It has **no notion of window scope**. So opening
Preferences → Shortcuts on a stock build should already show ~60 of 95 rows
highlighted red, each with a *"Ce raccourci est aussi utilisé par…"* tooltip,
for bindings that are entirely correct.

**Consequence for this work item:** the rule "never collide with the existing
95" is *wrong* — cross-window reuse is the established convention here.
Applying it would force artificial keys onto actions that should share.

**Do this first:** give each registry entry a scope (the window/class that owns
it) and have `checkConflicts()` compare only within a scope. Until then, adding
172 rows makes an already-noisy page worse.

This is a defect in shipped QElectroTech, not in the plan. Worth filing
separately — it is user-visible on any build with the Shortcuts page.

---

## 1. Decision rules

1. **Blank is the default answer.** A predefined key is one the user cannot
   reclaim without visiting the config page, so it must be earned.
2. A default requires **both** high frequency **and** a conventional key.
   "Someone might want this" is a blank registration.
3. Prefer an unused `QKeySequence::StandardKey` over an invented chord.
4. Never invent bare single-letter shortcuts: QET's editors have focused text
   inputs (`QLineEdit`, property docks) that legitimately consume plain letters.
5. Categories must reuse existing `tr()` strings — `Général`, `Profondeur`,
   `Éditeur de schémas`, `Éditeur d'élément`, `Éditeur de cartouche`,
   `Panneau des éléments`, `Autonumérotation`, `Éditeur de texte` — or the
   config page grows near-duplicate groups.

## 2. Defaults to assign — 5 of 172

Every one uses a `StandardKey` that is **currently unused** anywhere in QET, so
none collide even under today's global checker.

| Action | Owner | id | Default |
|---|---|---|---|
| `&Configurer QElectroTech` | QETMainWindow | `mainwindow.configure` | `QKeySequence::Preferences` |
| `Première page` | ProjectPrintWindow | `printwindow.first_page` | `QKeySequence::MoveToStartOfDocument` |
| `Page précédente` | ProjectPrintWindow | `printwindow.previous_page` | `QKeySequence::MoveToPreviousPage` |
| `Page suivante` | ProjectPrintWindow | `printwindow.next_page` | `QKeySequence::MoveToNextPage` |
| `Dernière page` | ProjectPrintWindow | `printwindow.last_page` | `QKeySequence::MoveToEndOfDocument` |

Rationale: Preferences is the single most conventional unbound action in the
app. The print-preview navigation is a closed, transient window where PageUp /
PageDown / Ctrl+Home / Ctrl+End carry no ambiguity and match every other
document viewer.

## 3. Everything else — 167 blank registrations

Registered so users **can** bind them; no key taken. Grouped by owner:

| Owner | Count | Note |
|---|---|---|
| QETDiagramEditor | 37 | mostly project/folio operations and view toggles |
| QETElementEditor | 21 | includes the drawing tools — see below |
| ProjectPrintWindow | 10 | the remainder after the 4 above |
| ElementsPanelWidget | 13 | context-menu items |
| ElementsCollectionWidget | 12 | context-menu items |
| QETApp | 11 | tray/window show-hide |
| QETMainWindow | 7 | remainder after Preferences |
| RichTextEditorToolBar | 9 | **English strings in a French UI — see §5** |
| TitleBlockTemplateView | 9 | grid row/column editing |
| MasterPropertiesWidget | 6 | link/unlink |
| ProjectView | 5 | folio navigation |
| DiagramView | 4 | context menu, incl. `Coller ici` |
| LinkSingleElementWidget | 4 | |
| others (9 owners) | 19 | 1–3 each |

### The drawing tools deserve a comment

`Ajouter une ligne / un rectangle / une ellipse / un polygone / du texte / un arc
/ une borne` are the highest-frequency unbound family in the app, and a prior
menu audit (upstream #677) already flagged them as toolbar-only. Drawing
applications conventionally bind these to bare letters (L, R, E, T).

**They still get blank registrations**, per rule 4: the element editor has
focused text inputs, and a bare `T` while a property field has focus is
ambiguous at best. This is exactly the case the blank-registration design
serves — a user who draws all day can bind `L`/`R`/`E`/`T` themselves in
seconds, and accepts the consequence knowingly. We should not make that choice
for everyone.

## 4. Id and category conventions

Ids follow the existing `<window>.<action>` pattern (`diagrameditor.print`,
`elementeditor.zoom_in`). Two existing ids are registered twice
(`elementeditor.delete`, `elementeditor.quit`) — that is legal, `ShortcutManager`
appends the target — but new ids must not reuse an existing string unless the
sharing is deliberate.

Category per owner:

| Owner | Category |
|---|---|
| QETDiagramEditor, DiagramView, ProjectView, SearchAndReplaceWidget | `Éditeur de schémas` |
| QETElementEditor, PolygonEditor, PartPolygon, QetShapeItem, ElementPropertiesEditorWidget | `Éditeur d'élément` |
| QETTitleBlockTemplateEditor, TitleBlockTemplateView, TitleBlockPropertiesWidget | `Éditeur de cartouche` |
| ElementsPanelWidget, ElementsCollectionWidget | `Panneau des éléments` |
| RichTextEditorToolBar | `Éditeur de texte` |
| QETApp, QETMainWindow, ProjectPrintWindow, TerminalStripEditorWindow, MasterPropertiesWidget, LinkSingleElementWidget, plclinkwidget | `Général` |

## 5. Two side findings worth acting on separately

1. **`RichTextEditorToolBar` ships English strings in a French-source UI** —
   `Insert &Image`, `Left Align`, `Center`, `Right Align`, `Justify`,
   `Superscript`, `Subscript`, `Simplify Rich Text`. French is the `tr()` source
   language everywhere else. These are untranslated, not merely unbound.
2. **`Télécharger une nouvelle version (dev)` appears twice** in QETMainWindow —
   possibly a duplicated action.

Neither is a shortcut problem; both are separate small fixes.

## 6. What S5 does with this

Apply §2 (5 defaults) and §3 (167 blanks) mechanically, using §4's ids and
categories. **Gate S5 on §0** — registering 172 rows into a page that already
mis-reports 60 conflicts produces something worse than what exists today.
