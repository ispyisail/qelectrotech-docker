#!/usr/bin/env bash
#
# inflight.sh — one view of everything in flight across this project.
#
# Pulls together, from GitHub (read-only) and the local git clone:
#   1. open pull requests grouped by state (awaiting review / changes
#      requested / draft / stale)
#   2. local branches with no corresponding PR — work only this machine knows
#   3. branches whose PR is merged — safe to prune
#
# And the mode that matters most: --search, which greps PR titles, PR bodies
# and local branch names in one pass over cached data. That is the
# duplicate-prevention search (see brief L4: PR #753 was opened as a duplicate
# of #661 because nobody could find the earlier work in one shot).
#
# Strictly read-only against GitHub: no pr create/edit/close/comment/merge and
# no api POST/PATCH/DELETE. Reads git state only — never checks out, prunes,
# or deletes branches.
#
# Usage:
#   inflight.sh                default view (sections above)
#   inflight.sh --search TERM  grep PR titles/bodies + branch names, one pass
#   inflight.sh --refresh      re-query GitHub, rebuild the cache, then run
#   inflight.sh --help
#
# gh results are cached under ~/.cache/qet-inflight/ and read by default so
# the tool stays fast enough that people actually run it (gh is rate-limited).
set -euo pipefail

REPO="qelectrotech/qelectrotech-source-mirror"
AUTHOR="ispyisail"
QET_FIX="${QET_FIX:-/home/user/qet-fix}"
CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/qet-inflight"
PRS_CACHE="$CACHE_ROOT/prs.json"
GH_LIMIT=300

usage() {
  awk 'NR >= 2 { if (/^#/) { sub(/^# ?/, ""); print } else exit }' "$0"
  exit "${1:-0}"
}

SEARCH_TERM=""
REFRESH=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --search)
      [[ $# -ge 2 ]] || { echo "error: --search needs a term (e.g. --search modal)" >&2; exit 1; }
      SEARCH_TERM="$2"
      shift 2
      ;;
    --refresh)
      REFRESH=1
      shift
      ;;
    -h|--help)
      usage 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage 1
      ;;
  esac
done

fetch_prs() {
  mkdir -p "$CACHE_ROOT"
  gh pr list --repo "$REPO" --author "$AUTHOR" --state all --limit "$GH_LIMIT" \
    --json number,title,body,state,updatedAt,isDraft,headRefName,reviewDecision \
    > "$PRS_CACHE.tmp" 2>/dev/null
  if [[ -s "$PRS_CACHE.tmp" ]] && python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$PRS_CACHE.tmp"; then
    mv "$PRS_CACHE.tmp" "$PRS_CACHE"
  else
    rm -f "$PRS_CACHE.tmp"
    return 1
  fi
}

mkdir -p "$CACHE_ROOT"

if [[ "$REFRESH" == 1 ]]; then
  if ! fetch_prs; then
    if [[ -s "$PRS_CACHE" ]]; then
      echo "warning: gh query failed (rate limited?); using cached PR data" >&2
    else
      echo "error: gh query failed and no cached PR data exists" >&2
      exit 1
    fi
  fi
elif [[ ! -s "$PRS_CACHE" ]]; then
  echo "no cache yet — fetching from GitHub..." >&2
  if ! fetch_prs; then
    echo "error: gh query failed (rate limited?) and no cached PR data exists" >&2
    exit 1
  fi
fi

CACHE_AGE="$(date -r "$PRS_CACHE" '+%Y-%m-%d %H:%M:%S')"

export QET_INFLIGHT_PRS="$PRS_CACHE"
export QET_INFLIGHT_QETFIX="$QET_FIX"
export QET_INFLIGHT_REPO="$REPO"
export QET_INFLIGHT_CACHE_AGE="$CACHE_AGE"
if [[ -n "$SEARCH_TERM" ]]; then
  export QET_INFLIGHT_MODE="search"
  export QET_INFLIGHT_TERM="$SEARCH_TERM"
else
  export QET_INFLIGHT_MODE="view"
fi

python3 - <<'PYEOF'
import json, os, subprocess
from datetime import datetime, timezone, timedelta

prs_path = os.environ["QET_INFLIGHT_PRS"]
qet_fix = os.environ["QET_INFLIGHT_QETFIX"]
repo = os.environ["QET_INFLIGHT_REPO"]
mode = os.environ["QET_INFLIGHT_MODE"]
term = os.environ.get("QET_INFLIGHT_TERM", "")
cache_age = os.environ.get("QET_INFLIGHT_CACHE_AGE", "unknown")
stale_days = 30

with open(prs_path) as fh:
    prs = json.load(fh)

for p in prs:
    p["state"] = (p.get("state") or "").upper()
    p["title"] = p.get("title") or ""
    p["body"] = p.get("body") or ""
    p["headRefName"] = p.get("headRefName") or ""

def updated_dt(p):
    return datetime.fromisoformat((p.get("updatedAt") or "").replace("Z", "+00:00"))

# ---- local branches -------------------------------------------------------
branches = []
out = subprocess.run(
    ["git", "-C", qet_fix, "branch", "--no-color"],
    capture_output=True, text=True, check=True,
).stdout
for line in out.splitlines():
    current = line.startswith("*")
    worktree = line.startswith("+")
    name = line.lstrip("*+ ").strip()
    if name:
        branches.append({"name": name, "current": current, "worktree": worktree})

headref_map = {}
for p in prs:
    headref_map.setdefault(p["headRefName"], []).append(p)

TRUNK = {"master", "main"}

def pr_line(p):
    return "#%d %-6s  %s" % (p["number"], p["state"], p["title"])

def branch_label(b):
    mark = "*" if b["current"] else ("+" if b["worktree"] else " ")
    label = b["name"]
    if b["current"]:
        label += "  [current]"
    if b["worktree"]:
        label += "  [in worktree]"
    return "%s %s" % (mark, label)

# ===========================================================================
# VIEW
# ===========================================================================
if mode == "view":
    opens = [p for p in prs if p["state"] == "OPEN"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

    awaiting = [p for p in opens
                if not p["isDraft"] and (p.get("reviewDecision") or "") != "CHANGES_REQUESTED"]
    changes  = [p for p in opens if (p.get("reviewDecision") or "") == "CHANGES_REQUESTED"]
    drafts   = [p for p in opens if p["isDraft"]]
    stale    = [p for p in opens if updated_dt(p) < cutoff]

    def sort_newest(lst):
        return sorted(lst, key=lambda p: p["number"], reverse=True)

    print("QET in-flight  —  %s  @  %s" % (repo, "ispyisail"))
    print("PR cache      : %s (fetched %s)" % (prs_path, cache_age))
    print("Local branches: %s (%d)" % (qet_fix, len(branches)))
    print()

    print("OPEN PULL REQUESTS (%d)" % len(opens))
    print("  awaiting review .... %d" % len(awaiting))
    print("  changes requested .. %d" % len(changes))
    print("  draft .............. %d" % len(drafts))
    print("  stale (>%dd) ....... %d" % (stale_days, len(stale)))
    print()

    def section(title, items, note=None):
        print("%s (%d):" % (title, len(items)))
        if not items:
            print("  (none)")
        else:
            for it in items:
                print("  " + it)
        if note:
            print("  %s" % note)
        print()

    section("Awaiting review", [pr_line(p) for p in sort_newest(awaiting)],
            note="no review yet submitted on any open PR, so this is all non-draft open PRs")
    section("Changes requested", [pr_line(p) for p in sort_newest(changes)])
    section("Draft", [pr_line(p) for p in sort_newest(drafts)])
    section("Stale — open, no update in >%d days" % stale_days, [pr_line(p) for p in sort_newest(stale)],
            note="this group overlaps the three above; a stale draft is listed under both")

    # ---- branch sections ----------------------------------------------------
    no_pr, prunable, closed_only = [], [], []
    for b in branches:
        if b["name"] in TRUNK:
            continue
        matches = headref_map.get(b["name"], [])
        if not matches:
            no_pr.append(b)
        elif any(m["state"] == "MERGED" for m in matches):
            prunable.append((b, [m for m in matches if m["state"] == "MERGED"]))
        elif any(m["state"] == "OPEN" for m in matches):
            pass  # has a live PR; visible above
        else:
            closed_only.append((b, matches))  # PR exists but was closed unmerged

    print("LOCAL BRANCHES WITH NO CORRESPONDING PR (%d)" % len(no_pr))
    if no_pr:
        for b in sorted(no_pr, key=lambda b: b["name"]):
            print("  " + branch_label(b))
        print("  (trunk branch master/main excluded — pushed trunk, not open work)")
    else:
        print("  (none)")
    print("  no PR found = no open/closed/merged PR has this branch as its head ref")
    print()

    print("BRANCHES WHOSE PR IS MERGED — PRUNE SAFE (%d)" % len(prunable))
    if prunable:
        width = max(len(b["name"]) for b, _ in prunable)
        for b, ms in sorted(prunable, key=lambda x: x[0]["name"]):
            for m in sorted(ms, key=lambda m: m["number"], reverse=True):
                wt = "  [in worktree — not deletable yet]" if b["worktree"] else ""
                print("  %-*s  ->  merged in #%d %s%s" % (width, b["name"], m["number"], m["title"], wt))
    else:
        print("  (none)")
    print()

    if closed_only:
        print("Branches whose only matching PR was CLOSED unmerged (%d) — still your work, not prunable:" % len(closed_only))
        for b, ms in sorted(closed_only, key=lambda x: x[0]["name"]):
            for m in ms:
                print("  %s  ->  #%d %s" % (b["name"], m["number"], pr_line(m).split("  ", 1)[1]))
        print()

# ===========================================================================
# SEARCH — one pass over titles, bodies, and branch names
# ===========================================================================
else:
    t = term.lower()
    pr_matches = []
    for p in prs:
        hit = t in p["title"].lower() or t in p["body"].lower()
        if hit:
            pr_matches.append(p)

    branch_matches = [b for b in branches if t in b["name"].lower()]

    print('SEARCH "%s"  —  %d PR match(es), %d branch match(es)' % (term, len(pr_matches), len(branch_matches)))
    print("scanned %d PRs (open+closed+merged) and %d local branches in one pass" % (len(prs), len(branches)))
    print()

    if pr_matches:
        print("PULL REQUESTS (all states — a closed/merged PR is still prior art):")
        for p in sorted(pr_matches, key=lambda p: p["number"], reverse=True):
            line = "  " + pr_line(p)
            if t not in p["title"].lower():
                line += "   [body match]"
            print(line)
        print()
    else:
        print("PULL REQUESTS: (no match)")
        print()

    if branch_matches:
        print("LOCAL BRANCHES:")
        for b in sorted(branch_matches, key=lambda b: b["name"]):
            matches = headref_map.get(b["name"], [])
            ref = ""
            if matches:
                m = sorted(matches, key=lambda m: m["number"], reverse=True)[0]
                ref = "   ->  PR #%d (%s)" % (m["number"], m["state"])
            print("  %s%s%s" % (b["name"], "  [in worktree]" if b["worktree"] else "", ref))
        print()
    else:
        print("LOCAL BRANCHES: (no match)")
        print()
PYEOF
