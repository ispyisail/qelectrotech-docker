#!/usr/bin/env bash
#
# qet-ab.sh -- A/B harness entry point for QElectroTech (LAB-PLAN.md L1).
#
# Builds two variants of QET (each a git ref, resolved and built in its
# own worktree/build tree under <repo>/build-ab/), runs the same CLI
# command against both inside isolated simulator/env.py sandboxes, and
# classifies the result as one of:
#
#   same           -- identical exit code, output, and any produced files
#   differs         -- both completed but something differs
#   a-only-fails    -- variant A crashed/timed out, B did not
#   b-only-fails    -- variant B crashed/timed out, A did not
#
# Exit code is 0 only for `same`.
#
# Usage:
#   scripts/qet-ab.sh --a master --b fix-cli-modal-dialog-hang \
#       -- --info /home/user/qet-fix/examples/schema_indus.qet
#
#   scripts/qet-ab.sh --a HEAD --b HEAD~1 --patch revert.diff \
#       -- --test-ops in.qet ops.json out.qet
#
# Everything after a literal '--' is the command, passed unchanged to
# both variants' qelectrotech binary. Options before '--' (see
# `scripts/qet-ab.sh --a x --b y --help` -- actually just run with no
# args past the harness options to see argparse's own --help):
#
#   --a REF          variant A (required)
#   --b REF          variant B (required)
#   --patch FILE     patch applied to variant B's worktree before building
#   --repo PATH      QET source checkout (default /home/user/qet-fix)
#   --build-root DIR default <repo>/build-ab
#   --timeout SECS   per-variant run timeout (default 60)
#   --format text|json
#   --keep           keep each variant's produced-files scratch dir
#
# Implementation: tools/abdiff/ (build.py, run.py, compare.py, report.py).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
exec python3 -m tools.abdiff "$@"
