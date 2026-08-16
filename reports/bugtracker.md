# QET bugtracker corpus — W4 stage 1 (inventory only)

- **Generated:** 2026-08-16T06:53:02Z
- **Source:** https://qelectrotech.org/bugtracker/ (anonymous, read-only)
- **QET binary under test:** `/home/user/qet-fix/build-fast/qelectrotech` @ `3ba741ed95339b5b855df0a4a951526de1dff980`
- **Scope:** open + unassigned (stage 1: inventory only, no ranking)

This is the stage-1 deliverable: an inventory of every **open, unassigned**
QElectroTech bugtracker issue, with a `repro_class` guess and — for the one
issue that has a project attachment and a headless verb — a real
`auto_repro` attempt. No ranking, no `code_paths`, no `likely_stale`, no
`effort_hint`. An inventory that stays an inventory.

---

## Criterion 1 — the corpus exists, with no gaps

The default anonymous filter hides only *closed* issues, so the list holds
**244** non-closed issues. Of those, **91** are open (status 10–50) *and* unassigned
(no handler on the issue). Every one was fetched, parsed, and recorded —
`parse_errors` is empty. `repro_class` distribution:

| repro_class | count |
|---|---|
| gui | 60 |
| headless | 13 |
| unclear | 18 |


Full inventory (id — summary — repro_class):

| id | summary | repro_class |
|---|---|---|
| 90 | For elements and templates, use localised names regardless if QET interface is translated or not... | unclear |
| 95 | Collections pane project titles do not fall back to show filename when title is not defined. | gui |
| 97 | Menu "File" > "Recently opened" is not updated until next program launch | unclear |
| 101 | Crash and other issues when editing an arc * REPEATABLE * | gui |
| 102 | Feature: Netlist would be nice to have in the future | gui |
| 104 | Another crash when saving * with debug screenshot * | gui |
| 105 | Conductors at angle instead of orthogonal - with steps to reproduce | gui |
| 106 | Crash when selecting an area * with screenshot of debugger * | gui |
| 108 | For wide conductors the automatic joining dot is too small/invisible | gui |
| 112 | No snap when zoomed out OR selection is big | gui |
| 116 | Links clickable in exported pdf (master+slave xref, folio ref, links in text) | headless |
| 133 | The location field shown at element sometimes do not show last line | unclear |
| 135 | Browse mode | unclear |
| 136 | Hang at connection folio ref to one more element, with other conductors | gui |
| 137 | Crash when making connector | gui |
| 140 | [RFE] Comply with XDG configuration | headless |
| 141 | Tabs not working | gui |
| 143 | Software closes with error everytime i load a saved project | gui |
| 159 | Conductor type | gui |
| 160 | Generate Fuse Tab | gui |
| 163 | Les nouveau fichiers projet crées sur un montage samba sont marqués executables | gui |
| 169 | No consigo hacer funcionar el Terminal Block Generator | unclear |
| 180 | Funcionamiento muy lento del programa. | gui |
| 181 | La liste des folio ne conserve pas son cartouche | unclear |
| 184 | Hard to select element if they are too close | gui |
| 185 | Moving element text using keyboard, causes the whole editor to shift | gui |
| 186 | Error in the online manual | gui |
| 187 | Moving elements by mouse does not respect the grid settings - fix included | gui |
| 188 | %projectfilename variable | headless |
| 192 | QET 0,8 | headless |
| 193 | Error in italian traslate | unclear |
| 194 | Change font of text in Title block template editor | gui |
| 207 | Implement add folio before or after selected folio | gui |
| 210 | Separate translation strings for label in component properties and nomenclature | gui |
| 211 | Charset-Issue on current installer (0.8-RC) | gui |
| 214 | Création de multiples références produits, pour un même élément. | headless |
| 215 | Edition manuelle de la nomenclature | headless |
| 216 | Edition de la nomenclature en mode tableau | gui |
| 217 | Mémoire d'entrée dans les informations éléments | unclear |
| 218 | Repère de taille de folio. | unclear |
| 223 | Connection between two wires | gui |
| 224 | Upgrade to newer version without uninstalling previous version | unclear |
| 226 | Alignemt on right-sided composite text wrong | gui |
| 227 | more font variables to set default font | gui |
| 229 | [AppImage] crash by right-click on conductor's control point | gui |
| 231 | Display in macOS dark mode | gui |
| 234 | TERMINAL PLUGIN FAIL | unclear |
| 236 | Update from 0.7 to 0.8 changed font size / scale | gui |
| 237 | A "-" in label of user elements causes line feed | unclear |
| 238 | Incorrectly order of pages in the table of contents | gui |
| 240 | Au démarrage, apparition d'un message de restauration de fichier entraînant un crash. | gui |
| 242 | Prefix for User Collection | gui |
| 243 | Allow copy from read-only element | gui |
| 245 | Not all custom variables are loaded correctly. | gui |
| 247 | XRef slave reference hidden with dark themes | headless |
| 248 | Project is not opened/visible when using filename with spaces | gui |
| 250 | Revisión de la propiedad del elemento "Terminal" | unclear |
| 253 | Terminals position on each element is random. | gui |
| 255 | UI text scaling on high DPI screen incorrect | gui |
| 256 | composite text folio reference overlapped | gui |
| 258 | Custom Title Block information's don't allow wrap text | gui |
| 259 | 0.8.1 tarball | unclear |
| 260 | Use cross references in pdf as hyperlink | headless |
| 261 | Use pdf as background | headless |
| 265 | master: slave reference layout support | gui |
| 267 | Diagram editor color choices | gui |
| 268 | Printing issue | headless |
| 271 | Font size incorrect when using Chromebook | gui |
| 272 | lier des bornes | unclear |
| 273 | Si blocca come se stesse facendo un salvataggio | gui |
| 278 | Crash on edit element : save as... i have wrong... save> crash | gui |
| 279 | Topic: Setup folder schematic default "user" not "desktop" | headless |
| 282 | When opening file to load, freezing and crashing | headless |
| 283 | Le logiciel crash lors de toute sauvegarde ou chargement | unclear |
| 284 | Bornes non affichés dans la liste "Parties" | unclear |
| 286 | crash after modify the nomenclature contents - can be avoided | gui |
| 288 | thumbnail of elements with accents in filename are not displayed when the element is in user collection | gui |
| 289 | Fonctionnalité de suppression d'une traduction de nom d'élément | gui |
| 291 | Crash on fast cancel at open element dialog | gui |
| 298 | Information d'un élément de type Bornier | gui |
| 299 | Absence des textes répertoire collection "One-Drive" | gui |
| 301 | create layers for groups of different symbols/ text fields include it in the DXF export. | headless |
| 305 | Impossible d'intégrer les "Panels" dans l'interface principale sous Wayland | gui |
| 306 | Restore files issue | gui |
| 307 | QET file types description bad encoding | gui |
| 308 | Preset for date is not saved | unclear |
| 311 | options contexts are not glued to top of window when opening "file", "edition" menus | gui |
| 312 | on reopen of the Projekt the Rotation of the Text on the Wires does not get rotated correctly | gui |
| 331 | Amélioration - Numérotation Auto - Saisie de l'incrément + Prochain numéro directement dans la fenêtre d'édition | gui |
| 335 | Element library icons are black and almost invisible on dark OS themes | gui |
| 339 | The interface to set the maximum number of slaves is not working | gui |


## Criterion 2 — reproductions attempted, with real output

`repro_class=headless` means the text implies an operation that maps to a
QET headless CLI verb (load/export/resave/info/titleblock). `auto_repro` is
only meaningful when the issue also carries a `.qet` **project** attachment
to run that verb against. Across all 91 issues there are exactly **two**
`.qet` project attachments: issue **#268** (headless, `proba.qet`) and
issue **#312** (gui, `Example.qet`). So exactly one issue qualifies.

The 13 headless issues and why each was or wasn't attempted:

| id | attachments | auto_repro |
|---|---|---|
| 116 | none | headless, but no .qet project attachment to run a verb against |
| 140 | none | headless, but no .qet project attachment to run a verb against |
| 188 | none | headless, but no .qet project attachment to run a verb against |
| 192 | pdf_print.png (file_id=93) | headless, but no .qet project attachment to run a verb against |
| 214 | none | headless, but no .qet project attachment to run a verb against |
| 215 | none | headless, but no .qet project attachment to run a verb against |
| 247 | none | headless, but no .qet project attachment to run a verb against |
| 260 | none | headless, but no .qet project attachment to run a verb against |
| 261 | none | headless, but no .qet project attachment to run a verb against |
| 268 | proba.pdf (file_id=157), proba.qet (file_id=158), proba-2.pdf (file_id=159), Screenshot.png (file_id=160), use_the_whole_page_unchechked.pdf (file_id=161) | attempted |
| 279 | none | headless, but no .qet project attachment to run a verb against |
| 282 | 20230217_214915.mp4 (file_id=171), 20230303.log (file_id=172) | headless, but no .qet project attachment to run a verb against |
| 301 | none | headless, but no .qet project attachment to run a verb against |


### Issue #268 — the one real reproduction

Attachment `proba.qet` (file_id=158) was downloaded into an isolated
`sandbox_context()` (own HOME/XDG, offscreen, no DISPLAY) and the implied
verb was run with a hard 120 s timeout:

```text
$ /home/user/qet-fix/build-fast/qelectrotech --export-pdf /tmp/qet-sim-_ipqhf27/work/proba.qet /tmp/qet-sim-_ipqhf27/work/out.pdf
exit_code = 0   timed_out = False   wall = 0.123s

--- stdout (tail) ---
Exported 2 page(s) -> /tmp/qet-sim-_ipqhf27/work/out.pdf

--- stderr (verbatim) ---
SQLite version:  "3.46.1"
is QRegularExpression ok?
is QRegularExpression ok?
Project content built in 0.065 seconds (elements collection 0.001, diagrams 0.064, terminal strips 0, refresh 0, database 0)
Project "proba.qet" (97 KiB) opened in 0.072 seconds (xml parsing 0.006, content 0.066)
```

**Not reproduced on `3ba741ed95339b5b855df0a4a951526de1dff980`** via `qelectrotech --export-pdf proba.qet out.pdf` — the project opens and
exports cleanly (exit 0, 2 pages, ~0.12 s). This is recorded as *not
reproduced*, never as *fixed*; a stage-2 human decides staleness.

`auto_repro_summary`: 13 headless → 1 attempted → 1 completed (exit 0).

## Criterion 3 — the three known-stale issues (#256, #278, #288)

These three are the issues the brief names as known-stale. They are all in
the corpus. None is headless-with-a-project, so `auto_repro` does **not**
cover them — and it must not be made to: two attach screenshots, not
projects, and each requires a human interaction (overlapping folio text,
the element-editor save-as flow, user-collection thumbnail rendering).

| id | repro_class | summary | attachments |
|---|---|---|---|
| 256 | gui | composite text folio reference overlapped | Bildschirmfoto von 2022-02-10 19-28-17.png, 01going_arrow_with_protocol.elmt, 02coming_arrow.elmt |
| 278 | gui | Crash on edit element : save as... i have wrong... save> crash | report.rtf |
| 288 | gui | thumbnail of elements with accents in filename are not displayed when the element is in user collection | Collection QET.png, Collection user.png, Bildschirmfoto_Element_erstellen.png |


The evidence for them here is therefore the honest kind: a recorded
`repro_class=gui`, a note of the attached artifacts, and the fact that the
scraper did not silently invent a headless repro for them. Reconfirming
(or retiring) these three is stage-2 work against a live build; it is not
faked in stage 1.

## Criterion 4 — the scraper fails loudly, not silently

The parser asserts shape and raises `ParseError` when a field the record
depends on is missing. Demonstrated against real cached pages by renaming
the HTML class a parser keys on (what a MantisBT theme change does):

```text
[1] clean parse bug 339 -> 'The interface to set the maximum number of slaves is not working'
[2] corrupted bug page raises -> ParseError: bug 339: required field 'bug-description' appears 0 time(s), expected exactly 1 -- page shape changed?
[3] clean list parse -> 50 rows
[4] corrupted list page raises -> ParseError: list page: buglist row has the right column count but the classes/order differ. Got: ['column-selection', 'column-edit', 'column-priority', 'column-id', 'column-bugnotes-count', 'column-attachments', 'column-category', 'column-severity', 'column-status', 'column-last-modified', 'column-summary-REMOVED']; want: ['column-selection', 'column-edit', 'column-priority', 'column-id', 'column-bugnotes-count', 'column-attachments', 'column-category', 'column-severity', 'column-status', 'column-last-modified', 'column-summary']
```

---

## Where the live MantisBT HTML differed from the brief's assumptions

1. **No "product version" field.** The bug detail page renders no Product
   Version cell at all (the field exists in the filter form but is never
   populated), so there is no `version` field to record. It is absent, not
   empty — and the scraper records it as `null`, not `""`.
2. **"steps-to-reproduce" and other fields are optional.** MantisBT only
   renders *Steps To Reproduce*, *Additional Information*, *OS*, *Platform*,
   etc. when they are non-empty, so most issues have none. Optional fields
   are `null` when absent, distinguishable from an explicitly-empty string.
3. **The tracker's own "Hide Status = resolved" filter is not applied.**
   POSTing `hide_status[]=80` is accepted and stored, but the resulting list
   still includes resolved issues. So the corpus filters open+unassigned
   **locally** from the full non-closed list (244 issues), which also keeps
   the count auditable.
4. **Attachments are embedded in the activities section**, not a dedicated
   table, and are identified by `file_download.php?file_id=N&type=bug`. The
   corpus records note URLs (filename + file_id) and does not auto-download.
5. **Only 2 of 91 issues carry a `.qet` project** (#268, #312). The rest
   attach screenshots, `.elmt` elements, `.rtf`/`.log` reports, or nothing.
   `auto_repro` is therefore inherently narrow at this snapshot — one real
   run, not thirteen.
