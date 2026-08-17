# labelstability — do folio-reference labels survive folio moves?

> X6 measurement report. Source ref scanned: `7307a59c101a`.

## Verdict on the maintainer's %f/%F claim

- **Confirmed mechanically, refuted in practice.** `%f` is folio *position* (`folioIndex()+1`); `%F` is the title-block folio *label* (`border_and_titleblock.folio()`). With a **stable literal** folio label, `%F` holds across a folio move and `%f` shifts — exactly as scorpio810 said.
- **But the workaround fails on the default configuration.** Every shipped example sets `folio="%id/%total"` ("3 of 12"), so `%F` expands to a position-derived string and shifts exactly like `%f`. Telling a user to "switch `%f` to `%F`" is not sufficient — they must also give each folio a stable literal label, which no shipped project does.
- **The displayed label is *not* the field that goes stale.** The live `<dynamic_elmt_text>` re-evaluates correctly on load/save. The field that goes wrong is the stored `<elementInformation name="label">`, which is never recomputed and is systematically off-by-one in shipped files.

## Criterion 1 — where labels live

- Report formula (project level): `<report label="%f-%l%c"/>`
- Sample arrow `{a7f7c228-ee6a-45cd-ac6c-8d8174736542}` (embed://import/06renvoi/02next_folio.elmt) on folio "Puissance" (order 2):
  - stored label `<elementInformation name="label">7-A11</elementInformation>`
  - displayed text `<dynamic_elmt_text info_name="label"><text>6-A10</text>`
  - links: {0d8ea98f-842b-4cec-9e47-6c99c15cdbf6}

The displayed label is the `<dynamic_elmt_text>` value; it is recomputed live from the project report formula applied to the *partner* arrow. The `<elementInformation name="label">` field is a separate, stored value that is **not** recomputed on save.

## Criterion 2 — the %f vs %F claim, tested

### Projet_vierge.qet

Perturbation: move folio "ARRIVEE PUISSANCE" to the end, then `--resave`.

| variant | formula | folio labels | arrows | label/text changed |
|---|---|---|---|---|
| %f_default | `%f-%l%c` | default | 10 | 5 |
| %f_stable | `%f-%l%c` | stable | 10 | 5 |
| %F_default | `%F-%l%c` | default | 10 | 5 |
| %F_stable | `%F-%l%c` | stable | 10 | 0 |

Samples (uuid before → after):

- `%f_default` {2da1fbf5-4177-45b5-: text `3-A1`→`2-A1`, stored label `4-A2`→`4-A2`
- `%f_default` {8262ce3f-f9bc-4db8-: text `3-A1`→`2-A1`, stored label `4-A2`→`4-A2`
- `%f_default` {bd220ea4-1e08-4216-: text `3-B1`→`2-B1`, stored label `4-B2`→`4-B2`
- `%f_default` {dcdc0539-6e99-49f1-: text `3-A1`→`2-A1`, stored label `4-A2`→`4-A2`
- `%f_stable` {2da1fbf5-4177-45b5-: text `3-A1`→`2-A1`, stored label `4-A2`→`4-A2`
- `%f_stable` {8262ce3f-f9bc-4db8-: text `3-A1`→`2-A1`, stored label `4-A2`→`4-A2`
- `%f_stable` {bd220ea4-1e08-4216-: text `3-B1`→`2-B1`, stored label `4-B2`→`4-B2`
- `%f_stable` {dcdc0539-6e99-49f1-: text `3-A1`→`2-A1`, stored label `4-A2`→`4-A2`
- `%F_default` {2da1fbf5-4177-45b5-: text `3/4-A1`→`2/4-A1`, stored label `4-A2`→`4-A2`
- `%F_default` {8262ce3f-f9bc-4db8-: text `3/4-A1`→`2/4-A1`, stored label `4-A2`→`4-A2`
- `%F_default` {bd220ea4-1e08-4216-: text `3/4-B1`→`2/4-B1`, stored label `4-B2`→`4-B2`
- `%F_default` {dcdc0539-6e99-49f1-: text `3/4-A1`→`2/4-A1`, stored label `4-A2`→`4-A2`
- `%F_stable` {2da1fbf5-4177-45b5-: text `FL3-A1`→`FL3-A1`, stored label `4-A2`→`4-A2`
- `%F_stable` {7ae5846b-c39a-48d7-: text ``→``, stored label `/`→`/`
- `%F_stable` {8193428b-91f8-4cc9-: text ``→``, stored label `/`→`/`
- `%F_stable` {8262ce3f-f9bc-4db8-: text `FL3-A1`→`FL3-A1`, stored label `4-A2`→`4-A2`

### affuteuse_250h.qet

Perturbation: move folio "Puissance" to the end, then `--resave`.

| variant | formula | folio labels | arrows | label/text changed |
|---|---|---|---|---|
| %f_default | `%f-%l%c` | default | 34 | 34 |
| %f_stable | `%f-%l%c` | stable | 34 | 34 |
| %F_default | `%F-%l%c` | default | 34 | 34 |
| %F_stable | `%F-%l%c` | stable | 34 | 0 |

Samples (uuid before → after):

- `%f_default` {0d8ea98f-842b-4cec-: text `2-F12`→`12-F12`, stored label `3-F13`→`3-F13`
- `%f_default` {16716212-c92e-4483-: text `5-E7`→`4-E7`, stored label `6-E8`→`6-E8`
- `%f_default` {25811f85-9609-4635-: text `3-C6`→`2-C6`, stored label `4-C7`→`4-C7`
- `%f_default` {2592f66a-f5a4-4e2f-: text `3-A0`→`2-A0`, stored label `4-A1`→`4-A1`
- `%f_stable` {0d8ea98f-842b-4cec-: text `2-F12`→`12-F12`, stored label `3-F13`→`3-F13`
- `%f_stable` {16716212-c92e-4483-: text `5-E7`→`4-E7`, stored label `6-E8`→`6-E8`
- `%f_stable` {25811f85-9609-4635-: text `3-C6`→`2-C6`, stored label `4-C7`→`4-C7`
- `%f_stable` {2592f66a-f5a4-4e2f-: text `3-A0`→`2-A0`, stored label `4-A1`→`4-A1`
- `%F_default` {0d8ea98f-842b-4cec-: text `2/12-F12`→`12/12-F12`, stored label `3-F13`→`3-F13`
- `%F_default` {16716212-c92e-4483-: text `5/12-E7`→`4/12-E7`, stored label `6-E8`→`6-E8`
- `%F_default` {25811f85-9609-4635-: text `3/12-C6`→`2/12-C6`, stored label `4-C7`→`4-C7`
- `%F_default` {2592f66a-f5a4-4e2f-: text `3/12-A0`→`2/12-A0`, stored label `4-A1`→`4-A1`
- `%F_stable` {0d8ea98f-842b-4cec-: text `FL2-F12`→`FL2-F12`, stored label `3-F13`→`3-F13`
- `%F_stable` {16716212-c92e-4483-: text `FL5-E7`→`FL5-E7`, stored label `6-E8`→`6-E8`
- `%F_stable` {25811f85-9609-4635-: text `FL3-C6`→`FL3-C6`, stored label `4-C7`→`4-C7`
- `%F_stable` {2592f66a-f5a4-4e2f-: text `FL3-A0`→`FL3-A0`, stored label `4-A1`→`4-A1`

## Criterion 3 — blank / wrong-number failure

### Projet_vierge.qet

- Repeated resave (3×) changed-vs-first-save counts: [0, 0, 0]
- Dangling link: removing both directions of a link, the displayed text goes from `3-A1` to `` (blank); the stored label stays `4-A2`.

### affuteuse_250h.qet

- Repeated resave (3×) changed-vs-first-save counts: [0, 0, 0]
- Dangling link: removing both directions of a link, the displayed text goes from `6-A10` to `` (blank); the stored label stays `7-A11`.


## Criterion 4 — corpus survey

- report formula usage: `%f`-based **22**, `%F`-based **0**, other 0, none 1

| project | report | arrows | no link | blank text |
|---|---|---|---|---|
| 741.qet | `%f-%l%c` | 0 | 0 | 0 |
| ArduinoLCD.qet | `%f-%l%c` | 0 | 0 | 0 |
| Habitat-Schemas_developpes.qet | `%f-%l%c` | 0 | 0 | 0 |
| Habitat-Unifilaire.qet | `%f-%l%c` | 0 | 0 | 0 |
| Projet_vierge.qet | `%f-%l%c` | 10 | 5 | 5 |
| ShellyParts.qet | `%f-%l%c` | 0 | 0 | 0 |
| affuteuse_250h.qet | `%f-%l%c` | 34 | 0 | 0 |
| cablage-eclairages_sikli-v5.qet | `%f-%l%c` | 0 | 0 | 0 |
| convertisseur.qet | `%f-%l%c` | 0 | 0 | 0 |
| câblage-éclairages-sikli-v5.qet | `%f-%l%c` | 0 | 0 | 0 |
| grafcet.qet | `/%f.%l%c` | 0 | 0 | 0 |
| industrial.qet | `%f-%l%c` | 0 | 0 | 0 |
| iso_sfc_example.qet | `%f-%l%c` | 0 | 0 | 0 |
| lmdg.qet | `%f-%l%c` | 0 | 0 | 0 |
| m_000.qet | `%f-%l%c` | 0 | 0 | 0 |
| perceuse.qet | `%f-%l%c` | 0 | 0 | 0 |
| photovoltaique.qet | `%f-%l%c` | 0 | 0 | 0 |
| pinball_williams_em.qet | `%f-%l%c` | 0 | 0 | 0 |
| schema_indus.qet | `None` | 0 | 0 | 0 |
| schema_unifilaire_voltaique2.qet | `%f-%l%c` | 0 | 0 | 0 |
| tableau_domestique.qet | `%f-%l%c` | 0 | 0 | 0 |
| tremie_vibrante.qet | `%f-%l%c` | 0 | 0 | 0 |
| weneedpolonez-Polonez_MR89_wiring_diagram.qet | `%f-%l%c` | 0 | 0 | 0 |
