# IEC 81346 designation-letter work — corrective plan

Status: **All four phases done (2026-08-06).** Remaining work is
incremental: further `qet_labels.xml` batches (C4), and adding
categories that need a new `<category>` node.

Phase C result: tooling recalibrated to the project's own convention and
repurposed to propose into `qet_labels.xml`. Scoring gate went 27/71
(40 contradictions) -> **71/71 with none**. First batch is
<https://github.com/qelectrotech/qelectrotech-elements/pull/70>
(8 categories in the core trees). Four more real bugs found by sampling
out-of-sample proposals -- see the tooling commit and README.

Phase D result: issue
<https://github.com/qelectrotech/qelectrotech-source-mirror/issues/671>
(six defects, evidence-backed) and PR
<https://github.com/qelectrotech/qelectrotech-source-mirror/pull/672>
(rewrite of `elementPrefixForLocation()`, 115 lines → ~50 + helper).
D1–D6 all addressed. The highest-impact one (D3, relocated collection
silently losing every prefix) was reproduced with a clean A/B and is
the likely cause of the long-standing forum reports.
Written 2026-08-06 after review of discussion #666, PR #668, PR #69.

Phase A result: closing comment posted and PR #69 closed —
<https://github.com/qelectrotech/qelectrotech-elements/pull/69#issuecomment-5201522579>

Phase B result: PR #668 amended (single clean commit, net diff vs
master is just dynamicelementtextitem.cpp + element.cpp) and
force-pushed — <https://github.com/qelectrotech/qelectrotech-source-mirror/pull/668>.
All 4 verification checks in B4 passed; a real, previously-latent
constructor-ordering bug was found and fixed along the way (not in
the original plan text — see the commit message and PR description
for detail). Next: Phase D (elementPrefixForLocation() bugs), then
Phase C (tooling repurposed as a qet_labels.xml proposal generator).

Read this whole file before touching anything. It exists because the first
attempt built a parallel system in ignorance of one that already shipped;
the point of the plan is to undo that cleanly, not to rebuild it.

---

## 0. What was discovered (facts, all verified — do not re-litigate)

QElectroTech **already has** a per-category designation-letter system:

- **Data**: `10_electric/qet_labels.xml` in the `qelectrotech-elements` repo.
  50 `<prefix>` entries; a category with no prefix inherits its parent's.
- **Code**: `autonum::elementPrefixForLocation()` —
  `sources/autoNum/assignvariables.cpp:714-829`. Called from `Element`'s
  constructor (`sources/qetgraphicsitem/element.cpp:119`) into `m_prefix`,
  read back via `Element::getPrefix()` (`element.cpp:1674`).
- **Surfaced** through the `%prefix` variable in a label formula
  (substituted at `assignvariables.cpp:395`).
- **Verified working live** on current master: placed a coil from
  `10_allpole/310_relays_contactors_contacts/01_coils`, set its label
  formula to `%prefix`, it rendered `K`. It is not broken.
- The QET manual already documents IEC 81346 letters officially:
  <https://download.qelectrotech.org/qet/manuals/html/users/element/properties/element_numbering.html>

Measured comparison of that system vs what PR #69 seeded:

| | `qet_labels.xml` | PR #69 |
|---|---|---|
| entries | 50 | 482 |
| effective coverage | 72 categories / 654 elements (9.5%) | 495 / 5003 (72.3%) |
| curation | hand-written | auto-derived keywords |

On the 72 categories both cover: **27 agree, 45 disagree (62% conflict).**
Several PR #69 letters are outright wrong (resistors→`K` should be `R`;
terminal strips→`U` should be `X`; heatings→`M` should be `R`;
timers→`K` should be `H`). Root cause: `tools/iec81346/letters.json` was
built from IEC 81346-2:2019 and marks `L`/`V`/`Y` "reserved, never used",
but the project's actual convention uses `L` (inductors), `V` (diodes),
`Y` (valves) plus compound codes `RB`, `KF`, `YB`, `EH`. **The tooling was
calibrated against the wrong edition of the standard.**

Forum context (`scorpio810` pointed at this in PR #69):
- <https://qelectrotech.org/forum/viewtopic.php?id=2178> — devs ask the
  community to help **populate `qet_labels.xml`**. Path breakage referenced
  there was fixed Oct 2023; confirmed — 24 of 364 listed paths are stale but
  **zero of the prefixed ones**.
- <https://qelectrotech.org/forum/viewtopic.php?id=1090> — *"if the labels
  file is in my custom collection, it will not work."* Still unfixed.
- <https://qelectrotech.org/forum/viewtopic.php?id=2651> — request to
  relocate the file for a shared team library. No dev reply.
- <https://qelectrotech.org/forum/viewtopic.php?id=1599> — a community
  Python tool that generates `qet_labels.xml` already exists. Precedent.

---

## Phase A — Close PR #69 (elements repo)

**Why**: it is a second source of truth for a concept that already has one,
and it contradicts the curated data on 62% of the overlap.

1. Post a closing comment on <https://github.com/qelectrotech/qelectrotech-elements/pull/69>
   that says plainly: the PR was written without noticing `qet_labels.xml`;
   it duplicates and contradicts it; closing in favour of contributing
   `<prefix>` entries to that file instead (Phase C). Thank `scorpio810`
   for the pointer — it was the correct and load-bearing correction.
   Include the 27-agree / 45-disagree number and 2–3 concrete wrong letters,
   so the closure is evidence-backed rather than vague.
2. Close the PR. Leave branch `feature-iec81346-designation-letters` on the
   `ispyisail` fork for reference; do **not** merge or delete yet.

**Done when**: PR shows closed with the explanatory comment.

---

## Phase B — Rework PR #668 (source-mirror)

**Why**: one idea in it survives review — `%prefix` only resolves when the
user manually types it into a formula, so nothing shows a letter *before*
numbering is configured. That is exactly discussion #666's state 1. Keep
that; drop everything that forked the data model.

Branch: `feature-iec81346-designation-letter` in `/home/user/qet-fix`
(current head `988ec4641`).

### B1. Revert the parallel mechanism entirely

Restore these three to `master` state:
- `sources/ElementsCollection/elementslocation.h` — remove `designationLetter()` decl
- `sources/ElementsCollection/elementslocation.cpp` — remove the whole method
- `sources/qetxml.cpp` — remove the `designation-letter` carry-over block

Easiest: `git checkout master -- <those three paths>`.

### B2. ⚠ Do NOT put the placeholder in `Element::actualLabel()`

The original PR did, and it is a **latent data-corruption bug**. Five call
sites write `actualLabel()`'s result back into the stored label:
`element.cpp` lines **1396, 1445, 1487, 1523, 1664**, e.g.

```cpp
const auto actual_label{actualLabel()};
if (!actual_label.isEmpty()) {
    m_data.m_informations.addValue(QStringLiteral("label"), actual_label);
}
```

So returning `"K?"` there would **persist `K?` into the project file as a
real, user-authored label** — permanently, and it would then win over any
later formula. (The original PR's own code comment claims the opposite.
The comment is wrong.)

### B3. Put it at display time instead

Both places that render a label call `element->actualLabel()` then
`setPlainText()`, in `sources/qetgraphicsitem/dynamicelementtextitem.cpp`:
- `elementInfoChanged()` — around line **824**
- the `updateXref`-adjacent block — around line **1096**

Add a small file-local helper and use it at both sites:

```cpp
// Purely presentational: when an element has no formula and no label yet,
// show its qet_labels.xml classification letter with a "?" so the folio
// reads as intentionally-unnumbered rather than blank. Never returned by
// Element::actualLabel(), because that value gets written back into the
// element's stored data (element.cpp:1396 et al) and would turn a
// placeholder into a real saved label.
static QString displayLabelFor(Element *element)
{
    const QString label = element->actualLabel();
    if (!label.isEmpty())
        return label;
    const QString prefix = element->getPrefix();
    return prefix.isEmpty() ? QString() : prefix + QStringLiteral("?");
}
```

`getPrefix()` is already populated from `qet_labels.xml` in the constructor —
**no new file parsing, no new attribute, no new lookup.** Net change should
be roughly 15 lines in one file.

### B4. Verify (all four must pass)

Using the live-test recipe in §Environment below:
1. Coil with nothing configured → shows **`K?`**.
2. Set label formula to `%prefix` → shows **`K`** (placeholder gone).
3. Set a manual label `TEST99` → shows **`TEST99`**.
4. **Save the project, close, reopen** → the coil still shows `K?`, and the
   saved `.qet` XML contains **no** `label="K?"`. Confirm by grepping the
   saved file. This is the regression test for B2 — do not skip it.

### B5. Rewrite the PR description

Force-push the branch, then update PR #668's body via REST PATCH (see
§Environment). It must: reference `qet_labels.xml` as the single source of
truth, state that the placeholder is display-only and never persisted, and
say the earlier revision of this PR introduced a parallel attribute that has
been withdrawn.

No settings gate for this — decided 2026-08-06, not revisiting unless a
maintainer specifically asks for one in review.

---

## Phase D — Fix `elementPrefixForLocation()`

All in `sources/autoNum/assignvariables.cpp:714-829` (~115 lines) unless
noted. **Investigated in depth 2026-08-06; six distinct bugs found, four
of them not in the original plan draft.** There are currently **zero**
GitHub issues mentioning `qet_labels`, and `scorpio810` explicitly asked
on the forum for bug reports — so filing one is genuinely new signal.

### The bugs, in descending real-world impact

**D3 — Relocating the common collection silently kills all prefixes.
Most likely the #1 real-world complaint; fix this even if nothing else.**

`QETApp::commonElementsDir()` (`sources/qetapp.cpp:590`) returns the
settings-override path (`elements-collections/common-collection-path`)
**verbatim, with no trailing `/` appended** — unlike its sibling
`customElementsDir()`, which explicitly normalizes:

```cpp
if(!m_custom_element_dir.endsWith("/")) { m_custom_element_dir.append("/"); }
```

Line 788 then does naive string concatenation:

```cpp
QString filepath = QETApp::commonElementsDir().append(qet_labels);
```

giving `<user-path>10_electric/qet_labels.xml` — a mangled path, file not
found, `return QString()`, prefixes silently stop working with no error
anywhere. The default install is unaffected because both build systems
bake in a path that happens to end in `/`
(`cmake/paths_compilation_installation.cmake`, `qelectrotech.pro`) — which
is exactly why this never shows up for developers.

This matches the forum reports precisely: thread 2651 (wants to relocate
the file to a shared team library) and pjstecheng's 2026 report in thread
2178 (broken "when element files and qet_labels.xml are **not in the
default directory**").

Note the `#ifndef QET_COMMON_COLLECTION_PATH` fallback at
`qetapp.cpp:622` — `applicationDirPath() + "/elements"` — also lacks the
slash, so hand-rolled builds hit this too.

Surveyed the blast radius: **exactly one** caller in the codebase
concatenates directly onto `commonElementsDir()`, and it is this line.
So fix it locally with a proper path join rather than changing
`commonElementsDir()`'s contract — lower risk, easier review. Mention the
API inconsistency in the issue and let maintainers decide whether to
normalize it.

**D2 — Every common-collection sub-tree except `10_electric` reads the
wrong file.**

The branch condition is:

```cpp
if (current_location.fileName() != "10_electric") { /* read CUSTOM collection */ }
else                                              { /* read COMMON collection */ }
```

Verified against the real `qelectrotech-elements` repo: the common
collection ships **five** top-level trees — `10_electric`, `20_logic`,
`30_hydraulic`, `50_pneumatic`, `60_energy` — and **only `10_electric`
contains a `qet_labels.xml`**. So an element from `20_logic` fails the
test, takes the custom branch, and tries to read the *user's*
`customElementsDir()/qet_labels.xml`: wrong collection entirely.

Root cause is architectural, and worth stating plainly in the issue:
once an element is imported into a project its location is
`embed://import/<original collection path>` — `XmlElementCollection::addElement()`
builds it as `"import/" % location.collectionPath(false)`, and
`collectionPath(false)` strips the `common://` / `custom://` / `company://`
protocol. **The originating collection is genuinely not recoverable**
post-import, which is why the code resorts to guessing from a hardcoded
folder name. The honest fix is to stop guessing: try each collection's
labels file in turn and use the first that both exists and matches.

**D4 — Company collection unhandled.** `QETApp::companyElementsDir()` is
a third collection; it falls into the "custom" branch. Same fix as D2.

**D1 — Stack buffer overflow.**

```cpp
QString path[10];
int i = -1;
while (...) { i++; path[i] = current_location.fileName(); ... }   // unbounded
```

Deepest category in the shipped collection is **8** levels, +1 for the
element itself = 9 slots — it fits, with one to spare. A user's custom
collection can nest arbitrarily deep, and nothing bounds the loop. This
is a stack write past the end of an array of `QString` objects, i.e.
memory corruption, not a clean crash. Dissolves entirely if the array
becomes a `QStringList`.

**D5 — The XML matching is structurally unsound.**

The scan is a flat token walk that matches any element whose `name`
attribute equals `path[i]`, decrementing `i` on each hit, with **no
verification that the match is actually a child of the previous match**.
It works on the shipped file only because depth-first document order
happens to align with the hierarchy.

The inheritance rule ("a directory with no prefix uses its parent's") is
implemented by scanning *forward* with `readNextStartElement()` /
`skipCurrentElement()`, which can only ever move deeper or sideways —
never back up to the parent. It produces the right answer solely because
the file format mandates that `<prefix>` appear *after* child
`<category>` elements, so an ancestor's prefix is always downstream in
document order. That constraint is documented in `qet_labels.xml`'s own
header comment — the data format is contorted to suit this parser. A
correct parser removes the constraint (while still reading existing
files fine). A category with no prefix whose parent also has none can
mis-attribute a following sibling's prefix.

**D6 — Dead code and duplication.** `file.isReadable();` at lines 748 and
790 discards its return value and does nothing. The common and custom
branches are ~40 lines of copy-paste differing only in the file path.

### Recommended approach: rewrite, don't patch

D1 and D5 both dissolve if the function is rewritten with `QDomDocument`
(or a proper recursive `QXmlStreamReader` walk) instead of the flat scan:
roughly 115 lines → ~50. Piecemeal patches to this parser would be harder
to review than a clean replacement, and D2/D3/D4 all need the
collection-resolution logic reworked anyway.

Shape of the replacement:

1. Build the path as a `QStringList` (no fixed array, no `dirLevel`
   bookkeeping).
2. Build a candidate list of labels files — common (`10_electric/` and,
   if present, any other top-level tree), custom (root), company — using
   `QDir`/`QDir::filePath()` for joining, never `.append()`.
3. Parse with `QDomDocument`; walk `<category name=...>` by *actual
   nesting*, matching each path segment against direct children only.
4. Resolve the prefix by walking back **up** the matched chain, taking
   the first ancestor that has one — explicit, order-independent, and
   backward-compatible with files that put `<prefix>` after children.
5. Return the first candidate file that yields a match.

Keep the existing `if (!location.isProject()) return QString();` guard —
the prefix is only meaningful for project-embedded elements.

### Verification

Reproduce each before fixing, and re-check after. Use the live-test
recipe in §Environment (install the real collection, place an element,
set the label formula to `%prefix`; or rely on the Phase B placeholder,
which now surfaces the prefix with no formula at all — considerably
faster to eyeball).

- **D3**: set a custom common-collection path in
  Configuration → paths *without* a trailing slash, restart, confirm
  prefixes break before the fix and work after.
- **D2**: place an element from `20_logic` and confirm it does not read
  the custom collection's file. (Note `20_logic` ships no labels file at
  all, so the correct post-fix result is "no prefix" — verify it is
  reached by the right path, e.g. via a temporary qet_labels.xml placed
  in `20_logic/`.)
- **D1**: construct a custom collection nested >9 levels deep and place
  an element from it. Expect corruption/crash before the fix.
- **D5**: a category whose parent has no `<prefix>` but whose following
  sibling does — confirm it no longer inherits the sibling's.

### Deliverables

1. **One GitHub issue** documenting all six with the evidence above,
   referencing forum threads 2178, 1090 and 2651. This is what
   `scorpio810` asked for and none exists today.
2. **One PR** with the rewrite, referencing that issue. Separate from
   #668 — different concern, and #668 should not be held up by it.

---

## Phase C — Repurpose the tooling as a `qet_labels.xml` proposal generator

This is the largest phase and the least urgent. Its output is a reviewable
**proposal**, never a direct bulk write.

### C1. Recalibrate to the project's actual letter convention

`tools/iec81346/letters.json` is calibrated to the wrong edition. Rebuild
the mapping from the project's own usage as ground truth: `L`=inductors /
current transformers, `V`=diodes, `Y`=valves, `R`=resistors and heating,
`P`=sensors and measuring instruments, `S`=contacts and manual switches,
`F`=fuses/breakers/thermal relays, plus compound `RB`, `KF`, `YB`, `EH`.

### C2. Use the 72 overlapping categories as a labelled test set

This is the key idea: `qet_labels.xml`'s 50 curated entries expand to 72
categories with a known-correct answer. Add a scoring script.

**Current score: 27/72. Target: ≥70/72 before proposing anything new.**

When the tool disagrees with a curated entry, the curated entry is right and
the keyword rules are wrong — fix the rules, never the expected value.

### C3. Emit `qet_labels.xml` `<prefix>` entries, not a new attribute

Rewrite `tools/iec81346/seed_categories.py` → `propose_labels.py`:
- reads the real `qet_labels.xml`
- **never modifies a category that already has a `<prefix>`**
- emits only additions, preserving the file's existing structure, and
  honouring its documented rule that `<prefix>` comes *after* child
  `<category>` elements
- writes a review CSV alongside the patch

### C4. Submit in small, reviewable batches

Not 482 categories in one PR. Start with one coherent subtree (e.g.
`10_allpole/390_sensors_instruments`), get review feedback on letter choices,
then continue. State plainly in each PR which entries are machine-proposed
and what the test-set score is.

### C5. Delete the dead seeding path

Once C3 exists, remove `designation-letter` handling from the tooling
entirely so nothing regenerates the withdrawn attribute.

---

## Environment gotchas (all hit at least once this session — read before building)

**SingleApplication collision.** Run `docker ps` first. If
`qet-testbuild` is up, it shares the host network namespace and a native
test binary gets silently absorbed into it as a secondary instance. Work
around by temporarily changing `QCoreApplication::setApplicationName()` in
`sources/main.cpp` — **and revert it before every commit.** It was left in
by accident more than once.

**Native builds have no element collection.** `commonElementsDir()` is
`/usr/local/share/qelectrotech/elements/` and is empty on this machine, so
`qet_labels.xml` will not be found and `%prefix` silently returns "". To
live-test anything prefix-related:

```bash
sudo mkdir -p /usr/local/share/qelectrotech/elements/
sudo cp -r /home/user/qelectrotech-docker/elements-10-electric/10_electric \
           /usr/local/share/qelectrotech/elements/
# ... test ...
sudo rm -rf /usr/local/share/qelectrotech/elements/10_electric   # clean up after
```

**Live-test recipe** (what worked): build dir
`/tmp/claude-1000/.../scratchpad/qet-build-pr633` (ninja, target
`qelectrotech`); `DISPLAY=:99` (Xvfb already running); launch with a
throwaway `HOME=` so the config is clean. Then: `Fichier > Nouveau` (Ctrl+N
alone did not create a project), type a term in the Collections search box —
it matches **display names, not filenames** (`coil` works, `bobine3` does
not) — then drag from the panel with **small incremental
`xdotool mousemove_relative` steps**; a single jump does not trigger Qt's
drag threshold. Press `Escape` after dragging or the next canvas click
places another copy. Select one element, then use the
`Propriétés de la sélection > Informations` tab, which exposes the
`Formule du label` and `Label` fields directly — far more reliable than the
auto-numbering dialogs, which never responded to automation here.

**Build side-effects.** Builds regenerate `lang/*.qm`. Run
`git checkout -- lang/*.qm` before committing or they pollute the diff.

**CSV parsing.** `tools/iec81346/report.csv` has quoted fields containing
commas. `awk -F','` silently produces garbage on those rows — use Python's
`csv` module.

**GitHub quirks on these repos.** `gh pr edit` fails with a Projects-classic
GraphQL error; update PR bodies with
`gh api repos/<owner>/<repo>/pulls/<n> -X PATCH -f body="$(cat file.md)"`
and re-read the body afterwards to confirm it landed. `gh pr create` must
use `--base master` for source-mirror (`--base main` for the elements repo).

---

## Recommended order

**A → B → D → C.** A and B are one conversation with the maintainers and
should land together. D is independent and probably the most immediately
useful thing to the project. C is a longer tail and should not block the
others.
