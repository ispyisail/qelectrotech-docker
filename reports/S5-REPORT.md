# S5 report — register the unbindable actions

Branch `s5-register-actions`, branched off `fix-shortcut-conflict-scope`
(upstream PR #759, the category-scoped conflict detection) as required.
22 commits: 1 header change + 21 owner `.cpp` files, one commit each.

## Criterion 1 — the count moves

Audit re-run against the worktree (`python3 tools/actionaudit/actionaudit.py`),
before = base commit `053903ad6`, after = `s5-register-actions` HEAD.

**Before:**

```json
  "registerAction_sites": 96,
  "registerAction_distinct_ids": 94,
  "gap_connected_unregistered": 171,
```

**After:**

```json
  "registerAction_sites": 262,
  "registerAction_distinct_ids": 260,
  "gap_connected_unregistered": 5,
```

`registerAction_sites` 96 → 262 (+166); `gap_connected_unregistered` 171 → 5
(−166). The brief's `95 → 267` / `176 → ~4` assumed the master baseline; the
`fix-shortcut-conflict-scope` base carries a different gap composition (see
"Brief corrections" below), so the real delta here is 166 registrations and
5 remaining gap records, not 172 and ~4.

## Criterion 2 — it builds

```
cmake -S /tmp/s5-src -B /tmp/s5-build -G Ninja -DCMAKE_BUILD_TYPE=Debug
    → "Configuring done (156.7s) / Generating done (0.3s) / Build files have been written"
    CMAKE_EXIT=0

ninja -C /tmp/s5-build qelectrotech
    → [496/496] Linking CXX executable qelectrotech
    NINJA_EXIT=0      (measured directly: echo "NINJA_EXIT=$?" > /tmp/s5-ninja.exit)
```

`qelectrotech` (161,731,216 bytes) produced at `/tmp/s5-build/qelectrotech`.

## Criterion 3 — no new conflicts

`tools/shortcut-harness/run.sh /tmp/s5-src`:

```
total rows: 5
conflicted rows after populateTable(): 2
    PASS   all five sample rows present
    PASS   same-category duplicate pair is flagged (2 rows)
    PASS   blank registrations in the same category are NOT flagged
    PASS   same key in a different category is NOT flagged (category scoping)
    PASS   exactly 2 conflicted rows (the planted pair), 0 from blanks
filter 'Profondeur' -> 1 visible
    PASS   filter matches exactly the 'Profondeur haut' row
ALL CHECKS PASSED
```

`HARNESS_EXIT=0`. Two blank registrations in one category and one same-key
cross-category action all stay unflagged; the only 2 conflicts are the planted
same-category duplicate pair. This is the `!isEmpty()` guard in
`checkConflicts()` (`sources/ui/configpage/shortcutsconfigpage.cpp:174,184`)
working as the brief stated.

## Criterion 4 — the 5 defaults are right

Extracted from the post-registration `actions.json` (all in category
`Général`):

| id | default_sequence |
|---|---|
| `mainwindow.configure` | `QKeySequence::Preferences` |
| `printwindow.first_page` | `QKeySequence::MoveToStartOfDocument` |
| `printwindow.previous_page` | `QKeySequence::MoveToPreviousPage` |
| `printwindow.next_page` | `QKeySequence::MoveToNextPage` |
| `printwindow.last_page` | `QKeySequence::MoveToEndOfDocument` |

These match `SHORTCUTS-S4-DECISIONS.md` §2 exactly. All 7 non-empty
`Général` defaults (the 5 above plus `mainwindow.manual_online` = `Qt::Key_F1`
and `mainwindow.fullscreen` = `Qt::CTRL | Qt::SHIFT | Qt::Key_F`) are pairwise
distinct — **no collision within the category**.

## Skipped records (with reasons)

Five records remain as `gap_connected_unregistered` (kind `action`/`checkable`),
plus one `dynamic` record that the metric does not count:

| owner | file:line | text | target | reason |
|---|---|---|---|---|
| QETDiagramEditor | sources/qetdiagrameditor.cpp:401 | `:/ico/22x22/guides.png` | `m_draw_guides` | icon path misparsed as label; registering would show the path as the action name |
| QETDiagramEditor | sources/qetdiagrameditor.cpp:2143 | (null) | `action` | null text / dynamic placeholder |
| QETMainWindow | sources/qetmainwindow.cpp:89 | (null) | `whatsthis_action_` | null text |
| diagramselection | sources/ui/diagramselection.cpp:106 | `Désélectionner tout` | `desl` | dead code (upstream issue #756) |
| MasterPropertiesWidget | sources/ui/masterpropertieswidget.cpp:1072 | `Coller depuis le presse-papiers` | (none) | `menu.addAction(tr(...))` result discarded — no variable to reference |
| RecentFiles | sources/recentfiles.cpp:180 | (null) | `action` | kind `dynamic`, outside the gap metric |

One more is worth flagging: `diagramview.cpp:621` registers a transient
popup `QAction *act` (`diagrameditor.act`) created fresh on every
rubber-band-select of >3 terminals. It is safe (parented to the view, and
`registerAction` prunes null `QPointer`s), but its target list grows by one
per gesture for the life of the view — a pre-existing per-gesture allocation,
not a leak introduced here.

## Per-owner commits (oldest → newest, on `s5-register-actions`)

```
b5519f223 S5: default registerAction() default_sequence argument
60027d9e7 S5: register actions in sources/ElementsCollection/elementscollectionwidget.cpp
5773c0d50 S5: register actions in sources/SearchAndReplace/ui/searchandreplacewidget.cpp
1a04271fc S5: register actions in sources/TerminalStrip/ui/terminalstripeditorwindow.cpp
03e3e3728 S5: register actions in sources/diagramview.cpp
0eb18ab62 S5: register actions in sources/editor/graphicspart/partpolygon.cpp
626173e5b S5: register actions in sources/editor/ui/polygoneditor.cpp
788332a10 S5: register actions in sources/editor/ui/qetelementeditor.cpp
1ecab0183 S5: register actions in sources/elementspanelwidget.cpp
189a6905b S5: register actions in sources/print/projectprintwindow.cpp
9cdeaa9ac S5: register actions in sources/projectview.cpp
2fa0cf41e S5: register actions in sources/qetapp.cpp
e8b145585 S5: register actions in sources/qetdiagrameditor.cpp
fdffdd9a7 S5: register actions in sources/qetgraphicsitem/qetshapeitem.cpp
b072e6819 S5: register actions in sources/qetmainwindow.cpp
1f86b8afd S5: register actions in sources/richtext/richtexteditor.cpp
ae22d7d9d S5: register actions in sources/titleblock/qettemplateeditor.cpp
d550b5e4e S5: register actions in sources/titleblock/templateview.cpp
3eaad1240 S5: register actions in sources/ui/linksingleelementwidget.cpp
1058120b4 S5: register actions in sources/ui/masterpropertieswidget.cpp
d6dfd9d16 S5: register actions in sources/ui/plclinkwidget.cpp
c00ecc896 S5: register actions in sources/ui/titleblockpropertieswidget.cpp
```

## Brief corrections / underspecifications

1. **Baseline numbers are branch-dependent.** The brief's `95 → 267` and
   `176 → ~4` assumed the audit at the S1 baseline. Branching off
   `fix-shortcut-conflict-scope` (as instructed) yields 96 sites and a 171
   gap, so the real outcome is 96 → 262 and 171 → 5. The delta (166
   registrations) is unchanged; the absolute after-gap is 5, not ~4, because
   the base carries a different gap composition.
2. **The harness did not match the current config page.** `tools/shortcut-harness/harness.cpp`
   had been extended for S6 against a `QTreeWidget` + quick-filter-combo +
   count-label config page that does not exist yet; `run.sh` failed with
   `harness could not find tree/filter/combo/count`. I restored a
   `QTableWidget` harness (the page is a 4-column `QTableWidget`) that drives
   the real `checkConflicts()`. This is committed as `64ca0b1`.
3. **`actionaudit.py` could not see blank registrations.** `collect_registrations`
   required 4 arguments, so the 3-argument blank calls were invisible to the
   gap metric. Fixed to accept 3 (`len(args) < 3`) so the metric reflects them.
4. **"22 owner `.cpp` files" is really 21 `.cpp` files + `shortcutmanager.h`.**
   The header is the 22nd modified file, not a 22nd owner.
