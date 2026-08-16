# TASK BRIEF — W5 prerequisite: make O4 evaluable

Work in `/home/user/qelectrotech-docker`. Self-contained.

> ## READ THIS FIRST — W5 itself is BLOCKED
>
> `TOOLING-PLAN.md` W5 asks for undo/redo metamorphic oracles (O4) on the
> `--test-ops` lab binary. **The op vocabulary is now done** (lab binary,
> branch `lab/test-ops-extended`, five new ops). **O4 still cannot be
> evaluated**, and this task is the reason why.
>
> **Do not attempt to build O4 in this task.** Build the prerequisite, prove it,
> stop. O4 comes after.

---

## 1. The blocker, measured

Driving the lab binary and comparing canonical states, **a no-op op sequence
fails its own round-trip**:

| ops | result |
|---|---|
| `[{"op":"select_all"}]` — changes nothing | **FAIL** |
| `select_all, delete, undo` | FAIL |
| `select_all, move, undo` | FAIL |
| `select_all, rotate, undo` | FAIL |

Because the no-op fails, this measures the **harness**, not the commands. Two
layers, both confirmed:

1. **First-save UUID churn** — two independent first-saves of a legacy project
   assign different conductor UUIDs. Warming the corpus (one resave first)
   removes this. *(W1 builds `warm-corpus`; if it exists, use it.)*
2. **The residual, and the real blocker** — after warming, the diff is
   `conductors key-set differs`. In `simulator/canon.py`, conductor identity is
   the sorted `(terminal1, terminal2)` pair. Terminal indices are assigned by
   `Diagram::toXml` iterating `QGraphicsScene::items()` — **stacking order, not
   content order**. So conductor keys shuffle between saves of identical
   content.

This is the known non-idempotence documented in
`tests/determinism/check.py`'s docstring. Full write-up: `FINDINGS.md` F002 on
branch `add-asan-compare-script`.

---

## 2. Two possible fixes — evaluate both, recommend one

### Option A — content-derived conductor identity in `canon.py` — **DO THIS**

**Measured 2026-08-16: no projection keyed on `terminal1`/`terminal2` can ever
be stable.** `Conductor::toXml()` writes no conductor uuid; `terminal1` is the
terminal's uuid when it has one, else a legacy integer from `table_adr_id` — a
`QHash<Terminal*, int>` rebuilt every save (`diagram.cpp:1039`), keyed by
pointer, filled in `QGraphicsScene::items()` order. Pointer iteration depends on
heap layout, so it differs **between processes**: three resaves of one warmed
file gave `terminal1="30"`, `"11"`, `"25"` for the same conductor.

So derive identity from `element1`/`element2` (element uuids) plus
`terminalname1`/`terminalname2` — all written by the same function whenever
terminals carry uuids. **There is no conductor `uuid` attribute to fall back
on; do not look for one.**

- Cheap, no C++, no upstream dependency.
- Must not weaken oracle O3 (data loss detection) — if a conductor genuinely
  disappears, the projection must still notice.

### Option B — fix `Diagram::toXml` ordering upstream

Iterate in a content-derived order rather than `QGraphicsScene::items()`
stacking order.

- Fixes the root cause and would make `tests/determinism` pass.
- C++, larger blast radius, and it changes saved-file byte output for everyone.

**Implement option A.** Option B is recorded for context and as a possible
upstream follow-up, but it is not this task: it changes saved-file output for
every user, and option A unblocks O4 without touching what QET writes to disk.
Say in your report if you found a reason A cannot work.

---

## 3. Definition of done — paste real output

### Criterion 1 — the no-op round-trips

With a warmed input, this must produce **zero canonical diffs**:

```bash
echo '[{"op":"select_all"}]' > ops.json
qelectrotech --test-ops warm.qet ops.json out.qet
# canon.diff(canonicalize(base), canonicalize(out)) == []
```

This is the whole task. If the no-op does not round-trip, nothing downstream is
measurable.

### Criterion 2 — real changes are still detected

The projection must not have gone blind. Show that a genuine change **is** still
caught:

- delete an element (no undo) → canon diff is **non-empty**
- a conductor removed from the file → still detected by O3

**A projection that reports "same" for everything passes criterion 1 and is
worthless.** Criterion 2 is what proves you did not simply blind the oracle.

### Criterion 3 — the four op round-trips

Re-run the table in §1 with the fix in place. Report each result honestly.

**If some still fail after the no-op passes, that is a REAL finding** — a
genuine undo/redo defect, which is exactly what O4 exists to find. Report it
with the op sequence and the diff; do **not** adjust the projection to make it
pass.

### Criterion 4 — nothing regressed

`python3 -m simulator selftest` green, and `tests/determinism` no worse than its
current baseline.

---

## 4. Environment + traps

| Thing | Value |
|---|---|
| Lab binary | `/home/user/qet-fix/build-lab/qelectrotech` (branch `lab/test-ops-extended`) |
| Ops available | `select`, `select_all`, `delete`, `move`, `rotate`, `rotate_texts`, `diagram`, `set_property`, `undo`, `redo` |
| Corpus | `/home/user/qet-fix/examples/741.qet` (67 conductors, single folio) |
| Python | 3.14, **stdlib only** |

1. **Warming does NOT fix this.** An earlier version of this brief said one
   `--resave` first would settle the ids. It does not — the churn recurs every
   save and varies between processes (see option A). Warm if you like for other
   reasons, but do not expect it to make anything deterministic.
2. **SingleApplication**: always use `simulator/env.py`'s `sandbox_context()`;
   check `docker ps` first.
3. **Animations**: some commands apply through `QPropertyAnimation`. Headless,
   the flag is set and the attribute written, but the animated *value* may not
   land. If a value looks wrong but the attribute is present, that is why —
   report it, don't fight it.

---

## 5. Scope

**May modify:** `simulator/canon.py` (option A), `simulator/tests/**`, and — only
if you recommend option B and say so first — `sources/diagram.cpp` on a branch
off `lab/test-ops-extended` in a **dedicated worktree**.

**Do NOT:** build O4 or any new oracle; touch `scenarios/`; `git checkout` in
`/home/user/qet-fix`'s main tree (it holds uncommitted work); push or post.

---

## 6. Report

Commit on a new branch. Report all four criteria with real pasted output, which
option you chose and why, and — if criterion 3 surfaces genuine undo/redo
failures — list them separately as candidate defects for W5 to chase.
