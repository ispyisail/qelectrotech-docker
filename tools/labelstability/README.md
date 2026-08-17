# labelstability — do folio-reference labels survive folio moves?

Task X6 of the cross-folio work (`CROSSPAGE-PLAN.md`). Python 3, stdlib only.
Drives the QElectroTech binary headlessly and answers the question left open by
the PR #702 rejection:

> "Use `%F` (folio label) instead of `%f` (folio position). `%F` stays stable
> when folios are moved, renamed or inserted; `%f` does not."

This tool **measures**; it does not repair.

## Run

```bash
python3 -m tools.labelstability \
    --binary /home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech \
    --examples /home/user/qet-fix/examples
```

Writes `reports/labelstability.json` and `reports/labelstability.md`.

## What it does

| Criterion | Answer produced |
|---|---|
| C1 | where a renvoi arrow's displayed label lives in the XML + the producing formula |
| C2 | reorder a folio in a `%f` variant vs a `%F` variant; which labels shift, which hold |
| C3 | resave a project three times; remove a link and watch the text go blank |
| C4 | survey every shipped example: `%f` vs `%F` vs other report formula |

## Environment traps honoured

- every QET run is `-platform offscreen` with isolated `HOME`/`XDG_CONFIG_HOME`/
  `XDG_DATA_HOME` (SingleApplication).
- every QET invocation has a timeout; `schema_indus.qet` is excluded from resave
  (hangs on a modal, upstream #661).
- all edits happen on copies in a temp dir — never under `examples/`.
- labels are compared **by arrow uuid**, never document order (`Diagram::toXml`
  is non-deterministic, upstream #754).

## Key facts this tool rests on

- report formula lives at project level: `<report label="%f-%l%c"/>`.
- `%f` = `folioIndex()+1` (physical position); `%F` =
  `border_and_titleblock.folio()` (the title-block folio field).
- the *displayed* label is the `<dynamic_elmt_text info_name="label"><text>`
  value, recomputed live from the report formula against the **partner** arrow
  (`DynamicElementTextItem::updateReportText`).
- the `<elementInformation name="label">` value is a separate stored field and
  is **not** recomputed on save — in shipped files it is stale/off-by-one.
