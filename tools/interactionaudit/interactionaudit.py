#!/usr/bin/env python3
"""
interactionaudit — static audit of what every QElectroTech graphics item does on
double-click, right-click and hover.

For every class deriving (directly or transitively) from QGraphicsItem,
QGraphicsObject, QGraphicsTextItem or QetGraphicsItem, produce a record:

    class, header, source, base, dblclick, dblclick_effect, context_menu,
    hover, press, accepts_hover

with multi-level inheritance resolved (a class that does not implement a handler
inherits it from the nearest ancestor that does — never guessed).

Python 3 stdlib only. No build, no QET launch. Runs over the whole source tree
in a couple of seconds.

Usage:
    python3 interactionaudit.py [QET_SOURCE_ROOT] [--out-dir DIR] [--ref-label ...]

Outputs:
    reports/interactions.json   — machine-readable inventory + outliers
    reports/interactions.md     — human summary, table sorted by dblclick_effect
"""

import argparse
import json
import os
import re
import subprocess

# ---------------------------------------------------------------------------
# Qt graphics item roots. Everything here derives from QGraphicsItem in Qt;
# we do not scan Qt source, so a chain that bottoms out in one of these (with no
# QET class reimplementing the handler) is reported as "none".
# ---------------------------------------------------------------------------
QT_GRAPHICS_BASES = {
    'QGraphicsItem', 'QGraphicsObject', 'QGraphicsTextItem', 'QGraphicsItemGroup',
    'QGraphicsPathItem', 'QGraphicsPixmapItem', 'QGraphicsSimpleTextItem',
    'QGraphicsLineItem', 'QGraphicsRectItem', 'QGraphicsEllipseItem',
    'QGraphicsPolygonItem', 'QGraphicsSvgItem', 'QGraphicsWidget', 'QGraphicsProxyWidget',
}

# Handlers this audit tracks -> field names in the record.
METHODS_AUDITED = [
    'mouseDoubleClickEvent', 'contextMenuEvent', 'hoverEnterEvent',
    'hoverLeaveEvent', 'mousePressEvent',
]


# ---------------------------------------------------------------------------
# C++ source helpers
# ---------------------------------------------------------------------------

def skip_ws(text, i):
    """Advance past whitespace (incl. newlines) and // /* */ comments."""
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\r\n':
            i += 1
        elif c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            i = n if j == -1 else j + 1
        elif c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            i = n if j == -1 else j + 2
        else:
            break
    return i


def match_paren(text, open_i):
    """Return index of the ')' matching text[open_i] (an opening bracket)."""
    depth = 0
    i = open_i
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            quote = c
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


_QUALIFIERS = ('const', 'override', 'final', 'noexcept')


def find_method_definitions(text, name, method):
    """Yield brace indices of DEFINITIONS of `name::method` in `text`.

    Distinguishes a definition (`void X::m(args) {`) from a base-class *call*
    (`X::m(event);`) by looking for a `{` after the argument list.
    """
    pat = re.compile(r'\b' + re.escape(name) + r'::' + method + r'\s*\(')
    for m in pat.finditer(text):
        close = match_paren(text, m.end() - 1)
        if close is None:
            continue
        j = skip_ws(text, close + 1)
        # trailing qualifiers: `) const {`, `) override {`, ...
        while True:
            progressed = False
            for kw in _QUALIFIERS:
                if text.startswith(kw, j):
                    j = skip_ws(text, j + len(kw))
                    progressed = True
                    break
            if not progressed:
                break
        if j < len(text) and text[j] == '{':
            yield j


def class_implements(name, method, cpp_all):
    """True if the class defines method itself (a definition, not a call)."""
    return any(True for _ in find_method_definitions(cpp_all, name, method))


def extract_method_body(text, name, method):
    """Extract the '{...}' body of `name::method`'s definition, or ''."""
    braces = list(find_method_definitions(text, name, method))
    if not braces:
        return ''
    brace = braces[0]
    depth = 0
    i = brace
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            quote = c
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[brace:i + 1]
        i += 1
    return ''


class SourceTree:
    """Reads and indexes the QET source tree once."""

    def __init__(self, root):
        self.root = root
        self.headers = []          # list of (abspath, relpath, text)
        self.sources = []          # list of (abspath, relpath, text)
        self.cpp_text = []         # concatenated .cpp text (for ::method search)
        self._load()

    def _load(self):
        for dirpath, _dirnames, filenames in os.walk(os.path.join(self.root, 'sources')):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, self.root)
                if fn.endswith('.h'):
                    with open(p, encoding='utf-8', errors='replace') as f:
                        self.headers.append((p, rel, f.read()))
                elif fn.endswith('.cpp'):
                    with open(p, encoding='utf-8', errors='replace') as f:
                        txt = f.read()
                    self.sources.append((p, rel, txt))
                    self.cpp_text.append(txt)

    def cpp_all(self):
        return '\n'.join(self.cpp_text)

    def cpp_for_header(self, header_rel):
        base = os.path.splitext(os.path.basename(header_rel))[0]
        for _p, rel, txt in self.sources:
            if os.path.splitext(os.path.basename(rel))[0] == base:
                return rel, txt
        return None, None


CLASS_RE = re.compile(r'^\s*(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*(.*?))?\s*(?:[{\n]|$)', re.MULTILINE)
ACCESS_RE = re.compile(r'\b(public|protected|private)\b')
VIRTUAL_RE = re.compile(r'\bvirtual\b')


def parse_bases(spec):
    """Split a C++ base-specifier list into bare base class names."""
    if not spec:
        return []
    bases = []
    for part in spec.split(','):
        part = VIRTUAL_RE.sub('', part)
        part = ACCESS_RE.sub('', part)
        part = re.sub(r'\s+', ' ', part).strip()
        part = part.strip(' {};')
        if part and re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', part):
            bases.append(part)
    return bases


def collect_classes(tree):
    """Return dict: class_name -> {'header': rel, 'bases': [...], 'header_text': ...}.

    Only classes declared with a base-specifier list (': public X') are kept;
    bare forward declarations (no ':') are irrelevant to this audit.
    """
    classes = {}
    for _p, rel, txt in tree.headers:
        for m in CLASS_RE.finditer(txt):
            name = m.group(1)
            spec = m.group(2)
            if spec is None:
                continue
            bases = parse_bases(spec)
            if not bases:
                continue
            classes[name] = {'header': rel, 'bases': bases, 'header_text': txt}
    return classes


def is_graphics_class(name, classes, memo):
    """True if `name` is (transitively) a QGraphicsItem-derived class."""
    if name in QT_GRAPHICS_BASES or name == 'QetGraphicsItem':
        return True
    if name in memo:
        return memo[name]
    memo[name] = False
    if name in classes:
        for b in classes[name]['bases']:
            if is_graphics_class(b, classes, memo):
                memo[name] = True
                break
    return memo[name]


def graphics_base(name, classes, memo):
    """Return the immediate base through which `name` inherits QGraphicsItem."""
    for b in classes[name]['bases']:
        if is_graphics_class(b, classes, memo):
            return b
    return None


def class_accepts_hover_own(name, classes, tree):
    """True if the class's own code calls setAcceptHoverEvents(true)."""
    c = classes.get(name)
    if not c:
        return False
    if 'setAcceptHoverEvents' in c['header_text']:
        return True
    _rel, src_text = tree.cpp_for_header(c['header'])
    if src_text and 'setAcceptHoverEvents' in src_text:
        return True
    return False


# ---------------------------------------------------------------------------
# Double-click effect classification.
# ---------------------------------------------------------------------------

EFFECT_ORDER = ['edit-properties', 'edit-text', 'navigate', 'delegate', 'signal', 'other', 'none']


def classify_dblclick_direct(body, name):
    """Classify a mouseDoubleClickEvent body's own calls.

    Returns (effects, details, base_calls) where `base_calls` are base classes
    the body forwards mouseDoubleClickEvent to (resolved separately).
    """
    effects = []
    details = []

    if 'editProperty' in body:
        effects.append('edit-properties')
        details.append('calls editProperty()')
    if re.search(r'setTextInteractionFlags\s*\(', body) or re.search(r'setEditable\s*\(', body):
        effects.append('edit-text')
        details.append('enters inline text editing')
    if (re.search(r'\bshowItem\s*\(', body) or re.search(r'\bshowMe\s*\(', body)
            or re.search(r'\bfitInView\s*\(', body) or re.search(r'\bcenterOn\s*\(', body)
            or 'zoomToLinkedElement' in body):
        effects.append('navigate')
        details.append('navigates to another item / folio')
    if re.search(r'\bemit\s*\(', body) or re.search(r'\bemit\s+', body):
        effects.append('signal')
        details.append('emits a signal')
    if 'TerminalStripEditorWindow::edit' in body:
        effects.append('other')
        details.append('other: opens TerminalStripEditorWindow (terminal strip editor)')

    base_calls = [b for b in re.findall(r'\b([A-Za-z_]\w*)\s*::\s*mouseDoubleClickEvent\s*\(', body)
                  if b != name]
    return effects, details, base_calls


def dblclick_effect_of(name, classes, tree, cpp_all, memo):
    """Resolve the double-click effect of a class, following the graphics chain.

    A class that does not define mouseDoubleClickEvent inherits the effect of
    the nearest graphics ancestor that does. A handler that forwards to a base
    class inherits that base's effect too (e.g. DynamicElementTextItem forwards
    to DiagramTextItem => edit-text) unless it already does its own thing.
    """
    if name in memo:
        return memo[name]
    if name in QT_GRAPHICS_BASES or name not in classes:
        memo[name] = ('none', '')
        return memo[name]

    body = extract_method_body(cpp_all, name, 'mouseDoubleClickEvent')
    if not body:
        gbase = graphics_base(name, classes, {})
        eff, det = dblclick_effect_of(gbase, classes, tree, cpp_all, memo) if gbase else ('none', '')
        memo[name] = (eff, det)
        return memo[name]

    effects, details, base_calls = classify_dblclick_direct(body, name)
    for base in base_calls:
        beff, bdet = dblclick_effect_of(base, classes, tree, cpp_all, memo)
        if beff != 'none' and beff not in effects:
            effects.append(beff)
            details.append('%s (via %s::mouseDoubleClickEvent)' % (beff, base))

    if not effects:
        if base_calls:
            effects = ['delegate']
            details = ['forwards to ' + ', '.join(base_calls) + '::mouseDoubleClickEvent']
        else:
            effects = ['other']
            details = ['handler does nothing classifiable']

    ordered = [e for e in EFFECT_ORDER if e in effects]
    memo[name] = (' + '.join(ordered), '; '.join(details))
    return memo[name]


def resolve_handler(name, method, classes, tree, cpp_all, memo):
    """Return ('own'|'inherited(Class)'|'none', ancestor)."""
    key = (name, method)
    if key in memo:
        return memo[key]

    seen = set()
    cur = name
    while cur and cur not in seen:
        seen.add(cur)
        if class_implements(cur, method, cpp_all):
            if cur == name:
                memo[key] = ('own', None)
            else:
                memo[key] = ('inherited(%s)' % cur, cur)
            return memo[key]
        if cur in QT_GRAPHICS_BASES:
            break
        if cur not in classes:
            break
        cur = graphics_base(cur, classes, {})
    memo[key] = ('none', None)
    return memo[key]


def subsystem_of(header_rel):
    if header_rel.startswith('sources/editor/'):
        return 'element-editor'
    if header_rel.startswith('sources/titleblock/'):
        return 'titleblock'
    if header_rel.startswith('sources/TerminalStrip/'):
        return 'terminal-strip'
    return 'diagram'


def source_ref(root):
    """Identify the exact source state that was scanned."""
    def git(*a):
        try:
            out = subprocess.run(('git', '-C', root) + a, capture_output=True,
                                 text=True, timeout=15)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    status = git('status', '--porcelain')
    dirty_src = None
    if status is not None:
        dirty_src = [l[3:].strip() for l in status.splitlines()
                     if l.strip().endswith(('.cpp', '.h', '.ui'))]
    return {
        'commit': git('rev-parse', 'HEAD'),
        'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
        'describe': git('describe', '--always', '--dirty'),
        'dirty_source_files': len(dirty_src) if dirty_src is not None else None,
        'dirty_source_sample': (dirty_src or [])[:5],
    }


def analyze(root):
    tree = SourceTree(root)
    classes = collect_classes(tree)
    cpp_all = tree.cpp_all()

    gmemo = {}
    graphics_classes = sorted(n for n in classes if is_graphics_class(n, classes, gmemo))

    dbl_memo = {}
    ctx_memo = {}
    he_memo = {}
    hl_memo = {}
    press_memo = {}
    eff_memo = {}

    items = []
    for name in graphics_classes:
        c = classes[name]
        gbase = graphics_base(name, classes, gmemo)

        dbl, dbl_anc = resolve_handler(name, 'mouseDoubleClickEvent', classes, tree, cpp_all, dbl_memo)
        effect, detail = dblclick_effect_of(name, classes, tree, cpp_all, eff_memo)

        ctx, _ = resolve_handler(name, 'contextMenuEvent', classes, tree, cpp_all, ctx_memo)

        he, _ = resolve_handler(name, 'hoverEnterEvent', classes, tree, cpp_all, he_memo)
        hl, _ = resolve_handler(name, 'hoverLeaveEvent', classes, tree, cpp_all, hl_memo)
        if he == 'own' or hl == 'own':
            hover = 'own'
        elif he.startswith('inherited') or hl.startswith('inherited'):
            hover = he if he.startswith('inherited') else hl
        else:
            hover = 'none'

        press, _ = resolve_handler(name, 'mousePressEvent', classes, tree, cpp_all, press_memo)

        if class_accepts_hover_own(name, classes, tree):
            accepts = 'own'
        else:
            anc = None
            cur = gbase
            seen = set()
            while cur and cur not in seen:
                seen.add(cur)
                if cur in QT_GRAPHICS_BASES:
                    break
                if cur in classes and class_accepts_hover_own(cur, classes, tree):
                    anc = cur
                    break
                if cur not in classes:
                    break
                cur = graphics_base(cur, classes, gmemo)
            accepts = 'inherited(%s)' % anc if anc else 'no'

        _cpp_rel, _cpp_txt = tree.cpp_for_header(c['header'])

        items.append({
            'class': name,
            'header': c['header'],
            'source': _cpp_rel or '',
            'subsystem': subsystem_of(c['header']),
            'base': gbase or '',
            'bases': c['bases'],
            'dblclick': dbl,
            'dblclick_effect': effect,
            'dblclick_detail': detail,
            'context_menu': ctx,
            'hover': hover,
            'hover_enter': he,
            'hover_leave': hl,
            'press': press,
            'accepts_hover': accepts,
        })

    def depth(n):
        d = 0
        cur = n
        seen = set()
        while cur in classes and cur not in seen:
            seen.add(cur)
            cur = graphics_base(cur, classes, gmemo)
            d += 1
        return d

    items.sort(key=lambda it: (depth(it['class']), it['class']))

    outliers = [it for it in items
                if it['dblclick_effect'] not in ('edit-properties', 'edit-text')]

    return {
        'classes': classes,
        'graphics_classes': graphics_classes,
        'items': items,
        'outliers': outliers,
    }


def summarize(res):
    items = res['items']
    return {
        'item_class_count': len(items),
        'dblclick_own': sum(1 for i in items if i['dblclick'] == 'own'),
        'dblclick_inherited': sum(1 for i in items if i['dblclick'].startswith('inherited')),
        'dblclick_none': sum(1 for i in items if i['dblclick'] == 'none'),
        'context_menu_own': sum(1 for i in items if i['context_menu'] == 'own'),
        'hover_own': sum(1 for i in items if i['hover'] == 'own'),
        'press_own': sum(1 for i in items if i['press'] == 'own'),
        'accepts_hover_own': sum(1 for i in items if i['accepts_hover'] == 'own'),
        'outlier_count': len(res['outliers']),
    }


def build_markdown(res, meta, ref):
    items = res['items']

    def effect_key(it):
        e = it['dblclick_effect']
        if e == 'edit-properties':
            return 4
        if e == 'edit-text':
            return 5
        if e == 'none':
            return 3
        return 1  # other / navigate / signal / compound — outliers first

    ordered = sorted(items, key=lambda it: (effect_key(it), it['dblclick_effect'], it['class']))

    lines = []
    lines.append('# Interaction audit — double-click / right-click / hover')
    lines.append('')
    lines.append('Generated by `tools/interactionaudit/interactionaudit.py`.')
    lines.append('')
    lines.append('## Source scanned')
    lines.append('')
    lines.append('- root: `%s`' % meta.get('source_root', ''))
    lines.append('- commit: `%s`' % ref.get('commit', ''))
    lines.append('- branch: `%s` (describe: `%s`)' % (ref.get('branch', ''), ref.get('describe', '')))
    lines.append('- dirty source files: `%s`' % ref.get('dirty_source_files', ''))
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    s = res['summary']
    lines.append('| Measure | Count |')
    lines.append('|---|---|')
    lines.append('| item classes (transitively QGraphicsItem-derived) | %d |' % s['item_class_count'])
    lines.append('| own `mouseDoubleClickEvent` | %d |' % s['dblclick_own'])
    lines.append('| inherited `mouseDoubleClickEvent` | %d |' % s['dblclick_inherited'])
    lines.append('| no `mouseDoubleClickEvent` in chain | %d |' % s['dblclick_none'])
    lines.append('| own `contextMenuEvent` | %d |' % s['context_menu_own'])
    lines.append('| own hover (enter/leave) | %d |' % s['hover_own'])
    lines.append('| own `mousePressEvent` | %d |' % s['press_own'])
    lines.append('| own `setAcceptHoverEvents(true)` | %d |' % s['accepts_hover_own'])
    lines.append('| non-edit double-click outliers | %d |' % s['outlier_count'])
    lines.append('')
    lines.append('## Items (sorted by `dblclick_effect`, outliers first)')
    lines.append('')
    lines.append('| Class | Subsystem | Base | Double-click | Effect | Context menu | Hover | Press | Accepts hover |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for it in ordered:
        eff = it['dblclick_effect']
        if it['dblclick_detail']:
            eff += ' — ' + it['dblclick_detail']
        lines.append('| `%s` | %s | `%s` | %s | %s | %s | %s | %s | %s |' % (
            it['class'], it['subsystem'], it['base'],
            it['dblclick'], eff, it['context_menu'], it['hover'],
            it['press'], it['accepts_hover'],
        ))
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Audit QET graphics-item interactions')
    ap.add_argument('qet_root', nargs='?', default='/home/user/qet-fix',
                    help='QET source root (default /home/user/qet-fix)')
    ap.add_argument('--out-dir', default='reports',
                    help='directory for interactions.json / interactions.md (default reports/)')
    ap.add_argument('--ref-label', default='',
                    help='human label for the ref scanned (e.g. upstream/master)')
    args = ap.parse_args(argv)

    root = os.path.abspath(args.qet_root)
    ref = source_ref(root)
    res = analyze(root)
    s = summarize(res)

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, 'interactions.json')
    md_path = os.path.join(args.out_dir, 'interactions.md')

    meta = {
        'generator': 'tools/interactionaudit/interactionaudit.py',
        'source_root': root,
        'source_ref': ref,
        'ref_label': args.ref_label,
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': meta,
            'summary': s,
            'items': res['items'],
            'outliers': [i['class'] for i in res['outliers']],
        }, f, indent=2)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(build_markdown({'items': res['items'], 'summary': s,
                                'outliers': res['outliers']}, meta, ref))

    print('scanned %d graphics item classes' % s['item_class_count'])
    print('wrote %s' % json_path)
    print('wrote %s' % md_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
