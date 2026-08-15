# TASK BRIEF — L6 phase 1: evidence inventory across 136 PRs

You are working in `/home/user/qelectrotech-docker`. This brief is
self-contained — do not assume any skill files or plan documents are loaded.

**This is a data-collection task, not a judgement task.** You are building an
inventory. Somebody else decides what it means.

---

## 1. Why this exists

A merged pull request (#707) turned out to have shipped with its central claim
verified by *reading the code*, not by *observing the behaviour*. Its own commit
message said so:

> "confidence in the fix instead rests on tracing the exact save-gate code path"

When it was finally tested properly, the fix was correct — but it had a **second
symptom nobody had noticed**. That second symptom was invisible precisely
because nobody had run the thing.

There are **136 pull requests** from this account. It is unlikely #707 is the
only one. Your job is to find out which others rest on inference rather than
observation.

---

## 2. What you are producing

A single machine-readable inventory: `reports/pr-evidence.json`, plus a
human-readable `reports/pr-evidence.md`.

For **every** PR, record:

| Field | Meaning |
|---|---|
| `number` | PR number |
| `title` | PR title |
| `state` | OPEN / MERGED / CLOSED |
| `evidence_class` | `observed` / `inferred` / `unstated` — see §3 |
| `evidence_markers` | Count of the signals in §3 |
| `quotes` | Up to 3 short quotes from the body that justify the classification |
| `claim` | One sentence: what the PR asserts it fixes or adds |

---

## 3. How to classify — apply these rules mechanically

Read each PR's **body and commit messages**.

**`observed`** — the PR contains evidence that something was actually run:
- pasted terminal output, exit codes, or timings
- a results table with concrete values (`67 vs 0`, `HUNG`, `exit=0`)
- fenced code blocks containing command invocations *and* their output
- explicit before/after measurements

**`inferred`** — the PR reasons about correctness from the source, with no
evidence of execution. Strong signals:
- "tracing the code path", "by inspection", "the gate is at line N so…"
- "should now", "will now", "this ensures" — with nothing run
- an explicit admission, as in #707: *"attempted but not completed"*

**`unstated`** — the body says what changed but makes no verification claim
either way. This is a real category; do not force it into the other two.

**When torn between `observed` and `inferred`, choose `inferred` and say why in
`quotes`.** A false `inferred` costs someone five minutes of re-reading. A false
`observed` means a suspect PR is never looked at again — that is the expensive
error, and the whole point of the exercise.

---

## 4. Calibration — verify before you process the corpus

These three are known-correct and **mechanically separable**. Confirmed
2026-08-16 with a crude evidence-marker count:

| PR | Must classify as | Marker count |
|---|---|---|
| **#707** | `inferred` | 0 |
| **#682** | `observed` | 6 |
| **#737** | `observed` | 6 |

**Run your classifier on these three first.** If it does not reproduce that
split, your rules are wrong — fix them before processing the other 133. Report
the calibration result explicitly.

---

## 5. Environment facts

| Thing | Value |
|---|---|
| Work here | `/home/user/qelectrotech-docker` |
| Upstream repo | `qelectrotech/qelectrotech-source-mirror` |
| PR author | `ispyisail` |
| Corpus size | **136** PRs (all states) |
| Python | 3.14, **stdlib only** |

```bash
gh pr list --repo qelectrotech/qelectrotech-source-mirror --author ispyisail \
  --state all --limit 200 --json number,title,state
gh pr view <N> --repo qelectrotech/qelectrotech-source-mirror --json body,commits
```

**Traps:**

1. **`gh` is rate-limited.** 136 PRs is a lot of calls — **cache every fetched
   body to disk** and read from cache on re-runs. Add `--refresh` to re-fetch.
   Do not re-query in a loop while developing your parser.
2. **Do not classify from the title.** Titles say what changed, never how it was
   verified. The signal is in the body and commit messages.
3. **A long body is not evidence.** Some PRs describe the mechanism at length
   with nothing run. Length correlates with neither class.

---

## 6. Definition of done

### Criterion 1 — calibration

Show your classifier's output for #707, #682, #737. Must be
`inferred`, `observed`, `observed`.

### Criterion 2 — full inventory

`reports/pr-evidence.json` covers all 136 PRs with no gaps. Report the
distribution: how many `observed`, `inferred`, `unstated`.

### Criterion 3 — spot-check

Pick **5 PRs you classified as `inferred`** and paste the quotes that justify
each. These will be checked by hand.

---

## 7. Scope boundary

**You may create:** `reports/pr-evidence.{json,md}`, a script under `tools/` to
generate them, and a cache directory.

**Do not:**

- **Rank, prioritise, or recommend anything.** That is phase 2 and is somebody
  else's job. Produce the inventory; stop there.
- Re-test any PR, check out any branch, or build anything.
- Run any `gh` command that writes: no `pr edit`, `pr comment`, `pr close`,
  `pr create`, or `api -X POST/PATCH/DELETE`. **Strictly read-only.**
- Modify `simulator/`, `scenarios/`, `tests/`, or any `.md` plan file.
- Push or post anywhere.

---

## 8. How to report back

Commit on a **new branch**, message describing what the inventory *records*.

Report:

1. **The calibration result** for the three PRs.
2. **The distribution** across the three classes.
3. **Your five spot-check quotes.**
4. **Anything ambiguous** — cases where the rules in §3 genuinely did not decide
   it. List them rather than guessing; those are the interesting ones.
5. Anything in this brief that was wrong or underspecified — say so plainly.

**Do not editorialise about which PRs are risky.** An inventory that stays an
inventory is exactly what is wanted here.
