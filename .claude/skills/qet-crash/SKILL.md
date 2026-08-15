---
name: qet-crash
description: Diagnose a QElectroTech crash, hang, or freeze — getting a stack trace, telling a hang from a busy-spin, and the sanitizer services. Load when QET segfaults, aborts, dies, stops responding, or a headless run never returns.
---

# QET crashes and hangs

Load `qet-env` first.

## Fast path: "it crashes when I open a file"

This is the most common report and it is bisectable in about five seconds.
Ask two questions, then run one command.

1. **Every file, or one specific file?** Every file → the install or config is
   broken, not the file; try a clean sandbox (`simulator/env.py`) before
   anything else. One file → that file triggers a bug and *is* the repro.
2. **A project (`.qet`) or an element (`.elmt`)?**

```bash
# project
QT_QPA_PLATFORM=offscreen timeout 120 \
  /home/user/qet-fix/build-fast/qelectrotech --resave the-file.qet /tmp/out.qet
# element
QT_QPA_PLATFORM=offscreen timeout 120 \
  /home/user/qet-fix/build-fast/qelectrotech --check-elements the-file.elmt
```

| Result | What it means | Next |
|---|---|---|
| Crashes headless | bug is in the load/parse path | best case — fully reproducible, no GUI, get a stack with the gdb recipe below and minimise the input |
| Runs fine headless | bug is in the GUI/render path | `docker compose run --rm qet-debug`, reproduce by hand under gdb |
| Hangs, no output | probably a modal dialog during load | see **Hangs** below — this is PR #737, not a crash |

**Known instance of exactly this symptom:** `xpx.elmt` in the element
collection contains `&#11;` (U+000B, illegal in XML 1.0) and **segfaults Qt's
`QDomDocument::setContent()`** instead of erroring. If the file is an element
and it dies during parse, check for illegal control bytes first — validate with
Python's `ElementTree`, which rejects them cleanly. That contrast is the
finding, and it is a bug in two places at once.

## Classify before investigating

These are three different bug classes with three different tools.

| Symptom | Process state | Reach for |
|---|---|---|
| Dies, exit code 139/134/11/6 | gone | ASan, stack trace |
| Unresponsive, ~0% CPU | blocked | modal dialog or deadlock |
| Unresponsive, ~100% CPU | busy-spin | bad numeric input |

Tell the last two apart by reading utime in `/proc/<pid>/stat`. A NaN
coordinate injected into a project produces a 100% busy-spin, not a crash —
that is a real defect found this way.

## Getting a stack trace on this machine

Core dumps are **unavailable by default**: `ulimit -c` is 0 and cores are piped
to apport. `ptrace_scope` also blocks `gdb -p` against a running process.

Launch under gdb instead — this works:

```bash
gdb -batch -ex run -ex bt --args \
  /home/user/qet-fix/build-fast/qelectrotech --resave in.qet out.qet
```

## AddressSanitizer

```bash
docker compose run --rm qet-asan          # ASan build, logs → asan-logs/
docker compose run --rm qet-tsan          # ThreadSanitizer → tsan-logs/
docker compose run --rm qet-valgrind      # memcheck → valgrind-logs/
```

Sanitizer services need `cap_add: SYS_PTRACE` and `seccomp:unconfined` — both
already set in `docker-compose.yml`. `build-cabinet-asan/` is a native ASan
tree if you need the fast loop instead.

For leak work specifically, `scripts/asan-compare.sh` diffs LeakSanitizer
reports between two refs. **The app must exit via WM_DELETE_WINDOW, never
SIGTERM** — LSan only reports on a clean exit, and a SIGTERM kill yields empty
reports for both refs and a meaningless diff.

## Hangs

Check for a modal dialog first. `QETProject::readProjectXml()` raises blocking
`QMessageBox` prompts for a project newer than the build or older than 0.6.
Headless there is nobody to answer, so **every** CLI verb hangs forever, during
load, before any export runs. `examples/schema_indus.qet` (version 0.3) does
this. Fix is PR #737 / local branch `fix/cli-headless-version-prompt-hang`.

For GUI stalls rather than full hangs, EventLoopWatchdog (PR #665, merged)
reports timer lateness, and the diagnostic logging ring buffer (PR #646/#647,
merged) captures what ran just before.

## Finding crashes rather than waiting for them

```bash
docker compose run --rm qet-fuzz-asan                    # GUI fuzzer + ASan
docker compose run --rm qet-edz-fuzz                     # EDZ importer, ASan+UBSan
python3 -m simulator sweep --binary <path> --corpus <dir> # malformed-input sweep
```

The simulator sweep found both a NaN-coordinate busy-spin hang and a NUL-byte
SIGSEGV (upstream PR #682). Logs land in host-mounted dirs (`fuzzer-asan-logs/`,
`edz-fuzz-logs/`), never inside the container — `--rm` discards container state.

## Reporting

Minimise the input first (see `qet-repro`), then write it up in `FINDINGS.md`
with the exact command, binary sha, and the trace. Crash fixes are the
fastest-merging category upstream; do not sit on one.
