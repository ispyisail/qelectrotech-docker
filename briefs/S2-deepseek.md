# TASK BRIEF — S2: dump every action the running application actually has

Self-contained. Assume no skill files or plan documents are loaded.

---

## 0. HOW THIS TASK ENDS — read first

Seven of twelve sessions on this project have failed the same way: they did the
work, then **ended their turn announcing they would wait** for a build. This
task involves a ~3 minute QElectroTech build, so you will be tempted.

- **Never end your turn while waiting.** Poll in a loop — sleep, re-check,
  continue — until the build or command finishes.
- **Never report a criterion done without pasting its real output.**
- Two sessions have also **crashed mid-run and lost everything** because they
  had written nothing to disk. **Commit early and often**, even when incomplete.

**Progress logging.** After each meaningful step append one line:

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/s2-progress.log
```

---

## 1. What this is for

A static audit (`tools/actionaudit`, already built) found **320 actions** in the
QElectroTech source, of which only 95 are registered with `ShortcutManager` and
therefore bindable by the user. Static analysis cannot tell:

- which actions are actually **reachable** in a running app,
- where each one **sits in the menus** (`Fichier > Exporter > …`),
- which are created **dynamically** and never appear in source as a literal.

S2 produces the runtime ground truth. S3 (a later task) joins it against the
static list.

---

## 2. What to build

A debug-only CLI flag in QElectroTech: `--dump-actions <output.json>`.

It must **not** be proposed upstream — this is a local analysis tool. Work on a
branch and say so in the commit message.

### Where to hook it

`sources/main.cpp:128-140` already has exactly the right precedent —
`CLIExport`, a headless subcommand handled **before SingleApplication is
constructed**:

```cpp
if (CLIExport::isExportRequest(raw_args)) {
    QApplication export_app(argc, argv);
    QETProject::setBackupEnabled(false);
    return CLIExport::run(export_app.arguments());
}
```

Model the dump on this and place it in the same block. **The comment there
explains why it must come first: SingleApplication forwards arguments to an
already-running instance**, so a flag handled later would be silently sent to
another process and produce nothing.

### What to walk

For each top-level window: recurse `menuBar()` to build a menu path per action
(`Fichier > Exporter > Exporter en PDF`), walk `QToolBar`s, then sweep
`findChildren<QAction*>()` to catch anything not in either.

Per action record: `text`, `objectName`, `shortcut` (as
`QKeySequence::toString()`), `enabled`, `visible`, `menu_path`, `toolbar`,
and the owning window's class name (`metaObject()->className()`).

### The part that is easy to get wrong

**Only the diagram editor exists at startup.** `QETElementEditor` and
`QETTitleBlockTemplateEditor` are separate `QMainWindow` classes constructed on
demand. A dump that only walks what exists after launch will miss roughly
two-thirds of the application, and will look plausible while doing so.

Construct one of each editor before dumping, and record which window each
action came from. If constructing one proves impractical headlessly, **say so
explicitly and report which windows are covered** — a documented gap is fine, a
silent one is not.

### Never open a project

A project file must not be loaded. `examples/schema_indus.qet` is version 0.3
and raises a modal during load that no offscreen process can dismiss — the
process then hangs forever (upstream issue #661). The dump exists to inspect
menus, not documents.

---

## 3. Definition of done — paste real output

### Criterion 1 — it runs headless and exits

```bash
qelectrotech -platform offscreen --dump-actions /tmp/actions-runtime.json
```

Exits **0 within 60 seconds**, writes the file. Paste the command, the exit
code (measured directly, **not** through a pipeline — `$?` after a pipe reads
the last command in the pipe) and the file size.

### Criterion 2 — menu paths are real

Show at least three actions with a non-trivial `menu_path`, including one
nested two levels deep. Paste them.

### Criterion 3 — all three editors are covered

Report the action count per window class. `QETDiagramEditor`,
`QETElementEditor` and `QETTitleBlockTemplateEditor` must each contribute
**≥ 1** action, or you must state plainly which is missing and why.

### Criterion 4 — cross-check against the static audit

`reports/actions.json` (in this repo) is the static list. Every dumped action
carrying a **non-empty shortcut** should appear there with `registered=true`,
or be a Qt built-in (e.g. a `QLineEdit` context-menu entry).

Report the three counts: matched, Qt built-in, and **neither**. The third
category is a genuine finding either way — it means the static audit missed
something, or an action gets a shortcut by a route nobody has documented.
Do not tune anything to make it zero.

---

## 4. Traps

1. **SingleApplication.** Run every invocation with isolated
   `HOME`, `XDG_CONFIG_HOME` and `XDG_DATA_HOME`, or a running instance answers
   instead. Run `docker ps` first; if a container with `network_mode: host` is
   up, stop and report it.
2. **Always pass a timeout** to any QET run (`timeout 60 …`). If the modal trap
   is hit the process never returns.
3. **`-platform offscreen`** for every run; there is no display.
4. **Build**: `cmake -S . -B <build> -G Ninja -DCMAKE_BUILD_TYPE=Debug` then
   `ninja -C <build> qelectrotech`, ~3 minutes cold. Poll it; do not park.

---

## 5. Environment

| Thing | Value |
|---|---|
| QET source | `/home/user/qet-fix` |
| Static audit output | `reports/actions.json` in this repo |
| Audit tool | `tools/actionaudit/actionaudit.py` |

**Never `git checkout`, `switch`, `stash` or `reset` in `/home/user/qet-fix`'s
main tree** — it holds ~30 uncommitted files on `cabinet-layout-editor` that are
not yours. Create your own worktree:

```bash
git -C /home/user/qet-fix worktree add /tmp/s2-src -b s2-action-dump master
```

Remove it when done; leave the branch.

---

## 6. Scope

**May modify (in your worktree):** `sources/main.cpp` and a new
`sources/cli/` dump source pair, plus whatever build file lists sources.

**May create (in this repo):** `reports/actions-runtime.json`, and a small
runner script if useful.

**Do NOT:** change `ShortcutManager` or `shortcutsconfigpage.*`; register any
new actions; modify `simulator/`, `scenarios/`, `tools/refdiff/`,
`tools/shortcut-harness/`, `tools/actionaudit/`, or any `.md` plan file; push,
open a PR, or post anywhere.

---

## 7. Report

Commit on a new branch in each repo. All four criteria with **real pasted
output**, the per-window action counts, the three cross-check counts, and
anything in this brief that was wrong or underspecified — particularly if
constructing the element or titleblock editor headlessly turns out to be
impractical.
