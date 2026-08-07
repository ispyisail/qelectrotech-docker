#!/usr/bin/env bash
# Entry point for the EDZ importer fuzzer container.
# 1. Generate malformed corpus files.
# 2. Run the harness under ASAN against every file.
# 3. Print any ASAN reports.
set -euo pipefail

LOG_DIR="${EDZ_FUZZ_LOG_DIR:-/edz-fuzzer/logs}"
CORPUS="/edz-fuzzer/corpus"
BINARY="/edz-fuzzer/build/fuzz_edz"

mkdir -p "$LOG_DIR" "$CORPUS"

echo "[edz-fuzzer] Generating corpus..."
python3 /edz-fuzzer/gen_corpus.py "$CORPUS" 2>&1 | tee "$LOG_DIR/corpus.log"

echo ""
echo "[edz-fuzzer] Running harness under ASAN..."
ASAN_OPTIONS="halt_on_error=0:log_path=$LOG_DIR/asan:detect_leaks=1" \
UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=0" \
    "$BINARY" "$CORPUS" 2>&1 | tee "$LOG_DIR/results.log"

echo ""
ASAN_FILES=$(ls "$LOG_DIR"/asan.* 2>/dev/null || true)
if [ -n "$ASAN_FILES" ]; then
    echo "[edz-fuzzer] ASAN/UBSan reports found:"
    cat $ASAN_FILES
else
    echo "[edz-fuzzer] No ASAN/UBSan reports — clean run."
fi

echo ""
echo "[edz-fuzzer] Done. Logs: $LOG_DIR"
