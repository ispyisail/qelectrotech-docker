#!/usr/bin/env python3
"""
tools.exportleak -- detect editing-state decoration leaking into exports.

    python3 -m tools.exportleak \
        --base-binary /path/to/master/qelectrotech \
        --candidate-binary /path/to/branch/qelectrotech \
        --corpus /home/user/qet-fix/examples \
        --out reports

Exports every corpus project to SVG/PNG/PDF from both binaries, builds a
per-folio SVG inventory (tag counts, colour set, partial-opacity features),
diffs candidate against baseline, and reports anything the candidate's
export contains that the baseline's does not.

Exit code is 1 when any leak is found, 0 otherwise. A leak is reported with
the affected project, folio, and the offending SVG feature (gained tag /
colour / partial opacity), plus the coarse PNG/PDF byte deltas.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env
from tools.exportleak import compare, export, report

DEFAULT_CORPUS = Path("/home/user/qet-fix/examples")
# examples/schema_indus.qet is project version 0.3 and raises a modal on
# load that no offscreen process can dismiss (upstream #661): it hangs
# forever, so it is excluded by default and the report says so.
DEFAULT_EXCLUDE = ["schema_indus.qet"]


def _log(msg: str) -> None:
    print(f"[exportleak] {msg}", file=sys.stderr)


def _projects(corpus: Path, excludes: list[str]) -> tuple[list[Path], list[str]]:
    if corpus.is_file():
        candidates = [corpus]
    else:
        candidates = sorted(corpus.glob("*.qet"))
    kept, dropped = [], []
    for p in candidates:
        if p.name in excludes:
            dropped.append(p.name)
        else:
            kept.append(p)
    return kept, dropped


def _run_all(binary: str, label: str, projects: list[Path], out_root: Path,
             timeout: float) -> tuple[dict[str, dict], float]:
    _log(f"exporting {len(projects)} project(s) from {label} ({binary}) ...")
    t0 = time.monotonic()
    inventories: dict[str, dict] = {}
    for i, project in enumerate(projects, 1):
        inv = export.export_one(binary, project, out_root, timeout)
        inventories[project.stem] = inv
        _log(f"  [{i}/{len(projects)}] {project.stem}: "
             f"{inv['svg_files']} folio(s), svg ok={inv['export']['svg']['returncode']}, "
             f"png ok={inv['export']['png']['returncode']}, "
             f"pdf ok={inv['export']['pdf']['returncode']} "
             f"({inv['export']['svg']['wall_seconds']:.1f}s)")
    return inventories, time.monotonic() - t0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python3 -m tools.exportleak",
        description="Detect editing-state decoration leaking into QET SVG/PNG/PDF "
                    "exports by diffing two builds' headless exports.",
    )
    ap.add_argument("--base-binary", required=True, metavar="PATH",
                    help="baseline qelectrotech binary")
    ap.add_argument("--candidate-binary", required=True, metavar="PATH",
                    help="candidate qelectrotech binary under test")
    ap.add_argument("--base-label", default="base", help="label for baseline (default 'base')")
    ap.add_argument("--candidate-label", default="candidate",
                    help="label for candidate (default 'candidate')")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                    help="directory of .qet projects, or one .qet (default %(default)s)")
    ap.add_argument("--out", type=Path, default=Path("reports"),
                    help="report dir (default ./reports)")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="per-export timeout in seconds (default 120)")
    ap.add_argument("--formats", default="svg,png,pdf",
                    help="comma list of svg,png,pdf (default all)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="project filename to exclude (repeatable)")
    ap.add_argument("--keep", action="store_true", help="keep the export scratch dir")
    return ap


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    for b in (args.base_binary, args.candidate_binary):
        if not Path(b).is_file():
            build_parser().error(f"binary not found: {b}")
    env.assert_no_other_qet_running("qelectrotech")

    projects, dropped = _projects(args.corpus, DEFAULT_EXCLUDE + args.exclude)
    if not projects:
        build_parser().error(f"no .qet projects under {args.corpus}")
    _log(f"corpus: {len(projects)} project(s) to export, {len(dropped)} excluded {dropped}")

    scratch = Path(tempfile.mkdtemp(prefix="exportleak-"))
    try:
        base_out = scratch / "base"
        cand_out = scratch / "candidate"
        base_inv, base_wall = _run_all(args.base_binary, args.base_label, projects,
                                       base_out, args.timeout)
        cand_inv, cand_wall = _run_all(args.candidate_binary, args.candidate_label,
                                       projects, cand_out, args.timeout)
    finally:
        if args.keep:
            _log(f"kept scratch dir: {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    diffs = compare.diff(base_inv, cand_inv)
    leaking = [d for d in diffs if d.get("leak")]
    leaking_folios = sum(
        1 for d in leaking for fd in d.get("folio_diffs", {}).values() if fd.get("leak")
    )

    run = {
        "meta": {
            "base": {"label": args.base_label, "binary": args.base_binary},
            "candidate": {"label": args.candidate_label, "binary": args.candidate_binary},
            "corpus": str(args.corpus),
            "formats": [f for f in args.formats.split(",") if f],
            "timeout": args.timeout,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "summary": {
            "projects": len(projects),
            "excluded": dropped,
            "leaking_projects": len(leaking),
            "leaking_folios": leaking_folios,
            "base_wall_seconds": round(base_wall, 1),
            "candidate_wall_seconds": round(cand_wall, 1),
        },
        "inventories": {"base": base_inv, "candidate": cand_inv},
        "diffs": diffs,
    }
    md, js = report.write(run, args.out)

    print(f"exportleak: {args.base_label} vs {args.candidate_label}")
    if leaking:
        print(f"  LEAK: {len(leaking)} project(s), {leaking_folios} folio(s)")
        for d in leaking:
            print(f"    - {d['project']}")
    else:
        print("  CLEAN: 0 leaks (candidate export contains nothing the baseline does not)")
    print(f"  report: {md}")
    print(f"  json:   {js}")

    return 1 if leaking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
