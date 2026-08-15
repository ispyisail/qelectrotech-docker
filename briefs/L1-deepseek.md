# TASK BRIEF — L1: `scripts/qet-ab.sh`, an A/B harness for QElectroTech

You are working in `/home/user/qelectrotech-docker`. Everything you need is in
this brief — it is self-contained. Do not assume any skill files, plans, or
project conventions have been loaded into your context.

---

## 1. What you are finishing

A command that builds two variants of QElectroTech, runs the same command
against each in isolation, and classifies the difference:

```bash
scripts/qet-ab.sh --a master --b fix-cli-modal-dialog-hang \
  -- --info /home/user/qet-fix/examples/schema_indus.qet
```

A *variant* is a git ref, a branch, or a patch applied to a ref. Verdicts are
exactly four: `same`, `differs`, `a-only-fails`, `b-only-fails`.

**This is a verification job, not a greenfield build.** A previous session wrote
a draft and stopped without ever running it.

### What exists (untracked, uncommitted, UNVERIFIED)

```
scripts/qet-ab.sh          42 lines
tools/abdiff/build.py     166
tools/abdiff/compare.py   189
tools/abdiff/run.py        46
tools/abdiff/report.py     70
tools/abdiff/__main__.py  124
tools/abdiff/README.md
```

A build tree also exists at `/home/user/qet-fix/build-ab/7307a59c101a/`.

**Not one of the three done-criteria in §5 was ever demonstrated.** No fixture
output, no build timings, no commit. The draft reads as structurally sensible —
it has the right verdict vocabulary and appears to handle timeouts deliberately
— but *appearing correct and being correct are different things, and that
difference is the entire job here.*

**Treat the draft as a draft to verify, not a foundation to trust.** Read it,
run the fixtures in §5, fix what fails. If timeout handling is wrong, rewrite
that part rather than patching around it.

---

## 2. Environment facts

| Thing | Value |
|---|---|
| Work here | `/home/user/qelectrotech-docker` |
| QET source | `/home/user/qet-fix` (git; `master` tracks upstream) |
| Example projects | `/home/user/qet-fix/examples/*.qet` |
| Build a ref | `scripts/qet-fastbuild.sh configure <src> <bld>` then `... build <bld>` |
| Build times | cold ≈ 55 s with warm ccache; a genuinely cold ref can take several minutes |
| Headless | `QT_QPA_PLATFORM=offscreen` — no X server needed for CLI verbs |
| Python | 3.14, **stdlib only** — add no dependencies |

### QET CLI verbs

`--info`, `--resave`, `--check-elements`, `--set-titleblock`,
`--export-pdf|png|svg|bom|nets|links|wires|cables`

### Modules you MUST reuse (do not hand-roll these)

| Module | Use it for |
|---|---|
| `simulator/env.py` | `sandbox_context()` — isolated `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME`; `assert_no_other_qet_running()` |
| `simulator/proc.py` | `run_cli(binary, args, sandbox, timeout=)` → `Outcome` with crash/timeout classification already done |
| `simulator/canon.py` | `canonicalize(path)`, `diff(a, b)` — semantic `.qet` comparison that ignores cosmetic churn |

These solve non-obvious edge cases and are already unit-tested. Writing your own
subprocess handling or XML diffing is a defect, not a shortcut.

---

## 3. Traps — every one of these has produced wrong results in this project

**Read all six. They are the difference between a working harness and one that
silently lies.**

1. **SingleApplication forwards to a live instance.** Launching QET while
   another instance is reachable does not start a new process — it hands the
   request to the existing one and returns *that binary's* answers, with no
   error. Overriding `HOME` alone is not enough because `XDG_CONFIG_HOME` is set
   on this machine. Always run through `simulator/env.py`'s sandbox. Run
   `docker ps` before you start; if a container is running with
   `network_mode: host`, **stop and report** rather than producing wrong results.

2. **A timeout is a difference, not an absence of one.** This is the most likely
   defect in the draft and the thing the main fixture exists to catch. If your
   harness blocks forever waiting for variant A, or concludes "neither produced
   output, therefore `same`", it has failed. Timeouts must be per-variant,
   bounded, and classified as a **failure of that variant**.

3. **`--export-wires` and `--export-cables` exit 1 on an empty result.** That is
   indistinguishable from a real failure by exit code alone. Don't let it
   produce a false `differs`.

4. **Buffered output.** QET's CLI writes through a buffered stream; the last
   line in a redirected log is the last line *flushed*, not the last processed.
   Never infer which input caused a problem from log position.

5. **Core dumps are off** (`ulimit -c` is 0) and `ptrace_scope` blocks
   `gdb -p` on a running process. Launching under `gdb -batch -ex run -ex bt`
   works if you need a trace — but you shouldn't for this task.

6. **`examples/schema_indus.qet` is version 0.3**, which makes QET raise a modal
   dialog during load. Headless there is nobody to answer it, so on `master`
   **every** CLI verb hangs forever. This is not a bug you are fixing — it is
   the *input* to your proof fixture.

---

## 4. Design requirements

- Build trees at `/home/user/qet-fix/build-ab/<sha>/`, keyed by resolved commit
  sha so repeat runs are free and ccache stays warm.
- Each variant's run gets its **own** sandbox via `simulator/env.py`.
- Comparison:
  - `.qet` outputs → `simulator/canon.py` `diff()` (semantic)
  - text output → byte-for-byte after stripping timestamps and absolute paths
  - always compare exit code, crash status, and timeout status
- Exit non-zero **only** on a real difference. `same` is the only verdict that
  exits 0.
- Report both text (human) and JSON (machine).

---

## 5. Definition of done — three criteria, each with exact expected output

You must run all three and **paste the real terminal output** of each. A summary
of what happened is not acceptable evidence.

### Criterion 1 — the hang A/B (the one that matters)

```bash
scripts/qet-ab.sh --a master --b fix-cli-modal-dialog-hang \
  -- --info /home/user/qet-fix/examples/schema_indus.qet
```

**Expected:** verdict `a-only-fails`. Variant A (`master`) times out; variant B
(`fix-cli-modal-dialog-hang`, which carries the fix) completes with exit 0. The
harness itself must **exit non-zero** and must not hang.

Both branches exist locally. Both sides of this were verified by hand on
2026-08-16, so the expected result is known-correct, not a guess.

### Criterion 2 — same-vs-same

```bash
scripts/qet-ab.sh --a master --b master \
  -- --info /home/user/qet-fix/examples/perceuse.qet
```

**Expected:** verdict `same`, exit code 0.

(Use `perceuse.qet`, not `schema_indus.qet` — the latter hangs on master, which
would make this criterion test the wrong thing.)

### Criterion 3 — ccache is working

Report wall-clock build time for **both** variants. The second must be
measurably faster than the first. State both numbers.

### Also required

- `python3 -m simulator selftest` must still pass. Paste the result.

---

## 6. Scope boundary

**You may create or modify only:**

- `scripts/qet-ab.sh`
- `tools/abdiff/**`
- Build trees under `/home/user/qet-fix/build-ab/`

**Off-limits — do not touch:**

- The QET source at `/home/user/qet-fix` beyond checking out refs into build
  trees. Do not commit there, do not modify tracked files there.
- `scenarios/` — finished work, kept as fixtures.
- `simulator/` — reuse it, don't edit it.
- Any other `.md` plan file in the repo.

**Do not:**

- Add a `rotate_texts` op, or any op, to `--test-ops`. That is a different work
  item. If you find yourself editing C++, you have gone off-scope.
- `git push`, open a pull request, or post anything to GitHub or any bug
  tracker.
- Commit to the branch `add-asan-compare-script`. Make your own branch.

---

## 7. How to report back

Commit your work on a **new branch** in `/home/user/qelectrotech-docker`, with a
message describing what the tool *detects* rather than what it is.

Then report:

1. **The three criteria**, each with its exact command and **real pasted
   output**.
2. **Both build timings.**
3. **The selftest result.**
4. **What was wrong with the draft**, specifically — or state plainly that it
   worked as written, if it did.
5. **Anything in this brief that was wrong, impossible, or underspecified.** Say
   so directly rather than working around it silently. If two readings of a
   requirement would lead to materially different work, state the assumption you
   made and carry on.

If a criterion fails and you cannot fix it, **say so and stop**. A clear report
of a blocked criterion is more useful than a workaround that makes the fixture
pass without the underlying behaviour being right — the fixture exists to be
trusted, so defeating it defeats the point of the task.
