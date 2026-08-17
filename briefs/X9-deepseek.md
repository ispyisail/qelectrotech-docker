# TASK BRIEF — X9: what is a folio-reference link *meant* to do, and does the corpus obey it?

Self-contained. Read `CROSSPAGE-PLAN.md` first.

---

## 0. HOW THIS TASK ENDS — read first

Seven of sixteen sessions on this project ended by **announcing they would
wait** instead of waiting. Two more **crashed and lost everything** because
nothing was on disk.

- **Never end your turn waiting.** Poll in a loop.
- **Commit early and often.**
- **Never report a criterion done without pasting its real output.**

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/x9-progress.log
```

---

## 1. The question

A folio-reference arrow says a wire continues on another page. There are two
kinds — `02next_folio` and `01previous_folio` — and each links to one partner.

**Nobody has written down what the rules actually are.** Before anyone changes
this subsystem, we need the intended contract stated and checked:

- Does a `next` arrow always point *forward* (partner on a later folio)?
- Does a `previous` arrow always point *backward*?
- Is the pair always one `next` and one `previous`?
- Is same-folio linking meaningful, or an error?
- Is placement meaningful — do `next` arrows live on the right edge?

**The existing system is what we are trying to fix. Do not design or implement
anything new.** This task produces evidence.

---

## 2. What is already known (measured — verify, don't assume)

| Fact | Value |
|---|---|
| `next` arrows: page position | n=31, x mean **760**, range 80–1050 |
| `prev` arrows: page position | n=22, x mean **282**, range 70–910 |
| Direction-inverted pairs | **2** (`affuteuse_250h`: folio 6 `previous` ↔ folio 7 `next`) |
| Same-folio links | **4** (`affuteuse_250h` folio 5) |
| Orphaned arrows (no link either way) | **5** (`Projet_vierge` folio 3) |
| Dangling / non-reciprocated | 0 / 0 |

And critically, from `sources/undocommand/linkelementcommand.cpp`,
`LinkElementCommand::isLinkable()`:

```cpp
case Element::PreviousReport:
    if (element_b->linkType() != Element::NextReport) return false;   // type only
    if (element_a->isFree() && element_b->isFree()) return true;      // no order check
```

**The code validates arrow *type* and nothing else** — not folio order, not
placement. That is why an inverted pair can exist and ships in an example file.

---

## 3. What to build

`tools/linksemantics/` — Python 3, stdlib only, static. No build, no QET launch.

### Part A — recover the intended contract from evidence

Do not guess it. Derive it from three independent sources and report each:

1. **The corpus.** For every linked pair: both folio orders, both directions,
   both x/y positions, and the page width (the diagram's `cols`×`colsize`).
   Express placement as a *fraction of page width*, not raw x — pages differ in
   size and raw x is not comparable.
2. **The code.** What does `isLinkable()` actually enforce? What does the link
   picker offer (`LinkSingleElementWidget` filters to the opposite type — quote
   the line)? What does the label formula `%f-%l%c` resolve to?
3. **The strings.** The element names and `tr()` labels
   (`Renvoi de folio suivant` / `précédent`) and any tooltips. These state the
   author's intent in words.

Where the three disagree, **say so** — that gap is the finding.

### Part B — score the corpus against the recovered contract

Per pair, report conformance on each rule, and list every deviation with
project, folios, uuids and positions. Distinguish:

- **violates the code's rules** (should have been impossible)
- **violates the apparent convention** (code allows it, practice says otherwise)

That distinction is the whole point: the second category is what a validation
fix would catch.

Output `reports/linksemantics.{json,md}`.

---

## 4. Definition of done — paste real output

### Criterion 1 — the contract, stated
A short numbered list of the rules the evidence supports, each tagged
`enforced-by-code`, `convention-only`, or `contradicted`. This is the
deliverable someone would read before touching the subsystem.

### Criterion 2 — placement is measured properly
Report `next`/`prev` position as a fraction of page width, with the
distribution. Confirm or refute "next lives on the right, previous on the left".
**The raw-x figures in §2 ignore page size — if normalising changes the picture,
say so.**

### Criterion 3 — every deviation named
The 2 inverted pairs, 4 same-folio links and 5 orphans, each with full
coordinates and uuids, plus anything else found. State for each whether the code
permits it.

### Criterion 4 — what a fix would have to check
Given the contract, list the concrete conditions `isLinkable()` would need to
test to prevent the deviations found. **Do not write the fix** — state the
conditions and which deviation each would have caught.

---

## 5. Traps

1. **Read `.qet` data files only.** `/home/user/qet-fix` is on
   `cabinet-layout-editor`; for source questions use `upstream/master` (the
   working tree is 195 commits behind). Record the ref — see
   `tools/actionaudit`'s `source_ref()`.
2. **Two arrow collections exist**: `embed://import/06renvoi/...` and
   `.../10_electric/10_allpole/100_sheet_referencing/...`, plus timestamped
   variants like `01previous_folio-20140521204844.elmt`. Match on
   `next_folio`/`previous_folio` as substrings. Ignoring the second collection
   previously produced a bogus 22-vs-17 imbalance.
3. **Folio identity is the `<diagram order=...>` attribute**, and it is a
   string — compare numerically, not lexically ("10" < "9" as text).
4. **Only 2 of 23 projects contain renvoi arrows.** A rule inferred from 44
   arrows is weak evidence; say so rather than overclaiming.
5. **Do not modify any `.qet` file or QET source.**

---

## 6. Scope

**May create:** `tools/linksemantics/**`, `reports/linksemantics.{json,md}`.

**Do NOT:** implement a fix; modify QET source or example files; touch
`simulator/`, `tools/refdiff/`, `tools/crosspage/`, `tools/actionaudit/`,
`tools/exportleak/`, `tools/labelstability/`, `tools/interactionaudit/`, or any
`.md` plan file; push or open a PR.

**Work on a new branch** in this repo.

---

## 7. Report

All four criteria with real pasted output, the contract as a numbered list, and
anything in this brief that was wrong or underspecified — especially if the
placement convention does not survive normalisation by page width.
