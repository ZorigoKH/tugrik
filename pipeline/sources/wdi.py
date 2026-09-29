"""World Bank World Development Indicators, API v2: annual growth, FDI and current account.

``GET https://api.worldbank.org/v2/country/{country}/indicator/{code}?format=json&per_page=100``
answers ``[meta, rows]``. With 100 rows a page every indicator fits on one page, and the
parser insists on it (``pages == 1``) rather than silently reading part of a series. Years
without data come back as ``"value": null`` and are dropped.

Licence: CC BY 4.0.
"""

from __future__ import annotations

import pandas as pd

from . import series

API = "https://api.worldbank.org/v2/country/{country}/indicator/{code}?format=json&per_page=100"

# series id -> (country, indicator)
SERIES = {
    "wdi_gdp_growth": ("MNG", "NY.GDP.MKTP.KD.ZG"),
    "wdi_fdi_pct_gdp": ("MNG", "BX.KLT.DINV.WD.GD.ZS"),
    "wdi_current_account_pct_gdp": ("MNG", "BN.CAB.XOKA.GD.ZS"),
    "wdi_china_gdp_growth": ("CHN", "NY.GDP.MKTP.KD.ZG"),
}


def fetch(http) -> dict[str, list]:
    return {
        sid: http.get(API.format(country=country, code=code)).json()
        for sid, (country, code) in SERIES.items()
    }


def parse(payload: dict[str, list]) -> dict[str, pd.Series]:
    out = {}
    for sid in SERIES:
        body = payload[sid]
        if not (isinstance(body, list) and len(body) == 2 and isinstance(body[0], dict)):
            raise ValueError(f"WDI {sid}: not a [meta, rows] answer")
        meta, rows = body
        if meta.get("pages") != 1:
            raise ValueError(f"WDI {sid}: {meta.get('pages')} pages, expected 1")
        if not rows:
            raise ValueError(f"WDI {sid}: no rows")
        out[sid] = series((row["date"], row["value"]) for row in rows)
    return out
