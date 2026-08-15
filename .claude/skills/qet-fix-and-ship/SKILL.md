---
name: qet-fix-and-ship
description: Write, verify and submit a QElectroTech change the way that actually gets merged upstream — branch, fast edit loop, verification, PR conventions and their known failure modes. Load when implementing a fix or feature in the QET source, or when preparing or submitting a pull request to qelectrotech.
---

# Fixing and shipping a QET change

Load `qet-env` first. Reproduce before you code (`qet-repro`).

## What actually merges

Measured across this account's PRs: **68 merged, 7 closed unmerged, 45 open** —
91% acceptance on anything that gets a decision. The maintainer is highly
responsive; the common assumption that features stall upstream is wrong here.

| Change type | Avg time to merge |
|---|---|
| "Fix bugtracker #NNN" | **0.2 days** |
| Feature (small, self-contained) | 1.7 days |
| Other fix | 2.6 days |

**What fails:** packaging and build-infrastructure changes (they need a
maintainer decision about release infra, not better code), and design-heavy
features that fight the existing architecture. If a change is in either
category, say so up front and get a signal before building it.

## The loop

```bash
cd /home/user/qet-fix
git checkout master && git pull upstream master
git checkout -b fix/short-description
# edit
scripts/qet-fastbuild.sh build /home/user/qet-fix/build-fast   # ~1.7 s
```

Never develop inside Docker — it is roughly 100× slower per iteration.

Keep the change **small and self-contained**. Match the surrounding code's
idiom, comment density and naming. Follow existing patterns rather than
introducing new ones: when adding a CLI flag, mirror `setBackupEnabled()`; when
adding a conductor property, mirror the existing line-style plumbing.

## Verify before shipping

1. **The exact symptom from the report is gone.** Re-run the reproduction
   command verbatim, not an approximation of it.
2. **Nothing else broke:**
   - touched save/load → `docker compose run --rm qet-determinism`
   - touched sanitizer-sensitive code → `docker compose run --rm qet-asan-regression`
   - general → `docker compose run --rm qet-test`
3. **GUI behaviour unchanged** if the change touches a shared code path. CLI
   fixes that alter GUI prompts are a common trap — check both.
4. `/code-review` on the diff.

## Translations

French is the `tr()` source language throughout QET — new user-facing strings
are written in French. `lupdate` is a **manual CMake target**, not automatic;
do not hand-edit `.ts` files.

## Opening the PR

```bash
gh pr create --repo qelectrotech/qelectrotech-source-mirror \
             --base master --head ispyisail:fix/short-description \
             --title "Fix bugtracker #NNN: <symptom>" --body "..."
```

- **`--base master` always.** Not a fork-only parent branch, even when the work
  is stacked — a stacked PR still targets `master`.
- Remotes here: `upstream` = qelectrotech (the real repo), `origin` = ispyisail
  (the fork you push to).
- **Cite the bugtracker number in the title** when there is one. That is the
  fastest-merging category and the citation is why.

## Known PR tooling failure

**`gh pr edit` fails on this repo** with a Projects-classic GraphQL error. To
change a title or body, PATCH via the REST API instead, then **re-read the PR
to confirm the change actually landed** — the failure is silent-ish and leaves
the old body in place.

```bash
gh api -X PATCH repos/qelectrotech/qelectrotech-source-mirror/pulls/NNN \
  -f body="..." && gh pr view NNN --json body
```

## Throwaway branches

`test-build-logging-wiring` and similar integration branches exist so several
PRs can be exercised together. They are **not proposed changes** — never open a
PR from one.

## Before you push

Do not push or open a PR unless the user asked for it. Report what you built
and what you verified, and let them decide.
