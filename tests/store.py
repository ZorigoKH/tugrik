"""A complete synthetic store for the build tests: every registry series, the static seeds
and ``status.json``, in the real shapes and date ranges but with made-up numbers (random
walks from a fixed seed). No real data, least of all the BoM's, is involved."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.fetch import to_csv
from pipeline.registry import SERIES
from pipeline.sources import series

LAST_MONTH = "2026-08"
TODAY = date(2026, 9, 28)


def months(first: str, last: str = LAST_MONTH) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def years(first: int, last: int) -> list[str]:
    return [str(y) for y in range(first, last + 1)]


def walk(rng: np.random.Generator, n: int, start: float, drift: float, vol: float) -> np.ndarray:
    """A geometric random walk of ``n`` steps from ``start``."""
    return start * np.exp(np.cumsum(rng.normal(drift, vol, n)))


def make(rng: np.random.Generator | None = None) -> dict[str, pd.Series]:
    """Every series of the store, plus the static seeds as ``static/<name>``."""
    rng = rng or np.random.default_rng(7)
    out: dict[str, pd.Series] = {}

    # the BoM's daily rate and the three published averages built from it
    first_day, last_day = date(2001, 1, 2), date(2026, 9, 27)
    days = [(first_day + timedelta(d)).isoformat() for d in range((last_day - first_day).days + 1)]
    out["bom_usdmnt_daily"] = series(
        zip(days, walk(rng, len(days), 1100.0, 0.00013, 0.003), strict=True)
    )
    daily = out["bom_usdmnt_daily"]
    weekdays = daily[pd.to_datetime(pd.Index(daily.index)).weekday < 5]
    mean = weekdays.groupby(weekdays.index.str[:7]).mean().loc[:LAST_MONTH]
    early = months("1990-07", "2000-12")
    early_values = walk(rng, len(early), 5.6, 0.04, 0.03)
    for name, first in (("imf", "1990-07"), ("bom", "1993-01"), ("nso", "1994-01")):
        noise = 1 + rng.normal(0, 0.0002, len(early) + len(mean))
        values = np.concatenate([early_values, mean.to_numpy()]) * noise
        s = series(zip(early + list(mean.index), values, strict=True))
        out[f"{name}_usdmnt_monthly_avg"] = s[s.index >= first]
    last = daily.groupby(daily.index.str[:7]).last().loc[:LAST_MONTH]
    out["nso_usdmnt_eop"] = series(last.loc["2006-01":].items())
    out["imf_usdmnt_eop"] = series(
        zip(early + list(last.index), [*early_values, *last], strict=True)
    )

    # policy decisions, CPI
    decisions = [
        ("2007-07-09", 6.4),
        ("2008-12-15", 9.75),
        ("2009-03-12", 14.0),
        ("2012-06-05", 13.25),
        ("2016-08-18", 15.0),
        ("2020-03-11", 10.0),
        ("2021-09-01", 6.0),
        ("2022-03-15", 9.0),
        ("2023-03-20", 13.0),
        ("2025-03-10", 12.0),
        ("2026-08-12", 12.5),
        ("2026-09-17", 12.5),
    ]
    out["bom_policy_rate_decisions"] = series(decisions)
    for kind, loc, scale in (("mom", 0.6, 1.0), ("yoy", 8.0, 3.0)):
        m = months("1991-10") if kind == "mom" else months("1993-01")
        v = rng.normal(loc, scale, len(m))
        full = series(zip(m, v, strict=True))
        out[f"nso_cpi_{kind}_b2015"] = full.loc[:"2022-07"]
        out[f"nso_cpi_{kind}_b2020"] = full.loc["2020-01":] + 0.05
        out[f"nso_cpi_{kind}_b2023"] = full.loc["2023-02" if kind == "mom" else "2024-01" :] + 0.1
        out[f"imf_cpi_{kind}"] = full.loc["2006-02" if kind == "mom" else "2007-01" :] + 0.02
    out["bom_cpi_yoy"] = out["nso_cpi_yoy_b2023"].combine_first(out["nso_cpi_yoy_b2020"])
    out["bom_cpi_yoy"] = series(out["bom_cpi_yoy"].loc["2009-09":].items())

    # trade
    trade = months("2011-01")
    goods = {
        "coal": ("kt", 2000.0, 80.0),
        "copper_conc": ("kt", 100.0, 1500.0),
        "gold": ("t", 1.0, 50000.0),
        "iron_ore": ("kt", 500.0, 70.0),
        "crude_oil": ("kbbl", 500.0, 60.0),
        "zinc_conc": ("kt", 20.0, 1000.0),
    }
    for good, (unit, volume, price) in goods.items():
        q = walk(rng, len(trade), volume, 0.004, 0.15)
        p = walk(rng, len(trade), price, 0.0, 0.06)
        out[f"nso_export_{good}_{unit}"] = series(zip(trade, q, strict=True))
        out[f"nso_export_{good}_kusd"] = series(zip(trade, q * p, strict=True))
    m = months("1997-01")
    out["nso_exports_total_musd"] = series(zip(m, walk(rng, len(m), 30.0, 0.012, 0.1), strict=True))

    # prices
    m = months("1990-01")
    for sid, start in (
        ("copper", 2500.0),
        ("coal_australian", 40.0),
        ("gold", 380.0),
        ("iron_ore", 30.0),
        ("brent", 20.0),
        ("zinc", 1200.0),
    ):
        out[f"pinksheet_{sid}"] = series(zip(m, walk(rng, len(m), start, 0.004, 0.05), strict=True))
    for metal in ("copper", "gold", "zinc"):
        ps = out[f"pinksheet_{metal}"].loc["1992-01":]
        out[f"imf_pcps_{metal}"] = ps * (1 + rng.normal(0, 0.002, len(ps)))
    out["fred_cnyusd_monthly_avg"] = series(
        zip(m, walk(rng, len(m), 4.7, 0.001, 0.01), strict=True)
    )
    out["imf_cnyusd_monthly_avg"] = out["fred_cnyusd_monthly_avg"] * 1.0001
    m = months("2006-01")
    out["fred_usd_broad_index"] = series(
        zip(m, walk(rng, len(m), 100.0, 0.0005, 0.015), strict=True)
    )
    m = months("1990-01", "2019-12")
    out["static/fred_twexbmth"] = series(
        zip(m, walk(rng, len(m), 90.0, 0.0005, 0.015), strict=True)
    )

    # annual
    for sid, first, last, loc, scale in (
        ("wdi_gdp_growth", 1990, 2025, 5.0, 4.0),
        ("wdi_china_gdp_growth", 1990, 2025, 8.0, 2.0),
        ("wdi_fdi_pct_gdp", 1990, 2024, 10.0, 8.0),
        ("wdi_current_account_pct_gdp", 1990, 2024, -8.0, 6.0),
        ("imf_weo_gdp_growth", 1990, 2031, 5.0, 4.0),
        ("imf_weo_cpi_inflation", 1991, 2031, 8.0, 4.0),
        ("imf_weo_gov_debt_pct_gdp", 2006, 2031, 60.0, 10.0),
        ("imf_weo_current_account_pct_gdp", 1991, 2031, -8.0, 6.0),
        ("imf_weo_china_gdp_growth", 1990, 2031, 8.0, 2.0),
    ):
        y = years(first, last)
        out[sid] = series(zip(y, rng.normal(loc, scale, len(y)), strict=True))
    for good, code in (
        ("coal", "hs2701"),
        ("copper_conc", "hs2603"),
        ("gold", "hs7108"),
        ("iron_ore", "hs2601"),
        ("crude_oil", "hs2709"),
        ("zinc_conc", "hs2608"),
    ):
        y = years(1996, 2007) if good != "zinc_conc" else years(2002, 2007)
        out[f"static/comtrade_mng_exports_{good}_{code}_musd"] = series(
            zip(y, rng.uniform(1.0, 300.0, len(y)), strict=True)
        )
    missing = set(SERIES) - set(out)
    assert not missing, missing
    return out


def status(stale: dict[str, str] | None = None) -> dict:
    """``status.json`` with every source ok, except those in ``stale`` ({source: error})."""
    stale = stale or {}
    sources = {}
    for src in ("bom", "nso", "pinksheet", "imf_sdmx", "imf_datamapper", "wdi", "fred"):
        info = {
            "imf_datamapper": {"weo_vintage": "April 2026"},
            "pinksheet": {"updated_on": "2026-09-02", "url": "https://example.org/x.xlsx"},
        }
        sources[src] = {
            "status": "stale" if src in stale else "ok",
            "error": stale.get(src),
            "last_obs": None,
            "last_changed": "2026-09-28",
            "revisions": 0,
            "info": info.get(src, {}),
        }
    return {"sources": sources, "series": {}, "store_version": 1}


def write(directory: Path, data: dict[str, pd.Series], stat: dict | None = None) -> Path:
    """Write a store (series, static seeds and status.json) into ``directory``."""
    (directory / "static").mkdir(parents=True, exist_ok=True)
    for sid, s in data.items():
        (directory / f"{sid}.csv").write_bytes(to_csv(s))
    (directory / "status.json").write_text(json.dumps(stat or status()), encoding="utf-8")
    return directory
