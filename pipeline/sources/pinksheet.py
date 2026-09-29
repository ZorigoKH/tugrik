"""World Bank Pink Sheet: monthly commodity prices in nominal US dollars.

The workbook's address carries a hash that the World Bank rotates about once a year, and old
addresses stay live but stop being updated. So every fetch reads the commodity-markets page
for the current link to ``CMO-Historical-Data-Monthly.xlsx`` instead of remembering one, and
the fetch stage checks that the workbook's "Updated on" date is recent.

In the sheet "Monthly Prices" (found by name: a "Mismatch Details" sheet now comes first)
the commodity names are in the row after the title block, the units in the row below, and
then one row per month labelled ``2026M08``. Missing prices are written ``…``.

Licence: CC BY 4.0.
"""

from __future__ import annotations

import io
import re
from datetime import datetime

import openpyxl
import pandas as pd

from . import series

PAGE = "https://www.worldbank.org/en/research/commodity-markets"
LINK = re.compile(r"https://thedocs\.worldbank\.org/[^\"'\s<>]*/CMO-Historical-Data-Monthly\.xlsx")
SHEET = "Monthly Prices"
MONTH = re.compile(r"(\d{4})M(\d{2})")

# series id -> (column name in the sheet, unit in the row below it)
COLUMNS = {
    "pinksheet_copper": ("Copper", "($/mt)"),
    "pinksheet_coal_australian": ("Coal, Australian", "($/mt)"),
    "pinksheet_gold": ("Gold", "($/troy oz)"),
    "pinksheet_iron_ore": ("Iron ore, cfr spot", "($/dmtu)"),
    "pinksheet_brent": ("Crude oil, Brent", "($/bbl)"),
    "pinksheet_zinc": ("Zinc", "($/mt)"),
}


def find_link(html: str) -> str:
    """The monthly workbook's address on the commodity-markets page."""
    match = LINK.search(html)
    if match is None:
        raise ValueError(f"no link to CMO-Historical-Data-Monthly.xlsx on {PAGE}")
    return match.group(0)


def fetch(http) -> dict:
    url = find_link(http.get(PAGE).text)
    return {"url": url, "xlsx": http.get(url).content}


def rows(xlsx: bytes) -> list[tuple]:
    """The cell values of the "Monthly Prices" sheet, row by row."""
    book = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
    try:
        if SHEET not in book.sheetnames:
            raise ValueError(f"the Pink Sheet workbook has no sheet {SHEET!r}")
        return [tuple(row) for row in book[SHEET].iter_rows(values_only=True)]
    finally:
        book.close()


def updated_on(cells: list[tuple]) -> str:
    """The "Updated on September 02, 2026" line of the title block, as ``2026-09-02``."""
    for row in cells[:10]:
        first = row[0] if row else None
        if isinstance(first, str) and first.strip().startswith("Updated on"):
            text = first.strip().removeprefix("Updated on").strip()
            return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    raise ValueError("the Pink Sheet has no 'Updated on' line")


def price(cell) -> float | None:
    """A price cell: a number, or None for ``…``, ``..`` and blanks."""
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return float(cell)
    return None


def parse(payload: dict) -> dict[str, pd.Series]:
    cells = rows(payload["xlsx"])
    names = {name for name, _ in COLUMNS.values()}
    header = next(
        (i for i, row in enumerate(cells[:20]) if names <= {str(c).strip() for c in row if c}),
        None,
    )
    if header is None:
        raise ValueError("the Pink Sheet has no header row naming every commodity used")
    head = [str(c).strip() if c is not None else "" for c in cells[header]]
    units = [str(c).strip() if c is not None else "" for c in cells[header + 1]]
    months = []
    for row in cells[header + 2 :]:
        match = MONTH.fullmatch(str(row[0]).strip()) if row and row[0] is not None else None
        if match:
            months.append((f"{match.group(1)}-{match.group(2)}", row))
    out = {}
    for sid, (name, unit) in COLUMNS.items():
        col = head.index(name)
        if units[col] != unit:
            raise ValueError(f"Pink Sheet {name!r} is now in {units[col]!r}, expected {unit!r}")
        out[sid] = series(
            (month, price(row[col] if col < len(row) else None)) for month, row in months
        )
    return out


def info(payload: dict) -> dict[str, str]:
    return {"updated_on": updated_on(rows(payload["xlsx"])), "url": payload["url"]}
