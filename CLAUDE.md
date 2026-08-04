# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository is a Docker harness for building, testing, and fuzzing [QElectroTech](https://github.com/qelectrotech/qelectrotech-source-mirror) — a Qt5/C++ electrical diagram editor. It does **not** contain QET source code; the source is cloned from GitHub during each Docker build. What lives here are:

- The multi-stage `Dockerfile` defining 9 distinct build targets
- `docker-compose.yml` wiring those targets to named services
- `run.sh` — a convenience wrapper around `docker compose`
- Patch files (`.cpp`, `.h`) that are `COPY`-ed over the cloned source to apply fixes before building
- `fuzzer/` — a headless Python GUI fuzzer driven by `xdotool`
- `edz-fuzzer/` — a standalone C++ harness (`fuzz_edz.cpp`) fuzzing the EDZ importer with ASAN+UBSan

## Commands

### Launch / build

```bash
./run.sh                    # build & run Release image (GUI via X11)
./run.sh debug              # GDB-attached debug build
./run.sh valgrind           # Valgrind memcheck → valgrind-logs/valgrind.log
./run.sh tsan               # ThreadSanitizer → tsan-logs/
./run.sh asan               # AddressSanitizer → asan-logs/
./run.sh shell              # bash inside Release container
./run.sh build-only         # build image without launching
./run.sh clean              # remove all containers, images, and volumes
```

### Tests

```bash
docker compose run --rm qet-test               # ctest under Xvfb (all tests, parallel 4)
docker compose run --rm qet-asan-regression    # PR #519 ASan regression suite (tests/asan-regression/)
```

### Fuzzing

```bash
# GUI fuzzer (plain debug binary)
docker compose run --rm qet-fuzz
FUZZER_HOURS=8 FUZZER_SPEED=fast docker compose run --rm qet-fuzz

# GUI fuzzer with AddressSanitizer
docker compose run --rm qet-fuzz-asan

# GUI fuzzer with ThreadSanitizer
docker compose run --rm qet-fuzz-tsan

# Fuzzer self-test (verifies xdotool/scrot/crash-detection infrastructure)
FUZZER_SELF_TEST=1 docker compose run --rm qet-fuzz

# EDZ importer fuzzer (C++ harness + malformed corpus + ASAN)
docker compose run --rm qet-edz-fuzz
```

Fuzzer logs land in host-mounted directories: `fuzzer-logs/`, `fuzzer-asan-logs/`, `fuzzer-tsan-logs/`, `edz-fuzz-logs/`.

### EDZ feature branch

```bash
docker compose run --rm qet-edz     # run QET built from feature/edz-import branch
```

### Combined test build (manual PR review)

```bash
docker compose run --rm qet-testbuild   # master + several PRs merged together
```

Builds the `test-build-logging-wiring` branch on the `ispyisail` fork: current
`master` with PR #646/#647 (diagnostic logging rework) and PR #625/#628/#629/#630
(discussion #503 wiring-database stack) merged in. This exists so several PRs can
be exercised in one session instead of the lead developer building each branch
individually. A `~/Desktop/QElectroTech-TestBuild.desktop` launcher runs it.

The branch is a **throwaway integration branch, not a proposed change** — never
open a PR from it.

To refresh after the underlying PR branches move: re-merge them onto current
`master`, force-push the branch, then rebuild **with a new cache key**:

```bash
docker compose build --build-arg TESTBUILD_REV=$(date +%s) qet-testbuild
```

The `TESTBUILD_REV` arg matters — Docker caches the `git clone` layer by command
string alone, so a plain rebuild silently reuses the old commits and produces a
stale binary that looks current. To check what an image actually contains:

```bash
docker run --rm qelectrotech:testbuild cat /BUILT_FROM.txt
```

### ASan before/after leak comparison (`scripts/asan-compare.sh`)

Host-side script (not Dockerized) that builds QET with ASan at a base ref and a patched ref (branch or PR number), opens the same `.qet` project in each, and diffs the LeakSanitizer reports. Requires a local checkout of `qelectrotech-source-mirror`, qmake/Qt dev deps, and `wmctrl` or `xdotool`:

```bash
scripts/asan-compare.sh -r /path/to/qet-repo -b master -p 519 -f /path/to/project.qet
```

Critical detail baked into the script: LeakSanitizer only reports on a **clean exit**, so the app must be closed via WM_DELETE_WINDOW, never SIGTERM — a SIGTERM kill yields empty reports for both refs and a meaningless diff.

## Architecture

### Dockerfile stages

| Stage | Target name | Purpose |
|-------|-------------|---------|
| 1 | `builder` | Release build from `main` branch |
| 2 | `test` | Inherits `builder`; runs `ctest` under Xvfb |
| 3 | `debug-builder` / `debug` | Debug build with GDB, Valgrind, strace |
| 4 | `runtime` | Minimal runtime image from `builder` |
| 5 | `tsan-builder` / `tsan` | ThreadSanitizer build |
| 6 | `asan-builder` / `asan` | AddressSanitizer build |
| 7 | `fuzzer-builder` / `fuzzer` | Debug build + Python GUI fuzzer |
| 8 | `fuzzer-asan-builder` / `fuzzer-asan` | ASAN build + Python GUI fuzzer |
| 9 | `fuzzer-tsan-builder` / `fuzzer-tsan` | TSan build + Python GUI fuzzer |
| 10 | `edz-builder` / `edz` | Feature branch build with EDZ patch files |
| 11 | `testbuild-builder` / `testbuild` | Combined multi-PR build for manual review (see above) |
| – | `edz-fuzzer-builder` / `edz-fuzzer` | C++ EDZ importer fuzzer (ASAN+UBSan, clang) |

Sanitizer stages require `cap_add: SYS_PTRACE` and `seccomp:unconfined` (set in `docker-compose.yml`).

### Patch files

The `.cpp` and `.h` files at the repo root are patches applied by `COPY` instructions over the cloned QET source. They target specific upstream PRs/issues:

| File(s) | Target in source tree | Fix |
|---------|----------------------|-----|
| `qetapp.cpp.patch` | `sources/qetapp.cpp` | PR #514 — thread-unsafe `QStandardPaths` |
| `machine_info.h`, `main.cpp`, `qetdiagrameditor.h` | `sources/` | PR #515 — `MachineInfo` uninit members, main-thread pre-init order |
| `fileelementcollectionitem.*`, `xmlprojectelementcollectionitem.*`, `elementscollectionmodel.cpp`, `elementslocation.cpp`, `terminal.cpp`, `qetinformation.h` | `sources/ElementsCollection/`, `sources/qetgraphicsitem/` | PR #516 — thread-safe `setUpData()`, inline const QString |
| `customelementgraphicpart.cpp`, `parttext.cpp`, `partdynamictextfield.cpp` | `sources/editor/graphicspart/` | Issue #481 — first-click moves item (spurious mouseMoveEvents from dock resize) |
| `addtabledialog.cpp` | `sources/factory/ui/` | Issue #283 — center alignment lost on load |
| `edzpart.h`, `edzpart.cpp`, `edzelementbuilder.cpp` | `sources/import/edz/` | PR #513 response — `terminalNr`-based grouping fix (EDZ stage only) |
| `styleeditor.cpp`, `exportdialog.cpp`, `genericpanel.cpp`, `elementscene.cpp` | various | ASAN stage only — additional fixes found via sanitizer runs |

Not all patches are applied to every stage — check the relevant `COPY` block in `Dockerfile` before editing.

### GUI fuzzer (`fuzzer/`)

`fuzzer.py` is the orchestrator. It starts QET as a subprocess, finds its window with `xdotool`, and runs a weighted-random loop of ~40 actions for a configured duration. Key modules:

- `actions/base.py` — `XDo` (xdotool wrapper) and `QETLayout` (window geometry → logical regions)
- `actions/element_ops.py` — drag/drop, move, rotate, delete elements
- `actions/wire_ops.py` — draw, flood, delete wires
- `actions/selection_ops.py` — select, cut, copy/paste, undo/redo
- `actions/diagram_ops.py` — zoom, scroll, pan, tab navigation
- `actions/project_ops.py` — new/save/export/print
- `actions/editor_ops.py` — element editor fuzzing
- `monitor.py` — `ProcessMonitor` watches for crashes and writes `crashes.jsonl`
- `analyze.py` — post-run crash log analysis and report generation

The container's `run.sh` starts Xvfb and optionally `openbox`, then calls `fuzzer.py`.

### EDZ importer fuzzer (`edz-fuzzer/`)

A standalone C++ fuzzing harness (`fuzz_edz.cpp`) that calls `EdzImporter::importToDirectory()` against a corpus of malformed `.edz` files generated by `gen_corpus.py`. Built with clang + ASAN + UBSan via its own `CMakeLists.txt`. Outputs ASAN reports to `edz-fuzz-logs/`.

### ASan regression suite (`tests/asan-regression/`)

Self-contained tests proving the four memory-leak fixes in upstream PR #519 (ExportDialog, GenericPanel, StyleEditor, ElementScene paste-area) remove their leaks without introducing use-after-free or double-free. Each `t*.cpp` compiles in two variants from one source — `-DLEGACY` selects the pre-patch code, default selects the patched code — and `run.sh` runs both under identical ASan, writing `report.md` and `raw/<test>_{legacy,patched}.out`. Exit code is non-zero if a patched variant leaks or hits a fatal ASan error. The `qet-asan-regression` compose service reuses the `qelectrotech:test` image and mounts this directory at `/work`.

## Key env vars for fuzzer containers

| Variable | Default | Description |
|----------|---------|-------------|
| `FUZZER_HOURS` | `1` | Duration |
| `FUZZER_SPEED` | `normal` | `slow` / `normal` / `fast` / `ultra` |
| `FUZZER_SEED` | (random) | Seed for reproducibility |
| `FUZZER_SCREENSHOT_INT` | `60` | Seconds between periodic screenshots |
| `FUZZER_SELF_TEST` | `0` | Set to `1` to run infrastructure self-test |
| `FUZZER_LOG_DIR` | `/fuzzer/logs` | Log output directory (mapped to host) |
