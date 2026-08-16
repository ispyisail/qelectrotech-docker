# TASK BRIEF — W3: corpus-wide regression sweep across two refs

Work in `/home/user/qelectrotech-docker`. Self-contained.

> ## RESCOPED — do not build this from scratch
>
> `TOOLING-PLAN.md` W3 was written before `scripts/qet-ab.sh` existed. That tool
> now does the hard half: resolve two refs, build each into a per-sha tree,
> run a command in an isolated sandbox per variant, and classify the result
> semantically (`same` / `differs` / `a-only-fails` / `b-only-fails`).
>
> **Extend it. Do not write a second two-ref harness.** If you find yourself
> reimplementing ref resolution, per-sha build caching, or canonical diffing,
> stop — that code exists and is tested.

---

## 1. What is missing

`qet-ab.sh` compares **one command**. W3 needs **the whole corpus, unattended,
on a schedule**, with a report you can read the morning after.

QET has no round-trip regression testing at all, and with ~50 open PRs from this
account it is the largest single source of change going in.

---

## 2. What to build

`tools/refdiff/` — a sweep layer over the existing harness:

- For each project in the corpus, per ref, run: `--resave`, `--info`,
  `--export-bom`, `--export-nets`, `--export-links`.
- Reuse `qet-ab.sh` / `tools/abdiff` for the actual per-command comparison.
  Build each ref **once**, not once per project.
- Classify each difference as:
  - **`regression`** — head crashes or times out where base did not; head loses
    elements, conductors, or uuids
  - **`improvement`** — the reverse
  - **`change`** — semantic difference, neither obviously worse
- **Only `regression` sets a non-zero exit code.**
- Write a dated report under `refdiff-reports/` (markdown + JSON).

### Unattended mode

A cron-friendly wrapper that runs `master` vs `master@{yesterday}` nightly.
**Local only** — do not touch `.github/` or any CI service. Notify on
transition, not on every run.

---

## 3. Traps

1. **Warm the corpus first.** Two independent first-saves of a legacy project
   assign different conductor UUIDs, which will show up as spurious `change`
   findings on every file. `python3 -m simulator warm-corpus` does this if W1
   has landed; otherwise resave once yourself before comparing.
2. **`Diagram::toXml` is not idempotent on master.** Conductor identity in
   `canon.py` derives from terminal indices, which are assigned in
   `QGraphicsScene` stacking order. Expect conductor key-set noise on *every*
   comparison until that is fixed (see `briefs/W5-prereq-deepseek.md`). **Report
   it as known noise; do not tune the classifier to hide it.**
3. **`--export-wires` / `--export-cables` exit 1 on an empty result** —
   indistinguishable from real failure by exit code alone. Do not let that
   produce a false `regression`.
4. **Strip timestamps and absolute paths** before byte-comparing text exports.
   QET also writes per-run wall-clock load timings to stderr, which vary every
   run — `tools/abdiff/compare.py` already normalizes these; reuse it rather
   than rediscovering it.
5. **SingleApplication**: every run through `simulator/env.py`'s sandbox. Check
   `docker ps` first.

---

## 4. Definition of done — paste real output

### Criterion 1 — a planted regression is caught

On a scratch branch off master, make `Diagram::toXml` skip serialising every
second element (a simple counter — **note `order` is a *diagram* attribute, not
an element one; do not key off it**). Build, run the sweep, and confirm it
reports `regression`, **names the lost uuids**, and exits non-zero.

Then delete the scratch branch.

A harness that has never caught a regression it was built to catch is unproven.

### Criterion 2 — clean run is clean

`master` vs `master` must report **zero regressions** and exit 0. Any residual
`change` findings must be attributable to trap 2 above — list them and say so.

### Criterion 3 — one real run

Run `master` vs a current feature branch of your choice. Paste the report and
say what it found.

### Criterion 4 — the schedule

Show the cron entry or systemd timer, and evidence it is registered.

---

## 5. Environment

| Thing | Value |
|---|---|
| Existing harness | `scripts/qet-ab.sh`, `tools/abdiff/` (branch `add-asan-compare-script`) |
| Corpus | `/home/user/qet-fix/examples/*.qet` (23) |
| Build | `scripts/qet-fastbuild.sh`; per-sha trees under `build-ab/` |
| Python | 3.14, **stdlib only** |

Builds are slow (~2 min cold, faster warm via ccache). Build each ref once and
reuse; do not rebuild per project.

---

## 6. Scope

**May create:** `tools/refdiff/**`, `refdiff-reports/**`, a cron entry.
**May modify:** `tools/abdiff/**` only if the sweep genuinely needs a new entry
point — say so in the report if you do.

**Do NOT:** write a second ref-resolution or build-caching layer; touch
`.github/`; modify `simulator/`, `scenarios/`, or plan files; push or post.

**Work on a new branch**, and never `git checkout` in `/home/user/qet-fix`'s
main tree — it holds uncommitted work.

---

## 7. Report

Commit on a new branch. All four criteria with real pasted output, the residual
noise from trap 2 quantified, and anything in this brief that was wrong or
underspecified.
