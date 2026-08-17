#!/bin/bash
# Launch a DeepSeek session, optionally waiting for off-peak pricing.
#
#   scripts/deepseek-run.sh [--wait] <workdir> <prompt-file> [logfile]
#
# DeepSeek charges 50% during off-peak hours. Per its pricing docs:
#   PEAK     01:00-04:00 and 06:00-10:00 UTC
#   OFF-PEAK every other hour  (half price on input, cached input and output)
#
# --wait sleeps until the next off-peak hour instead of running now. Without it
# the script runs immediately and just reports which rate you are paying, so a
# session is never silently delayed when you wanted it now.
#
# Re-check the window if DeepSeek changes pricing: this encodes their published
# hours as of 2026-08-17, not a rule that can be derived.
set -euo pipefail

WAIT=0
if [ "${1:-}" = "--wait" ]; then WAIT=1; shift; fi
WORKDIR="${1:?usage: deepseek-run.sh [--wait] <workdir> <prompt-file> [logfile]}"
PROMPT_FILE="${2:?missing prompt file}"
LOGFILE="${3:-$WORKDIR/deepseek-run.log}"

is_peak() {                       # 0 = peak (expensive), 1 = off-peak
    local h; h=$(date -u +%-H)
    if   [ "$h" -ge 1 ] && [ "$h" -lt 4  ]; then return 0
    elif [ "$h" -ge 6 ] && [ "$h" -lt 10 ]; then return 0
    else return 1; fi
}

seconds_to_offpeak() {
    local h m now target
    h=$(date -u +%-H); m=$(date -u +%-M)
    now=$(( h * 60 + m ))
    if   [ "$h" -ge 1 ] && [ "$h" -lt 4  ]; then target=$(( 4 * 60 ))
    elif [ "$h" -ge 6 ] && [ "$h" -lt 10 ]; then target=$(( 10 * 60 ))
    else echo 0; return; fi
    echo $(( (target - now) * 60 ))
}

if is_peak; then
    if [ "$WAIT" = "1" ]; then
        secs=$(seconds_to_offpeak)
        echo "[deepseek] PEAK now ($(date -u +%H:%M) UTC). Waiting ${secs}s for off-peak." >&2
        sleep "$secs"
    else
        echo "[deepseek] WARNING: running during PEAK hours ($(date -u +%H:%M) UTC) -- full price." >&2
        echo "[deepseek] Use --wait to defer until off-peak (50%)." >&2
    fi
else
    echo "[deepseek] off-peak ($(date -u +%H:%M) UTC) -- 50% rate." >&2
fi

KEY=$(cat ~/.deepseek_key | tr -d '\n')
cd "$WORKDIR"
exec env -u ANTHROPIC_API_KEY \
    ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic" \
    ANTHROPIC_AUTH_TOKEN="$KEY" \
    ANTHROPIC_MODEL="deepseek-v4-pro" \
    claude -p "$(cat "$PROMPT_FILE")" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep" > "$LOGFILE" 2>&1
