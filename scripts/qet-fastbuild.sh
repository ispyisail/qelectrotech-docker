#!/usr/bin/env bash
#
# qet-fastbuild.sh — configure a QElectroTech build tree tuned for a fast
# edit/compile/run loop.
#
# Measured on a 24-thread Xeon E5-2650 v4, Qt 5.15.18, GCC 15.2, against
# qelectrotech-source-mirror master 4ff2be3f4:
#
#   configure (fresh build dir)      217 s  ->   2.9 s
#   cold full build                  236 s  ->    55 s
#   full rebuild, warm ccache        236 s  ->   4.4 s
#   edit one .cpp -> runnable       5.55 s  ->  1.72 s
#   edit diagram.h (94 dependents)  50.6 s  ->   6.2 s
#
# See QET-BUILD-SPEED.md for how those numbers were obtained and why.
#
# Usage:
#   scripts/qet-fastbuild.sh setup                 # one-off: deps + ccache config
#   scripts/qet-fastbuild.sh configure [src] [bld] # configure a build tree
#   scripts/qet-fastbuild.sh build     [bld]       # build it
#   scripts/qet-fastbuild.sh loop      [bld]       # time the edit/rebuild loop
#
set -euo pipefail

QET_SRC_DEFAULT="${QET_SRC:-$HOME/qet-fix}"
QET_BUILD_DEFAULT="${QET_BUILD:-$QET_SRC_DEFAULT/build-fast}"
DEPS_CACHE="${QET_DEPS_CACHE:-$HOME/.cache/qet-deps}"
CCACHE_DIR_DEFAULT="${CCACHE_DIR:-$HOME/.cache/ccache}"

# The seven FetchContent dependencies QET clones at configure time, as
# <FetchContent name>=<git url>@<tag>. Miss one and a fully-disconnected
# configure fails at generate time rather than configure time, which makes it
# look like an unrelated error (e.g. "Catch2::Catch2 ... target was not found").
DEPS=(
  "pugixml=https://github.com/zeux/pugixml.git@v1.15"
  "SingleApplication=https://github.com/itay-grudev/SingleApplication.git@v3.2.0"
  "ecm=https://invent.kde.org/frameworks/extra-cmake-modules.git@v5.77.0"
  "kcoreaddons=https://invent.kde.org/frameworks/kcoreaddons.git@v5.77.0"
  "kwidgetsaddons=https://invent.kde.org/frameworks/kwidgetsaddons.git@v5.77.0"
  "Catch2=https://github.com/catchorg/Catch2.git@v2.13.10"
  "GTest=https://github.com/google/googletest.git@v1.17.0"
)

die() { echo "error: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

cmd_setup() {
  local missing=()
  have ccache || missing+=(ccache)
  have mold   || missing+=(mold)
  if (( ${#missing[@]} )); then
    echo "Installing: ${missing[*]}"
    sudo apt-get install -y ccache mold
  fi

  mkdir -p "$DEPS_CACHE"
  for entry in "${DEPS[@]}"; do
    local name="${entry%%=*}" rest="${entry#*=}"
    local url="${rest%@*}" tag="${rest##*@}"
    local dir="$DEPS_CACHE/${name,,}-src"
    if [[ -d "$dir/.git" ]]; then
      echo "  have  $name"
    else
      echo "  clone $name @ $tag"
      git clone --depth 1 --branch "$tag" "$url" "$dir" >/dev/null 2>&1 \
        || die "failed to clone $name from $url @ $tag"
    fi
  done

  # ccache tuning. Each of these was necessary, not cosmetic:
  #   sloppiness=pch_defines,time_macros
  #       without it ccache refuses to cache any TU that uses a PCH --
  #       measured 68% of compiles falling through as "Could not use
  #       precompiled header".
  #   base_dir
  #       without it, absolute -I paths bake the build directory into the
  #       hash, so a second build tree gets ~5% hits instead of ~73%.
  export CCACHE_DIR="$CCACHE_DIR_DEFAULT"
  mkdir -p "$CCACHE_DIR"
  ccache -o max_size=20G
  ccache -o sloppiness=pch_defines,time_macros,include_file_mtime,include_file_ctime
  ccache -o base_dir="$HOME"
  ccache -o hash_dir=false
  echo
  echo "ccache configured:"
  ccache -p | grep -E "max_size|sloppiness|base_dir|hash_dir" | sed 's/^/  /'
  echo
  echo "Deps cached in $DEPS_CACHE"
  echo "Next: scripts/qet-fastbuild.sh configure"
}

cmd_configure() {
  local src="${1:-$QET_SRC_DEFAULT}" bld="${2:-$QET_BUILD_DEFAULT}"
  [[ -f "$src/CMakeLists.txt" ]] || die "no CMakeLists.txt in $src"
  [[ -d "$DEPS_CACHE" ]] || die "run 'setup' first (no dep cache at $DEPS_CACHE)"

  local args=(
    -S "$src" -B "$bld" -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
    -DCMAKE_C_COMPILER_LAUNCHER=ccache
    -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=mold
    -DFETCHCONTENT_FULLY_DISCONNECTED=ON
  )
  for entry in "${DEPS[@]}"; do
    local name="${entry%%=*}"
    args+=("-DFETCHCONTENT_SOURCE_DIR_${name^^}=$DEPS_CACHE/${name,,}-src")
  done

  # PCH is opt-in and only takes effect if the tree carries the
  # target_precompile_headers() block (see QET-BUILD-SPEED.md). Harmless if not.
  args+=(-DQET_ENABLE_PCH=ON)

  export CCACHE_DIR="$CCACHE_DIR_DEFAULT"
  echo "Configuring $src -> $bld"
  time cmake "${args[@]}"
}

cmd_build() {
  local bld="${1:-$QET_BUILD_DEFAULT}"
  export CCACHE_DIR="$CCACHE_DIR_DEFAULT"
  time ninja -C "$bld" qelectrotech
}

cmd_loop() {
  local bld="${1:-$QET_BUILD_DEFAULT}" src="${QET_SRC:-$QET_SRC_DEFAULT}"
  local probe="$src/sources/undocommand/rotateselectioncommand.cpp"
  [[ -f "$probe" ]] || die "probe file missing: $probe"
  export CCACHE_DIR="$CCACHE_DIR_DEFAULT"

  cp "$probe" "$probe.fastbuild-bak"
  trap 'mv -f "$probe.fastbuild-bak" "$probe" 2>/dev/null || true' EXIT

  echo "Timing edit -> runnable binary (real semantic edits, 3 runs)"
  echo "NOTE: a comment-only edit is invisible after preprocessing and will"
  echo "      produce a misleading ccache hit -- these append real code."
  for i in 1 2 3; do
    cp "$probe.fastbuild-bak" "$probe"
    printf '\nint qet_fastbuild_probe_%d() { return %d; }\n' "$i" "$((i * 7))" >> "$probe"
    /usr/bin/time -f "  run$i: %e s" ninja -C "$bld" qelectrotech 2>&1 | tail -1
  done
}

case "${1:-}" in
  setup)     shift; cmd_setup "$@" ;;
  configure) shift; cmd_configure "$@" ;;
  build)     shift; cmd_build "$@" ;;
  loop)      shift; cmd_loop "$@" ;;
  *)
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
