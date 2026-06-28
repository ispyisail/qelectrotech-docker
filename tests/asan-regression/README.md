# PR #519 targeted ASan regression tests

Small, self-contained AddressSanitizer tests that prove the four memory-leak
fixes in [PR #519](https://github.com/qelectrotech/qelectrotech-source-mirror/pull/519)
remove their leaks **without** introducing use-after-free, double-free, or
behavioural regressions.

See [`EVIDENCE.md`](EVIDENCE.md) for the write-up and results.

## Files

| file | what it tests |
|------|---------------|
| `t1_exportdialog_qdeleteall.cpp` | `~ExportDialog()` `qDeleteAll(diagram_lines_)` — the `.clear()` doubt |
| `t2_genericpanel_contract.cpp`  | `getItemForDiagram()` `nullptr` contract + all caller patterns |
| `t3_styleeditor_layout.cpp`     | parentless `QGridLayout` ownership (no orphaned layout) |
| `t4_elementscene_pastearea.cpp` | `m_paste_area` delete + `!scene()` double-free guard |
| `run.sh`     | builds each test `LEGACY` vs patched, runs under ASan, writes `report.md` |
| `lsan.supp`  | LeakSanitizer suppressions for third-party Qt/fontconfig noise |

Each `.cpp` compiles in two variants from one source: `-DLEGACY` selects the
pre-patch code, the default selects the PR #519 code. Comparing the two under
identical ASan isolates exactly what the patch changed.

## Run

```bash
# from the repo root (uses the cached qelectrotech:test image: g++, Qt5, ASan)
docker compose run --rm qet-asan-regression

# or directly
docker run --rm -v "$PWD/tests/asan-regression:/work" -w /work \
  --entrypoint bash qelectrotech:test -c 'bash run.sh'
```

Exit code is non-zero if any patched variant leaks attributable bytes or hits a
fatal ASan error. Outputs:

- `report.md` — generated summary table
- `raw/<test>_{legacy,patched}.out` — full ASan logs per run
