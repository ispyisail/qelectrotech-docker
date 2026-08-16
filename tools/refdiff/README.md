# tools/refdiff — corpus-wide differential regression sweep (W3)

A sweep layer over the existing two-ref harness (`tools/abdiff`, wrapped by
`scripts/qet-ab.sh`). That harness already resolves two refs to commit shas,
builds each into a per-sha worktree/build tree (`<repo>/build-ab/<sha>/`), runs
one command in an isolated `simulator/env.py` sandbox per variant, and
classifies the result semantically. `tools/refdiff` reuses **all** of that —
it does not resolve refs, cache builds, or canon-diff anything itself; it runs
the existing per-command comparison over a whole corpus and adds the one thing
a single-command harness cannot: a *direction*.

```bash
python3 -m tools.refdiff --base master --head fix-cli-modal-dialog-hang
python3 -m tools.refdiff --base master --head HEAD~1 --corpus /path/to/one.qet
```

## What it does

For every `.qet` project in the corpus and every verb
(`--resave`, `--info`, `--export-bom`, `--export-nets`, `--export-links`):

1. build each ref **once** (a repeat run reuses the per-sha tree + ccache);
2. run the verb against each variant in its own isolated sandbox with a hard
   per-variant `--timeout`;
3. compare with `tools.abdiff.compare` (crash/timeout/exit-code/stdout/stderr/
   produced-file semantics, with the known benign-nonzero carve-outs);
4. classify the difference:
   - **`regression`** — head crashes or times out where base did not, or head
     loses elements / conductors / uuids (the resave `.qet` delta);
   - **`improvement`** — the reverse;
   - **`change`** — a semantic difference with no obvious direction (a text
     export that differs, or a same-key-set value change).

Only `regression` sets a non-zero exit code. A dated markdown + JSON report is
written under `refdiff-reports/<timestamp>/` (override with `--out`).

## Text-export normalisation (trap 2, in text form)

Saved `.qet` output is compared with `simulator/canon.diff()` — never bytes.
Text exports are byte-compared **after** `tools/refdiff/normalize.py` rewrites
them into a canonical, order-independent form:

- `--export-links` iterates `Diagram::elements()` (which walks
  `QGraphicsScene::items()`, F003/F004), so its CSV row order churns between
  processes → data rows are sorted.
- `--export-nets` numbers nets in `Diagram::conductors()` traversal order, so
  both the `"net": N` field and array order churn → net numbers are dropped and
  nets are compared as a sorted set of `{wire_no, sorted terminals}`.
- `--export-bom` is `ORDER BY label` but tie order is DB-internal → rows are
  sorted for safety.
- `--info` is already a deterministic JSON of counts → round-tripped with
  sorted keys so key order cannot matter.

None of these exports embed timestamps or absolute paths; those live in
stdout/stderr, which `tools/abdiff/compare.py` already normalises.

## Unattended mode

`tools/refdiff/nightly.sh` runs `master` vs `master@{yesterday}`, writes the
dated report every night, and prints a transition NOTICE to stdout (which cron
emails) only when the run's summary changed since the previous run. Local only
— nothing is posted, `.github/` is untouched.

```bash
37 3 * * * cd /home/user/qelectrotech-docker && tools/refdiff/nightly.sh
```

## Layout

```
__main__.py    CLI + sweep loop (python3 -m tools.refdiff)
classify.py    regression / improvement / change classification + content delta
normalize.py   canonical form for text exports (order-independent byte-compare)
report.py      dated markdown + JSON report
nightly.sh     cron wrapper: master vs master@{yesterday}, notify on transition
tests/         unit tests for classify + normalize (no binary needed)
```

`build.py` from TOOLING-PLAN.md W3.1's sketch is deliberately absent: ref
resolution and per-sha build caching already live in `tools/abdiff/build.py`
and are imported, not reimplemented.
