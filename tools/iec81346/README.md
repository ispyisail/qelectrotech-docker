# IEC 81346-2 classification tooling

Supports discussion [#666](https://github.com/qelectrotech/qelectrotech-source-mirror/discussions/666)
(auto-derive a device's IEC 81346-2 classification letter from its element
category). Phase 1 per that discussion's proposed scope: build the reference
data + a reviewable, re-runnable matching tool, seed it, and let coverage
grow rather than trying to classify all ~6900 elements by hand in one pass.

## Files

- **`letters.json`** — IEC 81346-2:2019 Table 1 (the 17 used entry-class
  letters), obtained legally from IEC's own free preview sample of the
  current standard, plus our own `common_examples` applying each definition
  to real device types.
- **`keywords.json`** — the actual matching rules `classify.py` uses:
  bilingual (EN/FR) phrase → class-code pairs. Plain data, not code — edit
  this to fix or extend coverage without touching the script.
- **`classify.py`** — walks a QET elements tree, extracts each element's
  English name (falling back to French, then the filename), and matches it
  against `keywords.json`. Longest phrase wins, so a specific match
  ("circuit breaker") always beats a shorter, more ambiguous one ("switch").
  No match is left unmatched, never guessed.
- **`report.csv`** — a run against the full `10_electric` tree (6918
  elements, fetched via the `qet-elements-10-electric` compose service),
  committed as a snapshot/starting point, not a live source of truth.

## Read this before trusting `letters.json`'s "K = relay" instincts

The current (2019, Edition 2.0) standard is **not** the familiar
K=relay/Q=breaker/S=switch folklore. It classifies by abstract *inherent
function* — e.g. K is officially "object for treating input signals and
providing an appropriate output" (information processing object), not
"the relay letter." A relay lands there because processing a signal is
what it does, not because the standard says so by name. The standard's own
text is explicit about this: *"Users should select the appropriate class
... based on the definition, and not rely upon the class name or the
examples."*

`letters.json`'s `official_definition`/`official_class_name` fields are
sourced from the real Table 1. Its `common_examples`, and everything in
`keywords.json`, are our own interpretation applying those definitions to
real device names — reasonable, but a judgment call, not a verbatim
standard quote. `keywords.json` is where to push back on a call you
disagree with.

## Running it

```bash
python3 classify.py /path/to/10_electric --out report.csv
```

Re-fetch `10_electric` first if you want current data:
`docker compose run --rm qet-elements-10-electric` (from the repo root) --
writes to `../elements-10-electric/`.

## Current coverage (last run: 6918 elements)

27.4% matched (1897), 72.6% unmatched. Unmatched is dominated by two honest
gaps rather than bugs:

- **Manufacturer catalog parts** with no descriptive name at all (e.g. Siemens
  `6ES7...` module codes) — nothing in the name to match against. Fixing
  this needs a different signal (category-folder context, Phase 3 in the
  discussion), not better keywords.
- **Generic/administrative words** (module, type, reference, general,
  wiring...) that aren't classification signals on their own, correctly
  left alone rather than force-matched.

Spot-checked a random sample across every matched class before calling this
usable — quality looked solid. One real bug found and fixed in the process:
`self` (meant to catch "self-inductance" as a synonym for inductor)
false-matched inside unrelated words like "Self-contained" and was removed
rather than kept for a small coverage gain.
