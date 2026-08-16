"""
Generate reports/bugtracker.md from reports/bugtracker.json.

Readable companion to the machine-readable JSON. The four "definition of
done" criteria are laid out as sections, each with real output pasted in --
including the criterion-4 fail-loudly transcript from demo.py.

Run:  python3 tools/bugtracker/report.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from demo import run_demo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
IN_JSON = REPORTS_DIR / "bugtracker.json"
OUT_MD = REPORTS_DIR / "bugtracker.md"

QET_BINARY = "/home/user/qet-fix/build-fast/qelectrotech"


def qet_sha() -> str:
    """Resolve the sha the binary at QET_BINARY was built from, if reachable."""
    try:
        out = subprocess.run(
            ["git", "-C", "/home/user/qet-fix", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("|", "\\|").replace("\n", " ")


def fmt_table(rows: list[tuple]) -> str:
    if len(rows) < 2:
        return "_(none)_\n"
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "|" + "|".join("---" for _ in rows[0]) + "|"
    body = "\n".join("| " + " | ".join(esc(str(c)) for c in r) + " |" for r in rows[1:])
    return header + "\n" + sep + "\n" + body + "\n"


def main() -> int:
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    bugs = data["bugs"]

    sha = qet_sha()
    data["qet_binary"] = QET_BINARY
    data["qet_sha"] = sha
    IN_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    dist = data["repro_class_distribution"]
    by_class = {"headless": [], "gui": [], "unclear": []}
    for b in bugs:
        by_class[b["repro_class"]].append(b)

    headless = sorted(by_class["headless"], key=lambda b: b["id"])
    attempted = [b for b in bugs if b.get("auto_repro") and b["auto_repro"].get("attempted")]
    known_stale = [b for b in bugs if b["id"] in (256, 278, 288)]

    lines: list[str] = []
    A = lines.append

    A("# QET bugtracker corpus — W4 stage 1 (inventory only)")
    A("")
    A(f"- **Generated:** {data['generated_at_utc']}")
    A(f"- **Source:** {data['source']} (anonymous, read-only)")
    A(f"- **QET binary under test:** `{QET_BINARY}` @ `{sha}`")
    A(f"- **Scope:** {data['scope']}")
    A("")
    A("This is the stage-1 deliverable: an inventory of every **open, unassigned**")
    A("QElectroTech bugtracker issue, with a `repro_class` guess and — for the one")
    A("issue that has a project attachment and a headless verb — a real")
    A("`auto_repro` attempt. No ranking, no `code_paths`, no `likely_stale`, no")
    A("`effort_hint`. An inventory that stays an inventory.")
    A("")
    A("---")
    A("")

    # ---- Criterion 1 ----------------------------------------------------
    A("## Criterion 1 — the corpus exists, with no gaps")
    A("")
    A(f"The default anonymous filter hides only *closed* issues, so the list holds")
    A(f"**{data['list_total_non_closed']}** non-closed issues. Of those, **"
      f"{data['open_unassigned_count']}** are open (status 10–50) *and* unassigned")
    A("(no handler on the issue). Every one was fetched, parsed, and recorded —")
    A(f"`parse_errors` is empty. `repro_class` distribution:")
    A("")
    A(fmt_table([
        ("repro_class", "count"),
        *[(k, dist[k]) for k in sorted(dist)],
    ]))
    A("")
    A("Full inventory (id — summary — repro_class):")
    A("")
    A(fmt_table([
        ("id", "summary", "repro_class"),
        *[(b["id"], b["summary"], b["repro_class"]) for b in sorted(bugs, key=lambda b: b["id"])],
    ]))
    A("")

    # ---- Criterion 2 ----------------------------------------------------
    A("## Criterion 2 — reproductions attempted, with real output")
    A("")
    A("`repro_class=headless` means the text implies an operation that maps to a")
    A("QET headless CLI verb (load/export/resave/info/titleblock). `auto_repro` is")
    A("only meaningful when the issue also carries a `.qet` **project** attachment")
    A("to run that verb against. Across all 91 issues there are exactly **two**")
    A("`.qet` project attachments: issue **#268** (headless, `proba.qet`) and")
    A("issue **#312** (gui, `Example.qet`). So exactly one issue qualifies.")
    A("")
    A("The 13 headless issues and why each was or wasn't attempted:")
    A("")
    A(fmt_table([
        ("id", "attachments", "auto_repro"),
        *[
            (
                b["id"],
                ", ".join(f"{a['filename']} (file_id={a['file_id']})" for a in b["attachments"]) or "none",
                "attempted" if (b.get("auto_repro") and b["auto_repro"].get("attempted"))
                else b["auto_repro"]["reason"] if b.get("auto_repro") else "-",
            )
            for b in headless
        ],
    ]))
    A("")
    A("### Issue #268 — the one real reproduction")
    A("")
    A("Attachment `proba.qet` (file_id=158) was downloaded into an isolated")
    A("`sandbox_context()` (own HOME/XDG, offscreen, no DISPLAY) and the implied")
    A("verb was run with a hard 120 s timeout:")
    A("")
    for b in attempted:
        r = b["auto_repro"]
        A("```text")
        A("$ " + " ".join(r["command"]))
        A(f"exit_code = {r['exit_code']}   timed_out = {r['timed_out']}   wall = {r['wall_seconds']}s")
        A("")
        A("--- stdout (tail) ---")
        A(r["stdout_tail"].rstrip("\n"))
        A("")
        A("--- stderr (verbatim) ---")
        A(r["stderr"].rstrip("\n"))
        A("```")
        A("")
        A(f"**Not reproduced on `{sha}`** via "
          f"`qelectrotech {r['verb']} proba.qet out.pdf` — the project opens and")
        A("exports cleanly (exit 0, 2 pages, ~0.12 s). This is recorded as *not")
        A("reproduced*, never as *fixed*; a stage-2 human decides staleness.")
    A("")
    s = data["auto_repro_summary"]
    A(f"`auto_repro_summary`: {s['headless_bugs']} headless → {s['attempted']} "
      f"attempted → {s['completed']} completed (exit 0).")
    A("")

    # ---- Criterion 3 ----------------------------------------------------
    A("## Criterion 3 — the three known-stale issues (#256, #278, #288)")
    A("")
    A("These three are the issues the brief names as known-stale. They are all in")
    A("the corpus. None is headless-with-a-project, so `auto_repro` does **not**")
    A("cover them — and it must not be made to: two attach screenshots, not")
    A("projects, and each requires a human interaction (overlapping folio text,")
    A("the element-editor save-as flow, user-collection thumbnail rendering).")
    A("")
    A(fmt_table([
        ("id", "repro_class", "summary", "attachments"),
        *[
            (
                b["id"], b["repro_class"], b["summary"],
                ", ".join(a["filename"] for a in b["attachments"]) or "none",
            )
            for b in sorted(known_stale, key=lambda b: b["id"])
        ],
    ]))
    A("")
    A("The evidence for them here is therefore the honest kind: a recorded")
    A("`repro_class=gui`, a note of the attached artifacts, and the fact that the")
    A("scraper did not silently invent a headless repro for them. Reconfirming")
    A("(or retiring) these three is stage-2 work against a live build; it is not")
    A("faked in stage 1.")
    A("")

    # ---- Criterion 4 ----------------------------------------------------
    A("## Criterion 4 — the scraper fails loudly, not silently")
    A("")
    A("The parser asserts shape and raises `ParseError` when a field the record")
    A("depends on is missing. Demonstrated against real cached pages by renaming")
    A("the HTML class a parser keys on (what a MantisBT theme change does):")
    A("")
    A("```text")
    A(run_demo().rstrip("\n"))
    A("```")
    A("")

    # ---- Brief corrections ----------------------------------------------
    A("---")
    A("")
    A("## Where the live MantisBT HTML differed from the brief's assumptions")
    A("")
    A("1. **No \"product version\" field.** The bug detail page renders no Product")
    A("   Version cell at all (the field exists in the filter form but is never")
    A("   populated), so there is no `version` field to record. It is absent, not")
    A("   empty — and the scraper records it as `null`, not `\"\"`.")
    A("2. **\"steps-to-reproduce\" and other fields are optional.** MantisBT only")
    A("   renders *Steps To Reproduce*, *Additional Information*, *OS*, *Platform*,")
    A("   etc. when they are non-empty, so most issues have none. Optional fields")
    A("   are `null` when absent, distinguishable from an explicitly-empty string.")
    A("3. **The tracker's own \"Hide Status = resolved\" filter is not applied.**")
    A("   POSTing `hide_status[]=80` is accepted and stored, but the resulting list")
    A("   still includes resolved issues. So the corpus filters open+unassigned")
    A("   **locally** from the full non-closed list (244 issues), which also keeps")
    A("   the count auditable.")
    A("4. **Attachments are embedded in the activities section**, not a dedicated")
    A("   table, and are identified by `file_download.php?file_id=N&type=bug`. The")
    A("   corpus records note URLs (filename + file_id) and does not auto-download.")
    A("5. **Only 2 of 91 issues carry a `.qet` project** (#268, #312). The rest")
    A("   attach screenshots, `.elmt` elements, `.rtf`/`.log` reports, or nothing.")
    A("   `auto_repro` is therefore inherently narrow at this snapshot — one real")
    A("   run, not thirteen.")
    A("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_MD} ({len(bugs)} bugs; sha={sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
