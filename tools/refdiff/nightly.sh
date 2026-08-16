#!/usr/bin/env bash
#
# nightly.sh -- cron-friendly wrapper for the W3 regression sweep.
#
# Runs `master` vs `master@{yesterday}` through tools.refdiff and writes a
# dated report under refdiff-reports/. The report is written every run (that
# is the artifact you read the morning after); this wrapper only *notifies*
# on a transition -- a NOTICE banner to stdout (which cron then emails) when
# the run's summary line differs from the previous run's. A stable clean
# sweep therefore produces a dated report but no notification.
#
# Local only: writes into refdiff-reports/, never posts anywhere, never
# touches .github/ or any CI service.
#
# Register it (user crontab) with e.g.:
#   37 3 * * * cd /home/user/qelectrotech-docker && tools/refdiff/nightly.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

REPORTS_DIR="$REPO_ROOT/refdiff-reports"
STATE_FILE="$REPORTS_DIR/.last-run-state"
mkdir -p "$REPORTS_DIR"

run_log="$(mktemp)"
trap 'rm -f "$run_log"' EXIT

set +e
python3 -m tools.refdiff --base master --head 'master@{yesterday}' "$@" >"$run_log" 2>&1
rc=$?
set -e

# Echo the full run log so cron's mail body always has it (including any
# non-transition run), then decide whether to add the transition notice.
cat "$run_log"

summary="$(grep -E '^  [0-9]+ same,' "$run_log" | head -n 1 || true)"
if [[ -z "$summary" ]]; then
    echo "refdiff-nightly: run produced no summary line (rc=$rc)" >&2
    exit "$rc"
fi

prev="$(cat "$STATE_FILE" 2>/dev/null || true)"
if [[ "$summary" != "$prev" ]]; then
    echo
    echo "======================================================================"
    echo "REFDIFF NIGHTLY: RESULT TRANSITION"
    echo "  previous : ${prev:-<no previous run recorded>}"
    echo "  now      : $summary"
    echo "======================================================================"
fi
printf '%s\n' "$summary" > "$STATE_FILE"

exit "$rc"
