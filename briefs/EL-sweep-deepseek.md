# TASK BRIEF — run exportleak for real: what editing state reaches exported files?

Work in this repo. Self-contained.

## 0. HOW THIS TASK ENDS
Seven of seventeen sessions here ended by **announcing they would wait**. Two
crashed having written nothing. **Poll in a loop, commit early, paste real
output.** Log progress:
`echo "$(date +%H:%M:%S) <step>" >> /tmp/el-progress.log`

## 1. Why
`tools/exportleak/` was built to prove a planted defect could be caught (the
halo that got upstream PR #701 rejected for appearing in PDF/PNG/SVG export).
**It has never been run to find a real one.** A detector that has only ever seen
a synthetic case is unproven against reality.

Bugtracker #247 shows the class is real: a cross-reference text inherits the
palette colour, so under a dark theme it is drawn white on a white page — and
that reaches printed output.

## 2. The job
Export every example project from a clean `upstream/master` build and inspect
the SVG (it is XML, so decoration is detectable textually) for anything that
looks like **editing state rather than document content**:

- translucent fills (`fill-opacity` / `stroke-opacity` below 1)
- selection or highlight colours (blue/cyan halos, dashed selection rects)
- text whose fill is **not** black/explicit — i.e. inherited from the palette
- anything drawn only when an item is hovered, selected or "current"

Run once with a **light** palette and once with a **dark** one
(`QApplication::setPalette`, or `-platform offscreen` plus a forced style) and
**diff the two**. Anything that differs between palettes is by definition
editing state leaking into a document — that is the strongest signal available
and needs no judgement call.

## 3. Definition of done — paste real output
1. Per-project SVG inventory from a clean master build.
2. **The light-vs-dark diff**: every element whose colour depends on the
   palette, with project, folio and the SVG fragment.
3. A verdict per finding: `document content` (fine) or `editing state` (a bug),
   with the reason.
4. If nothing leaks, **say so plainly** — a clean result is a real result, and
   more useful than a strained one.

## 4. Traps
1. `examples/schema_indus.qet` hangs forever on a modal (upstream #661) —
   exclude it and say so.
2. Isolated `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME` and `-platform offscreen`
   on every run; check `docker ps` first (SingleApplication).
3. SVG ids/timestamps vary between runs — normalise before diffing and state
   exactly what you normalised.
4. **Never `git checkout`/`stash`/`reset`** in `/home/user/qet-fix`.
5. Do not modify QET source.

## 5. Scope
**May create:** `reports/exportleak-sweep.{json,md}`, small additions to
`tools/exportleak/`.
**Do NOT:** modify QET source; touch other tools; push or open a PR.

## 6. Report
All four criteria with real pasted output, and anything in this brief that was
wrong or underspecified.
