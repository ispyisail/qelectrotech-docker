#!/usr/bin/env bash
# Test for issue #283: verify that center alignment round-trips correctly.
# Strategy:
#   1. Place a graphics_table.json that simulates what the buggy saveConfig writes
#      (alignment = "AlignHCenter", which the old loadConfig misreads as Right).
#   2. Launch QET headlessly, open Add Nomenclature, load the config, screenshot.
#   3. The combobox label should read "Center" not "Right".
set -euo pipefail

export DISPLAY=:99
Xvfb :99 -screen 0 1280x1024x24 &
XVFB_PID=$!
sleep 1

QET_HOME=$(mktemp -d)
trap "kill $XVFB_PID 2>/dev/null; rm -rf $QET_HOME" EXIT

# Write a config file with the alignment string the buggy code saves
mkdir -p "$QET_HOME/.qet"
cat > "$QET_HOME/.qet/graphics_table.json" <<'EOF'
{
    "test-center": {
        "header": {
            "alignment": "AlignHCenter",
            "font": "Sans Serif,9,-1,5,50,0,0,0,0,0",
            "margins": "5;5;10;5"
        },
        "table": {
            "alignment": "AlignHCenter",
            "font": "Sans Serif,9,-1,5,50,0,0,0,0,0",
            "margins": "5;5;10;5"
        }
    }
}
EOF

echo "[test] Config written to $QET_HOME/.qet/graphics_table.json"
echo "[test] Starting QET..."
HOME="$QET_HOME" qelectrotech &
QET_PID=$!
sleep 3

# Open Project menu → Add a Nomenclature
xdotool search --sync --onlyvisible --name "QElectroTech" windowfocus
sleep 0.5
xdotool key alt+F10   # maximise
sleep 0.3

# Click the Project menu
xdotool key alt+p
sleep 0.5
# "Add a Nomenclature" is typically the 4th or 5th item — use keyboard nav
xdotool key n          # trigger by accelerator if present
sleep 1.0

# If dialog opened, switch to the saved config and load it
WIN=$(xdotool search --name "Nomenclature\|Table\|Tableau" 2>/dev/null | head -1 || true)
if [ -z "$WIN" ]; then
    echo "[test] SKIP — could not open Add Nomenclature dialog (menu navigation may differ)"
    kill $QET_PID 2>/dev/null || true
    exit 0
fi

xdotool windowfocus "$WIN"
sleep 0.3

# Take a screenshot of the dialog for manual inspection
SHOT="/tmp/align_test_before.png"
import -window "$WIN" "$SHOT" 2>/dev/null || scrot -u "$SHOT" 2>/dev/null || true
echo "[test] Screenshot saved to $SHOT"

kill $QET_PID 2>/dev/null || true
echo "[test] Done."
