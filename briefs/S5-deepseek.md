# TASK BRIEF — S5: register the 172 unbindable actions

Self-contained. Assume no skill files or plan documents are loaded.

---

## 0. HOW THIS TASK ENDS — read first

Seven of thirteen sessions on this project have failed by **ending their turn
while waiting** for a build. Two more **crashed mid-run and lost everything**
because nothing was on disk yet.

- **Never end your turn waiting.** Poll in a loop until the build finishes.
- **Commit after every owner file.** A crash should cost minutes, not the task.
- **Never report a criterion done without pasting its real output.**

Progress logging, after each meaningful step:

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/s5-progress.log
```

---

## 1. What this does

QElectroTech has a configurable-shortcut system (`ShortcutManager` + a Shortcuts
config page). **An action not registered with it cannot be bound to a key by the
user at all** — it never appears in the page.

Today 95 actions are registered. An audit found **172 more** that are wired to a
slot (they do something) and reachable, but unregistered. This task registers
them.

**Almost all get NO default key.** The point is to make them *bindable*, not to
take 172 keys away from users. Only 5 get a default.

The decisions are already made — read **`SHORTCUTS-S4-DECISIONS.md`** in this
repo. Do not re-decide them.

---

## 2. Branch off the conflict-scoping fix, not master

```bash
git -C /home/user/qet-fix worktree add /tmp/s5-src -b s5-register-actions fix-shortcut-conflict-scope
```

`fix-shortcut-conflict-scope` (upstream PR #759) scopes conflict detection to the
category. **Without it this task makes things worse**: the page already reports
60 of 95 bindings as false conflicts because it compares globally, and adding
172 rows to that is not an improvement.

---

## 3. Generate the calls; do not hand-edit 172 sites

### Step 1 — expose the variable name (small prerequisite)

`tools/actionaudit/actionaudit.py` already computes each action's assignment
target internally (`find_ctor_target`, stored as `target` on the record) but
does **not** emit it. Add it to the JSON output as `target`.

Re-run and confirm the 172 gap records now carry a usable variable name.

### Step 2 — generate

Write `tools/actionaudit/gen_registrations.py` that reads `reports/actions.json`
and emits, for each of the 172, the exact line to insert:

```cpp
ShortcutManager::instance().registerAction(<target>, "<id>", tr("<category>"));
```

- **id**: `<window>.<snake_case_of_variable>` — e.g. `m_add_nomenclature` in
  `QETDiagramEditor` → `diagrameditor.add_nomenclature`. Derive from the
  **variable**, not the French label. Strip a leading `m_`.
- **category**: from §4 of `SHORTCUTS-S4-DECISIONS.md` (owner → category table).
  Reuse the existing `tr()` strings **exactly**; a new near-duplicate string
  creates a duplicate group in the page.
- **placement**: immediately after the construction statement at
  `file`:`line`. For actions from `.ui` files the call must come **after
  `setupUi()`**, not at declaration.
- **5 exceptions**: the actions in §2 of the decisions doc take a
  `QKeySequence::…` default as the 4th argument.

### Step 3 — apply, one owner file per commit

22 owner files. Commit each separately so the change is reviewable; a single
172-line commit is not.

Add `#include "shortcutmanager.h"` where missing.

### Step 4 — optional ergonomics (S5a)

Give `registerAction`'s `default_sequence` parameter a default value of
`QKeySequence()` in `sources/shortcutmanager.h`, so the 167 blank calls can omit
the argument. One line; makes the diff markedly easier to read.

---

## 4. Definition of done — paste real output

### Criterion 1 — the count moves

Re-run `python3 tools/actionaudit/actionaudit.py /home/user/qet-fix --out-dir …`
against your worktree:

```
registerAction_sites:      95  ->  267
gap_connected_unregistered: 176 ->  ~4   (the 4 noise records remain)
```

Paste the before and after summary blocks.

### Criterion 2 — it builds

```bash
cmake -S /tmp/s5-src -B /tmp/s5-build -G Ninja -DCMAKE_BUILD_TYPE=Debug
ninja -C /tmp/s5-build qelectrotech
```

Paste the final lines and the exit code, **measured directly** — `$?` after a
pipe reads the pipe's last command, not the build.

### Criterion 3 — no new conflicts

Run `tools/shortcut-harness/run.sh /tmp/s5-src`. With the scoping fix in place,
adding 167 blank registrations must introduce **zero** new conflicts (blank
sequences never conflict — `checkConflicts()` guards on `!isEmpty()`).

### Criterion 4 — the 5 defaults are right

Show that the five actions in §2 of the decisions doc carry their intended
`QKeySequence` and that none collides with an existing binding **within its
category**.

---

## 5. Traps

1. **Do not invent categories.** Only these exist: `Général`, `Profondeur`,
   `Éditeur de schémas`, `Éditeur d'élément`, `Éditeur de cartouche`,
   `Panneau des éléments`, `Autonumérotation`, `Éditeur de texte`.
2. **French is the `tr()` source language.** Never add English UI strings.
3. **Two ids are already registered twice** (`elementeditor.delete`,
   `elementeditor.quit`) — legal, `ShortcutManager` appends the target. But do
   not *create* new duplicate ids.
4. **`registerAction`'s first argument is a `QObject*`** — one existing call
   registers a `QPushButton`. Do not assume `QAction`.
5. **Build takes ~3 minutes.** Poll it; do not park.
6. Some of the 172 are created by `addAction("text")` rather than
   `new QAction` — those have no variable to reference. If a record has no
   usable `target`, **skip it and list it in your report** rather than
   inventing one. A documented skip is fine; a wrong reference is not.

---

## 6. Scope

**May modify (in your worktree):** the 22 owner `.cpp` files, and
`sources/shortcutmanager.h` for §4 only.
**May create (in this repo):** `tools/actionaudit/gen_registrations.py`, and
`reports/actions.json` may be regenerated.

**Do NOT:** change `checkConflicts()` or the config page; alter
`ShortcutManager`'s behaviour beyond the default argument; touch `simulator/`,
`scenarios/`, `tools/refdiff/`, or any `.md` plan file; push or open a PR.

**Never `git checkout`/`switch`/`stash`/`reset` in `/home/user/qet-fix`'s main
tree** — it holds ~30 uncommitted files on `cabinet-layout-editor`.

---

## 7. Report

All four criteria with real pasted output, the per-owner commit list, every
record you skipped and why, and anything in this brief that was wrong or
underspecified.
