---
name: qet-repro
description: Turn a vague QElectroTech bug report into a deterministic, minimal reproduction — headless first, GUI only when forced. Load when reproducing a bugtracker entry, confirming a user-reported symptom, or checking whether a reported bug still exists on master.
---

# Reproducing a QET bug

Load `qet-env` first. The order below is deliberate: each step is cheaper and
more reliable than the one after it.

## 1. Does it still exist?

**If it came from the bugtracker, check our own merged PRs first** — see
`qet-triage` step 0. ~16 bugtracker numbers are already fixed from this
account, and a `gh pr list` search settles it in five seconds where a repro
attempt costs a build. Search on the phrase `bugtracker #NNN`, not the bare
number: GitHub PR/issue numbers collide with bugtracker numbers constantly.

**Then try current master.** Three hand-picked bugtracker entries in a row
(#256, #278, #288) turned out to be already fixed.

```bash
git -C /home/user/qet-fix log --oneline -1 master
scripts/qet-fastbuild.sh build /home/user/qet-fix/build-fast
```

If it does not reproduce, that is a **result**. Record it precisely — *"not
reproduced on `<sha>` via `<exact command>`"* — and report it. Do not assert
"fixed" without naming the command you ran.

## 2. Headless first

If the symptom touches load, save, export, or the element collection, it is
reachable without a GUI. This is faster, deterministic, and gives clean output.

```bash
QT_QPA_PLATFORM=offscreen timeout 120 \
  /home/user/qet-fix/build-fast/qelectrotech --resave in.qet out.qet
```

Verbs: `--resave`, `--info`, `--check-elements`, `--export-pdf|png|svg|bom|nets|links|wires|cables`, `--set-titleblock`.

- **Always use a timeout.** A version-incompatible project raises a modal
  dialog during load and hangs every verb forever (PR #737).
- `--export-wires` / `--export-cables` **exit 1 on an empty result**, which is
  indistinguishable from a real failure. Do not read that as a crash.
- `--check-elements` takes an element file or directory, **not** a project.

For anything scripted, drive it through `simulator/proc.py` `run_cli()` inside
a `simulator/env.py` sandbox rather than raw `subprocess` — you get crash and
timeout classification and real isolation for free.

## 3. Save/load symptoms have dedicated tools

Do not eyeball XML diffs.

```bash
docker compose run --rm qet-determinism        # did a save lose or reorder data?
python3 -c "from simulator import canon; ..."  # canon.diff(a, b) — semantic diff
```

`canon.canonicalize()` ignores cosmetic churn (colours, fonts) and keeps
identity-bearing state, so a diff it reports is real.

**Known artifact, not a bug:** the first save of a legacy project invents
conductor UUIDs (67 of them on `741.qet`), stable from the second save on.
Resave once before comparing.

## 4. GUI only when forced

If the symptom genuinely needs interaction:

```bash
docker compose run --rm qet-debug      # GDB attached
```

Do **not** build GUI automation for this. `scenarios/` exists, is finished, and
is not to be extended — it cost ~3,500 lines and found zero QET defects.

## 5. Minimise before reporting

A one-line repro is worth ten times a project file.

- `simulator/shrink.py` `ddmin()` shrinks a mutation trace automatically.
- By hand: bisect by folio, then by element. **Do not** infer the culprit from
  log position — `out` in `cli_export.cpp` is a buffered `QTextStream`, so the
  last line in a redirected log is the last *flushed*, not the last processed.
  Bisect by directory, then by file.
- Validate suspect XML with Python's `ElementTree` too. If Python rejects a
  file that Qt segfaults on, *that contrast is the finding* — it separates "the
  file is bad" from "Qt mishandles bad input", and they are different bugs in
  different repos.

## 6. Write it down

Every confirmed reproduction gets an entry in `FINDINGS.md`: exact command,
binary sha, input file (committed if small), expected vs actual, and whether it
is already known upstream.
