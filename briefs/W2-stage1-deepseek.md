# TASK BRIEF — W2 stage 1: `qet-lint` core rules

Work in `/home/user/qelectrotech-docker`. Self-contained.

**Stage 1 only.** Five rules, all with known-bad files to prove them against.
Stage 2 (the semantic rules) is a separate task and is explicitly out of scope.

---

## 1. What you are building

A dependency-free static checker for QElectroTech project (`.qet`) and element
(`.elmt`) files. No build, no launch, no GUI — seconds per full run over a
corpus nobody has ever swept semantically.

```
tools/qet-lint/
  __main__.py        # qet-lint [--format text|json] [--baseline FILE] PATHS...
  rules_project.py   # P0xx rules over .qet
  rules_element.py   # E0xx rules over .elmt
  model.py           # parse once into a light DOM shared by all rules
  report.py          # text + JSON output, baseline diffing
  tests/  README.md
```

Every rule is a function taking the parsed model and yielding
`Violation(rule_id, severity, path, line, message, evidence)`.

Severities: `error` (data loss or crash risk), `warning` (real defect, cosmetic
impact), `info` (opt-in, off by default).

---

## 2. The five rules — all have proof fixtures

| ID | Check | Severity | Implement with |
|---|---|---|---|
| **P001** | any coordinate attribute is NaN or Inf | error | **Already written** — call `simulator/canon.py`'s `nan_or_inf_violations()`. Do not reimplement |
| **P002** | illegal XML 1.0 control byte anywhere in the file (U+0000–08, 0B, 0C, 0E–1F) | error | raw byte scan |
| **P003** | duplicate `uuid` value within one project | error | `canon.canonicalize()` already builds `uuid_universe` — reuse it |
| **E001** | file does not parse as XML (Python `ElementTree`) | error | 5 known-bad files exist in the collection, all in `<name lang="ca">` from one bad translation batch |
| **E002** | illegal control byte in an element | error | same scan as P002 |

**Nothing else.** Do not add rules from `TOOLING-PLAN.md` W2.2/W2.3 that are not
in this table — those need their hypotheses verified against QET's source first
and belong to stage 2.

---

## 3. Baseline support

`--baseline baseline.json`: violations recorded there are known and do not fail
the run, so the tool is a **gate on new problems** rather than a wall of
pre-existing noise.

Copy the shape of `tests/determinism/baseline.json` — including its
**"got worse" comparison** and its `--write-baseline` flag. A baseline that
merely suppresses hides a rule silently breaking.

---

## 4. Definition of done — paste real output

### Criterion 1 — the three known-bad files, with no special configuration

| File | Must be flagged |
|---|---|
| `elements-10-electric/10_electric/20_manufacturers_articles/johnson_controls/dx/modules_extension/xpx.elmt` | **E002** |
| `simulator/reports/findings/nul_byte_segv_cablage.qet` | **P002** |
| `simulator/reports/findings/nan_coordinate_hang_grafcet.qet` | **P001** |

All three exist in this repo right now — verified. `xpx.elmt` contains `&#11;`
(U+000B, illegal in XML 1.0) and **segfaults Qt's `QDomDocument::setContent()`**
rather than erroring; Python's `ElementTree` rejects it cleanly. That contrast
is the point.

### Criterion 2 — full corpus run

Run over all 23 example projects **and** all 6,918 `.elmt` files. Must complete
in **under a minute**. Report the violation count per rule.

### Criterion 3 — E001's five bad files

E001 should find ~5 malformed elements. Report how many and list them. If the
number differs from 5, say so — do not tune the rule to hit a target.

### Criterion 4 — baseline works

Record a baseline, re-run (expect clean exit 0), then introduce one new
violation and confirm the run fails. Paste both exits.

---

## 5. Guard against a false-positive flood

After the first full run: **hand-verify at least 3 instances of every rule that
fires**, by opening the file and confirming the finding is real. Record the
verification in `tools/qet-lint/README.md`.

Any rule whose sample turns out to be legitimate content gets demoted to `info`
or deleted. **A rule nobody checked is worse than no rule** — it trains people
to ignore the tool.

These five are all crash-or-corruption rules, so a large count is a surprise
worth investigating, not a success.

---

## 6. Environment

| Thing | Value |
|---|---|
| Projects | `/home/user/qet-fix/examples/*.qet` (23) |
| Elements | `elements-10-electric/10_electric` (6,918 `.elmt`) |
| Python | 3.14, **stdlib only** — no lxml, no external XML libs |

**No QET binary is needed for this task at all.** It is pure file analysis. If
you find yourself building or launching QET, you have gone off-scope.

**Validate suspect XML with `ElementTree`.** Python rejecting a file that Qt
segfaults on *is the finding* — it separates "the file is bad" from "Qt
mishandles bad input". They are different bugs in different repos.

---

## 7. Scope

**May create:** `tools/qet-lint/**`, a baseline file.

**Do NOT:** add rules beyond the five in §2; modify `simulator/` (import from it,
don't edit it); touch `scenarios/`, `tests/`, or any `.md` plan file; push or
post anywhere. Report findings — do not file them upstream.

**Work on a new branch**; the shared tree may have other sessions in it.

---

## 8. Report

Commit on a new branch. Report all four criteria with real pasted output, the
per-rule violation counts, your hand-verification notes, and anything in this
brief that was wrong or underspecified.
