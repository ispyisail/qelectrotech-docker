# Coverage audit — what the tooling cannot see

**L5, 2026-08-16.** Analysis, not construction. The question:

> What classes of QET defect can no existing tool observe, and which two or
> three are worth making observable?

Every tool in this repo works on **files** or the **headless CLI**. That was the
right call — the file layer has now found five real defects while a 3,500-line
GUI-driving harness (`scenarios/`) found none. But it means whole categories are
invisible, and nobody had written down which.

---

## 1. The observation surface as it stands

| Tool | Observes | Blind to |
|---|---|---|
| `simulator/` sweep | malformed-input crashes, save corruption, NaN/Inf | anything needing interaction |
| `tests/determinism` | save idempotence (I1, still failing), data preservation (I3) | anything not expressible as a resave |
| `tests/asan-regression` | leaks in four specific paths | everything else |
| `scripts/qet-ab.sh` | semantic diff between two refs, one command | whatever the command doesn't cover |
| `scripts/cli-sweep.sh` | **exit codes** of every verb × every project | whether the output is *correct* |
| `tools/qet-lint` | NaN/Inf, illegal control bytes, duplicate uuids, unparseable XML | anything requiring the app to run |
| `--test-ops` lab binary | select, delete, move, rotate, rotate_texts, set_property, undo, redo | see gap 2 |
| `fuzzer/` | crashes reachable by random clicking | anything non-crashing |

---

## 2. Recommended: three gaps worth closing

Ranked by (likelihood a real defect lives there) × (cost to make observable).
Each names a **defect that actually shipped**, because a gap with no plausible
defect behind it is not worth closing however real the gap is.

### Gap 1 — Export *fidelity*. Nothing reads what an export produced.

`cli-sweep.sh` records exit code, wall time, RSS and fd count for every verb ×
project. **It never opens the output file.** No oracle in the repo reads a
`.pdf`, `.svg`, `.png`, or any text export. "QET produced a BOM" is verified;
"the BOM is correct" is not.

**The defect that proves it: PR #724, "Fix wire-name export doubling every
conductor's count."** The export ran, exited 0, produced a file — with every
count doubled. Every check in this repo passes that. It was closed unmerged,
so the underlying question is still live.

**Cost: low for text exports.** `--export-bom`, `-nets`, `-links`, `-wires`,
`-cables` are parseable, and the counts are checkable against the `.qet` the
export came from — conductor count, element count, net count. That is an
oracle, not a snapshot test, so it survives cosmetic format changes.

PDF/PNG/SVG *rendering* fidelity is a different and much more expensive
problem. **Not recommended** — see §3.

### Gap 2 — Multi-folio. The op exists; nothing drives it.

**13 of 23 example projects are multi-folio.** L2 added a `diagram` op to
`--test-ops` so operations can target folios beyond the first. Grepping for
anything that exercises it finds exactly two hits, both in
`test_executor_ops.py`, both asserting the *JSON shape* of the op:

```python
self.assertEqual(diagram_op(1), {"op": "diagram", "index": 1})
```

**Nothing has ever driven folio 2 against a real binary.** Every oracle result
in this repo — including F005's rotate-undo defect — is folio-1 only.

**The defects that prove it:** PR #732 (bugtracker #238, *"summary lists folios
in the wrong order"*) and PR #736 (*"folio report link picker showing candidates
as blank rows"*), both open. Cross-folio behaviour is also where PR #659 parked.

**Cost: lowest of the three.** The op is built and merged. This is extending
existing sweeps to iterate folios rather than assuming index 0 — a loop, not a
new subsystem.

### Gap 3 — The database and the file are never compared.

QET builds a SQLite database at load (`sources/dataBase/projectdatabase.cpp`).
Exactly **one** invariant is checked anywhere: `element_count ==
element_info_count`, in `fixture_element_info_orphan.py`. Nothing verifies that
the DB and the `.qet` agree about conductors, terminals, cross-references, or
anything else.

**The defect that proves it: PR #664**, orphan `element_info` rows after
delete/undo. It was **found by a user reporting lag**, not by tooling — and the
one narrow check that exists today was written *afterwards*, from that bug.

**Cost: moderate.** Needs the DB read alongside the file, and the two projected
into comparable shapes. But the payoff is a genuine cross-check: two independent
representations of the same project that must agree, which is a stronger oracle
than either alone.

---

## 3. Deliberately not recommended

Recording these so the same ground is not re-litigated.

| Gap | Why not |
|---|---|
| **GUI interaction state machines** (drag, rubber-band, in-place edit) | Genuinely uncovered, and genuinely expensive. `scenarios/` spent ~3,500 lines here for zero defects. Six failed GUI-automation attempts during F001 hit four separate environmental blockers before touching the bug. The cost is not the automation, it is that the environment fights back. |
| **PDF/PNG/SVG render fidelity** | Comparing rendered output needs reference images, tolerance tuning, and font/DPI stability. High maintenance, and the failure mode is usually "diff is noisy" rather than "bug found". Text-export fidelity (gap 1) covers the same defect class far more cheaply. |
| **Element / terminal-strip / title-block editors** | Uncovered, but low change traffic and each needs its own harness. Revisit only if a defect cluster appears there. |
| **Two instances / file changed under the app** | Real (SingleApplication has bitten this project repeatedly), but it is an *environment* hazard the tooling already guards against via `simulator/env.py`. A defect here would be in QET's file-watching, which is a narrow surface. |
| **Undo/redo composition beyond `--test-ops`** | Now largely *covered*, not a gap — W5-prereq unblocked O4 and it immediately found F005. The remaining limit is op vocabulary, which is incremental work, not a missing capability. |

---

## 4. Honest caveats

- **Two of these three are cheap because earlier work already paid for them.**
  Gap 2 needs a loop because L2 built the op; gap 1 needs a parser because
  `cli-sweep` already runs every verb. Neither would have ranked this high a day
  ago.
- **Gap 3 is the one most likely to find something and most likely to take
  longer than estimated.** Reading QET's SQLite schema from outside means
  tracking a schema that upstream can change without notice.
- **"No tool observes this" is not the same as "this is worth observing."**
  Most of §3 is genuinely uncovered. The three in §2 are separated from them by
  having a shipped defect behind them, not by being bigger holes.
- I did **not** survey the ~75 untouched bugtracker entries for defect clusters
  before ranking. W4 is building that corpus now; if it shows a cluster in a §3
  area, this ranking should be revisited rather than trusted.
