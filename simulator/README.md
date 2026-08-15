# QET simulator

An oracle-rich test harness for QElectroTech, implementing Phases 1–2 (and
part of §5–6) of [`SIMULATOR-DESIGN.md`](../SIMULATOR-DESIGN.md). Read that
document first — this file is "how to run it and what it actually found,"
not the design rationale.

**Status:** built, self-tested (99 unit tests), and run for real against a
Release build of `qelectrotech-source-mirror` master. Every claim below was
verified against real output, not assumed — where a claim turned out to be
wrong during development, this file says so.

## What's here

```
simulator/
  env.py       isolated sandbox (HOME/XDG/offscreen) + SingleApplication guard
  proc.py      run the CLI binary, classify crash/timeout/sanitizer/Q_ASSERT
  canon.py     canonical projection of a .qet file -- the core comparison logic
  trace.py     serialisable, replayable Step/Trace records
  mutate.py    6 text mutators + 2 byte mutators, each with exact replay
  oracles.py   O1/O2/O3/O6/O9 as named, composable Finding-producing functions
  shrink.py    ddmin over a Trace
  runner.py    corpus x mutators -> resave -> oracles, with quarantine, auto-shrink,
               and the O9 double-run determinism self-check on every sweep
  __main__.py  `python3 -m simulator sweep|replay|selftest`
  fixtures/    known-bug fixtures (design doc §10)
  tests/       99 unit tests, no binary needed except test_proc.py's real-subprocess tests
  reports/     JSONL sweep output (gitignored)
```

## Quick start

```bash
# No binary needed -- pure logic tests:
python3 -m simulator selftest

# Needs a Release build with cli_export.cpp (any recent build has it):
python3 -m simulator.fixtures.fixture_determinism --binary /path/to/qelectrotech

python3 -m simulator sweep --binary /path/to/qelectrotech --iterations 150 --seed 1

python3 -m simulator replay --binary /path/to/qelectrotech --trace simulator/reports/<file>.json
```

## Design decision, stated once here since it's easy to misread the code
without it: **O2/O3/O6-delta are checked between two CONSECUTIVE resaves of
content QET has already accepted (resave1 -> resave2), never between the raw
mutated seed and resave1.** QET is expected to change or reject a mutated
seed on load -- that's the point of feeding it adversarial input, not a
violation. What must hold is that once QET has processed something once,
processing it again must be stable. See `runner.py`'s module docstring.

---

## What was actually found

### 1. Two real, previously-known bugs, rediscovered independently

Running `fixture_determinism.py` against the real corpus
(`qet-fix/examples/*.qet`, 23 files) using nothing but `canon.py` and
`oracles.py`:

- **21 of 23 files fail O2** (resave is not idempotent). This is
  `tests/determinism/check.py`'s documented I1 gap, confirmed independently.
  The 2 clean files (`ShellyParts.qet`, `pinball_williams_em.qet`) have zero
  conductors, so there's nothing for the bug to act on -- the harness isn't
  passing those by luck, there's genuinely nothing to find.
- **`schema_indus.qet` hangs** on a plain `--resave`, caught by the generic
  O1 timeout oracle. This is the exact hang already documented in
  `tests/determinism/check.py`'s own docstring -- rediscovered without the
  harness having been told about it specifically.

### 2. A more precise root cause than what was previously documented

`tests/determinism/check.py` attributes I1 to `Diagram::toXml` iterating
`QGraphicsScene::items()` (stacking order, not content order). Investigating
what `canon.diff()` actually reported (`conductors key-set differs:
only_a=['0-43', ...] only_b=['0-48', ...]`) led to the real mechanism:

`Conductor::toXml()` (`sources/qetgraphicsitem/conductor.cpp:1052`) writes
terminal identity two ways depending on whether the terminal has a uuid:

```cpp
if (terminal1->uuid().isNull()) {
    // legacy method to identify the terminal
    dom_element.setAttribute("terminal1", table_adr_id.value(terminal1));
} else {
    dom_element.setAttribute("terminal1", terminal1->uuid().toString());
    // + element1, element1_label, terminalname1, ...
}
```

`table_adr_id` is a fresh `QHash<Terminal*, int>` built new on every save, so
the legacy path's numeric IDs are a serialization artifact, not stable
content. Measured across the full 23-file corpus: **2,608 legacy references
vs 450 uuid-based ones** -- the non-deterministic path is the dominant case
in real files, not an edge case. Not fixed here (that's a QET source change,
out of scope for the harness); recorded precisely so it doesn't need
re-deriving.

### 3. Bugs the harness found in itself, while stress-testing QET

Worth listing separately, because a testing tool that only ever reports
*other* code's bugs either has none of its own (unlikely) or isn't being
tested hard enough. Both were found by the sweep, not written as unit tests
first:

- **`grid_regressions()` crashed on a NaN position** (`round(nan / grid)`
  raises `ValueError`). Reachable because `o6_nan_inf` and `o6_grid_regression`
  are separate oracles and a NaN can reach the second one. Fixed in
  `canon.py`'s `on_grid()`, with a regression test.
- **The crash-detection regex would never have matched real sanitizer
  output.** Copied from `fuzzer/monitor.py`:
  `r"=+\d+=+\s+ERROR:..."` requires whitespace between `==` and `ERROR:`.
  Real ASan/LSan output (`tests/asan-regression/raw/*.out`, verified with
  `cat -A`) has none: `==22==ERROR: LeakSanitizer:`. **This is also present
  in `fuzzer/monitor.py`, not just this harness's copy** -- flagged here,
  not fixed there, since that's a different subsystem and a decision about
  whether/how to fix it belongs to whoever owns that file. Fixed in this
  harness's `proc.py`, verified against every real `.out` sample in
  `tests/asan-regression/raw/`.

### 4. 150-iteration adversarial mutation sweep: two new, reproducible bugs

Two sweeps were run (150 iterations each, 6 text + 2 byte mutators, single
mutation per seed, real binary).

**First sweep** (before corpus quarantine existed) reported "7 crashes" --
investigation showed **all 7 traced to the one already-known
`schema_indus.qet` hang** (confirmed by cross-referencing the JSONL report's
`seed_name` field, not assumed), re-triggered by random seed selection
regardless of what mutation was applied. That file hangs unconditionally,
mutated or not, so re-testing it repeatedly spent sweep budget without
searching anything new. Fixed by adding `health_check_corpus()`: every seed
is verified to round-trip a single `--resave` cleanly before being used, and
known-broken seeds are quarantined and reported once instead of
re-discovered on every random pick.

**Second sweep**, quarantine active (`schema_indus.qet` correctly excluded,
confirmed in the run's own summary), found **4 crashes reducing to 2
distinct, independently-reproduced bugs** -- not re-discoveries of anything
previously documented:

**a) A single NaN coordinate causes an infinite CPU-spin, not a crash or a
clean rejection.** Hit on 3 separate seed files
(`grafcet.qet` x, `Habitat-Schemas_developpes.qet` y,
`iso_sfc_example.qet` y). Reproduced independently of the sweep machinery
(direct `apply_resolved` + `run_cli`, not through `runner.py`), and
confirmed via `/proc/<pid>/stat` that this is a genuine busy loop, not a
blocked wait: **2.98 of 3.00 wall-clock seconds were user CPU time.**
Minimal repro: `simulator/reports/findings/nan_coordinate_hang_grafcet.qet`
-- a single `x="nan"` on one element, everything else untouched.

**b) A single bit flip that turns XML whitespace into an embedded NUL byte
causes a SIGSEGV.** Byte offset 51565 in `cablage-eclairages_sikli-v5.qet`:
flipping bit 5 of a space character (`0x20` -> `0x00`) between two
`</conductor>`/`<conductor` tags -- not inside any attribute value, just
indentation whitespace. **Reproduced 3/3 runs**, always `signal 11`.
Minimal repro: `simulator/reports/findings/nul_byte_segv_cablage.qet`.

Both are recorded with their exact mutation args in
`simulator/reports/findings/manifest.json` for exact replay via
`python3 -m simulator replay`. Root-causing either in QET's C++ is out of
scope for this pass -- the harness's job was to find and minimally
reproduce them, which it did; diagnosing/fixing them is separate follow-on
work.

**How to read this honestly:** 150 single-mutation trials against 23 files
is a small sample of QET's actual input space, and it surfaced two
independent, reproducible bugs -- a real "should break, and did break"
result, not a null result dressed up as one. It does not mean these are the
only two, or that deeper mutation chains (`--chain-length N`, not exercised
here) or coverage-guided steering (`SIMULATOR-DESIGN.md` §7, not built)
wouldn't find more.

### 5. O9 self-check (wired in during a post-review hardening pass): resave is run-to-run nondeterministic on legacy seeds

The O9 double-run self-check (design doc §3, "check this first, on every
run") flagged its own corpus on its first real run: identical input, two
separate processes, different canonical output (`o9_deterministic: false`).
Two distinct signatures, both probed and attributed rather than assumed:

- **67 fresh conductor uuids per first save.** A legacy file whose
  conductors lack uuids (741.qet: all 67 of them) gets a new random uuid
  assigned to every `<conductor>` on first load. Probed: stable from the
  second save on (resave1 -> resave2 keeps the same 67 uuids, same order),
  and elements/diagrams are NOT assigned uuids this way (11 uuid-less
  elements in the seed stay uuid-less). One-time migration churn, not
  ongoing instability.
- **Legacy terminal-ID churn** -- the I1 mechanism already documented in §2:
  `table_adr_id` is a pointer-keyed `QHash<Terminal*, int>` rebuilt per save,
  so the numeric `terminal1`/`terminal2` IDs differ across process runs.

Consequence for the harness: on a legacy-heavy corpus O9 reports these two
findings on every sweep and `o9_deterministic` stays `false` even though the
harness's own Python pipeline is deterministic by construction. That is
correct behaviour, not a defect -- the check's job is to expose cross-run
nondeterminism, and it does. It cannot be expected to pass until the I1 bug
is fixed upstream (and until first-save conductor-uuid migration is made
deterministic, e.g. uuid-from-content). The findings are recorded at
`iteration: -1` in the JSONL and do not block the sweep; on seeds with no
legacy identifiers there is nothing for it to flag.

---

## Known gap: three of the four §10 fixtures need more than the CLI can give

`SIMULATOR-DESIGN.md` §10 names four known bugs as the harness's success
criteria. Only one is reachable through what exists today:

| # | Bug | Reachable via L1 CLI? |
|---|---|---|
| 1 | PR #664 -- `element_info` orphan row | **No.** The project database is `QSqlDatabase::addDatabase("QSQLITE", ...)` with **no `setDatabaseName()` call** (`sources/dataBase/projectdatabase.cpp:255`) -- confirmed by reading the source, not assumed -- so it defaults to Qt's `:memory:` SQLite and never touches disk. Nothing to inspect after the process exits. |
| 2 | PR #660 -- group rotation drifts off-grid | **No.** `RotateSelectionCommand` is a `QUndoCommand`; there is no CLI verb that rotates a selection. `canon.grid_regressions()` is ready to check the *result* the moment there's a way to *produce* one. |
| 3 | PR #668 -- placeholder label persisted | **No.** Needs live label editing, which is a GUI/undo-stack operation. |
| 4 | Determinism gap (`resave` not idempotent) | **Yes** -- see §1 above. |

This isn't a design failure; it's the design doc's own L1/L2/L3 distinction
being confirmed empirically rather than asserted. Two ways to close the gap,
both already named in `SIMULATOR-DESIGN.md`:

- **L2 (GUI):** reuse `fuzzer/actions/*` (already implements rotate,
  add/delete element, undo/redo) for scripted -- not random -- specific
  sequences, using `canon.py` on the saved file as the oracle instead of
  screenshots.
- **L3 (new CLI hook):** `sources/cli_export.cpp` already runs a real
  `QApplication` under `QT_QPA_PLATFORM=offscreen` (confirmed: CLI mode
  works headlessly today), so a new dev-only verb that constructs a
  `Diagram`, applies a named `QUndoCommand`, and dumps state is technically
  straightforward -- but it's a QET source change, not something to add
  silently while "building the simulator."

Also confirmed and *not* pursued in this pass: `pathological_titleblock_columns()`
(the PR #679-crash-family generator in `mutate.py`) is built and
unit-tested for correct output shape, but `TitleBlockTemplate::minimumWidth()`
-- the function PR #679 crashed in -- has exactly one caller in the entire
codebase (`sources/titleblock/templateview.cpp:998`,
`TitleBlockTemplateView::updateDisplayedMinMaxWidth()`), which is GUI-editor
tooltip code with no CLI path to it. Same L1/L2 gap as above; recorded so
the generator function doesn't look silently unused.

---

## What wasn't built (Phases 3–7 of the design doc)

- **O4, undo/redo metamorphic testing** -- the highest-value oracle in the
  design doc -- is blocked on the same L2/L3 gap as fixtures #1-3 above.
  Nothing to build until there's a way to drive an undo command headlessly.
- **Coverage-guided steering** (§7) -- needs an instrumented build
  (`-fprofile-instr-generate`) not attempted here.
- **The GUI (L2) executor** -- deliberately last in the design doc's phasing
  for the reasons stated there (least observable, least reproducible layer).

## Running the tests

```bash
python3 -m simulator selftest          # 99 tests, no binary, ~10s
```

`test_proc.py`'s `TestRunCliReal` class spawns real subprocesses
(`/usr/bin/true`, `/usr/bin/sleep`, a Python one-liner that SIGSEGVs itself)
to exercise the real subprocess/timeout/signal path without depending on a
qelectrotech build; everything else is pure-Python logic against real
`.qet` files already in `qet-fix/examples/`.
