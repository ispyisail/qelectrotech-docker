#!/usr/bin/env bash
#
# cli-sweep.sh -- exercise every headless CLI verb against every project in a
# corpus (plus --check-elements over the element collection), recording enough
# per-run telemetry to spot a hang or a resource leak at a glance.
#
# Restored after the original was lost (W1 brief §2d). It was worth more than
# its size: ~15 min runtime, 185 runs, two real bugs (the modal-dialog hang on
# version-incompatible projects, and an element-collection validation failure).
#
# Usage:
#   scripts/cli-sweep.sh --binary /path/to/qelectrotech
#   scripts/cli-sweep.sh --binary /path/to/qelectrotech --corpus /path/one.qet
#   scripts/cli-sweep.sh --binary /path/to/qelectrotech --elements /path/10_electric
#   scripts/cli-sweep.sh --binary /path/to/qelectrotech --timeout 120 --out /tmp/sweep
#
# Exit code: non-zero if any run crashed or timed out (or exited non-zero for a
# reason other than the known --export-wires / --export-cables "Nothing to
# export" exit 1 -- see cli_export.cpp exportCsv(), W1 brief trap 3).
set -uo pipefail

# ---------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------
BINARY=""
CORPUS="/home/user/qet-fix/examples"
ELEMENTS="/home/user/qelectrotech-docker/elements-10-electric/10_electric"
TIMEOUT=120
OUT_DIR="${CLI_SWEEP_OUT:-$PWD/cli-sweep-logs}"

# All project-loading verbs, in cli_export.cpp exportFlags() order. The 12th
# flag, --check-elements, is not a project verb (it takes an element file or
# directory) and is run once at the end.
PROJECT_VERBS=( --export-pdf --export-png --export-svg --export-cables
                --export-wires --export-bom --export-nets --export-links
                --info --resave --set-titleblock )

RUNS_FILE=""   # set in main
TMP_ROOT=""    # set in main

_usage() {
  cat >&2 <<'EOF'
usage: cli-sweep.sh --binary PATH [options]

  --binary PATH     qelectrotech binary to exercise (required)
  --corpus PATH     dir of .qet projects, or a single .qet file
                    (default /home/user/qet-fix/examples)
  --elements PATH   element collection dir for --check-elements
                    (default .../elements-10-electric/10_electric)
  --timeout SEC     per-run wall-clock timeout (default 120)
  --out DIR         where runs.jsonl and the scratch dir land
                    (default ./cli-sweep-logs)
EOF
}

_die() { printf 'cli-sweep: error: %s\n' "$*" >&2; exit 2; }

# ---------------------------------------------------------------------
# Per-run JSON emission. One JSON object per run, one line each. The two
# log tails can contain arbitrary text (newlines, quotes, non-ASCII), so
# serialization is delegated to python3 rather than hand-rolled in bash.
# ---------------------------------------------------------------------
_emit_json() {
  python3 - "$@" <<'PY'
import json, sys
(label, verb, rc, wall, timed_out, peak_kb, max_fds, failed, fail_reason,
 stdout_tail, stderr_tail) = sys.argv[1:]
print(json.dumps({
    "case": label,
    "verb": verb,
    "exit_code": int(rc) if rc != "" else None,
    "wall_seconds": float(wall),
    "timed_out": timed_out == "1",
    "peak_rss_kb": int(peak_kb),
    "fd_count": int(max_fds),
    "failed": failed == "1",
    "fail_reason": fail_reason or None,
    "stdout_tail": stdout_tail,
    "stderr_tail": stderr_tail,
}, ensure_ascii=False))
PY
}

# Known-benign nonzero exit (W1 brief trap 3): --export-wires / --export-cables
# exit 1 with "Nothing to export (empty list)." when the project has no
# wires/cables -- indistinguishable from a real failure by exit code alone.
_is_benign() {
  local verb="$1" rc="$2" stderr_tail="$3"
  [[ "$rc" == "1" ]] || return 1
  case "$verb" in
    --export-wires|--export-cables) ;;
    *) return 1 ;;
  esac
  [[ "$stderr_tail" == *"Nothing to export"* ]]
}

# Run one case. `label` is for the JSON/summary; the remaining argv is what
# follows the binary. Returns 0 on a clean run, 1 on anything that should make
# the sweep exit non-zero (timeout, crash, or an unexpected non-zero exit).
run_case() {
  local label="$1"; shift
  local -a argv=("$@")
  local verb="${argv[0]:-}"

  # Fresh, fully isolated sandbox per run (mirrors simulator/env.py):
  # own HOME + XDG_* so SingleApplication cannot forward to a live instance,
  # offscreen platform so no X11 is needed, and no DISPLAY/WAYLAND to reach
  # across to a real session.
  local sandbox; sandbox="$(mktemp -d "${TMP_ROOT}/sb.XXXXXX")"
  mkdir -p "$sandbox/home" "$sandbox/config" "$sandbox/data" "$sandbox/work"

  local sout="$sandbox/stdout.log" serr="$sandbox/stderr.log"
  local start_ns; start_ns="$(date +%s%N)"

  HOME="$sandbox/home" \
  XDG_CONFIG_HOME="$sandbox/config" \
  XDG_DATA_HOME="$sandbox/data" \
  QT_QPA_PLATFORM=offscreen \
  DISPLAY= WAYLAND_DISPLAY= \
  "$BINARY" "${argv[@]}" >"$sout" 2>"$serr" &
  local pid=$!

  # Poll /proc for peak RSS (VmHWM) and fd count while enforcing the timeout.
  local timed_out=0 peak_kb=0 max_fds=0
  local deadline_ns=$(( start_ns + TIMEOUT * 1000000000 ))
  while kill -0 "$pid" 2>/dev/null; do
    local now_ns; now_ns="$(date +%s%N)"
    if (( now_ns >= deadline_ns )); then
      timed_out=1
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
    if [[ -r "/proc/$pid/status" ]]; then
      local vmhwm nfd
      vmhwm="$(awk '/^VmHWM:/{print $2}' "/proc/$pid/status" 2>/dev/null)"
      nfd="$(ls -1 "/proc/$pid/fd" 2>/dev/null | wc -l)"
      [[ "${vmhwm:-0}" =~ ^[0-9]+$ ]] || vmhwm=0
      [[ "${nfd:-0}" =~ ^[0-9]+$ ]] || nfd=0
      (( vmhwm > peak_kb )) && peak_kb=$vmhwm
      (( nfd > max_fds )) && max_fds=$nfd
    fi
    sleep 0.1
  done

  wait "$pid" 2>/dev/null
  local rc=$?
  (( timed_out )) && rc=""   # we killed it; there is no self-reported exit code

  local end_ns; end_ns="$(date +%s%N)"
  local wall_s; wall_s="$(awk -v a="$start_ns" -v b="$end_ns" \
      'BEGIN{printf "%.3f", (b-a)/1000000000}')"

  # Tail both logs. W1 brief trap 4: the last line in a redirected log is the
  # last *flushed*, not the last processed -- so these are diagnostics, never
  # the basis for classifying a run. NULs stripped so argv-bound JSON is safe.
  local stdout_tail stderr_tail
  stdout_tail="$(tail -c 4000 "$sout" 2>/dev/null | tr -d '\000' || true)"
  stderr_tail="$(tail -c 4000 "$serr" 2>/dev/null | tr -d '\000' || true)"

  local failed=0 fail_reason=""
  if (( timed_out )); then
    failed=1; fail_reason="timeout"
  elif [[ -n "$rc" ]] && (( rc >= 128 )); then
    failed=1; fail_reason="crash (signal, exit $rc)"
  elif [[ -n "$rc" ]] && (( rc != 0 )); then
    if _is_benign "$verb" "$rc" "$stderr_tail"; then
      : # known empty-result exit 1 -- not a failure
    else
      failed=1; fail_reason="nonzero exit $rc"
    fi
  fi

  _emit_json "$label" "$verb" "$rc" "$wall_s" "$timed_out" "$peak_kb" "$max_fds" \
             "$failed" "$fail_reason" "$stdout_tail" "$stderr_tail" >>"$RUNS_FILE"

  local status="OK"; (( failed )) && status="FAIL"
  printf '  [%s] %-46s rc=%-4s wall=%ss rss=%sKB fd=%s%s\n' \
    "$status" "$label" "${rc:-KILL}" "$wall_s" "$peak_kb" "$max_fds" \
    "${fail_reason:+  ($fail_reason)}"

  rm -rf "$sandbox"
  return "$failed"
}

# ---------------------------------------------------------------------
# Summary: read runs.jsonl back and print a table + the failure list.
# ---------------------------------------------------------------------
_print_summary() {
  python3 - "$RUNS_FILE" "$BINARY" "$CORPUS" "$TIMEOUT" <<'PY'
import json, sys
runs_file, binary, corpus, timeout = sys.argv[1:]
runs = [json.loads(l) for l in open(runs_file) if l.strip()]
fails = [r for r in runs if r["failed"]]
timeouts = [r for r in fails if r["timed_out"]]
crashes = [r for r in fails if (r["fail_reason"] or "").startswith("crash")]
nonzero = [r for r in fails if (r["fail_reason"] or "").startswith("nonzero")]

print("=" * 78)
print("cli-sweep summary")
print(f"  binary : {binary}")
print(f"  corpus : {corpus}")
print(f"  timeout: {timeout}s")
print(f"  runs   : {len(runs)}   failed: {len(fails)}"
      f"   (timeouts {len(timeouts)}, crashes {len(crashes)},"
      f" other-nonzero {len(nonzero)})")
if fails:
    print("-" * 78)
    print("failures:")
    for r in fails:
        print(f"  [{r['fail_reason']}] {r['case']}"
              f"  exit={r['exit_code']} wall={r['wall_seconds']}s"
              f" rss={r['peak_rss_kb']}KB fd={r['fd_count']}")
        for tag in ("stderr_tail",):
            if r[tag].strip():
                print(f"      {tag}: {r[tag].strip()[-400:]}")
print("=" * 78)
PY
}

# ---------------------------------------------------------------------
main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --binary)   BINARY="${2:-}"; shift 2 ;;
      --corpus)   CORPUS="${2:-}"; shift 2 ;;
      --elements) ELEMENTS="${2:-}"; shift 2 ;;
      --timeout)  TIMEOUT="${2:-}"; shift 2 ;;
      --out)      OUT_DIR="${2:-}"; shift 2 ;;
      -h|--help)  _usage; exit 0 ;;
      *)          _die "unknown argument: $1"; ;;
    esac
  done

  [[ -n "$BINARY" ]] || _die "--binary is required (see --help)"
  [[ -x "$BINARY" ]] || _die "binary not executable: $BINARY"
  [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || _die "--timeout must be a positive integer seconds"
  command -v python3 >/dev/null || _die "python3 not found on PATH"

  # W1 brief trap 1: a live qelectrotech instance would silently forward every
  # launch to itself. We sandbox each run against that, but a *host-network*
  # container (qet-scenarios/qet-reportlink/qet-megatest) can still steal
  # native launches at the SingleApplication level -- surface it before we
  # spend 15 minutes collecting wrong answers.
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qE 'qet-(scenarios|reportlink|megatest)'; then
    _die "a host-network QET container is running -- stop it first (docker ps)"
  fi
  if pgrep -x "$(basename "$BINARY")" >/dev/null 2>&1; then
    _die "a process named $(basename "$BINARY") is already running -- stop it first"
  fi

  mkdir -p "$OUT_DIR"
  RUNS_FILE="$OUT_DIR/runs.jsonl"
  : > "$RUNS_FILE"
  TMP_ROOT="$(mktemp -d "$OUT_DIR/.scratch.XXXXXX")"
  trap 'rm -rf "$TMP_ROOT"' EXIT

  shopt -s nullglob
  local -a projects=()
  if [[ -f "$CORPUS" ]]; then
    projects=( "$CORPUS" )
  elif [[ -d "$CORPUS" ]]; then
    mapfile -t projects < <(printf '%s\n' "$CORPUS"/*.qet | sort)
  else
    _die "corpus not found: $CORPUS"
  fi
  (( ${#projects[@]} > 0 )) || _die "no .qet files under $CORPUS"

  printf 'cli-sweep: binary=%s\ncli-sweep: corpus=%s (%d project(s))\n' \
    "$BINARY" "$CORPUS" "${#projects[@]}"
  printf 'cli-sweep: %d project-loading verb(s) + --check-elements, timeout %ss\n\n' \
    "${#PROJECT_VERBS[@]}" "$TIMEOUT"

  local failed_total=0 run_id=0
  local project stem verb outdir label s

  for project in "${projects[@]}"; do
    stem="$(basename "$project" .qet)"
    for verb in "${PROJECT_VERBS[@]}"; do
      outdir="$TMP_ROOT/out/$run_id"
      mkdir -p "$outdir"
      label="$stem $verb"
      case "$verb" in
        --export-pdf)     run_case "$label" "$verb" "$project" "$outdir/out.pdf" ;;
        --export-png)     run_case "$label" "$verb" "$project" "$outdir/png" ;;
        --export-svg)     run_case "$label" "$verb" "$project" "$outdir/svg" ;;
        --export-cables)  run_case "$label" "$verb" "$project" "$outdir/out.csv" ;;
        --export-wires)   run_case "$label" "$verb" "$project" "$outdir/out.csv" ;;
        --export-bom)     run_case "$label" "$verb" "$project" "$outdir/out.csv" ;;
        --export-nets)    run_case "$label" "$verb" "$project" "$outdir/out.json" ;;
        --export-links)   run_case "$label" "$verb" "$project" "$outdir/out.csv" ;;
        --info)           run_case "$label" "$verb" "$project" "$outdir/out.json" ;;
        --resave)         run_case "$label" "$verb" "$project" "$outdir/out.qet" ;;
        --set-titleblock) run_case "$label" "$verb" "$project" "$outdir/out.qet" "revision=CLI-SWEEP" ;;
      esac
      s=$?
      run_id=$((run_id + 1))
      (( s )) && failed_total=$((failed_total + 1))
    done
  done

  # --check-elements takes an element file/directory, NOT a project.
  outdir="$TMP_ROOT/out/check-elements"
  mkdir -p "$outdir"
  run_case "check-elements $(basename "$ELEMENTS")" "--check-elements" "$ELEMENTS"
  s=$?
  (( s )) && failed_total=$((failed_total + 1))

  printf '\n'
  _print_summary
  printf 'cli-sweep: %d failed run(s) -> exit %d\n' "$failed_total" "$(( failed_total > 0 ? 1 : 0 ))"
  return $(( failed_total > 0 ? 1 : 0 ))
}

main "$@"
