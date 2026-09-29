"""NSO Mongolia (1212.mn): consumer prices, exchange rates and exports, through PxWeb.

Each table is a POST of a PxWeb query to ``data.1212.mn``; the answer is json-stat2. The
dimension ids are Mongolian even in the English API (``Сар`` is the month), so the queries
and the parser use the dimension ids and category codes, which are stable, and check the
English labels only to make sure a code still means what it did.

* CPI, national, overall index (group ``0``), month-on-month and year-on-year percent change,
  one series per base year (``2015=100``, ``2020=100``, ``2023=100``). The query asks for
  every base, so a new base year shows up as a series the registry does not know, and the
  fetch rejects it: the splice (newest base first, in the build) then needs a human.
* MNT per USD, monthly average (code ``2``) and end of period (code ``10``). The two labels
  differ only in their leading spaces, which is why codes are used.
* Total exports, million USD a month.
* Exports of six goods, value (thousand USD) and volume, published as year-to-date totals
  and turned into monthly flows here (:func:`pipeline.transform.ytd_to_monthly`).

Licence: official statistics; 1212.mn allows reuse citing "Source: Mongolian Statistical
Service".
"""

from __future__ import annotations

import itertools
import math
import re

import pandas as pd

from ..transform import ytd_to_monthly
from . import series

API = "https://data.1212.mn/api/v1/en/NSO/Economy%2C%20environment/"
MONTH = "Сар"
BASE_YEAR = "Суурь он"
GROUP = "Бүлэг"
CURRENCY = "Валют"
TRADE_INDICATOR = "Гадаад худалдааны үндсэн үзүүлэлт"
MEASURE = "Статистик үзүүлэлт"
COMMODITY = "Гол нэр төрлийн бараа"

TABLES = {
    "cpi_mom": "Consumer%20Price%20Index/DT_NSO_0600_009V1.px",
    "cpi_yoy": "Consumer%20Price%20Index/DT_NSO_0600_010V1.px",
    "fx": "Money%20and%20Finance/DT_NSO_0700_008V1.px",
    "exports": "Foreign%20Trade/DT_NSO_1400_003V1.px",
    "commodities": "Foreign%20Trade/DT_NSO_1400_006V2_month.px",
}

# commodity code -> (series name, volume unit, the label NSO gives it)
GOODS = {
    "6": ("gold", "t", "Gold, unwrought or in semi-manufactured forms (t)"),
    "7": ("copper_conc", "kt", "Copper ores and concentrate (thous.t)"),
    "11": ("iron_ore", "kt", "Iron ores & concentrates (thous.t)"),
    "12": ("zinc_conc", "kt", "Zincum concentrate (thous.t)"),
    "31": ("coal", "kt", "Coal (thous.t)"),
    "32": ("crude_oil", "kbbl", "Crude petroleum oils (thous.barrel)"),
}
VOLUME, VALUE = "0", "1"  # MEASURE codes: "Volume", "Value(USD.thous)"

# A value of None means every category of that dimension (PxWeb's "all" filter). Dimensions
# left out, such as the month, come back whole.
QUERIES = {
    "cpi_mom": {BASE_YEAR: None, GROUP: ["0"]},
    "cpi_yoy": {BASE_YEAR: None, GROUP: ["0"]},
    "fx": {CURRENCY: ["2", "10"]},
    "exports": {TRADE_INDICATOR: ["11"]},
    "commodities": {MEASURE: [VOLUME, VALUE], COMMODITY: list(GOODS)},
}


def query(selection: dict[str, list[str] | None]) -> dict:
    """A PxWeb query body asking for json-stat2."""
    parts = []
    for code, values in selection.items():
        if values is None:
            parts.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
        else:
            parts.append({"code": code, "selection": {"filter": "item", "values": values}})
    return {"query": parts, "response": {"format": "json-stat2"}}


def fetch(http) -> dict:
    """Every table, decoded from json-stat2 JSON (``Http`` keeps to two requests a second)."""
    return {key: http.post(API + TABLES[key], json=query(QUERIES[key])).json() for key in TABLES}


# -- json-stat2 ----------------------------------------------------------------------------
def categories(ds: dict, dim: str) -> list[str]:
    """The category codes of one dimension, in the dataset's order."""
    index = ds["dimension"][dim]["category"]["index"]
    if isinstance(index, dict):
        return sorted(index, key=index.__getitem__)
    return list(index)


def label(ds: dict, dim: str, code: str) -> str:
    """The English label of a category, without the padding NSO puts in front."""
    return ds["dimension"][dim]["category"]["label"][code].strip()


def table(ds: dict) -> pd.DataFrame:
    """A json-stat2 dataset as a long table: one column of category codes per dimension
    (named by dimension id), then ``value`` (None where the cell is empty)."""
    dims = ds["id"]
    codes = [categories(ds, d) for d in dims]
    cells = math.prod(len(c) for c in codes)
    values = ds["value"]
    if isinstance(values, dict):  # the sparse form: {"position": value}
        dense: list[float | None] = [None] * cells
        for pos, v in values.items():
            dense[int(pos)] = v
        values = dense
    if len(values) != cells or list(ds["size"]) != [len(c) for c in codes]:
        raise ValueError("json-stat2: the values do not match the dimension sizes")
    frame = pd.DataFrame(list(itertools.product(*codes)), columns=dims, dtype=object)
    frame["value"] = pd.Series(values, dtype=object)
    return frame


def monthly(ds: dict, rows: pd.DataFrame) -> pd.Series:
    """The rows of one series as a monthly series: month codes become their ``YYYY-MM`` labels."""
    dates = [label(ds, MONTH, code) for code in rows[MONTH]]
    return series(zip(dates, rows["value"], strict=True))


def pick(frame: pd.DataFrame, codes: dict[str, str]) -> pd.DataFrame:
    """The rows whose dimension codes match, e.g. ``pick(frame, {CURRENCY: "2"})``."""
    mask = pd.Series(True, index=frame.index)
    for dim, code in codes.items():
        mask &= frame[dim] == code
    return frame[mask]


def check_label(ds: dict, dim: str, code: str, expected: str) -> None:
    found = label(ds, dim, code)
    if found != expected:
        raise ValueError(f"NSO {dim} code {code} is now {found!r}, expected {expected!r}")


# -- parse ---------------------------------------------------------------------------------
def parse(payload: dict) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}

    for key, kind in (("cpi_mom", "mom"), ("cpi_yoy", "yoy")):
        ds = payload[key]
        frame = table(ds)
        check_label(ds, GROUP, "0", "Overall index")
        for code in categories(ds, BASE_YEAR):
            base = re.fullmatch(r"(\d{4})=100", label(ds, BASE_YEAR, code))
            if base is None:
                raise ValueError(f"NSO CPI base {label(ds, BASE_YEAR, code)!r} is not YYYY=100")
            rows = pick(frame, {BASE_YEAR: code, GROUP: "0"})
            out[f"nso_cpi_{kind}_b{base.group(1)}"] = monthly(ds, rows)

    ds = payload["fx"]
    frame = table(ds)
    for code, name in (("2", "nso_usdmnt_monthly_avg"), ("10", "nso_usdmnt_eop")):
        check_label(ds, CURRENCY, code, "USD")
        out[name] = monthly(ds, pick(frame, {CURRENCY: code}))

    ds = payload["exports"]
    check_label(ds, TRADE_INDICATOR, "11", "Exports")
    out["nso_exports_total_musd"] = monthly(ds, pick(table(ds), {TRADE_INDICATOR: "11"}))

    ds = payload["commodities"]
    frame = table(ds)
    check_label(ds, MEASURE, VOLUME, "Volume")
    check_label(ds, MEASURE, VALUE, "Value(USD.thous)")
    for code, (good, unit, expected) in GOODS.items():
        check_label(ds, COMMODITY, code, expected)
        for measure, suffix in ((VALUE, "kusd"), (VOLUME, unit)):
            rows = pick(frame, {MEASURE: measure, COMMODITY: code})
            out[f"nso_export_{good}_{suffix}"] = ytd_to_monthly(monthly(ds, rows))
    return out
