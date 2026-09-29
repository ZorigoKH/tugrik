"""IMF DataMapper API v2: World Economic Outlook actuals and forecasts, by year.

``GET .../api/v2/{indicator}/MNG`` answers with every country, not just Mongolia, under
``values[indicator][country]`` as ``{"2025": 6.8, ...}``. Mongolia and China are read from
it. The ``indicators`` block names the WEO release (``World Economic Outlook (April
2026)``), recorded as the vintage.

Akamai in front of imf.org returns 403 for custom and browser user agents and 200 for the
default ``python-requests`` one; whether it admits GitHub's runners is what the probe
workflow is for. If it fails, growth falls back to WDI and the forecasts keep their previous
vintage (they change only in April and October).

Licence: IMF terms of use, free reuse with attribution.
"""

from __future__ import annotations

import re

import pandas as pd

from . import series

API = "https://www.imf.org/external/datamapper/api/v2/"
INDICATORS = ("NGDP_RPCH", "PCPIPCH", "GGXWDG_NGDP", "BCA_NGDPD")

# series id -> (indicator, country)
SERIES = {
    "imf_weo_gdp_growth": ("NGDP_RPCH", "MNG"),
    "imf_weo_cpi_inflation": ("PCPIPCH", "MNG"),
    "imf_weo_gov_debt_pct_gdp": ("GGXWDG_NGDP", "MNG"),
    "imf_weo_current_account_pct_gdp": ("BCA_NGDPD", "MNG"),
    "imf_weo_china_gdp_growth": ("NGDP_RPCH", "CHN"),
}


def fetch(http) -> dict[str, dict]:
    return {code: http.get(f"{API}{code}/MNG").json() for code in INDICATORS}


def parse(payload: dict[str, dict]) -> dict[str, pd.Series]:
    out = {}
    for sid, (code, country) in SERIES.items():
        values = payload[code].get("values", {}).get(code, {}).get(country)
        if not isinstance(values, dict) or not values:
            raise ValueError(f"DataMapper {code}: no values for {country}")
        out[sid] = series(values.items())
    return out


def info(payload: dict[str, dict]) -> dict[str, str]:
    """The WEO vintage, e.g. ``April 2026``, from the growth indicator's source line."""
    source = payload["NGDP_RPCH"].get("indicators", {}).get("NGDP_RPCH", {}).get("source", "")
    match = re.search(r"World Economic Outlook \((\w+ \d{4})\)", source)
    if match is None:
        raise ValueError(f"DataMapper: no WEO vintage in {source!r}")
    return {"weo_vintage": match.group(1)}
