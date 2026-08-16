# PR evidence inventory — L6 phase 1

Repo `qelectrotech/qelectrotech-source-mirror`, author `ispyisail`, corpus 136 PRs.

## Distribution

- observed: **22**
- inferred: **108**
- unstated: **6**

Classes follow the brief §3: `observed` = pasted output / measured values / before-after numbers present; `inferred` = reasoning from source or a verification claim with nothing run (incl. an explicit "attempted but not completed" admission); `unstated` = what changed only, no verification claim either way.

| # | State | Class | Markers | Claim |
|---|---|---|---|---|
| 483 | MERGED | inferred | 0 | Add headless command-line export (PDF / PNG / SVG / cable-list / wire-list) |
| 485 | MERGED | unstated | 0 | CLI export: don't draw the editor grid in PDF/PNG/SVG output |
| 489 | MERGED | inferred | 0 | CLI: add verification & data-export tools (info, BOM, nets, links, check-elements, resave) |
| 490 | MERGED | inferred | 0 | CLI: clickable cross-reference hyperlinks in PDF export |
| 493 | MERGED | observed | 1 | CLI: add --set-titleblock, and fix headless backup crash |
| 494 | MERGED | inferred | 0 | Element editor Save As: label the field as a file name, not 'element name' |
| 495 | MERGED | inferred | 0 | Folio properties: auto-add a title block's custom variables |
| 496 | MERGED | inferred | 0 | Fix regional system locale loading the wrong translation (pt_BR/nl_BE/nl_NL) |
| 497 | MERGED | inferred | 0 | Clear read-only state when a project is saved to a writable file |
| 498 | MERGED | inferred | 0 | Find translations when lang/ is beside bin/, not inside it (fixes #86) |
| 499 | CLOSED | inferred | 0 | Make the 'Shift to move element text' hint discoverable |
| 501 | MERGED | inferred | 0 | PartText: keep text position stable across save/reopen on font-size change (#158) |
| 502 | OPEN | inferred | 0 | Add conductor properties to the selection-properties dock (#500) |
| 504 | CLOSED | unstated | 0 | [Draft / PoC] Database-driven from-to wiring list + "Add a wiring list" (RFC for #503) |
| 505 | OPEN | inferred | 0 | Fix Qt6 build: cmake KF6 support + C++ source compatibility |
| 506 | MERGED | inferred | 0 | snap: pin qet-tb-generator source to tag v1.31 |
| 507 | OPEN | inferred | 0 | snap: migrate to core24, kde-neon-6 (Qt6), cmake build |
| 508 | MERGED | inferred | 0 | Drop dead ~/Application Data/qet fallback for qet_tb_generator (Windows) |
| 510 | OPEN | observed | 2 | ci: add Flatpak build workflow (x86_64 + aarch64) — rebase of #396 |
| 511 | MERGED | unstated | 0 | Fix #159: reset unused-element highlight when elements become used again |
| 512 | MERGED | inferred | 0 | Fix #492: wait for async backup before destroying QETProject (use-after-free) |
| 513 | MERGED | inferred | 0 | Import EPLAN Data Portal parts (.edz) into element collections |
| 514 | MERGED | observed | 2 | Fix SIGSEGV: cache QStandardPaths results in dataDir/configDir for thread safety |
| 515 | MERGED | inferred | 0 | Fix three uninitialised-value bugs found by Valgrind |
| 516 | OPEN | inferred | 0 | Fix data race in setUpData() and duplicate static QString constants in header |
| 517 | MERGED | inferred | 0 | snap: stage libxcb-cursor0 to fix xcb plugin crash on Ubuntu 24.04 (issue #373) |
| 518 | MERGED | observed | 1 | Fix TerminalData memory leak in Terminal destructor |
| 519 | MERGED | observed | 2 | Fix four memory leaks found by AddressSanitizer |
| 520 | MERGED | inferred | 0 | fix(editor): suppress spurious first-click element moves |
| 521 | MERGED | inferred | 0 | fix(collection): isCustomCollection() false-positive on company path |
| 522 | MERGED | inferred | 0 | fix(#283): restore center alignment when loading table config |
| 523 | OPEN | unstated | 0 | Fix #413: paste no longer adds '_' label to conductors that had no label |
| 524 | MERGED | inferred | 0 | Fix #391: collection panel blank when path contains accented chars or is too long (Windows) |
| 525 | CLOSED | unstated | 0 | macOS: set CFBundleShortVersionString in Info.plist |
| 526 | OPEN | unstated | 0 | fix(terminal-strip): free-terminal move button disabled and unresponsive (#409) |
| 528 | MERGED | observed | 2 | Fix #527: use ApplicationModal for Project Properties and app config dialogs |
| 555 | MERGED | inferred | 0 | edz: make EdzArchive error strings translatable (+ German and French) |
| 557 | MERGED | observed | 1 | qmake: allow building without KDE Frameworks 5 (CONFIG+=no_kf5) |
| 558 | MERGED | inferred | 0 | Clear the application stylesheet when using system colors |
| 559 | MERGED | inferred | 0 | Fix language (and data paths) when opening a .qet by double-click on Windows |
| 560 | MERGED | observed | 1 | Log project load times, split by phase |
| 572 | MERGED | inferred | 0 | Fix #531: page-level empty title block variable no longer shadows project-level value |
| 573 | MERGED | inferred | 0 | Fix #487: drag-selecting dynamic text fields silently converts their text source |
| 583 | MERGED | inferred | 0 | Add a local, per-project time-spent tracker |
| 584 | MERGED | inferred | 0 | Fix: potential-selector dialog can't actually be cancelled (#581) |
| 585 | OPEN | inferred | 0 | Diagram: Tab/Shift+Tab item-selection cycling + select-all-conductors/text-fields |
| 586 | MERGED | inferred | 0 | Add Ctrl+G "jump to element" quick-open popup |
| 587 | MERGED | inferred | 0 | Add configurable shortcuts: Shortcuts preferences page + app-wide registry |
| 589 | MERGED | inferred | 0 | Add live cursor-coordinate readout to the element editor status bar |
| 590 | MERGED | inferred | 0 | Add undo/redo support for folio add, delete, and reorder |
| 591 | OPEN | inferred | 0 | Add drag-to-resize for dynamic element text width (#577 phase 1) |
| 593 | MERGED | inferred | 0 | Add wrap-and-carry (cyclic/modulo) auto-numbering |
| 594 | MERGED | inferred | 0 | Add alphabetical auto-numbering (a, b, ... z, aa, ab, ...) |
| 619 | OPEN | inferred | 0 | Make system pugixml (BUILD_PUGIXML=OFF) actually usable |
| 620 | MERGED | inferred | 0 | Fix element library icons invisible on dark OS themes |
| 621 | OPEN | inferred | 0 | Inherit text configuration from the last placed instance of the same element |
| 622 | CLOSED | inferred | 0 | Fix folders showing with no name in the elements panel |
| 624 | MERGED | inferred | 0 | Show unsaved-changes state in the main window title (macOS modified dot) |
| 625 | OPEN | observed | 2 | Give Conductor its own persisted uuid (discussion #503, slice 1) |
| 626 | MERGED | inferred | 0 | Add quick reset buttons to the auto-numbering dock |
| 628 | OPEN | observed | 3 | Add terminal and conductor tables to projectDataBase (discussion #503, slice 2) |
| 629 | OPEN | inferred | 0 | Add wiring_list_view: from-to wiring list over the conductor tables (discussion #503, slice 3) |
| 630 | OPEN | inferred | 0 | Wiring list dialog + excluded-conductor count (discussion #503, slice 4) |
| 631 | OPEN | observed | 2 | BOM: wire count per element (discussion #503, slice 5) |
| 632 | MERGED | inferred | 0 | Fix Cyclique (modulo) parts defaulting to modulus 0 (follow-up to #593) |
| 633 | MERGED | inferred | 0 | Never leave a collection folder without a name (replaces #622) |
| 634 | MERGED | inferred | 0 | Numbering parts: user-settable display format (zero mask) |
| 635 | OPEN | inferred | 0 | 3D mouse (SpaceMouse/SpacePilot) pan/zoom via libspnav — Linux phase (discussion #599) |
| 637 | MERGED | inferred | 0 | Add "Export to SVG" to the element editor (discussion #605) |
| 638 | OPEN | inferred | 0 | Color management for conductor auto-numbering (discussion #606) |
| 640 | OPEN | inferred | 0 | Configuration export/import for switching QET config profiles (discussion #610) |
| 641 | OPEN | inferred | 0 | Generate cabinet placement thumbnails from manufacturer/reference info (discussion #602) |
| 642 | MERGED | inferred | 0 | Add user-defined custom properties on elements (discussion #611) |
| 643 | OPEN | inferred | 0 | Add adjustable background frame in the element editor (discussion #604) |
| 645 | MERGED | inferred | 0 | Cover auto-numbering counter changes with undo/redo (discussion #608) |
| 646 | MERGED | inferred | 0 | Rework diagnostic logging: fix file writer, add rotation and a ring buffer (discussion #644, steps 1-3) |
| 647 | MERGED | inferred | 0 | Add crash-time ring flush and diagnostics export UI (discussion #644, steps 4-5) |
| 648 | OPEN | inferred | 0 | IEC 81346 plant/location fallback and composite structure-id token (discussion #613) |
| 650 | OPEN | inferred | 0 | Page-match abbreviation for %{structure_id} + %{structure_id_full} token (discussion #649) |
| 652 | OPEN | inferred | 0 | Structure box: a labeling frame carrying its own IEC 81346 identity (discussion #649) |
| 654 | OPEN | inferred | 0 | Rotate crash-recovery backups instead of overwriting a single snapshot |
| 655 | CLOSED | inferred | 0 | Add configurable conductor end-cap style (square/round/flat) |
| 656 | MERGED | inferred | 0 | Remember last-used shape/text style for new items this session |
| 657 | OPEN | inferred | 0 | Consolidate QETDiagramEditor's ~60 QActions into a DiagramEditorActions pool |
| 658 | MERGED | inferred | 0 | Add "Insert folio above/below" to the elements panel's folio menu |
| 659 | OPEN | inferred | 0 | Preserve master/slave links when pasting or duplicating a folio |
| 660 | MERGED | inferred | 0 | Add "rotate group" to actually rotate a selection as a whole |
| 661 | OPEN | observed | 2 | Fix command-line tools hanging forever on a modal message box |
| 664 | OPEN | observed | 1 | Fix element_info orphan row causing UNIQUE constraint errors on undo |
| 665 | MERGED | observed | 2 | Add an event-loop responsiveness watchdog (discussion #644 follow-up) |
| 668 | OPEN | inferred | 0 | Show a live IEC 81346-2 placeholder label when nothing else is configured |
| 672 | OPEN | inferred | 0 | Fix element prefix lookup: relocated collections, non-10_electric trees, unbounded array |
| 678 | MERGED | observed | 1 | Add two orphaned actions to the menus, drop two dead members |
| 680 | MERGED | observed | 1 | Add optional precompiled headers behind QET_ENABLE_PCH (default OFF) |
| 682 | OPEN | observed | 5 | Reject non-finite element positions and illegal XML control bytes |
| 683 | OPEN | inferred | 1 | Add --test-ops: headless scripted editing for automated regression testing |
| 690 | OPEN | inferred | 0 | Draft/preview: SVG icons for the concepts no icon theme provides (88 icons) |
| 691 | OPEN | inferred | 0 | Dialogs remember their size/position; drop a hardcoded light-mode color |
| 692 | OPEN | inferred | 0 | Draft: fast element insertion — all four phases from #676 |
| 693 | MERGED | inferred | 0 | Fix crash changing dynamic text color and confirming with Enter (bugtracker #323) |
| 695 | MERGED | inferred | 0 | Fix invisible element icons on dark themes in two dialogs missed by the earlier fix (bugtracker #335) |
| 696 | MERGED | inferred | 0 | Fix "use current date" preset lost unless the Folio tab is active on save (bugtracker #308) |
| 697 | MERGED | inferred | 0 | Edit increment and preview the next number in the auto-numbering dock (bugtracker #331) |
| 701 | CLOSED | inferred | 0 | Make folio-referencing arrows clickable and show link state |
| 702 | CLOSED | inferred | 0 | Add auto-numbering for folio-reference (report) arrow labels |
| 706 | MERGED | inferred | 0 | Scroll the diagram view to the selected search hit (bugtracker #309) |
| 707 | MERGED | inferred | 0 | Fix bugtracker #312: wire text rotation not preserved on reload |
| 710 | OPEN | inferred | 0 | Fix bugtracker #307: QET file type description bad encoding |
| 711 | OPEN | inferred | 0 | Fix bugtracker #306: crash when restoring backup files on startup |
| 712 | MERGED | inferred | 0 | Fix bugtracker #296: cross-reference text overlaps element label by default |
| 713 | OPEN | inferred | 0 | Fix bugtracker #291: crash on fast cancel at open element dialog |
| 714 | MERGED | inferred | 0 | Fix bugtracker #281: new-part wizard's element editor opens behind main window |
| 715 | MERGED | inferred | 0 | Fix bugtracker #275: element properties window stuck centered on macOS |
| 716 | MERGED | inferred | 0 | Fix bugtracker #270: Save As on Snap produces file with no .qet extension |
| 717 | MERGED | inferred | 0 | Fix bugtracker #251: title block template with slash in name fails silently |
| 718 | OPEN | inferred | 0 | Fix bugtracker #247: XRef slave reference hidden with dark themes |
| 719 | OPEN | inferred | 0 | Fix bugtracker #245: bare %name custom variables not detected in title blocks |
| 721 | OPEN | inferred | 0 | Enable Information tab in element editor for Slave and Terminal basetypes |
| 724 | CLOSED | observed | 2 | Fix wire-name export doubling every conductor's count |
| 725 | MERGED | inferred | 0 | Fix PDF export truncating project filenames at the first dot |
| 726 | MERGED | inferred | 0 | Fix bugtracker #333: selecting several dynamic texts overwrites their colours |
| 728 | OPEN | observed | 1 | Fix bugtracker #248: files passed to a running instance are never opened |
| 729 | OPEN | inferred | 0 | Don't drop files handed to a starting instance while the backup prompts are up |
| 732 | OPEN | inferred | 0 | Fix bugtracker #238: summary lists folios in the wrong order |
| 733 | OPEN | inferred | 0 | Fix bugtracker #243: allow copying out of a read-only element |
| 736 | OPEN | inferred | 0 | Fix folio report link picker showing candidates as blank rows |
| 737 | CLOSED | observed | 4 | Fix headless CLI hanging forever on version-incompatible projects |
| 738 | MERGED | inferred | 0 | Fix nameless "false" row in the element Informations panel |
| 740 | MERGED | inferred | 0 | Export slave cross-reference labels to DXF |
| 743 | MERGED | inferred | 0 | Fix bugtracker #291: crash on cancelling open-element dialog before collection load finishes |
| 744 | MERGED | inferred | 0 | Fix bugtracker #335: element icons invisible on dark themes |
| 746 | OPEN | inferred | 0 | Fix pasted conductors getting an unwanted "_" label |
| 747 | OPEN | inferred | 0 | Fix real_font_size_ desyncing from the actual font in PartText |
| 750 | MERGED | inferred | 0 | Export the master-side cross-reference table to DXF |
| 752 | OPEN | observed | 1 | Take the modal dialog out of RotateTextsCommand's constructor |
| 753 | CLOSED | observed | 1 | Add a non-interactive mode so headless runs cannot block on a modal |
