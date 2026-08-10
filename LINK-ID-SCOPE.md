# Scope: "Link ID" for folio-reference arrows

**Status:** **ON HOLD — waiting on database work to land first.** Design + pre-implementation review complete; no code written.

Reason for the hold: §11.2 found that the `element_info` SQLite table's columns are generated directly from `QETInformation::elementInfoKeys()`. Adding `link_id` therefore changes the database schema as a side effect, so this work should not start while database changes are in flight — it would collide. Revisit once that has settled.

Supersedes the approach in the closed PR #702.

---

## 1. Why

A folio-reference arrow currently displays only `%f-%l%c` — the *grid cell* of its linked partner. `Diagram::convertPosition()` returns a letter + number only; sub-cell position is discarded. With QET's default grid (`colsize="60" rowsize="80"`) and arrow elements of `30×20`, **up to 8 arrows share one cell reference**. A bundle of wires crossing between pages — the ordinary case — produces several arrows all reading `2-C3`, with no way to tell them apart.

QET's partial mitigation is the wire number, which *is* unique per potential and *does* propagate across report links (`relatedPotentialConductors()` traverses folio reports). But it is optional, and it lives on a separate text object on the conductor, so the arrow's own reference is not self-sufficient.

**Goal:** give each linked pair a short identifier, identical at both ends, that proves two arrows are the same crossing — independent of grid density and of whether wire numbering is in use.

`Link ID`, not "Device ID": an arrow is not a physical device. The identifier belongs to the *crossing*, not to a component.

---

## 2. Hard compatibility constraints

These are non-negotiable; violating any of them is what broke the previous attempt.

| Rule | Reason |
|---|---|
| **Do not change what `label` means for report arrows.** | For reports, `label` is redefined to "where my partner is" — hard-coded in `updateReportText()`, `reportReplacedCompositeText()` and `zoomToLinkedElement()`. Auto-numbering writing its own value into `label` is exactly what collided last time. |
| **Keep `%f-%l%c` working and displayed.** | ID identifies; location navigates. Both are needed — that's the two-part scheme this is modelled on. |
| **Old QET must still open new files.** | Better than tolerated — see §2.1: old builds *retain and re-save* the key intact. |
| **New QET must still open old files.** | Achieved: missing key ⇒ empty Link ID ⇒ renders as today. |
| **Existing drawings must not change behaviour.** | Achieved: numbering is driven by a project-level Renvois rule that no existing project has. No rule ⇒ no IDs ⇒ nothing happens. |
| **No forced migration of existing projects.** | See §6 — the elements-repo change becomes a convenience, not a prerequisite. |

### 2.1 Why this is safely backward compatible (verified)

`DiagramContext` — which backs `<elementInformations>` — is **schema-free in both directions**:

- `DiagramContext::fromXml()` accepts any `name`/value pair; there is no whitelist and no validation against `elementInfoKeys()`.
- `DiagramContext::toXml()` writes back *every* key present in the hash.

So an older QET build does not merely open a file containing `link_id` — it **loads it, keeps it, and re-saves it unchanged**. A project can round-trip through an older version without losing Link IDs. That is a stronger guarantee than most format additions get, and it is what makes this design safe to ship incrementally.

> **Implementation caveat:** `toXml()` skips `elementInformation` entries whose value is empty. A *seeded but blank* `link_id` therefore will **not** survive a save/load cycle. §6.1 depends on the key being present for the text-binding dropdown, so seeding must happen at runtime (on element construction/load), not by relying on file persistence.

---

## 3. Design

Add one element-information key, `link_id`, stored **locally on both arrows of a pair**.

```
<elementInformations>
    <elementInformation name="link_id" show="1">12</elementInformation>
</elementInformations>
```

### Why store it on both ends rather than mirroring live

This is the single most important improvement over the previous attempt. Because the value is *local*, it renders through the ordinary element-info path — exactly like `comment` or `function` — via `elementInfoChanged()`.

That means:
- **no new update path**, so nothing competes with `updateReportText()`; the two-writers race is structurally impossible
- **no live cross-element evaluation**, so nothing to go stale, nothing to re-wire on load
- **each element round-trips independently** in XML
- if the partner is deleted, this arrow keeps a meaningful value instead of blanking

The link itself stays UUID-based, exactly as now. The Link ID is an *attribute of the pair*, not the linking mechanism.

---

## 4. Improvements on the original plan

The plan as proposed is sound. Six changes I'd make — §4.6 is the one that matters most at scale:

### 4.1 Asymmetric assignment — the *out* arrow owns the number

An earlier draft of this scope said "assign at link time." **That is wrong at scale**, and §4.6 explains why. The correct split is asymmetric:

| | Link ID at placement |
|---|---|
| **Going / out arrow** | Yes — auto-numbered. It originates the crossing. |
| **Coming / in arrow** | No. It receives an ID by *matching* an existing out arrow. |

This still satisfies the original complaint exactly — that complaint was specifically that placing a **Coming** arrow consumed a number it had no business owning. It does so without breaking bulk workflows.

Once an in arrow's Link ID matches an unlinked out arrow's, they link automatically. So "numbers are the link" — but on a dedicated field, with `label` untouched, which is what makes it viable this time.

Hook: `LinkElementCommand::redo()` has an `AllReport` branch guarded by `m_first_redo` that already reconciles properties across a newly-formed link — the right place for reconciliation and validation.

> Note: that existing branch is additionally gated on both elements having conductors. Link ID handling must run regardless of whether conductors are attached.

### 4.2 Gap-filling has an undo trap that must be specified

The rule "reuse the lowest free number" interacts badly with undo:

1. Link #5 is deleted → 5 becomes free
2. A new link is created → takes 5
3. **Undo the deletion** → two live links both numbered 5

This is a genuine correctness bug, and the previous prototype did not handle it. Options, in preference order:

- **(a)** Re-validate on undo: when a delete is undone, if its ID is now taken, assign a fresh one. Requires the restore path to check.
- **(b)** Don't return an ID to the pool until it leaves the undo stack. Cleaner semantically, awkward to implement.
- **(c)** Accept and detect: allow the collision but surface duplicates (see §4.3).

Recommend **(a) + (c)**.

### 4.3 Duplicate detection is needed regardless

Manual editing, copy/paste, undo, and merging work from two people all make duplicate IDs reachable. The feature is worthless if a duplicate passes silently — the whole point is that the ID *proves* identity. Minimum: flag duplicates visibly (the existing `Element::setHighlighted()` / dangling-link popup patterns are precedents).

### 4.4 Make gap-filling optional (default on)

Reusing numbers is right for you and wrong for some others: across drawing revisions, if rev A's link 5 is a pump feed and rev B's link 5 is a lighting circuit, anyone diffing printouts is misled. Some documentation regimes forbid reuse for that reason.

A per-project checkbox next to the Renvois rule — "Reuse freed numbers" — costs almost nothing and defaults to on, matching your preference.

### 4.5 Reconcile, don't clobber, when both ends already have IDs

Re-linking two arrows that each already carry a different ID needs an answer. QET has an established UX for precisely this: `PotentialSelectorDialog` asks which properties to keep when linking merges two potentials. Follow it — offer both values, let the user pick, apply to both ends.

---

### 4.6 Bulk pairing — the 100-arrow problem

Click-to-pair does not scale. Place 100 out arrows on one page and 100 in arrows on another and there is no way to know which pairs with which — the picker just lists 100 near-identical candidates.

**How other packages avoid this:** they don't pair by clicking at all. The identifier *is* the pairing key, assigned when the arrow is placed, and the link is derived by matching it.

- **EPLAN** — interruption points pair automatically by identical *name*. Give both ends the same name and they are linked; cross-references generate themselves. There is no pick-your-partner step.
- **AutoCAD Electrical** — source/destination signal arrows. The source carries a signal code; when placing a destination you choose from a list of *unmatched sources*, so the candidate set is only ever the genuinely available ones.
- **E3.series / SEE Electrical** — connections carry signal names; cross-referencing follows from the name.

QET is the outlier: it pairs by UUID through a manual picker, and derives the displayed text from geometry.

Three mechanisms, in order of value:

1. **Seed the Link ID from the wire number where one exists.** QET already propagates wire numbers across potentials (`relatedPotentialConductors()` traverses folio reports). Where wires are meaningfully numbered on both pages, pairing is then free and needs no new UI. *Caveat: numbers only propagate once linked, so this helps for hand-numbered or pre-numbered wires, not for auto-numbered ones — chicken-and-egg.*
2. **A batch "match folio references" dialog.** Two columns — unmatched outs, unmatched ins — with auto-match by wire number or by geometric order (top-to-bottom), manual override on any row, applied as one undo command. This is the direct answer to the 100-arrow case and the single highest-value addition to this scope.
3. **Filter the existing picker to unmatched candidates only**, and make Link ID the first, searchable column. Cheap; strictly better than today even without (2).

**Consequence: duplicate detection becomes load-bearing, not hygiene.** Once the ID is the pairing key, a duplicate is an ambiguous link, not merely a confusing label. §4.3 must block or hard-flag duplicates rather than quietly warn.

**Keep UUID as the binding.** Use the Link ID to *form* the link, and the existing UUID reference to *hold* it. Renumbering afterwards then never silently unlinks anything — which is the main risk of a pure match-by-name scheme.

---

## 5. Lifecycle

| Event | Behaviour |
|---|---|
| Place **out** arrow | Allocate a Link ID (§4.1). |
| Place **in** arrow | No Link ID. Nothing consumed. |
| Set an in arrow's ID to match an unlinked out arrow | Auto-link the pair. |
| Link via the picker, in arrow has no ID | Adopt the out arrow's ID. |
| Link, both ends have different IDs | Prompt (§4.5). |
| Set an ID that duplicates a live one | Block or hard-flag — the ID is the pairing key (§4.6). |
| Unlink | Clear on both ends; return the ID to the free pool. *An unlinked arrow showing a link's ID would be misleading.* |
| Delete one arrow of a pair | Partner is unlinked by existing code ⇒ same as Unlink. |
| Copy / paste | Clear. `newUuid()` already breaks the link, so the copy is not the same crossing. **Add `link_id` to the reset list in `diagramcommands.cpp`** alongside `label`/`comment`/`location`. |
| Undo / redo | Must not produce duplicates — §4.2. |
| Save / load | Plain element info; no special handling. |
| Manual override | Allowed — see §6.2. |

---

## 6. Display, and why the migration wall disappears

The previous attempt stalled here: the arrow has one dynamic text, `label` owns it, and adding a second one means changing `.elmt` files in the separate **qelectrotech-elements** repo — which existing projects would never pick up, because they embed their own copy of the element definition under `<collection>`.

That blocker is avoidable.

### 6.1 QET already lets a dynamic text bind to any element-info key

`DynamicElementTextModel` builds its info dropdown from `QETInformation::elementInfoKeys()`, filtered to keys the element actually carries (`if(dc.contains(info))`). So once `link_id` is a registered key **and present on the element**, a user can add a text bound to it through the existing *texts* tab — in an existing project, with no new element definition and no migration.

Implication: **seed `link_id` (empty) on report arrows** so the key exists and is bindable before the first link.

### 6.2 Recommended rollout

1. Register `ELMT_LINK_ID = "link_id"` in `qetinformation.{h,cpp}`, add to `elementInfoKeys()` and `translatedInfoKey()`.
2. Seed the empty key on report arrows.
3. Ship a `link_id` field in the *Folio referencing* tab for viewing and manual override — report arrows get no `ElementInfoWidget`, so this is where it belongs.
4. **Optionally** add a second `<dynamic_text>` to `01coming_arrow.elmt` / `02going_arrow.elmt` upstream, so newly-placed arrows show it without setup.

Step 4 becomes a nicety. Steps 1–3 alone deliver the feature to every existing project.

---

## 7. Numbering engine

Reuse the `NumerotationContext` machinery, including the "Renvois" category and the Préfixe/Suffixe work from the closed PR — that part was sound and is independent of what broke.

Specification points the original plan leaves open:

- **"In use" is defined as:** the set of non-empty `link_id` values on report arrows in the project. Compute from current document state; never from a persisted counter, which is what drifts.
- **Compare rendered labels, not raw counters** — with a prefix/suffix rule, `R1-A` is the identity, not `1`.
- **Non-numeric parts:** gap-filling applies only when the rule contains a plain `unit`/`ten`/`hundred` part. Alpha and cyclic (wrap) rules keep increment-only behaviour; say so in the UI rather than guessing.
- **The dock's "next value" preview must reflect gap-filling**, or it will contradict what actually gets assigned.
- **Performance:** a naive scan is O(n) per link with a formula render per candidate. Fine for hundreds of links; cache the in-use set per project and invalidate on link add/remove if it becomes hot.

---

### 7.1 Explicit non-goal: one-to-many signals

AutoCAD Electrical lets one source feed several destinations. QET's `ReportElement` is strictly 1:1 — `linkToElement()` calls `unlinkAllElements()` before storing the new partner, and the class comment states there must be only one linked element. Supporting 1:many would mean reworking the report link model itself and is **out of scope**; adopt ACE's *pairing* model, not its cardinality.

---

## 8. Decisions still needed

1. **Clear or keep the ID on unlink?** Recommended: clear (§5). Keeping it makes re-linking restore the old number, which is friendlier but means an unlinked arrow displays a link ID.
2. **Is the ID scoped per project, or per project + folio range?** Assumed per project.
3. **Should linking also offer to sync the wire number?** The potential merge already prompts for conductor properties; adding Link ID to the same dialog may be tidier than a second prompt.
4. **Duplicate handling: warn, auto-renumber, or block?** §4.3 assumes warn.

---

## 9. Implementation checklist

| Area | File(s) |
|---|---|
| Register the key | `sources/qetinformation.{h,cpp}` |
| Batch match dialog (§4.6) | new — modelled on `sources/ui/linksingleelementwidget.*` |
| Seed on report arrows | `sources/qetgraphicsitem/reportelement.cpp` |
| Assign / reconcile on link | `sources/undocommand/linkelementcommand.cpp` (`redo()`, `AllReport` branch) |
| Free-number allocation | new helper; numbering via `sources/autoNum/` |
| Clear on paste | `sources/diagramcommands.cpp` (reset list) |
| UI: view + manual override | `sources/ui/linksingleelementwidget.{h,cpp,ui}` |
| UI: "reuse freed numbers" option | `sources/ui/configpage/projectconfigpages.cpp` (Renvois tab) |
| Optional element change | `qelectrotech-elements` repo — arrow `.elmt` files |

**Explicitly not touched:** `dynamicelementtextitem.cpp`. If this scope ends up needing changes there, the design has drifted back toward the failure mode of the previous attempt.

---

## 10. Test plan

1. Place Coming and Going arrows — neither takes a number; existing `%f-%l%c` still renders.
2. Link them — both show the same Link ID; one undo reverts link *and* ID.
3. Save, close, reopen — ID and location reference both survive.
4. Delete one arrow — partner unlinks and clears its ID.
5. Create links 1,2,3; delete 2; create a new link — it takes 2.
6. **Then undo the deletion** — no duplicate 2 (§4.2).
7. Copy/paste a linked pair — copies carry no ID.
8. Two crossings landing in the same grid cell — identical `2-C3`, distinct Link IDs. *This is the case the whole feature exists for.*
9. Open a new-format file in stock QET — opens cleanly, Link IDs ignored.
10. Open an old file in the new build — no Link IDs, behaviour unchanged.
11. Turn off "reuse freed numbers" — allocation goes strictly monotonic.
12. **Place 100 out arrows and 100 in arrows; pair them.** Batch-match by wire number and by order; confirm one undo reverts the whole operation. *If this is painful, the feature has failed its main purpose (§4.6).*
13. Set an in arrow's Link ID by hand to match an unlinked out arrow — they link automatically.
14. Attempt to set a duplicate Link ID — blocked or hard-flagged.

---

## 11. Pre-implementation review (second pass)

Findings from a second code review, before any code is written. Two remove risk; four add work.

### 11.1 BLOCKING — the Link ID cannot be a live formula

`formula` is a **single per-element field**; `actualLabel()` evaluates that one string. There is no per-key formula, so there is nowhere to put a `link_id` formula that re-evaluates.

Consequence: the Renvois rule must compute the Link ID **once, at assignment, and store a literal string**. Prefix/suffix is applied at generation time.

This is correct behaviour for an identity — an ID that silently changed would defeat the purpose. But it must be stated, because it means:

- editing the Renvois rule does **not** retroactively change existing IDs;
- therefore a **"renumber all folio references"** action is probably wanted, as an explicit, undoable operation;
- the reusable part of the autonum engine is the *allocation + undoable counter advance* (`SetAutoNumContextCommand`), **not** the formula/label pipeline.

### 11.2 Adding the key to `elementInfoKeys()` has an 18-site blast radius

`QETInformation::elementInfoKeys()` has 18 consumers. Most auto-adapt, but two matter:

- **`ElementInfoWidget::buildInterface()` renders every key for every element** except terminals. A plain resistor would gain a "Link ID" field. There is an existing precedent for type-scoping — `terminalElementInfoKeys()` — so follow it, or filter `link_id` out of this widget explicitly.
- **`DynamicElementTextModel` (the §6.1 escape from the migration wall) already self-filters** with `if(dc.contains(info))`. So the key must be in `elementInfoKeys()` for the dropdown to consider it, but it will only *appear* on elements that actually carry it. That tension resolves cleanly: register the key globally, seed it only on report arrows, and suppress it in `ElementInfoWidget`.

### 11.3 Advanced Search & Replace can bulk-rewrite report arrows

Basic S&R deliberately skips reports — it filters to `Master | Simple | Terminale | Thumbnail`. **Advanced S&R does not filter at all** (`searchandreplaceworker.cpp`, `who == 1` iterates every element). Once `link_id` is a listed info key, a user could mass-rewrite Link IDs and create duplicates across the project in one action.

Either exclude `link_id` from the S&R key lists, or validate on apply. Given §4.6 makes the ID the pairing key, exclusion is safer.

### 11.4 Auto-link-on-match must never run during file load

`Element::initLink()` restores links from stored UUIDs at load time, calling `linkToElement()`. If "matching IDs auto-link" also runs then, it can invent links that were not in the file, or race the UUID restore.

Gate the matching logic to **user-initiated edits only** — never during `initLink()` / `refreshContents()`.

### 11.5 Duplicate *out* arrow IDs make matching undefined

If two out arrows share an ID — reachable via the §4.2 undo trap, paste, or manual edit — an in arrow carrying that ID has no well-defined partner. This is the second independent reason duplicate prevention is load-bearing rather than cosmetic (§4.3, §4.6).

### 11.6 Two risks that turned out not to exist

- **No database migration needed.** The project SQLite DB is opened without `setDatabaseName()` — it is in-memory and rebuilt on every project open. The `element_info` table's columns are generated from `elementInfoKeys()`, so the new column appears automatically. Old files are unaffected.
- **BOM/nomenclature exports are unaffected.** `createElementNomenclatureView()` uses a hand-written column list, not `elementInfoKeys()`, so `link_id` will not leak into nomenclature output unless deliberately added.

### 11.7 Before building locally

The worktree currently has the **abandoned** "numbers ARE the link" prototype applied as uncommitted changes (`link-id-parked-redesign.patch`). Revert to `896c6008` before starting Link ID work, or local test results will reflect the rejected design rather than this one.

---

## Appendix: the earlier, abandoned attempt

`link-id-parked-redesign.patch` (this repo) is the uncommitted "numbers ARE the link"
prototype from the PR #702 session, preserved for salvage. It applies to
`feature/report-link-autonum` on the ispyisail fork. It contains four things:

- Coming arrows no longer consume a number on placement (`element.cpp`)
- the link picker auto-opens on placing a Coming arrow (`diagrameventaddelement.cpp`)
- a "Numéro" column in the picker (`linksingleelementwidget.cpp`)
- `actualLabel()` mirroring + gap-filling allocation (`element.cpp`, `dynamicelementtextitem.cpp`)

The first three are reusable. The fourth is the part that repurposed `label` and is
the failure mode this scope exists to avoid — see §2. The gap-filling allocator is
worth reading as a starting point, but note it does **not** handle the undo trap in §4.2.

Background: <https://github.com/qelectrotech/qelectrotech-source-mirror/pull/702> —
closed; see the post-mortem comment for why the original approach could not work.
