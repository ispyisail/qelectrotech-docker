# TASK BRIEF — L3: run the gates automatically

You are working in `/home/user/qelectrotech-docker`. This brief is
self-contained — do not assume any skill files or plan documents are loaded.

**This is plumbing.** Every gate below already exists and already works. You are
wiring them into one runner with baselines and transition detection. You are not
writing new tests, and you are not fixing any gate that fails.

---

## 1. The problem

Four quality gates exist in this repo. All of them only ever run when a human
remembers to type the command. With 50 open pull requests, that means a lot of
surface drifting unwatched.

Your job: one script that runs them all, compares against a baseline, and says
something **only when a result changes**.

---

## 2. The gates

| Gate | Command | Status |
|---|---|---|
| Determinism | `docker compose run --rm qet-determinism` | Exists, image built |
| ASan regression | `docker compose run --rm qet-asan-regression` | Exists, image built |
| Test suite | `docker compose run --rm qet-test` | Exists, image built |
| CLI sweep | `scripts/cli-sweep.sh` | **DOES NOT EXIST YET** |

Verified 2026-08-16: the three compose services are defined, and the
`qelectrotech:test` and `qelectrotech:asan` images are already built, so no slow
first-time image build is needed.

**`scripts/cli-sweep.sh` is a different work item and has not been built.** Your
runner must handle its absence gracefully: report it as `not-built`, and **do
not** let that count as a failure. When it later appears, the runner should pick
it up with no code change.

---

## 3. What to build

### `scripts/gates.sh`

- Runs every gate in sequence.
- Writes a dated report to `gate-reports/YYYY-MM-DD-HHMMSS.json` plus a
  human-readable `.md` alongside it.
- Per gate, records: name, command, exit code, wall-clock duration, status
  (`pass` / `fail` / `not-built` / `error`), and the tail of its output.
- **Exits non-zero only if a gate got *worse* than its baseline.** A gate that
  was already failing and still fails is not a regression — it is the status quo.

### Baselines

Some gates are **known to fail today** and that is expected. The determinism
gate in particular fails on a real, understood upstream issue
(`Diagram::toXml` iterates in stacking order rather than content order).

- Store expected results in `gate-reports/baseline.json`.
- Provide `--write-baseline` to record the current state as the new expected
  state. This mirrors the existing pattern in `tests/determinism/baseline.json`
  — read that file to see the shape before inventing your own.
- **Baseline known failures; never silently skip them.** A skipped gate looks
  identical to a passing one, which is exactly the failure mode this whole task
  exists to prevent.

### Transition detection

- Report `pass→fail` and `fail→pass` transitions prominently.
- **Notify only on transition.** A nightly "everything is fine" message trains
  the reader to ignore all messages, which defeats the purpose.
- Notification can be as simple as writing a `gate-reports/ALERT.md` and
  printing to stdout — do not add a dependency, do not send email, do not post
  to any external service.

### Scheduling

Add a cron entry or systemd timer that runs it nightly. **Local machine only.**
Do not add anything to a CI service, and do not touch any GitHub workflow file.

---

## 4. Environment facts

| Thing | Value |
|---|---|
| Work here | `/home/user/qelectrotech-docker` |
| Python | 3.14, **stdlib only** — add no dependencies |
| Shell | bash |
| Gates take | minutes each; the full run may take 10–30 min |

**Traps that apply:**

1. **`docker compose run --rm` discards the container filesystem.** Anything a
   gate writes inside the container is gone when it exits. Capture stdout and
   stderr on the host side; do not expect to find files afterwards.
2. **`docker compose run` does not rebuild the image.** That is fine here — you
   *want* the existing images. Do not add `--build`; it would make each nightly
   run enormously slower for no benefit.
3. **A hung gate must not hang the runner.** Give every gate a generous but
   finite timeout (e.g. 30 minutes) and record a timeout as `error`, not as
   `pass`.

---

## 5. Definition of done — paste real output for each

### Criterion 1 — a full run produces a report

```bash
scripts/gates.sh
```

Must run all gates, write a dated report under `gate-reports/`, and show
`not-built` for the CLI sweep. Paste the summary output and the report file.

### Criterion 2 — a regression is caught

You do **not** need to build C++ for this. Simulate a regression by editing
`gate-reports/baseline.json` so one gate's expected status differs from its
actual status, then re-run:

```bash
scripts/gates.sh
```

**Expected:** the changed gate is flagged as a transition, and the script
**exits non-zero**. Paste the output and the exit code (`echo $?`).

### Criterion 3 — restoring goes green

Restore the baseline (or run `scripts/gates.sh --write-baseline`), then run
again.

**Expected:** exit 0, and the transition is reported as resolved. Paste the
output.

### Criterion 4 — the schedule is installed

Show the cron entry or systemd timer, and evidence it is registered
(`crontab -l` or `systemctl --user list-timers`).

---

## 6. Scope boundary

**You may create or modify:**

- `scripts/gates.sh`
- `gate-reports/**` (new directory)
- A crontab entry or systemd user timer

**Do not:**

- Modify any gate, any test, `tests/**`, `simulator/**`, `scenarios/**`, or
  `docker-compose.yml`.
- **Fix a failing gate.** If a gate fails, that is data — baseline it and report
  it. Fixing it is a different task and is explicitly not yours.
- Add `--build` to any docker compose command.
- Touch `.github/`, push, open a pull request, or post anywhere.

---

## 7. How to report back

Commit on a **new branch**, with a message describing what the runner *detects*.

Report:

1. **All four criteria**, each with its exact command and **real pasted
   output** — not a summary.
2. **Which gates passed, failed, or errored** on the first real run, and which
   you baselined as known-failing.
3. **Total wall-clock time** for a full run — this determines whether nightly is
   the right cadence.
4. **Anything in this brief that was wrong, impossible, or underspecified.** Say
   so plainly rather than working around it silently.

If a gate fails in a way you do not understand, **report it and move on** — do
not investigate, and do not fix. Cataloguing the current state accurately is the
deliverable.
