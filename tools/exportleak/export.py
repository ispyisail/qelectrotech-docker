"""
Run one qelectrotech binary over the corpus and collect per-project
SVG inventories plus coarse PNG/PDF size figures.

Each run goes through tools.abdiff.run.run_variant, which wraps
simulator/env.py's sandbox + simulator/proc.py's run_cli: isolated
HOME/XDG_*, QT_QPA_PLATFORM=offscreen, no DISPLAY/WAYLAND, a hard
timeout, and a liveness guard against SingleApplication forwarding to a
stale process. That isolation is the whole game here -- the export must
describe *this* binary, never a process left running by another session.
"""
from __future__ import annotations

import time
from pathlib import Path

from tools.abdiff.run import run_variant
from tools.exportleak.inventory import png_dimensions, svg_inventory

# Retry a run that was refused because a concurrent session's qelectrotech
# was alive (SingleApplication would forward to it and every result would
# silently describe the wrong binary). Mirrors tools.refdiff's policy.
_RETRY_ATTEMPTS = 12
_RETRY_WAIT = 10.0

FORMATS = ("svg", "png", "pdf")


def _run(binary: str, args: list[str], produced_dir: Path, timeout: float) -> dict:
    """Run one export, retrying on a transient concurrent-qelectrotech refusal."""
    last = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            outcome = run_variant(binary, args, timeout=timeout, produced_dir=produced_dir)
            return {
                "returncode": outcome.returncode,
                "crashed": outcome.crashed,
                "crash_kind": outcome.crash_kind,
                "timed_out": outcome.timed_out,
                "wall_seconds": round(outcome.wall_seconds, 3),
                "stderr_tail": outcome.stderr[-800:],
            }
        except Exception as e:  # SandboxError / BuildError style transient refusal
            last = e
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_WAIT)
    assert last is not None
    raise last


def export_one(binary: str, project: Path, out_root: Path, timeout: float) -> dict:
    """Export one project to SVG/PNG/PDF and inventory the results.

    Returns a dict with the per-folio SVG inventories plus PNG/PDF totals.
    `out_root/<stem>/` is created and left in place for the caller (which
    owns its cleanup)."""
    stem = project.stem
    project_dir = out_root / stem
    project_dir.mkdir(parents=True, exist_ok=True)

    runs: dict[str, dict] = {}
    for fmt in FORMATS:
        produced = project_dir / fmt
        produced.mkdir(parents=True, exist_ok=True)
        if fmt == "pdf":
            args = ["--export-pdf", str(project), str(produced / "out.pdf")]
        else:
            args = [f"--export-{fmt}", str(project), str(produced)]
        runs[fmt] = _run(binary, args, produced, timeout)

    # SVG inventory, one entry per folio file (name -> inventory).
    folios: dict[str, dict] = {}
    svg_dir = project_dir / "svg"
    for svg in sorted(svg_dir.glob("*.svg")):
        folios[svg.stem] = svg_inventory(svg)

    # PNG: total bytes and total pixels across folios (a leaked halo changes
    # the rendered pixels, hence the encoded size).
    png_dir = project_dir / "png"
    png_files = sorted(png_dir.glob("*.png"))
    png_bytes = sum(p.stat().st_size for p in png_files)
    png_pixels = 0
    for p in png_files:
        dims = png_dimensions(p)
        if dims:
            png_pixels += dims[0] * dims[1]

    pdf_path = project_dir / "pdf" / "out.pdf"
    pdf_bytes = pdf_path.stat().st_size if pdf_path.exists() else 0

    return {
        "project": stem,
        "folios": folios,
        "svg_files": len(folios),
        "png": {"bytes": png_bytes, "pixels": png_pixels, "files": len(png_files)},
        "pdf": {"bytes": pdf_bytes, "files": 1 if pdf_path.exists() else 0},
        "export": runs,
    }
