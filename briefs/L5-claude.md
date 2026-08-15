# TASK BRIEF — L5: coverage audit (Claude Opus 5)

> **Executor: Claude Opus 5, effort `xhigh`. Do not delegate this one.**
>
> Every other item in this plan has a mechanical proof fixture — a command whose
> output is either right or wrong. **This one does not, and cannot.** The
> deliverable is a judgement about what the tooling is *structurally blind to*,
> and a confidently wrong answer here sends the next several days of work at the
> wrong target. There is no fixture to catch that.
>
> It is also cheap: the output is a document, there is no build loop, and the
> whole corpus is already-known context.

---

## 1. The question

Every tool in this repo works on **files** or the **headless CLI**. That was a
deliberate, correct decision — the file layer found four real defects while a
3,500-line GUI-driving harness found zero.

But it means whole categories of defect are **invisible**, and nobody has
written down which.

> *What classes of QET defect can no existing tool observe, and which two or
> three are worth making observable?*

---

## 2. What exists — the observation surface

| Tool | Observes | Blind to |
|---|---|---|
| `simulator/` mutation sweep | malformed-input crashes, save corruption, NaN/Inf geometry | anything needing interaction |
| `tests/determinism/` | save idempotence, data preservation across resave | anything not expressible as resave |
| `tests/asan-regression/` | leaks in four specific paths | everything else |
| `scripts/asan-compare.sh` | leak deltas between two refs | non-leak behaviour |
| `--test-ops` (lab binary) | select, delete, rotate, undo, redo on **diagram 1 only** | multi-folio, GUI state, anything without an op |
| `fuzzer/` (GUI, ASan) | crashes reachable by random clicking | anything non-crashing |
| CLI verbs | load, save, export, element checks | everything interactive |

---

## 3. Areas to assess

For each, answer: **can any existing tool observe this — and if not, what would
it take?**

- GUI interaction state machines — drag, rubber-band select, in-place text edit
- Multi-folio behaviour — cross-references, folio reordering, the summary page
- Live SQLite database state (`sources/dataBase/projectdatabase.cpp`) versus
  what the `.qet` file says. *(Note: an orphan-row bug in exactly this gap
  became PR #664 — found by a user, not by tooling.)*
- Undo/redo composition beyond what `--test-ops` can currently drive
- Rendering and export **fidelity** — is the PDF correct, or merely produced?
- Element editor, terminal strip editor, title-block editor
- Anything needing two instances, or a file changing under the running app

---

## 4. The rule that makes this useful

**Rank by (likelihood a real defect lives there) × (cost to make it
observable). Recommend at most three.**

A list of twenty gaps is not an audit — it is a restatement of the problem. The
value is entirely in the cut.

**For each of your top three, name one concrete defect that would have been
caught** — ideally one already in the bugtracker, the merged-PR history, or
`FINDINGS.md`. A gap with no plausible defect behind it is not worth closing,
however real the gap is.

Sources for candidate defects:

- `FINDINGS.md` in this repo
- the QET bugtracker at <https://qelectrotech.org/bugtracker/> (~75 untouched)
- merged PR history for `ispyisail` — bugs found by users, not tools

---

## 5. Deliverable

`COVERAGE-GAPS.md` at the repo root:

1. **The full assessment** — every area in §3, with a one-line verdict on
   whether anything observes it today.
2. **The top three**, each with: the gap, the concrete defect it would have
   caught, an estimate of what making it observable costs, and the reasoning
   for its rank.
3. **What you deliberately did not recommend, and why.** The rejects matter —
   they stop the same ground being re-litigated next month.

Write the ranking's reasoning down rather than asserting it. Someone should be
able to disagree with a specific step rather than with the conclusion as a
whole.

---

## 6. Scope

**Analysis only.** Do not build anything, do not modify any tool, do not add a
test. The deliverable is one markdown file.

Do not push, open a PR, or post anywhere.

---

## 7. Honesty requirements

- **If an area turns out to be adequately covered, say so.** Finding fewer gaps
  than expected is a legitimate result and more useful than a padded list.
- **If the top three are obvious and boring, say that too.** Do not manufacture
  a surprising finding.
- **Distinguish "no tool observes this" from "this is worth observing."** They
  are different claims and only the second justifies work. Most of the blind
  spots in §3 are real; only a few matter.
