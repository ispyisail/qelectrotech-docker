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

- register with **no** default (bindable, no key taken) — expected to be the
  majority;
- register **with** a default, where the action is frequent and a conventional
  key exists.

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
