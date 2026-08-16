#!/usr/bin/env bash
#
# lab-rebase.sh — keep the permanent --test-ops "lab binary" current with
# upstream and prove every op still works.
#
# What it does:
#   1. Fetch upstream/master (read-only; never touches any checked-out tree).
#   2. Bring the lab branch current with upstream/master.
#   3. Rebuild it into /home/user/qet-fix/build-lab/.
#   4. Smoke-test each --test-ops op and report PASS/FAIL per op.
#
# Why it targets lab/test-ops-extended rather than feature/test-ops-cli:
#   L2's §4 required merging fix/rotate-texts-dialog-out-of-command (PR #752)
#   into the lab branch before implementing rotate_texts. That merge (a) gave
#   the branch a merge commit and (b) already pulled upstream/master into it.
#   feature/test-ops-cli alone predates both the merge and the five new ops, so
#   building it could not smoke-test rotate_texts. The permanent binary is the
#   lab branch. Because the branch now carries a merge commit, the update path
#   uses `git rebase --rebase-merges` (a plain rebase would linearize it and
#   drop the §4 merge, re-introducing the conflicts that merge resolved).
#
# Safety (L2 §5a): this script only ever runs read-only git commands in
# /home/user/qet-fix (fetch, worktree list). The rebase happens inside the
# dedicated lab worktree, never in the main tree, and aborts on any conflict
# rather than leaving the branch mid-rebase.
#
# Usage:
#   scripts/lab-rebase.sh            # default branch + worktree + build dir
#
# Overrides (env):
#   QET_SRC        main QET repo            (default $HOME/qet-fix)
#   LAB_BRANCH     branch to keep current   (default lab/test-ops-extended)
#   LAB_WORKTREE   dedicated worktree path  (default $HOME/qet-fix-wt/lab)
#   LAB_BUILD      build tree               (default $HOME/qet-fix/build-lab)
#   SKIP_REBASE    set to 1 to skip the fetch/rebase step (build+smoke only)
#
set -euo pipefail

QET_SRC="${QET_SRC:-$HOME/qet-fix}"
LAB_BRANCH="${LAB_BRANCH:-lab/test-ops-extended}"
LAB_WORKTREE="${LAB_WORKTREE:-$HOME/qet-fix-wt/lab}"
LAB_BUILD="${LAB_BUILD:-$HOME/qet-fix/build-lab}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FASTBUILD="$HERE/qet-fastbuild.sh"

die() { echo "lab-rebase: error: $*" >&2; exit 1; }

[[ -d "$QET_SRC/.git" ]] || die "no git repo at QET_SRC=$QET_SRC"
[[ -x "$FASTBUILD" ]] || die "missing $FASTBUILD"

# ---------------------------------------------------------------- 1. fetch --
if [[ "${SKIP_REBASE:-0}" != "1" ]]; then
  echo "lab-rebase: fetching upstream/master"
  git -C "$QET_SRC" fetch upstream master || die "git fetch upstream failed"
fi

# Find (or create) the worktree that has LAB_BRANCH checked out.
WT_PATH="$(git -C "$QET_SRC" worktree list --porcelain \
  | awk -v b="$LAB_BRANCH" '
      /^worktree / { wt=$2 }
      /^branch / && $0 ~ ("refs/heads/" b "$") { print wt }
    ' | head -1)"

if [[ -z "$WT_PATH" ]]; then
  echo "lab-rebase: branch $LAB_BRANCH not checked out anywhere; creating worktree at $LAB_WORKTREE"
  git -C "$QET_SRC" worktree add "$LAB_WORKTREE" "$LAB_BRANCH" \
    || die "could not create worktree (is $LAB_BRANCH checked out elsewhere?)"
  WT_PATH="$LAB_WORKTREE"
else
  echo "lab-rebase: $LAB_BRANCH checked out at $WT_PATH"
fi

# Never rebase over uncommitted work.
if [[ -n "$(git -C "$WT_PATH" status --porcelain)" ]]; then
  die "worktree $WT_PATH is dirty — commit or stash there first, then re-run"
fi

# -------------------------------------------------------------- 2. rebase --
if [[ "${SKIP_REBASE:-0}" != "1" ]]; then
  if git -C "$QET_SRC" merge-base --is-ancestor upstream/master "$LAB_BRANCH"; then
    echo "lab-rebase: $LAB_BRANCH already contains upstream/master — up to date, no rebase"
  else
    echo "lab-rebase: rebasing $LAB_BRANCH onto upstream/master (--rebase-merges)"
    if ! git -C "$WT_PATH" rebase --rebase-merges upstream/master; then
      git -C "$WT_PATH" rebase --abort 2>/dev/null || true
      die "rebase conflicted — aborted. Resolve manually in $WT_PATH; the branch is unchanged."
    fi
  fi
fi

# -------------------------------------------------------------- 3. build --
if [[ ! -f "$LAB_BUILD/CMakeCache.txt" ]]; then
  echo "lab-rebase: configuring $WT_PATH -> $LAB_BUILD"
  "$FASTBUILD" configure "$WT_PATH" "$LAB_BUILD"
fi
echo "lab-rebase: building qelectrotech in $LAB_BUILD"
"$FASTBUILD" build "$LAB_BUILD"
BIN="$LAB_BUILD/qelectrotech"
[[ -x "$BIN" ]] || die "build produced no binary at $BIN"

# --------------------------------------------------------- 4. smoke test --
EXAMPLE="$WT_PATH/examples/741.qet"
[[ -f "$EXAMPLE" ]] || die "smoke-test fixture missing: $EXAMPLE"
ELEMENT_UUID="$(grep -o '<element [^>]*uuid="{[^}]*}"' "$EXAMPLE" | head -1 | grep -o '{[^}]*}')"
[[ -n "$ELEMENT_UUID" ]] || die "could not extract an element uuid from $EXAMPLE"

SANDBOX="$(mktemp -d /tmp/lab-rebase-sb.XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT
mkdir -p "$SANDBOX"/{cfg,home}
export QT_QPA_PLATFORM=offscreen
export XDG_CONFIG_HOME="$SANDBOX/cfg"
export HOME="$SANDBOX/home"

# name -> ops JSON. Each op must run headless to completion and print the
# one-line JSON summary; PASS/FAIL is decided on exit code + summary presence.
smoke_one() {
  local name="$1" ops="$2"
  local in="$SANDBOX/in.qet" out="$SANDBOX/out.qet" opsf="$SANDBOX/ops.json" log="$SANDBOX/log"
  cp "$EXAMPLE" "$in"
  printf '%s' "$ops" > "$opsf"
  if timeout 30 "$BIN" --test-ops "$in" "$opsf" "$out" >"$log" 2>&1; then
    local summary
    summary="$(grep 'ops_applied' "$log" | tail -1)"
    if [[ -n "$summary" ]]; then
      echo "PASS  $name  $summary"
      return 0
    fi
  fi
  echo "FAIL  $name  (no JSON summary; see $log)"
  return 1
}

echo "lab-rebase: smoke-testing ops against $EXAMPLE"
fails=0
smoke_one select_all   '[{"op":"select_all"}]' || fails=$((fails+1))
smoke_one move         '[{"op":"select_all"},{"op":"move","dx":10,"dy":10}]' || fails=$((fails+1))
smoke_one diagram      '[{"op":"diagram","index":0}]' || fails=$((fails+1))
smoke_one set_property "[{\"op\":\"set_property\",\"uuid\":\"$ELEMENT_UUID\",\"key\":\"label\",\"value\":\"SMOKE\"}]" || fails=$((fails+1))
smoke_one rotate_texts '[{"op":"rotate_texts","angle":45}]' || fails=$((fails+1))

echo
if (( fails )); then
  echo "lab-rebase: $fails op(s) FAILED"
  exit 1
fi
echo "lab-rebase: all ops PASS"
