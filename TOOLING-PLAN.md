# QET quality-tooling plan

Five tools to build, in order. Written to be executed by someone (or some
model) who has **not** seen the sessions that produced the existing
`simulator/`, `scenarios/`, and `tests/` code. Every path, command, and trap
below has been verified against this machine on 2026-08-16.

**Read §0, §1 and §2 before starting any work item. They are not preamble —
they are the parts that decide whether the output is worth anything.**

---

## 0. Rules of engagement

1. **Build nothing that drives the GUI.** Every tool here works on files and
   the headless CLI. If a design step seems to need `xdotool`, a window, or a
   screenshot, stop and ask — the answer is almost certainly "push the check
   down to the file layer instead". (`scenarios/` is ~3,500 lines of GUI
   driving that found zero QET defects; `simulator/` is a comparable size at
   the file layer and found two. That contrast is why this plan exists.)

2. **Every tool must prove itself against a defect that is already known
   before it is trusted on anything new.** Each work item below names its
   *proof fixture*. A tool that runs clean on its first sweep has almost
   certainly failed to be wired up, not proved QET correct. Do not report a
   work item as done until its proof fixture is detected.

3. **Do not file anything upstream.** No `gh pr create`, no pushes to
   `qelectrotech/*`, no posts to the bugtracker, no comments on discussions.
   The repo owner files.

   But **do not let a real finding die in a JSON file either.** Every defect
   that survives verification gets an entry in `FINDINGS.md` at the repo root:
   one section per finding, with the exact command that reproduces it, the
   binary's git sha, the input file (committed if small), what was expected,
   what happened, and whether it is already known upstream. That file is the
   handoff. A finding that exists only inside `reports/*.jsonl` has not been
   reported.

4. **Do not modify anything under `scenarios/`.** It is finished work kept as
   fixtures.

5. **Verify every claim about QET's behaviour against QET's source** at
   `/home/user/qet-fix` before encoding it as a rule. A lint rule derived from
   a guess about the file format produces thousands of false positives over a
   6,918-file collection and destroys the tool's credibility in one run.

6. **Prefer extending the existing modules to writing new ones.**
   `simulator/canon.py`, `simulator/env.py`, and `simulator/proc.py` already
   solve canonicalisation, sandbox isolation, and subprocess handling
   correctly, including edge cases that are not obvious. Import them.

7. When a work item is complete, commit it on its own branch in
   `/home/user/qelectrotech-docker` with a message describing what it
   *detects*, not what it *is*.

---

## 1. Environment facts

| Thing | Value |
|---|---|
| Harness repo (work here) | `/home/user/qelectrotech-docker` |
| QET source checkout | `/home/user/qet-fix` (git, branch `master` = upstream mirror) |
| Second worktree | `/home/user/qet-fix-wt` |
| Prebuilt binaries | `/home/user/qet-fix/build-fast/qelectrotech` (also `build-cabinet`, `build-cabinet-asan`, `build-mega`) |
| Project corpus | `/home/user/qet-fix/examples/*.qet` — 23 files |
| Element corpus (local mirror) | `/home/user/qelectrotech-docker/elements-10-electric/10_electric` — 6,918 `.elmt` |
| Element corpus (full upstream) | clone `qelectrotech/qelectrotech-elements` if a wider sweep is wanted |
| Build a ref | `scripts/qet-fastbuild.sh configure <src> <bld>` then `... build <bld>` (cold ≈ 55 s, warm ≈ 4.4 s — see `QET-BUILD-SPEED.md`) |
| Headless rendering | `QT_QPA_PLATFORM=offscreen` — no Xvfb needed for CLI verbs |
| Python | 3.14, stdlib only. Do not add dependencies. |

**Existing QET CLI verbs** (`sources/cli_export.cpp:67-78`):
`--export-pdf`, `--export-png`, `--export-svg`, `--export-cables`,
`--export-wires`, `--export-bom`, `--export-nets`, `--export-links`,
`--info`, `--check-elements`, `--resave`, `--set-titleblock`.
Plus `--test-ops` on the branch `feature/test-ops-cli` only (see W5).

**Existing harness pieces worth reusing:**

| Module | What it gives you |
|---|---|
| `simulator/env.py` | `make_sandbox()`, `sandbox_context()`, `assert_no_other_qet_running()` — fully isolated `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME` |
| `simulator/proc.py` | `run_cli(binary, args, sandbox, timeout=)` → `Outcome` with crash/timeout classification |
| `simulator/canon.py` | `canonicalize(path) -> Canon`, `diff(a, b)`, `canon_equal()`, `nan_or_inf_violations()`, `grid_regressions()` |
| `simulator/oracles.py` | `o1_crash`, `o2_idempotence`, `o3_semantic_preservation`, `o6_nan_inf`, `o6_grid_regression`, `o9_determinism`, and the `Finding` type |
| `simulator/runner.py` | sweep loop, corpus health check, ddmin shrinking wiring |
| `tests/determinism/check.py` | standalone resave idempotence/preservation gate with a `baseline.json` |
| `scripts/asan-compare.sh` | the working pattern for "build two refs, run both, diff" |

Run the harness's own unit tests at any time with
`python3 -m simulator selftest` (needs no binary). **Keep them passing.**

---

## 2. Traps that have already cost this project time

These are not hypothetical. Each one has produced wrong results here before.

1. **SingleApplication forwards to a live instance.** Launching QET while
   another instance is reachable does not start a new process — it hands the
   request to the old one, and you get *that* binary's answers with no error.
   Overriding `HOME` alone is not enough on this machine because
   `XDG_CONFIG_HOME` is set. Always go through `simulator/env.py`, and always
   call `env.assert_no_other_qet_running()` first. Check `docker ps` too: a
   running container with `network_mode: host` has cross-contaminated native
   test runs here twice.

2. **First save of a legacy project invents UUIDs.** QET writes a `uuid` on
   every `<conductor>`, and assigns fresh ones when loading a file that lacks
   them. So `resave(x)` differs from `resave(resave(x))` in UUIDs on older
   files — 67 of them on `741.qet` — and it is *stable from the second save
   on*. This is a migration artifact, not corruption. It is currently making
   the O9 self-check fail and blocking the whole sweep. W1 fixes it.

3. **`out` in `cli_export.cpp` is a buffered `QTextStream`.** The last line in
   a redirected log is the last line *flushed*, not the last processed. Never
   infer which input crashed from log position — bisect by directory, then by
   file.

4. **Core dumps are unavailable by default** (`ulimit -c` is 0, cores piped to
   apport) and `ptrace_scope` blocks `gdb -p` on a running process. Launching
   under `gdb -batch -ex run -ex bt` works and gives the crash frame.

5. **A project newer than the build, or older than 0.6, raises a modal
   `QMessageBox` during load** — headless, that hangs *every* CLI verb
   forever, before any export runs. `examples/schema_indus.qet` (version 0.3)
   does this. Fixed only on branches carrying PR #737/#661. Always pass a
   timeout; treat timeout as a finding, not an error.

6. **`docker compose run` does not rebuild the image.** Build explicitly, or
   the container silently runs old code. Docker also caches `git clone` layers
   by command string, so pass a changing build arg when a branch has moved.

7. **`docker compose run --rm` discards the container filesystem.** Anything
   written to the container's `/tmp` is gone. Mount a host directory.

8. **`--export-wires` / `--export-cables` exit 1 on an empty result**
   (`cli_export.cpp:271`), which is indistinguishable from a real failure.
   Special-case it rather than counting it as a crash.

9. **Validate suspect XML with a non-Qt parser too.** Python's `ElementTree`
   rejecting a file that Qt segfaults on *is the finding* — it separates "the
   file is bad" from "Qt mishandles bad input". Both matter, but they are
   different bugs and go to different repos.

---

## W1 — Unblock the mutation sweep (do this first)

**Goal:** the existing mutation sweep runs clean-of-artifacts again, and the
lost CLI sweep script is restored. This is the cheapest item and the only one
that resurrects a *proven* bug finder — the current `simulator/` found the
NaN-coordinate hang and the NUL-byte SIGSEGV that became upstream PR #682.

**Estimated size:** small. One afternoon.

### W1.1 Fix the first-save UUID artifact

Symptom to reproduce first: `simulator/reports/sweep_1786765847.jsonl` line 1
records `o9_self_check` failing with *"identical input produced different
canonical output"* and 67 UUIDs differing in each direction. Cause is trap #2.
`run_sweep()` treats that as "every other finding is suspect", so the sweep is
effectively dead.

Fix by **warming the corpus**, not by weakening the oracle:

- Add a `warm-corpus` subcommand to `simulator/__main__.py`:
  `python3 -m simulator warm-corpus --binary PATH --corpus IN --out OUT`
- For each `.qet` in `IN`: run `--resave` once inside a sandbox, write the
  *output* to `OUT/<same name>`. Skip and report any file whose resave
  crashes, times out, or produces nothing (that is itself worth reporting —
  log it, do not abort the warm-up).
- Sweeps and replays then point `--corpus` at `OUT`. Warmed files already
  carry their UUIDs, so the first-save churn cannot appear inside a run.
- Write a `WARMED_FROM.txt` into `OUT` recording the source dir, the binary
  path, and the binary's git describe, so a stale warm corpus is detectable.

Do **not** make `canon.py` ignore UUIDs. The UUID set is what O3 uses to prove
a save did not lose data; blinding it would remove the harness's best
corruption oracle. The docstring in `canon.py` lines 22-29 explains this —
read it.

Also check whether O2 findings currently in the reports (`"resave is not
idempotent"` on `perceuse.qet` etc.) survive against the warmed corpus. Some
will be the same artifact; some are real (the known `Diagram::toXml` stacking
order defect described in `tests/determinism/check.py`'s docstring). Split
them and record which is which — that list is a deliverable.

**Warming breaks replay of existing traces.** Mutators record *byte offsets*,
and a trace stores `seed_name` + `seed_sha256`, which `cmd_replay` resolves
against whatever `--corpus` it is given. A warmed file has different bytes, so
every trace already recorded under `simulator/reports/*.jsonl` replays only
against the **original** `examples/` directory. Do not delete or overwrite the
original corpus, and make `replay` print a clear message when the hash does not
match (it already warns — check the warning actually fires and is legible).

### W1.2 Add a regression test

Add to `simulator/tests/`: a test asserting that warming is idempotent
(`warm(warm(x))` canon-equals `warm(x)`) using a small fixture project. Keep
the whole suite green: `python3 -m simulator selftest`.

### W1.3 Restore the CLI sweep script

`scratchpad/sweep.sh` was lost when the scratchpad was cleared. It was worth
more than its size: ~15 minutes of runtime, 185 runs, and it found two real
bugs (upstream PR #737, elements PR #71) — more than three hand-picked
bugtracker entries did.

Rewrite as `scripts/cli-sweep.sh` (committed this time):

- For every project in the corpus × every CLI verb from §1, run in a fresh
  sandbox with `QT_QPA_PLATFORM=offscreen` and a **120 s timeout**.
- Also run `--check-elements` over the element corpus directory. Note it takes
  an element file or directory, **not** a project.
- Record per-run: exit code, wall time, stdout/stderr tails, timeout flag,
  and peak RSS + fd count (cheap, and it kills the "resource exhaustion"
  hypothesis instantly when a late run fails).
- Emit one JSON line per run plus a summary table. Non-zero exit if any run
  crashed or timed out, excluding the known `--export-wires` empty-result
  exit-1 case (trap #8).

**Proof fixture:** run the sweep against `examples/schema_indus.qet` (version
0.3) with a binary built from plain `master`: **every verb that loads the
project must be reported as a timeout** (the earlier sweep saw 8 — do not
hard-code that number, it depends on which verbs you run). Then rebuild from
the local branch `fix/cli-headless-version-prompt-hang`, which carries PR #737,
and re-run: it must report none. If the script cannot tell those two binaries
apart, it is not wired up correctly.

**Done when:** `python3 -m simulator sweep --binary … --corpus <warmed>` runs
50 iterations with `o9_self_check` passing; `scripts/cli-sweep.sh` is
committed and demonstrates the proof fixture; selftest suite green.

---

## W2 — `qet-lint`: static validator for `.qet` and `.elmt`

**Goal:** a dependency-free static checker that reads project and element
files and reports semantic defects, over a corpus nobody has ever swept
semantically. No build, no launch, no GUI — seconds per full run.

**Estimated size:** the largest item here — so **ship it in two stages** and do
not start stage 2 until stage 1 is verified and committed.

- **W2 stage 1 — the five rules that already have proof fixtures**: P001, P002,
  P003, E001, E002. All five are crash-or-corruption rules, all five are
  checkable without reading much QET source, and between them they cover every
  known-bad file in this repo. Stage 1 alone is a useful tool.
- **W2 stage 2 — the semantic rules**: everything else in the tables below.
  Each one needs its hypothesis confirmed against QET's source first, and each
  one can turn out to be wrong (one already did — see the note after the
  project table). Add them one at a time, running the full corpus after each.

Do not implement all eighteen rules and then start verifying. That is how a
rule that fires 783 times gets shipped.

### W2.1 Layout

```
tools/qet-lint/
  __init__.py
  __main__.py        # CLI: qet-lint [--format text|json] [--baseline FILE] PATHS...
  rules_project.py   # P0xx rules over .qet
  rules_element.py   # E0xx rules over .elmt
  model.py           # parse once into a light DOM shared by all rules
  report.py          # text + JSON output, baseline diffing
  tests/
  README.md
```

Contract for every rule: a function taking the parsed model and yielding
`Violation(rule_id, severity, path, line, message, evidence)`. Severities:
`error` (data loss or crash risk), `warning` (real defect, cosmetic impact),
`info` (opt-in, off by default).

CLI must support `--baseline baseline.json`: violations recorded there are
known and do not fail the run, so the tool becomes a *gate* on new problems
rather than a wall of pre-existing noise. `tests/determinism/check.py` does the
same thing — it records expected results and exits non-zero only when something
**got worse**, with `--write-baseline` to re-record. Copy that shape, including
the "got worse" comparison; a baseline that merely suppresses is one that hides
a rule silently breaking.

### W2.2 Rules — projects (`.qet`)

Each rule is a hypothesis. **Confirm the hypothesis against QET's source
before implementing** — the file that consumes the construct is named where
known.

| ID | Check | Severity | Verify against |
|---|---|---|---|
| P001 | any coordinate attribute is NaN/Inf | error | already implemented — `canon.nan_or_inf_violations()`, just call it. This is the class upstream PR #682 fixed |
| P002 | illegal XML 1.0 control byte anywhere in the file (U+0000-08, 0B, 0C, 0E-1F) | error | the NUL-byte SIGSEGV in `simulator/reports/findings/` |
| P003 | duplicate `uuid` value within one project | error | `canon.canonicalize()` already builds `uuid_universe` — reuse |
| P004 | `<conductor>` references a terminal that does not exist on the named element | error | `sources/qetgraphicsitem/conductor.cpp`, `terminal.cpp` |
| P005 | master/slave cross-reference points at a missing element uuid | error | `sources/ui/masterpropertieswidget.cpp`, `sources/properties/elementdata.cpp` |
| P007 | title-block template referenced but not embedded in the project | warning | `sources/titleblock/` |
| P008 | diagram `order` attributes are not a contiguous 1..N | warning | `moveDiagramUp/Down` in `sources/qetdiagrameditor.cpp` |
| P009 | project version newer than current, or ≤ 0.6 | info | the modal-hang class, trap #5 |
| P010 | element position off the grid | info, **off by default** | PR #660. Many legitimate projects are off-grid; only meaningful as a *delta* across an edit, which is W3/W5's job, not a static rule |

**There is deliberately no "orphan `element_info` row" rule here.** That was in
an earlier draft and it is wrong: `element_info` is a *runtime SQLite table*
created in `sources/dataBase/projectdatabase.cpp:308` with
`FOREIGN KEY (element_uuid) REFERENCES element (uuid)`. The `.qet` file stores
element information inline as `<elementInformations>` inside each `<element>`,
so there are no free-standing rows in a file at rest and the PR #664 defect
cannot be seen statically. It is a live-state bug and belongs to W5's O5 —
which checks the database. Do not re-add it here.

### W2.3 Rules — elements (`.elmt`)

| ID | Check | Severity | Notes |
|---|---|---|---|
| E001 | file does not parse as XML (Python `ElementTree`) | error | 5 known bad files in the mirror; all in `<name lang="ca">` from one bad translation batch |
| E002 | illegal control byte | error | `xpx.elmt` contains `&#11;` and **segfaults Qt's `QDomDocument::setContent()`** rather than erroring. That contrast (Python rejects, Qt dies) is the finding |
| E003 | two terminals at identical (x, y, orientation) | warning | verify against `sources/qetgraphicsitem/terminal.cpp` |
| E004 | no `<name lang="fr">` | info, **off by default** | **Measured: 783 of 6,918 files, 11%.** Mostly `20_manufacturers_articles` (ifm, festo) and `98_graphics` forms, where an untranslated catalogue part number is correct content, not a defect. As a warning it would bury every real finding on the first run. If enabled at all, scope it to hand-drawn categories and exclude `20_manufacturers_articles` |
| E005 | `<definition>` width/height ≤ 0, or drawing extends outside the declared box | warning | verify against `sources/editor/` |
| E006 | duplicate uuid across the whole collection | error | collection-wide, needs a second pass |
| E007 | attribute value outside its enumerated domain (e.g. terminal `orientation` ∉ {n,s,e,w}) | error | enumerate from the source, not from guesswork |
| E008 | `<name>` entry present but empty | info | |

### W2.4 Guard against a false-positive flood

After the first full run over 6,918 elements: **do not report the results
until you have hand-verified at least 3 instances of every rule that fires**,
by opening the file and tracing what QET does with it. Any rule whose sample
turns out to be legitimate content gets demoted to `info` or deleted. Record
the verification in `tools/qet-lint/README.md`. A rule nobody checked is worse
than no rule.

**Proof fixture:** `qet-lint` must, with no special configuration, flag:
(a) `xpx.elmt` under E002; (b)
`simulator/reports/findings/nul_byte_segv_cablage.qet` under P002; (c)
`simulator/reports/findings/nan_coordinate_hang_grafcet.qet` under P001.
Those three are known-bad files sitting in the repo already.

**Done when:** all three proof fixtures are flagged, a full corpus run
completes in under a minute, a baseline file exists, and every firing rule has
its hand-verification written up.

**Follow-on (optional, only after the above):** propose the same checks
upstream as a `--check-project` CLI verb, sibling to the existing
`--check-elements`. That is a user-facing feature rather than test
infrastructure, which matters — feature PRs merge here in ~1.7 days, build
infrastructure stalls indefinitely. Do not start this without the repo owner
asking for it.

---

## W3 — Version-differential regression harness

**Goal:** detect regressions between two refs automatically. Build ref A and
ref B, push the whole corpus through both, canon-diff the outputs, report what
changed. QET has no round-trip regression testing today.

**Estimated size:** medium. Most of the parts already exist.

### W3.1 Layout

```
tools/refdiff/
  __init__.py
  __main__.py     # python3 -m tools.refdiff --base master --head <ref> [--corpus DIR]
  build.py        # wraps scripts/qet-fastbuild.sh; caches builds per commit sha
  compare.py      # runs verbs, canon-diffs, classifies differences
  report.py       # markdown + JSON
```

Model it on `scripts/asan-compare.sh`, which already implements the two-ref
shape correctly.

### W3.2 Behaviour

- Resolve both refs to commit shas; keep build trees at
  `/home/user/qet-fix/build-refdiff/<sha>/` so repeat runs are cheap. ccache
  makes a second ref roughly a warm build.
- For each corpus project run, per ref, in an isolated sandbox each:
  `--resave`, `--info`, `--export-bom`, `--export-nets`, `--export-links`.
- Compare:
  - `--resave` outputs via `canon.diff()` — semantic, so cosmetic churn does
    not spam the report;
  - text exports byte-for-byte, after stripping timestamps and absolute paths
    (find these empirically; log what you stripped);
  - exit codes, and crash/timeout status.
- Classify each difference as `regression` (head crashes/times out where base
  did not; head loses elements/conductors/uuids), `improvement` (the reverse),
  or `change` (semantic difference, neither obviously worse). Only
  `regression` sets a non-zero exit code.

### W3.3 Make it runnable unattended

Add a `docker compose` service or a cron-friendly wrapper that runs
`master` vs `master@{yesterday}` nightly and writes a dated report under
`refdiff-reports/`. Do not have it post anywhere.

**Proof fixture:** plant a deliberate regression on a scratch branch off
master — in `Diagram::toXml`, skip serialising every second element (a simple
counter; **note `order` is a *diagram* attribute, not an element one — do not
key off it**) — build it, and confirm `refdiff` reports a `regression` with a
non-zero exit and names the lost uuids. Then delete the scratch branch. A
harness that has never seen a regression it was supposed to catch is unproven.

**Done when:** the planted regression is caught, a clean `master` vs `master`
run reports zero differences (this also re-proves determinism), and one real
run of `master` vs a current feature branch has been produced and read.

---

## W4 — Bugtracker triage engine

**Goal:** turn the ~75 untouched bugs at <https://qelectrotech.org/bugtracker/>
into a ranked, evidence-backed worklist. This is the highest raw
quality-value item: fixes citing a bugtracker ID have historically merged
upstream in about 0.2 days, faster than any other category.

It is also where measurement matters most — three hand-picked entries
(#256, #278, #288) all turned out to be **not reproducible on master**, i.e.
already fixed. Proving that is itself valuable, because it lets stale bugs be
closed. The tool's job is to separate live from stale cheaply.

**Estimated size:** medium. Independent of W1-W3; can be built in parallel.

### W4.1 Fetching

The tracker is **MantisBT**. Relevant URLs:

- list: `/bugtracker/view_all_bug_page.php`
- single issue: `/bugtracker/view.php?id=<n>`
- RSS: `/bugtracker/issues_rss.php`

There is no authenticated API token here, so scrape HTML. Requirements:

- **Cache every fetched page to disk** and read from cache by default; add
  `--refresh` to re-fetch. Never re-scrape in a loop while developing parsers.
- Parse with `html.parser` from the stdlib (`urllib.request` to fetch). No
  `requests`, no `beautifulsoup4` — and **no regex over HTML**, which is where
  a MantisBT table scraper silently starts returning empty fields after any
  theme change. Assert the parser found the expected field count per row and
  fail loudly if it did not.
- Rate-limit to ≤ 1 request/second and set a descriptive User-Agent. This is a
  small volunteer-run server.
- Parse: id, summary, description, steps-to-reproduce, status, resolution,
  reporter, dates, attachments (note `.qet`/`.elmt` attachment URLs — do not
  download them automatically without the owner's go-ahead), product version,
  OS.

### W4.2 Classification

Stage this the same way as W2. **Stage 1 is the part with durable value: a
complete, structured, locally-cached corpus of every open bug plus an
attempted reproduction.** That is worth having even if every heuristic below
turns out to be useless.

Stage 1, for each open unassigned bug:

- **`repro_class`**: `headless` (description implies file load/save/export or
  CLI — attemptable now), `gui` (needs interaction), `unclear`.
- **`auto_repro`**: for `headless` bugs with an attached project, run the
  implied CLI verb against it under the sandbox and record the outcome
  verbatim — command, exit code, stderr. This is the highest-value field in
  the whole tool and the only one that produces evidence rather than a guess.

Stage 2, only once stage 1 is committed and its records have been spot-checked:

- **`code_paths`**: candidate source files from a keyword → path table over
  `git grep` in `/home/user/qet-fix`, kept in an editable JSON file
  (`tools/iec81346/keywords.json` is the pattern to copy).
- **`likely_stale`**: the bug predates a merged commit touching its candidate
  paths, or auto-repro succeeds where the bug says it fails. Always a
  *hypothesis to check*, never a conclusion.
- **`effort_hint`**: size of the candidate code path region.

Be honest about stage 2: keyword→path matching over a codebase this size is
crude, and a confident-looking wrong `code_paths` is worse than an empty one.
If the calibration below does not separate, ship stage 1 and say why.

Output a markdown worklist sorted by (likely fixable × likely live), plus the
raw JSON. Ship a `--stale-only` view — the "these look already fixed, confirm
and close" list is a distinct piece of work with its own value.

### W4.3 Hard guardrails

- **Never post, comment, or log in to the bugtracker.** Read-only, always.
- Never assert "fixed" without a reproduction attempt on current master; write
  "not reproduced on `<sha>` via `<exact command>`" and let a human judge.

**Proof fixture — and a warning about it.** The calibration set is #256, #278
and #288 (hand-checked: **not reproducible on master**, i.e. already fixed)
*plus* at least three bugs known to have been live and since fixed by a real
PR — #291, #306 and #335 are documented cases with PRs attached.

**Three samples can be overfitted by accident.** Tuning heuristics until the
stale three come out stale is trivial and proves nothing; that is why the live
set is in the calibration too. The bar is: the classifier separates the two
groups *without* a rule that names any specific bug id. If it cannot, say so
in the README and ship the classifier as `unclear` for everything rather than
shipping a confident wrong answer.

**Done when:** every open unassigned bug has a record, the calibration set
separates without id-specific rules, and the top-20 worklist has been read end
to end by a human and judged plausible.

---

## W5 — Undo/redo and integrity oracles on `--test-ops`

**Goal:** the highest-value oracle in `SIMULATOR-DESIGN.md` that was never
built — metamorphic undo/redo testing. QET has roughly 40 `QUndoCommand`
subclasses; each one is a free hypothesis of the form "undo restores exactly
the prior state". It needs no reference implementation.

The reason this stalled was the belief it required GUI driving. It does not.
`--test-ops` already gives a headless editing surface.

**Estimated size:** medium-to-large, and the most valuable of the five.

### W5.1 Understand what exists

Branch `feature/test-ops-cli` in `/home/user/qet-fix` (commit `9679d208d`)
adds a `--test-ops` verb implemented in `sources/cli_export.cpp`:

```
qelectrotech --test-ops <project.qet> <ops.json> <output.qet>
```

`ops.json` is a JSON array. The op vocabulary today is exactly five ops:

| op | args | notes |
|---|---|---|
| `select` | `uuids: [...]` | clears then rebuilds selection; unknown uuids warn on stderr, non-fatal |
| `delete` | — | refuses if the selection has a non-deletable terminal |
| `rotate` | `angle` (default 90) | rejects `as_group` explicitly — that needs PR #660 |
| `undo` | — | `diagram->undoStack().undo()` |
| `redo` | — | |

It prints a one-line JSON summary with `ops_applied`, `element_count`,
`element_info_count`. It operates on `project.diagrams().first()` only.

The Python side already exists: `simulator/executor_ops.py` (`run_ops()`,
`first_element_uuid()`), with tests, plus
`simulator/fixtures/fixture_element_info_orphan.py` reproducing PR #664
through it.

**The branch does not need to merge upstream for this work to proceed.** It is
open as PR #683 and infrastructure PRs stall here. Treat it as a permanent
local test branch: rebase it onto master when master moves, keep building it
locally. Only the *bugs it finds* need to go upstream.

### W5.2 Extend the op vocabulary

In `sources/cli_export.cpp` on that branch, add ops in this order (each is a
few lines, following the existing `applySelect`/`rotate` shape — find the
matching `QUndoCommand` subclass in `sources/undocommand/` and push it):

1. `select_all`
2. `move` (`dx`, `dy`)
3. `diagram` (`index`) — so ops can target folios other than the first
4. `paste` / `copy` (this exercises the ElementScene paste path that the ASan
   regression suite already covers for leaks)
5. `add_element` (`path`, `x`, `y`) — from the element collection
6. `set_property` (`uuid`, `key`, `value`)

Follow the existing precedent for unsupported arguments: **fail loudly with a
clear stderr message and exit 2**, never silently ignore. The `as_group`
handling is the model.

Mirror each new op in `simulator/executor_ops.py` with a helper, and add a
unit test that does not need a binary (assert the JSON that gets written).

### W5.3 Build the oracles

Add to `simulator/oracles.py`:

- **O4 — undo/redo metamorphic.** Given a state s₀ and an op:
  `canon(s₀) == canon(undo(op(s₀)))` and `canon(op(s₀)) == canon(redo(undo(op(s₀))))`.
  Run at two depths: single-step, and N-step (apply 20 ops, undo 20, compare
  to start). The N-step form catches commands that are individually correct
  but do not compose — that is where the interesting bugs are.
- **O5 — referential integrity.** After any op sequence: every
  `element_info` row has a live `element` row; every conductor references two
  existing terminals; every master/slave link resolves. Check it **twice, from
  two sources** — the saved XML and the project's SQLite database — and
  require the two to agree. Their disagreement is itself an oracle, and is
  exactly the shape of PR #664.
- **O6 extension.** `canon.grid_regressions()` already exists; apply it across
  op sequences rather than only across resaves. `rotate90` four times must be
  the identity; `rotate(θ)` then `rotate(−θ)` must be the identity;
  copy → paste → delete-pasted must be the identity.

### W5.4 Build the op sweeper

New `simulator/opsweep.py`, modelled on `runner.py`:

- Generate a seeded random op trace against a corpus project; resolve every
  argument concretely (**record the actual uuid and coordinates used, never
  "a random element"** — otherwise replay diverges and the trace is worthless
  as a bug report).
- Run it through `--test-ops`, check O1/O4/O5/O6, shrink failures with the
  existing `shrink.ddmin`, and write the trace JSON alongside the finding.
- Reuse `Trace` from `simulator/trace.py` — do not invent a second trace
  format.
- Add `python3 -m simulator opsweep --binary … --iterations N`.

**Proof fixture:** `simulator/fixtures/fixture_element_info_orphan.py`
reproduces PR #664 (an orphan `element_info` row after a delete/undo cycle).
O5 must independently rediscover that defect from *generated* op traces, not
from the hand-written fixture. If it cannot rediscover a bug known to be inside
its search space, the oracle is not checking what it claims.

The two binaries you need already exist as local branches, and this has been
verified:

- **without the fix** — `feature/test-ops-cli` as-is. PR #664 is still open
  upstream and that branch carries no `element_info` fix, so a plain build of
  it is the "bug present" binary. Nothing to construct.
- **with the fix (control)** — merge the local branch
  `fix-element-info-orphan-row` (or `pr-664`) into a scratch copy of
  `feature/test-ops-cli` and build that. O5 must go quiet on this one.

A finding that does not disappear on the control binary is a false positive in
the oracle, not a bug in QET.

**Done when:** the proof fixture is rediscovered from a generated trace, O4
runs at both depths across all extended ops, every finding writes a replayable
trace, and `python3 -m simulator selftest` is green.

---

## 6. Order of work

```
W1  ──►  W2  ──►  W3
 │                 ▲
 └──────► W5 ──────┘        W4 runs in parallel throughout
```

- **W1 first, always.** It is small, and until it is done the one proven bug
  finder in the repo produces uninterpretable output.
- **W2 next** — best value per hour, and its parsing model is reused by W3's
  comparison layer.
- **W5 can start any time after W1** and is the most valuable of the five; it
  is placed later only because it is the largest. If effort has to be cut,
  cut W3 before W5.
- **W4 is independent** of all the others — different skills, different
  failure modes. Interleave it.

## 7. Global definition of done

A work item is done when **all** of these hold:

1. Its proof fixture is detected, and the detection is reproducible from a
   clean checkout with one documented command.
2. `python3 -m simulator selftest` is green.
3. The tool has a `README.md` stating what it detects, what it deliberately
   does not, and every known false-positive class.
4. One full real run has been executed and its report read end to end by a
   human — not just "it exits 0".
5. Findings are collected in the tool's report. **Nothing has been filed
   upstream, pushed to a QET repo, or posted to the bugtracker.**
