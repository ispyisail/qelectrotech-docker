#!/usr/bin/env bash
#
# scripts/gates.sh — run the four quality gates, compare each result against a
# recorded baseline, and say something only when a result changes.
#
# This is plumbing. Every gate already exists; this script only runs them,
# records results, and flags transitions. It never fixes a gate and never
# skips a known-failing one.
#
# Gates:
#   determinism     docker compose run --rm qet-determinism
#   asan-regression docker compose run --rm qet-asan-regression
#   test            docker compose run --rm qet-test
#   cli-sweep       scripts/cli-sweep.sh        (NOT BUILT YET — reported not-built)
#
# Usage:
#   scripts/gates.sh                        run all gates, write a dated report
#   scripts/gates.sh --write-baseline       record current results as the new
#                                           expected state (gate-reports/baseline.json)
#   scripts/gates.sh --only <gate>          run only one gate (repeatable)
#   scripts/gates.sh --help
#
# Reports land in gate-reports/YYYY-MM-DD-HHMMSS.{json,md}. On any transition
# (pass->fail, fail->pass, ...) an ALERT.md is written next to them; on a clean
# run ALERT.md is removed. Notification is local only — no email, no external
# services.
#
# Exit codes:
#   0  no gate got worse than its baseline (or a baseline was written)
#   1  at least one gate got worse than its baseline (a regression)
#   2  usage error, or the runner could not produce a report
#
set -uo pipefail

# Keep docker findable under cron's minimal PATH.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GATE_DIR="$REPO_ROOT/gate-reports"
BASELINE_FILE="$GATE_DIR/baseline.json"
LOG_DIR="$GATE_DIR/logs"
ALERT_FILE="$GATE_DIR/ALERT.md"
TIMEOUT_SECONDS="${GATE_TIMEOUT_SECONDS:-1800}"   # per-gate; a timeout is an `error`

# ---------------------------------------------------------------------------
# Gate registry. A gate with a probe is only run while the probe succeeds;
# otherwise it is recorded as `not-built`. The CLI sweep does not exist yet, so
# it is probed; when scripts/cli-sweep.sh appears the runner picks it up with
# no code change.
# ---------------------------------------------------------------------------
GATE_NAMES=(determinism asan-regression test cli-sweep)

declare -A GATE_CMD=(
  [determinism]="docker compose run -T --rm --name gate-determinism qet-determinism"
  [asan-regression]="docker compose run -T --rm --name gate-asan-regression qet-asan-regression"
  [test]="docker compose run -T --rm --name gate-test qet-test"
  [cli-sweep]="bash scripts/cli-sweep.sh"
)
declare -A GATE_PROBE=(
  [cli-sweep]="[ -e scripts/cli-sweep.sh ]"
)

usage() {
  sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
ONLY=()
WRITE_BASELINE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --write-baseline) WRITE_BASELINE=1 ;;
    --only)
      if [[ $# -lt 2 ]]; then
        printf 'gates.sh: --only requires a gate name\n' >&2
        exit 2
      fi
      shift
      ONLY+=("$1")
      ;;
    --only=*) ONLY+=("${1#--only=}") ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'gates.sh: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

declare -A RUN_THIS=()
if [[ ${#ONLY[@]} -gt 0 ]]; then
  for g in "${ONLY[@]}"; do
    if ! printf '%s\n' "${GATE_NAMES[@]}" | grep -qx "$g"; then
      printf 'gates.sh: unknown gate: %s (known: %s)\n' "$g" "${GATE_NAMES[*]}" >&2
      exit 2
    fi
    RUN_THIS[$g]=1
  done
else
  for g in "${GATE_NAMES[@]}"; do RUN_THIS[$g]=1; done
fi

N_TOTAL=0
for g in "${GATE_NAMES[@]}"; do [[ -n "${RUN_THIS[$g]:-}" ]] && N_TOTAL=$((N_TOTAL + 1)); done
if [[ "$N_TOTAL" -eq 0 ]]; then
  printf 'gates.sh: nothing to run\n' >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
mkdir -p "$GATE_DIR" "$LOG_DIR"

RUN_ID="$(date +%Y-%m-%d-%H%M%S)"
REPORT_JSON="$GATE_DIR/$RUN_ID.json"
n=1
while [[ -e "$REPORT_JSON" ]]; do
  RUN_ID="$(date +%Y-%m-%d-%H%M%S)-$((n++))"
  REPORT_JSON="$GATE_DIR/$RUN_ID.json"
done
REPORT_MD="$GATE_DIR/$RUN_ID.md"
RUN_LOG_DIR="$LOG_DIR/$RUN_ID"
mkdir -p "$RUN_LOG_DIR"

RAWFILE="$(mktemp "${TMPDIR:-/tmp}/gates-raw.XXXXXX")"
trap 'rm -f "$RAWFILE"' EXIT

printf 'gate run %s — %d gate(s), %s s timeout each\n' "$RUN_ID" "$N_TOTAL" "$TIMEOUT_SECONDS"

i=0
for name in "${GATE_NAMES[@]}"; do
  [[ -n "${RUN_THIS[$name]:-}" ]] || continue
  i=$((i + 1))
  cmd="${GATE_CMD[$name]}"
  probe="${GATE_PROBE[$name]:-}"
  logfile="$RUN_LOG_DIR/$name.log"
  start="$SECONDS"

  if [[ -n "$probe" ]] && ! eval "$probe"; then
    status="not-built"
    exit_code=127
    printf 'not-built: %s\n' "$cmd" > "$logfile"
  else
    # Clear any stale container left by a previously crashed run.
    case "$name" in
      determinism|asan-regression|test) docker rm -f "gate-$name" >/dev/null 2>&1 || true ;;
    esac

    # Run in its own session so a hung gate can be killed as a whole tree.
    setsid bash -c "$cmd" >"$logfile" 2>&1 &
    pid=$!
    timed_out=0
    while kill -0 "$pid" 2>/dev/null; do
      if (( SECONDS - start >= TIMEOUT_SECONDS )); then
        timed_out=1
        printf 'TIMED OUT after %s s\n' "$TIMEOUT_SECONDS" >> "$logfile"
        case "$name" in
          determinism|asan-regression|test)
            docker rm -f "gate-$name" >/dev/null 2>&1 || true
            ;;
        esac
        kill -TERM -- -"$pid" 2>/dev/null || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
          kill -0 "$pid" 2>/dev/null || break
          sleep 1
        done
        kill -KILL -- -"$pid" 2>/dev/null || true
        break
      fi
      sleep 1
    done
    wait "$pid" 2>/dev/null
    exit_code=$?
    if [[ "$timed_out" -eq 1 ]]; then
      exit_code=124
    fi
    if [[ "$exit_code" -eq 0 ]]; then
      status="pass"
    elif [[ "$exit_code" -eq 124 ]]; then
      status="error"
    else
      status="fail"
    fi
  fi
  duration=$((SECONDS - start))

  printf '%s|%s|%s|%s|%s|%s\n' "$name" "$cmd" "$exit_code" "$duration" "$status" "$logfile" >> "$RAWFILE"
  printf '  [%d/%d] %-14s %-10s (exit %s, %s s)\n' "$i" "$N_TOTAL" "$name" "$status" "$exit_code" "$duration"
done

# ---------------------------------------------------------------------------
# Render the report, compare against baseline, write ALERT.md, choose exit code
# ---------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  printf 'gates.sh: python3 not found — cannot render report\n' >&2
  exit 2
fi

ONLY_CSV="$(IFS=,; echo "${ONLY[*]}")"

python3 - "$RAWFILE" "$REPORT_JSON" "$REPORT_MD" "$BASELINE_FILE" "$ALERT_FILE" \
  "$RUN_ID" "$WRITE_BASELINE" "$TIMEOUT_SECONDS" "$REPO_ROOT" "$ONLY_CSV" <<'PY'
import json
import os
import re
import sys
import glob
import datetime


def main():
    (rawfile, report_json, report_md, baseline_file, alert_file, run_id,
     write_baseline, timeout_seconds, repo_root, only_csv) = sys.argv[1:11]

    write_baseline = write_baseline == "1"
    timeout_seconds = int(timeout_seconds)
    only = [x for x in only_csv.split(",") if x]

    VALID = ("pass", "fail", "not-built", "error")
    SEVERITY = {"pass": 0, "not-built": 1, "fail": 2, "error": 3}
    REPORT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}(?:-\d+)?\.json$")

    warnings = []
    alert_existed_before = os.path.exists(alert_file)

    # ---- raw per-gate results from the runner --------------------------------
    gates = {}
    with open(rawfile, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            name, cmd, exit_code, duration, status, log_path = line.split("|")
            try:
                with open(log_path, encoding="utf-8", errors="replace") as lf:
                    tail = "\n".join(lf.read().splitlines()[-40:])
            except OSError:
                tail = "(log unreadable: %s)" % log_path
            gates[name] = {
                "name": name,
                "command": cmd,
                "exit_code": int(exit_code),
                "duration_seconds": int(duration),
                "status": status,
                "log_file": log_path,
                "tail": tail,
            }

    # ---- baseline --------------------------------------------------------------
    baseline = {}
    baseline_parse_error = None
    baseline_present = os.path.exists(baseline_file)
    if baseline_present:
        try:
            with open(baseline_file, encoding="utf-8") as fh:
                baseline = json.load(fh)
            if not isinstance(baseline, dict):
                baseline_parse_error = "baseline file is not a JSON object"
                baseline = {}
        except Exception as e:  # noqa: BLE001 - report rendering must not crash
            baseline_parse_error = "cannot read baseline: %s" % e
            baseline = {}

    # ---- previous report, for resolved/persisting detection --------------------
    prev_regressions = set()
    try:
        reports = sorted(
            p for p in glob.glob(os.path.join(repo_root, "gate-reports", "*.json"))
            if REPORT_RE.match(os.path.basename(p)) and run_id not in os.path.basename(p)
        )
        if reports:
            with open(reports[-1], encoding="utf-8") as fh:
                prev = json.load(fh)
            prev_gates = prev.get("gates", {}) if isinstance(prev, dict) else {}
            for gname, gd in prev_gates.items():
                if gd.get("regression"):
                    prev_regressions.add(gname)
    except Exception:  # noqa: BLE001
        pass  # first run, or previous report unreadable

    # ---- transition detection ---------------------------------------------------
    regressions = []
    improvements = []
    new_gates = []
    for name, d in gates.items():
        base = baseline.get(name) if isinstance(baseline, dict) else None
        d["baseline"] = base
        if base is None:
            d["transition"] = None
            d["regression"] = False
            new_gates.append(name)
            continue
        if base not in VALID:
            warnings.append("%s: baseline value %r is not a valid status; no comparison" % (name, base))
            d["transition"] = None
            d["regression"] = False
            continue
        if d["status"] == base:
            d["transition"] = None
            d["regression"] = False
            continue
        d["transition"] = "%s->%s" % (base, d["status"])
        d["regression"] = SEVERITY[d["status"]] > SEVERITY[base]
        if d["regression"]:
            regressions.append(name)
        else:
            improvements.append(name)

    resolved = []
    persisting = []
    for gname in sorted(prev_regressions):
        if gname in gates:
            if gates[gname]["regression"]:
                persisting.append(gname)
            else:
                resolved.append(gname)

    # ---- baseline write / exit-code decision -----------------------------------
    baseline_written = None
    errored = [n for n, d in gates.items() if d["status"] == "error"]
    if write_baseline:
        if errored:
            warnings.append(
                "baseline records error for %s — a hang/infrastructure failure is now the "
                "expected state; a transition back to pass or fail will be alerted" % ", ".join(errored))
        for n, d in gates.items():
            baseline[n] = d["status"]
        with open(baseline_file, "w", encoding="utf-8") as fh:
            json.dump(baseline, fh, indent=2, sort_keys=True)
            fh.write("\n")
        baseline_written = True
        baseline_present = True
        exit_code = 0
    else:
        exit_code = 1 if regressions else 0

    # ---- report files -----------------------------------------------------------
    timestamp_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "command_line": "scripts/gates.sh" + ("".join(" --only " + x for x in only)),
        "write_baseline": write_baseline,
        "baseline_written": baseline_written,
        "baseline_file": "gate-reports/baseline.json",
        "baseline_present": baseline_present,
        "baseline_parse_error": baseline_parse_error,
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "gates": gates,
        "regressions": regressions,
        "improvements": improvements,
        "resolved": resolved,
        "persisting": persisting,
        "warnings": warnings,
    }
    with open(report_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    def fmt_duration(s):
        if s < 60:
            return "%ss" % s
        return "%dm%02ss" % (s // 60, s % 60)

    md = []
    md.append("# Gate run %s" % run_id)
    md.append("")
    md.append("- When: %s" % timestamp_utc)
    md.append("- Command: `%s`" % report["command_line"])
    md.append("- Baseline: present" if baseline_present else "- Baseline: none yet")
    md.append("- Timeout per gate: %ss" % timeout_seconds)
    md.append("- Write-baseline mode: %s" % ("yes" if write_baseline else "no"))
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append("| Gate | Status | Baseline | Transition | Time | Exit |")
    md.append("|---|---|---|---|---|---|")
    for name, d in gates.items():
        md.append("| %s | %s | %s | %s | %s | %s |" % (
            name,
            d["status"],
            d.get("baseline") or "—",
            d.get("transition") or "—",
            fmt_duration(d["duration_seconds"]),
            d["exit_code"],
        ))
    md.append("")
    if new_gates:
        md.append("## New gates (no baseline entry yet)")
        md.append("")
        for n in new_gates:
            md.append("- %s (status %s) — run `--write-baseline` to record" % (n, gates[n]["status"]))
        md.append("")
    if regressions:
        md.append("## Regressions")
        md.append("")
        for n in regressions:
            d = gates[n]
            md.append("- **%s**: %s (command: `%s`)" % (n, d["transition"], d["command"]))
        md.append("")
    if improvements:
        md.append("## Improvements")
        md.append("")
        for n in improvements:
            md.append("- %s: %s" % (n, gates[n]["transition"]))
        md.append("")
    if resolved:
        md.append("## Resolved")
        md.append("")
        for n in resolved:
            md.append("- %s: regression from the previous run is gone" % n)
        md.append("")
    if persisting:
        md.append("## Still regressing")
        md.append("")
        for n in persisting:
            md.append("- %s" % n)
        md.append("")
    if warnings:
        md.append("## Warnings")
        md.append("")
        for w in warnings:
            md.append("- %s" % w)
        md.append("")
    md.append("## Output tails")
    md.append("")
    for name, d in gates.items():
        md.append("### %s" % name)
        md.append("")
        md.append("```text")
        md.append(d["tail"])
        md.append("```")
        md.append("")

    with open(report_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # ---- ALERT.md ---------------------------------------------------------------
    if not write_baseline:
        transitions_present = bool(regressions or improvements)
        if transitions_present:
            with open(alert_file, "w", encoding="utf-8") as fh:
                fh.write("# Gate transition alert — %s\n\n" % timestamp_utc)
                fh.write("Run `scripts/gates.sh` detected a change versus "
                         "`gate-reports/baseline.json`.\n\n")
                if regressions:
                    fh.write("## Regressions (got worse)\n\n")
                    for n in regressions:
                        d = gates[n]
                        fh.write("- **%s**: %s\n" % (n, d["transition"]))
                    fh.write("\n")
                if improvements:
                    fh.write("## Improvements (got better)\n\n")
                    for n in improvements:
                        fh.write("- %s: %s\n" % (n, gates[n]["transition"]))
                    fh.write("\n")
                fh.write("See %s for details.\n" % os.path.basename(report_md))
        elif os.path.exists(alert_file):
            os.remove(alert_file)

    # ---- stdout summary ----------------------------------------------------------
    print()
    print("Gate run %s" % run_id)
    if baseline_parse_error:
        print("  baseline: PRESENT BUT UNREADABLE — %s" % baseline_parse_error)
    elif baseline_present:
        print("  baseline: %s (present)" % os.path.basename(baseline_file))
    else:
        print("  baseline: none yet — run `scripts/gates.sh --write-baseline` to record")
    print()
    print("  %-16s %-10s %-10s %-8s %-8s %s" % ("GATE", "STATUS", "BASELINE", "DELTA", "TIME", "EXIT"))
    for name, d in gates.items():
        print("  %-16s %-10s %-10s %-8s %-8s %s" % (
            name, d["status"], d.get("baseline") or "—",
            d.get("transition") or "—", fmt_duration(d["duration_seconds"]), d["exit_code"]))
    print()
    if new_gates:
        for n in new_gates:
            print("  note: %s has no baseline entry yet (status %s)" % (n, gates[n]["status"]))
    if regressions:
        print("  * REGRESSIONS (got worse than baseline):")
        for n in regressions:
            print("    - %s: %s" % (n, gates[n]["transition"]))
    if improvements:
        print("  + IMPROVEMENTS (got better than baseline):")
        for n in improvements:
            print("    - %s: %s" % (n, gates[n]["transition"]))
    if resolved:
        print("  ~ RESOLVED (regression from previous run now matches baseline):")
        for n in resolved:
            print("    - %s" % n)
    if persisting:
        print("  x STILL REGRESSING (same as previous run):")
        for n in persisting:
            print("    - %s" % n)
    if not (regressions or improvements or resolved or persisting or new_gates):
        print("  no transitions — all gates match baseline.")
    if write_baseline:
        print("  baseline updated: %s" % os.path.basename(baseline_file))
        if errored:
            print("  NOTE: %s recorded as error in the baseline (see warning below)" % ", ".join(errored))
    elif regressions or improvements:
        print("  ALERT.md written: %s" % os.path.basename(alert_file))
    elif alert_existed_before:
        print("  ALERT.md cleared — no transitions this run")
    if warnings:
        print()
        for w in warnings:
            print("  warning: %s" % w)
    print()
    print("  report: %s" % os.path.relpath(report_md, repo_root))
    print("  exit: %s" % exit_code)
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - a rendering bug must not look like a regression
        print("gates.sh: internal error rendering report: %s" % e, file=sys.stderr)
        sys.exit(2)
PY
runner_rc=$?
exit "$runner_rc"
