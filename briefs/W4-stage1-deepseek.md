# TASK BRIEF — W4 stage 1: bugtracker corpus + reproduction attempts

Work in `/home/user/qelectrotech-docker`. Self-contained.

**Stage 1 only.** Build the corpus and attempt reproductions. **Do not rank,
prioritise, or recommend anything** — that is stage 2 and needs judgment a
scraper cannot supply.

---

## 1. Why this is worth doing

The QElectroTech bugtracker has **~75 open bugs nobody has touched**. Measured
across this account's PRs, fixes citing a bugtracker ID have merged upstream in
about **0.2 days** — faster than any other category of change.

But three hand-picked entries in a row (#256, #278, #288) turned out to be
**not reproducible on master** — already fixed, nobody closed them. Proving that
is valuable too: it lets stale bugs be closed.

So the job is to separate live from stale, cheaply, with evidence.

---

## 2. Fetching

The tracker is **MantisBT** at <https://qelectrotech.org/bugtracker/>:

- list: `/bugtracker/view_all_bug_page.php`
- issue: `/bugtracker/view.php?id=<n>`
- RSS: `/bugtracker/issues_rss.php`

No API token exists, so scrape HTML.

**Requirements — all four matter:**

1. **Cache every fetched page to disk**, read from cache by default, `--refresh`
   to re-fetch. Never re-scrape in a loop while developing parsers.
2. **Rate-limit to ≤ 1 request/second** with a descriptive User-Agent. This is a
   small volunteer-run server. Do not parallelise the fetch.
3. **Parse with `html.parser` from the stdlib.** No `requests`, no
   `beautifulsoup4`, and **no regex over HTML** — that is where a MantisBT
   scraper silently starts returning empty fields after any theme change.
   Assert the expected field count per row and **fail loudly** if it changes.
4. **Read-only, always.** Never post, comment, or log in.

Parse per bug: id, summary, description, steps-to-reproduce, status, resolution,
reporter, dates, product version, OS, and attachment URLs.

**Do not download attachments automatically** — note the URLs and stop.

---

## 3. Per-bug record

For each **open, unassigned** bug produce:

| Field | Meaning |
|---|---|
| `id`, `summary`, `status`, `dates`, `version`, `os` | as scraped |
| `repro_class` | `headless` (description implies file load/save/export or CLI), `gui` (needs interaction), `unclear` |
| `auto_repro` | for `headless` bugs **with an attached project**: run the implied CLI verb against it in a sandbox and record command, exit code, stderr verbatim |
| `attachments` | URLs only |

**`auto_repro` is the highest-value field in the whole task** — it is the only
one that produces evidence rather than a guess. Prioritise getting it right over
breadth of parsing.

Output `reports/bugtracker.json` plus a readable `reports/bugtracker.md`.

---

## 4. Explicitly OUT of scope — stage 2

Do **not** implement:

- `code_paths` — keyword→source-file matching
- `likely_stale` heuristics
- `effort_hint`
- any ranking, prioritisation, or "you should fix this next" list

Those need judgment and a calibration set, and a confidently wrong `code_paths`
is worse than an empty one. **An inventory that stays an inventory is exactly
what is wanted here.**

---

## 5. Definition of done — paste real output

### Criterion 1 — the corpus exists

Every open unassigned bug has a record, with no gaps. Report the count and the
`repro_class` distribution.

### Criterion 2 — reproductions attempted

For every `headless` bug with an attachment, show the command run and its real
output. Report how many were attempted and how many completed.

### Criterion 3 — the known-stale three

#256, #278 and #288 were hand-checked as **not reproducible on master**. If your
`auto_repro` covers any of them, show what it found.

**Do not classify them as stale by rule** — that is stage 2's judgment. Just
show the evidence your reproduction attempt produced, whatever it says.

### Criterion 4 — the scraper is honest

Show what happens when a parse field is missing: it must **fail loudly**, not
silently record an empty string. Demonstrate it (e.g. against a malformed
saved page).

---

## 6. Environment + traps

| Thing | Value |
|---|---|
| QET source | `/home/user/qet-fix` |
| Binary | `/home/user/qet-fix/build-fast/qelectrotech` (build with `scripts/qet-fastbuild.sh` if absent) |
| Python | 3.14, **stdlib only** (`urllib.request` + `html.parser`) |

1. **Always pass a timeout** to any QET CLI run. A version-incompatible project
   raises a modal during load and hangs every verb forever — and bugtracker
   attachments are exactly where old-version projects live. Use 120 s.
2. **SingleApplication**: run every reproduction through `simulator/env.py`'s
   `sandbox_context()`. Check `docker ps` first.
3. **`--check-elements` takes an element file or directory, not a project.**
4. Attachments are untrusted input from strangers. Run them in the sandbox,
   never against your own config.

---

## 7. Scope

**May create:** `tools/bugtracker/**`, `reports/bugtracker.{json,md}`, a cache
directory.

**Do NOT:** post, comment, or authenticate to the bugtracker — read-only,
always; download attachments beyond those needed for an attempted repro;
implement any stage-2 field (§4); push or open a PR.

**Never assert "fixed."** Write *"not reproduced on `<sha>` via `<exact
command>`"* and let a human judge.

**Work on a new branch.**

---

## 8. Report

Commit on a new branch. All four criteria with real pasted output, the counts
and distribution, and anything in this brief that was wrong or underspecified —
particularly if the MantisBT HTML does not match what §2 assumes.
