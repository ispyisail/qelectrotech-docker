# TASK BRIEF — X6: do folio-reference labels survive folio moves?

Self-contained. Read `CROSSPAGE-PLAN.md` in this repo first.

---

## 0. HOW THIS TASK ENDS — read first

Seven of fourteen sessions on this project ended by **announcing they would
wait** instead of waiting. Two more **crashed and lost everything** because
nothing was on disk.

- **Never end your turn waiting.** Poll in a loop.
- **Commit early and often.**
- **Never report a criterion done without pasting its real output.**

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/x6-progress.log
```

---

## 1. Why this exists — a real rejection, and a claim to verify

Upstream PR #702 auto-numbered folio-reference arrow labels. It was **closed**.
The maintainer's diagnosis:

> *"Auto-numbering evaluates the formula once, at creation time, while a folio
> report / cross-reference needs to be re-evaluated live every time a page is
> opened, moved, or inserted — that's why the label goes blank or picks up the
> wrong number after save/reopen."* — scorpio810

He also gave a no-code workaround, and **this is the claim to test**:

> Use **`%F`** (folio *label*) instead of **`%f`** (folio *position*). `%F` stays
> stable when folios are moved, renamed or inserted; `%f` does not, because it
> depends on the folio's physical position.

**Your first job is not to build a feature. It is to find out whether the
existing behaviour is as described.** That question is currently unanswered, and
everything downstream depends on it.

---

## 2. What to build

`tools/labelstability/` — Python 3, stdlib only, driving the QET binary.

The experiment, per project containing folio-reference arrows:

1. Record every arrow's rendered label text **before** any change.
2. Perturb the folio order — reorder, rename, or insert a folio (by editing the
   `<diagram order=...>` / title attributes in a **copy** of the `.qet`).
3. Resave through QET (`--resave`) so labels are re-evaluated.
4. Record every arrow's label **after**, and diff.

Report per project: which labels changed, which held, and whether the formula in
use was `%f`-based or `%F`-based.

Output `reports/labelstability.{json,md}`.

---

## 3. Definition of done — paste real output

### Criterion 1 — where labels actually live
Show, from the XML, exactly where an arrow's displayed label text is stored and
what formula produces it. Name the file and element path. Everything else rests
on this, so state it concretely rather than assuming.

### Criterion 2 — **the `%f` vs `%F` claim, tested**
Construct two variants of the same project — one whose report formula uses
`%f`, one using `%F` — reorder a folio in each, and report what happens to the
labels.

**Expected from the maintainer's account:** `%f` labels shift or break; `%F`
labels hold. **If that is not what you observe, say so plainly and show the
output.** Confirming or refuting this is the deliverable; a refutation is a
finding, not a failure.

### Criterion 3 — the blank-label failure
The maintainer reports labels going *blank* or picking up the wrong number after
save/reopen. Try to reproduce that: resave a project twice and compare labels
across both saves. Report whether you can reproduce it, and under what
conditions.

### Criterion 4 — corpus survey
Across the 23 examples, report how many report formulas use `%f` versus `%F`
versus something else. If the shipped examples mostly use the fragile form, that
is worth knowing.

---

## 4. Traps

1. **Always pass a timeout.** `examples/schema_indus.qet` hangs forever on a
   modal (upstream #661). Exclude it and say so.
2. **SingleApplication**: isolated `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME`,
   `-platform offscreen`, every run. Check `docker ps` first.
3. **Work on copies.** Never modify anything under
   `/home/user/qet-fix/examples/`.
4. **`Diagram::toXml` is not deterministic** — element order and legacy terminal
   ids churn between saves (upstream #754). Compare labels **by arrow uuid**,
   never by document order, or you will see phantom changes.
5. **Never `git checkout`/`stash`/`reset` in `/home/user/qet-fix`'s main tree.**
6. A binary already exists at `/home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech`
   (master). Reuse it rather than building, unless you need a different ref.

---

## 5. Scope

**May create:** `tools/labelstability/**`, `reports/labelstability.{json,md}`.

**Do NOT:** modify QElectroTech source; change any file under `examples/`;
implement a fix or a new numbering scheme — this task **measures**, it does not
repair; modify `simulator/`, `tools/refdiff/`, `tools/crosspage/`, or any `.md`
plan file; push or open a PR.

**Work on a new branch** in this repo.

---

## 6. Report

All four criteria with real pasted output, an explicit verdict on the `%f`/`%F`
claim, and anything in this brief that was wrong or underspecified. If the
maintainer's description does not match observed behaviour, that is the most
important thing in your report — lead with it.
