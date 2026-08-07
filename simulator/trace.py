"""
Traces: the serialisable, replayable record of what the simulator did.

Design note (see SIMULATOR-DESIGN.md §4.1): a trace of prose ("clicked
button 41, seed 12345") is not a bug report. A trace here is a list of
Step records with fully RESOLVED arguments -- the actual byte offset
flipped, the actual attribute dropped -- so that replaying a trace
reproduces a failure without re-running the RNG. Every mutator in
mutate.py returns resolved Steps for exactly this reason.

A Trace is a chain: each Step is applied to the file *produced by the
previous step*, using the qelectrotech --resave CLI as the "commit"
point that turns a mutated/loaded state back into an XML file to hand
to the next step (or to an oracle).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Step:
    """One resolved, replayable action against a project file."""

    seq: int
    op: str                    # e.g. "mutate.bitflip", "mutate.drop_attr", "cli.resave"
    args: dict[str, Any]       # fully resolved -- no "random", no "pick one"
    note: str = ""

    def to_dict(self) -> dict:
        return {"seq": self.seq, "op": self.op, "args": self.args, "note": self.note}

    @staticmethod
    def from_dict(d: dict) -> "Step":
        return Step(seq=d["seq"], op=d["op"], args=d["args"], note=d.get("note", ""))


@dataclass
class Trace:
    """A full, replayable scenario: a seed file plus an ordered Step list."""

    seed_name: str
    seed_sha256: str
    seed: int                  # RNG seed used to GENERATE this trace (0 if hand-written)
    steps: list[Step] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def append(self, op: str, args: dict, note: str = "") -> Step:
        step = Step(seq=len(self.steps), op=op, args=args, note=note)
        self.steps.append(step)
        return step

    def to_dict(self) -> dict:
        return {
            "seed_name": self.seed_name,
            "seed_sha256": self.seed_sha256,
            "seed": self.seed,
            "created_at": self.created_at,
            "meta": self.meta,
            "steps": [s.to_dict() for s in self.steps],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False))

    @staticmethod
    def load(path: Path) -> "Trace":
        d = json.loads(Path(path).read_text())
        t = Trace(
            seed_name=d["seed_name"],
            seed_sha256=d["seed_sha256"],
            seed=d["seed"],
            created_at=d.get("created_at", 0.0),
            meta=d.get("meta", {}),
        )
        t.steps = [Step.from_dict(s) for s in d["steps"]]
        return t

    def sub_trace(self, indices: list[int]) -> "Trace":
        """A copy containing only the steps at `indices`, renumbered. Used by shrink.py."""
        t = Trace(
            seed_name=self.seed_name, seed_sha256=self.seed_sha256,
            seed=self.seed, meta=dict(self.meta, shrunk_from=len(self.steps)),
        )
        for new_seq, i in enumerate(indices):
            old = self.steps[i]
            t.steps.append(Step(seq=new_seq, op=old.op, args=old.args, note=old.note))
        return t
