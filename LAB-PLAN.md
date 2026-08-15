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

### The models

| Model | ID | Input / output per MTok | Context | Positioning |
|---|---|---|---|---|
| Claude Fable 5 | `claude-fable-5` | $10 / $50 | 1M | Most capable widely released; hardest reasoning and long-horizon agentic work |
| Claude Opus 5 | `claude-opus-5` | $5 / $25 | 1M | Complex agentic coding and long-horizon work; half Fable's cost |
| Claude Sonnet 5 | `claude-sonnet-5` | $3 / $15 (intro $2 / $10 to 2026-08-31) | 1M | Best speed-to-intelligence; near-Opus on coding and agentic work |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | 200K | Fastest and cheapest; simple, well-specified tasks |

### Minimum model per item

"Minimum" means: the cheapest model I'd expect to finish the item without
supervision, given this repo's skills are installed. Escalate on failure rather
than starting high.

| Item | Minimum model | Effort | Why that floor |
|---|---|---|---|
| **L1** A/B harness | `claude-sonnet-5` | `xhigh` | Shell + Python against existing modules. Spec is tight and verification is mechanical — but it has to make judgment calls about what counts as a difference, which is past Haiku |
| **L2** Lab binary + ops | `claude-sonnet-5` | `xhigh` | C++ in an unfamiliar Qt codebase. Each new op mirrors an existing one, so the pattern carries it. **Escalate to `claude-opus-5` for `paste` and `add_element`** — those touch the ElementScene paste path and the collection loader, neither of which has a clean template |
| **L3** Gates in CI | `claude-haiku-4-5` | `medium` | Wiring existing, already-working commands into a runner. No design decisions left |
| **L4** In-flight visibility | `claude-haiku-4-5` | `medium` | `gh` queries plus formatting. Pure data plumbing |
| **L5** Coverage audit | `claude-opus-5` | `xhigh` | Analysis, not construction. Requires reasoning about what the tooling is structurally blind to — a wrong answer here is confidently wrong and costs a wasted build |
| **L6** Verification audit | `claude-opus-5` | `xhigh` | Reading 45 open PRs and judging claim-by-claim which were observed vs inferred. High false-positive risk; the whole value is in the judgment |

**Nothing here needs `claude-fable-5`.** These are well-scoped engineering
tasks against a documented codebase, not open-ended research. Reach for it only
if an item stalls on Opus twice.

**The skills change the floor.** `.claude/skills/` now carries the environment
facts, the routing, and the traps that used to be tacit. A Sonnet or Haiku
session in this repo starts with the SingleApplication guard, the build recipe,
and the vocabulary map already in hand — which is most of what made these tasks
need a bigger model before. If an item fails on its stated minimum, check
whether the relevant skill is missing something before blaming the model.

### Per-session harness

- One item per session. Give it: this file, `TOOLING-PLAN.md` §0–§2, and the
  item's section. Do not hand a model both plans at once.
- Effort settings above are starting points. Coding and agentic work runs best
  at `xhigh`; drop to `high` if a session is burning tokens without progress.
- **Verification stays with you.** Every item's proof fixture is something you
  can check in one command. Run it yourself before accepting the work.

---

## L1 — `scripts/qet-ab.sh`: the A/B harness

**Do this first.** It pays back on every future fix, and L2's proof depends on
it being convenient.

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

### Proof fixture

Reproduce the PR #707 A/B in **one command**. Against `examples/741.qet` with
`rotation` attributes stripped, variant A = `feature/test-ops-cli`, variant B =
the same branch with the two `forceRotateByUser` lines reverted, command =
`--test-ops` with a `rotate_texts` op: the harness must report **67 vs 0**
rotation attributes and exit non-zero.

That exact comparison took ~40 minutes by hand and is written up in
`FINDINGS.md` F001-b. If the harness can't reproduce it in one invocation, it
hasn't replaced anything.

**Done when:** the proof fixture reproduces; a same-vs-same run reports `same`
and exits 0; the second variant's build is measurably faster than the first
(ccache is working).

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

Then the real one: **L1's proof fixture must run against this binary with no
scratch work.** If reproducing the #707 A/B still requires hand-adding an op,
L2 isn't done.

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
