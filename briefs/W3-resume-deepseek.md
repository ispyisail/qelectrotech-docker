# TASK BRIEF — W3 RESUME: prove the corpus sweep catches a regression

Self-contained. Assume no skill files or plan documents are loaded.

**This is a resume.** The code is written. Nothing about it has been shown to
work. Your job is the proving, not the building.

---

## 0. HOW THIS TASK ENDS — read first

The previous session wrote ~950 lines and then **ended its turn by announcing it
would wait for a sweep to finish**. It produced no reports and demonstrated no
criteria. That is the one way to fail this brief.

- **Never end your turn while waiting.** Poll in a loop — sleep, re-check,
  continue — until the thing completes.
- **Never report a criterion done without pasting its real output.**
- If something genuinely cannot finish, say so explicitly and stop. "Criterion 1
  blocked because X" is a good outcome. Silence while waiting is not.

Six of nine sessions on this project have failed this way. Do not be the
seventh.

---

## 1. What exists

Branch **`w3-refdiff-wip`** (commit `50adc5c`) in
`/home/user/qelectrotech-docker`:

```
tools/refdiff/__main__.py     287 lines   CLI: --base --head --corpus --repo --timeout
tools/refdiff/classify.py     165         regression / improvement / change
tools/refdiff/normalize.py     98
tools/refdiff/report.py        95
tools/refdiff/nightly.sh       55
tools/refdiff/tests/           162         test_classify.py
tools/abdiff/compare.py        +8          (plus 30 lines of tests)
```

**Start from this branch.** Read the code before running it — the previous
session never got to see any of it execute, so treat it as a draft to verify.

**What was NOT done:** no `refdiff-reports/` were produced, and none of the four
criteria below were demonstrated.

**Already cleaned up for you:** the previous session left a
`w3-planted-regression` branch checked out in a worktree at `/tmp/w3-regress-src`
— a branch that deliberately makes `Diagram::toXml` drop every second element.
Both have been removed. **You will need to recreate that branch for criterion 1,
and you must remove it again when done.** A branch that corrupts saved output,
left lying in the QET repo, will silently poison other sessions that build from
that tree.

---

## 2. What the tool is for

`scripts/qet-ab.sh` already compares **one command** across two refs. W3 is the
same idea across **the whole corpus, unattended**: every project × five verbs ×
two refs, classified, with a report you can read the morning after.

QET has no round-trip regression testing at all, and this account has ~50 open
PRs — it is the largest single source of change going in.

---

## 3. Definition of done — paste real output for each

### Criterion 1 — a planted regression is caught (**the one that matters**)

Recreate the scratch branch. In `Diagram::toXml`, skip serialising every second
element with a simple counter — **note `order` is a *diagram* attribute, not an
element one; do not key off it.** The previous session's diff was correct:

```cpp
int w3_skip_counter = 0;   // planted regression
    if (w3_skip_counter++ % 2 != 0)
        continue;
```

Build it, run the sweep against `master`, and confirm it reports
**`regression`**, **names the lost uuids**, and **exits non-zero**.

Then **delete the branch and its worktree.**

A harness that has never caught a regression it was built to catch is unproven,
and this is the only criterion that proves it.

### Criterion 2 — a clean run is clean

`master` vs `master` must report **zero regressions** and exit 0.

**Expect this to be genuinely clean.** The `canon.py` projection is now
content-derived and order-independent — verified today: two consecutive resaves
of `741.qet`, `perceuse.qet` and `ShellyParts.qet` each give **0 canon diffs**.
If you see conductor or element churn between two runs of the same ref, that is
a **real finding** — report it; do not write it off as known noise.

### Criterion 3 — one real run

Run `master` vs a current feature branch of your choice. Paste the report and
say what it found.

### Criterion 4 — the schedule

Show `nightly.sh` registered as a cron entry or systemd user timer, and evidence
it is registered (`crontab -l` / `systemctl --user list-timers`). **Local only** —
do not touch `.github/` or any CI service.

---

## 4. Traps

1. **Compare saved `.qet` projects with `canon.diff()`, never a byte or line
   diff.** Byte-level output is still non-deterministic — `Diagram::toXml` emits
   elements in `QGraphicsScene` stacking order, so raw bytes differ between runs
   and `tests/determinism`'s I1 still fails. Text *exports* can be byte-compared
   after normalisation; saved projects cannot.
2. **`--export-wires` / `--export-cables` exit 1 on an empty result** —
   indistinguishable from real failure by exit code alone. Do not let that
   produce a false `regression`.
3. **QET writes per-run wall-clock load timings to stderr**, which vary every
   run. `tools/abdiff/compare.py` already normalises these — reuse it rather
   than rediscovering it.
4. **SingleApplication**: every run through `simulator/env.py`'s
   `sandbox_context()`. Run `docker ps` first; if a container with
   `network_mode: host` is up, stop and report.
5. **Build each ref once**, not once per project. ccache makes the second ref
   nearly warm; rebuilding per project turns a 10-minute sweep into hours.

---

## 5. Scope

**May modify:** `tools/refdiff/**`, `refdiff-reports/**`, a cron entry, and
`tools/abdiff/**` only if the sweep genuinely needs a new entry point (say so if
you do).

**Do NOT:** write a second ref-resolution or build-caching layer — `qet-ab.sh`
and `tools/abdiff` already do that; touch `.github/`; modify `simulator/`,
`scenarios/`, `tests/`, or any `.md` plan file; push, open a PR, or post
anywhere.

**Leave the QET repo as you found it.** No `git checkout`, `switch`, `stash` or
`reset` in `/home/user/qet-fix`'s main tree — it holds uncommitted work. Use a
dedicated worktree for the planted-regression branch and remove it afterwards.

---

## 6. Report

Commit on a branch off `w3-refdiff-wip`. Report all four criteria with **real
pasted output**, confirm the planted-regression branch and worktree are gone,
give the wall-clock for a full sweep, and flag anything in this brief that was
wrong or underspecified — say so plainly rather than working around it.
