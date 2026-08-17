# TASK BRIEF — triage the bugtracker corpus into fixable candidates

Work in this repo. Self-contained.

---

## 0. HOW THIS TASK ENDS — read first

Seven of seventeen sessions on this project ended by **announcing they would
wait** instead of waiting. Two more **crashed and lost everything** because
nothing was on disk.

- **Never end your turn waiting.** Poll in a loop.
- **Commit early and often.**
- **Never report a criterion done without pasting its real output.**

```bash
echo "$(date +%H:%M:%S) <what you just finished>" >> /tmp/bt-progress.log
```

---

## 1. What exists

`reports/bugtracker.json` — 91 open, unassigned QElectroTech bugtracker entries,
already scraped (89 `new`, 2 `acknowledged`). Fields include `id`, `summary`,
`description`, `category`, `repro_class` (`headless` 13 / `gui` 60 /
`unclear` 18), `attachments`, `date_submitted`.

**Do not re-scrape the bugtracker.** It is a small volunteer-run server and the
corpus is already on disk. If you must fetch anything, rate-limit to
≤1 request/second with a descriptive User-Agent, and **never post, comment or
log in.**

## 2. The job

Classify each of the 91 into exactly one bucket, with a one-line reason:

| Bucket | Meaning |
|---|---|
| `bug-fixable` | a real defect, and the fix looks self-contained |
| `bug-hard` | a real defect, but large or architectural |
| `rfe` | a feature request, not a defect |
| `needs-info` | too vague to act on without asking the reporter |
| `likely-fixed` | describes behaviour that current master no longer has |

**`likely-fixed` must be evidence-based**, not a guess — three hand-picked
entries (#256, #278, #288) already turned out to be fixed years ago and never
closed. Say what you checked.

Then, for everything in `bug-fixable`, add:

- `entry_point` — the file(s)/class the fix would touch, found by reading the
  source, not guessed from the summary
- `test_route` — how it could be verified **headlessly**, naming a tool in
  `tools/` if one applies
- `size` — `one-liner` / `small` / `medium`

Output `reports/bugtracker-triage.{json,md}`, sorted with `bug-fixable`
one-liners first.

## 3. Tools you already have

Use them rather than inventing new ones:

| Tool | What it can verify |
|---|---|
| `tools/crosspage` | folio-reference arrow structure |
| `tools/exportleak` | anything that leaks into PDF/PNG/SVG export |
| `tools/labelstability` | label/formula behaviour across folio moves |
| `tools/pagemoves` | link survival across page operations |
| `tools/interactionaudit` | what double-click / right-click / hover do per item class |
| `tools/actionaudit` | every QAction and its shortcut binding |
| QET CLI | `--info`, `--resave`, `--export-*`, `--check-elements` |

## 4. Definition of done — paste real output

1. **All 91 classified**, with the bucket distribution.
2. **The `bug-fixable` list**, each with entry point, test route and size.
3. **At least three entry points verified** by opening the source and quoting
   the relevant lines — not inferred from the bug title.
4. **Anything you reclassify** from the existing `repro_class` — say which and
   why. That field was assigned by a scraper and is not authoritative.

## 5. Traps

1. **`/home/user/qet-fix` is on `cabinet-layout-editor`, ~195 commits behind
   upstream.** For source questions use `upstream/master` (`git show
   upstream/master:<path>` or a worktree). Record which you used.
2. **Never `git checkout`/`stash`/`reset`** in that tree — it holds uncommitted
   work.
3. **Do not fix anything.** This task produces a ranked list; fixes are separate.
4. **Do not file, comment on, or close anything upstream.**
5. A French-language bug report is not automatically vague — translate before
   marking `needs-info`.

## 6. Scope

**May create:** `reports/bugtracker-triage.{json,md}`, and a small script under
`tools/bugtracker/` if it helps.

**Do NOT:** modify QET source; re-scrape the tracker; touch other `tools/`;
push or open a PR.

**Work on the branch you are on.**

## 7. Report

All four criteria with real pasted output, the bucket distribution, and anything
in this brief that was wrong or underspecified.
