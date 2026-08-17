# CROSSPAGE-PLAN.md — testing and analysing cross-folio wire links

Goal: tooling to **test and analyse** how wires connect across pages — the folio
reference arrows (*renvois de folio*) and the links behind them.

This is analysis tooling, **not** the Link-ID feature. `LINK-ID-SCOPE.md` is a
separate, on-hold design for making an arrow's printed reference unambiguous.
Read it before proposing UI changes; do not restart it here.

---

## 1. The data model (measured 2026-08-17, master `7307a59c1`)

A folio arrow is an ordinary element of type `embed://import/06renvoi/*.elmt`
carrying a link to its partner:

```xml
<element type="embed://import/06renvoi/02next_folio.elmt"
         uuid="{a7f7c228-...}" x="770" y="440">
  <terminals><terminal id="0" x="-9" y="0" orientation="3"/></terminals>
  <links_uuids>
    <link_uuid uuid="{0d8ea98f-...}"/>     <!-- the partner element's uuid -->
  </links_uuids>
</element>
```

`link_uuid` is **the same mechanism master/slave cross-references use**, so any
tool must filter by element type — not every link is a folio crossing.

### Baseline over the 23 example projects

| Measure | Count |
|---|---|
| Projects containing links | 7 (`industrial` 300 refs, `m_000` 130, `affuteuse_250h` 70, …) |
| `06renvoi` arrow elements | 44 |
| Links crossing to another folio | 35 |
| Links **within the same folio** | **4** |
| Arrows with **no link at all** | **5** |
| Dangling links (target uuid absent) | 0 |
| Non-reciprocated links | 0 |
| Direction pairing | next→prev **22**, prev→next **17** |

Two things in that table are already findings, and both become fixtures:

- **5 arrows link to nothing.** An arrow that references no partner is a dead
  reference in a shipped example.
- **next→prev 22 vs prev→next 17 cannot both be right.** If every link is
  reciprocated (and none is unreciprocated), the two directions must be equal.
  Something is being miscounted or some arrows carry multiple links. **The first
  tool must explain this discrepancy** — it is the calibration case.

---

## 2. Why tooling rather than a fix

The complaint is that cross-page linking is unsatisfactory. Before changing it,
we need to be able to say precisely *what is wrong and how often*. Today there
is no way to answer:

- how many crossings a project has, and whether each is well-formed;
- whether a wire's electrical potential actually continues across the crossing;
- whether editing and saving preserves links;
- whether QET's own view of connectivity agrees with the file's.

Each work item below answers one of those.

---

## 3. Work items

### X1 — `tools/crosspage`: structural linter (DeepSeek)

Static, stdlib-only, no build. One record per crossing plus a violations list.

Rules, each with a real fixture in the corpus:

| Rule | Meaning | Corpus baseline |
|---|---|---|
| `X001` | arrow with no `link_uuid` | **5 expected** |
| `X002` | `link_uuid` target does not exist | 0 expected |
| `X003` | link not reciprocated by the partner | 0 expected |
| `X004` | arrow linked **within its own folio** | **4 expected** |
| `X005` | `next_folio` linked to another `next_folio` (direction mismatch) | 0 expected |
| `X006` | arrow carrying more than one `link_uuid` | unknown — measure it |
| `X007` | `next` arrow whose partner is on an *earlier* folio (or vice versa) | unknown — measure it |

**Report the ref you scanned** (see `tools/actionaudit`'s `source_ref`) — a scan
of a feature branch is not comparable with one of master.

**Definition of done:** the counts above reproduce exactly, **and the tool
explains the 22-vs-17 direction imbalance in §1.** If the imbalance turns out to
be a bug in that measurement rather than in the data, say so — that is a good
outcome, not a failure.

### X2 — potential continuity across a crossing (DeepSeek)

Structure being valid does not mean the wire is connected. Walk:

```
conductor -> terminal -> arrow element -> link_uuid -> partner arrow
          -> terminal -> conductor (on the other folio)
```

and emit one record per **cross-page net**: the folios touched, conductors on
each side, and the wire number(s) carried.

Findings to surface:

- a crossing whose two sides carry **different wire numbers** (the arrow says
  they are one potential; the labels disagree);
- an arrow **not attached to any conductor** — it links a partner but carries no
  wire, so nothing actually crosses;
- a net spanning **3+ folios**, which the grid-cell reference cannot express at
  all (this is the concrete form of the `LINK-ID-SCOPE.md` complaint).

QET computes something similar in `relatedPotentialConductors()`, which
traverses folio reports — read it before inventing a different traversal.

### X3 — round-trip preservation (DeepSeek, small)

Do links survive a save? Reuse the existing sweep: `tools/refdiff` already
resaves every project across two refs and diffs a canonical projection.

Extend `simulator/canon.py` to include, per element, its **sorted set of
`link_uuid` targets**, so a lost or rewritten link registers as a semantic
difference instead of passing silently.

**Fixture:** delete one `link_uuid` from a copy of `affuteuse_250h.qet` and
confirm `canon.diff()` reports it. A projection that cannot see a deleted link
cannot police one.

**Trap:** `canon.py` has been bitten twice by keying on a bare uuid
(FINDINGS F006, F007). `link_uuid` targets are **element** uuids, which are
project-unique — but scope the key to the owning element anyway.

### X4 — does QET agree with us? (Claude/human — judgment)

Compare X2's computed nets against QET's own output: `--export-nets` and
`--export-links` already exist as CLI verbs.

Any disagreement is a finding on one side or the other, and deciding which is
wrong is not mechanical — hence not delegated. Expect the CLI verbs to be the
weaker source: they are barely exercised.

---

## 4. Sequencing

X1 → X2 → X3 can proceed in order; X4 needs X2. X1 alone may be enough to
characterise the complaint, so **look at X1's output before committing to X2**.

## 5. Scope

**Do not** change QET behaviour, the arrow element definitions, or the printed
reference format. That is `LINK-ID-SCOPE.md`'s territory and it is on hold for a
stated reason (the `element_info` schema is generated from
`QETInformation::elementInfoKeys()`, so adding a field changes the database).

This plan produces measurements. What to *do* about them is a later decision.
