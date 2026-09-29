"""FRED (Federal Reserve Bank of St. Louis): the broad dollar index and CNY per USD.

``GET https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}`` answers a two-column
CSV, ``observation_date,{series}``, with dates like ``2006-01-01`` and ``.`` where a value
is missing. No key. It must be fetched with the default user agent: a spoofed browser one
hangs.

* TWEXBGSMTH: nominal broad US dollar index, goods and services, January 2006 = 100. The
  build splices the discontinued TWEXBMTH (a static seed in ``data/static``) in front.
* EXCHUS: Chinese yuan per US dollar, monthly average.

Licence: Federal Reserve Board data; cite FRED.
"""

from __future__ import annotations

import csv
import io

import pandas as pd

from . import series

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"

SERIES = {
    "fred_usd_broad_index": "TWEXBGSMTH",
    "fred_cnyusd_monthly_avg": "EXCHUS",
}


def fetch(http) -> dict[str, str]:
    return {sid: http.get(URL.format(id=fred_id)).text for sid, fred_id in SERIES.items()}


def value(text: str) -> float | None:
    """A FRED cell: a number, or None for ``.`` and blanks."""
    text = text.strip()
    return None if text in ("", ".") else float(text)


def parse(payload: dict[str, str]) -> dict[str, pd.Series]:
    out = {}
    for sid, fred_id in SERIES.items():
        reader = csv.reader(io.StringIO(payload[sid]))
        header = next(reader, None)
        if header is None or len(header) != 2 or header[1].strip() != fred_id:
            raise ValueError(f"FRED {fred_id}: unexpected header {header}")
        out[sid] = series((row[0][:7], value(row[1])) for row in reader if row)
    return out
