# Quick element insertion — scope document

Implementation scope for making element placement in QElectroTech fast without a
mouse drag.

**Verified against** `qelectrotech-source-mirror` master `7307a59c1`.
Every file:line reference below was checked against that tree — re-verify before
relying on them if master has moved significantly.

**Status:** design agreed, nothing implemented. Phase 1 is the recommended first PR.

---

## 1. The finding this whole document rests on

QET already has a good element-placement interaction. It has grid snapping,
element rotation, automatic terminal wiring, undo integration, and it stays
loaded so you can place the same symbol repeatedly.

It is called `DiagramEventAddElement`, and it has **exactly one entry point in
the entire codebase**:

```
$ grep -rn "DiagramEventAddElement" sources/ --include=*.cpp | grep -v diagrameventaddelement.cpp
sources/diagramview.cpp:223
```

That call site is inside `DiagramView::handleElementDrop()`. The only way to
reach the fast path is to complete a drag-and-drop from the Collections dock.

Meanwhile the most natural alternative gesture is bound to the slowest possible
action — double-clicking an element in the Collections tree calls
`editElement()`, which opens an Element Editor window
(`sources/ElementsCollection/elementscollectionwidget.cpp:268`).

**The engine is built. There is one door, and it is the slow one.**

The scope below is therefore mostly *wiring*, not construction. This matters for
how the work is pitched: it is not "add a feature", it is "expose one that
already exists".

---

## 2. Verified inventory — what already exists

Do not rebuild any of these.

| Capability | Where | Notes |
|---|---|---|
| Place mode: ghost item follows cursor, grid-snapped | `sources/diagramevent/diagrameventaddelement.cpp` `mouseMoveEvent` | uses `Diagram::snapToGrid()`, so it follows the user's configured grid |
| Left click places, **stays loaded for repeats** | same, `mouseReleaseEvent` → `addElement()` | commits via `AddGraphicsObjectCommand` under a parent `QUndoCommand` named `tr("Ajouter %1")` |
| Right click / double click cancel | same | |
| Esc cancels | `sources/diagramevent/diagrameventinterface.cpp:60` | base-class default for every diagram event |
| `Space` rotates the pending element 90° | `sources/diagramevent/diagrameventaddelement.cpp:174` | **see §7.1 — this is a hotkey trap** |
| Auto-connect aligned free terminals on placement | `diagrameventaddelement.cpp` `addElement()` | honours the project's `autoConductor()` setting |
| Search index over display name **and every element-info field** | `sources/ElementsCollection/fileelementcollectionitem.cpp:303-329` | builds `QStringList` from `ElementsLocation::elementInformations()` (description, manufacturer, manufacturer_reference, …) + `localName()`, stored at `Qt::UserRole+1` |
| Index built **eagerly at startup, multithreaded** | `sources/ElementsCollection/elementscollectionmodel.cpp:297` | `QtConcurrent::map(m_items_list_to_setUp, setUpData)` — the whole collection is indexed and resident before the user types anything |
| Thumbnail cache (SQLite) | `sources/elementscollectioncache.cpp` | tables `names(path, locale, uuid, name)` and `pixmaps(path, uuid, pixmap)`; lazily filled via `ElementsLocation::icon()` |
| Search field with debounce | `elementscollectionwidget.cpp:189`, timer at `:77` | 500 ms debounce, 3-character minimum (`:947`) |
| Search filters by hiding tree rows | `elementscollectionwidget.cpp:999` | `m_tree_view->setRowHidden(...)` — **view state, not model state**. See §7.2, this is load-bearing. |
| User-definable palette: own folder tree | Collections context menu → New directory | `QETApp::customElementsDir()` |
| Copy an element into it by dragging | `elementscollectionmodel.cpp:193` | `ElementCollectionHandler::copy()`; drops into the common collection are refused |
| Shared team collection | `QETApp::companyElementsDir()` | already a shipped, separate collection root |
| Multi-element groups | `.qetmak` macros, own tab in the dock | created via `DiagramView::createTemplateFromSelection()` |
| Rebindable shortcut registry + preferences page | `sources/shortcutmanager.h`, `sources/ui/configpage/shortcutsconfigpage.cpp` | `registerAction(target, id, category, default)` — registered actions appear in preferences automatically |
| Element drag MIME format | `application/x-qet-element-uri` | see §7.3 for a quirk |

**Absent:** any keyboard path to insertion; any recent/favourite *elements* list
(`sources/recentfiles.cpp` is recent *files* only).

### Collection scale, for sizing decisions

The shipped collection is ~8,750 `.elmt` files under 5 top-level categories
(`10_electric`, `20_logic`, `30_hydraulic`, `50_pneumatic`, `60_energy`).
`ElementsCollectionWidget::loadingFinished()` already logs the load time via
`qInfo()` — use that number rather than guessing when tuning.

---

## 3. Design principles

Carried over from the original picker spec, and still correct:

1. **Positional constancy.** Tile positions never reorder themselves. The value
   is in performing a sequence blind after a week. Frequency ordering is
   confined to a separate "Recent" surface.
2. **Type-ahead is the escape hatch.** Icons cover the top ~40 symbols; typing
   covers the remaining thousands.
3. **Non-modal accelerators.** Everything reachable by key is also clickable.
   Neither path is privileged.
4. **Place mode, not drag mode.** After selection the element follows the
   cursor; click places; it stays loaded for repeats.
5. **Latency: popup visible in well under 100 ms.** Achievable only by sharing
   the already-built model (§5.2), not by building a second one.

Added, and specific to this codebase:

6. **Add doors to rooms that exist.** Every phase below should be a new call
   site for existing machinery. If a phase requires a new search index, a new
   thumbnail path, or a new config parser, that is a signal it has been designed
   wrong.
7. **Existing drag-and-drop insertion must keep working, unchanged.**

---

## 4. Configuration: a folder, not a file

**Decision: there is no config file format. A quick palette is a folder in the
custom collection.**

Designate a folder under `QETApp::customElementsDir()` (default `__quick__`, or
any folder via a right-click "Use as quick palette"). Its subfolders become the
category tiles; their contents become the element tiles.

Rationale — every requirement a config format would have had is already met by
the filesystem plus shipped UI:

| Requirement | How the folder satisfies it |
|---|---|
| User-editable | Drag an element into it, in the dock that is already open |
| Hand-editable, diffable, version-controllable | It is a directory tree |
| Shared team palette on a network path | `companyElementsDir()` — a shipped feature built for this |
| Layering / precedence | common / company / custom already are the layers, and users already understand them |
| Fixed ordering | Filename prefixes `01_`, `02_`, … — **already the convention** in the shipped collection (`10_electric`, `20_logic`, …) |
| Icons | `ElementsLocation::icon()`, already cached |
| Missing element → placeholder + warning | A missing file simply is not in the folder |
| Customise mode | Drag it in the panel. Nothing to build. |

Consequences:

- Accelerators derive from slot position, as originally intended — and position
  is now **visible in the filename**, which reinforces positional constancy
  instead of hiding it in a file the user cannot see.
- No merge semantics, no schema, no validation, no "reset to default" logic, no
  editor mode, no spring-loaded drag targets.
- Setup instructions are one sentence.

**Store in `QSettings` only:** the resolved palette folder path, and the MRU
list. Both are small and neither is worth a file. Follow the existing key
convention, e.g. `diagrameditor/quick_palette_path`
(`sources/qetdiagrameditor.cpp:2179` shows the house style).

---

## 5. Phases

Each phase ships independently and is useful alone. Do not start a later phase
before the earlier one builds, runs, and is committed.

### Phase 1 — Insert without dragging *(recommended first PR, ~100 lines)*

Two new call sites for `DiagramEventAddElement`. No new widget, no config, no
format change.

**1a. Double-click / Enter in Collections inserts.**

`elementscollectionwidget.cpp:268` currently routes `doubleClicked` to
`editElement()`. Change it to enter place mode at the diagram view centre.
Editing stays available on the context menu (where it already lives); add `F2`
as its key.

- Route through the same `ElementsLocation` the drag path builds.
- Keep the existing `.qetmak` guard — macros go to `DiagramEventAddMacro`, as
  `diagramview.cpp:220` already does.
- Do the same for the macros tree (`:290`).

**1b. "Insert last element" action.**

- Store the last successfully placed `ElementsLocation` on `QETDiagramEditor`.
- New `QAction`, registered through `ShortcutManager::registerAction()` with id
  `diagrameditor.insert_last_element`, category `tr("Éditeur de schémas")`.
- Triggering it re-enters place mode with that location.
- Disable it when there is no last element, or the diagram is read-only.
- **Proposed default key: `A`** (see §7.1). Rebindable for free via the registry.

While implementing 1b, keep the last *N* locations rather than only one — this
is the MRU that Phase 3 needs, and it costs nothing now.

**Acceptance:** place a contactor, a fuse and three terminals using only the
keyboard and clicks on the canvas, with the Collections dock closed after the
first insertion. Existing drag-and-drop still works. Undo behaves identically to
panel insertion, including for a run of repeats.

### Phase 2 — Flat ranked search results

The existing search hides tree rows, so hits stay scattered across an expanded
tree. Add a `QSortFilterProxyModel` over the same model producing a flat, ranked
list.

- No new index — filter on the `Qt::UserRole+1` string that already exists.
- Rank exact prefix match above substring match above element-info-field match.
- Useful in the dock on its own, before any popup exists.

### Phase 3 — The picker popup

**The picker is `ElementsCollectionWidget` shown in a popup.** Not a new widget.

- `Qt::Popup | Qt::FramelessWindowHint`, moved to `QCursor::pos()`, clamped to
  `QGuiApplication::screenAt(...)->availableGeometry()`.
- Search field focused on open; Phase 2's flat list as the results body.
- Enter / double-click → Phase 1's place mode, popup closes.
- Esc closes with no side effect.
- Top row: the palette folder from §4. Bottom strip: MRU chips from Phase 1b.
- Opened by a hotkey registered through `ShortcutManager`.

Prerequisite work, and the only real engineering in this phase:

**5.2 — Hoist model ownership.** Today each `ElementsCollectionWidget` builds
its own `ElementsCollectionModel` in `reload()`
(`elementscollectionwidget.cpp:827`). A second instance would double an already
slow startup. Make it a shared singleton owned by `QETApp`.

**Precedent exists in the same class**: `QETApp::collectionCache()` is already a
static singleton (`sources/qetapp.cpp:77`, constructed at `:137`). Follow that
shape exactly — `QETApp::collectionModel()`.

**Retune for popup use.** The dock's 500 ms debounce and 3-character minimum
are right for a background panel and wrong for something opened and closed in
two seconds. Use ~120 ms and 1 character in the popup. Consider the same for the
dock, but as a separate change.

### Phase 4 — Category grid

Only after Phase 3 is in use. A grid of tiles for the palette folder's
subfolders with `1`–`8` accelerators, element tiles on the letter row, expanding
beside the category so mouse travel stays short.

This is presentation over data that Phase 3 already has. If it turns out the
flat search plus MRU is enough, this phase can be dropped without loss — decide
from use, not up front.

---

## 6. Explicitly out of scope

- **Not replacing the Collections panel.** It stays, for managing and editing
  elements. This is an additional fast path.
- **Not a radial/pie menu.** Electrical symbol sets do not fit in ~8 radial
  slots. Grid only.
- **No change to the `.elmt` format or the collection structure.**
- **No user tags.** There is no tag concept in `.elmt` today. Searching tags
  would be a separate feature; the existing index already covers description,
  manufacturer and reference, which is most of the practical benefit.
- **No new SQLite querying for search.** The in-memory model already holds a
  richer index than the cache does (§2), and it is complete at startup whereas
  the cache is lazily filled.

---

## 7. Technical notes and traps

### 7.1 `Space` is a trap; pick another key

`Space` is bound four times:

```
diagrameditor.rotate_selection          Space          qetdiagrameditor.cpp:638
diagrameditor.rotate_group_selection    Shift+Space    qetdiagrameditor.cpp:639
diagrameditor.rotate_texts              Ctrl+Space     qetdiagrameditor.cpp:640
rotate the pending element 90°          Space          diagrameventaddelement.cpp:174
```

The last one is decisive: `Space` already has a meaning *inside* place mode, so
it cannot also be the key that enters it.

**Free keys:** in the diagram editor the only bare bindings are `Delete` and
`Space`. Bare letters have precedent elsewhere in the app (`F` = flip, `M` =
mirror in the element editor).

**Proposed: `A`.** Matches KiCad's add-symbol key for the crossover audience,
and reads correctly in QET's source language ("Ajouter"). `S` (SolidWorks) is an
equally defensible alternative.

The choice is low-stakes and should be presented as such: `registerAction()`
makes it a *default*, not a commitment, and it lands in the Shortcuts
preferences page automatically.

**Inline text editing.** Bare single-key shortcuts coexist with QET's on-canvas
text editing because Qt routes `QEvent::ShortcutOverride` through
`QGraphicsScene` to the focused text control, which accepts it while editable.
`Space` already relies on this. Note that QET's own `hasTextEditing()` guard
(`sources/diagramcontent.cpp:373`) is used **only** for keys handled directly in
`DiagramView::keyPressEvent` (the arrow keys, `diagramview.cpp:785-800`), not
for `QAction` shortcuts. Worth one manual test with a new bare-letter binding
rather than assuming either way.

### 7.2 Model sharing is safe — and it is an accident worth preserving

The dock's search filters via `m_tree_view->setRowHidden(...)`
(`elementscollectionwidget.cpp:999`) and expands via `setExpanded`. Both are
**view** state, not model state. So a popup filtering aggressively will not
disturb the dock rendering the same model behind it.

Per-widget state that must stay per-widget when the model is hoisted:
`m_showed_index`, `m_index_at_context_menu`, and the search field contents.

The refactor is therefore: let `ElementsCollectionWidget` accept an
externally-owned model instead of always constructing one. Small and reviewable.

### 7.3 Drag payload quirk

`DiagramView::handleElementDrop()` checks for
`application/x-qet-element-uri` but then reads `event->mimeData()->text()`, not
the registered format's data. Both are set by the drag sources
(`elementstreeview.cpp:117`, `:215`). If any new code produces this MIME data,
set both, or the drop silently builds a null location.

### 7.4 Element URI prefixes

Five, not three: `common://`, `company://`, `custom://`, `embed://`,
`macros://` (`elementslocation.cpp:184`). There is no `embedded://`.

### 7.5 Undo stack scope

`QETProject::undoStack()` is **per project**, aggregated into a `QUndoGroup` on
the diagram editor. Anything that is not a diagram edit — UI/palette
customisation in particular — must not go on it, or Ctrl+Z after customising
will undo a menu change and the entry will persist in the project's history.

---

## 8. Open decisions

1. **Double-click behaviour change (Phase 1a).** Changing double-click from
   "open editor" to "insert" is a behaviour change for existing users. Options:
   default to insert with a preference to restore; or `Alt`+double-click to
   edit. Recommend raising in discussion before the PR, not inside it.
2. **Hotkey default** — `A` vs `S` vs something else. Low-stakes, rebindable.
3. **Palette folder discovery.** Fixed default name (`__quick__`) versus
   right-click "Use as quick palette" on any folder. The latter is more
   flexible; the former is more discoverable. Possibly both.
4. **Whether Phase 4 is needed at all** once Phase 3 plus MRU is in use.

---

## 9. Rejected alternatives, and why

Recorded so they are not re-proposed later.

| Rejected | Why |
|---|---|
| A `<quickmenu>` XML config with default/shared/user layers and merge rules | The custom collection already is a user-editable, drag-populated, icon-rendering, searchable palette, and common/company/custom already are the layers. The format would have added a schema, a parser, validation, merge semantics and a "reset to default" path to achieve what a folder achieves with none of them. |
| SolidWorks-style live customise mode: popup re-shown as `Qt::Tool`, spring-loaded category folders, drag-off-to-remove, changes on the undo stack | This was the single largest chunk of engineering in the original spec, and its entire job was to let a user say "these 40 symbols, in this order". Dragging into a folder in the dock does that today. Also depended on putting UI state on the project undo stack — see §7.5. |
| Querying the SQLite cache for type-ahead | The cache holds one name per locale plus a pixmap, is lazily filled, and carries strictly less than the in-memory model, which is complete at startup. |
| Searching user tags | No tag concept exists in `.elmt`. Separate feature. |
| `Space` as the picker/repeat hotkey | Bound four times, one of them inside place mode itself. §7.1. |
| Building a new popup widget with its own grid, search, and thumbnail cache | All three exist in `ElementsCollectionWidget`, already translated. §5 Phase 3. |
