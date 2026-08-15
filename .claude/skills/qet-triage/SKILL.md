---
name: qet-triage
description: Route any QElectroTech request to the right workflow and tool. Load FIRST whenever the user reports something wrong with QET, asks for a fix, asks what to work on, asks for a feature, or describes a symptom without saying what to do about it — "QET crashed", "this is broken", "fix bugtracker #NNN", "find me bugs", "it's slow", "can you add X".
---

# QET triage

The user directing this work is **not a QET internals developer**. They report
symptoms and outcomes. Your job is to pick the workflow, not to ask them which
one they want.

Load `qet-env` before running anything. Then match the request below.

**Every branch starts with a cheap existence check. Do it before building
anything.** Is it already fixed, already implemented, already known? Each check
below costs seconds; skipping it costs a build, and in testing that was the
failure mode of *every* branch of this router — the workflow was right and it
started too far in.

**This includes checking your own open PRs, and that check is the one most
often skipped.** There are ~45 of them. It applies to architecture and refactors
too, not just bug fixes — a good idea now was very likely a good idea two weeks
ago, and may already be sitting in review:

```bash
gh pr list --repo qelectrotech/qelectrotech-source-mirror --author ispyisail \
  --state open --limit 100 --json number,title,headRefName \
  --jq '.[] | "#\(.number)  \(.title)"' | grep -i '<keyword>'
```

Real case: a "non-interactive mode for headless runs" was designed, built,
verified and opened as #753 — then found to be a duplicate of #661, opened
twelve days earlier from this same account, with the same hook point and the
same four guards. One `gh pr list | grep -i modal` would have caught it.

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

**First, translate the words.** The user names things the way the UI and the
trade do; the codebase usually uses something else ("wire" → conductor, "page"
→ folio/diagram, "symbol" → element). Load **`qet-glossary`** before grepping,
or you will conclude the feature does not exist.

1. **Is it already known?** Check <https://qelectrotech.org/bugtracker/> and
   GitHub discussions before anything else.
2. **Is it already fixed?** Reproduce on current master *first*. Three
   hand-picked bugtracker entries in a row (#256, #278, #288) turned out to be
   already fixed. This step has the best time-saved-per-minute in the project.
3. **Ask *when* it is wrong.** This is the question that localises the bug —
   not "which subsystem do you think it is", which the user cannot answer.

   | When it goes wrong | Where the bug is | Reach for |
   |---|---|---|
   | Wrong the moment it is created | the creating code | native build, GUI repro |
   | Right, then wrong after save + reload | serialization | `qet-determinism`, then `canon.diff()` — **no build needed** |
   | Wrong only after copy / paste / duplicate | the paste path | known bug family; check open PRs first |
   | Right in the app, wrong in a PDF/BOM/DXF export | export only | the relevant `--export-*` verb, headless |
   | Wrong only on some folios / some projects | data-dependent | get the file; it is the reproduction |

   The reload and export rows are answerable in minutes with no build at all.
   Ask the question before choosing a tool.

4. → **Load `qet-repro`.**

---

## "Fix bugtracker #NNN"

**Step 0, before anything else: have we already fixed it?** Roughly 16 of the
bugtracker numbers have already been addressed from this account. Checking
takes five seconds; discovering it by failing to reproduce takes a build.

```bash
gh pr list --repo qelectrotech/qelectrotech-source-mirror --author ispyisail \
  --state all --limit 100 --json number,title,state \
  --jq '.[] | select(.title|test("NNN")) | "PR #\(.number) \(.state) \(.title)"'
```

If it comes back merged, say so and stop: *"already fixed — PR #NNN, merged
<date>"*. That is the complete answer to the request.

**Trap: `#312` is ambiguous.** Bugtracker numbers and GitHub PR/issue numbers
are separate systems that collide constantly. `git log --grep=312` on this
repo returns both PR #707 (which fixes *bugtracker* 312) **and** an unrelated
`Merge pull request #312 from Arusekk/dark-mode-collections`. Always search on
the phrase `bugtracker #NNN`, not the bare number, and confirm which system the
user means if it is not obvious.

Not already fixed? → **Load `qet-repro`, then `qet-fix-and-ship`.**

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

**Step 0: does it already exist?** A feature request from someone who does not
know the app deeply is very often one of three things, and all three are
cheaper to check than to build:

| | Check |
|---|---|
| Already implemented | grep the source — **translate the words first** (`qet-glossary`), the codebase rarely uses the user's term |
| Implemented under a different name or menu | check the UI actions in `sources/qetdiagrameditor.cpp` and the panel context menus |
| Implemented but **conditionally disabled** | look for a guard on the call — the feature may be off for read-only projects, empty selections, or a missing setting |

The third case is the subtle one and it is common. Worked example: *"can you
make the folio tabs reorderable"* — they already are. `projectview.cpp:842`
does `m_tab->setMovable(true)`, `QTabBar::tabMoved` is wired to
`ProjectView::tabMoved`, and reordering by menu exists too
(`moveDiagramUp/Down`, `elementspanelwidget.cpp:110`). But line 999 does
`m_tab->setMovable(editable)` — so on a read-only project dragging silently
does nothing. That request is not a feature at all; it is either a usage
question or a bug about the read-only state, and building anything would have
been wasted work.

If it exists, say so, say how to reach it, and ask whether the real complaint
is that it does not work in their situation.

Only once it genuinely does not exist:

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
