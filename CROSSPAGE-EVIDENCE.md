# Cross-folio linking: measured evidence

Everything below was measured, not inferred. Each item names how to reproduce it,
because these numbers are meant to be quoted in upstream discussion and a number
you cannot re-derive is worth nothing.

**Refs:** QET source measured at `upstream/master` `eb095f9a1` unless stated.
The staged branches in §4 were later rebased onto `e2e0df784`; the two
intervening upstream commits touch only `sources/import/edz/edzpart.cpp`, so
no measurement here is affected.
Note `/home/user/qet-fix`'s working tree sits on `cabinet-layout-editor` and is
~195 commits behind upstream — a static scan of it is **not** comparable with a
runtime measurement from master. That mistake produced a phantom finding once
(see `reports/orphan-analysis.md`).

---

## 0. Summary — what we learned

**The mechanism is sound. The feedback is not.** Every layer that moves data
works; every layer that tells the user what happened is weak. That is the whole
finding, and it reframes the original complaint ("cross-page linking is not
user-friendly") as accurate but misdirected: nothing is corrupting drawings.

### Works — verified, not assumed

| Behaviour | Evidence |
|---|---|
| Links survive every page operation | insert / move-to-front / move-to-end / move-past-partner / reverse-all: **0 lost, 0 retargeted, 0 dangling, 0 orphaned** on two projects |
| Labels re-evaluate on their own | inserting a page turns `7-A0` into `8-A0` |
| Wire numbers propagate the whole potential | one edit updated **93 conductors across 26 non-contiguous folios** in one undo command |
| Deleting a page cleans up the link | zero dangling references afterwards |

### Broken — all of it feedback

| Problem | Measured |
|---|---|
| References are ambiguous | **176 of 400 arrows (44%)** share a reference with another arrow on the same folio; in `industrial` **all 39** colliding groups point to *different* partners |
| Deleting a page orphans partners silently | 8–9 arrows left claiming a wire continues nowhere, no warning |
| Reordering pages silently invalidates direction | reversing page order makes **72** links backwards in `m_000`; two shipped projects already contain such links |
| The picker leads with empty columns | `Fonction` and `Tension / Protocole` populated **0.0%** across 3059 conductors; identity sits in columns 6–8 |
| One action, two rules | inline edit propagates unconditionally; the properties dialog asks first |

### Two conclusions that testing overturned

**A link-time check was the wrong fix.** The obvious response to inverted links
was validation in `isLinkable()`. Moving one folio then turned 2 inverted links
into 0 *without touching any link* — correctness depends on folio order, which
changes after linking. The check could not have prevented the state and would
have blocked linking before folios are arranged. Replaced by a diagnostic.

**The first measurements covered 13% of the data.** Matching only `06renvoi`
arrows saw 53 of 400 and missed the two largest families, so every early number
was drawn from an unrepresentative sample — including a direction imbalance that
turned out to be an artifact of the filter itself.

Both are recorded because the cost of re-deriving "we tried that and it was
wrong" is higher than the cost of writing it down.

---

## 1. The corpus is bigger than the obvious filter suggests

400 folio-reference arrows across 8 families in 23 example projects:

| Family | Count | | Family | Count |
|---|---|---|---|---|
| `going_arrow` | 128 | | `next_folio` | 31 |
| `coming_arrow` | 115 | | `previous_folio` | 22 |
| `nastepna` (PL) | 49 | | `jump_to` (SFC) | 4 |
| `poprzednia` (PL) | 49 | | `jump_from` (SFC) | 2 |

Matching only `06renvoi` + `next_folio`/`previous_folio` sees **53 of 400 (13%)**
and silently excludes the two largest families. `tools/crosspage` originally did
exactly that; every rule it reported was computed over an unrepresentative
sample, and its "explanation" of a 22-vs-17 direction imbalance was an artifact
of its own filter (with all families counted, pairing is exactly 188/188).

```bash
python3 tools/crosspage/crosspage.py       # 400 arrows; X001=24 X004=30 X007=4
```

## 2. What works — verified, not assumed

### Wire numbers propagate across the whole potential

Editing one conductor via the UI path (`textItem()->setPlainText()` →
`displayedTextChanged()`):

| Project | potential | folios spanned | conductors updated |
|---|---|---|---|
| `affuteuse_250h` | widest | 4 (3,4,6,7) | **12 of 12** |
| `industrial` | widest | **26** (5,6,9–31,40) | **93 of 93** |

Traversal does not degrade with distance, and the folio set is non-contiguous —
it hops arrows between non-adjacent pages and still reaches every one.
`relatedPotentialConductors()` defaults to `all_diagram = true`.

### Page operations never damage a link

Eight operations on `affuteuse_250h` (34 arrows) and `m_000` (98), compared by
arrow uuid (never document order — `Diagram::toXml` is not order-stable, #754):

| Operation | lost | retargeted | dangling | orphaned |
|---|---|---|---|---|
| insert page between linked folios | 0 | 0 | 0 | 0 |
| move page to end / to front | 0 | 0 | 0 | 0 |
| move page past its partner | 0 | 0 | 0 | 0 |
| reverse every page | 0 | 0 | 0 | 0 |

Labels re-evaluate correctly: inserting a page between folios 6 and 7 changed
the two affected references from `7-A0`/`7-D0` to `8-A0`/`8-D0`.

```bash
python3 tools/pagemoves/pagemoves.py /home/user/qet-fix/examples/affuteuse_250h.qet
```

## 3. What does not work

### 44% of arrows print an ambiguous reference

176 of 400 arrows display a reference identical to another arrow **on the same
folio**. In `industrial`, all 39 colliding groups point to **different**
partners — not one is a harmless duplicate:

| Project | ambiguous arrows | groups |
|---|---|---|
| `industrial` | 94 | 39 (23 of width 2, 16 of width 3) |
| `m_000` | 50 | 23 |
| `affuteuse_250h` | 18 | 9 |
| `tableau_domestique` | 8 | 4 |
| `Projet_vierge` | 6 | 2 |

The label is `%f-%l%c` — folio, line, column — so it identifies a **grid cell**,
not a link, and several arrows fit in one cell. This is the premise of
`LINK-ID-SCOPE.md`, which estimated "up to 8 arrows per cell"; the measured
reality is 44% affected in groups of 2 and 3.

### Direction validity goes stale on reorder

Link correctness depends on folio order, which changes after linking:

| | correct | inverted |
|---|---|---|
| `affuteuse_250h` as shipped | 28 | **2** |
| after moving folio 6 to the end | **30** | **0** |
| `m_000` after reversing all pages | — | **72** |

No link was created, edited or deleted. **This is why a check in
`isLinkable()` is the wrong fix** — it cannot prevent a state that appears
later, and would block linking before folios are arranged.

Two shipped projects contain inverted links, in different arrow families:

```
affuteuse_250h  folio 6[prev] -> folio 7,  folio 7[next] -> folio 6
industrial      folio 6[prev] -> folio 7,  folio 7[next] -> folio 6
```

### Deleting a page silently orphans its partners

| | arrows lost | orphaned | dangling |
|---|---|---|---|
| `affuteuse_250h` delete folio 6 | 8 | **8** | 0 |
| `m_000` delete folio 6 | 9 | **9** | 0 |

Cleanup is correct — zero dangling references — but the surviving arrow still
claims a wire continues elsewhere, with no warning. Likely the origin of the 24
orphaned arrows already in the shipped corpus.

### The link picker leads with columns that are almost always empty

Populated rates over 3,059 conductors in the corpus:

| Column (original order) | Populated |
|---|---|
| N° de fil | 43.2% |
| **Fonction** | **0.0%** |
| **Tension / Protocole** | **0.0%** |
| Couleur du conducteur | 2.6% |
| Section du conducteur | 2.3% |
| N° de folio / Position / Titre de folio | *columns 6–8* |

Observed in the real widget with 17 free candidates, three rows read
`8 |  |  |  |  | 5 | …` — indistinguishable until column 7.

### Same behaviour, two different rules

| Path | Propagates to the potential? |
|---|---|
| Inline text edit on the drawing | **always**, no prompt |
| Properties dialog | only if *"Appliquer … à l'ensemble des conducteurs de ce potentiel"* is ticked (default on) |

Editing inline silently rewrote 93 conductors across 26 folios with no prompt.
Which behaviour is *correct* is a product decision, not a bug to fix unilaterally.

## 4. Staged locally, not uploaded

Branches in `/home/user/qet-fix`, each single-purpose, probe-free, on
`upstream/master`:

| Branch | Change | Verified by |
|---|---|---|
| `feature-check-links` | `--check-links` CLI diagnostic (+87) | reports affuteuse/industrial 2 inverted each, exit 1; `m_000` 0 inverted with its 26 same-folio links **not** reported, exit 0; reorder flips 2→0 |
| `fix-link-picker-columns` | identity-first picker columns (+51/−33) | real widget, 17 candidates, columns and values reordered together; folio/position/title made searchable; settings key versioned to `report-state-v2` at both save and load |
| `remove-dead-setpropertytopotential` | remove 40 dead lines | 0 callers; superseded 2016-12-19 by `d8a374629`; builds clean |

**These will drift.** `cli_export.cpp` and `linksingleelementwidget.cpp` are
actively touched upstream; rebase periodically rather than at upload time.

## 5. Deliberately not built

- **Link IDs** for the 44% ambiguity — `LINK-ID-SCOPE.md`, on hold because
  `element_info` columns are generated from `QETInformation::elementInfoKeys()`,
  so adding a field changes the database schema.
- **Folio-order validation in `isLinkable()`** — disproved by §3; the diagnostic
  replaces it.
- **Placement validation** — the convention (next right / previous left;
  next bottom / previous top for vertical families) holds by median but is
  bimodal: `industrial` uses a second internal grid position, and 61 `next`
  arrows sit legitimately on the left half.
- **Autonumbering propagation** — #702 was closed with "I don't think it's worth
  wasting your time on this PR"; well-trodden ground on the forum.

## 6. Open questions that belong upstream

1. Is an inverted link an error at all, or an accepted state after a folio move?
2. Should the diagnostic live in the CLI, in the diagnostic-logging work
   (#646/#647), or in the UI?
3. Are same-folio links intentional? `m_000` uses 13 vertical pairs
   deliberately, so `--check-links` counts them and does not report them.
4. Should inline editing offer the same "apply to whole potential" choice the
   properties dialog does?
