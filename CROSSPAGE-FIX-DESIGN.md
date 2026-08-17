# Design: what a fix for folio-link correctness must actually be

**Status:** design only, no code. Supersedes the earlier sketch of "add
folio-order validation to `isLinkable()`", which testing showed to be wrong.

---

## 1. The defect

`LinkElementCommand::isLinkable()` validates the arrow **type** (a `next` must
pair with a `previous`) and nothing else. It never checks folio order, so a
`previous`-folio arrow can point at a *later* folio.

Two shipped example projects contain such links:

```
affuteuse_250h.qet   folio 6[prev] -> folio 7,  folio 7[next] -> folio 6   (next_folio family)
industrial.qet       folio 6[prev] -> folio 7,  folio 7[next] -> folio 6   (going_arrow family)
```

## 2. Why link-time validation is the WRONG fix

**Link correctness is not a property of the link. It is a property of the link
*plus the current folio order*, and folio order changes afterwards.**

Measured on `affuteuse_250h.qet`, moving one folio and re-saving:

| | correct | inverted |
|---|---|---|
| before | 28 | **2** |
| after moving folio 6 to the end | **30** | **0** |

No link was created, edited or deleted. Reordering folios alone turned both
inverted links correct.

Three consequences:

1. **A link-time check cannot prevent inversions.** The user links correctly,
   then reorders folios, and the link is inverted with no further action.
2. **A link-time check would block legitimate work.** Linking before arranging
   folios is normal; the "wrong" order may be temporary.
3. **The two inversions in the corpus are probably not user error at all** —
   more likely the residue of a folio move, exactly as reproduced above.

## 3. Two more rules that must NOT be enforced

**Same-folio links are legitimate.** 30 exist, and 26 are a systematic pattern:
`m_000.qet` folios 4 and 5 use 13 pairs of the *vertical* Polish family
(`nastepna_strona_1-1` / `poprzednia_strona_1-1`) — a wire leaving the bottom of
a page and re-entering at the top of the same page. Blocking this would break a
real project.

**Placement cannot be validated.** The convention (next on the right, previous
on the left; next at the bottom, previous at the top for vertical families) holds
by median but is bimodal: `industrial` places one cluster of `going_arrow` at
the page edge and another at a fixed internal grid position. 61 `next` arrows sit
on the left half legitimately. A placement rule would produce mass false
positives.

## 4. What the fix should be

A **project-level diagnostic**, not a link-time block.

- Report, per project, every link whose direction disagrees with the current
  folio order, naming both folios and both arrows.
- Surface it where a user can act on it and ignore it — never as a modal, never
  as something drawn into the diagram (upstream #701 was rejected for putting an
  editing-state indicator into `paint()`, which reached PDF/PNG/SVG export).
- Re-evaluate after a folio move, since that is when inversions appear.

Explicitly **not**: blocking `isLinkable()`, auto-swapping arrow types, or
rewriting links on reorder — each changes a user's drawing without being asked.

## 5. Open questions for the maintainer

These are design decisions, not implementation details, and they belong upstream
before any code:

1. Is an inverted link considered an error at all, or an accepted state after a
   folio move?
2. Should the diagnostic live in the existing diagnostic-logging work
   (PR #646/#647), as a CLI verb, or in the UI?
3. Are same-folio links intentional (as `m_000` suggests) or tolerated?

## 6. How it would be tested

`tools/crosspage` already detects every case, over all 400 arrows and 8 arrow
families. The reorder experiment in §2 is reproducible with
`tools/labelstability`'s helpers. Any implementation can be checked by:

- the two known inverted pairs being reported;
- the 26 `m_000` same-folio links **not** being reported;
- the 61 left-half `next` arrows **not** being reported;
- a reorder flipping the reported set, as measured above.
