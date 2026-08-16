# qet-lint

Dependency-free static checker for QElectroTech project (`.qet`) and element
(`.elmt`) files. No build, no launch, no GUI — pure file analysis, seconds
over the whole corpus.

```bash
python3 tools/qet-lint/__main__.py [--format text|json] \
    [--baseline FILE] [--write-baseline] [--include-info] PATHS...
```

`PATHS` may be files or directories (directories are walked for `*.qet` and
`*.elmt`). Exit code is 0 when there is nothing new to act on; any regression
against the baseline (or any finding when there is no baseline) exits 1.

## The five rules (stage 1)

| ID | Check | Severity |
|---|---|---|
| P001 | any coordinate attribute is NaN or Inf | error |
| P002 | illegal XML 1.0 control character anywhere in a `.qet` | error |
| P003 | duplicate `uuid` value within one project | error |
| E001 | `.elmt` does not parse as XML (ElementTree) | error |
| E002 | illegal XML 1.0 control character in an `.elmt` | error |

P001 is not reimplemented here: it calls
`simulator/canon.py::nan_or_inf_violations()` and only attaches a source line
to each finding. P002 and E002 are the same byte scanner applied to the two
file kinds. P003 reuses the uuid extraction canonicalize() uses to build
`uuid_universe` (a `root.iter()` scan of `uuid` attributes) — see the note
below on why it is scoped to `<element>` uuids.

### What "illegal control character" covers (P002/E002)

XML 1.0 forbids U+0000–0008, U+000B, U+000C and U+000E–001F (U+0009 tab,
U+000A LF, U+000D CR are the only legal ASCII controls). The scanner flags
both ways one of those code points can reach the file:

1. a **raw control byte** (e.g. `0x00`), which ElementTree rejects as "not
   well-formed";
2. a **numeric character reference** (`&#11;` / `&#x0B;`), which ElementTree
   rejects as "reference to invalid character number" and which
   **segfaults Qt's `QDomDocument::setContent()`** rather than erroring.

The brief describes P002's implementation as a "raw byte scan". A raw byte
scan alone cannot see form 2 (the file holds the six ASCII characters
`&#11;`, not a `0x0B` byte) — and form 2 is exactly what the criterion-1
fixture `xpx.elmt` contains. So the scanner handles both. That contrast —
"Python rejects it cleanly, Qt segfaults" — is the finding the fixture
exists to demonstrate.

## Hand-verification (brief §5: a rule nobody checked is worse than no rule)

Every rule that fires was checked by opening the file, not by trusting the
count.

### P001 — 1 instance (all of them)

`simulator/reports/findings/nan_coordinate_hang_grafcet.qet:93`:

```xml
<element freezeLabel="false" z="10" y="170" x="nan" prefix=""
        type="embed://import/grafcet2/etape.elmt" orientation="0"
        uuid="{12113ca8-85f5-4358-8548-fe386fa41760}">
```

A literal `x="nan"` on an `<element>`. Real. (This is the one project in the
known-bad set; the 23 example projects are clean, matching canon.py's note
that no real un-corrupted project should ever contain one.)

### P002 — 1 instance (all of them)

`simulator/reports/findings/nul_byte_segv_cablage.qet:616`: a raw `0x00` at
byte offset 51565. ElementTree rejects the file with "not well-formed
(invalid token): line 616, column 13", matching the reported line. Real.

### P003 — scoped to `<element>` uuids, 0 findings on the corpus

The brief points P003 at canonicalize's `uuid_universe`, which collects
**every** `uuid` attribute in the document. Counting occurrences over that
full universe and flagging any repeat produces a ~500-violation flood across
18 of the 23 known-good example projects. Three hand-verified samples of
that flood, all in files QET loads and renders correctly:

1. `perceuse.qet` — `<dynamic_elmt_text uuid="{9bfe240c-…}">` **×30**, all at
   the same relative position `x="-8" y="12"`: thirty instances of the same
   element sharing the element *definition's* text uuid. (QET's current
   source regenerates this uuid per instance — `element.cpp` "the uuid is
   the uuid of the description and not the uuid of instantiated dynamic text
   field" — but these files predate that fix.)
2. `perceuse.qet` — `<dynamic_text uuid="{d7645379-…}">` **×167** at many
   different positions: a folio's title-block texts, duplicated when the
   folio was duplicated.
3. `ShellyParts.qet` — `<terminal uuid="{455839e4-…}">` **×8** with different
   names (`SW`, `O1`, `L`, `GND`, `12V`, `O2`, …): terminal uuids copied
   across element instances.

None of these is "two objects sharing one identity"; they are QET's
copy-on-instantiate behaviour. Flagging them as `error` would be exactly the
false-positive flood §5 warns about, so P003 flags only the uuid that *is* a
strict identity — the `<element>` uuid, which QET resolves conductors
(via terminal uuid), cross-folio links (`link_uuid`) and undo/redo by, and
which is unique across all 23 example projects (0 duplicates). A duplicate
here is real corruption and will fail the gate.

*(Separately observed, not a rule: `cablage-eclairages_sikli-v5.qet` embeds
two `<definition>` blocks with the same `<uuid>` child but different content
— a genuine definition-uuid collision. Out of stage-1 scope; worth a stage-2
rule.)*

### E001 — 2 instances (all of them)

The brief says "~5 known-bad files, all in `<name lang="ca">`". The current
collection yields **2**, not 5; reported as-is, not tuned to a target.

1. `…/johnson_controls/dx/modules_extension/xpx.elmt:4` — `reference to
   invalid character number`, from `<name lang="ca">Unitat xPx &#11;erge</name>`.
2. `…/91_en_60617/en_60617_06/en_60617_06_04/en_60617_06_04_01.elmt:37` —
   `mismatched tag`, from a `<name lang="ca">` entry whose raw content is
   unclosed and embeds a `<name lang="cs">…</name>`.

Both are in `<name lang="ca">` translation content, as the brief describes;
there are just two of them now.

### E002 — 1 instance (all of them)

`xpx.elmt:4` — `&#11;` (U+000B) inside `<name lang="ca">`. Same byte the
E001 row above points at; E001 says "Python rejects it", E002 says "here is
the illegal character that made it so".

## Baseline

`--write-baseline` records `{path: {rule: count}}` (same shape as
`tests/determinism/baseline.json`, with a count instead of a bool):

```bash
python3 tools/qet-lint/__main__.py --baseline baseline.json --write-baseline \
    /home/user/qet-fix/examples \
    /home/user/qelectrotech-docker/elements-10-electric/10_electric \
    simulator/reports/findings

python3 tools/qet-lint/__main__.py --baseline baseline.json \
    /home/user/qet-fix/examples \
    /home/user/qelectrotech-docker/elements-10-electric/10_electric \
    simulator/reports/findings      # exit 0: no regressions
```

A run compares against the baseline and fails only on **regressions** — a
(file, rule) whose count went up or is brand new. The inverse is reported as
"vanished (fixed, or a rule stopped firing)" so a rule silently breaking is
visible, not hidden: if P001 fires N times yesterday and zero today, that
shows up as N vanished violations rather than a green run.

## Tests

```bash
python3 -m unittest discover -s tools/qet-lint/tests -v
```

Hermetic — the fixtures are synthetic, so the tests pass without the QET
element collection or example projects present.
