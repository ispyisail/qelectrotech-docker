#!/usr/bin/env python3
"""
Stage-2 triage: classify the 91 open/unassigned bugtracker entries into five
buckets and emit reports/bugtracker-triage.{json,md}.

Source of truth for every ``entry_point``: upstream/master @ e2e0df784
(worktree /home/user/qet-fix-upstream), read line-by-line -- never guessed
from the bug summary. ``likely-fixed`` is evidence-based: each entry names the
commit or the source line that shows the behaviour is gone.

Run:  python3 tools/bugtracker/triage.py
"""
from __future__ import annotations

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_REF = "upstream/master @ e2e0df784 (worktree /home/user/qet-fix-upstream)"

# ---------------------------------------------------------------------------
# Data.  Each record: id, bucket, reason, and (for the right bucket) the extras.
# ---------------------------------------------------------------------------

FIXABLE = [
    # --- one-liners first ---
    dict(
        id=95,
        size="one-liner",
        summary="Collections pane project titles do not fall back to show filename when title is not defined.",
        reason=("XmlProjectElementCollectionItem::localName() returns the hardcoded string "
                "'Projet sans titre' when the project has no <title>, instead of falling back "
                "to the project filename."),
        entry_point="sources/ElementsCollection/xmlprojectelementcollectionitem.cpp:62  (XmlProjectElementCollectionItem::localName)",
        quote='setText(QObject::tr("Projet sans titre"));',
        test_route=("unit test: assert localName() returns the project's file name when the "
                    "<title> element is absent; smoke: QET --info on a title-less .qet."),
    ),
    dict(
        id=108,
        size="one-liner",
        summary="For wide conductors the automatic joining dot is too small/invisible",
        reason=("Conductor::paint() draws every junction as a fixed 3.0-unit ellipse, so the dot "
                "is invisible under a wide conductor (it should scale with the conductor width)."),
        entry_point="sources/qetgraphicsitem/conductor.cpp:577  (Conductor::paint)",
        quote="painter -> drawEllipse(QRectF(point.x() - 1.5, point.y() - 1.5, 3.0, 3.0));",
        test_route=("tools/exportleak (or QET --export-svg of a project with a wide conductor): "
                    "assert the junction ellipse radius grows with conductor width."),
    ),
    dict(
        id=163,
        size="one-liner",
        summary="Les nouveau fichiers projet crées sur un montage samba sont marqués executables",
        reason=("QET::writeXmlFile() saves through QSaveFile without normalising the file "
                "permissions, so a project created on a Samba mount inherits the exec bit."),
        entry_point="sources/qet.cpp:654  (QET::writeXmlFile)",
        quote="bool QET::writeXmlFile(QDomDocument &xml_doc, const QString &filepath, QString *error_message)",
        test_route=("headless: QET --resave <proj> <outdir>/x.qet; stat -c %a <outdir>/x.qet "
                    "-- assert the exec bits are cleared (caveat: needs a SMB mount to reproduce)."),
    ),
    dict(
        id=248,
        size="one-liner",
        summary="Project is not opened/visible when using filename with spaces",
        reason=("QET::splitWithSpaces() splits on the regex [^\\\\]?(?:\\\\\\\\)*  which consumes the "
                "character before an escaped space (and the escape), so filenames with spaces do "
                "not round-trip through the recent-files list."),
        entry_point="sources/qet.cpp:538  (QET::splitWithSpaces)",
        quote='QStringList escaped_strings = string.split(QRegularExpression("[^\\\\]?(?:\\\\\\\\)* "),Qt::SkipEmptyParts);',
        test_route=("unit test: QET::splitWithSpaces(QET::joinWithSpaces([...])) round-trips lists "
                    "containing spaces/backslashes; smoke: QET --info on a project whose path has a space."),
    ),
    # --- small ---
    dict(
        id=97,
        size="small",
        summary='Menu "File" > "Recently opened" is not updated until next program launch',
        reason=("QETDiagramEditor builds the File>Recently-opened submenu once at construction by "
                "snapshotting QETApp::projectsRecentFiles()->menu()->actions(); entries added later "
                "in the session never appear because the actions are copied, not shared."),
        entry_point="sources/qetdiagrameditor.cpp:863  (QETDiagramEditor, File menu setup)",
        quote="recentfile->addActions(QETApp::projectsRecentFiles()->menu()->actions());",
        test_route=("unit test: assert the submenu holds the live QMenu (shared object) rather than a "
                    "snapshot of actions(); GUI smoke: open two projects, confirm both appear in "
                    "File>Recently-opened without restart."),
    ),
    dict(
        id=237,
        size="small",
        summary='A "-" in label of user elements causes line feed',
        reason=("DynamicElementTextItem sets QTextOption::WordWrap plus a text width, which makes the "
                "hyphen-minus (U+002D) a word-break opportunity -- so a user-element label like 'A-B' "
                "wraps onto two lines."),
        entry_point="sources/qetgraphicsitem/dynamicelementtextitem.cpp:64,1435  (DynamicElementTextItem::setup/refresh)",
        quote="option.setWrapMode(QTextOption::WordWrap);  ...  document()->setTextWidth(m_text_width);",
        test_route=("tools/exportleak (or QET --export-svg) on an element whose label contains '-' with "
                    "text_width>0: assert the text stays on one line (caveat: needs text_width>0)."),
    ),
    dict(
        id=238,
        size="small",
        summary="Incorrectly order of pages in the table of contents",
        reason=("SummaryQueryWidget::queryStr() builds its ORDER BY from the displayed column name "
                "rather than the folio's real position, so the TOC/summary sorts pages in the wrong "
                "order once folios are reordered."),
        entry_point="sources/dataBase/ui/summaryquerywidget.cpp:66  (SummaryQueryWidget::queryStr)",
        quote='QString order_by = " ORDER BY ";',
        test_route=("unit test: queryStr() emits an ORDER BY on the folio position; "
                    "tools/labelstability: reorder folios and diff the summary order."),
    ),
    dict(
        id=240,
        size="small",
        summary="Au démarrage, apparition d'un message de restauration de fichier entraînant un crash.",
        reason=("QETDiagramEditor::openBackupFiles() deletes the QETProject when its state is not Ok, "
                "then falls through to addProject(project) on the freed pointer -- a use-after-free "
                "whenever a stale autosave file can't be opened."),
        entry_point="sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)",
        quote="delete project;   ...   addProject(project);",
        test_route=("headless + ASan: open a .qet that is a stale/broken autosave so "
                    "openBackupFiles() hits the error path; assert no UAF (fix: capture the filename, "
                    "delete project, then `continue;`)."),
    ),
    dict(
        id=242,
        size="small",
        summary="Prefix for User Collection",
        reason=("Autonum's elementPrefixForLocation() treats '10_electric' as a special case and reads "
                "the COMMON qet_labels.xml for it, ignoring the user's own qet_labels.xml in the "
                "custom-elements dir -- so user prefixes are dropped for that collection."),
        entry_point="sources/autoNum/assignvariables.cpp:743  (elementPrefixForLocation)",
        quote='if (current_location.fileName() != "10_electric"){',
        test_route=("unit test: elementPrefixForLocation() for a 10_electric location honours the user "
                    "qet_labels.xml; tools/labelstability for an end-to-end autonum check."),
    ),
    dict(
        id=245,
        size="small",
        summary="Not all custom variables are loaded correctly.",
        reason=("TitleBlockTemplate::listOfVariables() scans for %{...} tokens with the regex "
                "%\\{([^}]+)\\} and so misses bare %name2/%name3 custom variables, which then never "
                "appear in the title-block variable list."),
        entry_point="sources/titleblocktemplate.cpp:1836  (TitleBlockTemplate::listOfVariables)",
        quote='static const QRegularExpression rx(QStringLiteral("%\\\\{([^}]+)\\\\}"));',
        test_route=("unit test: listOfVariables() on a template containing '%name2 %name3' returns both "
                    "tokens; smoke: open the title-block template editor and check the variable list."),
    ),
    dict(
        id=247,
        size="small",
        summary="XRef slave reference hidden with dark themes",
        reason=("The slave cross-reference item is painted with a hardcoded Qt::black text colour in "
                "DynamicElementTextItem, so on a dark theme the slave label is black-on-dark and "
                "invisible (both on screen and in SVG/PDF export)."),
        entry_point="sources/qetgraphicsitem/dynamicelementtextitem.cpp:556,795,1377  (DynamicElementTextItem::updateXref)",
        quote="m_slave_Xref_item->setDefaultTextColor(Qt::black);",
        test_route=("tools/exportleak (or QET --export-svg) on a master/slave xref: assert the slave "
                    "label colour is inherited from the item rather than hardcoded black; "
                    "tools/crosspage for the arrow structure."),
    ),
    dict(
        id=306,
        size="small",
        summary="Restore files issue",
        reason=("Same defect as #240 -- the restore/autosave recovery path in "
                "QETDiagramEditor::openBackupFiles() can use a deleted QETProject pointer."),
        entry_point="sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)",
        quote="delete project;   ...   addProject(project);",
        test_route="as #240 (headless + ASan against a stale autosave).",
    ),
]

HARD = [
    dict(id=133, summary="The location field shown at element sometimes do not show last line",
         reason=("Real defect: wrapped location text drops its last line -- an ElementTextItem "
                 "height/layout computation issue tied to font metrics; needs layout work, not a "
                 "one-line fix.")),
    dict(id=136, summary="Hang at connection folio ref to one more element, with other conductors",
         reason=("Real hang when linking a folio ref with other conductors present; intermittent and "
                 "deep in link/interaction code, not reproduced on master.")),
    dict(id=185, summary="Moving element text using keyboard, causes the whole editor to shift",
         reason=("Keyboard-nudging element text scrolls the whole editor -- item-move and view-scroll "
                 "state interact; touches event handling broadly.")),
    dict(id=268, summary="Printing issue",
         reason=("Print output shifted/scaled; depends on printer driver and page geometry. The attached "
                 "proba.qet exports cleanly headless, so the fault is in the print path, not the data.")),
    dict(id=286, summary="crash after modify the nomenclature contents - can be avoided",
         reason=("Crash after editing nomenclature contents -- DB-backed view with an avoidable trigger; "
                 "needs a reproduced stack to localise.")),
    dict(id=305, summary='Impossible d\'intégrer les "Panels" dans l\'interface principale sous Wayland',
         reason=("Docking panels into the main window fails under Wayland -- Qt platform/QDockWidget "
                 "integration, not app logic.")),
]

RFE = [
    dict(id=90, summary="For elements and templates, use localised names regardless if QET interface is translated or not...",
         reason="Feature: localise element/template names regardless of UI language."),
    dict(id=102, summary="Feature: Netlist would be nice to have in the future", reason="Feature: netlist export."),
    dict(id=116, summary="Links clickable in exported pdf (master+slave xref, folio ref, links in text)",
         reason="Feature: clickable links in exported PDF."),
    dict(id=135, summary="Browse mode", reason="Feature: read-only browse mode."),
    dict(id=140, summary="[RFE] Comply with XDG configuration", reason="Feature: XDG config compliance."),
    dict(id=159, summary="Conductor type", reason="Feature: conductor-type property."),
    dict(id=160, summary="Generate Fuse Tab", reason="Feature: generate a fuse tab."),
    dict(id=184, summary="Hard to select element if they are too close", reason="Feature: easier selection of close elements."),
    dict(id=194, summary="Change font of text in Title block template editor", reason="Feature: choose the title-block font."),
    dict(id=207, summary="Implement add folio before or after selected folio", reason="Feature: add folio before/after selected."),
    dict(id=210, summary="Separate translation strings for label in component properties and nomenclature",
         reason="Feature: split label/nomenclature translation strings."),
    dict(id=214, summary="Création de multiples références produits, pour un même élément.",
         reason="Feature: multiple product references per element."),
    dict(id=215, summary="Edition manuelle de la nomenclature", reason="Feature: manual nomenclature editing."),
    dict(id=216, summary="Edition de la nomenclature en mode tableau", reason="Feature: table-mode nomenclature editing."),
    dict(id=217, summary="Mémoire d'entrée dans les informations éléments", reason="Feature: remember element-info entries."),
    dict(id=218, summary="Repère de taille de folio.", reason="Feature: folio-size marker."),
    dict(id=223, summary="Connection between two wires", reason="Feature: join two wires end-to-end."),
    dict(id=224, summary="Upgrade to newer version without uninstalling previous version",
         reason="Feature: in-place upgrade (installer behaviour)."),
    dict(id=227, summary="more font variables to set default font", reason="Feature: more default-font variables."),
    dict(id=231, summary="Display in macOS dark mode", reason="Feature: macOS dark-mode support."),
    dict(id=243, summary="Allow copy from read-only element", reason="Feature: copy from read-only element."),
    dict(id=250, summary='Revisión de la propiedad del elemento "Terminal"', reason="Feature: revise the Terminal property."),
    dict(id=258, summary="Custom Title Block information's don't allow wrap text",
         reason="Feature: wrap text in title-block information."),
    dict(id=260, summary="Use cross references in pdf as hyperlink", reason="Feature: cross-references as PDF hyperlinks."),
    dict(id=261, summary="Use pdf as background", reason="Feature: PDF as background."),
    dict(id=265, summary="master: slave reference layout support", reason="Feature: master/slave reference layout support."),
    dict(id=267, summary="Diagram editor color choices", reason="Feature: diagram-editor colour choices."),
    dict(id=279, summary='Topic: Setup folder schematic default "user" not "desktop"',
         reason="Feature/preference: default schematic folder."),
    dict(id=289, summary="Fonctionnalité de suppression d'une traduction de nom d'élément",
         reason="Feature: delete an element-name translation."),
    dict(id=298, summary="Information d'un élément de type Bornier", reason="Feature: bornier element information."),
    dict(id=301, summary="create layers for groups of different symbols/ text fields include it in the DXF export.",
         reason="Feature: layers + DXF export."),
    dict(id=331, summary="Amélioration - Numérotation Auto - Saisie de l'incrément + Prochain numéro directement dans la fenêtre d'édition",
         reason="Feature: autonumber increment / next-number fields."),
]

NEEDS_INFO = [
    dict(id=101, summary="Crash and other issues when editing an arc * REPEATABLE *",
         reason="2015 crash report, no repro project; the arc editor has been reworked since, but no "
                "specific fix commit identified -- can't act without a repro."),
    dict(id=104, summary="Another crash when saving * with debug screenshot *",
         reason="Crash on save, screenshot only, no version/repro steps."),
    dict(id=106, summary="Crash when selecting an area * with screenshot of debugger *",
         reason="Crash on area select, debugger screenshot only, no repro."),
    dict(id=137, summary="Crash when making connector", reason="Crash making a connector, no repro."),
    dict(id=141, summary="Tabs not working", reason="2016 report, no version/repro; tab behaviour reworked since, not pinned to a fix."),
    dict(id=143, summary="Software closes with error everytime i load a saved project",
         reason="Closes on every project load, no repro/version."),
    dict(id=169, summary="No consigo hacer funcionar el Terminal Block Generator",
         reason="Spanish: TBG plugin fails to run -- no plugin version/log; the plugin is a separate Python component."),
    dict(id=180, summary="Funcionamiento muy lento del programa.", reason="Slow performance, no profile/version."),
    dict(id=186, summary="Error in the online manual", reason="Manual error, no specific page/string."),
    dict(id=192, summary="QET 0,8", reason="Print/export issue with a single screenshot, no repro steps."),
    dict(id=193, summary="Error in italian traslate", reason="Which string is mistranslated is unspecified; translations regenerated since, not pinned."),
    dict(id=211, summary="Charset-Issue on current installer (0.8-RC)", reason="Installer/packaging charset issue, no details."),
    dict(id=234, summary="TERMINAL PLUGIN FAIL", reason="Terminal plugin fails, no log."),
    dict(id=236, summary="Update from 0.7 to 0.8 changed font size / scale",
         reason="0.7->0.8 font-size migration, no repro project."),
    dict(id=253, summary="Terminals position on each element is random.", reason="Terminal positions random, no steps."),
    dict(id=255, summary="UI text scaling on high DPI screen incorrect", reason="High-DPI scaling, environment-specific."),
    dict(id=259, summary="0.8.1 tarball", reason="Question about the 0.8.1 tarball, not a defect."),
    dict(id=271, summary="Font size incorrect when using Chromebook", reason="Font size on Chromebook, environment-specific."),
    dict(id=272, summary="lier des bornes", reason="Question ('link terminals'), no detail."),
    dict(id=273, summary="Si blocca come se stesse facendo un salvataggio", reason="Freeze 'as if saving', no repro."),
    dict(id=282, summary="When opening file to load, freezing and crashing",
         reason="Freeze on file open; video+log attached but no reproducible steps on master."),
    dict(id=283, summary="Le logiciel crash lors de toute sauvegarde ou chargement", reason="Crash on any save/load, no repro."),
    dict(id=284, summary="Bornes non affichés dans la liste \"Parties\"",
         reason="Vague: terminals missing from the element-editor 'Parties' list; no steps/version to pin a fix."),
    dict(id=311, summary='options contexts are not glued to top of window when opening "file", "edition" menus',
         reason="Wayland/flatpak menu glitch, environment-specific."),
]

LIKELY_FIXED = [
    dict(id=105, summary="Conductors at angle instead of orthogonal - with steps to reproduce",
         evidence=("Conductor system rewritten to orthogonal-only; "
                   "Conductor::pathFromXml (conductor.cpp) now runs a coherence check that rejects the "
                   "reported angular paths.")),
    dict(id=112, summary="No snap when zoomed out OR selection is big",
         evidence=("Grid snap is now unconditional -- commit 99064fe2a removed the zoom/selection-size "
                   "gate that caused the reported behaviour.")),
    dict(id=181, summary="La liste des folio ne conserve pas son cartouche",
         evidence=("The per-folio cartouche in the folio summary list was removed in the summary refactor "
                   "(commits 132f3ad1b / 53663e20e / 0c381eae2) -- the cartouche-preservation issue is gone.")),
    dict(id=187, summary="Moving elements by mouse does not respect the grid settings - fix included",
         evidence=("Diagram::snapToGrid (diagram.cpp) now reads QSettings('diagrameditor/Xgrid'); the "
                   "reported 'ignores grid' behaviour is superseded.")),
    dict(id=188, summary="%projectfilename variable",
         evidence=("%projectfilename was removed along with the folio-summary refactor (same commits as "
                   "#181); the variable no longer exists on master.")),
    dict(id=226, summary="Alignemt on right-sided composite text wrong",
         evidence=("Fixed by achim's 0a6efa466 + 73ce3ae9f (composite-text alignment); reproduced on "
                   "master -- the right-aligned text is no longer misaligned.")),
    dict(id=229, summary="[AppImage] crash by right-click on conductor's control point",
         evidence="Fixed by commit 778837a77 (right-click on a conductor control point no longer crashes)."),
    dict(id=256, summary="composite text folio reference overlapped",
         evidence=("Fixed by 0a6efa466 + 73ce3ae9f (composite-text overlap); reproduced on master -- no "
                   "longer reproducible.")),
    dict(id=278, summary="Crash on edit element : save as... i have wrong... save> crash",
         evidence=("ElementsCollectionModel::~ElementsCollectionModel() now m_future.waitForFinished() "
                   "(commit 39ac5716c, comment cites 'bugtracker #291'); the async-load save-as crash is fixed.")),
    dict(id=288, summary="thumbnail of elements with accents in filename are not displayed when the element is in user collection",
         evidence="Unicode/accented filename path fixed by commit 31edf30c6."),
    dict(id=291, summary="Crash on fast cancel at open element dialog",
         evidence="Same async collection-loading fix as #278 (commit 39ac5716c)."),
    dict(id=299, summary="Absence des textes répertoire collection \"One-Drive\"",
         evidence="One-Drive collection text absence fixed by commit 31edf30c6 (unicode path handling)."),
    dict(id=307, summary="QET file types description bad encoding",
         evidence="File-type description encoding fixed by commit e9e2ea5b0."),
    dict(id=308, summary="Preset for date is not saved",
         evidence=("Fixed by commit 5ba08284f5 / merged PR #696 ('current-date-preset-bug308') -- the date "
                   "preset is now persisted.")),
    dict(id=312, summary="on reopen of the Projekt the Rotation of the Text on the Wires does not get rotated correctly",
         evidence=("Fixed by commit 6c76b1f6a -- text-on-wire rotation is now forceRotateByUser, so "
                   "reopened projects keep their rotation.")),
    dict(id=335, summary="Element library icons are black and almost invisible on dark OS themes",
         evidence=("ElementsTreeView's constructor (elementscollection treeview) now forces a black-on-light "
                   "palette 'or the icons become invisible on dark themes' -- sources/ElementsCollection/elementstreeview.cpp:51.")),
    dict(id=339, summary="The interface to set the maximum number of slaves is not working",
         evidence="Fixed by commit fe6191f26 (the max-slaves interface works on master)."),
]

# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------

def _record(kind, d):
    r = dict(d)
    r["bucket"] = kind
    return r

records = []
for d in FIXABLE:
    records.append(_record("bug-fixable", d))
for d in HARD:
    records.append(_record("bug-hard", d))
for d in RFE:
    records.append(_record("rfe", d))
for d in NEEDS_INFO:
    records.append(_record("needs-info", d))
for d in LIKELY_FIXED:
    records.append(_record("likely-fixed", d))

by_id = {r["id"]: r for r in records}
assert len(by_id) == 91, f"expected 91 records, got {len(by_id)}"

BUCKET_ORDER = ["bug-fixable", "bug-hard", "rfe", "needs-info", "likely-fixed"]
SIZE_ORDER = {"one-liner": 0, "small": 1, "medium": 2}

def sort_key(r):
    b = BUCKET_ORDER.index(r["bucket"])
    if r["bucket"] == "bug-fixable":
        return (b, SIZE_ORDER.get(r.get("size"), 3), r["id"])
    return (b, r["id"])

records.sort(key=sort_key)

# ---------------------------------------------------------------------------
# Reclassifications from the scraper's repro_class (criterion 4)
# ---------------------------------------------------------------------------

RECLASS = [
    dict(id=163, from_="gui", to="headless",
         why=("The fix is in the save path (QET::writeXmlFile, qet.cpp:654), which is fully "
              "CLI-verifiable: --resave a project then stat the file mode. The scraper saw 'Samba mount' "
              "and assumed GUI.")),
    dict(id=242, from_="gui", to="headless",
         why=("The defect is a pure lookup (elementPrefixForLocation, assignvariables.cpp:743) that picks "
              "the wrong labels file -- unit-testable without a GUI.")),
    dict(id=248, from_="gui", to="headless",
         why=("splitWithSpaces/joinWithSpaces (qet.cpp:538) are pure string functions; the bug is a "
              "deterministic regex round-trip, unit-testable headlessly.")),
    dict(id=247, from_="headless", to="gui",
         why=("Scraper saw 'PDF/export' and said headless, but the root cause is a hardcoded Qt::black "
              "text colour in a graphics item -- a rendering/theme defect that also leaks into export.")),
    dict(id=237, from_="unclear", to="gui",
         why=("Not vague: it is a specific QTextOption::WordWrap hyphen break in DynamicElementTextItem "
              "(dynamicelementtextitem.cpp:64) -- a rendering defect, verifiable via SVG export.")),
    dict(id=108, from_="gui", to="headless",
         why=("The hardcoded 3.0-unit junction dot (conductor.cpp:577) is inspectable in the exported SVG "
              "without a mouse.")),
    dict(id=112, from_="gui", to="likely-fixed",
         why=("Reclassified from 'open bug' to fixed: snapToGrid is now unconditional (99064fe2a), so the "
              "reported no-snap behaviour no longer exists.")),
    dict(id=339, from_="gui", to="likely-fixed",
         why=("Reclassified from 'open bug' to fixed: the max-slaves interface works on master (fe6191f26).")),
]

# ---------------------------------------------------------------------------
# Emit JSON
# ---------------------------------------------------------------------------

out = {
    "generated_from": SRC_REF,
    "input": "reports/bugtracker.json (91 open + unassigned)",
    "bucket_distribution": {
        k: sum(1 for r in records if r["bucket"] == k) for k in BUCKET_ORDER
    },
    "reclassifications_from_repro_class": RECLASS,
    "records": records,
}

json_path = os.path.join(REPO, "reports", "bugtracker-triage.json")
with open(json_path, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
    f.write("\n")

# ---------------------------------------------------------------------------
# Emit Markdown
# ---------------------------------------------------------------------------

def esc(s):
    return s.replace("|", "\\|")

lines = []
a = lines.append
a("# QET bugtracker triage — 91 open/unassigned issues, classified")
a("")
a(f"- **Source of truth for entry points:** `{SRC_REF}` (read line-by-line, not guessed).")
a("- **Input:** `reports/bugtracker.json` (91 open + unassigned).")
a("- **Method:** every `likely-fixed` entry names a commit or source line showing the behaviour is gone; every `bug-fixable` entry names the file/line the fix touches.")
a("")

a("## Bucket distribution")
a("")
a("| bucket | count |")
a("|---|---|")
for k in BUCKET_ORDER:
    a(f"| {k} | {out['bucket_distribution'][k]} |")
a("")
a("Total: **91**.")
a("")

a("## `bug-fixable` (sorted: one-liners first)")
a("")
a("| id | size | entry_point | test_route (headless) |")
a("|---|---|---|---|")
for r in records:
    if r["bucket"] != "bug-fixable":
        continue
    a(f"| {r['id']} | {r['size']} | `{esc(r['entry_point'])}` | {esc(r['test_route'])} |")
a("")

a("### Fixable — what each one is")
a("")
for r in records:
    if r["bucket"] != "bug-fixable":
        continue
    a(f"- **#{r['id']}** ({r['size']}) — {r['summary']}  ")
    a(f"  - **why:** {r['reason']}  ")
    a(f"  - **entry point:** `{r['entry_point']}`  ")
    a(f"  - **test route:** {r['test_route']}")
a("")

a("## Entry points verified by reading the source (criterion 3)")
a("")
a("The following were opened in `upstream/master` and the lines quoted, not inferred from titles:")
a("")
for r in records:
    if r["bucket"] == "bug-fixable" and r.get("quote"):
        a(f"- **#{r['id']}** — `{esc(r['entry_point'])}`: `{esc(r['quote'])}`")
a("")

a("## `bug-hard`")
a("")
for r in records:
    if r["bucket"] != "bug-hard":
        continue
    a(f"- **#{r['id']}** — {r['summary']} — {r['reason']}")
a("")

a("## `rfe` (feature requests)")
a("")
for r in records:
    if r["bucket"] != "rfe":
        continue
    a(f"- **#{r['id']}** — {r['summary']} — {r['reason']}")
a("")

a("## `needs-info`")
a("")
for r in records:
    if r["bucket"] != "needs-info":
        continue
    a(f"- **#{r['id']}** — {r['summary']} — {r['reason']}")
a("")

a("## `likely-fixed` (evidence-based)")
a("")
a("| id | summary | what I checked |")
a("|---|---|---|")
for r in records:
    if r["bucket"] != "likely-fixed":
        continue
    a(f"| {r['id']} | {esc(r['summary'])} | {esc(r['evidence'])} |")
a("")

a("## Reclassifications from the scraper's `repro_class` (criterion 4)")
a("")
a("The scraper's `repro_class` (headless/gui/unclear) was a keyword heuristic. Where source-reading contradicts it:")
a("")
a("| id | from | to | why |")
a("|---|---|---|---|")
for r in RECLASS:
    a(f"| {r['id']} | {r['from_']} | {r['to']} | {esc(r['why'])} |")
a("")

md_path = os.path.join(REPO, "reports", "bugtracker-triage.md")
with open(md_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"wrote {json_path}")
print(f"wrote {md_path}")
print("bucket distribution:", out["bucket_distribution"])
