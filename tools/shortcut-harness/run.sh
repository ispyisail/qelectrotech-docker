#!/bin/bash
# Build and run the ShortcutsConfigPage harness against the CURRENT QET source.
#
# Compiles the real shortcutmanager.cpp and shortcutsconfigpage.cpp standalone
# against Qt5 -- no QElectroTech build needed, runs in seconds. Sources are
# re-copied on every run, so the harness always tests current code.
#
#   ./run.sh [path-to-qet-source]      default: /home/user/qet-fix
set -euo pipefail

QET_SRC="${1:-/home/user/qet-fix}/sources"
HERE="$(cd "$(dirname "$0")" && pwd)"
QT_INC="${QT_INC:-/usr/include/x86_64-linux-gnu/qt5}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for f in shortcutmanager.cpp shortcutmanager.h; do
    cp "$QET_SRC/$f" "$WORK/"
done
for f in shortcutsconfigpage.cpp shortcutsconfigpage.h configpage.h; do
    cp "$QET_SRC/ui/configpage/$f" "$WORK/"
done
cp "$HERE/harness.cpp" "$WORK/"

# QET::Icons is stubbed: the page uses only these two symbols, and pulling in
# the real qeticons.cpp would drag in the Qt resource system for no benefit.
# If the page starts using another icon the build fails loudly here -- add it.
cat > "$WORK/qeticons.h" <<'HDR'
#ifndef QETICONS_STUB_H
#define QETICONS_STUB_H
#include <QIcon>
namespace QET { namespace Icons { extern QIcon EditUndo; extern QIcon ConfigureToolbars; } }
#endif
HDR
cat > "$WORK/qeticons.cpp" <<'SRC'
#include "qeticons.h"
namespace QET { namespace Icons { QIcon EditUndo; QIcon ConfigureToolbars; } }
SRC

# Flatten the two relative includes now that everything sits in one dir.
sed -i 's|#include "\.\./\.\./qeticons\.h"|#include "qeticons.h"|; s|#include "\.\./\.\./shortcutmanager\.h"|#include "shortcutmanager.h"|' "$WORK/shortcutsconfigpage.cpp"

cd "$WORK"
moc -I"$QT_INC" shortcutsconfigpage.h -o moc_shortcutsconfigpage.cpp
moc -I"$QT_INC" configpage.h          -o moc_configpage.cpp
g++ -fPIC -std=c++17 harness.cpp shortcutmanager.cpp shortcutsconfigpage.cpp qeticons.cpp \
    moc_shortcutsconfigpage.cpp moc_configpage.cpp \
    -I"$QT_INC" -I"$QT_INC/QtCore" -I"$QT_INC/QtGui" -I"$QT_INC/QtWidgets" -I. \
    -lQt5Core -lQt5Gui -lQt5Widgets -o harness

QT_QPA_PLATFORM=offscreen HOME="$WORK/home" XDG_CONFIG_HOME="$WORK/cfg" ./harness
