"""
HTML parsers for the QET MantisBT bugtracker, built only on the stdlib
html.parser (no regex over HTML, no third-party deps).

The one rule that matters: when the page does not have the shape this
parser expects, it must fail loudly (ParseError) rather than silently
return an empty string for a field. Two concrete mechanisms:

  * ListPageParser asserts every data row in the ``#buglist`` table has
    exactly the 11 expected ``column-*`` cells, in order.
  * BugPageParser asserts the eight required ``bug-*`` cells (id, summary,
    description, status, resolution, reporter, date-submitted,
    last-modified) are each present exactly once.

Optional fields (steps-to-reproduce, additional-information, os, platform,
product version, ...) are only rendered by MantisBT when non-empty, so they
are returned as ``None`` when absent -- which is distinguishable from an
explicitly-empty string, never mistaken for a parse success.
"""
from __future__ import annotations

from html.parser import HTMLParser

BASE_URL = "https://qelectrotech.org/bugtracker/"


class ParseError(RuntimeError):
    """Raised when a fetched page does not have the expected HTML shape."""


# --- list page -----------------------------------------------------------

# The exact column order of the #buglist table (MantisBT 2.x "Ace" theme).
LIST_COLUMNS = [
    "column-selection",
    "column-edit",
    "column-priority",
    "column-id",
    "column-bugnotes-count",
    "column-attachments",
    "column-category",
    "column-severity",
    "column-status",
    "column-last-modified",
    "column-summary",
]

# Status ids that count as "open" (not resolved, not closed).
OPEN_STATUS_IDS = {10, 20, 30, 40, 50}


def _cell_text(cell: dict) -> str:
    return "".join(cell["text"]).replace("\xa0", " ").strip()


def _cell_status_id(cell: dict) -> int | None:
    for cls in cell["classes"]:
        if cls.startswith("status-") and cls.endswith("-fg"):
            try:
                return int(cls[len("status-"):-len("-fg")])
            except ValueError:
                return None
    return None


def _cell_has_handler(cell: dict) -> bool:
    return any("view_user_page.php" in h for h in cell["hrefs"])


class _BuglistParser(HTMLParser):
    """Walk the #buglist table and collect data rows with column assertions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.saw_tbody = False
        self._in_tbody = False
        self._finished = False
        self._in_tr = False
        self._row_cells: list[dict] = []
        self._row_cell: dict | None = None
        self._row_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._finished:
            return
        if tag == "tbody":
            self._in_tbody = True
            self.saw_tbody = True
            self._in_tr = False
            return
        if not self._in_tbody:
            return
        if tag == "tr":
            self._in_tr = True
            self._row_cells = []
            self._row_cell = None
            self._row_text = []
            return
        if tag == "td" and self._in_tr:
            a = dict(attrs)
            self._row_cell = {"class": a.get("class", ""), "text": [], "hrefs": [], "classes": []}
            return
        if self._row_cell is not None:
            a = dict(attrs)
            if tag == "br":
                self._row_text.append("\n")
            if tag == "a" and a.get("href"):
                self._row_cell["hrefs"].append(a["href"])
            if a.get("class"):
                self._row_cell["classes"].extend(a["class"].split())

    def handle_endtag(self, tag: str) -> None:
        if self._finished:
            return
        if tag == "tbody" and self._in_tbody:
            self._in_tbody = False
            self._finished = True
            self._in_tr = False
            return
        if not self._in_tbody:
            return
        if tag == "td" and self._row_cell is not None:
            self._row_cell["text"].append("".join(self._row_text))
            self._row_cells.append(self._row_cell)
            self._row_cell = None
            self._row_text = []
            return
        if tag == "tr" and self._in_tr:
            self._finish_row()
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if not self._finished and self._row_cell is not None:
            self._row_text.append(data)

    def _finish_row(self) -> None:
        if not self._row_cells:
            return
        classes = [c["class"] for c in self._row_cells]
        if len(classes) != len(LIST_COLUMNS) or classes != LIST_COLUMNS:
            got = ", ".join(f"'{c}'" for c in classes) or "(empty)"
            want = ", ".join(f"'{c}'" for c in LIST_COLUMNS)
            if len(classes) != len(LIST_COLUMNS):
                detail = (f"has {len(classes)} columns, expected {len(LIST_COLUMNS)}")
            else:
                detail = ("has the right column count but the classes/order "
                          "differ")
            raise ParseError(
                f"list page: buglist row {detail}. Got: [{got}]; want: [{want}]"
            )
        by = {c["class"]: c for c in self._row_cells}

        id_hrefs = by["column-id"]["hrefs"]
        if not id_hrefs:
            raise ParseError("list page: buglist row missing issue id link")
        bug_id = _extract_id_from_href(id_hrefs[0])

        self.rows.append(
            {
                "id": bug_id,
                "summary": _cell_text(by["column-summary"]),
                "category": _cell_text(by["column-category"]),
                "severity": _cell_text(by["column-severity"]),
                "status": _cell_text(by["column-status"]),
                "status_id": _cell_status_id(by["column-status"]),
                "has_handler": _cell_has_handler(by["column-status"]),
                "last_modified": _cell_text(by["column-last-modified"]),
                "bugnotes_count": _cell_text(by["column-bugnotes-count"]),
                "attachment_count": _cell_text(by["column-attachments"]),
            }
        )


def _extract_id_from_href(href: str) -> int:
    # href looks like "/bugtracker/view.php?id=339" or "view.php?id=339"
    marker = "view.php?id="
    i = href.find(marker)
    if i == -1:
        raise ParseError(f"list page: unexpected id link href: {href!r}")
    tail = href[i + len(marker):]
    digits = ""
    for ch in tail:
        if ch.isdigit():
            digits += ch
        else:
            break
    if not digits:
        raise ParseError(f"list page: id link has no numeric id: {href!r}")
    return int(digits)


def parse_list_page(page_html: str) -> list[dict]:
    """
    Parse one ``view_all_bug_page.php`` page into a list of row dicts.

    Raises ParseError if the #buglist table is missing or a data row does
    not have exactly the 11 expected columns.
    """
    start = page_html.find('id="buglist"')
    if start == -1:
        raise ParseError("list page: #buglist table not found")
    parser = _BuglistParser()
    parser.feed(page_html[start:])
    parser.close()
    if not parser.saw_tbody:
        raise ParseError("list page: #buglist <tbody> not found")
    return parser.rows


# --- bug detail page ------------------------------------------------------

# Fields that must be present exactly once on every bug detail page.
REQUIRED_BUG_CELLS = [
    "bug-id",
    "bug-summary",
    "bug-description",
    "bug-status",
    "bug-resolution",
    "bug-reporter",
    "bug-date-submitted",
    "bug-last-modified",
]

# Fields MantisBT only renders when non-empty (absent otherwise).
OPTIONAL_BUG_CELLS = [
    "bug-steps-to-reproduce",
    "bug-additional-information",
    "bug-os",
    "bug-os-build",
    "bug-platform",
    "bug-project",
    "bug-category",
    "bug-view-status",
    "bug-priority",
    "bug-severity",
    "bug-reproducibility",
    "bug-tags",
    "bug-assigned-to",
]


def _classes_status_id(classes: list[str]) -> int | None:
    for cls in classes:
        if cls.startswith("status-") and cls.endswith("-fg"):
            try:
                return int(cls[len("status-"):-len("-fg")])
            except ValueError:
                return None
    return None


def _file_id_from_href(href: str) -> int | None:
    marker = "file_id="
    i = href.find(marker)
    if i == -1:
        return None
    tail = href[i + len(marker):]
    digits = ""
    for ch in tail:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else None


class _BugCellCollector(HTMLParser):
    """Collect every ``<td class="bug-*">`` cell plus attachment links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: dict[str, list[str]] = {}
        self.cell_status_ids: dict[str, int | None] = {}
        self.cell_hrefs: dict[str, list[str]] = {}
        self.attachments: dict[int, str] = {}  # file_id -> filename ("" if none)
        self._in_cell = False
        self._cell_class: str | None = None
        self._text: list[str] = []
        self._classes: list[str] = []
        self._hrefs: list[str] = []
        self._in_a = False
        self._a_href: str | None = None
        self._a_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "td":
            cls = a.get("class", "") or ""
            if cls.startswith("bug-"):
                self._in_cell = True
                self._cell_class = cls
                self._text = []
                self._classes = []
                self._hrefs = []
            return
        if tag == "a" and a.get("href"):
            href = a["href"]
            self._in_a = True
            self._a_href = href
            self._a_text = []
            if "file_download.php?file_id=" in href:
                fid = _file_id_from_href(href)
                if fid is not None:
                    self.attachments.setdefault(fid, "")
            if self._in_cell:
                self._hrefs.append(href)
            return
        if tag == "br" and self._in_cell:
            self._text.append("\n")
        if a.get("class") and self._in_cell:
            self._classes.extend(a["class"].split())

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_cell:
            text = "".join(self._text)
            self.cells.setdefault(self._cell_class, []).append(text)
            if self._cell_class == "bug-status":
                self.cell_status_ids.setdefault(self._cell_class, _classes_status_id(self._classes))
            self.cell_hrefs.setdefault(self._cell_class, []).extend(self._hrefs)
            self._in_cell = False
            self._cell_class = None
            return
        if tag == "a" and self._in_a:
            text = "".join(self._a_text).strip()
            if self._a_href and "file_download.php?file_id=" in self._a_href:
                fid = _file_id_from_href(self._a_href)
                if fid is not None and text and not self.attachments.get(fid):
                    self.attachments[fid] = text
            self._in_a = False
            self._a_href = None
            self._a_text = []
            return

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._text.append(data)
        if self._in_a:
            self._a_text.append(data)


def parse_bug_page(page_html: str, bug_id: int) -> dict:
    """Parse one ``view.php?id=N`` page into a field dict.

    Raises ParseError if any REQUIRED_BUG_CELLS field is missing or appears
    more than once (the HTML shape changed, or a field silently vanished).
    """
    collector = _BugCellCollector()
    collector.feed(page_html)
    collector.close()

    for field in REQUIRED_BUG_CELLS:
        count = len(collector.cells.get(field, []))
        if count != 1:
            raise ParseError(
                f"bug {bug_id}: required field '{field}' appears {count} time(s), "
                f"expected exactly 1 -- page shape changed?"
            )

    def one(field: str) -> str:
        return collector.cells[field][0].replace("\xa0", " ").strip()

    out: dict = {
        "id": bug_id,
        "summary": one("bug-summary"),
        "description": one("bug-description"),
        "status": one("bug-status"),
        "status_id": collector.cell_status_ids.get("bug-status"),
        "resolution": one("bug-resolution"),
        "reporter": one("bug-reporter"),
        "date_submitted": one("bug-date-submitted"),
        "last_modified": one("bug-last-modified"),
    }

    # Strip the "NNNNNNN: " prefix MantisBT prepends to the summary cell.
    prefix = f"{bug_id:07d}: "
    if out["summary"].startswith(prefix):
        out["summary"] = out["summary"][len(prefix):]

    for field in OPTIONAL_BUG_CELLS:
        vals = collector.cells.get(field, [])
        out[field.removeprefix("bug-")] = vals[0].replace("\xa0", " ").strip() if vals else None

    # Attachments: full download URLs (deduped by file_id).
    out["attachments"] = [
        {
            "file_id": fid,
            "filename": name,
            "url": f"{BASE_URL}file_download.php?file_id={fid}&type=bug",
        }
        for fid, name in sorted(collector.attachments.items())
    ]

    return out


def clean_text(s: str | None) -> str:
    """Normalise whitespace (not HTML parsing) for display/classification."""
    if s is None:
        return ""
    return " ".join(s.split())
