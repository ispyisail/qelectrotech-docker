# TASK BRIEF — X5: detect editing-state decoration leaking into exports

Self-contained. Read `CROSSPAGE-PLAN.md` in this repo first.

---

## 0. HOW THIS TASK ENDS — read first

Seven of fourteen sessions on this project ended by **announcing they would
wait** for a build instead of waiting. Two more **crashed and lost everything**
because nothing was on disk. This task needs a ~3 minute QElectroTech build.

- **Never end your turn waiting.** Poll in a loop.
- **Commit early and often.**
- **Never report a criterion done without pasting its real output.**

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/x5-progress.log
```

---

## 1. Why this exists — a real rejection

Upstream PR #701 added a blue halo around folio-reference arrows to show they
were linked. It was **rejected**, and the decisive reason was:

> *"this halo is drawn inside `paint()`, so it also shows up in PDF export as
> well as PNG/SVG exports. This is an editing-state indicator that has no place
> on a final document meant to be printed or shared."* — scorpio810

The maintainer left the door open: an indicator would be acceptable if
*"restricted to interactive display only (hover, or excluded at export/print
time)"*.

**This tool is the check that would have caught that before submitting**, and it
applies to any future editing-state visual, not just that one.

---

## 2. What to build

`tools/exportleak/` — Python 3, stdlib only.

QElectroTech exports headlessly already (`sources/cli_export.cpp`):
`--export-pdf`, `--export-png`, `--export-svg`.

**SVG is the important one: it is XML, so a leaked decoration can be detected
textually** — element counts by tag, distinct stroke/fill colours, anything with
partial opacity (halos are usually translucent) — rather than by fragile image
comparison.

1. Export every corpus project to SVG (plus PNG for a coarse sanity check).
2. Build an inventory per folio: tag counts, colour set, opacity usage.
3. Compare two builds — baseline vs candidate — and report anything present in
   the candidate's export but not the baseline's.

Output `reports/exportleak.{json,md}`.

---

## 3. Definition of done — paste real output

### Criterion 1 — baseline inventory
Export the corpus from a clean `master` build; report per-project SVG tag counts
and the distinct colour set.

### Criterion 2 — **a planted leak is caught** (the one that matters)
On a scratch branch, recreate the defect #701 died on: in the folio-report
element's `paint()`, unconditionally draw a translucent coloured halo (a filled
ellipse, or a wide semi-transparent stroke around the bounding rect).

Build, export, and confirm the tool **reports the leak**, names the affected
projects and the offending SVG feature, and **exits non-zero**.

Then **delete the scratch branch and its build directory.** A branch that alters
rendering, left in the QET repo, silently poisons later comparisons.

*A leak detector that has never caught a leak is unproven — this criterion is
the point of the task.*

### Criterion 3 — no false positives
`master` vs `master`: exporting the same build twice must report **zero** leaks.
If SVG output is not byte-stable, normalise (ids, timestamps, float precision)
and state exactly what you normalised — do not loosen the comparison until it
passes.

### Criterion 4 — what each format can detect
Confirm the planted halo also shows as a difference in PNG (file size / pixel
count) and PDF (file size). Report honestly what each format can and cannot
detect; SVG is the precise one.

---

## 4. Traps

1. **Always pass a timeout.** `examples/schema_indus.qet` is version 0.3 and
   hangs forever on a modal (upstream #661). Exclude it and say so.
2. **SingleApplication**: isolated `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME` and
   `-platform offscreen` on every run. Check `docker ps` first.
3. **Export writes one file per folio** for PNG/SVG — use a temp dir per run.
4. **Never `git checkout`/`stash`/`reset` in `/home/user/qet-fix`'s main tree**;
   it holds uncommitted work on `cabinet-layout-editor`. Use a worktree.
5. Build: `cmake -S <src> -B <build> -G Ninja -DCMAKE_BUILD_TYPE=Debug` then
   `ninja -C <build> qelectrotech`. Poll it.

---

## 5. Scope

**May create:** `tools/exportleak/**`, `reports/exportleak.{json,md}`, and
temporarily a scratch branch in the QET repo for criterion 2 **which you must
delete**.

**Do NOT:** leave any QET source change behind; modify `simulator/`,
`tools/refdiff/`, `tools/crosspage/`, `tools/actionaudit/`, or any `.md` plan
file; push or open a PR.

**Work on a new branch** in this repo.

---

## 6. Report

All four criteria with real pasted output, confirmation the scratch branch and
build are gone, wall-clock for a full corpus export, and anything in this brief
that was wrong or underspecified.
