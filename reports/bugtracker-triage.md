# QET bugtracker triage — 91 open/unassigned issues, classified

- **Source of truth for entry points:** `upstream/master @ e2e0df784 (worktree /home/user/qet-fix-upstream)` (read line-by-line, not guessed).
- **Input:** `reports/bugtracker.json` (91 open + unassigned).
- **Method:** every `likely-fixed` entry names a commit or source line showing the behaviour is gone; every `bug-fixable` entry names the file/line the fix touches.

## Bucket distribution

| bucket | count |
|---|---|
| bug-fixable | 12 |
| bug-hard | 6 |
| rfe | 32 |
| needs-info | 24 |
| likely-fixed | 17 |

Total: **91**.

## `bug-fixable` (sorted: one-liners first)

| id | size | entry_point | test_route (headless) |
|---|---|---|---|
| 95 | one-liner | `sources/ElementsCollection/xmlprojectelementcollectionitem.cpp:62  (XmlProjectElementCollectionItem::localName)` | unit test: assert localName() returns the project's file name when the <title> element is absent; smoke: QET --info on a title-less .qet. |
| 108 | one-liner | `sources/qetgraphicsitem/conductor.cpp:577  (Conductor::paint)` | tools/exportleak (or QET --export-svg of a project with a wide conductor): assert the junction ellipse radius grows with conductor width. |
| 163 | one-liner | `sources/qet.cpp:654  (QET::writeXmlFile)` | headless: QET --resave <proj> <outdir>/x.qet; stat -c %a <outdir>/x.qet -- assert the exec bits are cleared (caveat: needs a SMB mount to reproduce). |
| 248 | one-liner | `sources/qet.cpp:538  (QET::splitWithSpaces)` | unit test: QET::splitWithSpaces(QET::joinWithSpaces([...])) round-trips lists containing spaces/backslashes; smoke: QET --info on a project whose path has a space. |
| 97 | small | `sources/qetdiagrameditor.cpp:863  (QETDiagramEditor, File menu setup)` | unit test: assert the submenu holds the live QMenu (shared object) rather than a snapshot of actions(); GUI smoke: open two projects, confirm both appear in File>Recently-opened without restart. |
| 237 | small | `sources/qetgraphicsitem/dynamicelementtextitem.cpp:64,1435  (DynamicElementTextItem::setup/refresh)` | tools/exportleak (or QET --export-svg) on an element whose label contains '-' with text_width>0: assert the text stays on one line (caveat: needs text_width>0). |
| 238 | small | `sources/dataBase/ui/summaryquerywidget.cpp:66  (SummaryQueryWidget::queryStr)` | unit test: queryStr() emits an ORDER BY on the folio position; tools/labelstability: reorder folios and diff the summary order. |
| 240 | small | `sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)` | headless + ASan: open a .qet that is a stale/broken autosave so openBackupFiles() hits the error path; assert no UAF (fix: capture the filename, delete project, then `continue;`). |
| 242 | small | `sources/autoNum/assignvariables.cpp:743  (elementPrefixForLocation)` | unit test: elementPrefixForLocation() for a 10_electric location honours the user qet_labels.xml; tools/labelstability for an end-to-end autonum check. |
| 245 | small | `sources/titleblocktemplate.cpp:1836  (TitleBlockTemplate::listOfVariables)` | unit test: listOfVariables() on a template containing '%name2 %name3' returns both tokens; smoke: open the title-block template editor and check the variable list. |
| 247 | small | `sources/qetgraphicsitem/dynamicelementtextitem.cpp:556,795,1377  (DynamicElementTextItem::updateXref)` | tools/exportleak (or QET --export-svg) on a master/slave xref: assert the slave label colour is inherited from the item rather than hardcoded black; tools/crosspage for the arrow structure. |
| 306 | small | `sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)` | as #240 (headless + ASan against a stale autosave). |

### Fixable — what each one is

- **#95** (one-liner) — Collections pane project titles do not fall back to show filename when title is not defined.  
  - **why:** XmlProjectElementCollectionItem::localName() returns the hardcoded string 'Projet sans titre' when the project has no <title>, instead of falling back to the project filename.  
  - **entry point:** `sources/ElementsCollection/xmlprojectelementcollectionitem.cpp:62  (XmlProjectElementCollectionItem::localName)`  
  - **test route:** unit test: assert localName() returns the project's file name when the <title> element is absent; smoke: QET --info on a title-less .qet.
- **#108** (one-liner) — For wide conductors the automatic joining dot is too small/invisible  
  - **why:** Conductor::paint() draws every junction as a fixed 3.0-unit ellipse, so the dot is invisible under a wide conductor (it should scale with the conductor width).  
  - **entry point:** `sources/qetgraphicsitem/conductor.cpp:577  (Conductor::paint)`  
  - **test route:** tools/exportleak (or QET --export-svg of a project with a wide conductor): assert the junction ellipse radius grows with conductor width.
- **#163** (one-liner) — Les nouveau fichiers projet crées sur un montage samba sont marqués executables  
  - **why:** QET::writeXmlFile() saves through QSaveFile without normalising the file permissions, so a project created on a Samba mount inherits the exec bit.  
  - **entry point:** `sources/qet.cpp:654  (QET::writeXmlFile)`  
  - **test route:** headless: QET --resave <proj> <outdir>/x.qet; stat -c %a <outdir>/x.qet -- assert the exec bits are cleared (caveat: needs a SMB mount to reproduce).
- **#248** (one-liner) — Project is not opened/visible when using filename with spaces  
  - **why:** QET::splitWithSpaces() splits on the regex [^\\]?(?:\\\\)*  which consumes the character before an escaped space (and the escape), so filenames with spaces do not round-trip through the recent-files list.  
  - **entry point:** `sources/qet.cpp:538  (QET::splitWithSpaces)`  
  - **test route:** unit test: QET::splitWithSpaces(QET::joinWithSpaces([...])) round-trips lists containing spaces/backslashes; smoke: QET --info on a project whose path has a space.
- **#97** (small) — Menu "File" > "Recently opened" is not updated until next program launch  
  - **why:** QETDiagramEditor builds the File>Recently-opened submenu once at construction by snapshotting QETApp::projectsRecentFiles()->menu()->actions(); entries added later in the session never appear because the actions are copied, not shared.  
  - **entry point:** `sources/qetdiagrameditor.cpp:863  (QETDiagramEditor, File menu setup)`  
  - **test route:** unit test: assert the submenu holds the live QMenu (shared object) rather than a snapshot of actions(); GUI smoke: open two projects, confirm both appear in File>Recently-opened without restart.
- **#237** (small) — A "-" in label of user elements causes line feed  
  - **why:** DynamicElementTextItem sets QTextOption::WordWrap plus a text width, which makes the hyphen-minus (U+002D) a word-break opportunity -- so a user-element label like 'A-B' wraps onto two lines.  
  - **entry point:** `sources/qetgraphicsitem/dynamicelementtextitem.cpp:64,1435  (DynamicElementTextItem::setup/refresh)`  
  - **test route:** tools/exportleak (or QET --export-svg) on an element whose label contains '-' with text_width>0: assert the text stays on one line (caveat: needs text_width>0).
- **#238** (small) — Incorrectly order of pages in the table of contents  
  - **why:** SummaryQueryWidget::queryStr() builds its ORDER BY from the displayed column name rather than the folio's real position, so the TOC/summary sorts pages in the wrong order once folios are reordered.  
  - **entry point:** `sources/dataBase/ui/summaryquerywidget.cpp:66  (SummaryQueryWidget::queryStr)`  
  - **test route:** unit test: queryStr() emits an ORDER BY on the folio position; tools/labelstability: reorder folios and diff the summary order.
- **#240** (small) — Au démarrage, apparition d'un message de restauration de fichier entraînant un crash.  
  - **why:** QETDiagramEditor::openBackupFiles() deletes the QETProject when its state is not Ok, then falls through to addProject(project) on the freed pointer -- a use-after-free whenever a stale autosave file can't be opened.  
  - **entry point:** `sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)`  
  - **test route:** headless + ASan: open a .qet that is a stale/broken autosave so openBackupFiles() hits the error path; assert no UAF (fix: capture the filename, delete project, then `continue;`).
- **#242** (small) — Prefix for User Collection  
  - **why:** Autonum's elementPrefixForLocation() treats '10_electric' as a special case and reads the COMMON qet_labels.xml for it, ignoring the user's own qet_labels.xml in the custom-elements dir -- so user prefixes are dropped for that collection.  
  - **entry point:** `sources/autoNum/assignvariables.cpp:743  (elementPrefixForLocation)`  
  - **test route:** unit test: elementPrefixForLocation() for a 10_electric location honours the user qet_labels.xml; tools/labelstability for an end-to-end autonum check.
- **#245** (small) — Not all custom variables are loaded correctly.  
  - **why:** TitleBlockTemplate::listOfVariables() scans for %{...} tokens with the regex %\{([^}]+)\} and so misses bare %name2/%name3 custom variables, which then never appear in the title-block variable list.  
  - **entry point:** `sources/titleblocktemplate.cpp:1836  (TitleBlockTemplate::listOfVariables)`  
  - **test route:** unit test: listOfVariables() on a template containing '%name2 %name3' returns both tokens; smoke: open the title-block template editor and check the variable list.
- **#247** (small) — XRef slave reference hidden with dark themes  
  - **why:** The slave cross-reference item is painted with a hardcoded Qt::black text colour in DynamicElementTextItem, so on a dark theme the slave label is black-on-dark and invisible (both on screen and in SVG/PDF export).  
  - **entry point:** `sources/qetgraphicsitem/dynamicelementtextitem.cpp:556,795,1377  (DynamicElementTextItem::updateXref)`  
  - **test route:** tools/exportleak (or QET --export-svg) on a master/slave xref: assert the slave label colour is inherited from the item rather than hardcoded black; tools/crosspage for the arrow structure.
- **#306** (small) — Restore files issue  
  - **why:** Same defect as #240 -- the restore/autosave recovery path in QETDiagramEditor::openBackupFiles() can use a deleted QETProject pointer.  
  - **entry point:** `sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)`  
  - **test route:** as #240 (headless + ASan against a stale autosave).

## Entry points verified by reading the source (criterion 3)

The following were opened in `upstream/master` and the lines quoted, not inferred from titles:

- **#95** — `sources/ElementsCollection/xmlprojectelementcollectionitem.cpp:62  (XmlProjectElementCollectionItem::localName)`: `setText(QObject::tr("Projet sans titre"));`
- **#108** — `sources/qetgraphicsitem/conductor.cpp:577  (Conductor::paint)`: `painter -> drawEllipse(QRectF(point.x() - 1.5, point.y() - 1.5, 3.0, 3.0));`
- **#163** — `sources/qet.cpp:654  (QET::writeXmlFile)`: `bool QET::writeXmlFile(QDomDocument &xml_doc, const QString &filepath, QString *error_message)`
- **#248** — `sources/qet.cpp:538  (QET::splitWithSpaces)`: `QStringList escaped_strings = string.split(QRegularExpression("[^\\]?(?:\\\\)* "),Qt::SkipEmptyParts);`
- **#97** — `sources/qetdiagrameditor.cpp:863  (QETDiagramEditor, File menu setup)`: `recentfile->addActions(QETApp::projectsRecentFiles()->menu()->actions());`
- **#237** — `sources/qetgraphicsitem/dynamicelementtextitem.cpp:64,1435  (DynamicElementTextItem::setup/refresh)`: `option.setWrapMode(QTextOption::WordWrap);  ...  document()->setTextWidth(m_text_width);`
- **#238** — `sources/dataBase/ui/summaryquerywidget.cpp:66  (SummaryQueryWidget::queryStr)`: `QString order_by = " ORDER BY ";`
- **#240** — `sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)`: `delete project;   ...   addProject(project);`
- **#242** — `sources/autoNum/assignvariables.cpp:743  (elementPrefixForLocation)`: `if (current_location.fileName() != "10_electric"){`
- **#245** — `sources/titleblocktemplate.cpp:1836  (TitleBlockTemplate::listOfVariables)`: `static const QRegularExpression rx(QStringLiteral("%\\{([^}]+)\\}"));`
- **#247** — `sources/qetgraphicsitem/dynamicelementtextitem.cpp:556,795,1377  (DynamicElementTextItem::updateXref)`: `m_slave_Xref_item->setDefaultTextColor(Qt::black);`
- **#306** — `sources/qetdiagrameditor.cpp:2098-2101  (QETDiagramEditor::openBackupFiles)`: `delete project;   ...   addProject(project);`

## `bug-hard`

- **#133** — The location field shown at element sometimes do not show last line — Real defect: wrapped location text drops its last line -- an ElementTextItem height/layout computation issue tied to font metrics; needs layout work, not a one-line fix.
- **#136** — Hang at connection folio ref to one more element, with other conductors — Real hang when linking a folio ref with other conductors present; intermittent and deep in link/interaction code, not reproduced on master.
- **#185** — Moving element text using keyboard, causes the whole editor to shift — Keyboard-nudging element text scrolls the whole editor -- item-move and view-scroll state interact; touches event handling broadly.
- **#268** — Printing issue — Print output shifted/scaled; depends on printer driver and page geometry. The attached proba.qet exports cleanly headless, so the fault is in the print path, not the data.
- **#286** — crash after modify the nomenclature contents - can be avoided — Crash after editing nomenclature contents -- DB-backed view with an avoidable trigger; needs a reproduced stack to localise.
- **#305** — Impossible d'intégrer les "Panels" dans l'interface principale sous Wayland — Docking panels into the main window fails under Wayland -- Qt platform/QDockWidget integration, not app logic.

## `rfe` (feature requests)

- **#90** — For elements and templates, use localised names regardless if QET interface is translated or not... — Feature: localise element/template names regardless of UI language.
- **#102** — Feature: Netlist would be nice to have in the future — Feature: netlist export.
- **#116** — Links clickable in exported pdf (master+slave xref, folio ref, links in text) — Feature: clickable links in exported PDF.
- **#135** — Browse mode — Feature: read-only browse mode.
- **#140** — [RFE] Comply with XDG configuration — Feature: XDG config compliance.
- **#159** — Conductor type — Feature: conductor-type property.
- **#160** — Generate Fuse Tab — Feature: generate a fuse tab.
- **#184** — Hard to select element if they are too close — Feature: easier selection of close elements.
- **#194** — Change font of text in Title block template editor — Feature: choose the title-block font.
- **#207** — Implement add folio before or after selected folio — Feature: add folio before/after selected.
- **#210** — Separate translation strings for label in component properties and nomenclature — Feature: split label/nomenclature translation strings.
- **#214** — Création de multiples références produits, pour un même élément. — Feature: multiple product references per element.
- **#215** — Edition manuelle de la nomenclature — Feature: manual nomenclature editing.
- **#216** — Edition de la nomenclature en mode tableau — Feature: table-mode nomenclature editing.
- **#217** — Mémoire d'entrée dans les informations éléments — Feature: remember element-info entries.
- **#218** — Repère de taille de folio. — Feature: folio-size marker.
- **#223** — Connection between two wires — Feature: join two wires end-to-end.
- **#224** — Upgrade to newer version without uninstalling previous version — Feature: in-place upgrade (installer behaviour).
- **#227** — more font variables to set default font — Feature: more default-font variables.
- **#231** — Display in macOS dark mode — Feature: macOS dark-mode support.
- **#243** — Allow copy from read-only element — Feature: copy from read-only element.
- **#250** — Revisión de la propiedad del elemento "Terminal" — Feature: revise the Terminal property.
- **#258** — Custom Title Block information's don't allow wrap text — Feature: wrap text in title-block information.
- **#260** — Use cross references in pdf as hyperlink — Feature: cross-references as PDF hyperlinks.
- **#261** — Use pdf as background — Feature: PDF as background.
- **#265** — master: slave reference layout support — Feature: master/slave reference layout support.
- **#267** — Diagram editor color choices — Feature: diagram-editor colour choices.
- **#279** — Topic: Setup folder schematic default "user" not "desktop" — Feature/preference: default schematic folder.
- **#289** — Fonctionnalité de suppression d'une traduction de nom d'élément — Feature: delete an element-name translation.
- **#298** — Information d'un élément de type Bornier — Feature: bornier element information.
- **#301** — create layers for groups of different symbols/ text fields include it in the DXF export. — Feature: layers + DXF export.
- **#331** — Amélioration - Numérotation Auto - Saisie de l'incrément + Prochain numéro directement dans la fenêtre d'édition — Feature: autonumber increment / next-number fields.

## `needs-info`

- **#101** — Crash and other issues when editing an arc * REPEATABLE * — 2015 crash report, no repro project; the arc editor has been reworked since, but no specific fix commit identified -- can't act without a repro.
- **#104** — Another crash when saving * with debug screenshot * — Crash on save, screenshot only, no version/repro steps.
- **#106** — Crash when selecting an area * with screenshot of debugger * — Crash on area select, debugger screenshot only, no repro.
- **#137** — Crash when making connector — Crash making a connector, no repro.
- **#141** — Tabs not working — 2016 report, no version/repro; tab behaviour reworked since, not pinned to a fix.
- **#143** — Software closes with error everytime i load a saved project — Closes on every project load, no repro/version.
- **#169** — No consigo hacer funcionar el Terminal Block Generator — Spanish: TBG plugin fails to run -- no plugin version/log; the plugin is a separate Python component.
- **#180** — Funcionamiento muy lento del programa. — Slow performance, no profile/version.
- **#186** — Error in the online manual — Manual error, no specific page/string.
- **#192** — QET 0,8 — Print/export issue with a single screenshot, no repro steps.
- **#193** — Error in italian traslate — Which string is mistranslated is unspecified; translations regenerated since, not pinned.
- **#211** — Charset-Issue on current installer (0.8-RC) — Installer/packaging charset issue, no details.
- **#234** — TERMINAL PLUGIN FAIL — Terminal plugin fails, no log.
- **#236** — Update from 0.7 to 0.8 changed font size / scale — 0.7->0.8 font-size migration, no repro project.
- **#253** — Terminals position on each element is random. — Terminal positions random, no steps.
- **#255** — UI text scaling on high DPI screen incorrect — High-DPI scaling, environment-specific.
- **#259** — 0.8.1 tarball — Question about the 0.8.1 tarball, not a defect.
- **#271** — Font size incorrect when using Chromebook — Font size on Chromebook, environment-specific.
- **#272** — lier des bornes — Question ('link terminals'), no detail.
- **#273** — Si blocca come se stesse facendo un salvataggio — Freeze 'as if saving', no repro.
- **#282** — When opening file to load, freezing and crashing — Freeze on file open; video+log attached but no reproducible steps on master.
- **#283** — Le logiciel crash lors de toute sauvegarde ou chargement — Crash on any save/load, no repro.
- **#284** — Bornes non affichés dans la liste "Parties" — Vague: terminals missing from the element-editor 'Parties' list; no steps/version to pin a fix.
- **#311** — options contexts are not glued to top of window when opening "file", "edition" menus — Wayland/flatpak menu glitch, environment-specific.

## `likely-fixed` (evidence-based)

| id | summary | what I checked |
|---|---|---|
| 105 | Conductors at angle instead of orthogonal - with steps to reproduce | Conductor system rewritten to orthogonal-only; Conductor::pathFromXml (conductor.cpp) now runs a coherence check that rejects the reported angular paths. |
| 112 | No snap when zoomed out OR selection is big | Grid snap is now unconditional -- commit 99064fe2a removed the zoom/selection-size gate that caused the reported behaviour. |
| 181 | La liste des folio ne conserve pas son cartouche | The per-folio cartouche in the folio summary list was removed in the summary refactor (commits 132f3ad1b / 53663e20e / 0c381eae2) -- the cartouche-preservation issue is gone. |
| 187 | Moving elements by mouse does not respect the grid settings - fix included | Diagram::snapToGrid (diagram.cpp) now reads QSettings('diagrameditor/Xgrid'); the reported 'ignores grid' behaviour is superseded. |
| 188 | %projectfilename variable | %projectfilename was removed along with the folio-summary refactor (same commits as #181); the variable no longer exists on master. |
| 226 | Alignemt on right-sided composite text wrong | Fixed by achim's 0a6efa466 + 73ce3ae9f (composite-text alignment); reproduced on master -- the right-aligned text is no longer misaligned. |
| 229 | [AppImage] crash by right-click on conductor's control point | Fixed by commit 778837a77 (right-click on a conductor control point no longer crashes). |
| 256 | composite text folio reference overlapped | Fixed by 0a6efa466 + 73ce3ae9f (composite-text overlap); reproduced on master -- no longer reproducible. |
| 278 | Crash on edit element : save as... i have wrong... save> crash | ElementsCollectionModel::~ElementsCollectionModel() now m_future.waitForFinished() (commit 39ac5716c, comment cites 'bugtracker #291'); the async-load save-as crash is fixed. |
| 288 | thumbnail of elements with accents in filename are not displayed when the element is in user collection | Unicode/accented filename path fixed by commit 31edf30c6. |
| 291 | Crash on fast cancel at open element dialog | Same async collection-loading fix as #278 (commit 39ac5716c). |
| 299 | Absence des textes répertoire collection "One-Drive" | One-Drive collection text absence fixed by commit 31edf30c6 (unicode path handling). |
| 307 | QET file types description bad encoding | File-type description encoding fixed by commit e9e2ea5b0. |
| 308 | Preset for date is not saved | Fixed by commit 5ba08284f5 / merged PR #696 ('current-date-preset-bug308') -- the date preset is now persisted. |
| 312 | on reopen of the Projekt the Rotation of the Text on the Wires does not get rotated correctly | Fixed by commit 6c76b1f6a -- text-on-wire rotation is now forceRotateByUser, so reopened projects keep their rotation. |
| 335 | Element library icons are black and almost invisible on dark OS themes | ElementsTreeView's constructor (elementscollection treeview) now forces a black-on-light palette 'or the icons become invisible on dark themes' -- sources/ElementsCollection/elementstreeview.cpp:51. |
| 339 | The interface to set the maximum number of slaves is not working | Fixed by commit fe6191f26 (the max-slaves interface works on master). |

## Reclassifications from the scraper's `repro_class` (criterion 4)

The scraper's `repro_class` (headless/gui/unclear) was a keyword heuristic. Where source-reading contradicts it:

| id | from | to | why |
|---|---|---|---|
| 163 | gui | headless | The fix is in the save path (QET::writeXmlFile, qet.cpp:654), which is fully CLI-verifiable: --resave a project then stat the file mode. The scraper saw 'Samba mount' and assumed GUI. |
| 242 | gui | headless | The defect is a pure lookup (elementPrefixForLocation, assignvariables.cpp:743) that picks the wrong labels file -- unit-testable without a GUI. |
| 248 | gui | headless | splitWithSpaces/joinWithSpaces (qet.cpp:538) are pure string functions; the bug is a deterministic regex round-trip, unit-testable headlessly. |
| 247 | headless | gui | Scraper saw 'PDF/export' and said headless, but the root cause is a hardcoded Qt::black text colour in a graphics item -- a rendering/theme defect that also leaks into export. |
| 237 | unclear | gui | Not vague: it is a specific QTextOption::WordWrap hyphen break in DynamicElementTextItem (dynamicelementtextitem.cpp:64) -- a rendering defect, verifiable via SVG export. |
| 108 | gui | headless | The hardcoded 3.0-unit junction dot (conductor.cpp:577) is inspectable in the exported SVG without a mouse. |
| 112 | gui | likely-fixed | Reclassified from 'open bug' to fixed: snapToGrid is now unconditional (99064fe2a), so the reported no-snap behaviour no longer exists. |
| 339 | gui | likely-fixed | Reclassified from 'open bug' to fixed: the max-slaves interface works on master (fe6191f26). |

