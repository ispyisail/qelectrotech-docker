---
name: qet-bughunt
description: Hunt for new QElectroTech defects with the sweep tooling, cheapest tool first. Load when asked to find bugs, look for problems, run the fuzzer or sweeps, decide what to work on next, or check the health of the element collection.
---

# Hunting QET bugs

Load `qet-env` first. Run these in order of cost and stop when there is enough
to work on. Measured yields are from this project's own history.

| Tool | Cost | Finds | Proven yield |
|---|---|---|---|
| `scripts/cli-sweep.sh` | ~15 min, no build | hangs/crashes in headless paths | 2 bugs (PR #737, elements #71) |
| `python3 -m simulator sweep` | ~30 min | malformed-input crashes, save corruption | 2 bugs (PR #682) |
| `tools/qet-lint` | seconds | semantic defects over 6,918 elements | not built yet — `TOOLING-PLAN.md` W2 |
| bugtracker triage | one-off | 75 untouched bugs, ranked | not built yet — W4 |
| `qet-fuzz-asan` | hours, unattended | GUI-only memory bugs | crash fixes #711, #713 |

## The cheap sweep

Every example project × every CLI verb, 120 s timeout, offscreen. Records exit
code, wall time, timeout flag, peak RSS and fd count.

```bash
scripts/cli-sweep.sh
```

RSS and fd sampling is the fastest way to *kill* a hypothesis: flat numbers
across a run rule out resource exhaustion in one minute.

## The mutation sweep

```bash
python3 -m simulator sweep --binary <path> --corpus <warmed-corpus> --iterations 50
python3 -m simulator replay --binary <path> --trace <trace.json>
python3 -m simulator selftest        # no binary needed; keep green
```

- **Warm the corpus first** (`warm-corpus` subcommand). Legacy projects invent
  conductor UUIDs on their first save, which trips the O9 determinism
  self-check and makes every other finding uninterpretable.
- Traces record byte offsets, so a trace replays only against the corpus it was
  recorded from. Do not overwrite the original `examples/`.
- If `o9_self_check` fails, **stop** — the harness is unreliable and no finding
  from that run can be trusted.

## Unattended fuzzing

```bash
FUZZER_HOURS=8 FUZZER_SPEED=fast docker compose run --rm qet-fuzz-asan
FUZZER_SELF_TEST=1 docker compose run --rm qet-fuzz    # verify the rig first
```

Logs go to host-mounted `fuzzer-asan-logs/`. `analyze.py` turns `crashes.jsonl`
into a report.

## Judging what you find

Most sweep output is not a bug. Before reporting anything:

1. **Reproduce it 3×.** Single-occurrence findings from a fuzzer are usually
   environmental.
2. **Check it against a control binary** where the defect should be absent. A
   finding that survives the control is a false positive in the tool.
3. **Check it is not a known artifact** — first-save UUID churn, the
   `--export-wires` empty-result exit 1, the `Diagram::toXml` stacking-order
   non-idempotence. All three look like bugs and are already understood.
4. **Minimise the input** (see `qet-repro`).

## Where findings go

`FINDINGS.md` at the repo root: exact repro command, binary sha, input file,
expected vs actual, whether it is known upstream. A finding that exists only
inside `reports/*.jsonl` has not been reported.

**Do not open PRs or post to the bugtracker without being asked.**

## Do not build GUI automation

`scenarios/` is finished work kept as fixtures. It cost ~3,500 lines and found
zero QET defects; the file-level tools of comparable size found four. If a
check seems to need a window, push it down to the file layer instead. The
reasoning is in `SIMULATOR-DESIGN.md` and `TOOLING-PLAN.md`.
