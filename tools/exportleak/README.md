# tools/exportleak — detect editing-state decoration leaking into exports

The check that would have caught upstream PR #701 before it was rejected:
that PR drew a blue halo around folio-reference arrows inside `paint()`, so
the halo also appeared in PDF/PNG/SVG exports. scorpio810's rejection was
exactly that — *"this is an editing-state indicator that has no place on a
final document meant to be printed or shared."*

This tool exports a corpus from two QET builds (baseline vs candidate) and
reports anything the candidate's export contains that the baseline's does
not. See `briefs/X5-deepseek.md`.

```bash
python3 -m tools.exportleak \
    --base-binary /path/to/master/qelectrotech \
    --candidate-binary /path/to/branch/qelectrotech \
    --corpus /home/user/qet-fix/examples \
    --out reports
```

## What it detects, and how

QET exports headlessly (`sources/cli_export.cpp`): `--export-pdf`,
`--export-png`, `--export-svg`, all through the same QPainter render path.
Anything drawn inside a QGraphicsItem's `paint()` reaches all three.

**SVG is the precise one** — it is XML, so a leaked decoration is found
textually, not by fragile image comparison:

- **tag counts** — a halo adds a new `<ellipse>`/`<path>`/`<rect>`, or grows
  an existing shape tag's count;
- **distinct colour set** — a coloured halo adds a stroke/fill colour;
- **partial opacity** — `fill-opacity`/`stroke-opacity`/`opacity < 1`, or an
  `rgba(...)` colour with alpha < 1 (halos are usually translucent).

PNG and PDF are compared only coarsely (file size, and PNG pixel count) as a
sanity check: they confirm *something changed*, but they cannot name it.

## Normalisation (criterion 3: no false positives)

The inventory never byte-compares SVG. QSvgGenerator output is not
byte-stable (ids, coordinate precision, transform matrices churn between
runs and builds), so those are *ignored by construction*: the inventory
records only tag names, colour tokens, and opacity scalars. Colours are
normalised (`#rgb` → `#rrggbb`, lowercase, `rgb(0, 0, 255)` whitespace
collapsed) so two spellings of one colour cannot produce a false diff.

## Layout

```
__main__.py    CLI + orchestration (python3 -m tools.exportleak)
export.py      run one binary over the corpus; per-project inventories
inventory.py   SVG/PNG/PDF parsing -> tag counts, colours, opacity
compare.py     baseline vs candidate diff; leak classification
report.py      reports/exportleak.{json,md}
```

## Scope

Reuses `tools/abdiff.run.run_variant` (sandbox + timeout + SingleApplication
guard) and `simulator/`. Does **not** modify QET, and is deliberately
independent of `tools/refdiff`/`tools/crosspage`.
