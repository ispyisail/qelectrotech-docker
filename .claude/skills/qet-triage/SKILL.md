---
name: qet-triage
description: Route any QElectroTech request to the right workflow and tool. Load FIRST whenever the user reports something wrong with QET, asks for a fix, asks what to work on, asks for a feature, or describes a symptom without saying what to do about it — "QET crashed", "this is broken", "fix bugtracker #NNN", "find me bugs", "it's slow", "can you add X".
---

# QET triage

The user directing this work is **not a QET internals developer**. They report
symptoms and outcomes. Your job is to pick the workflow, not to ask them which
one they want.

Load `qet-env` before running anything. Then match the request below.

---

## "It crashed" / "it froze" / "it hung"

→ **Load `qet-crash`.**

**If it crashes on opening a specific file, that file is the reproduction.**
Go headless before anything else — `--resave` for a project, `--check-elements`
for an element, both with a timeout. Crashing headless means the bug is in the
load path (best case: reproducible, minimisable, clean stack). Running fine
headless means it is in the GUI path, which is a different investigation. Do
not open a GUI to chase a crash you can trigger from the command line.

Split crash from hang immediately, because they are different bug classes:
- **Crash** (process dies) → ASan, stack trace, minimal input.
- **Hang** (process alive, unresponsive) → look for a modal dialog first. A
  version-incompatible project hangs every headless verb forever (PR #737).
  A busy-spin at 100% CPU is a third thing again (a NaN coordinate does this).

Check `/proc/<pid>/stat` utime to tell a busy-spin from a block. Crash fixes
merge upstream faster than any other category — do not sit on one.

---

## "This behaves wrong" (nothing crashes)

1. **Is it already known?** Check <https://qelectrotech.org/bugtracker/> and
   GitHub discussions before anything else.
2. **Is it already fixed?** Reproduce on current master *first*. Three
   hand-picked bugtracker entries in a row (#256, #278, #288) turned out to be
   already fixed. This step has the best time-saved-per-minute in the project.
3. Does the symptom involve **saving, loading, or exporting**?
   - **Yes** → no build needed. `tests/determinism/check.py` answers "did a save
     lose or reorder data", `simulator/canon.py` `diff()` answers "what exactly
     changed". → **Load `qet-repro`.**
   - **No** → native build, reproduce in the GUI. → **Load `qet-repro`.**

---

## "Fix bugtracker #NNN"

→ **Load `qet-repro`, then `qet-fix-and-ship`.**

Reproduce on current master before writing any code. If it does not reproduce,
that is a *result*, not a dead end: record "not reproduced on `<sha>` via
`<exact command>`" and tell the user — closing a stale bug is real work.

~75 open bugs have never been touched, and bugtracker-citing fixes have merged
in ~0.2 days on average. This is the highest-yield work available.

---

## "Find me bugs" / "what should I work on?"

→ **Load `qet-bughunt`.** Cheapest tool first; stop when there is enough to
work on.

---

## "I want feature X" / "someone asked for X in discussion #NNN"

1. Is there a discussion or bugtracker entry? If not, create one and get a
   signal **before** building.
2. Does it fight the existing architecture? If yes, write a scope doc first and
   post it — design-heavy features that fight the architecture are the one
   category that gets closed unmerged here. `QUICK-INSERT-SCOPE.md` and
   `LINK-ID-SCOPE.md` are the pattern to follow.
3. Otherwise: native build, small and self-contained. → `qet-fix-and-ship`.

Small self-contained features merge in ~1.7 days. Packaging and build-infra
changes stall indefinitely — that needs a maintainer decision, not better code.

---

## "Did we break something?" / "review this"

- Changed C++ → `/code-review`, then build and exercise the affected path.
- Changed save/load → `docker compose run --rm qet-determinism`. This is the
  gate that catches silent data loss.
- Sanitizer-sensitive code → `docker compose run --rm qet-asan-regression`.
- Full corpus check across two refs → `tools/refdiff` (see `TOOLING-PLAN.md`
  W3; build it if it does not exist yet).

---

## "It's slow" / "it lags" / "it hangs for a moment"

Both tools for this already exist upstream and are merged:
- **EventLoopWatchdog** (PR #665) — reports UI stalls via timer lateness.
- **Diagnostic logging + crash-time ring flush** (PR #646/#647) — enable it,
  reproduce, read the ring buffer for what happened before the stall.

Sample RSS and fd count while reproducing. Flat numbers rule out a leak in a
minute and stop a wrong hypothesis early.

---

## Always

- **Findings go in `FINDINGS.md`** at the repo root — repro command, binary
  sha, input file, expected vs actual, and whether it is known upstream. A
  finding that lives only in a JSONL report has not been reported.
- **Do not open PRs or post to the bugtracker without being asked.** Report
  what you found and let the user decide.
- Full reference for humans: `DECISION-TREE.md`.
