---
name: qet-env
description: QElectroTech environment facts — which build tree, which docker service, which branch, and the isolation traps. Load before building, running, or launching QET in any form, or when a run gives results that look wrong, stale, or impossible.
---

# QET environment

## Before running anything

1. **`docker ps`** — a running container with `network_mode: host` steals
   native launches. QET uses SingleApplication: a second instance forwards its
   request to the first and returns *that* process's answers with **no error**.
   This has produced wrong results in this project twice. If a result looks
   impossible, check this first.
2. **`git -C /home/user/qet-fix branch --show-current`** — 179 local branches
   exist. Know which one is checked out before building.
3. Python work driving QET must go through `simulator/env.py`
   (`sandbox_context()`, `assert_no_other_qet_running()`), which gives an
   isolated `HOME` + `XDG_CONFIG_HOME` + `XDG_DATA_HOME`. Overriding `HOME`
   alone is **not** enough on this machine.

## The three environments

| | Native | Docker | No build |
|---|---|---|---|
| Where | `/home/user/qet-fix` + `scripts/qet-fastbuild.sh` | `docker compose run --rm <service>` | `simulator/`, `tools/`, `scripts/` |
| Edit → runnable | **1.7 s** | minutes | n/a |
| For | writing and iterating a C++ fix | sanitizers, fuzzing, clean-room builds | reading/mutating `.qet` and `.elmt` |

**Rule:** changing C++ → Native. Need a sanitizer or a guaranteed-clean build
→ Docker. Only looking at files → no build at all.

Reaching for Docker to develop a fix is the most common wrong turn here; it is
roughly 100× slower than the native edit loop.

## Building

```bash
scripts/qet-fastbuild.sh setup                    # one-off: deps + ccache
scripts/qet-fastbuild.sh configure <src> <bld>
scripts/qet-fastbuild.sh build <bld>
```

Cold ≈ 55 s, warm ≈ 4.4 s, single-file edit ≈ 1.7 s. Details in
`QET-BUILD-SPEED.md`. Do not hand-roll cmake invocations.

| Build tree | What it is |
|---|---|
| `build-fast/` | the edit-loop build — default for development |
| `build-cabinet/` | cabinet-layout feature branch |
| `build-cabinet-asan/` | same, with AddressSanitizer |
| `build-mega/`, `build-aux/` | older experiment trees — leave alone |

## Docker services

Full table in `CLAUDE.md`. The ones that matter most:

| Service | Purpose |
|---|---|
| `qet-asan` / `qet-tsan` / `qet-valgrind` | sanitizer runs |
| `qet-debug` | GDB-attached debug build |
| `qet-test` | ctest under Xvfb |
| `qet-determinism` | save idempotence / data-preservation gate |
| `qet-asan-regression` | PR #519 leak-fix regression suite |
| `qet-fuzz`, `qet-fuzz-asan`, `qet-fuzz-tsan` | GUI fuzzers |
| `qet-scenarios` | scripted GUI scenarios (fixtures — do not extend) |

**`docker compose run` does not rebuild the image.** Build explicitly first, or
the container silently runs old code. Docker also caches `git clone` layers by
command string, so pass a changing build arg when a branch has moved:

```bash
docker compose build --build-arg TESTBUILD_REV=$(date +%s) qet-testbuild
docker run --rm qelectrotech:testbuild cat /BUILT_FROM.txt   # verify contents
```

**`docker compose run --rm` discards the container filesystem.** Anything
written to the container's `/tmp` is gone — mount a host directory.

## Headless

`QT_QPA_PLATFORM=offscreen` is enough for the CLI verbs; no Xvfb needed. Always
pass a timeout — a version-incompatible project raises a modal dialog during
load and hangs every CLI verb forever (PR #737, still open).

## Paths

| | |
|---|---|
| Harness, tools, docs | `/home/user/qelectrotech-docker` |
| QET source | `/home/user/qet-fix` |
| Example projects | `/home/user/qet-fix/examples` (23 `.qet`) |
| Element collection | `elements-10-electric/10_electric` (6,918 `.elmt`) |
