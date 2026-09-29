"""IMF data portal, SDMX 2.1 REST, as CSV: exchange rates, CPI and commodity prices.

No key. The CSV comes back when the request says ``Accept:
application/vnd.sdmx.data+csv;version=1.0.0``; the user agent must stay the default (see
:mod:`pipeline.http`). One row per observation, with the dimensions as columns;
``TIME_PERIOD`` looks like ``2026-M08``. Some responses carry stray rows dated 1900, which
are dropped.

* ER, Mongolia: MNT per USD, period average (``PA_RT``) and end of period (``EOP_RT``) -
  inputs to the FX consensus.
* CPI, Mongolia, all items: year-on-year and month-on-month percent change - the fallback
  if NSO fails, and a cross-check on it.
* PCPS: copper, gold and zinc in USD - a cross-check on the Pink Sheet.
* ER, China: CNY per USD, period average - the fallback for FRED's.

Licence: IMF terms of use, free reuse with attribution.
"""

from __future__ import annotations

import io

import pandas as pd

from . import series

API = "https://api.imf.org/external/sdmx/2.1/data/"
URLS = {
    "er_mng": API + "IMF.STA,ER,latest/MNG.XDC_USD..M",
    "cpi_mng": API + "IMF.STA,CPI,latest/MNG.CPI._T..M",
    "pcps": API + "IMF.RES,PCPS/G001.PCOPP+PGOLD+PZINC.USD.M?startPeriod=1990",
    "er_chn": API + "IMF.STA,ER,latest/CHN.XDC_USD..M",
}
ACCEPT = {"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}


def fetch(http) -> dict[str, str]:
    return {key: http.get(url, headers=ACCEPT).text for key, url in URLS.items()}


def sdmx_series(text: str, **match: str) -> pd.Series:
    """The monthly observations of the rows whose columns equal ``match``."""
    frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    missing = [c for c in ("TIME_PERIOD", "OBS_VALUE", *match) if c not in frame.columns]
    if missing:
        raise ValueError(f"SDMX CSV has no column {missing[0]}")
    for column, value in match.items():
        frame = frame[frame[column] == value]
    frame = frame[~frame["TIME_PERIOD"].str.startswith("1900")]
    dates = frame["TIME_PERIOD"].str.replace("-M", "-", regex=False)
    values = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
    return series(zip(dates, values, strict=True))


def parse(payload: dict[str, str]) -> dict[str, pd.Series]:
    er = {"COUNTRY": "MNG", "INDICATOR": "XDC_USD", "FREQUENCY": "M"}
    cpi = {"COUNTRY": "MNG", "INDEX_TYPE": "CPI", "COICOP_1999": "_T", "FREQUENCY": "M"}
    pcps = {"COUNTRY": "G001", "DATA_TRANSFORMATION": "USD", "FREQUENCY": "M"}
    er_chn = {"COUNTRY": "CHN", "INDICATOR": "XDC_USD", "FREQUENCY": "M"}
    return {
        "imf_usdmnt_monthly_avg": sdmx_series(
            payload["er_mng"], **er, TYPE_OF_TRANSFORMATION="PA_RT"
        ),
        "imf_usdmnt_eop": sdmx_series(payload["er_mng"], **er, TYPE_OF_TRANSFORMATION="EOP_RT"),
        "imf_cpi_yoy": sdmx_series(
            payload["cpi_mng"], **cpi, TYPE_OF_TRANSFORMATION="YOY_PCH_PA_PT"
        ),
        "imf_cpi_mom": sdmx_series(
            payload["cpi_mng"], **cpi, TYPE_OF_TRANSFORMATION="POP_PCH_PA_PT"
        ),
        "imf_pcps_copper": sdmx_series(payload["pcps"], **pcps, INDICATOR="PCOPP"),
        "imf_pcps_gold": sdmx_series(payload["pcps"], **pcps, INDICATOR="PGOLD"),
        "imf_pcps_zinc": sdmx_series(payload["pcps"], **pcps, INDICATOR="PZINC"),
        "imf_cnyusd_monthly_avg": sdmx_series(
            payload["er_chn"], **er_chn, TYPE_OF_TRANSFORMATION="PA_RT"
        ),
    }
