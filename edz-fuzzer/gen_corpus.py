#!/usr/bin/env python3
"""
Generate a corpus of malformed and edge-case .edz files for fuzzing the
EdzImporter pipeline.  Covers failures at every layer:
  1. Archive-level  (EdzArchive / edzsevenzip)
  2. XML-level      (EdzPart)
  3. Builder-level  (EdzElementBuilder)
"""
import os
import subprocess
import sys
import tempfile

OUT = sys.argv[1] if len(sys.argv) > 1 else "corpus"
os.makedirs(OUT, exist_ok=True)


def write(name, data: bytes):
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(data)
    print(f"  {name:55s} {len(data):>8d} bytes")


def make_7z(name, files: dict):
    """
    Create a 7z archive at OUT/name containing {filename: content} entries.
    Returns True on success.
    """
    with tempfile.TemporaryDirectory() as tmp:
        for fname, content in files.items():
            fpath = os.path.join(tmp, fname)
            os.makedirs(os.path.dirname(fpath) or tmp, exist_ok=True)
            with open(fpath, "wb") as f:
                f.write(content if isinstance(content, bytes) else content.encode())
        out_path = os.path.join(OUT, name)
        r = subprocess.run(
            ["7z", "a", "-t7z", "-mx=1", out_path] + list(files.keys()),
            cwd=tmp, capture_output=True,
        )
        if r.returncode != 0:
            print(f"  WARNING: 7z failed for {name}: {r.stderr.decode()[:120]}")
            return False
        size = os.path.getsize(out_path)
        print(f"  {name:55s} {size:>8d} bytes  [7z]")
        return True


# ── Shared minimal valid part.xml ─────────────────────────────────────────────
MINIMAL_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts>
  <part P_ARTICLE_PARTNR="TEST-001"
        P_ARTICLE_MANUFACTURER="TestCo"
        P_ARTICLE_ORDERNR="ORD-001"
        P_ARTICLE_TYPENR=""
        P_ARTICLE_DESCR1="en_EN@Test Part;"
        P_ARTICLE_DESCR2="">
    <functiontemplate connectionDesignation="1"
        connectiondescription="L+" terminalNr="X01"/>
    <functiontemplate connectionDesignation="2"
        connectiondescription="L-" terminalNr="X01"/>
    <functiontemplate connectionDesignation="PE"
        connectiondescription="PE" terminalNr="X01"/>
  </part>
</EDZ_Parts>
"""

print("Generating corpus ...")

# ── 1. Archive-level failures ─────────────────────────────────────────────────
print("\n[Archive-level]")
write("empty.edz",            b"")
write("five_bytes.edz",       b"\x00\x01\x02\x03\x04")
write("zip_magic.edz",        b"PK\x03\x04" + b"\x00" * 100)
write("bad_magic.edz",        b"\xDE\xAD\xBE\xEF\xCA\xFE" + b"\x00" * 100)
write("7z_magic_only.edz",    b"7z\xBC\xAF\x27\x1C")
write("7z_truncated.edz",     b"7z\xBC\xAF\x27\x1C" + b"\x00" * 20)
write("7z_garbage_body.edz",  b"7z\xBC\xAF\x27\x1C" + bytes(range(256)) * 8)

# ── 2. Valid archive, bad content ─────────────────────────────────────────────
print("\n[Valid archive, bad content]")
make_7z("no_part_xml.edz",    {"readme.txt": "no part xml here"})
make_7z("empty_part_xml.edz", {"part.part.xml": ""})
make_7z("malformed_xml.edz",  {"part.part.xml": "<not valid xml <<<\x00"})
make_7z("no_part_element.edz",{"part.part.xml": "<?xml version='1.0'?><EDZ_Parts/>"})
make_7z("part_no_attrs.edz",  {"part.part.xml":
    "<?xml version='1.0'?><EDZ_Parts><part/></EDZ_Parts>"})

# ── 3. Valid XML, edge-case content ───────────────────────────────────────────
print("\n[XML edge cases]")
make_7z("valid_minimal.edz",  {"part.part.xml": MINIMAL_XML})

# No pins — hits the dummy-pin fallback in EdzElementBuilder
make_7z("no_pins.edz", {"part.part.xml": b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="NOPINS" P_ARTICLE_MANUFACTURER="Co"
  P_ARTICLE_ORDERNR="NOPINS-001" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@No Pins;" P_ARTICLE_DESCR2=""/>
</EDZ_Parts>"""})

# 1000 pins — stress the layout arithmetic and terminal-name set
pins_xml = (b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="BIG" P_ARTICLE_MANUFACTURER="Co"
  P_ARTICLE_ORDERNR="BIG-001" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@Big Part;" P_ARTICLE_DESCR2="">"""
+ b"".join(
    f'<functiontemplate connectionDesignation="{i+1}" '
    f'connectiondescription="Pin {i+1}" '
    f'terminalNr="X{i//10+1:02d}"/>'.encode()
    for i in range(1000)
)
+ b"</part></EDZ_Parts>")
make_7z("many_pins_1000.edz", {"part.part.xml": pins_xml})

# Very long strings — stress string handling throughout
long_s = "A" * 10_000
make_7z("long_strings.edz", {"part.part.xml": f"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="{long_s}" P_ARTICLE_MANUFACTURER="{long_s}"
  P_ARTICLE_ORDERNR="{long_s}" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@{long_s};" P_ARTICLE_DESCR2="en_EN@{long_s};">
  <functiontemplate connectionDesignation="1"
      connectiondescription="{long_s}" terminalNr="X01"/>
</part></EDZ_Parts>""".encode()})

# XML special characters (must be entity-encoded in attributes)
make_7z("special_chars.edz", {"part.part.xml": b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="A&amp;B" P_ARTICLE_MANUFACTURER="Co&lt;Ltd&gt;"
  P_ARTICLE_ORDERNR="X/Y-Z_1.2" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@&lt;Special&gt; &amp; &quot;Chars&quot;;"
  P_ARTICLE_DESCR2="">
  <functiontemplate connectionDesignation="PE"
      connectiondescription="&lt;GND&gt;" terminalNr=""/>
  <functiontemplate connectionDesignation="L+"
      connectiondescription="24V&amp;DC" terminalNr=""/>
</part></EDZ_Parts>"""})

# Duplicate pin designations — exercises the collision guard
make_7z("duplicate_pins.edz", {"part.part.xml": b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="DUP" P_ARTICLE_MANUFACTURER="Co"
  P_ARTICLE_ORDERNR="DUP-001" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@Dup Pins;" P_ARTICLE_DESCR2="">
  <functiontemplate connectionDesignation="1" connectiondescription="A" terminalNr="X01"/>
  <functiontemplate connectionDesignation="1" connectiondescription="B" terminalNr="X01"/>
  <functiontemplate connectionDesignation="1" connectiondescription="C" terminalNr="X01"/>
  <functiontemplate connectionDesignation="2" connectiondescription="D" terminalNr="X01"/>
</part></EDZ_Parts>"""})

# Rich multilang blob — exercises langDict parsing and pickLang fallbacks
make_7z("multilang.edz", {"part.part.xml": b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="ML" P_ARTICLE_MANUFACTURER="Co"
  P_ARTICLE_ORDERNR="ML-001" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="de_DE@Testteil;en_EN@Test Part;fr_FR@Pi\xc3\xa8ce test;zh_CN@\xe6\xb5\x8b\xe8\xaf\x95\xe9\x83\xa8\xe4\xbb\xb6;"
  P_ARTICLE_DESCR2="de_DE@Kommentar;;mit;;Semikolon;en_EN@Comment;;with;;semicolon;">
  <functiontemplate connectionDesignation="1"
      connectiondescription="L+" terminalNr="X01"/>
</part></EDZ_Parts>"""})

# Malformed multilang blob — exercises the regex edge cases
make_7z("malformed_multilang.edz", {"part.part.xml": b"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="BML" P_ARTICLE_MANUFACTURER="Co"
  P_ARTICLE_ORDERNR="BML-001" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="@@@;de_DE@;en_EN@;XX_XX@garbage@more@"
  P_ARTICLE_DESCR2="no_lang_markers_at_all">
  <functiontemplate connectionDesignation="1"
      connectiondescription="" terminalNr=""/>
</part></EDZ_Parts>"""})

# Unicode in pin designations and manufacturer
make_7z("unicode_pins.edz", {"part.part.xml": """<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="UNI" P_ARTICLE_MANUFACTURER="测试Co"
  P_ARTICLE_ORDERNR="UNI-001" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@Unicode Test;" P_ARTICLE_DESCR2="">
  <functiontemplate connectionDesignation="Ü1"
      connectiondescription="Ü+" terminalNr="Xα"/>
  <functiontemplate connectionDesignation="中文"
      connectiondescription="测试" terminalNr="Xβ"/>
  <functiontemplate connectionDesignation="ñ2"
      connectiondescription="café" terminalNr="Xγ"/>
</part></EDZ_Parts>""".encode()})

# ── 4. Filename-collision bait ────────────────────────────────────────────────
# ABC/123 and ABC 123 both sanitize to ABC_123.elmt — tests silent-overwrite path
print("\n[Filename collision bait]")
for variant, ordernr, label in [
    ("collision_1.edz", "ABC/123", "Part A"),
    ("collision_2.edz", "ABC 123", "Part B"),
]:
    make_7z(variant, {"part.part.xml": f"""<?xml version="1.0" encoding="utf-8"?>
<EDZ_Parts><part P_ARTICLE_PARTNR="{ordernr}" P_ARTICLE_MANUFACTURER="Co"
  P_ARTICLE_ORDERNR="{ordernr}" P_ARTICLE_TYPENR=""
  P_ARTICLE_DESCR1="en_EN@{label};" P_ARTICLE_DESCR2="">
  <functiontemplate connectionDesignation="1"
      connectiondescription="+" terminalNr="X01"/>
</part></EDZ_Parts>""".encode()})

total = len(os.listdir(OUT))
print(f"\nCorpus: {total} files written to {OUT}/")
