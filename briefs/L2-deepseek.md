# TASK BRIEF — L2: the permanent lab binary

You are working in `/home/user/qelectrotech-docker` and
`/home/user/qet-fix` (the QElectroTech C++ source). Everything you need is in
this brief — it is self-contained. Do not assume any skill files, plans, or
project conventions have been loaded into your context.

**This task edits C++.** L1 (a Python/shell harness) did not. If you have not
done L1, that is fine — they are independent.

---

## 1. Why this exists

QElectroTech has a headless scripted-editing verb, `--test-ops`, that lets a
test drive real editing operations with no GUI:

```bash
qelectrotech --test-ops <project.qet> <ops.json> <output.qet>
```

It is the only way to exercise QET's undo/redo commands from a script. It has
already been used to reproduce and fix a real bug that could not otherwise be
tested.

**The problem: it keeps evaporating.** It lives on a branch that is open
upstream and not merged, and every op beyond the original five has so far been
added on a scratch branch and then lost. Your job is to make it permanent and
extend it.

---

## 2. What exists today

Branch **`feature/test-ops-cli`** in `/home/user/qet-fix`, commit `9679d208d`.

**It is currently up to date with `master`** (merge-base == master == `7307a59c1`,
master is 0 commits ahead). No rebase is needed right now.

The verb is implemented in `sources/cli_export.cpp`. Five ops exist:

| op | args | notes |
|---|---|---|
| `select` | `uuids: [...]` | clears then rebuilds selection; unknown uuids warn on stderr, non-fatal |
| `delete` | — | refuses if the selection holds a non-deletable terminal |
| `rotate` | `angle` (default 90) | rejects `as_group` explicitly with exit 2 |
| `undo` | — | `diagram->undoStack().undo()` |
| `redo` | — | `diagram->undoStack().redo()` |

It prints a one-line JSON summary (`ops_applied`, `element_count`,
`element_info_count`) and operates on `project.diagrams().first()` only.

The Python side already exists at `simulator/executor_ops.py` (`run_ops()`,
`first_element_uuid()`), with unit tests.

**Read `applySelect()` and the `rotate` branch in `sources/cli_export.cpp`
before writing anything.** Every op you add mirrors that shape: parse the JSON
object, find the matching `QUndoCommand` subclass in `sources/undocommand/`,
push it onto `diagram->undoStack()`.

---

## 3. What to build

### 3a. `scripts/lab-rebase.sh` (in `/home/user/qelectrotech-docker`)

A maintenance script that:

1. Rebases `feature/test-ops-cli` onto current `upstream/master`
2. Rebuilds it into `/home/user/qet-fix/build-lab/`
3. Runs a smoke test of every op and reports pass/fail per op

The branch is current *today*, so this is forward-looking maintenance — but it
must actually work when run, not just exist.

### 3b. New ops, in this order

Each mirrors the existing pattern. The template column tells you what to copy.

| op | args | Template / command class |
|---|---|---|
| `select_all` | — | `diagram->selectAll()` — simplest, do this first |
| `move` | `dx`, `dy` | `sources/undocommand/movegraphicsitemcommand.h` |
| `diagram` | `index` | Not an undo command — switches which diagram subsequent ops target. Currently hardcoded to `.first()` |
| `set_property` | `uuid`, `key`, `value` | Look in `sources/properties/` |
| `rotate_texts` | `angle` | `sources/undocommand/rotatetextscommand.h` — **see the hard dependency in §4** |

### 3c. Rules for every op

- **Fail loudly on unsupported arguments**: clear message on stderr, `return 2`.
  Never silently ignore an argument you don't understand. The existing
  `as_group` rejection in the `rotate` branch is the exact pattern to copy.
- **Mirror each op in `simulator/executor_ops.py`** with a helper function, plus
  a unit test that asserts the JSON written — tests must not require a binary.

---

## 4. HARD DEPENDENCY — read before touching `rotate_texts`

`rotate_texts` **cannot work on `master`'s version of the command.** Verified:

```cpp
// master — opens a modal QDialog inside the constructor. Unusable headlessly.
RotateTextsCommand(Diagram *diagram, QUndoCommand *parent=nullptr);

// branch fix/rotate-texts-dialog-out-of-command — takes the angle as a parameter
RotateTextsCommand(Diagram *diagram, qreal rotation, QUndoCommand *parent=nullptr);
static bool hasSelectedTexts(Diagram *diagram);
static bool askRotation(qreal &rotation);
```

On `master` the command calls `QDialog::exec()` from its own constructor, so it
cannot be *constructed* without a human clicking a button. There is no way to
drive it from a script.

**Therefore: merge the local branch `fix/rotate-texts-dialog-out-of-command`
into your lab branch before implementing `rotate_texts`.** That branch exists
locally and is open upstream as PR #752.

If that merge conflicts in a way you cannot resolve confidently, **stop and
report** — implement the other four ops and say plainly that `rotate_texts` is
blocked. Do not attempt to reimplement the refactor yourself.

---

## 5. OUT OF SCOPE — do not implement

**`paste` / `copy` and `add_element` are deliberately excluded.** They touch the
ElementScene paste path and the element-collection loader, neither of which has
a clean template to copy, and getting them wrong is expensive. They are assigned
to a different, more capable model.

If you find yourself reading `elementscene.cpp` or the collection loader, you
have gone off-scope. Stop.

---

## 5a. WORK IN A DEDICATED WORKTREE — do not check out in the main tree

**The main working tree at `/home/user/qet-fix` currently holds 24 uncommitted
modified files on branch `cabinet-layout-editor`. That is real unfinished human
work. A `git checkout` there could destroy it.**

Create your own worktree and do all C++ work inside it:

```bash
cd /home/user/qet-fix
git worktree add -b lab/test-ops-extended /home/user/qet-fix-wt/lab feature/test-ops-cli
cd /home/user/qet-fix-wt/lab
# merge the #752 branch here, edit here, build from here
```

Rules:

- **Never run `git checkout`, `git switch`, `git stash`, or `git reset` in
  `/home/user/qet-fix` itself.** Read-only commands (`git log`, `git show`,
  `git branch --list`, `git worktree add`) are fine there.
- Do not touch the branches `cabinet-layout-editor`, `master`, or
  `fix-cli-modal-dialog-hang`.
- Another build may be running concurrently in `/home/user/qet-fix/build-ab/`.
  **Leave that directory alone.** Build into `/home/user/qet-fix/build-lab/`.

If `git worktree add` fails because a branch is already checked out elsewhere,
pick a different branch name — do not force it, and do not remove somebody
else's worktree.

---

## 6. Environment facts

| Thing | Value |
|---|---|
| Harness repo | `/home/user/qelectrotech-docker` |
| QET C++ source | `/home/user/qet-fix` |
| Build | `scripts/qet-fastbuild.sh configure <src> <bld>` then `... build <bld>` |
| Build target dir | `/home/user/qet-fix/build-lab/` |
| Build time | ~55 s warm ccache; several minutes genuinely cold |
| Headless | `QT_QPA_PLATFORM=offscreen` |
| Python | 3.14, **stdlib only** |

**Traps that apply to this task:**

1. **SingleApplication forwards to a live instance.** Launching QET while
   another is reachable returns *that* binary's answers with no error.
   Overriding `HOME` alone is insufficient — `XDG_CONFIG_HOME` is set here. Run
   through `simulator/env.py`'s `sandbox_context()`. Check `docker ps` first;
   if a container with `network_mode: host` is running, stop and report.
2. **Always pass a timeout.** Some projects raise a modal during load and hang
   every CLI verb forever (`examples/schema_indus.qet` is version 0.3 and does
   exactly this). Never run a QET CLI command unbounded.
3. **Animations need an event loop.** Some commands apply their effect through
   `QPropertyAnimation`. Headless, the undo-stack flag is set and the attribute
   is written, but the animated *value* may not land. If a fixture shows the
   right attribute with an unexpected value, this is why — report it, don't
   fight it.

---

## 7. Definition of done — paste real output for each

### Criterion 1 — the 67 vs 0 fixture (the one that matters)

This is the whole point of the task. Using `examples/741.qet` (67 conductors,
single folio) with all `rotation` attributes stripped first:

```bash
echo '[{"op":"rotate_texts","angle":45}]' > /tmp/ops.json
QT_QPA_PLATFORM=offscreen /home/user/qet-fix/build-lab/qelectrotech \
  --test-ops /tmp/in.qet /tmp/ops.json /tmp/out.qet
grep -o '<conductor [^>]*\brotation="[^"]*"' /tmp/out.qet | wc -l
```

**Expected: 67.**

Then the control — rebuild with the two `forceRotateByUser` calls in
`sources/undocommand/rotatetextscommand.cpp` reverted to `forceMovedByUser`, and
re-run:

**Expected: 0.**

That 67-vs-0 split is a known-correct result, verified by hand on 2026-08-16.
If you get anything else, the op is not doing what it claims.

### Criterion 2 — every op executes

Run each of the five ops you implemented against `examples/741.qet` and show it
completes without error. Paste the JSON summary line for each.

### Criterion 3 — `scripts/lab-rebase.sh` works

Run it. It must complete and report per-op status. Paste the output.

### Criterion 4 — tests green

```bash
cd /home/user/qelectrotech-docker && python3 -m simulator selftest
```

Must pass. Paste the result.

---

## 8. Scope boundary

**You may modify:**

- `sources/cli_export.cpp` and `sources/cli_export.h` — **on your lab branch
  only**
- `sources/undocommand/*` — only if merging `fix/rotate-texts-dialog-out-of-command`
- `simulator/executor_ops.py` and its tests
- `scripts/lab-rebase.sh` (new)

**Do not:**

- Commit to `master` in `/home/user/qet-fix`. Work on a branch off
  `feature/test-ops-cli`.
- `git push`, open a pull request, or post to GitHub or any bug tracker. The
  `--test-ops` branch is already PR #683 upstream; **it does not need to merge
  for this task to succeed** — a permanent local branch is the goal.
- Touch `scenarios/`, or edit `simulator/` beyond `executor_ops.py` and tests.
- Implement `paste`, `copy`, or `add_element` (§5).

---

## 9. How to report back

Commit on a **new branch** off `feature/test-ops-cli`, message describing what
the binary now *lets you test*.

Report:

1. **All four criteria**, each with its exact command and **real pasted
   output** — not a summary.
2. **Which ops you implemented**, and which (if any) you could not.
3. **Whether `rotate_texts` was unblocked** by the §4 merge, or blocked.
4. **Anything in this brief that was wrong, impossible, or underspecified.** Say
   so directly rather than working around it silently. If two readings of a
   requirement lead to materially different work, state your assumption and
   carry on.

If criterion 1 does not produce 67 vs 0, **say so and stop.** Do not adjust the
fixture to make it pass — the fixture is the thing being trusted, and a fixture
bent to fit defeats the entire purpose of the task. A clear report of a failure
is worth more than a green result that means nothing.
