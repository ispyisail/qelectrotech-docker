#!/usr/bin/env bash
# Entry point for the fuzzer container.
# Starts Xvfb, optional window manager, then runs the fuzzer.
#
# Key env vars:
#   FUZZER_HOURS           — how long to fuzz (default 1)
#   FUZZER_SPEED           — slow | normal | fast (default normal)
#   FUZZER_SEED            — random seed
#   FUZZER_SCREENSHOT_INT  — seconds between screenshots (default 60)
#   FUZZER_SELF_TEST=1     — run self-test instead of fuzzing

set -euo pipefail

DISPLAY="${DISPLAY:-:99}"
SCREEN="${SCREEN:-1280x800x24}"
LOG_DIR="${FUZZER_LOG_DIR:-/fuzzer/logs}"
HOURS="${FUZZER_HOURS:-1}"
SPEED="${FUZZER_SPEED:-normal}"
SEED="${FUZZER_SEED:-}"
SCREENSHOT_INT="${FUZZER_SCREENSHOT_INT:-60}"
SELF_TEST="${FUZZER_SELF_TEST:-0}"

mkdir -p "$LOG_DIR/screenshots"

echo "[run.sh] Starting Xvfb on $DISPLAY ($SCREEN)"
Xvfb "$DISPLAY" -screen 0 "$SCREEN" +extension GLX &
XVFB_PID=$!
sleep 1.5

# Lightweight window manager helps QET size itself properly
if command -v openbox >/dev/null 2>&1; then
    DISPLAY="$DISPLAY" openbox &
    sleep 0.5
elif command -v fluxbox >/dev/null 2>&1; then
    DISPLAY="$DISPLAY" fluxbox &
    sleep 0.5
fi

export DISPLAY

SEED_ARG=()
[ -n "$SEED" ] && SEED_ARG=(--seed "$SEED")

if [ "$SELF_TEST" = "1" ]; then
    echo "[run.sh] Running self-test..."
    python3 /fuzzer/fuzzer.py --self-test 2>&1 | tee "$LOG_DIR/selftest.log"
    EXIT_CODE=${PIPESTATUS[0]}
    echo "[run.sh] Self-test exited with code $EXIT_CODE"
    echo "[run.sh] Screenshots saved to: $LOG_DIR/screenshots/"
    kill "$XVFB_PID" 2>/dev/null || true
    exit $EXIT_CODE
fi

echo "[run.sh] Fuzzing for ${HOURS}h at speed=${SPEED}, screenshots every ${SCREENSHOT_INT}s"
python3 /fuzzer/fuzzer.py \
    --hours "$HOURS" \
    --speed "$SPEED" \
    --screenshot-interval "$SCREENSHOT_INT" \
    "${SEED_ARG[@]}" \
    2>&1 | tee "$LOG_DIR/fuzzer.log"

echo "[run.sh] Fuzzing done.  Generating report..."
python3 /fuzzer/analyze.py "$LOG_DIR/crashes.jsonl" \
    --out "$LOG_DIR/report.txt" || true

echo "[run.sh] Report: $LOG_DIR/report.txt"
echo "[run.sh] Screenshots: $LOG_DIR/screenshots/"

kill "$XVFB_PID" 2>/dev/null || true
