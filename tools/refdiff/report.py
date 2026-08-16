"""
Render a refdiff sweep as a dated markdown report + JSON sidecar.

The markdown is the thing a human reads the morning after; the JSON is the
machine-readable form (one key per finding, full lost/gained uuid lists, and
both variants' run summaries). Both are written by write() into the caller's
output directory.
"""
from __future__ import annotations

import json
from pathlib import Path


def render_markdown(sweep: dict) -> str:
    s = sweep["summary"]
    lines: list[str] = []
    lines.append(f"# refdiff sweep: {sweep['base_ref']} vs {sweep['head_ref']}")
    lines.append("")
    lines.append(f"- generated: {sweep['generated_at']}")
    lines.append(f"- base: `{sweep['base_ref']}` = `{sweep['base_sha'][:12]}`")
    lines.append(f"- head: `{sweep['head_ref']}` = `{sweep['head_sha'][:12]}`")
    lines.append(f"- corpus: {sweep['corpus']} ({s['projects']} project(s))")
    lines.append(f"- verbs: {' '.join(sweep['verbs'])}  (timeout {sweep['timeout']:g}s)")
    lines.append("")
    lines.append("## build")
    for label in ("base", "head"):
        b = sweep["build"][label]
        reused = " [reused]" if b["reused"] else ""
        lines.append(
            f"- {label}: {b['ref']} `{b['sha'][:12]}` "
            f"configure {b['configure_seconds']:.1f}s + build {b['build_seconds']:.1f}s{reused}"
        )
    lines.append("")
    lines.append("## summary")
    skipped = f", **{s['skipped']} skipped**" if s.get("skipped") else ""
    lines.append(
        f"- {s['comparisons']} comparisons ({s['projects']} projects x {len(sweep['verbs'])} verbs): "
        f"**{s['same']} same**, **{s['regression']} regression**, "
        f"**{s['improvement']} improvement**, **{s['change']} change**{skipped}"
    )
    lines.append("")
    if sweep["regressions"]:
        lines.append("## regressions")
        lines.append("")
        for f in sweep["regressions"]:
            lines.extend(_finding_block(f))
    else:
        lines.append("## regressions")
        lines.append("")
        lines.append("none.")
        lines.append("")

    other = [f for f in sweep["findings"] if f["category"] != "regression"]
    lines.append("")
    lines.append("## other findings (improvement / change)")
    lines.append("")
    if other:
        for f in other:
            lines.extend(_finding_block(f))
    else:
        lines.append("none.")
    lines.append("")
    return "\n".join(lines)


def _finding_block(f: dict) -> list[str]:
    lines = [f"### {f['project']} {f['verb']} — {f['category'].upper()}"]
    lines.append("")
    for r in f["reasons"]:
        for sub in r.splitlines():
            lines.append(f"  {sub}")
    lines.append("")
    if f["category"] != "skipped":
        lines.append(
            f"  base: {'CRASH(' + f['base']['crash_kind'] + ')' if f['base']['crashed'] else 'exit ' + str(f['base']['returncode'])} "
            f"({f['base']['wall_seconds']:.1f}s)  |  "
            f"head: {'CRASH(' + f['head']['crash_kind'] + ')' if f['head']['crashed'] else 'exit ' + str(f['head']['returncode'])} "
            f"({f['head']['wall_seconds']:.1f}s)"
        )
        lines.append("")
    return lines


def render_json(sweep: dict) -> str:
    return json.dumps(sweep, indent=2, ensure_ascii=False) + "\n"


def write(sweep: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "report.md"
    js = out_dir / "report.json"
    md.write_text(render_markdown(sweep), encoding="utf-8")
    js.write_text(render_json(sweep), encoding="utf-8")
    return md, js
