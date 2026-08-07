"""
The orchestrator: corpus x mutators -> qelectrotech --resave -> oracles,
with automatic Trace capture and shrinking on any finding.

Core design decision, worth stating explicitly: oracles O2/O3/O6-delta
are checked between TWO CONSECUTIVE resaves of content QET has already
accepted and rewritten (resave1 -> resave2), never between the raw
mutated seed and resave1. QET is EXPECTED to change or repair a mutated
seed on load -- that is not a violation, that is the point of feeding it
adversarial input. What must hold is that once QET has processed
something once and produced a file, processing that file again must be
stable. This mirrors exactly how the real determinism bug in master was
found and verified by hand before this runner existed (see
SIMULATOR-DESIGN.md and simulator/README.md).
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simulator import canon, env, mutate, oracles, shrink
from simulator.proc import Outcome, run_cli
from simulator.trace import Trace


@dataclass
class RunConfig:
    binary: str
    corpus_dir: Path
    reports_dir: Path
    iterations: int = 50
    chain_length: int = 1          # mutations applied per seed before the first resave
    grid: int = 10
    timeout: float = 20.0
    master_seed: int = 0
    mutator_names: list[str] = field(default_factory=lambda: list(mutate.ALL_MUTATOR_NAMES))


@dataclass
class IterationResult:
    trace: Trace
    findings: list[oracles.Finding]
    shrunk_trace: Trace | None = None

    def to_dict(self) -> dict:
        return {
            "trace": self.trace.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "shrunk_trace": self.shrunk_trace.to_dict() if self.shrunk_trace else None,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def discover_corpus(corpus_dir: Path) -> list[Path]:
    return sorted(corpus_dir.glob("*.qet"))


@dataclass
class CorpusHealth:
    healthy: list[Path]
    quarantined: dict[str, str]  # filename -> reason


def health_check_corpus(corpus: list[Path], cfg: RunConfig, base_sandbox_dir: Path) -> CorpusHealth:
    """
    Verify every seed round-trips a single --resave cleanly BEFORE it is
    used for mutation. A seed that crashes even unmutated (e.g.
    examples/schema_indus.qet, which hangs unconditionally -- see
    tests/determinism/check.py's own docstring and
    simulator/fixtures/fixture_determinism.py) tells a mutation sweep
    nothing new no matter what is done to it: every mutated variant
    inherits the same unconditional crash, so a 150-iteration sweep spends
    part of its budget re-discovering ONE already-known bug instead of
    searching for new ones. First measured for real: 7/7 crash findings
    in an early sweep traced back to that single seed file. Quarantining
    upfront is cheap and makes every subsequent iteration count.
    """
    healthy, quarantined = [], {}
    for seed in corpus:
        with env.sandbox_context(base_sandbox_dir) as sb:
            out = sb.work / "healthcheck.qet"
            outcome = run_cli(cfg.binary, ["--resave", str(seed), str(out)], sb, timeout=cfg.timeout)
        if outcome.crashed:
            quarantined[seed.name] = f"{outcome.crash_kind}: {outcome.crash_message}"
        else:
            healthy.append(seed)
    return CorpusHealth(healthy=healthy, quarantined=quarantined)


def _build_mutated_trace(seed_path: Path, seed_bytes: bytes, cfg: RunConfig, rng: random.Random) -> Trace:
    """Pick `cfg.chain_length` mutators (retrying on inapplicable ones) and
    record each as a resolved Step. Does NOT execute anything against the
    binary -- this only builds the trace."""
    trace = Trace(seed_name=seed_path.name, seed_sha256=_sha256(seed_bytes), seed=rng.getstate()[1][0])
    current = seed_bytes
    attempts_budget = cfg.chain_length * 10  # generous retry budget for inapplicable mutators
    applied = 0
    while applied < cfg.chain_length and attempts_budget > 0:
        attempts_budget -= 1
        name = rng.choice(cfg.mutator_names)
        result = mutate.apply_named(name, current, rng)
        if result is None:
            continue
        trace.append(f"mutate.{name}", result.args)
        current = result.data
        applied += 1
    return trace


def _apply_trace_to_bytes(trace: Trace, seed_bytes: bytes) -> bytes:
    """Deterministic replay of a trace's mutate.* steps against seed_bytes."""
    current = seed_bytes
    for step in trace.steps:
        if not step.op.startswith("mutate."):
            continue
        current = mutate.apply_resolved(step.args, current)
    return current


def _execute_and_check(mutated_bytes: bytes, cfg: RunConfig, sandbox: env.Sandbox) -> list[oracles.Finding]:
    """Run the resave-twice pipeline against `mutated_bytes` and return
    every Finding across O1/O2/O3/O6. This is the function both the main
    loop and the shrinker's `reproduces` predicate call."""
    findings: list[oracles.Finding] = []

    seed_file = sandbox.work / "mutated_input.qet"
    seed_file.write_bytes(mutated_bytes)

    resave1 = sandbox.work / "resave1.qet"
    outcome1 = run_cli(cfg.binary, ["--resave", str(seed_file), str(resave1)], sandbox, timeout=cfg.timeout)
    findings += oracles.o1_crash(outcome1)
    if outcome1.crashed or not resave1.exists():
        return findings  # nothing further to check -- QET never produced output to compare

    findings += oracles.o6_nan_inf(resave1)

    resave2 = sandbox.work / "resave2.qet"
    outcome2 = run_cli(cfg.binary, ["--resave", str(resave1), str(resave2)], sandbox, timeout=cfg.timeout)
    c1 = oracles.o1_crash(outcome2)
    if c1:
        findings += [oracles.Finding(f.oracle, f.severity, f"second resave: {f.message}", f.detail) for f in c1]
        return findings
    if not resave2.exists():
        return findings

    findings += oracles.o2_idempotence(resave1, resave2)
    findings += oracles.o3_semantic_preservation(resave1, resave2)
    findings += oracles.o6_grid_regression(resave1, resave2, grid=cfg.grid)

    return findings


def run_iteration(seed_path: Path, cfg: RunConfig, rng: random.Random, base_sandbox_dir: Path) -> IterationResult:
    seed_bytes = seed_path.read_bytes()
    trace = _build_mutated_trace(seed_path, seed_bytes, cfg, rng)
    mutated_bytes = _apply_trace_to_bytes(trace, seed_bytes)

    with env.sandbox_context(base_sandbox_dir) as sb:
        findings = _execute_and_check(mutated_bytes, cfg, sb)

    result = IterationResult(trace=trace, findings=findings)

    if findings and len(trace.steps) > 0:
        target_oracles = {f.oracle for f in findings}

        def reproduces(candidate: Trace) -> bool:
            candidate_bytes = _apply_trace_to_bytes(candidate, seed_bytes)
            with env.sandbox_context(base_sandbox_dir) as sb2:
                cand_findings = _execute_and_check(candidate_bytes, cfg, sb2)
            return bool({f.oracle for f in cand_findings} & target_oracles)

        if len(trace.steps) > 1:
            result.shrunk_trace = shrink.ddmin(trace, reproduces)
        else:
            result.shrunk_trace = trace  # already minimal

    return result


def run_sweep(cfg: RunConfig) -> dict[str, Any]:
    """
    Main entry point: run cfg.iterations mutation trials across the
    corpus, write every finding to a JSONL report, return a summary.
    """
    env.assert_no_other_qet_running(cfg.binary)

    all_seeds = discover_corpus(cfg.corpus_dir)
    if not all_seeds:
        raise RuntimeError(f"no .qet files found in {cfg.corpus_dir}")

    health = health_check_corpus(all_seeds, cfg, cfg.reports_dir)
    corpus = health.healthy
    if not corpus:
        raise RuntimeError(
            f"every seed in {cfg.corpus_dir} failed its health check: {health.quarantined}"
        )

    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = cfg.reports_dir / f"sweep_{int(time.time())}.jsonl"

    rng = random.Random(cfg.master_seed)
    summary = {
        "iterations": 0, "findings_by_oracle": {}, "crashes": 0,
        "report_path": str(report_path),
        "corpus_size": len(all_seeds),
        "quarantined_seeds": health.quarantined,
        # Per-mutator attempt/finding counts, independent of whether any
        # finding occurred. Without this, a sweep report only ever shows
        # mutators that produced a finding -- there is no way to tell
        # "this mutator ran 60 times and QET handled it cleanly every
        # time" apart from "this mutator never actually ran" (a real
        # selection bug). Both look identical as silence. Found the hard
        # way: truncate_bytes had zero occurrences across ~500 mutation
        # picks in every sweep run so far, which looked exactly like a
        # bug until this counter (and a standalone check) showed it is
        # selected at the expected ~1/8 rate and every truncated input is
        # cleanly rejected by QDomDocument, never a crash.
        "mutator_attempts": {name: 0 for name in cfg.mutator_names},
        "mutator_findings": {name: 0 for name in cfg.mutator_names},
    }

    with open(report_path, "w") as report_f:
        for i in range(cfg.iterations):
            seed_path = rng.choice(corpus)
            result = run_iteration(seed_path, cfg, rng, cfg.reports_dir)
            summary["iterations"] += 1

            attempted = {s.op.removeprefix("mutate.") for s in result.trace.steps}
            for name in attempted:
                summary["mutator_attempts"][name] = summary["mutator_attempts"].get(name, 0) + 1

            if result.findings:
                record = {"iteration": i, **result.to_dict()}
                report_f.write(json.dumps(record) + "\n")
                report_f.flush()
                for name in attempted:
                    summary["mutator_findings"][name] = summary["mutator_findings"].get(name, 0) + 1
                for f in result.findings:
                    summary["findings_by_oracle"][f.oracle] = summary["findings_by_oracle"].get(f.oracle, 0) + 1
                    if f.severity == "crash":
                        summary["crashes"] += 1

    return summary
