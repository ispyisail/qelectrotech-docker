# PR #519 — Memory-leak fixes: regression evidence

**Question this answers:** do the four fixes in
[PR #519](https://github.com/qelectrotech/qelectrotech-source-mirror/pull/519)
break anything? Specifically the two doubts raised in review:

1. **`qDeleteAll(diagram_lines_)`** in `~ExportDialog()` — *"qDeleteAll leaves
   the container full of dangling pointers, don't we need `.clear()` to avoid
   crashes?"* (plc-user, `sources/exportdialog.cpp:115`)
2. **`getItemForDiagram()`** logic — *"Don't we change the logic with these
   modifications?"* (plc-user, `sources/genericpanel.cpp:328`)

That the leaks shrink is already confirmed (scorpio810's manual ASan runs,
603 KB → 67 KB). What was untested is **safety**: no use-after-free, no
double-free, no behavioural regression. The upstream `tests/` tree is a
skeleton (`tst_My_test.cpp` stubs) and exercises none of the four changed
files, so this adds targeted tests that do.

## Method

For each fix, one source file is compiled in **two variants** from the same
code via a `-DLEGACY` switch:

| variant | code path |
|---------|-----------|
| `LEGACY` | the **pre-patch** code |
| patched | the **PR #519** code |

Both run under **AddressSanitizer + LeakSanitizer** (Qt `offscreen` platform).
Each test replicates the *exact* ownership/lifetime pattern of the real class
(parent-child reparenting, cache + `makeItem`, layout install order, scene
add/remove). "Leak (ours)" counts only leak blocks whose stack references the
test source, so third-party Qt allocation noise is excluded.

The `LEGACY` column proves the test genuinely reproduces the bug; the patched
column proves the fix removes it **and** introduces no fatal memory error.

## Results

| Test | Fix | LEGACY leak | PATCHED leak | Fixed | Fatal errors (patched) |
|------|-----|-----------:|------------:|------:|------------------------|
| t1 | `ExportDialog` — `qDeleteAll` in dtor | 960 B | **0 B** | 960 B | none |
| t2 | `GenericPanel::getItemForDiagram` contract | 128 B | **0 B** | 128 B | none |
| t3 | `StyleEditor` — parentless `QGridLayout` | 160 B | **0 B** | 160 B | none |
| t4 | `ElementScene::m_paste_area` + double-free guard | 80 B | **0 B** | 80 B | none |

**Verdict: PASS.** Every fix eliminates exactly its own leak, leaves zero
attributable leaks, and produces no use-after-free, double-free, or SEGV.
(t2's patched run is *fully* ASan-clean — not even Qt platform noise.)

## Addressing the two doubts directly

### Doubt 1 — `qDeleteAll` without `.clear()` (t1)

`t1` reproduces the real structure: `ExportDialog` owns
`QHash<int, ExportDiagramLine*>`; each line's child widgets are reparented to a
dialog-owned container (Qt owns them), and `~ExportDiagramLine()` is empty.
`~ExportDialog()` calls `qDeleteAll` with no `.clear()`.

Running 5 build/destroy cycles under ASan: **no use-after-free, no double-free,
no leak.** The `.clear()` is unnecessary because `qDeleteAll` is the **last
statement of the destructor** — the `QHash` member is destroyed immediately
afterwards and only frees its internal node storage; it never dereferences the
(now-dangling) pointer values. The Qt-docs `.clear()` advice applies to a
container that is **reused** after `qDeleteAll`, which a destructor never does.
Adding `.clear()` would be harmless but buys nothing.

### Doubt 2 — `getItemForDiagram` logic change (t2)

The patch changes one contract: the no-`created`-argument overload, for an
**uncached** diagram, now returns `nullptr` instead of a freshly-allocated,
**parentless, unregistered** `QTreeWidgetItem` that the caller immediately
leaks. `t2` transcribes the function verbatim and checks every real caller
pattern:

- **`addDiagram()` path** (always passes `&created`): unchanged — item created,
  `created==true`, registered. *(regression guard — passes)*
- **cached lookup, no `created` arg**: unchanged — returns the cached item.
  *(regression guard — passes)*
- **uncached, no `created` arg, behind `if (item)`**: LEGACY returns an orphan
  the caller leaks (128 B); patched returns `nullptr`, the guard skips, no leak,
  no crash.

Every real call site of the no-`created` overload already null-guards the
result, so the new `nullptr` return is safe:

| call site | guard |
|-----------|-------|
| `sources/qetdiagrameditor.cpp:1857` | `if (item) … setCurrentItem(item)` |
| `sources/qetdiagrameditor.cpp:1870` | `if (item) … setCurrentItem(item)` |
| `sources/elementspanelwidget.cpp:273,290,307,324,341,358,375` | `if (auto item = …) item->setSelected(true)` |
| `sources/genericpanel.cpp` `addDiagram()` | passes `&creation_required` (non-null) → early return never taken |

The behaviour change is therefore both **safe** (no caller can crash) and
**strictly better** (the old return value was an unusable item that was always
leaked).

## Reproduce

```bash
# from the repo root
docker compose run --rm qet-asan-regression
# or directly:
docker run --rm -v "$PWD/tests/asan-regression:/work" -w /work \
  --entrypoint bash qelectrotech:test -c 'bash run.sh'
```

Raw ASan logs land in `tests/asan-regression/raw/<test>_{legacy,patched}.out`;
the machine-generated summary is `report.md`.
