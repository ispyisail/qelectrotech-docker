"""
auto_repro: run the implied headless CLI verb against a bugtracker project
attachment, inside an isolated sandbox, and record the evidence.

The one rule from the brief that matters here: NEVER assert "fixed". A clean
run is recorded as "not reproduced on <sha> via <exact command>", never as
"fixed". The human (stage 2) judges staleness; this module only produces the
command, exit code, and stderr verbatim.

Sandboxing is simulator/env.py's sandbox_context(): own HOME + XDG_*, offscreen
platform, no DISPLAY -- so SingleApplication cannot forward the launch to a
live instance. Every run gets a hard 120 s timeout, because a
version-incompatible project raises a modal during load and hangs every verb
forever, and bugtracker attachments are exactly where old-version projects
live.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from simulator.env import sandbox_context  # noqa: E402

from fetch import USER_AGENT  # noqa: E402

QET_BINARY = "/home/user/qet-fix/build-fast/qelectrotech"
TIMEOUT = 120.0

REPORTS_DIR = REPO_ROOT / "reports"
IN_JSON = REPORTS_DIR / "bugtracker.json"

# Output argument per flag (relative to the sandbox work dir).
_OUTPUT_ARG = {
    "--export-pdf": "out.pdf",
    "--export-png": "out_png",
    "--export-svg": "out_svg",
    "--export-cables": "out.csv",
    "--export-wires": "out.csv",
    "--export-bom": "out.csv",
    "--export-nets": "out.json",
    "--export-links": "out.csv",
    "--info": "out.json",
    "--resave": "out.qet",
    "--set-titleblock": "out.qet",
}


def implied_verb(text: str) -> str | None:
    """Pick the single CLI verb the bug text most implies (or None)."""
    t = " " + (text or "").lower() + " "
    if "dxf" in t:
        return None  # no DXF CLI verb exists
    if "print" in t or "export in pdf" in t or "pdf" in t:
        return "--export-pdf"
    if "png" in t:
        return "--export-png"
    if "svg" in t:
        return "--export-svg"
    if "bom" in t or "nomenclature" in t:
        return "--export-bom"
    if "cross reference" in t or "cross-reference" in t or " xref" in t or "xref " in t:
        return "--export-links"
    if "wire" in t or "conductor" in t:
        return "--export-wires"
    if "cable" in t:
        return "--export-cables"
    if "netlist" in t or " nets" in t:
        return "--export-nets"
    if "title block" in t or "titleblock" in t:
        return "--set-titleblock"
    if "resave" in t or "re-save" in t or "save" in t:
        return "--resave"
    return "--info"  # minimal "does it load" check


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())


def project_attachment(record: dict) -> dict | None:
    """Return the first .qet attachment (a project), else None."""
    for a in record.get("attachments", []):
        fn = (a.get("filename") or "").lower()
        if fn.endswith(".qet"):
            return a
    return None


def run_repro(binary: str, flag: str, project: Path, sandbox) -> dict:
    """Run one verb inside the sandbox and return the recorded evidence."""
    out_arg = _OUTPUT_ARG[flag]
    out_path = sandbox.work / out_arg
    argv = [binary, flag, str(project), str(out_path)]
    if flag == "--set-titleblock":
        argv.append("revision=CLI-REPRO")

    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            argv,
            cwd=str(sandbox.work),
            env=sandbox.child_env(),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        rc = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc = None
        stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    wall = round(time.monotonic() - start, 3)

    return {
        "attempted": True,
        "command": argv,
        "exit_code": rc,
        "timed_out": timed_out,
        "wall_seconds": wall,
        "stdout_tail": stdout[-4000:],
        "stderr": stderr,  # verbatim, per the brief
    }


def main() -> int:
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    bugs = data["bugs"]

    attempted = completed = 0
    for rec in bugs:
        if rec["repro_class"] != "headless":
            rec["auto_repro"] = None
            continue

        att = project_attachment(rec)
        if att is None:
            rec["auto_repro"] = {
                "attempted": False,
                "reason": "headless, but no .qet project attachment to run a verb against",
            }
            continue

        flag = implied_verb(" ".join([rec["summary"], rec["description"] or ""]))
        if flag is None:
            rec["auto_repro"] = {
                "attempted": False,
                "reason": "no headless CLI verb maps to this bug's text",
            }
            continue

        attempted += 1
        print(f"auto_repro #{rec['id']}: {flag} against {att['filename']} "
              f"(file_id={att['file_id']})", flush=True)

        with sandbox_context() as sb:
            local = sb.work / att["filename"]
            download(att["url"], local)
            result = run_repro(QET_BINARY, flag, local, sb)
            result["attachment_file_id"] = att["file_id"]
            result["attachment_filename"] = att["filename"]
            result["verb"] = flag
            rec["auto_repro"] = result
            if not result["timed_out"] and result["exit_code"] == 0:
                completed += 1
            print(f"    -> exit_code={result['exit_code']} "
                  f"timed_out={result['timed_out']} "
                  f"wall={result['wall_seconds']}s", flush=True)

    data["auto_repro_summary"] = {
        "headless_bugs": sum(1 for b in bugs if b["repro_class"] == "headless"),
        "attempted": attempted,
        "completed": completed,
    }
    IN_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nauto_repro: attempted={attempted} completed={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
