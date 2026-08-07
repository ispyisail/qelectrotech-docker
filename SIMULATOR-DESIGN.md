# QET simulator — design document

A stateful, oracle-rich test simulator for QElectroTech: drives the application
through long realistic sessions and **checks properties that must hold**, rather
than only waiting for it to crash.

**Status:** design only, nothing built. Written to be handed to an implementer.
**Grounded against:** `qelectrotech-source-mirror` master `4ff2be3f4`, and the
existing `fuzzer/` in this repo (2,003 lines).

---

## 1. Thesis

> The existing fuzzer solved the **driving** problem — how to make the app do
> things. The valuable, unbuilt work is the **oracle** problem — how to know
> something went wrong when the app *doesn't* crash.

`fuzzer/fuzzer.py` picks from ~40 weighted actions and clicks. Its only oracle
is `monitor.py`: process died, or a sanitizer printed. That finds memory-safety
bugs and hard asserts. It is structurally incapable of finding anything else.

### Evidence: score the real defects found in this project

| Defect | Symptom | Crash-only fuzzer finds it? |
|---|---|---|
| PR #664 — `removeElement()` never cleaned `element_info` | orphan DB rows, growing lag | **No** — no crash |
| PR #660 / disc. #618 — group rotate around fractional pivot | elements permanently off-grid | **No** — no crash |
| PR #668 — placeholder written into stored data | corrupted `.qet` on save | **No** — no crash |
| `tests/determinism` — `resave` not idempotent | save reorders content | **No** — no crash |
| PR #679 — title block `0.0/0.0` → NaN | `Q_ASSERT` abort | **Yes** |

**One in five.** Every other defect was found by a human reasoning about an
invariant. Each of those invariants is mechanically checkable. That is the
entire argument for this design.

---

## 2. Substrate: drive at the most observable layer

Three possible drive surfaces, ranked by observability:

| Layer | Coverage | Observability | Deterministic replay |
|---|---|---|---|
| **L1 — headless CLI** (`--resave`, `--info`, `--export-*`, `--check-elements`) | load / transform / save only | **total** (files + stdout) | **exact** |
| **L2 — GUI via xdotool** (today's fuzzer) | everything | poor (pixels) | no (timing) |
| **L3 — test IPC hook** | everything | total | exact |

`sources/cli_export.cpp:64-80` already exposes eleven headless commands. That is
a far better substrate than pixel-poking, and it is already there.

**Design rule: push every check that *can* live at L1 down to L1.** Use L2 only
for things that genuinely require the GUI (interaction state machines, dialogs,
drag-and-drop). Most invariants in §3 are L1-checkable.

L3 does not exist. It is what `SCRIPTING-RFC.md` proposes, and **a test harness
is one of the strongest arguments for that RFC** — worth noting in the RFC
itself, because "we need this to test the app properly" is a better motivation
than "users want macros."

### Hard isolation requirement

QET uses `SingleApplication`. Launching a second instance **forwards the request
to the running one instead of starting fresh**. Combined with
`network_mode: host` this has already cross-contaminated test launches with a
live container twice in this project.

The simulator MUST:
- run with its own `HOME`, `XDG_CONFIG_HOME`, **and** `XDG_DATA_HOME`
  (`XDG_CONFIG_HOME` is set on this machine — overriding `HOME` alone is not
  enough)
- use a private `DISPLAY`
- assert no other `qelectrotech` process is reachable before starting
- never use `network_mode: host`

Getting this wrong doesn't fail loudly — it produces results from the wrong
binary. Make it a startup precondition that aborts.

---

## 3. The oracle catalogue

This is the core of the design. Each oracle is independent, cheap to add, and
maps to a defect class.

### O1 — Crash / sanitizer *(exists)*
Process death, ASan/UBSan/TSan output. Keep `monitor.py` as-is.

### O2 — Round-trip idempotence
`resave(resave(x)) ≡ resave(x)` byte-for-byte.
Already implemented in `tests/determinism/check.py` (I1). **Known to fail on
master** — `Diagram::toXml` iterates `QGraphicsScene::items()`, which returns
stacking order, not content order. Fold that harness in rather than rewriting.

### O3 — Semantic preservation
Element / conductor / terminal counts and the full UUID set survive a resave.
Also in `check.py` (I3). An O3 failure is data loss — always a bug.

### O4 — Undo/redo metamorphic *(highest value, not built)*
```
s₀ --op--> s₁ --undo--> s₀'     assert canon(s₀) == canon(s₀')
        s₁ <--redo-- s₀'        assert canon(s₁) == canon(s₁')
```
Applies to **every** undoable operation, needs no reference implementation, and
catches a huge class of "command doesn't fully restore state" bugs. QET has ~40
`QUndoCommand` subclasses; each is a hypothesis this oracle tests for free.

Run it at two depths: single-step, and *N*-step (do 20 ops, undo 20, compare to
start). The N-step form catches commands that are individually correct but don't
compose.

### O5 — Referential integrity
- every `element_info.element_uuid` has a matching `element` row *(this is
  exactly PR #664)*
- every conductor references two terminals that exist
- every master/slave cross-reference points to a live element
- no diagram references a missing title block template

Checkable from the SQLite DB (`sources/dataBase/projectdatabase.cpp`) and from
the saved XML independently — **and they should agree with each other**, which
is itself an oracle.

### O6 — Geometric invariants
- an item on the grid stays on the grid after any rotate/move/undo cycle
  *(this is exactly PR #660)*
- `rotate90` applied 4× is the identity
- `rotate(θ)` then `rotate(−θ)` is the identity
- copy → paste → delete-pasted is the identity
- items never acquire NaN/Inf coordinates *(the class PR #679 sat in)*

The NaN check is cheap and should run on every state dump.

### O7 — Liveness
`EventLoopWatchdog` (PR #665) already detects stalls via `QTimer` lateness. Wire
its output into the crash log as a first-class failure, not a warning. A UI that
hangs for 5 s is a defect even though nothing crashed.

### O8 — Resource conservation
Run a cycle that must be net-zero (add 100 elements, delete them, undo, redo,
undo), then compare RSS, FD count, and QObject count to baseline. Growth beyond
a threshold across repeated cycles is a leak.

Run under ASan/LSan for exact attribution; the counting version is for long
soak runs where sanitizer overhead is too slow.

### O9 — Determinism
Same seed ⇒ identical trace ⇒ identical final canonical state. If this fails the
simulator itself is unreliable and every other result is suspect. **Check this
first, on every run.**

### O10 — Differential
Same logical change applied two ways (GUI vs CLI; or v0.100 vs v0.90 binaries)
should converge to the same canonical state. Version-differential mode doubles
as automated regression detection.

---

## 4. Architecture

```
                    ┌─────────────────────────────┐
                    │   Scenario / generator      │  weighted grammar,
                    │   (seeded, deterministic)   │  corpus-seeded
                    └──────────────┬──────────────┘
                                   │  Trace = [Command]      ← first-class data
                    ┌──────────────▼──────────────┐
                    │        Executor             │
                    │  L1 CLI  │  L2 GUI  │ L3 IPC│
                    └──────────────┬──────────────┘
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
     ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
     │ Reference model│   │ State extractor│   │ Fault injector │
     │ (pure, in-proc)│   │ .qet XML + DB  │   │ ENOSPC, kill…  │
     └────────┬───────┘   └────────┬───────┘   └────────────────┘
              └────────┬───────────┘
                       ▼
              ┌────────────────┐        ┌──────────────┐
              │    Oracles     │──fail──▶   Shrinker   │──▶ minimal repro
              │    O1…O10      │        │    (ddmin)   │
              └────────────────┘        └──────────────┘
```

### 4.1 Trace as data — the non-negotiable part

Today's fuzzer logs prose to `actions.log`. A report of *"crashed after 4,312
actions, seed 12345"* is close to useless.

Commands must be **serialisable, replayable records**:

```json
{"seq": 41, "op": "rotate_selection", "args": {"uuids": ["a1b2…"], "angle": 90},
 "pre_hash": "9f2c…", "post_hash": "3d81…"}
```

Requirements:
- record the **resolved** arguments (the actual UUID and coordinate used), never
  "a random element" — otherwise replay diverges
- replay must reproduce the failure without the RNG
- traces are the artefact a bug report attaches

Everything else in this design is worth more if this is right, and worth much
less if it is wrong. Build it first.

### 4.2 Reference model

A small pure model of what the project *should* contain: folios; per folio the
set of elements (uuid, type, position, rotation); conductors (uuid, two terminal
refs); texts; per-element info fields; undo depth.

The model is updated by each command's *intent*. It does **not** need to model
rendering, layout, or anything visual — only what the canonical projection
compares.

### 4.3 Canonical projection

Comparing raw `.qet` files is too strict (timestamps, `saveddate`, element
ordering). Define `canon(state)` — a sorted, normalised projection:

- UUID sets, sorted
- positions rounded to the configured grid, as integers
- volatile fields (`saveddate*`, `savedtime`, `savedfilepath`) stripped
- element info as sorted key/value pairs

`canon()` is the single most important piece of code in the harness: too strict
and it drowns you in false positives; too loose and it hides real bugs. **Write
it with tests of its own**, including a test that it *does* detect a
deliberately corrupted state.

### 4.4 Shrinking

On failure, run delta-debugging (ddmin) over the trace: repeatedly drop
subsequences and re-run, keeping any shorter trace that still fails. Turns 4,000
actions into 3.

This is the difference between a tool people use and a tool that produces
unreadable logs nobody reads. It only works if §4.1 is done properly.

---

## 5. Adversarial inputs — "break stuff that should break"

### 5.1 Pathological but *valid* projects
Generate, don't hand-write:
- 10,000 elements on one folio; 500 folios; 50,000 conductors
- every element carrying maximum-length info fields
- deeply chained master/slave cross-references, including **cycles**
- a conductor network that is one fully-connected component
- title blocks whose columns are all relative and sum to exactly 100 %
  *(this is PR #679's crash — generate the whole family: sums of 0, 99, 100,
  101, 1000; zero columns; one column)*

### 5.2 Text and encoding
Every user-visible text field is an injection point. Fuzz with: RTL (Arabic /
Hebrew — QET ships `ar` translations), combining marks, zero-width joiners,
4-byte emoji, `%`-sequences that collide with the label mini-language
(`%{label}`, `%prefix`, unbalanced `%{`), XML metacharacters, 10 MB strings, NUL
bytes.

The `%`-collision class is specific and likely: four separate mini-languages
share `%` syntax (see `SCRIPTING-RFC.md`). Feeding one's syntax to another is a
targeted test, not a random one.

### 5.3 Malformed files
The EDZ fuzzer (`edz-fuzzer/`) already does this for `.edz`. Extend the same
pattern to `.qet`, `.elmt`, `.titleblock`: truncation at every byte offset, bit
flips, XML bombs (billion laughs), wrong-but-plausible schemas, valid XML with
semantically impossible content (conductor referencing its own terminal twice).

### 5.4 Environment hostility
- locale switching mid-session (**French is the `tr()` source language** — the
  fallback path is the interesting one)
- `LC_NUMERIC=de_DE` — decimal-comma locales are a classic source of
  coordinate-parsing corruption; QET writes positions with `QString::number()`
- clock jumps backwards mid-session (title block `saveddate`, backup rotation —
  PR #654)
- read-only collection directory; missing common elements dir
- 30 000 elements in the user collection (startup indexing is eager and
  multithreaded — `elementscollectionmodel.cpp:297`)

### 5.5 Concurrency
- two windows on one project
- element editor open on an element while the diagram deletes it
- `SingleApplication` forwarding while a modal dialog is up
- TSan runs specifically around collection loading, which is the one place QET
  uses `QtConcurrent::map`

---

## 6. Fault injection

Classic source of silent data loss, and no fuzzer here does it today.

| Fault | How | What it should prove |
|---|---|---|
| Disk full mid-save | small tmpfs, or `LD_PRELOAD` returning `ENOSPC` on `write` | original file intact, error surfaced |
| `SIGKILL` mid-save | kill during the write window | original intact or recoverable backup |
| Read-only target | `chmod a-w` | clean refusal, no partial file |
| I/O error on read | fault-injecting FUSE mount | no crash, clear message |

**Verified during this design:** `QET::writeXmlFile()` (`sources/qet.cpp:672`)
uses `QSaveFile`, so saves *are* atomic — the naive "truncate then write" data
loss class does not apply. Do not spend time there.

The remaining hypothesis worth testing: `QSaveFile` only persists on
`commit()`, and a missed/ignored commit failure silently discards the save
while the UI reports success. Test that specifically, at the `ENOSPC` boundary.

---

## 7. Making random search actually effective

Random clicking plateaus quickly. Two multipliers:

**Coverage-guided steering.** Build an instrumented binary
(`-fprofile-instr-generate -fcoverage-mapping`, or `--coverage`). After each
scenario, diff edge coverage; keep traces that reached new edges as seeds and
mutate them. This is the difference between AFL and `rand()`, and it applies to
GUI action sequences just as well as to byte inputs.

**Corpus seeding.** Start from real projects (`examples/*.qet`, 8,755 shipped
elements) rather than empty documents. Most interesting states are reachable
only after a realistic amount of structure exists.

**Bisect on failure.** When a property regresses, auto-run `git bisect` over the
trace to name the introducing commit. Cheap to add once traces replay reliably,
and turns the tool from "reports bugs" into "reports causes."

---

## 8. Phasing

Each phase is independently useful. Do not start one before the previous builds
and runs.

**Phase 1 — Trace + replay + canon (foundation).**
Serialisable commands, deterministic replay, `canon()` with its own tests, O9
(determinism) as the self-check. No new oracles yet. *Nothing else is worth
building until a failure can be replayed.*

**Phase 2 — L1 oracle harness.**
Absorb `tests/determinism/check.py` (O2, O3), add O5 (referential integrity) and
O6's NaN/grid checks. All headless, all CI-able, no display. This is where the
cost/benefit is best.

**Phase 3 — Undo/redo metamorphic (O4).**
Highest-value new oracle. Needs Phase 1's replay and Phase 2's `canon()`.

**Phase 4 — Shrinker.**
ddmin over traces. Makes everything before it usable by humans.

**Phase 5 — Adversarial generators (§5) and fault injection (§6).**

**Phase 6 — Coverage-guided steering (§7).**

**Phase 7 — GUI layer.** Fold in the existing `fuzzer/` as an L2 executor behind
the same trace/oracle interface. Deliberately last: it is the least observable
and least reproducible layer, and most invariants don't need it.

---

## 9. Non-goals

- **Not a replacement for `fuzzer/`.** It becomes the L2 executor in Phase 7.
- **Not a unit-test framework.** `tests/` (Catch2/GTest) stays.
- **Not pixel/screenshot comparison.** Brittle, and it tests Qt's renderer, not
  QET.
- **Not a performance benchmark.** Different tool, different discipline.
- **Not upstreamed initially.** Prove value here first; the oracles that earn
  their keep can be proposed as CI checks later, individually.

---

## 10. Success criteria

The design works if it can, from a cold start, rediscover the four non-crash
defects in §1:

1. Delete an element, check `element_info` for orphan rows → **finds PR #664**
2. Group-rotate a grid-aligned selection 4×, compare to start → **finds PR #660**
3. Set a designation letter, save, reload, diff → **finds PR #668**
4. `resave` twice, byte-compare → **finds the determinism gap** *(already does)*

**Write those four as fixtures before building the generator.** They are known
positives; a harness that cannot catch a bug you already understand will not
catch one you don't. If a fixture passes, the oracle is wrong — fix the oracle,
not the fixture.

That is also the honest way to size the work: the whole design is only justified
if it can reproduce these cheaply.
