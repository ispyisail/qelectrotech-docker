#!/usr/bin/env bash
#
# guiauto.sh — reliable X11 GUI automation helpers for driving Qt apps
#              (QElectroTech) under this xrdp/xorgxrdp session.
#
# WHY THIS EXISTS
# ===============
# Driving QET with bare xdotool in this environment fails in THREE silent,
# non-obvious ways. All were diagnosed empirically (see DIAGNOSIS below);
# none produces an error message — actions just don't happen, which reads
# like "xdotool is flaky" and burns a lot of time.
#
#   1. EVERY MOUSE CLICK IS DELIVERED TWICE.
#      Qt5's xcb plugin under this xorgxrdp X server receives both XInput2
#      and core X11 pointer events for one physical action, so a single
#      `xdotool click 1` arrives as two press/release pairs in the same
#      millisecond. Consequences: a menu opens then instantly closes; a
#      checkbox toggles twice and looks inert; a button fires twice.
#      Keyboard input is NOT affected — which is why `xdotool key ctrl+n`
#      always worked while clicks appeared to do nothing.
#      FIX: launch the app with QT_XCB_NO_XI2=1 (see qet_launch below).
#      Measured: 3 clicks -> 6 presses (default) vs 3 presses (with the fix).
#
#   2. `xdotool search --name` RETURNS THE WRONG WINDOWS.
#      Name matching is a substring match across ALL clients, so searching
#      "QElectroTech" also returns:
#        - unmapped 1x1 / 3x3 Qt-internal utility windows (activating one
#          gives "XGetWindowProperty[_NET_WM_DESKTOP] failed (code=1)"), and
#        - any *browser tab* whose page title contains the word.
#      Clicks then land in Chrome instead of the app, invisibly.
#      FIX: always select by PID, and require the window to be mapped
#      (IsViewable) and above a minimum size. See win_main.
#
#   3. `xdotool getwindowgeometry` REPORTS THE WRONG ORIGIN.
#      Under xfwm4 (a reparenting WM) it returns the client origin with the
#      frame offset applied twice — measured (+5,+29) here. Window-relative
#      clicks computed from it land ~30px low, which still lands *inside* the
#      window (so nothing looks broken) but misses the menu bar, toolbar
#      buttons and dialog buttons you were aiming at.
#      FIX: use win_geom(), which reads xwininfo's "Absolute upper-left".
#      Verified by cropping a screenshot at both candidate origins and
#      checking which one starts exactly at the menu bar.
#
# DIAGNOSIS SUMMARY (2026-08-15, xrdp session, X.Org 21.1.22, xfwm4, Qt 5.15.3)
#   XTEST ext ......... present
#   input devices ..... 1 XTEST pointer + 1 xrdpMouse (no duplicate devices)
#   click doubling .... reproduced with a minimal Qt widget, both via XTEST
#                       and via XSendEvent; eliminated by QT_XCB_NO_XI2=1
#   keyboard doubling . none
#   geometry offset ... xdotool 1933,67 vs xwininfo 1928,38 for the same window
#
# VALIDATION (all previously-failing steps, now passing)
#   - dismiss a modal error dialog by clicking its OK button
#   - Ctrl+N new project
#   - open the "Projet" menu and have it STAY open (the canonical symptom of
#     the double-click bug: the duplicate click closed it instantly)
#   - click a menu item and get its dialog
#   - place the app window on the monitor the CLI terminal is not on
#
# USAGE
#   source /home/user/qelectrotech-docker/scripts/guiauto.sh
#   qet_launch /path/to/qelectrotech --config-dir ... # sets GUI_PID
#   W=$(win_main "$GUI_PID")
#   win_activate "$W"
#   click_at 400 300           # absolute screen coords, XTEST
#   click_in "$W" 120 80       # window-relative -> absolute, XTEST
#   type_keys ctrl+n
#   shot /tmp/x.png            # full screen
#   shot_win "$W" /tmp/w.png   # just that window
#   gui_cleanup                # kill GUI_PID
#
set -uo pipefail

: "${DISPLAY:=:10.0}"
export DISPLAY

GUI_PID=""

# --- launching -------------------------------------------------------------

# qet_launch <binary> [args...]
# Launches detached, with the XI2 workaround, and exports GUI_PID.
#
# NOTE on PID capture: do NOT wrap in `setsid` here. setsid forks and exits,
# so $! would be the (already dead) wrapper rather than the app, and every
# later `xdotool search --pid` would find nothing. We background directly and
# disown; if the shell still hands back a PID that isn't the running binary
# (job-control quirks), fall back to resolving it by binary path.
qet_launch() {
    local bin="$1"; shift
    env QT_XCB_NO_XI2=1 "$bin" "$@" \
        > "${GUI_LOG:-/tmp/guiauto-app.log}" 2>&1 < /dev/null &
    GUI_PID=$!
    disown 2>/dev/null || true
    sleep 2
    if ! kill -0 "$GUI_PID" 2>/dev/null; then
        local real; real=$(pgrep -f "^${bin}" | head -1)
        [ -n "$real" ] && GUI_PID="$real"
    fi
    export GUI_PID
    echo "launched pid=$GUI_PID (QT_XCB_NO_XI2=1)" >&2
}

gui_cleanup() {
    [ -n "$GUI_PID" ] && kill "$GUI_PID" 2>/dev/null
    return 0
}

# --- geometry --------------------------------------------------------------
#
# IMPORTANT: do not use `xdotool getwindowgeometry` for coordinate math.
# Under xfwm4 (reparenting WM) it returns the client origin with the frame
# offset added a second time — measured here as (+5,+29) off, which is enough
# to miss menu items and toolbar buttons entirely while still landing
# somewhere inside the window, so clicks appear to "do nothing".
# xwininfo's "Absolute upper-left" is the true client-area origin; verified
# by cropping a screenshot at both origins and checking which one starts at
# the menu bar.
#
# win_geom <win> — echoes "X Y W H" (absolute, client area)
win_geom() {
    local w="$1"
    xwininfo -id "$w" 2>/dev/null | awk '
        /Absolute upper-left X/ {x=$NF}
        /Absolute upper-left Y/ {y=$NF}
        /^  Width:/  {wd=$NF}
        /^  Height:/ {ht=$NF}
        END { if (wd != "") print x, y, wd, ht }'
}

# --- window selection ------------------------------------------------------

# win_list <pid> — all mapped windows belonging to pid, "id WxH+X+Y name"
win_list() {
    local pid="$1" id
    for id in $(xdotool search --pid "$pid" 2>/dev/null); do
        xwininfo -id "$id" 2>/dev/null | grep -q "IsViewable" || continue
        local X Y WIDTH HEIGHT
        read -r X Y WIDTH HEIGHT < <(win_geom "$id") || continue
        echo "$id ${WIDTH}x${HEIGHT}+${X}+${Y} $(xdotool getwindowname "$id" 2>/dev/null)"
    done
}

# win_main <pid> [min_w] [min_h] — largest mapped window for pid (the real UI).
# Filters out Qt's unmapped 1x1/3x3 helper windows by area.
win_main() {
    local pid="$1" min_w="${2:-200}" min_h="${3:-200}"
    local best="" best_area=0 id
    for id in $(xdotool search --pid "$pid" 2>/dev/null); do
        xwininfo -id "$id" 2>/dev/null | grep -q "IsViewable" || continue
        local X Y WIDTH HEIGHT
        read -r X Y WIDTH HEIGHT < <(win_geom "$id") || continue
        [ "$WIDTH" -lt "$min_w" ] && continue
        [ "$HEIGHT" -lt "$min_h" ] && continue
        local area=$(( WIDTH * HEIGHT ))
        if [ "$area" -gt "$best_area" ]; then best_area=$area; best=$id; fi
    done
    [ -n "$best" ] && echo "$best"
}

# win_wait <pid> <timeout_s> — block until a usable main window exists; echoes id
win_wait() {
    local pid="$1" timeout="${2:-20}" waited=0 w=""
    while [ "$waited" -lt "$timeout" ]; do
        w=$(win_main "$pid")
        if [ -n "$w" ]; then echo "$w"; return 0; fi
        sleep 1; waited=$((waited+1))
    done
    echo "win_wait: no window for pid $pid after ${timeout}s" >&2
    return 1
}

# win_by_name <pid> <substring> — a specific dialog/window of this pid only
win_by_name() {
    local pid="$1" want="$2" id
    for id in $(xdotool search --pid "$pid" 2>/dev/null); do
        xwininfo -id "$id" 2>/dev/null | grep -q "IsViewable" || continue
        local n; n=$(xdotool getwindowname "$id" 2>/dev/null)
        case "$n" in *"$want"*) echo "$id"; return 0;; esac
    done
    return 1
}

# --- monitor placement -----------------------------------------------------
#
# On this 2-monitor xrdp session the Claude CLI terminal lives on one monitor.
# Test windows must go on the OTHER one, so the human can watch the automation
# without it being hidden behind (or fighting for stacking with) the terminal.

# mon_list — "X Y W H" per monitor, one per line
mon_list() {
    xrandr --listmonitors 2>/dev/null | tail -n +2 | while read -r _ _ geo _; do
        # geo looks like 1920/508x1080/286+0+0
        echo "$geo" | sed -E 's#([0-9]+)/[0-9]+x([0-9]+)/[0-9]+\+([0-9]+)\+([0-9]+)#\3 \4 \1 \2#'
    done
}

# mon_of_window <win> — index of the monitor containing that window's centre
mon_of_window() {
    local w="$1"
    local X Y WIDTH HEIGHT
    read -r X Y WIDTH HEIGHT < <(win_geom "$w") || return 1
    local cx=$(( X + WIDTH/2 )) cy=$(( Y + HEIGHT/2 )) i=0
    while read -r mx my mw mh; do
        if [ "$cx" -ge "$mx" ] && [ "$cx" -lt $(( mx+mw )) ] \
        && [ "$cy" -ge "$my" ] && [ "$cy" -lt $(( my+mh )) ]; then
            echo "$i"; return 0
        fi
        i=$((i+1))
    done < <(mon_list)
    echo 0
}

# term_monitor — index of the monitor showing the Claude CLI terminal
term_monitor() {
    local id
    for id in $(xdotool search --name "claude" 2>/dev/null); do
        xwininfo -id "$id" 2>/dev/null | grep -q IsViewable || continue
        mon_of_window "$id"; return 0
    done
    echo 0   # assume terminal is on monitor 0 if not found
}

# win_unmaximize <win>
# xfwm4 silently ignores windowmove/windowsize on a maximized window, so any
# placement must un-maximize first. xdotool 3.2016 has no `windowstate`, and
# wmctrl isn't installed here, so we send the EWMH _NET_WM_STATE message with
# a small helper built alongside this script.
win_unmaximize() {
    local w="$1"
    local helper; helper="$(dirname "${BASH_SOURCE[0]}")/helpers/wmstate"
    [ -x "$helper" ] && "$helper" "$w" unmaximize && sleep 0.5
    return 0
}

# win_place_away <win> [margin] — move/resize win to fill the monitor the
# Claude terminal is NOT on. No-op (centres on monitor 0) if only one monitor.
win_place_away() {
    local w="$1" margin="${2:-0}"
    win_unmaximize "$w"
    local nmon; nmon=$(mon_list | wc -l)
    local target=0
    if [ "$nmon" -gt 1 ]; then
        local tm; tm=$(term_monitor)
        target=$(( tm == 0 ? 1 : 0 ))
    fi
    local mx my mw mh
    read -r mx my mw mh < <(mon_list | sed -n "$((target+1))p")
    # leave room for the WM titlebar/panel
    local x=$(( mx + margin )) y=$(( my + margin + 30 ))
    xdotool windowmove "$w" "$x" "$y"
    sleep 0.4
    # xfwm4 re-parents and offsets by the frame size, so the window can end up
    # a few px past where we asked. Measure where it actually landed and size
    # it to the space that is genuinely left on this monitor.
    local X Y WIDTH HEIGHT
    read -r X Y WIDTH HEIGHT < <(win_geom "$w")
    local ww=$(( mx + mw - X - margin )) hh=$(( my + mh - Y - margin ))
    [ "$ww" -lt 400 ] && ww=400
    [ "$hh" -lt 300 ] && hh=300
    xdotool windowsize "$w" "$ww" "$hh"
    sleep 0.6
    echo "placed window $w on monitor $target (${X},${Y} ${ww}x${hh})" >&2
}

# --- interaction (always XTEST: real events, honoured by Qt grabs/menus) ----

win_activate() {
    local w="$1"
    xdotool windowraise "$w" 2>/dev/null
    xdotool windowfocus "$w" 2>/dev/null
    xdotool windowactivate "$w" 2>/dev/null   # may warn on odd windows; harmless
    sleep 0.4
    return 0
}

# click_at <abs_x> <abs_y> [button]
click_at() {
    local x="$1" y="$2" btn="${3:-1}"
    xdotool mousemove "$x" "$y"
    sleep 0.25
    xdotool click "$btn"
    sleep 0.45
}

# click_in <win> <rel_x> <rel_y> [button] — window-relative click
click_in() {
    local w="$1" rx="$2" ry="$3" btn="${4:-1}"
    local X Y WIDTH HEIGHT
    read -r X Y WIDTH HEIGHT < <(win_geom "$w") || return 1
    click_at $(( X + rx )) $(( Y + ry )) "$btn"
}

# drag_in <win> <x1> <y1> <x2> <y2> — press, move in steps, release.
# Stepped movement matters: Qt drag-and-drop needs intermediate motion
# events to pass its start-drag distance threshold.
drag_in() {
    local w="$1" x1="$2" y1="$3" x2="$4" y2="$5"
    local X Y WIDTH HEIGHT
    read -r X Y WIDTH HEIGHT < <(win_geom "$w") || return 1
    local ax1=$(( X + x1 )) ay1=$(( Y + y1 )) ax2=$(( X + x2 )) ay2=$(( Y + y2 ))
    xdotool mousemove "$ax1" "$ay1"; sleep 0.3
    xdotool mousedown 1;             sleep 0.3
    local i
    for i in $(seq 1 10); do
        xdotool mousemove $(( ax1 + (ax2-ax1)*i/10 )) $(( ay1 + (ay2-ay1)*i/10 ))
        sleep 0.06
    done
    sleep 0.3
    xdotool mouseup 1;               sleep 0.5
}

type_keys() { xdotool key --clearmodifiers "$@"; sleep 0.4; }
type_text() { xdotool type --clearmodifiers --delay 40 "$1"; sleep 0.4; }

# --- capture ---------------------------------------------------------------

shot() { scrot -o "${1:-/tmp/guiauto.png}"; }

# shot_win <win> <out.png> — crop the screenshot to just that window
shot_win() {
    local w="$1" out="${2:-/tmp/guiauto-win.png}"
    local X Y WIDTH HEIGHT
    read -r X Y WIDTH HEIGHT < <(win_geom "$w") || return 1
    local tmp; tmp=$(mktemp /tmp/guiauto-full-XXXX.png)
    scrot -o "$tmp"
    python3 - "$tmp" "$out" "$X" "$Y" "$WIDTH" "$HEIGHT" <<'PY'
import sys
from PIL import Image
src,dst,x,y,w,h = sys.argv[1],sys.argv[2],*map(int,sys.argv[3:7])
im = Image.open(src)
x0,y0 = max(0,x), max(0,y)
x1,y1 = min(im.width, x+w), min(im.height, y+h)
im.crop((x0,y0,x1,y1)).save(dst)
PY
    rm -f "$tmp"
    echo "$out"
}

# --- self-test -------------------------------------------------------------
# Verifies the click-doubling workaround is actually in effect, using a
# throwaway Qt widget that counts presses. Run this if clicks start
# misbehaving again (e.g. after an X server / Qt upgrade).
guiauto_selftest() {
    local d=/home/user/.claude/jobs/48a6a92d/tmp/clicktest
    [ -x "$d/build/clicktest" ] || { echo "selftest helper not built at $d"; return 1; }
    local before after
    (env DISPLAY=$DISPLAY QT_XCB_NO_XI2=1 "$d/build/clicktest" > "$d/st.log" 2>&1 &)
    sleep 3
    local w; w=$(xdotool search --name "CLICKTEST-UNIQUE-9x7" | tail -1)
    local X Y WIDTH HEIGHT
    read -r X Y WIDTH HEIGHT < <(win_geom "$w")
    click_at $(( X + 100 )) $(( Y + 50 ))
    click_at $(( X + 100 )) $(( Y + 50 ))
    click_at $(( X + 100 )) $(( Y + 50 ))
    local n; n=$(grep -c PRESS "$d/st.log")
    pkill -x clicktest 2>/dev/null
    if [ "$n" = "3" ]; then echo "guiauto selftest: PASS (3 clicks -> 3 presses)"; return 0
    else echo "guiauto selftest: FAIL (3 clicks -> $n presses; XI2 doubling not suppressed)"; return 1; fi
}
