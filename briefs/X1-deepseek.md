# TASK BRIEF — X1: structural linter for cross-folio wire links

Self-contained. Assume no skill files or plan documents are loaded, except
`CROSSPAGE-PLAN.md` in this repo, which you should read first.

---

## 0. HOW THIS TASK ENDS — read first

Seven of fourteen sessions on this project ended by **announcing they would wait**
for something instead of waiting. Two more **crashed mid-run and lost everything**
because nothing was on disk.

- **Never end your turn waiting.** Poll in a loop until the thing finishes.
- **Commit early and often**, even when incomplete.
- **Never report a criterion done without pasting its real output.**

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/x1-progress.log
```

---

## 1. What you are building

`tools/crosspage/` — a static analyser for folio-reference arrows (*renvois*)
in `.qet` project files. **Python 3, stdlib only. No build, no QET launch.**

A folio arrow is an element whose `type` contains `06renvoi`, carrying:

```xml
<links_uuids><link_uuid uuid="{partner-element-uuid}"/></links_uuids>
```

`link_uuid` is also used by master/slave cross-references, so **filter by
element type** — not every link is a folio crossing.

Output `reports/crosspage.json` + a readable `reports/crosspage.md`: one record
per arrow (uuid, folio order, type, direction, partner, partner folio) plus a
violations list.

---

## 2. The rules

| Rule | Meaning | Expected on the 23 examples |
|---|---|---|
| `X001` | arrow carries no `link_uuid` | **5** |
| `X002` | `link_uuid` target uuid does not exist in the project | **0** |
| `X003` | partner does not link back | **0** |
| `X004` | arrow linked to a partner **on its own folio** | **4** |
| `X005` | `next_folio` linked to another `next_folio`, or `previous` to `previous` | **0** |
| `X006` | arrow carrying more than one `link_uuid` | measure it |
| `X007` | `next` arrow whose partner sits on an earlier folio, or `previous` on a later one | measure it |

Direction comes from the element type: `02next_folio.elmt` vs
`01previous_folio.elmt`. **Note the timestamped variants** —
`01previous_folio-20140521204844.elmt` and similar exist in the corpus and are
the same thing; match on `next_folio` / `previous_folio` as substrings, not on
exact filenames.

Folio identity is the `<diagram>` element's `order` attribute.

---

## 3. Definition of done — paste real output

### Criterion 1 — the baseline reproduces

Run over `/home/user/qet-fix/examples/*.qet` and reproduce the table above:
**X001 = 5, X002 = 0, X003 = 0, X004 = 4, X005 = 0**, plus measured values for
X006 and X007.

If a number differs, **say so and show your working — do not tune the rule to
hit the target.** A disagreement is either a bug in your parser or an error in
this brief, and both are worth knowing.

### Criterion 2 — explain the direction imbalance

Counting links from arrows only, an earlier probe found
**next→prev = 22 but prev→next = 17**. If every link is reciprocated (and X003
finds none unreciprocated), those two must be equal.

**Explain the discrepancy.** Candidates: arrows carrying multiple links (X006);
links pointing at non-arrow elements; arrows whose partner is a master/slave
element rather than a renvoi; the earlier probe double-counting.

**If the earlier probe was simply wrong, say that plainly** — that is a correct
answer, not a failure. Show the numbers your tool produces and how they
reconcile.

### Criterion 3 — the 5 unlinked arrows, named

List them: project, folio order, element uuid, arrow type, position. These are
dead references in shipped example files; the report should make each one
findable.

### Criterion 4 — record the ref you scanned

`tools/actionaudit/actionaudit.py` has a `source_ref()` helper that records
commit, branch and uncommitted source files. Do the same. A scan of a feature
branch is not comparable with a scan of master, and this project has already
lost time to exactly that mistake.

---

## 4. Traps

1. **`/home/user/qet-fix` is checked out on `cabinet-layout-editor`, not
   master.** For the corpus that is fine — you are reading `.qet` data files,
   not source — but record the ref anyway (criterion 4).
2. **Not every `link_uuid` is a folio crossing.** Master/slave cross-references
   use the same tag. Filter by element type.
3. **Two projects have near-identical names** (`cablage-eclairages_sikli-v5.qet`
   and `câblage-éclairages-sikli-v5.qet`). They are different files; do not
   deduplicate them.
4. **A project may contain zero arrows** — 16 of the 23 do. That is not an error.
5. **Do not modify any `.qet` file.** This is read-only analysis.

---

## 5. Scope

**May create:** `tools/crosspage/**`, `reports/crosspage.{json,md}`.

**Do NOT:** modify QElectroTech source or any `.qet` file; change
`simulator/`, `tools/refdiff/`, `tools/actionaudit/`, or any `.md` plan file;
implement X2/X3/X4 from the plan (continuity, round-trip, CLI comparison) —
they are separate items; push or open a PR.

**Work on a new branch** in this repo.

---

## 6. Report

Commit on a new branch. All four criteria with real pasted output, the X006 and
X007 measurements, and anything in this brief that was wrong or underspecified —
particularly the 22-vs-17 figure, which came from a quick probe and may itself
be the error.
