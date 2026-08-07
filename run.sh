#!/usr/bin/env bash
# run.sh — helper to build and launch QElectroTech in Docker
set -euo pipefail

MODE="${1:-run}"     # run | debug | valgrind | tsan | asan | shell | build-only

# Allow X connections from the local Docker user
xhost +local:docker 2>/dev/null || true

case "$MODE" in
  run)
    echo "▶ Launching QElectroTech (Release)..."
    docker compose up --build qet
    ;;

  debug)
    echo "▶ Launching QElectroTech under GDB (Debug build)..."
    docker compose run --rm --build qet-debug
    ;;

  valgrind)
    mkdir -p valgrind-logs
    echo "▶ Running under Valgrind — output → valgrind-logs/valgrind.log"
    docker compose run --rm --build qet-valgrind
    echo "✔ Done. See valgrind-logs/valgrind.log"
    ;;

  tsan)
    mkdir -p tsan-logs
    echo "▶ Running under ThreadSanitizer — reports → tsan-logs/tsan.<PID>"
    echo "  Use the app normally; close it when done to flush logs."
    echo "  Filter QET-specific races: grep '/src/sources/' tsan-logs/tsan.*"
    docker compose run --rm --build qet-tsan
    echo "✔ Done. See tsan-logs/"
    ;;

  asan)
    mkdir -p asan-logs
    echo "▶ Running under AddressSanitizer — reports → asan-logs/asan.<PID>"
    echo "  Use the app normally; close it when done to flush leak reports."
    echo "  Filter QET-specific errors: grep '/src/sources/' asan-logs/asan.*"
    docker compose run --rm --build qet-asan
    echo "✔ Done. See asan-logs/"
    ;;

  shell)
    echo "▶ Opening shell inside Release container..."
    docker compose run --rm --entrypoint bash qet
    ;;

  build-only)
    echo "▶ Building image only (no launch)..."
    docker compose build qet
    ;;

  clean)
    echo "▶ Removing containers, images, and volumes..."
    docker compose down --rmi all --volumes
    ;;

  *)
    echo "Usage: $0 [run|debug|valgrind|tsan|asan|shell|build-only|clean]"
    exit 1
    ;;
esac
