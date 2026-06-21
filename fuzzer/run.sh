#!/usr/bin/env bash
# Entry point for the fuzzer container.
# Starts Xvfb, optional window manager, then runs the fuzzer.

set -euo pipefail

DISPLAY="${DISPLAY:-:99}"
SCREEN="${SCREEN:-1280x800x24}"
LOG_DIR="${FUZZER_LOG_DIR:-/fuzzer/logs}"
HOURS="${FUZZER_HOURS:-1}"
SPEED="${FUZZER_SPEED:-normal}"
SEED="${FUZZER_SEED:-}"

mkdir -p "$LOG_DIR"

echo "[run.sh] Starting Xvfb on $DISPLAY ($SCREEN)"
Xvfb "$DISPLAY" -screen 0 "$SCREEN" +extension GLX &
XVFB_PID=$!
sleep 1.5

# Optional: lightweight window manager helps QET size itself properly
if command -v openbox >/dev/null 2>&1; then
    DISPLAY="$DISPLAY" openbox &
    sleep 0.5
elif command -v fluxbox >/dev/null 2>&1; then
    DISPLAY="$DISPLAY" fluxbox &
    sleep 0.5
fi

export DISPLAY

echo "[run.sh] Fuzzing for ${HOURS}h at speed=${SPEED}"
SEED_ARG=()
[ -n "$SEED" ] && SEED_ARG=(--seed "$SEED")

python3 /fuzzer/fuzzer.py \
    --hours "$HOURS" \
    --speed "$SPEED" \
    "${SEED_ARG[@]}" \
    2>&1 | tee "$LOG_DIR/fuzzer.log"

echo "[run.sh] Fuzzing done.  Generating report..."
python3 /fuzzer/analyze.py "$LOG_DIR/crashes.jsonl" \
    --out "$LOG_DIR/report.txt" || true

echo "[run.sh] Report: $LOG_DIR/report.txt"

kill "$XVFB_PID" 2>/dev/null || true
