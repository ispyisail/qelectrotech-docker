# RFC: A scripting / automation layer for QElectroTech

**Status:** Draft for discussion — no code written, nothing committed to.
**Scope:** Proposal and staged plan. I'm looking for direction before building anything.

---

## Summary

QET already contains four separate user-facing mini-languages, one of which is full SQL
with a GUI builder in front of it. This RFC proposes to stop growing them independently
and instead generalise the pattern that `ProjectDBModel` already established: **a friendly
builder UI over a stable text representation, backed by one documented object model.**

The proposal is deliberately staged so that the first step is useful on its own and small
enough to review, and each later step is optional.

I am not proposing to "add a scripting language" as a single feature. That framing is what
usually kills this kind of work in a project with limited maintainer time.

---

## Motivation

Comparable tools in adjacent industries all ship automation of some kind — SolidWorks (VBA
/ COM), BarTender, Excel, PeakHMI, EPLAN. The recurring requests they serve are the same
ones that show up for electrical CAD:

- Bulk renumbering and re-labelling across folios
- Generating repeated circuits (e.g. 40 near-identical motor starters) from a CSV or ERP export
- Custom nomenclature / BOM output beyond what is compiled in
- Design rule checks — unconnected terminals, duplicate labels, conductor gauge vs. protective
  device rating, terminal strip consistency
- Batch operations over element libraries
- Parametric elements, where terminal count or geometry derives from parameters

Today each of these either requires a C++ patch or is done by hand.

---

## What QET already has

This is the part I think is under-appreciated, and it's why I'm proposing evolution rather
than a new subsystem.

### Four existing languages

| Where | Form | Reference |
|---|---|---|
| Element info in dynamic texts | `%{label}`, `%{void}` | `sources/qetinformation.cpp:57-65,214-219` |
| Title block fields | `%var` and `%{var}` | `sources/titleblock/titleblocktemplate.cpp:1730,1743` |
| Auto-numbering | prefix / sequence / folio composition | `sources/autoNum/assignvariables.cpp` |
| Project reports | **arbitrary SQL** | `sources/qetgraphicsitem/ViewItem/projectdbmodel.h:65-66,82` |

The first three are string substitution with no arithmetic and no conditionals. They have
overlapping but non-identical syntax and separate implementations.

### The fourth one is the interesting one

`ProjectDBModel` is a diagram item whose persisted state is a SQL string (`m_query`,
`setQuery()`), run against the project database. Users configure it through
`ElementQueryWidget` / `SummaryQueryWidget` (`sources/dataBase/ui/`), which:

- **generate** SQL from column checkboxes and filter dropdowns
  (`elementquerywidget.cpp:285-331`), and
- **parse it back** into UI state when reloading (`elementquerywidget.cpp:120`, with the
  filter forms recovered by regex at `:243-273`).

So QET has already answered the hardest design question in this space — *how do you give
non-programmers real query power without making them write code?* — and the answer it chose
is a builder UI over a text representation. That pattern is what I want to extend.

(One caveat worth stating: because the reverse parse is regex-based, it only understands the
subset the builder itself emits. Hand-written SQL likely won't survive an edit round-trip.
That's a known limitation of the current design, not a criticism of it.)

### The project database

`projectDataBase` (`sources/dataBase/projectdatabase.cpp:250`) builds an in-memory SQLite
representation of the project. Schema (`:264-303`):

- Tables: `diagram`, `element`, `diagram_info`, `element_info`
- Views: `element_nomenclature_view` (`:333`), `project_summary_view` (`:416`)
- Public query entry point: `projectDataBase::newQuery()`

**Two important limits.** There is no conductor table and no terminal table — so wiring-
and connectivity-based rules are not reachable from the DB today. And the DB is not live:
`updateDB()` (`:84`) fully repopulates, and is only called from four places
(`qetproject.cpp:1438`, `bomexportdialog.cpp:102`, `projectdbmodel.cpp:200`,
`projectdbmodelpropertieswidget.cpp:104`).

I flag this because it directly bounds what's cheap: **reporting and BOM work is close;
design rule checking is not.** Any claim that DRC is nearly free is wrong.

---

## Proposal

### Phase 0 — Unify and extend the expression language

Merge the three substitution syntaxes behind one documented evaluator, and add what's
actually missing: arithmetic, conditionals, and a small string/format function library.

```
IF(gauge < 2.5, "UNDERSIZED", "")
%{manufacturer} & " " & UPPER(%{reference})
```

No engine, no new dependency. For a large share of real use cases — title blocks, labels,
conditional text, numbering — this is the entire feature. It is also the piece that best
matches "easy to use" for the typical QET user.

Backwards compatibility is a hard requirement: existing `%{...}` and `%var` content must
continue to evaluate identically.

### Phase 1 — Read-only scripting

A script runner exposing a **read-only** project object model. No mutators at all.

This unlocks custom exports, BOM variants, reports, and non-destructive checks, with no risk
of document corruption and no undo-stack concerns — so review can focus purely on API shape.

### Phase 2 — Mutating API, plus a recorder

Mutation goes through the existing undo commands (44 direct `QUndoCommand` subclasses across
26 headers today), with each script run wrapped in a single undo macro. That count is also a
fair estimate of the facade's size — it is not a small phase.

Alongside it — and I'd argue *as part of it, not after* — a **macro recorder**. Recording
user actions and emitting the equivalent script is how people actually learn this kind of
API in SolidWorks and Excel; almost nobody starts from a blank file. Because mutations
already funnel through `QUndoCommand`, serialising the undo stack into script calls is
tractable rather than speculative.

This is also the phase where the `ProjectDBModel` precedent applies most directly: ship the
builder UI with the language, not later.

### Phase 3 — Headless mode

`qelectrotech --script foo.js project.qet`, for batch and CI use.

Note this is genuinely new ground: QET currently builds a single executable
(`CMakeLists.txt:85,94`), and `qet_elementscaler` — despite its origin as a standalone tool
— is compiled into it and invoked from the element editor (`qetelementeditor.cpp:1521`),
not from a command line. `QETArguments` (`sources/qetarguments.h`) is the natural place to
hang the option.

### Phase 4 (optional) — External Python

Rather than embedding CPython, document the project DB schema and let Phase 3 export it.
Python users then script QET with the stdlib `sqlite3` module and pandas/openpyxl, with
**zero new dependency for QET and no change to any packaging pipeline**. This serves the
audience that most wants automation without paying the cost that would sink the feature.

---

## Engine choice

Recommendation: **`QJSEngine`**.

| | Dependency cost | Qt5 + Qt6 | Binding effort |
|---|---|---|---|
| **QJSEngine (JS)** | `QT += qml`, stock Qt module | yes | near-zero via moc |
| Lua + sol2 | vendored, ~250 KB | n/a | manual, per class |
| QuickJS | vendored, ~1 MB | n/a | manual, per class |
| Embedded Python | interpreter + stdlib in 4 pipelines | yes | moderate |
| QtScript | — | **no** (removed in Qt6) | — |

Reasoning:

- **QET builds against both Qt5 and Qt6** (`CMakeLists.txt:55-67`), which eliminates QtScript
  outright.
- **Binding cost dominates.** QET is QObject-dense; `QJSEngine::newQObject()` exposes
  `Q_PROPERTY` / `Q_INVOKABLE` automatically. With Lua or QuickJS, every exposed class needs
  a hand-written binding maintained forever — the tax that most often stalls this work.
- **Packaging is the real constraint.** `QT += qml` is a new module for QET (current
  components: `qet_compilation_vars.cmake:19-27`, `qelectrotech.pro:233`) but it ships with
  Qt everywhere and needs no change to the AppImage / aarch64 / Debian-Ubuntu-Windows /
  Flatpak scripts. Embedding CPython would require work in all four, indefinitely.
- **One engine serves Phases 0 and 1**, if the expression evaluator runs in a locked-down
  context with no globals and no I/O.

Lua is the strongest counter-argument on pure readability — smaller syntax, 1-based indexing
that matches how engineers count terminals and folios. I'd still favour QJSEngine on
maintenance cost, but I'd like to hear if others weigh that differently.

---

## Design principles

1. **A language-agnostic C++ facade.** Scripts talk to a dedicated API layer, not to
   `Diagram*` / `Element*` directly. This keeps QET's internals free to change, and leaves
   room for a second front-end (Lua, visual, Python) without a redesign. This is the least
   reversible decision here and matters more than the engine choice.
2. **All mutation through `QUndoCommand`**, one macro per script run. A script that bypasses
   undo corrupts the editor silently.
3. **GUI thread only.** Recent work in this area (#514 thread-unsafe `QStandardPaths`, #515
   `MachineInfo` initialisation and main-thread pre-init ordering, #516 thread-safe
   `setUpData()`) suggests cross-thread access is an area where QET has had to be careful.
   Scripting should not add a new source of it.
4. **Versioned API** from the first commit.
5. **Builder UI is part of the feature**, following `ProjectDBModel`.

---

## Security

Scripts embedded in `.qet` files would mean arbitrary code execution on open, and project
files are routinely emailed between contractors.

Proposal: **user-directory scripts only, explicit invocation, never auto-run.** Project-
embedded scripts should be a separate, later discussion with its own threat model, if ever.

---

## Non-goals

- A plugin system for third-party UI extensions
- Replacing existing `%{...}` syntax (extension only, no breakage)
- Embedding CPython
- A visual / node-based editor — real precedent exists (Grasshopper, Node-RED) and it is the
  genuinely easiest option for non-programmers, but the implementation cost is not realistic
  for this project's maintainer capacity

---

## Open questions

1. Is Phase 0 alone worth doing regardless of whether scripting ever lands? I think yes.
2. Is there appetite for the `qml` module dependency, or is avoiding it worth the ongoing
   binding cost of Lua/QuickJS?
3. Should conductor and terminal tables be added to the project DB independently of this?
   They'd benefit BOM/reporting on their own and are the prerequisite for any wiring-aware
   rule checking.
4. Is the non-live `updateDB()` refresh acceptable for scripting, or does it need an
   incremental path first? Full repopulation per script call may not scale on large projects.
5. Does the regex round-trip limitation in `ElementQueryWidget` need addressing before more
   weight is put on that pattern?

---

## What I'm asking for

Direction on whether Phase 0 is welcome as a standalone contribution, and whether the
overall staging looks sensible, before any implementation work starts.

Happy to be told the answer is "not now" — I'd rather know before writing code than after.
