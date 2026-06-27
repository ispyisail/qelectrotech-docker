#!/usr/bin/env bash
#
# asan-compare.sh — Compare ASan/LeakSanitizer reports before and after a patch,
# for QElectroTech (QET) pull requests.
#
# Based on the script posted by @scorpio810 on PR #519, hardened so the app is
# shut down with a real window-close (WM_DELETE_WINDOW) instead of SIGTERM.
# This matters: LeakSanitizer only emits its report on a *clean* exit (return
# from main() -> atexit handlers). Qt does not install a SIGTERM handler by
# default, so `kill -TERM` tends to terminate the process before LSan runs and
# you get an empty report for BOTH refs — a meaningless diff.
#
# What it does:
#   1. Builds QET with AddressSanitizer at the BASE commit (e.g. master)
#   2. Runs it against a given .qet project, captures the leak report
#   3. Builds QET with AddressSanitizer at the PATCHED commit (e.g. a PR branch)
#   4. Runs it against the same project, captures the leak report
#   5. Diffs the two reports so you can see exactly what changed
#
# Requirements:
#   - A git checkout of qelectrotech-source-mirror
#   - qmake, make, a C++ toolchain, and the same Qt/dependencies you'd normally
#     use to build QET
#   - Linux (LeakSanitizer's automatic leak detection at exit is not supported
#     on macOS; if you're on macOS, run this inside a Linux container)
#   - For the clean window-close: `wmctrl` (preferred) or `xdotool`. If neither
#     is installed the script falls back to SIGTERM and warns you that the leak
#     report may be empty.
#
# Usage:
#   ./asan-compare.sh -r /path/to/qet-repo -b master -p 519 -f /path/to/project.qet
#   ./asan-compare.sh -r /path/to/qet-repo -b master -p some-branch -f /path/to/project.qet
#
# Options:
#   -r   Path to the local QET git repository (required)
#   -b   Base ref to compare from, e.g. "master" (required)
#   -p   Patched ref to compare to (required). Can be:
#          - a pull request number, e.g. "519" (the script fetches
#            refs/pull/519/head from origin automatically)
#          - any branch name or commit already known to git, e.g. "origin/some-branch"
#   -f   Path to a .qet project file to open during the test (required)
#   -o   Output directory for logs and reports (default: ./asan-compare-results)
#   -j   Parallel build jobs (default: number of CPU cores)
#   -t   Seconds to let the app run before it is closed automatically (default: 15)
#        Increase this if you want to manually exercise StyleEditor, ExportDialog,
#        GenericPanel or ElementScene paths during the run — see note below.
#   -w   Extra seconds to wait for the app to exit cleanly after the close
#        request, before escalating to SIGTERM/SIGKILL (default: 20). Bump this
#        if you need time to dismiss a "save changes?" dialog by hand.
#
# IMPORTANT — about test coverage:
#   Simply opening a project only exercises the diagram-loading code path.
#   It does NOT exercise StyleEditor, ExportDialog, the paste-area in
#   ElementScene, or most of GenericPanel's code paths.
#   This script launches the app and waits -t seconds before closing it,
#   giving you a window to interact with it manually (open the element editor,
#   try Export, copy/paste an element, etc.) if you want full coverage of a
#   given patch. Automating that interaction is out of scope for this script.
#
#   If you make changes during that window, QET may pop a "save changes?" dialog
#   when the close is requested. The script waits -w seconds for the process to
#   exit on its own, so you can dismiss the dialog (choose Discard) by hand; only
#   after that does it escalate. A clean exit is what makes LSan fire, so prefer
#   dismissing the dialog over letting it escalate.
#
# Output:
#   <outdir>/base-report.txt      — full LeakSanitizer output for the base ref
#   <outdir>/patched-report.txt   — full LeakSanitizer output for the patched ref
#   <outdir>/diff.txt             — unified diff between the two reports
#   <outdir>/summary.txt          — short summary (total bytes leaked, before/after)

set -euo pipefail

OUTDIR="./asan-compare-results"
JOBS="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
RUNTIME=15
CLOSE_WAIT=20

usage() {
    grep '^#' "$0" | sed -e 's/^# \{0,1\}//' -e 's/^#$//'
    exit 1
}

while getopts "r:b:p:f:o:j:t:w:h" opt; do
    case "$opt" in
        r) REPO="$OPTARG" ;;
        b) BASE_REF="$OPTARG" ;;
        p) PATCHED_REF="$OPTARG" ;;
        f) PROJECT_FILE="$OPTARG" ;;
        o) OUTDIR="$OPTARG" ;;
        j) JOBS="$OPTARG" ;;
        t) RUNTIME="$OPTARG" ;;
        w) CLOSE_WAIT="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

: "${REPO:?Missing -r <repo path>. Run with -h for usage.}"
: "${BASE_REF:?Missing -b <base ref>. Run with -h for usage.}"
: "${PATCHED_REF:?Missing -p <patched ref>. Run with -h for usage.}"
: "${PROJECT_FILE:?Missing -f <project .qet file>. Run with -h for usage.}"

if [[ ! -d "$REPO/.git" ]]; then
    echo "Error: $REPO does not look like a git repository (no .git directory)." >&2
    exit 1
fi

if [[ ! -f "$PROJECT_FILE" ]]; then
    echo "Error: project file not found: $PROJECT_FILE" >&2
    exit 1
fi

PROJECT_FILE="$(cd "$(dirname "$PROJECT_FILE")" && pwd)/$(basename "$PROJECT_FILE")"
mkdir -p "$OUTDIR"
OUTDIR="$(cd "$OUTDIR" && pwd)"

ASAN_CXXFLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer"
ASAN_LFLAGS="-fsanitize=address"

# How we close the running app. Prefer a proper WM_DELETE_WINDOW close so Qt
# runs its normal shutdown (and therefore LSan runs at exit). Detected once.
CLOSE_TOOL=""
if command -v wmctrl >/dev/null 2>&1; then
    CLOSE_TOOL="wmctrl"
elif command -v xdotool >/dev/null 2>&1; then
    CLOSE_TOOL="xdotool"
fi

log() {
    echo "[asan-compare] $*"
}

# request_window_close <pid>
# Sends a real "close window" event (WM_DELETE_WINDOW) to the QET window so Qt
# performs a normal shutdown. Returns non-zero if no GUI close tool is available.
request_window_close() {
    local pid="$1"
    case "$CLOSE_TOOL" in
        wmctrl)
            # Match the QElectroTech top-level window by title and ask the WM to
            # close it (this delivers WM_DELETE_WINDOW, i.e. the same as the [x]).
            if wmctrl -l 2>/dev/null | grep -qi 'qelectrotech'; then
                wmctrl -c 'QElectroTech' 2>/dev/null || \
                    wmctrl -l 2>/dev/null | grep -i 'qelectrotech' | \
                    awk '{print $1}' | while read -r wid; do wmctrl -i -c "$wid"; done
                return 0
            fi
            return 1
            ;;
        xdotool)
            # --pid is the most reliable match; fall back to class/name search.
            local wid
            wid="$(xdotool search --pid "$pid" 2>/dev/null | head -n1 || true)"
            [[ -z "$wid" ]] && wid="$(xdotool search --class qelectrotech 2>/dev/null | head -n1 || true)"
            [[ -z "$wid" ]] && wid="$(xdotool search --name -i qelectrotech 2>/dev/null | head -n1 || true)"
            if [[ -n "$wid" ]]; then
                xdotool windowclose "$wid" 2>/dev/null
                return 0
            fi
            return 1
            ;;
        *)
            return 1
            ;;
    esac
}

# wait_for_exit <pid> <seconds>
# Polls for the process to disappear, up to <seconds>. Returns 0 if it exited.
wait_for_exit() {
    local pid="$1" secs="$2" waited=0
    while kill -0 "$pid" 2>/dev/null; do
        (( waited >= secs )) && return 1
        sleep 1
        waited=$(( waited + 1 ))
    done
    return 0
}

# shutdown_app <pid>
# Tries, in order: WM close (clean, LSan fires) -> SIGTERM -> SIGKILL.
shutdown_app() {
    local pid="$1"

    if [[ -n "$CLOSE_TOOL" ]]; then
        log "Requesting a clean window-close (via $CLOSE_TOOL) on pid $pid ..."
        if request_window_close "$pid"; then
            if wait_for_exit "$pid" "$CLOSE_WAIT"; then
                log "App exited cleanly — LeakSanitizer report should be present."
                return 0
            fi
            log "App still alive after ${CLOSE_WAIT}s (a save dialog may be open)."
        else
            log "Could not locate the QET window to close it."
        fi
    else
        log "WARNING: neither wmctrl nor xdotool found — cannot do a clean close."
        log "         Falling back to SIGTERM; the leak report may be empty."
    fi

    log "Escalating: sending SIGTERM to pid $pid ..."
    kill -TERM "$pid" 2>/dev/null || true
    if wait_for_exit "$pid" 5; then
        return 0
    fi

    log "Still alive — sending SIGKILL to pid $pid ..."
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

# resolve_ref <ref>
# If <ref> is a plain pull-request number (e.g. "519"), fetch
# refs/pull/<n>/head from origin into a local branch "pr-<n>" and echo
# that branch name. Otherwise, just echo the ref unchanged.
resolve_ref() {
    local ref="$1"
    if [[ "$ref" =~ ^[0-9]+$ ]]; then
        local local_branch="pr-${ref}"
        log "Ref '$ref' looks like a PR number — fetching refs/pull/${ref}/head from origin ..." >&2
        git fetch origin "pull/${ref}/head:${local_branch}" --force --quiet
        echo "$local_branch"
    else
        echo "$ref"
    fi
}

# build_and_run <ref> <report_file>
# Checks out <ref>, builds it with ASan, runs it against $PROJECT_FILE,
# and writes the LeakSanitizer report to <report_file>.
build_and_run() {
    local ref="$1"
    local report_file="$2"

    log "=== Preparing ref: $ref ==="
    pushd "$REPO" >/dev/null

    git fetch --all --quiet || true
    ref="$(resolve_ref "$ref")"
    git checkout --quiet "$ref"
    git clean -fdx --quiet
    git submodule update --init --recursive --quiet 2>/dev/null || true

    local build_dir="build-asan-$(echo "$ref" | tr '/:' '__')"
    mkdir -p "$build_dir"
    pushd "$build_dir" >/dev/null

    log "Running qmake for $ref ..."
    qmake CONFIG+=debug \
        QMAKE_CXXFLAGS+="$ASAN_CXXFLAGS" \
        QMAKE_LFLAGS+="$ASAN_LFLAGS" \
        ../qelectrotech.pro

    log "Building $ref with $JOBS job(s) (this can take a while) ..."
    make -j"$JOBS"

    local binary
    binary="$(find . -maxdepth 1 -type f -executable -iname 'qelectrotech*' | head -n1)"
    if [[ -z "$binary" ]]; then
        echo "Error: could not find the built qelectrotech binary in $build_dir" >&2
        popd >/dev/null
        popd >/dev/null
        return 1
    fi

    log "Running $binary against $PROJECT_FILE for ${RUNTIME}s."
    log "  --> If you want to test StyleEditor / ExportDialog / GenericPanel /"
    log "      ElementScene paths, interact with the app now in its window."
    log "      The app will be asked to close automatically after ${RUNTIME}s."

    # Note: we deliberately do NOT pre-create report_file here. ASan will
    # write its own file at "${report_file%.txt}.<pid>", and pre-creating
    # report_file would make it match that same glob below.
    # detect_leaks=1 is the default on Linux but we set it explicitly for clarity.
    # log_path lets ASan write straight to a file we can collect, even across
    # the graceful-quit signal below.
    ASAN_OPTIONS="detect_leaks=1:log_path=${report_file%.txt}" \
        "./$binary" "$PROJECT_FILE" &
    local app_pid=$!

    sleep "$RUNTIME"

    # Clean window-close (WM_DELETE_WINDOW) so Qt shuts down normally and
    # LeakSanitizer runs at exit; escalates to SIGTERM/SIGKILL only if needed.
    shutdown_app "$app_pid"

    # ASAN_OPTIONS log_path writes to <prefix>.<pid>; collect it back into
    # report_file. The grep -v guard is just a defensive safety net in case
    # report_file already existed from a previous run with the same name.
    local generated
    generated="$(ls "${report_file%.txt}".* 2>/dev/null | grep -v -F -- "$report_file" | head -n1 || true)"
    if [[ -n "$generated" && -f "$generated" && "$generated" != "$report_file" ]]; then
        mv "$generated" "$report_file"
    fi

    if [[ ! -s "$report_file" ]]; then
        echo "(no leak report produced — either no leaks were detected, or the app did not exit cleanly)" > "$report_file"
    fi

    popd >/dev/null
    popd >/dev/null
    log "=== Done with ref: $ref -> $report_file ==="
}

extract_total_bytes() {
    local report_file="$1"
    grep -oE 'AddressSanitizer: [0-9]+ byte\(s\) leaked' "$report_file" 2>/dev/null \
        | grep -oE '[0-9]+' | head -n1 || echo "0"
}

BASE_REPORT="$OUTDIR/base-report.txt"
PATCHED_REPORT="$OUTDIR/patched-report.txt"
DIFF_FILE="$OUTDIR/diff.txt"
SUMMARY_FILE="$OUTDIR/summary.txt"

ORIGINAL_REF="$(cd "$REPO" && git rev-parse --abbrev-ref HEAD)"

if [[ -z "$CLOSE_TOOL" ]]; then
    log "WARNING: no wmctrl/xdotool detected. The app will be stopped with"
    log "         SIGTERM, which usually skips LeakSanitizer's exit-time report."
    log "         Install wmctrl (or xdotool) for a reliable clean close."
fi

build_and_run "$BASE_REF" "$BASE_REPORT"
build_and_run "$PATCHED_REF" "$PATCHED_REPORT"

log "Restoring original branch/ref: $ORIGINAL_REF"
(cd "$REPO" && git checkout --quiet "$ORIGINAL_REF") || true

log "Diffing reports ..."
diff -u "$BASE_REPORT" "$PATCHED_REPORT" > "$DIFF_FILE" || true

BASE_BYTES="$(extract_total_bytes "$BASE_REPORT")"
PATCHED_BYTES="$(extract_total_bytes "$PATCHED_REPORT")"

{
    echo "ASan leak comparison summary"
    echo "============================="
    echo "Base ref:      $BASE_REF"
    echo "Patched ref:   $PATCHED_REF"
    echo "Project file:  $PROJECT_FILE"
    echo "Runtime:       ${RUNTIME}s per run (manual interaction window)"
    echo "Close method:  ${CLOSE_TOOL:-SIGTERM fallback (no wmctrl/xdotool)}"
    echo ""
    echo "Total leaked (base):    ${BASE_BYTES} byte(s)"
    echo "Total leaked (patched): ${PATCHED_BYTES} byte(s)"
    echo ""
    echo "Full reports: $BASE_REPORT / $PATCHED_REPORT"
    echo "Diff:         $DIFF_FILE"
} | tee "$SUMMARY_FILE"

log "All done. See $OUTDIR for full output."
