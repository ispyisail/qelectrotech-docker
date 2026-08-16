"""Corpus-wide differential regression sweep for QElectroTech (W3).

A thin sweep layer over the existing two-ref harness (`tools/abdiff`,
wrapped by `scripts/qet-ab.sh`). That harness already resolves two refs,
builds each into a per-sha worktree/build tree, runs one command in an
isolated `simulator/env.py` sandbox per variant, and classifies the result
semantically. This package's only job is to run it over a whole corpus of
`.qet` projects and five CLI verbs, then classify each difference as
`regression` / `improvement` / `change` and write a dated report.

See `tools/refdiff/README.md` and TOOLING-PLAN.md W3.
"""
