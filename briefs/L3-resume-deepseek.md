# TASK BRIEF — L3 RESUME: finish the gates runner

Work in `/home/user/qelectrotech-docker`. Self-contained.

**This is a resume, not a restart.** Most of the work is done and on disk. Read
what exists before changing anything.

---

## 0. HOW THIS TASK ENDS — read first

A previous session did the build, then **ended its turn by announcing it would
wait for a background task**. That is the one way to fail this brief.

- **Never end your turn while waiting for something.** Poll it: run a loop that
  sleeps and re-checks until the thing completes, then continue.
- **Never report a criterion as done without pasting its real output.**
- If something genuinely cannot finish, say so explicitly and stop — a clear
  "criterion 3 blocked because X" is a good outcome. Silence while waiting is
  not.

---

## 1. What already exists (untracked, uncommitted)

| Path | State |
|---|---|
| `scripts/gates.sh` | 19.6 KB, works — ran a full sweep successfully |
| `gate-reports/2026-08-16-135451.{json,md}` | a completed run |
| `gate-reports/logs/**` | per-gate logs |
| `gate-reports/.gitignore` | present |

**Criterion 1 is already demonstrated.** That run produced:

| Gate | Status | Exit |
|---|---|---|
| `asan-regression` | pass | 0 |
| `determinism` | **fail** | 1 |
| `test` | **fail** | 137 (SIGKILL — hit the 30-min timeout) |
| `cli-sweep` | not-built | 127 |

Both of those failures are **correct and expected**:

- `determinism` fails on the known `Diagram::toXml` stacking-order
  non-idempotence. **Baseline it. Do not fix it.**
- `cli-sweep` does not exist yet (it is another work item). `not-built` is the
  right status and must not count as failure.
- `test` hitting a 30-minute timeout is a **real finding** — that gate has been
  unusable and nobody noticed. Record it; do not investigate or fix it.

---

## 2. What is missing — do exactly this

### Criterion 2 — a regression is caught

**No C++ build needed.** Edit `gate-reports/baseline.json` so one gate's
expected status differs from its actual status, then re-run:

```bash
scripts/gates.sh; echo "EXIT=$?"
```

**Expected:** the changed gate is flagged as a transition, and the script
**exits non-zero**. Paste output and exit code.

> Beware: a full run takes ~33 minutes because the `test` gate burns its whole
> timeout. If your runner supports selecting gates, use a fast subset for
> criteria 2 and 3 and say so. Otherwise start the run and **poll until it
> finishes** — do not end your turn waiting.

### Criterion 3 — restoring goes green

Restore the baseline (or `scripts/gates.sh --write-baseline`), re-run.

**Expected:** exit 0, transition reported as resolved. Paste output.

### Criterion 4 — the schedule

Install a cron entry or systemd user timer for a nightly run. **Local machine
only** — do not touch `.github/` or any CI service.

Show it registered: `crontab -l` or `systemctl --user list-timers`.

### Then: commit

Commit `scripts/gates.sh` and the baseline on a **new branch**. Message should
describe what the runner *detects*.

**Do not commit** `gate-reports/logs/**` or the dated report files — those are
run output, and there is already a `gate-reports/.gitignore`. Check it covers
them; extend it if not.

---

## 3. Traps

1. **`docker compose run --rm` discards the container filesystem.** Capture
   stdout/stderr host-side.
2. **Do not add `--build`** to any compose command — the images
   (`qelectrotech:test`, `:asan`) are already built, and rebuilding would make
   every nightly run enormously slower.
3. **A hung gate must not hang the runner.** The existing 30-minute timeout is
   correct; `test` hitting it is data, not a bug in your script.
4. **Baseline known failures; never silently skip them.** A skipped gate looks
   identical to a passing one, which is the exact failure this task exists to
   prevent.

---

## 4. Scope

**May modify:** `scripts/gates.sh`, `gate-reports/baseline.json`,
`gate-reports/.gitignore`, a crontab entry.

**Do NOT:** fix any failing gate; modify `tests/**`, `simulator/**`,
`scenarios/**`, or `docker-compose.yml`; investigate why `test` hangs; push,
open a PR, or post anywhere.

Another session may be running in this working tree — **never `git checkout`,
`git stash`, or `git reset` here.** Create your branch with
`git switch -c <name>` only if the tree is clean of others' work; otherwise
commit from a `git worktree`.

---

## 5. Report

Report criteria 2, 3 and 4 with **real pasted output**, confirm criterion 1 from
the existing report, state which gates you baselined as known-failing, give the
total wall-clock for a full run, and flag anything in this brief that was wrong
or underspecified.
