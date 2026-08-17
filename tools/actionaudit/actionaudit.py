#!/usr/bin/env python3
"""
actionaudit — static analysis of QElectroTech action / shortcut bindings.

Enumerates every QAction (and QAbstractButton registered as a shortcut target)
constructed in the QElectroTech source, and answers for each one: is it passed
to ShortcutManager::registerAction() (bindable), and is it wired to a slot or
signal (does it do something)?

Python 3 stdlib only. No build, no QET launch. Runs over the whole source tree
in a few seconds.

Outputs:
    reports/actions.json   — machine-readable inventory + registrations
    reports/actions.md     — human summary (counts, gap list)

Usage:
    python3 actionaudit.py [QET_SOURCE_ROOT] [--out-dir DIR]
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Low-level source helpers
# ---------------------------------------------------------------------------

CLOSE = {'(': ')', '[': ']', '{': '}'}
OPEN = set('([{')
CLOSERS = set(')]}')


def find_matching(text, start):
    """text[start] is an opening bracket; return (close_index, inner_text).

    Skips string literals, char literals, // line comments and /* block */
    comments, and tracks nested brackets of every kind.
    """
    close_ch = CLOSE[text[start]]
    depth = 0
    i = start
    n = len(text)
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
        if c in OPEN:
            depth += 1
        elif c in CLOSERS:
            depth -= 1
            if depth == 0:
                return i, text[start + 1:i]
        i += 1
    return -1, None


def split_top_level(s):
    """Split `s` on commas at bracket/string depth 0 (comments not expected)."""
    parts = []
    depth = 0
    cur = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '"':
            cur.append(c)
            i += 1
            while i < n:
                cur.append(s[i])
                if s[i] == '\\':
                    i += 1
                    if i < n:
                        cur.append(s[i])
                elif s[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if c == "'":
            cur.append(c)
            i += 1
            while i < n:
                cur.append(s[i])
                if s[i] == '\\':
                    i += 1
                    if i < n:
                        cur.append(s[i])
                elif s[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if c in OPEN:
            depth += 1
        elif c in CLOSERS:
            depth -= 1
        if c == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append(''.join(cur).strip())
    return parts


def non_code_spans(text):
    """Return sorted (start, end) spans of string/char literals and comments."""
    spans = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == '"':
                    j += 1
                    break
                j += 1
            spans.append((i, j))
            i = j
            continue
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == "'":
                    j += 1
                    break
                j += 1
            spans.append((i, j))
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            j = n if j == -1 else j
            spans.append((i, j))
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            j = n if j == -1 else j + 2
            spans.append((i, j))
            i = j
            continue
        i += 1
    return spans


def in_spans(pos, spans):
    lo, hi = 0, len(spans)
    while lo < hi:
        mid = (lo + hi) // 2
        s, e = spans[mid]
        if pos < s:
            hi = mid
        elif pos >= e:
            lo = mid + 1
        else:
            return True
    return False


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
TR_RE = re.compile(r'(?:QObject::)?tr\s*\(\s*"((?:[^"\\]|\\.)*)"')


def string_literal(s):
    m = STRING_RE.search(s)
    return m.group(1) if m else None


def tr_text(s):
    """Return the tr("...") label in an expression, else a plain string literal."""
    m = TR_RE.search(s)
    if m:
        return m.group(1)
    return string_literal(s)


def target_key(target):
    """Normalise a registerAction target expression to a matchable key."""
    t = re.sub(r'^\s*this\s*->\s*', '', target.strip())
    m = re.match(r'ui\s*->\s*([A-Za-z_]\w*)', t)
    if m:
        return ('ui', m.group(1))
    m = re.match(r'([A-Za-z_]\w*)', t)
    if m:
        return m.group(1)
    return None


def stem_of(relpath):
    return os.path.splitext(os.path.basename(relpath))[0]


# ---------------------------------------------------------------------------
# C++ parsing
# ---------------------------------------------------------------------------

GROUP_NOISE = {'this', 'parent', 'nullptr', 'Q_NULLPTR', 'NULL', '0',
               'triggered', 'hovered'}


def collect_group_vars(text, spans=None):
    """Names of QActionGroup variables declared or constructed in `text`.

    Handles `QActionGroup *x`, `QActionGroup x,` and multi-name member lists:
        QActionGroup
            a, *b, c;

    Skips `QActionGroup::member` accesses, `new QActionGroup(...)`
    constructors, and occurrences inside comments/strings (`spans`).
    """
    names = set()
    for m in re.finditer(r'\bQActionGroup\b', text):
        if spans and in_spans(m.start(), spans):
            continue
        nxt = text[m.end():m.end() + 1]
        if nxt == ':' or nxt == '(':   # QActionGroup::x / QActionGroup( or new QActionGroup(
            continue
        j = text.find(';', m.end())
        if j == -1:
            j = len(text)
        if j - m.end() > 400:          # distant `;` -> not a declaration
            continue
        seg = text[m.end():j]
        for name in re.findall(r'\*?\s*([A-Za-z_]\w*)\s*[=,;]', seg):
            if name not in GROUP_NOISE:
                names.add(name)
    return names


def collect_returned_groups(text, spans=None):
    """QActionGroup variables `return`ed from a `QActionGroup *`-returning
    function (e.g. QET::depthActionGroup). A returned group is wired by its
    caller, so its member actions are connected even across files."""
    groups = set()
    for m in re.finditer(
            r'\bQActionGroup\s*\*\s*(?:[A-Za-z_]\w*\s*::\s*)?([A-Za-z_~]\w*)\s*\(',
            text):
        if spans and in_spans(m.start(), spans):
            continue
        j = text.find('{', m.end())
        if j == -1:
            continue
        end, _ = find_matching(text, j)
        if end == -1:
            continue
        body = text[j:end]
        for rm in re.finditer(r'\breturn\s+([A-Za-z_]\w*)\s*;', body):
            groups.add(rm.group(1))
    return groups


def collect_connect_senders(text, spans):
    """Normalised sender expression (first arg) of every connect(...)."""
    senders = []
    for m in re.finditer(r'\bconnect\b', text):
        if in_spans(m.start(), spans):
            continue
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        args = split_top_level(inner)
        if not args:
            continue
        sender = args[0].strip().lstrip('&').strip()
        sender = re.sub(r'^\s*this\s*->\s*', '', sender)
        senders.append(sender)
    return senders


def collect_auto_connect_slots(text):
    """Slot names like `on_m_x_triggered` implemented in this file."""
    slots = set()
    for m in re.finditer(r'::\s*(on_[A-Za-z0-9_]+_triggered)\s*\(', text):
        slots.add(m.group(1))
    return slots


def collect_auto_connect_clicked_slots(text):
    """Slot names like `on_m_x_clicked` implemented in this file (buttons)."""
    slots = set()
    for m in re.finditer(r'::\s*(on_[A-Za-z0-9_]+_clicked)\s*\(', text):
        slots.add(m.group(1))
    return slots


def collect_compared_vars(text, spans):
    """Variable names used in an equality comparison (`==` / `!=`).

    Qt context menus are often wired without a signal/slot connect: the
    QMenu::exec() return value is compared against a stored action pointer
    (`QAction *a = menu.addAction(...); if (menu.exec() == a) {...}`). A
    compared action pointer does something, so treat it as connected.
    """
    names = set()
    for m in re.finditer(r'([A-Za-z_]\w*)\s*(?:==|!=)', text):
        if in_spans(m.start(), spans):
            continue
        names.add(m.group(1))
    for m in re.finditer(r'(?:==|!=)\s*([A-Za-z_]\w*)', text):
        if in_spans(m.start(), spans):
            continue
        names.add(m.group(1))
    return names


def find_ctor_target(text, pos):
    """Name of the variable a construction at `pos` is assigned to, or None.

    Handles `QAction *x = ...`, `x = ...`, `this->x = ...`, member-init-list
    `x(new QAction(...))`, and receiver calls `x = GROUP.addAction(...)`.
    """
    prefix = text[max(0, pos - 320):pos]
    cut = max(prefix.rfind(';'), prefix.rfind('{'), prefix.rfind('}'))
    stmt = prefix[cut + 1:]
    # member-init list:  NAME(  directly before the construction token
    m = re.search(r'([A-Za-z_]\w*)\s*\(\s*$', stmt)
    if m and m.group(1) not in {'addAction', 'registerAction', 'connect',
                                'addWidget', 'addActions'}:
        return m.group(1)
    # last assignment in the statement:  NAME =  (excluding ==, !=, <=, >=)
    ms = list(re.finditer(r'([A-Za-z_]\w*)\s*=\s*(?!=)', stmt))
    if ms:
        return ms[-1].group(1)
    return None


# factory methods that construct a wired QAction and are assigned to a variable
FACTORY_RE = re.compile(r'\b(createCheckableAction|createUndoAction|createRedoAction|createAction)\b')
GENERIC_TEMP = {'result'}


def collect_new_qactions(text, relpath, spans, owner):
    """Records for every `new QAction(...)` construction."""
    out = []
    for m in re.finditer(r'\bnew\s+QAction\b', text):
        if in_spans(m.start(), spans):
            continue
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        args = [a for a in split_top_level(inner) if a != '']
        line = line_of(text, m.start())
        target = find_ctor_target(text, m.start())

        label = None
        for a in args:
            t = tr_text(a)
            if t is not None:
                label = t
                break

        # helper-internal temp (createCheckableAction's `result`) — not a
        # user-facing action; the factory call site is recorded separately.
        if target in GENERIC_TEMP and label is None:
            continue

        kind = classify_kind(args, label)
        if label is None and kind != 'dynamic':
            # textless `new QAction` pushed into a list and marked
            # `setSeparator(true)` (diagramview) is a separator, not an action.
            pre = text[max(0, m.start() - 60):m.start()]
            post = text[end:end + 200]
            if '<<' in pre or 'setSeparator(true)' in post:
                kind = 'separator'
        out.append({
            'source': 'cpp',
            'id': None,
            'text': label,
            'file': relpath,
            'line': line,
            'registered': False,
            'default_sequence': None,
            'category': None,
            'connected': False,
            'kind': kind,
            'owner': owner(line),
            'target': target,
            'group': None,
            'constructor': 'new QAction',
            'args': args,
        })
    return out


def classify_kind(args, label):
    if label is not None:
        return 'action'
    if args:
        first = args[0]
        if re.fullmatch(r'[A-Za-z_]\w*', first):
            if first not in {'this', 'nullptr', 'NULL', 'Q_NULLPTR', '0', 'parent'}:
                return 'dynamic'
            return 'action'      # textless `new QAction(this)` — parent only
        if ICONISH_RE.match(first):
            return 'action'      # icon-only action
        return 'dynamic'         # QString(...) / QLatin1String(...) / QStringLiteral(...) / runtime var
    return 'action'


def collect_factory_actions(text, relpath, spans, owner):
    """Records for QAction factory calls: createCheckableAction, createUndoAction,
    createRedoAction, QWhatsThis::createAction."""
    out = []
    for m in FACTORY_RE.finditer(text):
        if in_spans(m.start(), spans):
            continue
        factory = m.group(1)
        pre = text[max(0, m.start() - 60):m.start()]
        # skip the *definition* of the local helper (static QAction *createCheckableAction...)
        if re.search(r'\bQAction\s*\*\s*$', pre):
            continue
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        target = find_ctor_target(text, m.start())
        if target is None:
            continue
        label = tr_text(inner)
        kind = 'checkable' if factory == 'createCheckableAction' else 'action'
        out.append({
            'source': 'cpp',
            'id': None,
            'text': label,
            'file': relpath,
            'line': line_of(text, m.start()),
            'registered': False,
            'default_sequence': None,
            'category': None,
            # factories wire the action to a receiver/slot or undo stack themselves
            'connected': True,
            'kind': kind,
            'owner': owner(line_of(text, m.start())),
            'target': target,
            'group': None,
            'constructor': factory,
            'args': [],
        })
    return out


ICONISH_RE = re.compile(r'^(QET::Icons::|QIcon\s*\(|QIcon\b|QIcon\s*::)')


def collect_addaction_creations(text, relpath, spans, owner, group_vars,
                                known_vars):
    """Records for implicit actions created by `addAction(...)`, in file order.

    `addAction(existingAction)` references are skipped. Returns
    (records, group_of list of (var, group)).
    """
    out = []
    group_of = []
    # process occurrences in source order so references see earlier creations
    matches = [m for m in re.finditer(r'\baddAction\b', text)
               if not in_spans(m.start(), spans)]
    for m in matches:
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        args = [a for a in split_top_level(inner) if a != '']
        if not args:
            continue
        line = line_of(text, m.start())

        pre = text[max(0, m.start() - 80):m.start()]
        gm = re.search(r'([A-Za-z_]\w*)\s*(?:->|\.)\s*$', pre)
        group = None
        if gm and gm.group(1) in group_vars:
            group = gm.group(1)

        first = args[0]
        is_icon_first = bool(ICONISH_RE.match(first))

        if is_icon_first and len(args) >= 2 and string_literal(args[1]) is not None:
            # addAction(icon, "text" | tr("text") [, receiver, slot])
            # (checked before text-first: QIcon("...") embeds a string literal)
            label = tr_text(args[1])
            target = find_ctor_target(text, m.start())
            has_slot = len(args) >= 4
            out.append({
                'source': 'cpp', 'id': None, 'text': label, 'file': relpath,
                'line': line, 'registered': False, 'default_sequence': None,
                'category': None, 'connected': has_slot, 'kind': 'action',
                'owner': owner(line), 'target': target, 'group': group,
                'constructor': 'addAction(icon,text)', 'args': args,
            })
            if target and group:
                group_of.append((target, group))
            if target:
                known_vars.add(target)
        elif string_literal(first) is not None:
            # addAction("text" | tr("text") [, receiver, slot])
            label = tr_text(first)
            target = find_ctor_target(text, m.start())
            has_slot = len(args) >= 3
            out.append({
                'source': 'cpp', 'id': None, 'text': label, 'file': relpath,
                'line': line, 'registered': False, 'default_sequence': None,
                'category': None, 'connected': has_slot, 'kind': 'action',
                'owner': owner(line), 'target': target, 'group': group,
                'constructor': 'addAction(text)', 'args': args,
            })
            if target and group:
                group_of.append((target, group))
            if target:
                known_vars.add(target)
        elif re.fullmatch(r'[A-Za-z_]\w*', first) and first not in known_vars \
                and not first.startswith('m_'):
            # addAction(identifier) — dynamic creation (QString variable, not an
            # existing QAction). e.g. recent-files / window list built in a loop.
            target = find_ctor_target(text, m.start())
            out.append({
                'source': 'cpp', 'id': None, 'text': None, 'file': relpath,
                'line': line, 'registered': False, 'default_sequence': None,
                'category': None, 'connected': False, 'kind': 'dynamic',
                'owner': owner(line), 'target': target, 'group': group,
                'constructor': 'addAction(dynamic)', 'args': args,
            })
            if target and group:
                group_of.append((target, group))
            if target:
                known_vars.add(target)
        # else: addAction(existingAction) reference — skip.
    return out, group_of


def collect_addaction_group_refs(text, spans, group_vars):
    """Explicit `GROUP->addAction(actionVar)` / `GROUP.addAction(actionVar)`
    memberships (references). Returns list of (var, group)."""
    group_of = []
    for m in re.finditer(r'\baddAction\b', text):
        if in_spans(m.start(), spans):
            continue
        pre = text[max(0, m.start() - 80):m.start()]
        gm = re.search(r'([A-Za-z_]\w*)\s*(?:->|\.)\s*$', pre)
        if not gm or gm.group(1) not in group_vars:
            continue
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        args = [a for a in split_top_level(inner) if a != '']
        if not args:
            continue
        vm = re.fullmatch(r'[A-Za-z_]\w*', args[0])
        if vm:
            group_of.append((args[0], gm.group(1)))
    return group_of


def collect_separators(text, relpath, spans, owner):
    """Records for addSeparator() calls."""
    out = []
    for m in re.finditer(r'\baddSeparator\b', text):
        if in_spans(m.start(), spans):
            continue
        line = line_of(text, m.start())
        out.append({
            'source': 'cpp', 'id': None, 'text': None, 'file': relpath,
            'line': line, 'registered': False, 'default_sequence': None,
            'category': None, 'connected': False, 'kind': 'separator',
            'owner': owner(line), 'target': None, 'group': None,
            'constructor': 'addSeparator', 'args': [],
        })
    return out


def collect_registrations(text, relpath, spans):
    """Every ShortcutManager::instance().registerAction(...) call site."""
    out = []
    for m in re.finditer(r'\bregisterAction\b', text):
        if in_spans(m.start(), spans):
            continue
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        args = split_top_level(inner)
        if len(args) < 3:
            continue
        idlit = string_literal(args[1])
        if idlit is None:
            # declaration/definition (`const QString &id`), not a call site.
            continue
        target = args[0].strip()
        category = tr_text(args[2])
        seq = ','.join(a.strip() for a in args[3:])
        out.append({
            'target': target,
            'target_key': target_key(target),
            'id': idlit,
            'category': category,
            'default_sequence': seq,
            'file': relpath,
            'line': line_of(text, m.start()),
        })
    return out


def collect_settexts(text, spans):
    """Map variable -> (text, checkable) from `VAR->setText(...)` /
    `VAR->setCheckable(true)` calls, to fill in actions constructed bare."""
    result = {}
    for m in re.finditer(r'\b([A-Za-z_]\w*)\s*->\s*setText\b', text):
        if in_spans(m.start(), spans):
            continue
        var = m.group(1)
        j = text.find('(', m.end())
        if j == -1:
            continue
        end, inner = find_matching(text, j)
        if end == -1:
            continue
        t = tr_text(inner)
        if t is not None:
            result.setdefault(var, {})['text'] = t
    for m in re.finditer(r'\b([A-Za-z_]\w*)\s*->\s*setCheckable\s*\(\s*true\b', text):
        if in_spans(m.start(), spans):
            continue
        result.setdefault(m.group(1), {})['checkable'] = True
    return result


def build_owner_fn(text):
    """Return a function mapping a line number to the enclosing class/namespace.

    Detects method *definitions* (`Ret Class::method(...)` followed by `{` or
    `:`), distinguishing them from calls (`ShortcutManager::instance()` is
    followed by `.`). Falls back to None (caller substitutes the file stem).
    """
    defs = []  # (line, class_name)
    for m in re.finditer(r'\b([A-Za-z_]\w*)::\s*([A-Za-z_~]\w*)\s*\(', text):
        j = text.find('(', m.end() - 1)
        if j == -1:
            continue
        end, _ = find_matching(text, j)
        if end == -1:
            continue
        k = end + 1
        while k < len(text) and text[k] in ' \t':
            k += 1
        if k >= len(text):
            continue
        if text[k] in '{:':
            defs.append((line_of(text, m.start()), m.group(1)))
    defs.sort()

    def owner(line):
        best = None
        for dline, cname in defs:
            if dline <= line:
                best = cname
            else:
                break
        return best

    return owner


# ---------------------------------------------------------------------------
# .ui parsing
# ---------------------------------------------------------------------------

def collect_ui_actions(relpath, text):
    """Records for every <action name="..."> declaration in a .ui file."""
    out = []
    line_by_name = {}
    for m in re.finditer(r'<action\s+name="([^"]+)"', text):
        line_by_name[m.group(1)] = line_of(text, m.start())

    class_name = None
    cm = re.search(r'<class>([^<]+)</class>', text)
    if cm:
        class_name = cm.group(1).strip()

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out

    for el in root.iter('action'):
        name = el.get('name')
        if not name:
            continue
        label = None
        checkable = False
        for prop in el.findall('property'):
            if prop.get('name') == 'text':
                s = prop.find('string')
                if s is not None and s.text:
                    label = s.text
            elif prop.get('name') == 'checkable':
                b = prop.find('bool')
                if b is not None and b.text.strip().lower() == 'true':
                    checkable = True
        out.append({
            'source': 'ui',
            'id': None,
            'text': label,
            'file': relpath,
            'line': line_by_name.get(name, 0),
            'registered': False,
            'default_sequence': None,
            'category': None,
            'connected': False,
            'kind': 'checkable' if checkable else 'action',
            'owner': class_name or relpath,
            'target': ('ui', name),
            'group': None,
            'constructor': '<action name>',
            'args': [],
        })
    return out


def collect_ui_connections(relpath, text):
    """Set of sender names appearing in <connection> blocks of a .ui file."""
    names = set()
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return names
    for conn in root.iter('connection'):
        sender = conn.find('sender')
        if sender is not None and sender.text:
            names.add(sender.text.strip())
    return names


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def scan_sources(root):
    """Walk `root/sources` for .cpp/.h/.hpp/.ui files, return list of paths."""
    base = os.path.join(root, 'sources')
    files = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != '.git']
        for fn in filenames:
            if fn.endswith(('.cpp', '.h', '.hpp', '.ui')):
                files.append(os.path.join(dirpath, fn))
    return files


def relpath(path, root):
    p = os.path.relpath(path, root)
    return p.replace(os.sep, '/')


def analyze(root):
    files = sorted(scan_sources(root))

    registrations = []
    actions = []
    group_of = []
    group_vars = set()
    connect_senders_by_file = {}
    compared_vars_by_file = {}
    auto_slots_by_stem = {}
    clicked_slots_by_stem = {}
    ui_connections = {}
    returned_groups = set()

    # Pre-pass: read every non-.ui file once and collect the GLOBAL set of
    # QActionGroup variable names. Group members are often declared in a
    # companion header (qetdiagrameditor.h) but constructed in a different file
    # (qetdiagrameditor.cpp), so a per-file pass undercounts them.
    texts = {}
    for path in files:
        rp = relpath(path, root)
        if rp.endswith('.ui'):
            continue
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        texts[rp] = text
        spans0 = non_code_spans(text)
        group_vars |= collect_group_vars(text, spans0)
        returned_groups |= collect_returned_groups(text, spans0)

    for path in files:
        rp = relpath(path, root)
        if rp.endswith('.ui'):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            actions.extend(collect_ui_actions(rp, text))
            ui_connections[rp] = collect_ui_connections(rp, text)
            continue

        text = texts.get(rp)
        if text is None:
            continue

        spans = non_code_spans(text)
        owner_fn = build_owner_fn(text)
        fallback = os.path.splitext(os.path.basename(rp))[0]

        def owner(line):
            return owner_fn(line) or fallback

        registrations.extend(collect_registrations(text, rp, spans))

        new_actions = collect_new_qactions(text, rp, spans, owner)
        factory_actions = collect_factory_actions(text, rp, spans, owner)

        known_vars = {a['target'] for a in new_actions if a['target']}
        known_vars |= {a['target'] for a in factory_actions if a['target']}

        add_actions, go1 = collect_addaction_creations(
            text, rp, spans, owner, group_vars, known_vars)
        separators = collect_separators(text, rp, spans, owner)

        actions.extend(new_actions)
        actions.extend(factory_actions)
        actions.extend(add_actions)
        actions.extend(separators)

        group_of.extend(go1)
        group_of.extend(collect_addaction_group_refs(text, spans, group_vars))

        # `new QAction(..., groupVar)` — parent is a QActionGroup
        for a in new_actions:
            if not a['target']:
                continue
            for arg in a['args']:
                if arg in group_vars:
                    a['group'] = arg
                    group_of.append((a['target'], arg))
                    break

        connect_senders_by_file[rp] = collect_connect_senders(text, spans)
        compared_vars_by_file[rp] = collect_compared_vars(text, spans)
        auto_slots_by_stem.setdefault(stem_of(rp), set()).update(
            collect_auto_connect_slots(text))
        clicked_slots_by_stem.setdefault(stem_of(rp), set()).update(
            collect_auto_connect_clicked_slots(text))

        # setText / setCheckable upgrades
        settexts = collect_settexts(text, spans)
        for a in new_actions + factory_actions + add_actions:
            if not a['target'] or a['target'] not in settexts:
                continue
            up = settexts[a['target']]
            if a['text'] is None and up.get('text'):
                a['text'] = up['text']
                if a['kind'] == 'separator':
                    a['kind'] = 'action'
            if up.get('checkable'):
                a['kind'] = 'checkable'

    # ---- resolve registration -> action records --------------------------
    regs_by_file_var = {}
    regs_by_stem_ui = {}
    for r in registrations:
        k = r['target_key']
        if isinstance(k, tuple) and k[0] == 'ui':
            regs_by_stem_ui.setdefault(stem_of(r['file']), {}).setdefault(k[1], []).append(r)
        else:
            regs_by_file_var.setdefault((r['file'], k), []).append(r)

    resolved = set()
    for a in actions:
        if a['source'] == 'ui':
            name = a['target'][1]
            regs = regs_by_stem_ui.get(stem_of(a['file']), {}).get(name)
            if regs:
                r = regs[0]
                a['registered'] = True
                a['id'] = r['id']
                a['default_sequence'] = r['default_sequence']
                a['category'] = r['category']
                a['constructed_file'] = a['file']
                a['constructed_line'] = a['line']
                a['file'] = r['file']
                a['line'] = r['line']
                resolved.add(('ui', stem_of(a['file']), name))
        else:
            v = a['target']
            if v:
                regs = regs_by_file_var.get((a['file'], v))
                if not regs:
                    # fall back: unique global var match (rare cross-file member)
                    cand = [r for key, rlist in regs_by_file_var.items()
                            if key[1] == v for r in rlist]
                    if cand:
                        regs = cand
                if regs:
                    r = regs[0]
                    a['registered'] = True
                    a['id'] = r['id']
                    a['default_sequence'] = r['default_sequence']
                    a['category'] = r['category']
                    a['constructed_file'] = a['file']
                    a['constructed_line'] = a['line']
                    a['file'] = r['file']
                    a['line'] = r['line']
                    resolved.add(('var', a['file'], v))

    # ---- backfill: registered targets that are not plain QActions ---------
    for r in registrations:
        k = r['target_key']
        if isinstance(k, tuple) and k[0] == 'ui':
            key = ('ui', stem_of(r['file']), k[1])
            if key in resolved:
                continue
            # a registered ui-> widget that is not a declared <action> — e.g. a
            # QPushButton (autonumberingdockwidget's m_configure_pb).
            actions.append({
                'source': 'ui', 'id': r['id'], 'text': None, 'file': r['file'],
                'line': r['line'], 'registered': True,
                'default_sequence': r['default_sequence'], 'category': r['category'],
                'connected': False, 'kind': 'button', 'owner': stem_of(r['file']),
                'target': ('ui', k[1]), 'group': None,
                'constructor': 'registered widget (non-QAction)', 'args': [],
            })
            resolved.add(key)
        else:
            key = ('var', r['file'], k)
            if key in resolved:
                continue
            actions.append({
                'source': 'cpp', 'id': r['id'], 'text': None, 'file': r['file'],
                'line': r['line'], 'registered': True,
                'default_sequence': r['default_sequence'], 'category': r['category'],
                'connected': False, 'kind': 'action', 'owner': stem_of(r['file']),
                'target': k, 'group': None,
                'constructor': 'registered (unresolved factory)', 'args': [],
            })
            resolved.add(key)

    # ---- resolve connected -------------------------------------------------
    connected_groups = set()
    for senders in connect_senders_by_file.values():
        for s in senders:
            if s in group_vars:
                connected_groups.add(s)

    group_map = {}
    for var, grp in group_of:
        group_map[var] = grp

    for a in actions:
        if a['connected']:
            continue
        if a['source'] == 'ui':
            name = a['target'][1]
            stem = stem_of(a['file'])
            if name in ui_connections.get(a['file'], set()):
                a['connected'] = True
                continue
            if f'on_{name}_triggered' in auto_slots_by_stem.get(stem, set()):
                a['connected'] = True
                continue
            if f'on_{name}_clicked' in clicked_slots_by_stem.get(stem, set()):
                a['connected'] = True
                continue
            if f'ui->{name}' in connect_senders_by_file.get(a['file'], []):
                a['connected'] = True
                continue
            # .ui action may be wired in its companion .cpp under a path that
            # differs from the .ui path; try same-stem senders as well
            for rp2, senders in connect_senders_by_file.items():
                if stem_of(rp2) == stem and f'ui->{name}' in senders:
                    a['connected'] = True
                    break
            continue

        v = a['target']
        if not v:
            continue
        if v in connect_senders_by_file.get(a['file'], []):
            a['connected'] = True
            continue
        if v in compared_vars_by_file.get(a['file'], []):
            # QMenu::exec() return-value comparison (no signal/slot connect)
            a['connected'] = True
            continue
        grp = group_map.get(v)
        if grp and (grp in connected_groups or grp in returned_groups):
            a['connected'] = True

    # ---- tidy records for output ------------------------------------------
    records = []
    for a in actions:
        records.append({
            'id': a['id'],
            'text': a['text'],
            'file': a['file'],
            'line': a['line'],
            'registered': a['registered'],
            'default_sequence': a['default_sequence'],
            'connected': a['connected'],
            'kind': a['kind'],
            'owner': a['owner'],
            'target': a['target'],
            'category': a['category'],
            'source': a['source'],
            'constructor': a['constructor'],
            'constructed_file': a.get('constructed_file'),
            'constructed_line': a.get('constructed_line'),
        })

    return {
        'registrations': registrations,
        'actions': records,
        'group_vars': sorted(group_vars),
        'connected_groups': sorted(connected_groups),
    }


def summarize(result):
    actions = result['actions']
    regs = result['registrations']

    ids = [r['id'] for r in regs]
    distinct = sorted(set(ids))
    dupes = {i: ids.count(i) for i in distinct if ids.count(i) > 1}

    n_registered = sum(1 for a in actions if a['registered'])
    n_connected = sum(1 for a in actions if a['connected'])
    n_gap = sum(1 for a in actions if a['connected'] and not a['registered']
                and a['kind'] in ('action', 'checkable'))
    n_unconnected = sum(1 for a in actions if not a['connected'])
    n_unconnected_real = sum(
        1 for a in actions if not a['connected'] and not a['registered']
        and a['kind'] in ('action', 'checkable'))

    kind_counts = {}
    for a in actions:
        kind_counts[a['kind']] = kind_counts.get(a['kind'], 0) + 1

    source_counts = {}
    for a in actions:
        source_counts[a['source']] = source_counts.get(a['source'], 0) + 1

    owner_gap = {}
    for a in actions:
        if a['connected'] and not a['registered'] \
                and a['kind'] in ('action', 'checkable'):
            owner_gap[a['owner']] = owner_gap.get(a['owner'], 0) + 1

    owner_unconnected = {}
    for a in actions:
        if not a['connected'] and not a['registered'] \
                and a['kind'] in ('action', 'checkable'):
            owner_unconnected[a['owner']] = owner_unconnected.get(a['owner'], 0) + 1

    # registered but unconnected — likely cross-file/group aliasing false negatives
    reg_unconnected = [
        a for a in actions if a['registered'] and not a['connected']]

    return {
        'registerAction_sites': len(regs),
        'registerAction_distinct_ids': len(distinct),
        'duplicate_ids': dupes,
        'total_actions': len(actions),
        'source_counts': source_counts,
        'kind_counts': kind_counts,
        'registered': n_registered,
        'connected': n_connected,
        'gap_connected_unregistered': n_gap,
        'unconnected': n_unconnected,
        'unconnected_real': n_unconnected_real,
        'gap_by_owner': owner_gap,
        'unconnected_by_owner': owner_unconnected,
        'registered_unconnected': [
            {'id': a['id'], 'file': a['file'], 'line': a['line']}
            for a in reg_unconnected],
        'ui_action_declarations': sum(
            1 for a in actions if a['source'] == 'ui' and a['kind'] != 'button'),
        'registered_buttons': sum(
            1 for a in actions if a['kind'] == 'button'),
    }


def render_md(s):
    lines = []
    lines.append('# QElectroTech action / shortcut audit')
    lines.append('')
    lines.append('Generated by `tools/actionaudit/actionaudit.py` (Python 3, stdlib only).')
    lines.append('Read-only static analysis — no QET build, no source modified.')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('| Metric | Count |')
    lines.append('|---|---|')
    rows = [
        ('`registerAction` call sites', s['registerAction_sites']),
        ('distinct registered ids', s['registerAction_distinct_ids']),
        ('actions enumerated', s['total_actions']),
        ('… constructed in C++ (`new QAction` + implicit `addAction` + factories)',
         s['source_counts'].get('cpp', 0)),
        ('… declared as `<action>` in `.ui` files', s['ui_action_declarations']),
        ('… registered non-action targets (QPushButton)',
         s['registered_buttons']),
        ('registered actions', s['registered']),
        ('connected actions (wired to a slot/signal)', s['connected']),
        ('gap: connected **and** unregistered', s['gap_connected_unregistered']),
        ('unconnected actions (possible bug)', s['unconnected']),
        ('… unconnected real actions (excluding separators/dynamic/registered)',
         s['unconnected_real']),
    ]
    for k, v in rows:
        lines.append(f'| {k} | {v} |')
    lines.append('')

    lines.append('### Duplicate registered ids (same id registered twice)')
    lines.append('')
    if s['duplicate_ids']:
        for k, v in sorted(s['duplicate_ids'].items()):
            lines.append(f'- `{k}` — {v} call sites')
    else:
        lines.append('- none')
    lines.append('')

    lines.append('### Kind breakdown')
    lines.append('')
    lines.append('| Kind | Count |')
    lines.append('|---|---|')
    for k in sorted(s['kind_counts']):
        lines.append(f'| `{k}` | {s["kind_counts"][k]} |')
    lines.append('')

    lines.append('### Gap list — connected but unregistered, by owner')
    lines.append('')
    lines.append('These do something but cannot be bound to a key.')
    lines.append('')
    lines.append('| Owner | Count |')
    lines.append('|---|---|')
    for k in sorted(s['gap_by_owner'], key=lambda x: -s['gap_by_owner'][x]):
        lines.append(f'| `{k}` | {s["gap_by_owner"][k]} |')
    lines.append('')

    lines.append('### Unconnected actions (wired to nothing), by owner')
    lines.append('')
    lines.append('Exists but triggers nothing — a possible bug, *not* a shortcut gap.')
    lines.append('')
    lines.append('| Owner | Count |')
    lines.append('|---|---|')
    for k in sorted(s['unconnected_by_owner'], key=lambda x: -s['unconnected_by_owner'][x]):
        lines.append(f'| `{k}` | {s["unconnected_by_owner"][k]} |')
    lines.append('')

    if s['registered_unconnected']:
        lines.append('### Registered but unconnected (analyser limitation)')
        lines.append('')
        lines.append('Registered actions the static pass could not prove connected —')
        lines.append('usually cross-file `QActionGroup` aliasing, not real bugs:')
        lines.append('')
        for a in s['registered_unconnected']:
            lines.append(f'- `{a["id"]}` at `{a["file"]}:{a["line"]}`')
        lines.append('')

    lines.append('## Notes / discrepancies vs the brief')
    lines.append('')
    lines.append('1. **The 97/95 split is not "two different targets share one id".** '
                 'Both duplicates are the *same* target registered under one id, '
                 'inside `#ifdef Q_OS_MAC / #else / #endif` with platform-specific '
                 'default sequences (`sources/editor/ui/qetelementeditor.cpp:1003-1010`): '
                 '`elementeditor.delete` is `Qt::Key_Backspace` on macOS vs '
                 '`Qt::Key_Delete` elsewhere, and `elementeditor.quit` is '
                 '`Qt::CTRL | Qt::Key_W` vs `Qt::CTRL | Qt::Key_Q`. Only one branch '
                 'compiles, so 95 rows on the config page, 97 call sites in source.')
    lines.append('')
    lines.append('2. **"on the order of 227 actions" undercounts.** The real total is '
                 '~320: 171 `new QAction`, 56 `.ui` `<action>`, plus implicit '
                 '`addAction(icon,text)`/`addAction(text)` creations (including '
                 '`QActionGroup::addAction(icon,text)`), factory-created actions '
                 '(`createUndoAction`/`createRedoAction`/`createCheckableAction`/'
                 '`createAction`), one registered `QPushButton`, and 46 separators.')
    lines.append('')
    lines.append('3. **`.ui` actions and shortcuts.** No `.ui` `<action>` carries a '
                 '`<property name="shortcut">` element, but 24 of the 56 are still '
                 'registered (and thus bindable) via `registerAction(ui->…, …)` in '
                 'their companion `.cpp`; the other 32 are genuinely unregistered. '
                 'Being "declared in a `.ui` file" does not imply unregistered.')
    lines.append('')
    lines.append('4. **`connected` is conservative.** Context-menu actions wired via '
                 '`QMenu::exec()` return-value comparison are detected, but an '
                 '`addAction` result discarded into an `else` branch ('
                 '`diagramselection.cpp:107`) is not; the four `depth.*` actions are '
                 'registered and wired through a `QActionGroup` returned by a helper, '
                 'which a single-file static pass cannot follow.')

    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Audit QET actions and shortcut bindings')
    ap.add_argument('qet_root', nargs='?', default='/home/user/qet-fix',
                    help='QET source root (default /home/user/qet-fix)')
    ap.add_argument('--out-dir', default='reports',
                    help='directory for actions.json / actions.md (default reports/)')
    args = ap.parse_args(argv)

    root = os.path.abspath(args.qet_root)
    result = analyze(root)
    s = summarize(result)

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, 'actions.json')
    md_path = os.path.join(args.out_dir, 'actions.md')

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'generator': 'tools/actionaudit/actionaudit.py',
                'source_root': root,
            },
            'summary': s,
            'registrations': result['registrations'],
            'actions': result['actions'],
        }, f, ensure_ascii=False, indent=2)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(render_md(s))

    print(f'wrote {json_path}')
    print(f'wrote {md_path}')
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
