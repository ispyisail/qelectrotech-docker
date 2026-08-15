# TASK BRIEF — L4: in-flight visibility

You are working in `/home/user/qelectrotech-docker`. This brief is
self-contained — do not assume any skill files or plan documents are loaded.

**This is data plumbing.** `gh` queries and git commands, formatted usefully.
No design decisions remain.

---

## 1. The problem this solves

There are **50 open pull requests** and **118 local branches** across this
project. There is no single view of them, and the cost of that is concrete:

A "non-interactive mode for headless runs" was recently designed, built,
verified, and opened as PR #753 — then discovered to be a **duplicate of PR
#661**, opened twelve days earlier from the same account, with the same hook
point and the same approach. #753 was closed. One search would have prevented
the entire wasted effort.

Your job: make that search take five seconds.

---

## 2. What to build

`scripts/inflight.sh` (grow it into `tools/inflight/` only if it genuinely
outgrows a script).

### Default view

Running it with no arguments shows:

1. **Open PRs grouped by state** — awaiting review, changes requested, draft,
   and **stale** (no update in >30 days).
2. **Local branches with no corresponding PR** — work that exists only on this
   machine and is invisible to everyone else.
3. **Branches whose PR is merged** — safe to prune.

### `--search <term>` — the mode that matters most

Greps PR titles, PR bodies, and local branch names **in one pass**. Make this
the fastest path in the tool; it is the mode that prevents duplicate work.

### Caching

- Cache `gh` results to disk (e.g. under `~/.cache/qet-inflight/`).
- Read from cache by default; add `--refresh` to re-query.
- Do not re-query GitHub on every invocation — the tool is useless if it is slow
  enough that people skip it.

---

## 3. Environment facts

| Thing | Value |
|---|---|
| Work here | `/home/user/qelectrotech-docker` |
| QET source (branches live here) | `/home/user/qet-fix` |
| Upstream repo | `qelectrotech/qelectrotech-source-mirror` |
| PR author to filter on | `ispyisail` |
| Python | 3.14, **stdlib only** — add no dependencies |
| `gh` CLI | installed and authenticated |

Useful starting point:

```bash
gh pr list --repo qelectrotech/qelectrotech-source-mirror --author ispyisail \
  --state open --limit 200 --json number,title,state,updatedAt,isDraft,headRefName
```

Local branches: `git -C /home/user/qet-fix branch`.

**Traps that apply:**

1. **`gh` is rate-limited.** This is exactly why the cache is required, not
   optional. A `--refresh` that runs on every invocation will get throttled.
2. **Branch names do not reliably match PR head refs.** Some branches were
   pushed under a different name, and some PRs were opened from a fork. Match on
   `headRefName` where available, and treat a non-match as "no PR found" rather
   than asserting the branch is unpushed.
3. **A branch checked out in a git worktree is marked `+` by `git branch`.**
   Strip that marker when parsing; don't let it corrupt branch names.

---

## 4. Definition of done — paste real output for each

### Criterion 1 — the duplicate-prevention search

```bash
scripts/inflight.sh --search modal
```

**Expected:** surfaces **both #661 and #753** (and #752, which also matches).
Verified 2026-08-16 — these three PRs all contain "modal" in their titles:

- `#753 CLOSED  Add a non-interactive mode so headless runs cannot block on a modal`
- `#752 OPEN    Take the modal dialog out of RotateTextsCommand's constructor`
- `#661 OPEN    Fix command-line tools hanging forever on a modal message box`

Then:

```bash
scripts/inflight.sh --search "non-interactive"
```

**Expected:** surfaces #753 at minimum.

These are the two searches that would have prevented the duplicate. If the tool
does not surface them, it has not solved the problem it exists for.

### Criterion 2 — the default view

```bash
scripts/inflight.sh
```

Must show all three sections. Paste the output.

**Sanity-check the numbers by hand** and report whether they match:

- open PRs should be around **50**
- local branches around **118**

If your counts differ substantially, say so and explain why — a stale-branch
count that is quietly wrong is worse than no tool.

### Criterion 3 — caching works

Time two consecutive runs. The second must be **noticeably faster** than the
first. Then show `--refresh` re-queries. Paste all three timings.

---

## 5. Scope boundary

**You may create or modify:**

- `scripts/inflight.sh`
- `tools/inflight/**` (only if the script genuinely outgrows one file)
- A cache directory under `~/.cache/`

**Do not:**

- Modify anything in `/home/user/qet-fix` — this tool only **reads** git state.
  No checkouts, no branch deletions, no pruning. Reporting that a branch is
  prunable is the deliverable; pruning it is not.
- Run any `gh` command that **writes**: no `pr create`, `pr edit`, `pr close`,
  `pr comment`, `pr merge`, or `api -X POST/PATCH/DELETE`. This tool is
  strictly read-only against GitHub.
- Touch `simulator/`, `scenarios/`, `tests/`, or any `.md` plan file.
- Push, open a pull request, or post anywhere.

---

## 6. How to report back

Commit on a **new branch**, with a message describing what the tool *shows*.

Report:

1. **All three criteria**, each with its exact command and **real pasted
   output** — not a summary.
2. **Your counts** for open PRs, branches without PRs, and prunable branches —
   and whether they matched the expected ballpark.
3. **Anything in this brief that was wrong, impossible, or underspecified.** Say
   so plainly rather than working around it silently.

If criterion 1 does not surface #661 and #753, **say so and stop.** That search
is the entire justification for the tool — a version of it that misses the known
duplicate would give false confidence, which is worse than having no tool at
all.
