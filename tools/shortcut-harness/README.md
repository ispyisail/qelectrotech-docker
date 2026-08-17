# shortcut-harness

Drives QElectroTech's real `ShortcutsConfigPage` offscreen, so GUI changes to
it can be verified mechanically in seconds.

```bash
./run.sh                      # against /home/user/qet-fix
./run.sh /path/to/qet-source  # against another checkout
```

It compiles the **real** `sources/shortcutmanager.cpp` and
`sources/ui/configpage/shortcutsconfigpage.cpp` standalone against Qt5 — no
QElectroTech build required. Sources are re-copied on every run, so it always
tests current code. `ConfigPage` is header-only; `QET::Icons` is stubbed to the
two symbols the page uses (the build fails loudly if it starts using another).

`harness.cpp` registers a small sample of actions — including deliberately
**blank** ones, per SHORTCUTS-PLAN §2 — then types into the real filter box and
counts visible rows.

## Baseline on master 7307a59c1

```
total rows: 4  visible: 4
  query 'Ctrl+S'      ->   0 visible   [search by key sequence]
  query 'export pdf'  ->   0 visible   [multi-keyword, different word order]
  query 'general'     ->   0 visible   [accent-insensitive]
  query 'Profondeur'  ->   1 visible   [plain category match -- control]
```

The first three zeros are the S6b gaps, measured rather than inferred. The
control proves the harness works, so a zero is a real miss and not a broken
test.

**Watch for vacuous probes.** The accent check first appeared to pass because
the harness registered the category unaccented (`"General"`); it only becomes a
real test with `Général`. A probe that cannot fail proves nothing.
