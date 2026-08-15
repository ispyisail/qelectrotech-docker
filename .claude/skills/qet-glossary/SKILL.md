---
name: qet-glossary
description: Translate QElectroTech user vocabulary into codebase names and source locations — wire/conductor, page/folio, symbol/element, tag/label, cross-reference. Load whenever a request names a QET concept in user language and you need to know where in the source it actually lives, or a grep for the user's word comes back thin.
---

# QET vocabulary → source

Users describe QET in the words the UI and the trade use. The codebase mostly
uses different ones. Grepping for the user's word is the standard way to
conclude wrongly that something does not exist.

**Measured on the source tree:** `conductor` appears in 126 files, `wire` in 11
(nearly all of them the `--export-wires` CLI verb). `element` 356 vs `symbol`
18. If a grep for the user's term comes back thin, translate first.

| User says | Codebase says | Where it lives |
|---|---|---|
| wire, cable, line | **conductor** | `sources/qetgraphicsitem/conductor.{cpp,h}` |
| wire label, wire number, wire name | **conductor text** | `sources/qetgraphicsitem/conductortextitem.{cpp,h}` |
| wire numbering, auto-numbering | **autonumerotation** | `sources/conductorautonumerotation.{cpp,h}`, `sources/autoNum/` |
| page, sheet | **folio** *(UI)* / **diagram** *(code)* | `sources/diagram.{cpp,h}`; both terms are used, `diagram` is the class |
| symbol, part, component | **element** | `sources/qetgraphicsitem/element.{cpp,h}` |
| symbol library, catalogue | **elements collection** | `sources/ElementsCollection/` |
| tag, text on a symbol | **element label** / **dynamic text** | `sources/qetgraphicsitem/dynamicelementtextitem.{cpp,h}` |
| free-standing text | **independent text** | `sources/qetgraphicsitem/independenttextitem.{cpp,h}` |
| cross-reference, XRef | **master / slave** | `sources/qetgraphicsitem/crossrefitem.*`, `masterelement.*`, `slaveelement.*` |
| title box, drawing frame | **title block** | `sources/titleblock/` |
| terminal strip | **terminal strip** | `sources/TerminalStrip/` |
| connection point on a symbol | **terminal** | `sources/qetgraphicsitem/terminal.{cpp,h}` |
| parts list, BOM | **nomenclature / BOM** | `--export-bom`, `sources/` export paths |
| project file | `.qet` (XML) | `sources/qetproject.{cpp,h}` |
| symbol file | `.elmt` (XML) | `sources/ElementsCollection/` |
| the database | project SQLite DB, built at load | `sources/dataBase/projectdatabase.cpp` |

## Local shorthand used in this project

| Shorthand | Means |
|---|---|
| "the advanced simulator" | the `scenarios/` module in the harness repo |
| "page N" | folio N of `tremie_vibrante.qet` |
| "the testbuild" | `qet-testbuild` — several PRs merged for manual review |

## Two naming traps

- **`--export-wires` and `--export-cables` are different exports**, and both
  exit 1 on an empty result. "Wires" there does mean conductors.
- **`element_info` is a runtime SQLite table**, not something in the `.qet`
  file. The file stores element data inline as `<elementInformations>`. A
  question about "element info" could mean either — ask which.

When you cannot find a concept, try the French: QET's `tr()` source language is
French throughout, and some identifiers follow it (`conductorautonumerotation`,
`nomenclature`, `folio`).
