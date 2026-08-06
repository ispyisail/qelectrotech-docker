# Designation-prefix tooling for QElectroTech's element collection

Proposes `<prefix>` entries for
[`qelectrotech-elements`](https://github.com/qelectrotech/qelectrotech-elements)'
`10_electric/qet_labels.xml`, which is where QElectroTech already stores each
category's designation letter. QET reads that file in
`autonum::elementPrefixForLocation()` and exposes the result as the `%prefix`
label-formula variable, so filling it in is what actually makes elements come
out as `-K1`, `-Q2`, `-X3` rather than unlabelled.

**Output is a proposal for a human to review, never a bulk write.**

## Read this before changing the rules

The prefixes in `qet_labels.xml` follow the classic DIN 40719 / IEC 60617-era
electrical convention — **not** the abstract "inherent function" table in
IEC 81346-2:2019. The two genuinely disagree: 81346-2:2019 would classify a
sensor as `B` and a switching contact as `Q`; this project uses `P` and `S`.
It also uses `L`, `V` and `Y` (which the 2019 edition marks reserved) plus
two-letter codes `EH`, `KF`, `RB`, `YB` that a single-letter scheme has no
room for.

An earlier version of this tooling was calibrated against the 2019 table and
consequently contradicted the project's own curated data on 62% of the
categories both covered. That work was withdrawn
([qelectrotech-elements#69](https://github.com/qelectrotech/qelectrotech-elements/pull/69)).
The lesson is worth keeping: **match the project, not the edition of the
standard you happen to be reading.**

## Files

| file | purpose |
|---|---|
| `letters.json` | what each prefix means *in this project*, with the curated category evidencing it |
| `keywords.json` | phrase → prefix rules (plain data, reviewable without reading Python) |
| `classify.py` | classifies individual **elements**; writes `report.csv` |
| `classify_category.py` | classifies a **category** (folder) — what proposals are built from |
| `score.py` | scores the category classifier against `qet_labels.xml` (ground truth) |
| `propose_labels.py` | emits a patched `qet_labels.xml` + a review CSV |
| `report.csv` | committed snapshot of the per-element pass |

## The scoring gate

`qet_labels.xml`'s 50 hand-curated entries expand, via its documented
inherit-from-parent rule, to **71 categories with a known-correct answer**.
That is a labelled test set, and it is the gate:

```bash
python3 tools/iec81346/score.py \
    --labels elements-10-electric/10_electric/qet_labels.xml
```

Current: **71/71 agree, 0 disagreements.**

Run it after any edit to `keywords.json` or `letters.json`. It exits
non-zero while any curated entry is contradicted. When the tool and the
curated data disagree, **the curated entry is right and the rules are
wrong** — fix the rules, never the expected value.

The score is measured on data the rules were tuned against, so treat it as a
regression gate rather than proof of accuracy. Sample the out-of-sample
proposals too; that is how every bug listed below was actually found.

## Usage

```bash
# refresh the per-element pass (needs the collection fetched, see below)
python3 tools/iec81346/classify.py elements-10-electric/10_electric \
    --tools-dir tools/iec81346 --out tools/iec81346/report.csv

# propose prefixes for one subtree at a time
python3 tools/iec81346/propose_labels.py \
    --labels elements-10-electric/10_electric/qet_labels.xml \
    --only 10_allpole \
    --out /tmp/qet_labels.proposed.xml \
    --review-csv /tmp/review.csv
```

Fetch the collection with `docker compose run --rm qet-elements-10-electric`.

## Safety rules in the proposal generator

Mostly learned from things that went wrong:

- a category that already has its own `<prefix>` is never touched;
- a category whose subtree wants a *different* prefix is skipped — the
  curator leaves those containers blank deliberately.
  `395_electronics_semiconductors` holds resistors (R), capacitors (C),
  inductors (L) and diodes (V), so stamping any one letter on the parent
  would silently mislabel the rest;
- where a parent and its descendants all want the same prefix, only the
  parent is proposed and inheritance covers the rest — that is how the
  existing file is written (50 entries covering 71 categories);
- manufacturer brand folders (`20_manufacturers_articles/<brand>`) are never
  proposed: heterogeneous by definition, a wrong call there inherits across
  that manufacturer's whole catalogue, and brand names genuinely collide with
  device vocabulary — `phoenix_contact`, and "WAGO Contact" in WAGO's own
  `qet_directory`, both match `contact`;
- `98_graphics/99_assembly_plan` (mixed panel thumbnails) and
  `10_allpole/100_folio_referencing` (page-continuation arrows, not devices)
  are excluded outright;
- element-name votes count only when they are at least half the folder, and
  only from element *names* — never from folder or `qet_directory` text,
  since `classify.py` walks those up through every ancestor, and that is how
  the WAGO brand name reached every card beneath it.

By default only categories already listed in `qet_labels.xml` are patched, so
each change is a one-line insertion and the diff stays reviewable. Insertion
is line-oriented rather than a re-serialisation, so the rest of the file keeps
its exact formatting, and `<prefix>` is placed after child `<category>`
elements as the file's own header comment requires. (That header comment
contains example XML, which a naive line parser will happily mistake for real
nodes — the patcher skips comment blocks for exactly this reason.)

## Known limitations

- Coverage is partial by design — a category with no clear evidence is left
  alone rather than guessed.
- The `W` class is extrapolated, not evidenced in `qet_labels.xml`; treat
  those proposals as weaker than the rest.
- Categories that would need a brand-new `<category>` node are reported but
  not written. Adding them is a later step.
