# QET work: what to reach for, and when

You do not need to know QET's internals to direct work on it. You need to know
which of three environments a task belongs in, and which tool answers the
question you are actually asking. That is all this document is.

Read §1 once. After that, jump straight to whichever entry in §3 matches the
words you just used.

---

## 1. The three environments (the thing nobody wrote down)

Almost every wrong turn in this project has been running work in the wrong one
of these.

| | **Native** | **Docker** | **No build** |
|---|---|---|---|
| Where | `/home/user/qet-fix` + `scripts/qet-fastbuild.sh` | `docker compose run --rm <service>` | `simulator/`, `tools/`, `scripts/` |
| Edit → runnable | **1.7 s** | minutes | n/a |
| Use it for | writing and iterating on a C++ fix | sanitizers, fuzzing, clean-room reproducible builds | reading or mutating `.qet` / `.elmt` files |
| Don't use it for | anything needing ASan/TSan/Valgrind | the edit loop — it is 100× slower | anything needing to run QET's UI |

**The rule:** *Am I changing C++?* → Native. *Do I need a sanitizer or a
guaranteed-clean build?* → Docker. *Am I only looking at files?* → No build.

Most people reach for Docker by habit because `run.sh` is the visible entry
point. For fixing a bug, that is the wrong choice and it costs you an hour.

### Before you run anything

1. **`docker ps`** — a running container with `network_mode: host` will steal
   your native launch. QET uses SingleApplication: a second instance forwards
   to the first and you get *its* answers with no error. This has produced
   wrong results here twice.
2. **`git -C /home/user/qet-fix branch --show-current`** — there are 179 local
   branches. Know which one you are on before you build.
3. Building? Use `scripts/qet-fastbuild.sh`, not a plain cmake invocation. See
   `QET-BUILD-SPEED.md`.

---

## 2. Which binary is which

| Build tree | What it is | When |
|---|---|---|
| `build-fast/` | the edit-loop build | default for all development |
| `build-cabinet/` | current feature branch build | cabinet-layout work |
| `build-cabinet-asan/` | same, with AddressSanitizer | chasing memory bugs in that branch |
| `build-mega/`, `build-aux/` | older experiment trees | leave alone; rebuild elsewhere |

---

## 3. The tree

### "QET crashed" / "it froze" / "it hung"

```
Can you make it happen again from a saved file?
├─ YES ─► headless first, always. It is faster and it gives a clean stack.
│         1. run the CLI verbs over that file with a 120 s timeout
│            → scripts/cli-sweep.sh, or a single --resave / --export-*
│         2. crashed?  → build ASan, get the report:
│                        docker compose run --rm qet-asan
│            hung?     → that is a *different* bug class. Check for a modal
│                        dialog (see trap: version-incompatible projects hang
│                        every CLI verb forever, PR #737)
│         3. shrink the input to something minimal before filing
│
└─ NO, only in the GUI ─► docker compose run --rm qet-debug   (gdb attached)
                          or  qet-fuzz-asan  to let the fuzzer find it again
```

**Notes that will save you time:** core dumps are off on this machine
(`ulimit -c` is 0) and `ptrace_scope` blocks `gdb -p`, so attach with
`gdb -batch -ex run -ex bt` instead. Crash fixes are the fastest-merging
category upstream — do not sit on them.

---

### "This behaves wrong" (but nothing crashes)

```
1. Is it already known?
   ├─ bugtracker: qelectrotech.org/bugtracker/  ← check FIRST
   └─ GitHub discussions
2. Is it already FIXED?
   ► Try to reproduce it on current master before doing anything else.
     Three hand-picked bugtracker entries in a row (#256, #278, #288) turned
     out to be already fixed. This step has the best time-saved-per-minute
     of anything in this document.
3. Does the symptom involve saving, loading, or exporting?
   ├─ YES ─► no build needed. Use the file-level tools:
   │          tests/determinism/check.py      (did a save lose or reorder data?)
   │          simulator/canon.py diff          (what exactly changed?)
   └─ NO  ─► native build, reproduce in the GUI, then fix
```

---

### "Fix bugtracker #NNN"

```
1. Reproduce on current master.  ← do not skip
   ├─ cannot reproduce ─► that is a finding. Record how you tried
   │                      ("not reproduced on <sha> via <command>") and move on.
   │                      Closing a stale bug is real work.
   └─ reproduces ─► continue
2. Native build, fastbuild loop, small self-contained change.
3. Verify the exact symptom from the bug report is gone.
4. PR from a branch off master, citing the bug number in the title.
```

Bugtracker-citing fixes have merged upstream in ~0.2 days on average — faster
than any other kind of change. ~75 of the open bugs have never been touched.
**This is the highest-yield work available.**

---

### "Find me some bugs" / "what should I work on?"

Cheapest first. Stop when you have enough to work on.

| Tool | Cost | Finds |
|---|---|---|
| `scripts/cli-sweep.sh` | ~15 min, no build | hangs and crashes in the headless paths |
| `python3 -m simulator sweep` | ~30 min | malformed-input crashes, save corruption |
| `tools/qet-lint` *(W2)* | seconds | semantic defects across 6,918 elements |
| bugtracker triage *(W4)* | one-off scrape | the 75 untouched bugs, ranked |
| `qet-fuzz-asan` | hours, unattended | GUI-only memory bugs |

See `TOOLING-PLAN.md` for the ones still to be built.

---

### "I want feature X" / "someone asked for X"

```
Is there a discussion or bugtracker entry for it?
├─ NO  ─► create one and get a signal before building anything
└─ YES ─► does it fight the existing architecture?
          ├─ YES ─► write a scope doc FIRST, post it, wait for a reaction.
          │         Design-heavy features that fight the architecture are the
          │         one category that gets closed unmerged here (see
          │         LINK-ID-SCOPE.md, QUICK-INSERT-SCOPE.md for the pattern)
          └─ NO  ─► native build, keep it small and self-contained
```

Features merge in ~1.7 days when they are small and self-contained. Packaging
and build-infrastructure changes stall indefinitely — that is not a reflection
on the work, it needs a maintainer decision about release infra.

---

### "Did we break something?" / "review this before I send it"

```
Changed C++?          ─► /code-review, then build and run the affected path
Changed save/load?    ─► tests/determinism  (this is the gate that catches
                          silent data loss)
Want a full check?    ─► tools/refdiff  (W3, once built) — same corpus through
                          two refs, semantic diff
Touching sanitizer-
sensitive code?       ─► docker compose run --rm qet-asan-regression
```

---

### "It's slow" / "it lags" / "it hangs for a moment"

Both of the tools for this already exist and are merged upstream:

- **EventLoopWatchdog** (PR #665) — reports UI stalls via timer lateness
- **Diagnostic logging + crash-time ring flush** (PR #646/#647) — turn it on
  and reproduce; the ring buffer captures what happened before the stall

Sample RSS and fd count while reproducing. Flat numbers rule out a leak in one
minute and stop you chasing the wrong hypothesis.

---

## 4. Where things live

| | |
|---|---|
| Harness, tools, docs | `/home/user/qelectrotech-docker` |
| QET source | `/home/user/qet-fix` |
| Element collection | `elements-10-electric/10_electric` |
| Example projects | `/home/user/qet-fix/examples` |
| Upstream bugtracker | <https://qelectrotech.org/bugtracker/> |
| Upstream repo | `qelectrotech/qelectrotech-source-mirror` |

**Documents, by what you want:**

| Want to… | Read |
|---|---|
| build faster | `QET-BUILD-SPEED.md` |
| know what tooling to build next | `TOOLING-PLAN.md` |
| understand the oracle/testing thesis | `SIMULATOR-DESIGN.md` |
| see how a scope doc is written | `QUICK-INSERT-SCOPE.md`, `LINK-ID-SCOPE.md` |
| work on IEC 81346 labelling | `IEC81346-PLAN.md` |
| work on icons | `ICONS-DOMAIN-SET.md`, `ICONS-HIDPI-PR1.md` |
| understand auto-wiring on placement | `AUTO-CONNECT-SHIFT-RESEARCH.md` |
| propose a scripting API | `SCRIPTING-RFC.md` |
