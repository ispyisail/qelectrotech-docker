"""
Mutation strategies -- the "break stuff" half of the simulator.

Each mutator is a pure function (text_or_bytes, rng) -> (mutated, resolved_args)
or None if it does not apply to this particular input (e.g. no uuid found to
corrupt). Every text-domain mutator's resolved_args carries a uniform
byte_start/byte_end/replacement triple, so ONE generic function
(apply_resolved) can redo the exact same edit later with no RNG involved --
that is what makes a Step in trace.py replayable per SIMULATOR-DESIGN.md
§4.1: replaying must reproduce the failure without the RNG.

Structural mutators operate on the XML as text (regex/string surgery)
rather than round-tripping through a DOM, specifically so a corrupted-XML
mutation (drop half a tag, truncate mid-attribute) is possible at all --
a DOM-based mutator could only ever produce well-formed XML, which would
make truncate_bytes and flip_random_bit redundant with everything else.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable

_UUID_RE = re.compile(r"\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}")
_ELEMENT_BLOCK_RE = re.compile(r"<element\b[^>]*>.*?</element>", re.S)
_TAG_ATTRS_RE = re.compile(r"<(\w+)((?:\s+[\w-]+=\"[^\"]*\")+)\s*/?>")
_COORD_ATTR_RE = re.compile(r'\b(x|y)="(-?\d+(?:\.\d+)?)"')
_ATTR_RE = re.compile(r'\s+([\w-]+)="[^"]*"')


@dataclass
class MutationResult:
    text: str | None            # decoded text after the edit (None for byte-domain results)
    data: bytes | None          # bytes after the edit -- always populated by apply_named()
    args: dict


class ReplayError(RuntimeError):
    """A recorded Step cannot be re-applied to the given bytes (e.g. the
    seed file changed since the trace was recorded, and a text-domain
    splice no longer lands on valid UTF-8)."""


def _splice(text: str, start: int, end: int, replacement: str, kind: str, **extra) -> MutationResult:
    """Every text mutator funnels through here so replay only needs one code path."""
    mutated = text[:start] + replacement + text[end:]
    args = {"kind": kind, "byte_start": start, "byte_end": end, "replacement": replacement, **extra}
    return MutationResult(mutated, None, args)


def drop_element_block(text: str, rng: random.Random) -> MutationResult | None:
    """Remove one whole <element>...</element>. Tests: dangling conductor
    references, O3 (uuid disappears), robustness of the load path."""
    blocks = list(_ELEMENT_BLOCK_RE.finditer(text))
    if not blocks:
        return None
    m = rng.choice(blocks)
    uuid_m = re.search(r'uuid="([^"]+)"', m.group(0))
    return _splice(text, m.start(), m.end(), "", "drop_element_block",
                    removed_uuid=uuid_m.group(1) if uuid_m else None)


def duplicate_uuid(text: str, rng: random.Random) -> MutationResult | None:
    """Stamp an existing uuid onto a second occurrence of ANOTHER uuid, so
    two distinct items claim the same identity. Tests uuid-collision
    handling -- a plausible outcome of a bad merge or copy-paste bug."""
    uuids = list({m.group(0) for m in _UUID_RE.finditer(text)})
    if len(uuids) < 2:
        return None
    victim, source = rng.sample(uuids, 2)
    idx = text.find(victim)  # first occurrence == the item's own defining attribute
    return _splice(text, idx, idx + len(victim), source, "duplicate_uuid",
                    victim_uuid=victim, replaced_with=source)


def corrupt_uuid_char(text: str, rng: random.Random) -> MutationResult | None:
    """Flip one hex character of a random uuid occurrence: syntactically
    valid uuid, but now a dangling reference (or a false collision).
    Tests referential-integrity handling on a broken-but-plausible id."""
    matches = list(_UUID_RE.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    hex_positions = [i for i, c in enumerate(m.group(0)) if c in "0123456789abcdefABCDEF"]
    pos = rng.choice(hex_positions)
    orig_char = m.group(0)[pos]
    new_char = rng.choice([c for c in "0123456789abcdef" if c != orig_char.lower()])
    corrupted = m.group(0)[:pos] + new_char + m.group(0)[pos + 1:]
    return _splice(text, m.start(), m.end(), corrupted, "corrupt_uuid_char",
                    original_uuid=m.group(0), corrupted_uuid=corrupted)


def inject_nan_coordinate(text: str, rng: random.Random) -> MutationResult | None:
    """Set a random x/y attribute to the literal string 'nan'. This is the
    exact fault class PR #679 crashed on (0.0/0.0 in title-block width
    math), generalised to every coordinate in the document."""
    matches = list(_COORD_ATTR_RE.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    return _splice(text, m.start(), m.end(), f'{m.group(1)}="nan"', "inject_nan_coordinate",
                    attribute=m.group(1), original_value=m.group(2))


def inject_inf_coordinate(text: str, rng: random.Random) -> MutationResult | None:
    matches = list(_COORD_ATTR_RE.finditer(text))
    if not matches:
        return None
    m = rng.choice(matches)
    sign = rng.choice(["inf", "-inf"])
    return _splice(text, m.start(), m.end(), f'{m.group(1)}="{sign}"', "inject_inf_coordinate",
                    attribute=m.group(1), original_value=m.group(2), injected=sign)


def drop_random_attribute(text: str, rng: random.Random) -> MutationResult | None:
    """Remove one attribute from a random tag. Tests handling of a
    missing-but-expected field (a common source of default-construction
    bugs -- see the review of PR #662's projectconfigpages.cpp)."""
    tag_matches = list(_TAG_ATTRS_RE.finditer(text))
    if not tag_matches:
        return None
    tm = rng.choice(tag_matches)
    tag, attrs_blob = tm.group(1), tm.group(2)
    attr_matches = list(_ATTR_RE.finditer(attrs_blob))
    if not attr_matches:
        return None
    am = rng.choice(attr_matches)
    abs_start = tm.start(2) + am.start()
    abs_end = tm.start(2) + am.end()
    return _splice(text, abs_start, abs_end, "", "drop_random_attribute",
                    tag=tag, attribute=am.group(1))


def truncate_bytes(data: bytes, rng: random.Random) -> MutationResult:
    """Truncate the raw file at a random byte offset. Same technique
    edz-fuzzer/ already uses for .edz; this applies it to .qet, which
    currently has no truncation-fuzzing coverage at all."""
    if len(data) == 0:
        return MutationResult(None, data, {"kind": "truncate_bytes", "offset": 0})
    offset = rng.randint(1, len(data))
    return MutationResult(None, data[:offset], {"kind": "truncate_bytes", "offset": offset, "original_size": len(data)})


def flip_random_bit(data: bytes, rng: random.Random) -> MutationResult:
    """Classic single-bit flip anywhere in the byte stream."""
    if len(data) == 0:
        return MutationResult(None, data, {"kind": "flip_random_bit", "byte_offset": 0, "bit": 0})
    byte_offset = rng.randrange(len(data))
    bit = rng.randrange(8)
    mutated = bytearray(data)
    mutated[byte_offset] ^= (1 << bit)
    return MutationResult(None, bytes(mutated), {
        "kind": "flip_random_bit", "byte_offset": byte_offset, "bit": bit,
        "original_byte": data[byte_offset], "new_byte": mutated[byte_offset],
    })


# Text-domain mutators (operate on the decoded XML string; args are always
# a byte_start/byte_end/replacement triple plus mutator-specific extras).
TEXT_MUTATORS: dict[str, Callable[[str, random.Random], MutationResult | None]] = {
    "drop_element_block": drop_element_block,
    "duplicate_uuid": duplicate_uuid,
    "corrupt_uuid_char": corrupt_uuid_char,
    "inject_nan_coordinate": inject_nan_coordinate,
    "inject_inf_coordinate": inject_inf_coordinate,
    "drop_random_attribute": drop_random_attribute,
}

# Byte-domain mutators (operate on raw bytes, can break XML well-formedness,
# and are replayed by re-deriving from a stored offset rather than a generic
# splice -- see apply_resolved()).
BYTE_MUTATORS: dict[str, Callable[[bytes, random.Random], MutationResult]] = {
    "truncate_bytes": truncate_bytes,
    "flip_random_bit": flip_random_bit,
}

ALL_MUTATOR_NAMES = list(TEXT_MUTATORS) + list(BYTE_MUTATORS)


def apply_named(name: str, data: bytes, rng: random.Random) -> MutationResult | None:
    """Apply one named mutator to `data`, decoding to text for text-domain
    mutators. Returns None if the mutator does not apply (e.g. no uuid
    present) -- callers should try a different mutator, not treat this
    as a failure."""
    if name in BYTE_MUTATORS:
        return BYTE_MUTATORS[name](data, rng)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None  # already-corrupted bytes; a text mutator can't help further
    result = TEXT_MUTATORS[name](text, rng)
    if result is None:
        return None
    return MutationResult(result.text, result.text.encode("utf-8"), result.args)


def apply_resolved(args: dict, data: bytes) -> bytes:
    """
    Deterministic replay counterpart to apply_named(): given the exact
    `args` a mutator produced, redo the exact same edit with no RNG
    involved. This is what makes a Trace (trace.py) replayable.
    """
    kind = args["kind"]
    if kind == "truncate_bytes":
        return data[: args["offset"]]
    if kind == "flip_random_bit":
        mutated = bytearray(data)
        mutated[args["byte_offset"]] ^= (1 << args["bit"])
        return bytes(mutated)
    # every text mutator: uniform byte_start/byte_end/replacement splice
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ReplayError(
            f"step kind={kind!r} cannot be replayed: the current bytes are not "
            f"valid UTF-8 (has the seed file changed since this trace was recorded?)"
        ) from e
    mutated = text[: args["byte_start"]] + args["replacement"] + text[args["byte_end"]:]
    return mutated.encode("utf-8")


def pathological_titleblock_columns(sums: list[int] | None = None) -> list[dict]:
    """
    Not a corpus mutator -- a direct generator for the family of inputs
    around PR #679's crash (columns summing to exactly 100% with zero
    absolute width -> 0.0/0.0 -> NaN -> Q_ASSERT). Returns `cols` attribute
    strings for a <grid> element, spanning the boundary the design doc
    calls for in §5.1: 0, 99, 100, 101, 1000, one column, zero columns.
    """
    if sums is None:
        sums = [0, 1, 99, 100, 101, 150, 1000]
    cases = []
    for total in sums:
        if total == 0:
            cases.append({"sum": 0, "cols": ""})
            continue
        n = min(4, max(1, total // 25 + 1))
        base = total // n
        parts = [base] * n
        parts[-1] += total - base * n
        cases.append({"sum": total, "cols": ";".join(f"t{p}%" for p in parts if p > 0) + ";"})
    cases.append({"sum": "single-huge", "cols": "t100000%;"})
    return cases
