#!/usr/bin/env bash
#
# run.sh — Build & run the PR #519 targeted ASan regression tests.
#
# For each test it builds two variants from the SAME source:
#     PATCHED  — the PR #519 code path (default)
#     LEGACY   — the pre-patch code path (-DLEGACY)
# then runs both under AddressSanitizer + LeakSanitizer and reports, per test:
#     - leaked bytes attributable to OUR code, LEGACY vs PATCHED (the fix delta)
#     - any use-after-free / double-free / SEGV in the PATCHED build (must be 0)
#
# Designed to run inside the qelectrotech:test image (has g++, Qt5 dev, ASan).
# Output: a human-readable table on stdout and a Markdown report at
# $OUTDIR/report.md (default ./report.md next to this script).

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="${OUTDIR:-$HERE}"
mkdir -p "$OUTDIR"
REPORT="$OUTDIR/report.md"
RAW="$OUTDIR/raw"
mkdir -p "$RAW"

CXX="${CXX:-g++}"
QT_CFLAGS="-fPIC -I/usr/include/x86_64-linux-gnu/qt5 \
  -I/usr/include/x86_64-linux-gnu/qt5/QtCore \
  -I/usr/include/x86_64-linux-gnu/qt5/QtGui \
  -I/usr/include/x86_64-linux-gnu/qt5/QtWidgets"
QT_LIBS="-lQt5Widgets -lQt5Gui -lQt5Core"
ASAN="-fsanitize=address -g -O1 -fno-omit-frame-pointer"

export QT_QPA_PLATFORM=offscreen
export ASAN_OPTIONS="detect_leaks=1:exitcode=1:abort_on_error=0:detect_odr_violation=0"
export LSAN_OPTIONS="suppressions=$HERE/lsan.supp:print_suppressions=0"

# Tests:  id|source|short title
TESTS=(
  "t1|t1_exportdialog_qdeleteall.cpp|ExportDialog: qDeleteAll(diagram_lines_) in dtor"
  "t2|t2_genericpanel_contract.cpp|GenericPanel: getItemForDiagram nullptr contract"
  "t3|t3_styleeditor_layout.cpp|StyleEditor: parentless QGridLayout ownership"
  "t4|t4_elementscene_pastearea.cpp|ElementScene: m_paste_area delete + double-free guard"
)

# parse_leak_bytes <report-file> <source-basename>
# Sums "Direct/Indirect leak of N byte(s)" for leak blocks whose stack mentions
# the given source basename — i.e. leaks attributable to OUR test code.
parse_leak_bytes() {
  # Portable (mawk/gawk): for each leak block, sum bytes only if the block's
  # stack references the test source basename.
  awk -v src="$2" '
    /(Direct|Indirect) leak of [0-9]+ byte/ {
      if (pending && mine) total += bytes
      line = $0
      sub(/.*leak of /, "", line)
      sub(/ byte.*/,    "", line)
      bytes = line + 0; mine = 0; pending = 1; next
    }
    pending && index($0, src) { mine = 1 }
    END { if (pending && mine) total += bytes; print total + 0 }
  ' "$1"
}

# detect_fatal <report-file> -> prints comma-list of fatal ASan error kinds
detect_fatal() {
  local f="$1" kinds=()
  grep -q "heap-use-after-free" "$f" && kinds+=("use-after-free")
  grep -q "double-free\|attempting double-free" "$f" && kinds+=("double-free")
  grep -q "SEGV on unknown address\|SUMMARY: AddressSanitizer: SEGV" "$f" && kinds+=("SEGV")
  grep -q "heap-buffer-overflow" "$f" && kinds+=("heap-buffer-overflow")
  (IFS=,; echo "${kinds[*]:-none}")
}

echo "# PR #519 — Targeted ASan regression evidence" >  "$REPORT"
echo ""                                              >> "$REPORT"
echo "Each fix is compiled in two variants from one source: \`LEGACY\` (pre-patch)" >> "$REPORT"
echo "and patched. Both run under AddressSanitizer + LeakSanitizer (Qt offscreen)." >> "$REPORT"
echo "\"Leaked (ours)\" counts only leak blocks whose stack references the test" >> "$REPORT"
echo "source, isolating the patch's effect from third-party Qt noise." >> "$REPORT"
echo ""                                              >> "$REPORT"
echo "| Test | Fix | LEGACY leak (ours) | PATCHED leak (ours) | Fixed | PATCHED fatal errors |" >> "$REPORT"
echo "|------|-----|-------------------:|--------------------:|------:|----------------------|" >> "$REPORT"

printf "\n%-4s %-58s %12s %12s %10s\n" "TEST" "FIX" "LEGACY" "PATCHED" "FATAL"
printf '%.0s-' {1..100}; printf "\n"

overall_ok=1

for entry in "${TESTS[@]}"; do
  IFS='|' read -r id src title <<< "$entry"
  base="$(basename "$src")"
  legacy_bin="$RAW/${id}_legacy"
  patched_bin="$RAW/${id}_patched"

  # --- build both variants ---
  if ! $CXX $ASAN $QT_CFLAGS -DLEGACY "$HERE/$src" -o "$legacy_bin" $QT_LIBS 2> "$RAW/${id}_legacy_build.log"; then
    echo "BUILD FAIL (legacy) $id — see $RAW/${id}_legacy_build.log"; overall_ok=0; continue
  fi
  if ! $CXX $ASAN $QT_CFLAGS "$HERE/$src" -o "$patched_bin" $QT_LIBS 2> "$RAW/${id}_patched_build.log"; then
    echo "BUILD FAIL (patched) $id — see $RAW/${id}_patched_build.log"; overall_ok=0; continue
  fi

  # --- run both variants ---
  "$legacy_bin"  > "$RAW/${id}_legacy.out"  2>&1;
  "$patched_bin" > "$RAW/${id}_patched.out" 2>&1

  legacy_leak="$(parse_leak_bytes "$RAW/${id}_legacy.out"  "$base")"
  patched_leak="$(parse_leak_bytes "$RAW/${id}_patched.out" "$base")"
  patched_fatal="$(detect_fatal "$RAW/${id}_patched.out")"
  legacy_fatal="$(detect_fatal "$RAW/${id}_legacy.out")"

  fixed=$(( legacy_leak - patched_leak ))

  verdict_ok=1
  [ "$patched_leak" -ne 0 ] && verdict_ok=0
  [ "$patched_fatal" != "none" ] && verdict_ok=0
  [ "$verdict_ok" -eq 1 ] || overall_ok=0

  printf "%-4s %-58.58s %12s %12s %10s\n" "$id" "$title" "$legacy_leak" "$patched_leak" "$patched_fatal"
  echo "| $id | $title | ${legacy_leak} B | ${patched_leak} B | ${fixed} B | ${patched_fatal} |" >> "$REPORT"
done

printf '%.0s-' {1..100}; printf "\n"
echo ""                                              >> "$REPORT"
if [ "$overall_ok" -eq 1 ]; then
  echo "**Verdict: PASS** — every fix eliminates its leak with zero PATCHED leaks and no use-after-free / double-free / SEGV." >> "$REPORT"
  echo "VERDICT: PASS"
else
  echo "**Verdict: FAIL** — see table and raw logs in \`raw/\`." >> "$REPORT"
  echo "VERDICT: FAIL"
fi
echo ""                                              >> "$REPORT"
echo "Raw ASan logs: \`tests/asan-regression/raw/<test>_{legacy,patched}.out\`." >> "$REPORT"

echo "Report written to $REPORT"
exit $(( overall_ok == 1 ? 0 : 1 ))
