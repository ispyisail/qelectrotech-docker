# TASK BRIEF — W1: unblock the mutation sweep

Work in `/home/user/qelectrotech-docker`. Self-contained — assume no skill files
or plan documents are loaded.

**Do this one first of the W-series.** It is small, and until it is done the one
proven bug-finder in this repo produces uninterpretable output.

---

## 1. Why

`simulator/` is a mutation sweep that has found **two real upstream bugs** (a
NaN-coordinate hang and a NUL-byte SIGSEGV, both became PR #682). It is
currently dead, for a reason that is understood and not a QET bug.

Its O9 self-check fails with *"identical input produced different canonical
output"* and 67 UUIDs differing in each direction. `run_sweep()` then treats
every other finding as suspect, so nothing it reports can be trusted.

**Cause — CORRECTED 2026-08-16, after this brief was first run:** the original
text here said QET assigns fresh conductor UUIDs on first load and stabilises
from the second save on, so warming the corpus would fix O9. **That is wrong.**
`Conductor::toXml()` writes no conductor uuid at all — only
`terminal1`/`terminal2`, which fall back to a legacy integer from a
`QHash<Terminal*, int>` rebuilt every save and filled in pointer order
(`diagram.cpp:1039`). The values differ **between processes**: three resaves of
one warmed file gave `terminal1="30"`, `"11"`, `"25"` for the same conductor.

Warming is still worth building — it removes a real confounder and the
subcommand is useful — but **it will not make O9 pass.** See §4 criterion 1.

Evidence: `simulator/reports/sweep_1786765847.jsonl`, line 1.

---

## 2. What to build

### 2a. `warm-corpus` subcommand

Add to `simulator/__main__.py`:

```bash
python3 -m simulator warm-corpus --binary PATH --corpus IN --out OUT
```

- For each `.qet` in `IN`: run `--resave` once inside a `simulator/env.py`
  sandbox, write the **output** to `OUT/<same name>`.
- A file whose resave crashes, times out, or produces nothing is **logged and
  skipped, not fatal** — that is itself worth reporting.
- Write `OUT/WARMED_FROM.txt` recording source dir, binary path, and the
  binary's git describe, so a stale warm corpus is detectable.
- Sweeps and replays then point `--corpus` at `OUT`.

> **Do NOT make `canon.py` ignore UUIDs.** The UUID set is what oracle O3 uses
> to prove a save did not lose data; blinding it removes the harness's best
> corruption oracle. Read the reasoning at `simulator/canon.py` lines 22–29
> before touching that file.

### 2b. Regression test

In `simulator/tests/`: assert warming is idempotent — `warm(warm(x))`
canon-equals `warm(x)` — using a small fixture project.

### 2c. Split the existing O2 findings

Reports contain *"resave is not idempotent"* findings (e.g. on `perceuse.qet`).
Some are the same UUID artifact; some are the **real** `Diagram::toXml`
stacking-order defect described in `tests/determinism/check.py`'s docstring.
**Re-run against the warmed corpus and produce the two lists.** That split is a
deliverable, not a side note.

### 2d. `scripts/cli-sweep.sh`

A previous version of this was lost. It was worth more than its size: ~15 min
runtime, 185 runs, **two real bugs found**. Rebuild it, committed this time.

- Every example project × every CLI verb, fresh sandbox,
  `QT_QPA_PLATFORM=offscreen`, **120 s timeout**.
- Plus `--check-elements` over the element corpus directory (it takes an element
  file or directory, **not** a project).
- Record per run: exit code, wall time, stdout/stderr tails, timeout flag, peak
  RSS, fd count. RSS/fd are cheap and kill the "resource exhaustion" hypothesis
  in one minute.
- One JSON line per run plus a summary table. Non-zero exit on any crash or
  timeout, **excluding** the known `--export-wires`/`--export-cables`
  empty-result exit 1 (trap 3 below).

---

## 3. Environment + traps

| Thing | Value |
|---|---|
| Harness repo | `/home/user/qelectrotech-docker` |
| QET source | `/home/user/qet-fix` |
| Corpus | `/home/user/qet-fix/examples/*.qet` (23 files) |
| Elements | `elements-10-electric/10_electric` (6,918 `.elmt`) |
| Build | `scripts/qet-fastbuild.sh configure <src> <bld>` then `build <bld>` |
| Python | 3.14, **stdlib only** |

1. **SingleApplication forwards to a live instance** and returns *its* answers
   with no error. Overriding `HOME` alone is not enough — `XDG_CONFIG_HOME` is
   set here. Always use `simulator/env.py`'s `sandbox_context()`. Run
   `docker ps` first; if a container with `network_mode: host` is up, stop and
   report.
2. **Always pass a timeout.** A version-incompatible project raises a modal
   during load and hangs every CLI verb forever.
3. **`--export-wires` / `--export-cables` exit 1 on an empty result** —
   indistinguishable from real failure by exit code alone.
4. **Buffered output**: the last line in a redirected log is the last
   *flushed*, not the last processed. Never infer the culprit from log position.

---

## 4. Definition of done — paste real output

### Criterion 1 — the sweep runs clean

```bash
python3 -m simulator warm-corpus --binary <BIN> --corpus /home/user/qet-fix/examples --out /tmp/warm
python3 -m simulator sweep --binary <BIN> --corpus /tmp/warm --iterations 50
```

**`o9_self_check` will NOT pass, and that is the expected result.** Report
`o9_deterministic` as measured and say why. Passing it is impossible without the
`canon.py` projection change (`briefs/W5-prereq-deepseek.md`), which is a
different task. **Do not weaken any oracle to make this green.**

### Criterion 2 — `cli-sweep.sh` discriminates

Run it against `examples/schema_indus.qet` (version 0.3, raises a modal on load)
with a binary built from plain `master`: **every verb that loads the project
must be reported as a timeout.** Then rebuild from the local branch
`fix-cli-modal-dialog-hang` and re-run: **none.**

If the script cannot tell those two binaries apart, it is not wired up.

### Criterion 3 — the O2 split

Produce the two lists (artifact vs real). Paste them.

### Criterion 4 — tests green

`python3 -m simulator selftest` must pass, including your new test.

---

## 5. Scope

**May modify:** `simulator/__main__.py`, `simulator/runner.py`,
`simulator/tests/**`, `scripts/cli-sweep.sh` (new).

**Do NOT:** weaken `canon.py`'s UUID handling; delete or overwrite the original
`examples/` corpus (traces record byte offsets and only replay against the
corpus they were recorded from); touch `scenarios/`; push or post anywhere.

**Work on a new branch.** The shared working tree may have other sessions in it
— never `git checkout`/`stash`/`reset` in `/home/user/qet-fix`.

---

## 6. Report

Commit on a new branch. Report all four criteria with **real pasted output**,
plus anything in this brief that was wrong or underspecified — say so plainly
rather than working around it.
