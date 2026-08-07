# QET build speed — measurements and setup

How to get QElectroTech's edit/compile/run loop under 2 seconds, and the
evidence for each change.

**Measured on:** 24-thread Xeon E5-2650 v4 @ 2.2 GHz, 76 GB RAM, build tree on
tmpfs. Qt 5.15.18, GCC 15.2, CMake 4.2.3, Ninja 1.13.2.
**Source:** `qelectrotech-source-mirror` master `4ff2be3f4`, Release build.

Setup script: `scripts/qet-fastbuild.sh`.

---

## 1. Results

| Scenario | Before | After | Speedup |
|---|---:|---:|---:|
| Configure a fresh build dir | 217 s | **2.9 s** | 75× |
| Cold full build (nothing cached) | 236 s | **55 s** | 4.3× |
| Full rebuild, ccache warm (branch switch) | 236 s | **4.4 s** | 54× |
| **Edit one `.cpp` → runnable binary** | **5.55 s** | **1.72 s** | **3.2×** |
| Edit `diagram.h` (94 dependents) | 50.6 s | **6.2 s** | 8.2× |

The 1.72 s figure is from **real semantic edits** (appending a new function),
not `touch`. That distinction matters — see §5.

### The sub-2 s number requires the PCH source patch

`scripts/qet-fastbuild.sh` alone — mold, ccache, fast configure, no change to
QET's `CMakeLists.txt` — gives:

| Scenario | Script only | Script + PCH patch |
|---|---:|---:|
| Configure | 2.9 s | 2.9 s |
| Full rebuild, ccache warm | 4.4 s | 4.4 s |
| **Edit one `.cpp` → runnable** | **5.08 s** | **1.72 s** |

Measured, not extrapolated. The edit loop is dominated by the single-TU compile
(§2), and mold and ccache cannot touch that: mold only saves 0.85 s of link, and
ccache cannot hit on a file whose content genuinely changed. **Only the PCH
moves the edit loop**, taking it from 5.08 s to 1.72 s.

So: the script is worth having on its own for the configure and branch-switch
wins, but if the goal is specifically a sub-2-second edit loop, §3.1 is not
optional.

The biggest practical win is arguably still not the headline number — it's the
54× on *full rebuild with a warm cache*. That is the branch-switch case, which
is what you actually pay when reviewing PRs: checkout, build, look, checkout
back.

---

## 2. Where the time actually went

Baseline decomposition of the 5.55 s edit-one-file loop:

| Step | Time |
|---|---:|
| AUTOMOC / AUTOUIC | 0.35 s |
| Compile 1 translation unit | **4.12 s** |
| Link (GNU ld.bfd 2.46) | 0.95 s |

So the loop was dominated by compiling a *single* file. Why:

```
sources/undocommand/rotateselectioncommand.cpp        214 lines
  after preprocessing                             197,796 lines   (6.5 MB)
```

**A 924× amplification, paid ~420 times per full build.** Qt's headers are the
entire cost.

What it is *not*:

| Variant | Time |
|---|---:|
| `-O3` (as configured) | 4.12 s |
| `-O2` | 4.14 s |
| `-O1` | 3.90 s |
| `-Og` | 3.85 s |
| `-O0` | 3.77 s |
| `-E` (preprocess only) | 0.59 s |

Dropping from `-O3` to `-O0` saves **0.35 s — 8%**. The usual advice ("build
Debug instead of Release, it compiles faster") is close to worthless here. The
cost is the compiler front-end parsing and doing semantic analysis on the
preprocessed Qt headers, and only a PCH addresses that.

---

## 3. The three changes that matter

### 3.1 Precompiled headers — 4.12 s → 1.21 s

Caches exactly the thing that was expensive: the parsed state of the Qt headers.

```cmake
if(QET_ENABLE_PCH)
    # The target mixes C++ with the 18 C files of the bundled LZMA decoder,
    # so the PCH must be restricted to CXX or the Qt headers get fed to the
    # C compiler.
    target_precompile_headers(${PROJECT_NAME} PRIVATE
        "$<$<COMPILE_LANGUAGE:CXX>:<QtCore/QtCore$<ANGLE-R>>"
        "$<$<COMPILE_LANGUAGE:CXX>:<QtGui/QtGui$<ANGLE-R>>"
        "$<$<COMPILE_LANGUAGE:CXX>:<QtWidgets/QtWidgets$<ANGLE-R>>"
        "$<$<COMPILE_LANGUAGE:CXX>:<QtXml/QtXml$<ANGLE-R>>"
    )
endif()
```

One-off PCH build: 7.5 s, 218 MB on disk.

This is the only change that needs a patch to QET's `CMakeLists.txt`; everything
else is command-line flags. Keep it behind an option — see §5 for why it should
default to OFF.

### 3.2 mold linker — 0.95 s → 0.10 s

Pure command-line, no source change:

```
-DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=mold
```

Verified the output is a working binary and identifies correctly:

```
$ readelf -p .comment qelectrotech | grep mold
  mold 2.40.4 (compatible with GNU ld)
$ QT_QPA_PLATFORM=offscreen ./qelectrotech --version
0.100.1-dev
```

### 3.3 ccache — full rebuild 236 s → 4.4 s

```
-DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_C_COMPILER_LAUNCHER=ccache
```

Two settings are **required**, not optional tuning — see §4.

---

## 4. Gotchas — every one of these was hit for real

**1. PCH breaks the build unless language-guarded.**
The `qelectrotech` target compiles 18 C files (`sources/import/edz/lzma/*.c`)
alongside the C++. A plain `target_precompile_headers(...)` list applies to
both languages, so Qt headers get handed to the C compiler:

```
qnamespace.h:64:1: error: unknown type name 'namespace'
```

Fix is the `$<$<COMPILE_LANGUAGE:CXX>:...>` wrapper in §3.1. Note `$<ANGLE-R>`
for the closing bracket — a literal `>` terminates the generator expression.

**2. ccache silently refuses to cache PCH builds.**
Out of the box, with a PCH in play:

```
Cacheable calls:   281 /  870 (32.30%)
Uncacheable calls: 589 /  870 (67.70%)
  Could not use precompiled header: 589 / 589 (100.0%)
```

Fix: `ccache -o sloppiness=pch_defines,time_macros` → 100% cacheable.

**3. ccache gets ~5% hits across build directories without `base_dir`.**
Absolute `-I` paths bake the build directory into the hash. Two build trees of
the same commit share almost nothing:

| | Hit rate | Rebuild |
|---|---:|---:|
| default | 5.4% | 79.6 s |
| `base_dir` + `hash_dir=false` | 73.3% | 22.8 s |

**4. There are seven FetchContent dependencies, not five.**
`pugixml`, `SingleApplication`, `ecm`, `kcoreaddons`, `kwidgetsaddons`,
**`Catch2`**, **`GTest`**. The last two live in `tests/*/CMakeLists.txt` and are
easy to miss. With `FETCHCONTENT_FULLY_DISCONNECTED=ON` and one dep unmapped,
the failure surfaces at *generate* time as something unrelated-looking:

```
CMake Error at tests/catch/CMakeLists.txt:107 (target_link_libraries):
  Target "C_unittests" links to: Catch2::Catch2 but the target was not found.
```

**5. clang is slower than GCC on this codebase.** Worth stating because
"switch to clang, it's faster" is common advice:

| | no PCH | with PCH |
|---|---:|---:|
| GCC 15.2 | **4.03 s** | **1.21 s** |
| clang 21 | 5.29 s | 1.44 s |

Stay on GCC. (clang's PCH is much smaller — 38 MB vs 218 MB — if disk ever
matters more than time.)

---

## 5. Caveats

**A comment-only edit is not a valid benchmark.** The preprocessor strips
comments, so ccache's preprocessor mode produces a hit and you measure 0.50 s
instead of 1.72 s. Any timing of this loop must make a real semantic change.
`scripts/qet-fastbuild.sh loop` does this correctly.

**PCH can hide missing `#include`s.** A `.cpp` that forgets `#include <QString>`
still compiles, because the PCH already provided it. That builds locally and
fails for anyone building without the PCH. This is the reason `QET_ENABLE_PCH`
should default to **OFF**: contributors and CI get the strict behaviour, and
only developers who opt in take the risk in exchange for the speed.

**`FETCHCONTENT_FULLY_DISCONNECTED=ON` pins dependencies.** Nothing will notice
a moved upstream tag. Re-run `qet-fastbuild.sh setup` after deleting the dep
cache to refresh.

---

## 6. Usage

```bash
scripts/qet-fastbuild.sh setup                     # once: install + clone deps
scripts/qet-fastbuild.sh configure ~/qet-fix bld   # ~3 s
scripts/qet-fastbuild.sh build bld
scripts/qet-fastbuild.sh loop bld                  # time the loop honestly
```

`setup` installs `ccache` and `mold` via apt, clones the seven dependencies into
`~/.cache/qet-deps`, and applies the ccache settings from §4.

The PCH block from §3.1 is **not** applied by the script — it is a source
change to QET's `CMakeLists.txt`. Without it everything else still works; you
get the configure, link and ccache wins but the per-TU compile stays at ~4 s.

---

## 7. Possible upstream contribution

The PCH block is the only piece that would need to go upstream, and it is
small: one `if(QET_ENABLE_PCH)` guard defaulting to OFF. It costs nothing when
disabled and gives a 3.4× per-file compile improvement when enabled.

Worth proposing separately, with the language-guard rationale from §4.1 in the
commit message — that detail is non-obvious and someone will otherwise
"simplify" the generator expressions away and break the C files.
