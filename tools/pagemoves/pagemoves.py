#!/usr/bin/env python3
"""pagemoves — does folio manipulation preserve cross-page links?

Applies each page operation to a copy of a project, re-saves through QET so
links and labels are re-evaluated, and reports what survived.

Metrics per operation, compared by arrow uuid (never by document order --
Diagram::toXml is not order-stable, upstream #754):

  arrows        how many folio-reference arrows exist after
  lost          arrows present before and gone after
  retargeted    links now pointing at a different partner uuid
  dangling      links pointing at a uuid that no longer exists
  orphaned      arrows left with no link at all
  relabelled    displayed reference text that changed
  inverted      direction disagrees with folio order (before -> after)
"""
import argparse, os, pathlib, re, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "labelstability"))
import labelstability as L  # noqa: E402

NEXT = ("next_folio", "going_arrow", "nastepna", "jump_to")
PREV = ("previous_folio", "coming_arrow", "poprzednia", "jump_from")


def kind(t):
    for k in NEXT:
        if k in t:
            return "next"
    for k in PREV:
        if k in t:
            return "prev"
    return None


def scan(path):
    """uuid -> (folio_order, direction, [link targets], label text)."""
    root = ET.parse(path).getroot()
    out = {}
    for d in root.iter("diagram"):
        o = d.get("order")
        for e in d.iter("element"):
            k = kind(e.get("type", ""))
            if not k:
                continue
            u = e.get("uuid")
            if not u:
                continue
            txt = None
            for dt in e.iter("dynamic_elmt_text"):
                tx = dt.find("text")
                if tx is not None and tx.text:
                    txt = tx.text
                    break
            out[u] = (o, k, [l.get("uuid") for l in e.iter("link_uuid")], txt)
    return out


def inverted_count(state):
    n = 0
    for u, (o, k, links, _t) in state.items():
        for l in links:
            if l not in state:
                continue
            try:
                a, b = int(o), int(state[l][0])
            except (TypeError, ValueError):
                continue
            if a == b:
                continue
            if (k == "prev" and b > a) or (k == "next" and b < a):
                n += 1
    return n


def compare(before, after):
    lost = [u for u in before if u not in after]
    common = [u for u in before if u in after]
    retargeted = [u for u in common if set(before[u][2]) != set(after[u][2])]
    dangling = [u for u in after if any(l not in after for l in after[u][2])]
    orphaned = [u for u in common if before[u][2] and not after[u][2]]
    relabelled = [u for u in common if before[u][3] != after[u][3]]
    return dict(arrows=len(after), lost=len(lost), retargeted=len(retargeted),
                dangling=len(dangling), orphaned=len(orphaned),
                relabelled=len(relabelled),
                inverted_before=inverted_count(before),
                inverted_after=inverted_count(after))


# --- page operations, each returning modified project text -------------------

def op_noop(head, blocks, tail):
    return head, blocks, tail


def op_move_first_to_end(head, blocks, tail):
    return head, blocks[1:] + [blocks[0]], tail


def op_move_last_to_front(head, blocks, tail):
    return head, [blocks[-1]] + blocks[:-1], tail


def op_reverse_all(head, blocks, tail):
    return head, list(reversed(blocks)), tail


def _index_of_order(blocks, order):
    for i, b in enumerate(blocks):
        m = re.search(r'order="(\d+)"', b)
        if m and m.group(1) == str(order):
            return i
    return None


def op_move_6_past_7(head, blocks, tail):
    i = _index_of_order(blocks, 6)
    if i is None:
        return head, blocks, tail
    b = blocks[:i] + blocks[i + 1:]
    return head, b + [blocks[i]], tail


def op_insert_between_6_and_7(head, blocks, tail):
    i = _index_of_order(blocks, 7)
    if i is None:
        return head, blocks, tail
    src = blocks[0]
    new = re.sub(r'order="\d+"', 'order="999"', src)
    new = re.sub(r'(title=")[^"]*(")', r'\1INSERTED\2', new, count=1)
    return head, blocks[:i] + [new] + blocks[i:], tail


def op_delete_folio_7(head, blocks, tail):
    i = _index_of_order(blocks, 7)
    if i is None:
        return head, blocks, tail
    return head, blocks[:i] + blocks[i + 1:], tail


def op_delete_folio_6(head, blocks, tail):
    i = _index_of_order(blocks, 6)
    if i is None:
        return head, blocks, tail
    return head, blocks[:i] + blocks[i + 1:], tail


OPS = [
    ("no-op (control)", op_noop),
    ("insert page between 6 and 7", op_insert_between_6_and_7),
    ("move folio 6 past folio 7", op_move_6_past_7),
    ("move first page to the end", op_move_first_to_end),
    ("move last page to the front", op_move_last_to_front),
    ("reverse every page", op_reverse_all),
    ("DELETE folio 7", op_delete_folio_7),
    ("DELETE folio 6", op_delete_folio_6),
]


def run(binary, src, workdir):
    rows = []
    base = workdir / "base.qet"
    L.resave(binary, src, base, workdir)
    before = scan(base)
    text = base.read_text(encoding="utf-8", errors="replace")
    head, blocks, tail = L.split_diagram_blocks(text)

    for name, fn in OPS:
        h, b, t = fn(head, list(blocks), tail)
        mod = workdir / ("op_" + re.sub(r"\W+", "_", name) + ".qet")
        mod.write_text(L.join_diagram_blocks(h, b, t), encoding="utf-8")
        out = workdir / ("after_" + re.sub(r"\W+", "_", name) + ".qet")
        try:
            L.resave(binary, mod, out, workdir)
            rows.append((name, compare(before, scan(out))))
        except Exception as exc:                      # resave refused / crashed
            rows.append((name, {"error": str(exc)[:60]}))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--binary",
                    default="/home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as td:
        rows = run(a.binary, pathlib.Path(a.project), pathlib.Path(td))
    hdr = ("operation", "arrows", "lost", "retgt", "dangl", "orph", "relbl", "inv")
    print(f"  {hdr[0]:<30}{hdr[1]:>7}{hdr[2]:>6}{hdr[3]:>7}{hdr[4]:>7}{hdr[5]:>6}{hdr[6]:>7}{hdr[7]:>10}")
    for name, m in rows:
        if "error" in m:
            print(f"  {name:<30}  ERROR: {m['error']}")
            continue
        inv = f"{m['inverted_before']}->{m['inverted_after']}"
        print(f"  {name:<30}{m['arrows']:>7}{m['lost']:>6}{m['retargeted']:>7}"
              f"{m['dangling']:>7}{m['orphaned']:>6}{m['relabelled']:>7}{inv:>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
