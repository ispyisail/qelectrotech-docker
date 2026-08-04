#!/usr/bin/env bash
# Save-determinism corpus — entrypoint for the qet-determinism compose service.
#
#   docker compose run --rm qet-determinism                    # gate: compare to baseline
#   docker compose run --rm qet-determinism --write-baseline   # record current state
#
# Runs headless via QT_QPA_PLATFORM=offscreen; no Xvfb needed, because
# `qelectrotech --resave` returns before any GUI is initialised.
set -uo pipefail

BINARY="${QET_BINARY:-/usr/local/bin/qelectrotech}"
CORPUS="${QET_CORPUS:-/src/examples}"

echo "── QElectroTech save-determinism corpus ──"
python3 /work/check.py --binary "$BINARY" --corpus "$CORPUS" "$@"
status=$?

echo
if [ $status -eq 0 ]; then
    echo "RESULT: pass"
else
    echo "RESULT: fail (exit $status)"
fi
exit $status
