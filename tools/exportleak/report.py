"""
Render an exportleak run to reports/exportleak.{json,md}.

The JSON is the machine-readable record (full inventories + diffs); the
markdown is the human-readable form: meta, the baseline per-project SVG
inventory (tag counts + colour set), the leak findings (project, folio,
offending feature), and the coarse PNG/PDF deltas.
"""
from __future__ import annotations

import json
from pathlib import Path


def _colour_set(colours: list[str], limit: int = 24) -> str:
    if not colours:
        return "(none)"
    shown = ", ".join(colours[:limit])
    if len(colours) > limit:
        shown += f", … (+{len(colours) - limit} more)"
    return shown


def _write_md(run: dict) -> str:
    meta = run["meta"]
    summary = run["summary"]
    diffs = run["diffs"]
    base_inv = run["inventories"]["base"]
    cand_inv = run["inventories"]["candidate"]

    lines: list[str] = []
    lines.append("# exportleak — editing-state decoration leaking into exports")
    lines.append("")
    lines.append("## Meta")
    lines.append("")
    lines.append(f"- baseline : `{meta['base']['label']}` — {meta['base']['binary']}")
    lines.append(f"- candidate: `{meta['candidate']['label']}` — {meta['candidate']['binary']}")
    lines.append(f"- corpus   : {meta['corpus']} ({summary['projects']} project(s) exported, "
                 f"{summary['excluded']} excluded)")
    lines.append(f"- formats  : {', '.join(meta['formats'])}")
    lines.append(f"- timeout  : {meta['timeout']}s / project")
    lines.append(f"- generated: {meta['generated_at']}")
    lines.append(f"- wall-clock (candidate export): {summary['candidate_wall_seconds']:.1f}s")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    if summary["leaking_projects"]:
        lines.append(f"**LEAK** — {summary['leaking_projects']} project(s) leak "
                     f"({summary['leaking_folios']} folio(s)). "
                     f"Exit code will be non-zero.")
    else:
        lines.append("**CLEAN** — zero leaks (candidate export contains nothing the "
                     "baseline does not).")
    lines.append("")

    lines.append("## Baseline SVG inventory (per project)")
    lines.append("")
    lines.append("| project | folios | shapes | tag counts (top) | distinct colours |")
    lines.append("|---|---|---|---|---|")
    for stem in sorted(base_inv):
        inv = base_inv[stem]
        folios = inv.get("folios", {})
        tags: dict[str, int] = {}
        colours: set[str] = set()
        shapes = 0
        for f in folios.values():
            for t, n in f.get("tags", {}).items():
                tags[t] = tags.get(t, 0) + n
            colours.update(f.get("colours", []))
            shapes += f.get("shape_count", 0)
        top_tags = ", ".join(f"{t}×{n}" for t, n in sorted(tags.items(), key=lambda kv: -kv[1])[:6])
        lines.append(f"| `{stem}` | {len(folios)} | {shapes} | {top_tags} | "
                     f"{_colour_set(sorted(colours))} |")
    lines.append("")

    if summary["leaking_projects"]:
        lines.append("## Leaks found (candidate has, baseline does not)")
        lines.append("")
        for d in diffs:
            if not d.get("leak"):
                continue
            stem = d["project"]
            lines.append(f"### `{stem}`")
            lines.append("")
            for folio, fd in d.get("folio_diffs", {}).items():
                if not fd.get("leak"):
                    continue
                bits = []
                if fd.get("tags_gained"):
                    bits.append("gained tags: " + ", ".join(
                        f"{t} ×{n}" for t, n in sorted(fd["tags_gained"].items())))
                if fd.get("colours_gained"):
                    bits.append("gained colours: " + ", ".join(fd["colours_gained"]))
                if fd.get("opacity_gained"):
                    bits.append("gained partial opacity: " + ", ".join(fd["opacity_gained"]))
                lines.append(f"- folio `{folio}`: " + "; ".join(bits))
            if d.get("png_bytes_delta") or d.get("png_pixel_delta") or d.get("pdf_bytes_delta"):
                lines.append(f"- PNG Δ {d['png_bytes_delta']:+d} bytes "
                             f"({d['png_pixel_delta']:+d} px), "
                             f"PDF Δ {d['pdf_bytes_delta']:+d} bytes")
            lines.append("")

        lines.append("## Coarse format deltas (all projects)")
        lines.append("")
        lines.append("| project | PNG Δbytes | PNG Δpixels | PDF Δbytes |")
        lines.append("|---|---|---|---|")
        for d in diffs:
            if d.get("missing_on"):
                lines.append(f"| `{d['project']}` | missing on {d['missing_on']} |||")
                continue
            lines.append(f"| `{d['project']}` | {d['png_bytes_delta']:+d} "
                         f"| {d['png_pixel_delta']:+d} | {d['pdf_bytes_delta']:+d} |")
        lines.append("")
    else:
        lines.append("## Coarse format deltas")
        lines.append("")
        lines.append("Zero leaks, so every PNG/PDF delta below is zero (identical build "
                     "exported twice).")
        lines.append("")

    return "\n".join(lines)


def write(run: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "exportleak.json"
    md = out_dir / "exportleak.md"
    js.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n")
    md.write_text(_write_md(run) + "\n")
    return md, js
