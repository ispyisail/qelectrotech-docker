# QET lab environment — build plan

Six work items that close the gap between *making* a change (1.7 s) and
*proving* it correct (30–60 min). Written to be executed one item per session.

**Prerequisite:** read `TOOLING-PLAN.md` §0–§2 first. Its rules of engagement,
environment facts, and traps apply here unchanged — this plan does not repeat
them. In particular: **every item names a proof fixture, and no item is done
until its proof fixture is detected.**

`TOOLING-PLAN.md` (W1–W5) and this plan (L1–L6) are independent. W-items build
*bug finders*; L-items build the *bench* those finders run on. L1 and L2 make
every W-item cheaper, so if both plans are in flight, do L1 first.

---

## Model selection

**Claude budget is the scarce resource. DeepSeek is the default executor; Claude
is reserved for judgment.** The split below follows one rule:

> **Construction with a mechanical proof fixture → DeepSeek.
> Judgment with no mechanical check → Claude.**

That rule works *because* every item in this plan already has a proof fixture.
The fixture is what makes a cheaper executor safe: it either passes or it
doesn't, and you can check it in one command without trusting the model's
self-report. On items where the deliverable is a judgment call, there is no
fixture to hide behind and a confidently wrong answer costs more than it saved.

### The models

| Model | ID | Role here |
|---|---|---|
| DeepSeek V4 Pro | `deepseek-v4-pro` | Default executor for construction items |
| DeepSeek V4 Flash | `deepseek-v4-flash` | Plumbing items and subagents |
| Claude Opus 5 | `claude-opus-5` | Judgment items, escalation, review |
| Claude Sonnet 5 | `claude-sonnet-5` | Escalation step between the two |

**Verified working 2026-08-16** against `https://api.deepseek.com/anthropic`:
both models respond on the Anthropic-compatible `/v1/messages` endpoint, and
**tool use works** — a tool-use probe returned `stop_reason: "tool_use"` with a
correctly-formed command. Tool use was the thing worth checking; every item in
this plan is agentic file-and-bash work, and an executor that can't call tools
is useless here regardless of its reasoning.

### Running DeepSeek

`~/.bashrc` already defines the switch; the key lives in `~/.deepseek_key`
(mode 600). **This runs as a separate terminal session, not as a subagent** —
a subagent spawned from a Claude session inherits that session's model config,
so there is no way to dispatch DeepSeek work from inside Claude Code:

```bash
use_deepseek     # sets ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN + model vars
claude           # or: deepseekrun
```

The workflow is therefore: **Claude writes the brief → you run it in a DeepSeek
session → you check the proof fixture → Claude reviews only if it fails.**

### Assignment per item

| Item | Executor | Why |
|---|---|---|
| **L1** A/B harness | `deepseek-v4-pro` | Tight spec, existing modules to reuse, mechanical fixture. **Already ~half built** — see the resumption note below |
| **L2** Lab binary + ops | `deepseek-v4-pro` | Each op mirrors an existing one in `cli_export.cpp`. **Escalate `paste`/`add_element` to Claude** — no clean template, and they touch the ElementScene paste path and collection loader |
| **L3** Gates in CI | `deepseek-v4-flash` | Wiring already-working commands into a runner. No design decisions remain |
| **L4** In-flight visibility | `deepseek-v4-flash` | `gh` queries plus formatting. Pure data plumbing |
| **L5** Coverage audit | **Claude Opus 5** | Naming what the tooling is *structurally blind to* is exactly the judgment a fixture can't check. Wrong here → a wasted build |
| **L6** phase 1 — evidence inventory | `deepseek-v4-pro` | **Revised 2026-08-16.** Classifying 136 PRs as observed/inferred/unstated turns out to be mechanically separable — a crude evidence-marker count already splits the calibration set (#707 scores 0, #682 and #737 score 6). That makes it delegable data collection, and 136 PR bodies is expensive Claude context for pattern-matching |
| **L6** phase 2 — rank the inferred | **Claude Opus 5** | Deciding which inferred claims are worth re-testing is risk judgment with a high false-positive cost. Runs on phase 1's inventory |

L5 and L6 are also the two cheapest items in Claude tokens — they produce a
document, not a codebase, and involve no build loop. Keeping them on Claude
costs little and protects the decisions that steer everything else.

### Escalation ladder — and its trigger

**This has not been benchmarked on this codebase.** DeepSeek's API works; how
well it executes *these* items is unmeasured. Treat each first assignment as an
experiment with a defined stopping rule rather than a settled decision:

```
deepseek-v4-flash → deepseek-v4-pro → claude-sonnet-5 → claude-opus-5
```

**Escalate when any of these is true**, rather than on a vague sense that it's
struggling:

1. The proof fixture fails twice with the same root cause.
2. It edits files outside the item's stated scope.
3. It reports done without having run the fixture — treat a self-report as no
   evidence at all.
4. It violates a `TOOLING-PLAN.md` §2 trap after being pointed at it (running
   without a sandbox, treating a timeout as an absence of difference).

Log the escalation and the trigger in the item's commit message. After two or
three items you'll have real data on where DeepSeek's ceiling sits here, which
is worth more than any guess made now.

### Briefing a DeepSeek session

The briefs matter more than they did for Claude. Include, every time:

- **The item's section from this file, verbatim** — plus `TOOLING-PLAN.md`
  §0–§2. Don't summarise; paste it.
- **The proof fixture as the definition of done**, with the exact command and
  the exact expected output.
- **An explicit scope boundary**: the files it may create or modify, and a
  statement that everything else is off-limits.
- **The traps that apply to this item**, restated inline. Don't rely on it
  finding them in a linked file.
- **"Show the real command output"** — not a summary of it.

`.claude/skills/` may or may not load in a DeepSeek session depending on how
Claude Code handles a non-Anthropic backend. **Assume it doesn't** and paste the
relevant skill content into the brief.

### Verification stays with you — and this is now load-bearing

Every fixture is a one-command check. With a cheaper executor, running it
yourself stops being good practice and becomes the mechanism the whole plan
rests on. A DeepSeek session reporting success is *not* evidence; the fixture
output is.

---

## L1 — `scripts/qet-ab.sh`: the A/B harness

**Do this first.** It pays back on every future fix, and L2's proof depends on
it being convenient.

> ### Resumption state (2026-08-16) — read before starting
>
> A first attempt got **partway** and stopped mid-run. On disk, **untracked and
> uncommitted**: `scripts/qet-ab.sh` and `tools/abdiff/` (`build.py`, `run.py`,
> `compare.py`, `report.py`, `__main__.py`, `README.md`). A build tree exists at
> `/home/user/qet-fix/build-ab/7307a59c101a/`.
>
> **None of the three done-criteria were demonstrated.** No fixture output, no
> build timings, no branch, no commit. The build layer looks right — the cmake
> invocation picked up ccache, mold, PCH and disconnected FetchContent from
> `qet-fastbuild.sh` — but *nothing about the harness has been shown to work.*
>
> Treat the existing code as **a draft to verify, not a foundation to build
> on.** Read it, run the fixtures, fix what fails. If the timeout handling is
> wrong (the most likely defect — see the fixture below), rewrite that part
> rather than patching around it.

**Goal:** one command builds two variants, runs the same thing against both,
and diffs the result.

```bash
scripts/qet-ab.sh --a master --b fix/my-branch -- --resave examples/741.qet out.qet
scripts/qet-ab.sh --a HEAD --b HEAD~1 --patch revert.diff -- --test-ops in.qet ops.json out.qet
```

A *variant* is a ref, a branch, or a patch applied to a ref. This is the
operation that dominates verification work and currently has zero support —
today it means a manual configure, build, run, edit, rebuild, run.

### Build it

```
scripts/qet-ab.sh          # the entry point
tools/abdiff/
  build.py                 # resolve ref → sha, build tree per sha, ccache-warm
  run.py                   # run the command in an isolated sandbox per variant
  compare.py               # classify the difference
  report.py                # text + JSON
```

- Model it on `scripts/asan-compare.sh` — the two-ref shape is already correct
  there. This generalises it from "diff LeakSanitizer output" to "diff anything".
- Build trees at `/home/user/qet-fix/build-ab/<sha>/`, keyed by sha so repeat
  runs are free. ccache makes the second variant nearly a warm build.
- Run each variant through `simulator/env.py`'s sandbox and
  `simulator/proc.py`'s `run_cli()` — do not hand-roll subprocess handling.
- Diffing: `.qet` outputs go through `simulator/canon.py` `diff()` (semantic,
  so cosmetic churn does not spam); text output byte-for-byte after stripping
  timestamps and absolute paths; always compare exit code and crash/timeout
  status.
- Classify as `same` / `differs` / `a-only-fails` / `b-only-fails`. Exit
  non-zero only on a real difference.

### Proof fixture — the CLI hang A/B

Both branches exist and both sides of this were verified by hand on
2026-08-16, so it is achievable today with no other work.

```bash
scripts/qet-ab.sh --a master --b fix-cli-modal-dialog-hang \
  -- --info /home/user/qet-fix/examples/schema_indus.qet
```

`examples/schema_indus.qet` is version 0.3, which raises a modal during load.
On `master` that hangs `--info` forever; on `fix-cli-modal-dialog-hang` (PR
#661) it completes with exit 0. The harness must report **`a-only-fails`** —
variant A timing out, variant B succeeding — and exit non-zero.

This is the case that matters most: **a timeout is a difference.** A harness
that hangs waiting for variant A, or that reports "no output from either" and
calls them equal, has failed the fixture. Timeouts must be first-class,
per-variant, and classified as failure.

**Second fixture, same-vs-same:** `--a master --b master` with any command must
report `same` and exit 0.

### Stretch fixture — once L2 lands

Reproduce the PR #707 A/B in one command: variant A = `feature/test-ops-cli`,
variant B = the same branch with the two `forceRotateByUser` lines reverted,
command = `--test-ops` with a `rotate_texts` op, against `examples/741.qet`
with `rotation` attributes stripped. Expect **67 vs 0** rotation attributes.

**That comparison is not runnable yet** — `rotate_texts` was added on a scratch
branch and discarded; L2 restores it. Do not attempt it during L1, and do not
add the op as a side quest. It is recorded here because it is the comparison
that took ~40 minutes by hand (`FINDINGS.md` F001-b), and it is the real
measure of whether this harness replaced anything.

**Done when:** the hang A/B classifies correctly and exits non-zero, the
same-vs-same run reports `same` and exits 0, and the second variant's build is
measurably faster than the first (ccache is working).

---

## L2 — The permanent lab binary

**Goal:** a `--test-ops`-capable QET binary that is always current with master
and always available — not a branch someone has to remember to cherry-pick.

Everything valuable in the last session became possible because of `--test-ops`,
and all of it evaporated because the op existed only in a scratch worktree.

### Build it

1. **Keep `feature/test-ops-cli` rebased on master.** It is open upstream as
   PR #683 and infrastructure PRs stall here — that does not matter. Treat it
   as a permanent local test branch. Add `scripts/lab-rebase.sh` that rebases it
   onto current `upstream/master`, rebuilds, and reports whether the build and
   the op vocabulary still work.
2. **Extend the op vocabulary**, in this order, each mirroring the existing
   `applySelect`/`rotate` shape in `sources/cli_export.cpp`:
   `select_all`, `move` (dx, dy), `diagram` (index — so ops can reach folios
   other than the first), `paste`/`copy`, `add_element` (path, x, y),
   `set_property` (uuid, key, value), `rotate_texts` (angle).
3. **Fail loudly on unsupported arguments** — exit 2 with a clear stderr
   message, never silently ignore. The existing `as_group` rejection is the
   model to copy.
4. **Mirror each op in `simulator/executor_ops.py`** with a helper and a unit
   test that needs no binary.
5. **Build it as `build-lab/`** and document it in the `qet-env` skill so the
   next session knows it exists.

**Escalate to `claude-opus-5`** for `paste`/`copy` and `add_element`. The others
have a working template in the file; those two don't.

### Proof fixture

`scripts/lab-rebase.sh` run against current master produces a binary that
executes all seven ops on `examples/741.qet` without error, and
`python3 -m simulator selftest` stays green.

Then the real one: **L1's stretch fixture must run against this binary with no
scratch work** — `scripts/qet-ab.sh` reproducing the #707 A/B (67 vs 0) in one
command. If that still requires hand-adding an op, L2 isn't done.

**Done when:** both fixtures pass, the rebase script is committed, and
`qet-env` documents the lab binary.

---

## L3 — Run the gates automatically

**Goal:** the checks that already exist stop depending on someone remembering.

`qet-determinism`, `qet-asan-regression`, `tests/determinism/check.py`, and
`scripts/cli-sweep.sh` (once W1.3 lands) are all working gates that only ever
run when invoked by hand. With 45 open PRs that is a lot of surface drifting.

### Build it

- A single `scripts/gates.sh` that runs every gate in sequence, collects
  pass/fail, and writes a dated report under `gate-reports/`.
- Wire it to run nightly — a cron entry or a systemd timer on this machine.
  **Local or fork-side only.** Upstream CI is a maintainer decision about
  release infrastructure and is exactly the category that stalls (#510).
- Non-zero exit if any gate regresses against its baseline. Gates that are
  *known* to fail (the `Diagram::toXml` stacking-order non-idempotence) must be
  baselined, not silently skipped — copy the `tests/determinism/baseline.json`
  pattern.
- Notify on transition only (pass→fail, fail→pass). A nightly "everything is
  fine" message trains you to ignore it.

### Proof fixture

Introduce a deliberate regression on a scratch branch — the same
`Diagram::toXml` drop-every-second-element used in `TOOLING-PLAN.md` W3 — and
confirm the nightly run flags it and exits non-zero. Then delete the branch and
confirm the next run goes green and reports the transition.

**Done when:** the planted regression is caught, baselines exist for the known
failures, and two consecutive clean runs produce no notification.

---

## L4 — In-flight visibility

**Goal:** one command answers "what am I already working on?"

This is the gap that produced PR #753 — a complete duplicate of #661, built and
opened before anyone checked. 45 open PRs, 116 branches, and no view across
them.

### Build it

`scripts/inflight.sh`, or `tools/inflight/` if it grows past a script:

- Open PRs grouped by state: awaiting review, changes requested, draft, stale
  (>30 days).
- Local branches with **no** corresponding PR — work that exists only here.
- Branches whose PR is merged (prunable).
- A `--search <term>` mode that greps titles, branch names, and PR bodies at
  once. This is the mode that would have caught #753; make it the fastest path.
- Cache the `gh` results to disk with a `--refresh` flag; don't re-query on
  every invocation.

### Proof fixture

`scripts/inflight.sh --search modal` must surface **both** #661 and the
now-closed #753, and `--search "non-interactive"` must surface #661. Those are
the two searches that would have prevented the duplicate.

**Done when:** the proof fixture works, the stale list matches a hand count, and
the `qet-triage` skill's step-0 snippet is updated to call this script instead
of a raw `gh pr list` pipe.

---

## L5 — Coverage audit: what can't be tested at all

**Analysis, not construction.** The deliverable is a document, not a tool.

**Goal:** name the classes of defect the current tooling is structurally blind
to, so the next build targets a real gap rather than deepening a covered one.

Every tool in this repo works on files or the headless CLI. That is deliberate
and correct — and it means whole categories are invisible. Name them.

### Do it

For each area, answer: *can any existing tool observe this, and if not, what
would it take?*

- GUI interaction state machines — drag, rubber-band select, in-place edit
- Multi-folio behaviour — cross-references, folio reordering, the summary
- Live database state (`projectdatabase.cpp`) versus what the `.qet` file says
- Undo/redo composition beyond what `--test-ops` can drive
- Rendering and export fidelity — is the PDF actually right, or just produced?
- Element editor, terminal strip editor, title-block editor
- Anything requiring two instances, or a file changing under the app

Rank by (likelihood a real bug lives there) × (cost to make it observable).
**Recommend at most three.** A list of twenty gaps is not an audit.

### Proof fixture

For each of the top three, name one **concrete defect that would have been
caught** — ideally one already in the bugtracker or the merged-PR history. A
gap with no plausible defect behind it is not worth closing.

**Done when:** `COVERAGE-GAPS.md` exists, each recommendation carries its
concrete defect, and the ranking's reasoning is written down rather than
asserted.

---

## L6 — Verification audit: inspection versus observation

**Analysis, not construction.**

**Goal:** find the other PRs whose central claim was verified by reading code
rather than by observing behaviour.

PR #707 shipped with "confidence rests on tracing the code path" written into
its own commit message, and when finally tested it turned out to have a second
symptom nobody had seen. It is unlikely to be the only one.

### Do it

- Pull all merged and open PRs from this account.
- For each, classify the evidence behind its central claim: **observed**
  (a command was run and its output recorded), **inferred** (code path traced),
  or **unstated**.
- For the `inferred` set, judge whether the claim is *checkable now* — with the
  lab binary from L2 and the harness from L1, many will be.
- Rank by (chance the inference is wrong) × (cost of it being wrong).

Be honest about the base rate: most inferred claims will be correct. The value
is in the few that aren't, so **do not pad the list**. An audit that flags 30
PRs is useless; one that flags 3 with reasons is worth doing.

### Proof fixture

The audit must independently classify **PR #707 as `inferred`** without being
told — it is the known-positive, and its commit message states the gap in plain
text. If the method misses that one, it will miss the subtler ones.

Calibration in the other direction: PR #682 and PR #737 both carry recorded
command output and must classify as `observed`.

**Done when:** every PR has a classification, the calibration set comes out
right, and the top-ranked candidates are listed with the specific check that
would settle each one.

---

## Order

```
L1 ──► L2 ──► (unblocks W5 and every future fix)
                    ▲
L6 ─────────────────┘   (L6 finds the claims; L1+L2 let you settle them)

L3, L4   independent, cheap, do them whenever
L5       independent analysis, do it before choosing the next build
```

- **L1 first**, always. Smallest, and everything else gets cheaper.
- **L2 next** — it is what makes L1 useful for anything beyond file-level work.
- **L3 and L4** are cheap enough to slot in anywhere; L4 in particular pays for
  itself the first time it prevents a duplicate.
- **L5 and L6** are analysis and can run in parallel with the builds, on
  different sessions. L6's output is a worklist that L1+L2 then execute against.

## Definition of done (all items)

1. The proof fixture is detected, reproducibly, with one documented command.
2. `python3 -m simulator selftest` is green.
3. The tool or document says what it covers and what it deliberately does not.
4. One real run has been executed and read end to end by a human.
5. Nothing filed upstream, pushed to a QET repo, or posted to the bugtracker.
