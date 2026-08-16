# tools/abdiff — A/B harness for QElectroTech

Implementation behind `scripts/qet-ab.sh` (LAB-PLAN.md L1). Builds two
variants of QET (each a git ref, optionally with a patch applied), runs
one command against each in isolation, and classifies the result.

```bash
scripts/qet-ab.sh --a master --b fix-cli-modal-dialog-hang \
    -- --info /home/user/qet-fix/examples/schema_indus.qet
```

## What it detects

- **CLI-visible regressions between two refs/branches**: crashes,
  hangs/timeouts, changed exit codes, changed stdout/stderr (after
  stripping sandbox tmp-dir paths and timestamps), and changed content
  in any file the command writes (`.qet`/`.elmt` compared semantically
  via `simulator/canon.py`, everything else byte-for-byte).
- **A timeout is a first-class, non-zero-exit result**, never silently
  treated as "no answer, therefore no difference." A run that exceeds
  `--timeout` on one side and completes on the other classifies as
  `a-only-fails` / `b-only-fails` before any output comparison happens.
- Whether a second variant's build benefits from ccache (reported
  timings; see `build.py`'s docstring for why a *new* build directory
  can still be fast).

## What it deliberately does not do

- **Does not drive the GUI.** Only the headless CLI verbs in
  `sources/cli_export.cpp` (`--info`, `--resave`, `--export-*`,
  `--check-elements`, `--test-ops` on branches that carry it, ...).
- **Does not accept a bare PR number** as a ref (unlike
  `scripts/asan-compare.sh`'s `-p`). Fetch the PR branch yourself first
  (`git fetch origin pull/<n>/head:pr-<n>`) and pass `pr-<n>`.
- **Does not sweep a corpus.** One command, one pair of variants, one
  verdict per invocation — for a whole-corpus differential run see
  `tools/refdiff/` (TOOLING-PLAN.md W3, not yet built as of L1).
- **Does not fail on a benign nonzero exit.** `--export-wires` /
  `--export-cables` legitimately return 1 on an empty result
  (TOOLING-PLAN.md trap #8); that specific case is excluded from the
  fail/crash classification so it does not manufacture a false
  `a-only-fails`.
- **Does not touch the caller's checkout.** Each variant builds in a
  *detached* git worktree under `<repo>/build-ab/<key>/src`, so
  `/home/user/qet-fix`'s currently checked-out branch is never changed.

## Known false-positive class

Two runs that both legitimately hang or crash **the same way** (same
`crash_kind`, same exit code) classify as `same`, not as a two-sided
failure outside the vocabulary — this is what makes `--a X --b X`
report `same` even for a command that hangs on `X`. If the two sides
fail for *different* reasons (e.g. one times out, the other ASan-crashes)
that is `differs`, since both are real information about the difference
between the variants.

## Layout

```
build.py    resolve ref -> sha, build a worktree + build tree, keyed by sha (+patch hash)
run.py      run the command in a simulator/env.py sandbox with a hard per-variant timeout
compare.py  classify same / differs / a-only-fails / b-only-fails
report.py   text + JSON rendering
__main__.py CLI glue (python3 -m tools.abdiff, wrapped by scripts/qet-ab.sh)
tests/      unit tests for compare.py's classification logic (no binary needed)
```
