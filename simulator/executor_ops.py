"""
Executor for qelectrotech's --test-ops verb (qet-fix branch
feature/test-ops-cli, PR pending). This is the L1-CLI answer to the gap
SIMULATOR-DESIGN.md documents: most of the interesting bugs found this
session needed live editing (delete, rotate, undo) applied to an
in-memory Diagram, which --resave/--export-*/--info cannot drive.

Requires a binary built from a branch containing --test-ops. Binaries
without it will report "unrecognized option" or similar on stderr and a
nonzero exit -- callers should treat that as "this feature isn't in this
build" rather than "the operation failed", which is why run_ops()
surfaces the raw Outcome rather than raising.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from simulator.env import Sandbox
from simulator.proc import Outcome, run_cli


def run_ops(
    binary: str,
    project_path: Path,
    ops: list[dict[str, Any]],
    sandbox: Sandbox,
    *,
    timeout: float = 15.0,
) -> tuple[Outcome, Path, dict[str, Any] | None]:
    """
    Write `ops` as the ops.json --test-ops expects, run it against
    `project_path`, and parse the one-line JSON summary from stdout if
    present. Returns (outcome, output_project_path, summary_or_None) --
    summary is None if the process crashed/errored before printing one,
    which callers should check for rather than assume success.
    """
    ops_file = sandbox.work / "ops.json"
    ops_file.write_text(json.dumps(ops))
    output = sandbox.work / "testops_output.qet"

    outcome = run_cli(
        binary, ["--test-ops", str(project_path), str(ops_file), str(output)],
        sandbox, timeout=timeout,
    )

    summary = None
    for line in outcome.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                summary = json.loads(line)
            except json.JSONDecodeError:
                continue

    return outcome, output, summary


def first_element_uuid(project_path: Path) -> str | None:
    """
    First element uuid in a project's first diagram, via canon.py rather
    than re-parsing XML here -- keeps exactly one place in this package
    that knows the .qet schema.
    """
    from simulator import canon
    c = canon.canonicalize(project_path)
    if not c.diagrams or not c.diagrams[0]["elements"]:
        return None
    return next(iter(c.diagrams[0]["elements"]))
