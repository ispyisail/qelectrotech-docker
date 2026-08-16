#!/usr/bin/env python3
"""L6 phase 1: evidence inventory across ispyisail's QElectroTech PRs.

Reads every PR body + commit message, classifies each as one of
`observed` / `inferred` / `unstated` (see the brief's §3), and emits
`reports/pr-evidence.{json,md}`.

Two commands, so that fetching and classifying are cleanly separated:

    fetch      -- pull the PR list + every PR body/commits, caching each
                  raw response to disk BEFORE any parsing. Idempotent:
                  skips what is already cached unless --refresh.
    classify   -- read ONLY from the cache, run the classifier, write the
                  reports. No network.

The classifier is deliberately mechanical. See CLASSIFY.md (sibling) for
the exact rules; the marker counts below were verified against the
brief's calibration set (#707 inferred, #682 observed, #737 observed).

Stdlib only, Python 3.14.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent            # tools/pr-evidence
CACHE = ROOT / "cache"
REPORTS = Path(__file__).resolve().parents[2] / "reports"
REPO = "qelectrotech/qelectrotech-source-mirror"
AUTHOR = "ispyisail"

LIST_PATH = CACHE / "pr-list.json"


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

def _gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _write_raw(path: Path, raw: str) -> None:
    """Cache the raw gh stdout to disk before it is ever parsed."""
    path.write_text(raw)


def fetch_list(refresh: bool = False) -> list[dict]:
    if LIST_PATH.exists() and not refresh:
        return json.loads(LIST_PATH.read_text())
    r = _gh(["pr", "list", "--repo", REPO, "--author", AUTHOR,
             "--state", "all", "--limit", "200",
             "--json", "number,title,state"])
    if r.returncode != 0:
        print(f"gh pr list failed:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    _write_raw(LIST_PATH, r.stdout)
    return json.loads(r.stdout)


def fetch_pr(number: int, refresh: bool = False) -> dict:
    path = CACHE / f"pr-{number}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    for attempt in range(3):
        r = _gh(["pr", "view", str(number), "--repo", REPO,
                 "--json", "number,title,state,url,body,commits"])
        if r.returncode == 0:
            _write_raw(path, r.stdout)      # cache BEFORE parsing
            return json.loads(r.stdout)
        print(f"  retry {attempt + 1}/3 for PR #{number}: {r.stderr.strip()}",
              file=sys.stderr)
        subprocess.run(["sleep", "2"])
    print(f"  FAILED to fetch PR #{number}", file=sys.stderr)
    sys.exit(1)


def cmd_fetch(refresh: bool) -> None:
    prs = fetch_list(refresh)
    print(f"{len(prs)} PRs listed", file=sys.stderr)
    done = 0
    for i, pr in enumerate(sorted(prs, key=lambda p: p["number"])):
        fetch_pr(pr["number"], refresh)
        done += 1
        if (i + 1) % 20 == 0 or i + 1 == len(prs):
            print(f"  cached {done}/{len(prs)}", file=sys.stderr)
    print("fetch complete", file=sys.stderr)


# --------------------------------------------------------------------------
# classifier
# --------------------------------------------------------------------------

# A fenced block counts as runtime *output* (not a code snippet) if it
# carries one of these signatures: a backtrace frame, a key=value program
# dump, a warning/error/exit line, a sanitizer signature, a shell prompt,
# or a block of `--flag` invocations.
#
# `<-` is only a backtrace as a line-leading frame marker ("<- Foo()");
# a gdb `#N` frame number is the other backtrace form. Inline `A <- B`
# arrows are NOT used (an ASCII diagram like "Zebra <- what" or a
# `// <- note` comment would false-positive). `Value=` (Windows registry)
# is excluded by requiring a program-dump value; `# ` comments are
# excluded by keeping only the `$ ` shell prompt; bare `->` is never used
# because C++ member access would false-positive.
OUTPUT_SIGNATURES = re.compile(
    r"^[ \t]*<-[ \t]"
    r"|^[ \t]*#\d+[ \t]+\S"
    r"|\bok=(?:true|false)"
    r"|\bvalue=(?:nan|inf|-?inf|true|false|-?[0-9])"
    r"|\bisfinite=(?:true|false)"
    r"|\bwarning:|\berror:|\bexit(?:ed)?\s"
    r"|\bsegmentation fault\b|\bsigsegv\b|\bsanitizer\b"
    r"|^[ \t]*\$[ \t]"
    r"|^[ \t]*--[a-z0-9\-]+(?:[ \t]|$)",
    re.IGNORECASE | re.MULTILINE,
)

# Word units that mark a *measured result* when a number sits just before
# them. Deliberately excludes "warnings", "leaks", "%", "files", and "runs"
# so that build tallies, prose like "fixed a leak", diff-size descriptions
# like "14 files changed", and verb forms like "re-runs" never masquerade
# as runtime evidence.
WORD_UNITS = (
    r"seconds?|secs?|milliseconds?|minutes?|mins?|hours?|hrs?"
    r"|bytes?|iterations?|elements?|conductors?"
    r"|timeouts?|crashes?|hangs?|frames?|fps"
)
# Compact unit suffixes ("100ms", "21 KB") that are unambiguous. `s`
# (seconds) is handled separately because "0s"/"1s" are usually plurals of
# a digit ("stored 0s"), not timings.
COMPACT_UNITS = r"ms|kib|mib|gib|kb|mb|gb|tb"

# A measured result: a number (optionally a fraction like 48/69 or a
# decimal) followed within up to two filler words by a unit word, a
# compact unit suffix, or a compact seconds suffix (two+ digits "120s" or
# a decimal "0.3s" — so "0s" never matches). The lookbehinds stop
# "UTF-8 bytes", "#501 ... runs" (issue refs), and "every 20 minutes"
# (a design periodicity, not a measurement) from matching. "506/506"
# matches no unit, so a bare test tally is never counted on its own.
MEASURED_RE = re.compile(
    r"(?<![\w#-])(?<!every\s)"
    r"(?:\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?"
    r"(?:(?:[\s-]+[A-Za-z][\w/\-]*){0,2}[\s-]+(?:%s)\b|(?:%s)\b)"
    r"|\d{2,}s\b|\d+\.\d+s\b)"
    % (WORD_UNITS, COMPACT_UNITS),
    re.IGNORECASE,
)

# A numeric comparison ("67 vs 0", "went from 8s to") -- requires digits.
COMPARISON_RE = re.compile(
    r"(?<![\w#-])\d+\s*(?:vs\.?|versus)\s*\d+"
    r"|\b(?:went from|down to|reduced (?:from|to)|dropped (?:from|to))\s*\d",
    re.IGNORECASE,
)

# §3 "inferred" STRONG signals -- an explicit admission that verification
# was incomplete or that confidence rests on reading the source. These
# override observed markers (the brief's "torn -> inferred" rule).
ADMISSION_STRONG_RE = re.compile(
    r"attempted but not completed"
    r"|not completed"
    r"|confidence .{0,60}?rests on tracing"
    r"|rests on (?:tracing|inspection|reading)"
    r"|verified by (?:reading|inspection)"
    r"|by inspection|from inspection"
    r"|without (?:actually )?running",
    re.IGNORECASE,
)

# Weaker admissions -- non-verification notes that only matter when there
# is no observed marker at all ("did not run", "untested", ...).
ADMISSION_WEAK_RE = re.compile(
    r"\buntested\b"
    r"|did not run|didn'?t run|haven'?t run|has not been run"
    r"|not (?:actually |fully )?(?:verified|tested|run|executed)"
    r"|could not complete|couldn'?t complete"
    r"|unable to (?:fully )?verify",
    re.IGNORECASE,
)

# "Reasons from source, nothing run" language.
REASONING_RE = re.compile(
    r"should now|will now|this ensures|now ensures|ensures that"
    r"|correct by construction|by construction"
    r"|tracing the (?:exact )?(?:save-gate )?code path"
    r"|traced the (?:exact )?(?:save-gate )?code path"
    r"|the (?:gate|check|fix) is at",
    re.IGNORECASE,
)

# A claim that something was verified/tested -- but with no concrete output.
CLAIM_RE = re.compile(
    r"\b(?:verified|verification|tested|testing|confirmed|validated|"
    r"checked|reproduced|built clean|compiled clean|compiles|"
    r"builds? clean(?:ly)?|links? clean(?:ly)?|compiles? clean(?:ly)?|"
    r"passes|passed|passing|tests? pass|"
    r"works as expected|behaves as expected|behaved as expected|"
    r"no (?:new )?warnings|zero (?:new )?warnings)\b",
    re.IGNORECASE,
)


def _fenced_blocks(text: str) -> tuple[list[str], str]:
    """Return (list of fenced block bodies, text with blocks removed)."""
    blocks: list[str] = []
    parts: list[str] = []
    pos = 0
    fence_re = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
    for m in fence_re.finditer(text):
        parts.append(text[pos:m.start()])
        blocks.append(m.group(1))
        pos = m.end()
    parts.append(text[pos:])
    return blocks, "\n".join(parts)


def _sentences(text: str) -> list[str]:
    # Don't split "2.98 of 3.00" mid-number: protect digit.digit periods.
    text = re.sub(r"(?<=\d)\.(?=\d)", "\u0000", text)
    parts = re.split(r"[\n.;!?]+", text)
    return [re.sub("\u0000", ".", s).strip() for s in parts if s.strip()]


def _markers(body: str) -> tuple[int, list[str], list[str]]:
    """Count evidence markers; return (count, measured_sentences, fenced_lines).

    Markers are counted on the PR body only. The commit message is almost
    always a rewritten copy of the body in this corpus, so including it
    would double-count the same evidence.
    """
    text = body or ""
    blocks, prose = _fenced_blocks(text)

    fenced = 0
    fenced_lines: list[str] = []
    for b in blocks:
        if OUTPUT_SIGNATURES.search(b):
            fenced += 1
            first = next((ln.strip() for ln in b.splitlines() if ln.strip()), "")
            fenced_lines.append(first)

    measured = 0
    measured_sentences: list[str] = []
    for s in _sentences(prose):
        if MEASURED_RE.search(s) or COMPARISON_RE.search(s):
            measured += 1
            measured_sentences.append(s)

    return fenced + measured, measured_sentences, fenced_lines


def classify(pr: dict) -> dict:
    body = pr.get("body") or ""
    commits = pr.get("commits") or []
    text = body
    for c in commits:
        for field in ("messageHeadline", "messageBody"):
            if c.get(field):
                text += "\n" + c[field]

    markers, measured_sentences, fenced_lines = _markers(body)

    strong = bool(ADMISSION_STRONG_RE.search(text))
    weak = bool(ADMISSION_WEAK_RE.search(text))
    reasoning = bool(REASONING_RE.search(text))
    claim = bool(CLAIM_RE.search(text))

    # Quotes come from the body (the canonical record); fall back to commit
    # text only if the body has no matching sentence.
    qtext = body if body else text

    if markers >= 1 and not strong:
        cls = "observed"
        quotes = (measured_sentences[:3] or fenced_lines[:3])
    elif strong or weak or (markers == 0 and (reasoning or claim)):
        cls = "inferred"
        # Quote the strongest justifier first: strong admission > weak
        # admission > reasoning > claim.
        quotes: list[str] = []
        for s in _sentences(qtext):
            if len(quotes) >= 3:
                break
            if strong and ADMISSION_STRONG_RE.search(s) and s not in quotes:
                quotes.append(s)
        if len(quotes) < 3:
            for s in _sentences(text):
                if len(quotes) >= 3:
                    break
                if weak and ADMISSION_WEAK_RE.search(s) and s not in quotes:
                    quotes.append(s)
        if len(quotes) < 3:
            for s in _sentences(text):
                if len(quotes) >= 3:
                    break
                if reasoning and REASONING_RE.search(s) and s not in quotes:
                    quotes.append(s)
        if len(quotes) < 3:
            for s in _sentences(text):
                if len(quotes) >= 3:
                    break
                if claim and CLAIM_RE.search(s) and s not in quotes:
                    quotes.append(s)
    else:
        cls = "unstated"
        quotes = []

    title = (pr.get("title") or "").strip()
    return {
        "number": pr.get("number"),
        "title": title,
        "state": pr.get("state"),
        "evidence_class": cls,
        "evidence_markers": markers,
        "quotes": [_clip(q) for q in quotes[:3]],
        "claim": title or _clip(body),
    }


def _clip(s: str, n: int = 200) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def cmd_classify(only: str | None) -> None:
    prs = fetch_list(refresh=False)
    if only:
        wanted = {int(x) for x in only.split(",") if x.strip()}
        prs = [p for p in prs if p["number"] in wanted]

    results: list[dict] = []
    for p in sorted(prs, key=lambda p: p["number"]):
        full = fetch_pr(p["number"], refresh=False)
        results.append(classify(full))

    dist = {"observed": 0, "inferred": 0, "unstated": 0}
    for r in results:
        dist[r["evidence_class"]] += 1

    out = {
        "repo": REPO,
        "author": AUTHOR,
        "corpus_size": len(results),
        "distribution": dist,
        "prs": results,
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "pr-evidence.json").write_text(
        json.dumps(out, indent=2) + "\n")
    (REPORTS / "pr-evidence.md").write_text(_render_md(out))
    print(f"wrote {REPORTS / 'pr-evidence.json'} and .md "
          f"({len(results)} PRs) distribution={dist}", file=sys.stderr)


def _render_md(out: dict) -> str:
    dist = out["distribution"]
    lines = [
        "# PR evidence inventory — L6 phase 1",
        "",
        f"Repo `{out['repo']}`, author `{out['author']}`, "
        f"corpus {out['corpus_size']} PRs.",
        "",
        "## Distribution",
        "",
        f"- observed: **{dist['observed']}**",
        f"- inferred: **{dist['inferred']}**",
        f"- unstated: **{dist['unstated']}**",
        "",
        "Classes follow the brief §3: `observed` = pasted output / measured "
        "values / before-after numbers present; `inferred` = reasoning from "
        "source or a verification claim with nothing run (incl. an explicit "
        "\"attempted but not completed\" admission); `unstated` = what changed "
        "only, no verification claim either way.",
        "",
        "| # | State | Class | Markers | Claim |",
        "|---|---|---|---|---|",
    ]
    for r in out["prs"]:
        claim = r["claim"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r['number']} | {r['state']} | {r['evidence_class']} "
            f"| {r['evidence_markers']} | {claim} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="cache PR list + bodies to disk")
    f.add_argument("--refresh", action="store_true",
                   help="re-fetch even if cached")
    c = sub.add_parser("classify", help="classify from cache, write reports")
    c.add_argument("--only", metavar="707,682,737",
                   help="classify only these PR numbers (calibration)")
    a = ap.parse_args()
    if a.cmd == "fetch":
        cmd_fetch(a.refresh)
    else:
        cmd_classify(getattr(a, "only", None))


if __name__ == "__main__":
    main()
