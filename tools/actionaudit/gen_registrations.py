#!/usr/bin/env python3
"""
gen_registrations — turn the actionaudit gap list into registerAction() lines.

Reads the audit JSON (produced by actionaudit.py, which now emits `target` on
every action record), selects the connected-but-unregistered actions, skips the
known noise records, and emits one `ShortcutManager::registerAction(...)` line
per remaining action together with the exact source location to insert it.

Outputs:
    reports/registrations.json — machine-readable insertion manifest
    reports/registrations.md  — human-readable plan

Usage:
    python3 gen_registrations.py [--actions-json PATH] [--source-root DIR]
                                  [--out-dir DIR]
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Fixed decisions (SHORTCUTS-S4-DECISIONS.md) — do NOT re-decide these.
# ---------------------------------------------------------------------------

# owner -> (window prefix, tr() category).  Categories reuse the existing
# tr() strings exactly so the config page does not grow near-duplicate groups.
OWNER_MAP = {
    # Éditeur de schémas
    'QETDiagramEditor':       ('diagrameditor', 'Éditeur de schémas'),
    'DiagramView':            ('diagrameditor', 'Éditeur de schémas'),
    'ProjectView':            ('diagrameditor', 'Éditeur de schémas'),
    'SearchAndReplaceWidget': ('diagrameditor', 'Éditeur de schémas'),
    # Éditeur d'élément
    'QETElementEditor':       ('elementeditor', "Éditeur d'élément"),
    'PolygonEditor':          ('polygoneditor', "Éditeur d'élément"),
    'PartPolygon':            ('partpolygon', "Éditeur d'élément"),
    'QetShapeItem':           ('qetshapeitem', "Éditeur d'élément"),
    # Éditeur de cartouche
    'QETTitleBlockTemplateEditor': ('titleblockeditor', 'Éditeur de cartouche'),
    'TitleBlockTemplateView':      ('titleblockeditor', 'Éditeur de cartouche'),
    'TitleBlockPropertiesWidget':  ('titleblockeditor', 'Éditeur de cartouche'),
    # Panneau des éléments
    'ElementsPanelWidget':     ('panel', 'Panneau des éléments'),
    'ElementsCollectionWidget': ('panel', 'Panneau des éléments'),
    # Éditeur de texte
    'RichTextEditorToolBar':   ('richtext', 'Éditeur de texte'),
    # Général
    'QETApp':                  ('qetapp', 'Général'),
    'QETMainWindow':           ('mainwindow', 'Général'),
    'ProjectPrintWindow':      ('printwindow', 'Général'),
    'TerminalStripEditorWindow': ('terminalstrip', 'Général'),
    'MasterPropertiesWidget':  ('masterproperties', 'Général'),
    'LinkSingleElementWidget': ('linksingleelement', 'Général'),
    'plclinkwidget':           ('plclink', 'Général'),
}

# The 5 actions that get a default key (decisions §2).  Keyed by
# (owner, variable name).  The expected id is asserted against the derived id.
DEFAULTS = {
    ('QETMainWindow', 'configure_action_'): (
        'QKeySequence::Preferences', 'mainwindow.configure'),
    ('ProjectPrintWindow', 'm_first_page_action'): (
        'QKeySequence::MoveToStartOfDocument', 'printwindow.first_page'),
    ('ProjectPrintWindow', 'm_previous_page_action'): (
        'QKeySequence::MoveToPreviousPage', 'printwindow.previous_page'),
    ('ProjectPrintWindow', 'm_next_page_action'): (
        'QKeySequence::MoveToNextPage', 'printwindow.next_page'),
    ('ProjectPrintWindow', 'm_last_page_action'): (
        'QKeySequence::MoveToEndOfDocument', 'printwindow.last_page'),
}


def variable_of(target):
    """The variable name a record's target refers to."""
    if isinstance(target, list) and target and target[0] == 'ui':
        return target[1]
    if isinstance(target, str) and target:
        return target
    return None


def target_expr_of(target):
    """The C++ expression to pass as registerAction's first argument."""
    if isinstance(target, list) and target and target[0] == 'ui':
        return 'ui->' + target[1]
    return target


_CAMEL = re.compile(r'(?<=[a-z0-9])([A-Z])')


def slug(var):
    """`m_add_nomenclature` -> `add_nomenclature`; `m_save_as_action` ->
    `save_as`; `configure_action_` -> `configure`."""
    s = var
    if s.startswith('m_'):
        s = s[2:]
    s = s.rstrip('_')
    if s.endswith('_action'):
        s = s[:-7]
    elif s.endswith('_act'):
        s = s[:-4]
    s = _CAMEL.sub(r'_\1', s).lower()
    return s


def skip_reasons(rec):
    """Return a list of reasons to skip this record (empty = register it)."""
    reasons = []
    if rec['owner'] == 'diagramselection':
        reasons.append('dead code (upstream issue #756)')
    if rec['text'] is None:
        reasons.append('null text / dynamic placeholder')
    if rec['text'] and rec['text'].startswith(':/'):
        reasons.append('icon path misparsed as text')
    if variable_of(rec.get('target')) is None:
        reasons.append('no assignment target (addAction(text) result discarded)')
    return reasons


def depth_of(relpath):
    """Directory depth of a path relative to sources/."""
    return relpath.count('/')


def include_line_for(relpath):
    n = depth_of(relpath)
    prefix = '../' * (n - 1)
    return '#include "%sshortcutmanager.h"' % prefix


def find_statement_end(text, line):
    """Line number of the `;` terminating the construction statement that
    starts on `line` (1-based).  Skips string/char literals and comments.
    Returns line of the first `;` at or after `line`."""
    lines = text.split('\n')
    # character offset of the start of `line`
    off = sum(len(l) + 1 for l in lines[:line - 1])
    n = len(text)
    i = off
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if c == "'":
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            i = n if j == -1 else j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == ';':
            return text.count('\n', 0, i) + 1
        i += 1
    return line


def find_setupui_line(text):
    """Line number of the `setupUi(this)` call in a companion .cpp, or None."""
    for m in re.finditer(r'\bsetupUi\s*\(\s*this\s*\)', text):
        # ignore the declaration `void setupUi(...)` — a call has `->` or `.`
        # immediately before it.
        pre = text[max(0, m.start() - 12):m.start()]
        if re.search(r'(->|\.)\s*$', pre):
            return text.count('\n', 0, m.start()) + 1
    return None


def find_line(text, needle):
    """1-based line number of the first occurrence of `needle`, or None."""
    i = text.find(needle)
    if i == -1:
        return None
    return text.count('\n', 0, i) + 1


# Records whose construction sits in a member-initialiser list (no statement
# to follow): register after the setText() that gives the action its label.
# Keyed by (owner, target_expr) -> setText needle.
MEMBER_INIT_ANCHORS = {
    ('RichTextEditorToolBar', 'm_link_action'): 'm_link_action->setText(',
    ('RichTextEditorToolBar', 'm_image_action'): 'm_image_action->setText(',
}


def build_manifest(actions, registrations, source_root):
    """Return (records, skips)."""
    existing_ids = {r['id'] for r in registrations}

    gap = [a for a in actions
           if a['connected'] and not a['registered']
           and a['kind'] in ('action', 'checkable')]

    records = []
    skips = []
    ids_seen = {}

    for a in gap:
        reasons = skip_reasons(a)
        if reasons:
            skips.append({'owner': a['owner'], 'file': a['file'],
                          'line': a['line'], 'text': a['text'],
                          'target': a.get('target'), 'reasons': reasons})
            continue

        owner = a['owner']
        if owner not in OWNER_MAP:
            skips.append({'owner': owner, 'file': a['file'], 'line': a['line'],
                          'text': a['text'], 'target': a.get('target'),
                          'reasons': ['owner not in OWNER_MAP']})
            continue

        window, category = OWNER_MAP[owner]
        var = variable_of(a['target'])
        target_expr = target_expr_of(a['target'])
        action_id = window + '.' + slug(var)

        # default key (decisions §2)?
        default = None
        key = (owner, var)
        if key in DEFAULTS:
            default, expected_id = DEFAULTS[key]
            if action_id != expected_id:
                raise SystemExit(
                    'id mismatch for default %r: derived %r != expected %r'
                    % (var, action_id, expected_id))

        # no new duplicate ids
        if action_id in existing_ids:
            skips.append({'owner': owner, 'file': a['file'], 'line': a['line'],
                          'text': a['text'], 'target': a.get('target'),
                          'reasons': ['id %r already registered' % action_id]})
            continue
        if action_id in ids_seen:
            raise SystemExit(
                'duplicate derived id %r (from %r and %r)' %
                (action_id, ids_seen[action_id], a.get('target')))

        ids_seen[action_id] = a.get('target')

        # --- placement ------------------------------------------------------
        member_anchor = MEMBER_INIT_ANCHORS.get((owner, target_expr))
        if member_anchor is not None:
            edit_file = a['file']
            abs_path = os.path.join(source_root, edit_file)
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            anchor_line = find_line(text, member_anchor)
            if anchor_line is None:
                raise SystemExit('anchor %r not found in %s'
                                 % (member_anchor, edit_file))
            insert_after = anchor_line
            indent_line = anchor_line
        elif a['source'] == 'ui':
            # insert in the companion .cpp after setupUi()
            cpp_file = os.path.splitext(a['file'])[0] + '.cpp'
            cpp_abs = os.path.join(source_root, cpp_file)
            with open(cpp_abs, 'r', encoding='utf-8', errors='replace') as f:
                cpp_text = f.read()
            setup_line = find_setupui_line(cpp_text)
            if setup_line is None:
                raise SystemExit(
                    'no setupUi() found in %s for ui action %s'
                    % (cpp_file, var))
            edit_file = cpp_file
            insert_after = setup_line
            indent_line = setup_line
        else:
            edit_file = a['file']
            abs_path = os.path.join(source_root, edit_file)
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            insert_after = find_statement_end(text, a['line'])
            indent_line = a['line']

        records.append({
            'owner': owner,
            'edit_file': edit_file,
            'insert_after_line': insert_after,
            'indent_line': indent_line,
            'target_expr': target_expr,
            'id': action_id,
            'category': category,
            'default_sequence': default,
            'source': a['source'],
            'orig_file': a['file'],
            'orig_line': a['line'],
            'text': a['text'],
        })

    # stable order: by edit_file, then by insert point, then by id
    records.sort(key=lambda r: (r['edit_file'], r['insert_after_line'], r['id']))
    return records, skips


def render_line(rec):
    if rec['default_sequence']:
        return ('ShortcutManager::instance().registerAction(%s, "%s", tr("%s"), %s);'
                % (rec['target_expr'], rec['id'], rec['category'],
                   rec['default_sequence']))
    return ('ShortcutManager::instance().registerAction(%s, "%s", tr("%s"));'
            % (rec['target_expr'], rec['id'], rec['category']))


def render_md(records, skips):
    from collections import Counter, defaultdict
    lines = []
    lines.append('# S5 registration plan')
    lines.append('')
    lines.append('Generated by `tools/actionaudit/gen_registrations.py`.')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('| Metric | Count |')
    lines.append('|---|---|')
    lines.append('| registrations to insert | %d |' % len(records))
    lines.append('| with a default key | %d |' %
                 sum(1 for r in records if r['default_sequence']))
    lines.append('| blank (no default) | %d |' %
                 sum(1 for r in records if not r['default_sequence']))
    lines.append('| owner files touched | %d |' %
                 len(set(r['edit_file'] for r in records)))
    lines.append('| skipped records | %d |' % len(skips))
    lines.append('')
    by_owner = Counter(r['owner'] for r in records)
    lines.append('## By owner')
    lines.append('')
    lines.append('| Owner | Count |')
    lines.append('|---|---|')
    for o in sorted(by_owner, key=lambda x: -by_owner[x]):
        lines.append('| `%s` | %d |' % (o, by_owner[o]))
    lines.append('')
    lines.append('## Defaults (decisions §2)')
    lines.append('')
    lines.append('| id | default |')
    lines.append('|---|---|')
    for r in records:
        if r['default_sequence']:
            lines.append('| `%s` | `%s` |' % (r['id'], r['default_sequence']))
    lines.append('')
    lines.append('## Skipped records')
    lines.append('')
    if skips:
        lines.append('| Owner | file:line | text | target | reason |')
        lines.append('|---|---|---|---|---|')
        for s in skips:
            lines.append('| `%s` | `%s:%s` | `%s` | `%s` | %s |'
                         % (s['owner'], s['file'], s['line'], s['text'],
                            s['target'], '; '.join(s['reasons'])))
    else:
        lines.append('- none')
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Generate registerAction() insertion plan from the audit')
    ap.add_argument('--actions-json', default='reports/actions.json')
    ap.add_argument('--source-root', default='/tmp/s5-src')
    ap.add_argument('--out-dir', default='reports')
    args = ap.parse_args(argv)

    with open(args.actions_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    actions = data['actions']
    registrations = data['registrations']

    records, skips = build_manifest(actions, registrations, args.source_root)

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, 'registrations.json')
    md_path = os.path.join(args.out_dir, 'registrations.md')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(render_md(records, skips))

    print('wrote %s' % json_path)
    print('wrote %s' % md_path)
    print('registrations: %d  (defaults: %d, blank: %d)' % (
        len(records),
        sum(1 for r in records if r['default_sequence']),
        sum(1 for r in records if not r['default_sequence'])))
    print('skipped: %d' % len(skips))
    for s in skips:
        print('  SKIP %s %s:%s %r target=%r :: %s' % (
            s['owner'], s['file'], s['line'], s['text'], s['target'],
            '; '.join(s['reasons'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
