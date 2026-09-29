"""Build: turn the store into the site's data, offline and deterministically.

    python -m pipeline.build --store data --out web/data --csv web/public/csv
                             [--today YYYY-MM-DD] [--save-inputs DIR]

The steps are transforms (:mod:`pipeline.transform`), the frozen regressions
(:mod:`pipeline.models`), the JSON records and their takeaways
(:mod:`pipeline.summarize`), then the files: ``meta.json``, ``overview.json``,
``copper.json``, ``coal.json``, ``prices.json``, ``growth.json`` and ``sources.json`` in
``--out``, and one ``<series id>.csv`` in ``--csv`` for every series that may be
redistributed (World Bank, NSO, IMF, the Fed, and this project's derived series; never the
BoM's, which carry no licence, nor Comtrade's).

Everything is staged in a temporary directory and checked by :mod:`pipeline.validate`
before anything moves; then the CSV files, the page files and ``meta.json`` (last) replace
the old ones with ``os.replace``. Files whose bytes are unchanged are left alone.
``generated_at`` changes only when some other content changed, so a rerun on the same
store (and the same ``--today``) changes no bytes.

``--today`` (default: the current date) is the date staleness is judged against: a source
is stale when its last fetch failed (``data/status.json``) or when a series is older than
its ``max_age_days``. When NSO or FRED is stale, the IMF's CPI or CNY/USD continues their
series (``"fallback"``). ``--save-inputs DIR`` also writes the model inputs to ``DIR`` in
the store's CSV format; that is how ``tests/fixtures/store_2026-09`` was made.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import sandwich

from . import SCHEMA_VERSION, __version__, models, transform
from . import summarize as s
from .fetch import read_series, read_status, to_csv
from .registry import SERIES, SOURCES
from .sources import SOURCE_IDS, series
from .validate import validate

PAGES = ("overview", "copper", "coal", "prices", "growth", "sources")
BOOM_BUST_FROM = "2008"
YEARS_FROM = "2002"
# a stale source whose role another source fills: {source: (what, fallback source)}
FALLBACKS = {"nso": ("CPI", "imf_sdmx"), "fred": ("CNY per USD", "imf_sdmx")}
MONTHS = "January February March April May June July August September October November December"
MONTH_NUMBERS = {name: i + 1 for i, name in enumerate(MONTHS.split())}

Log = Callable[[str], object]


class BuildError(Exception):
    """The build cannot go on; nothing has been written."""


# -- the store -----------------------------------------------------------------------------
def read_store(store: Path) -> tuple[dict[str, pd.Series], dict]:
    """Every stored series (static seeds as ``static/<name>``) and ``status.json``."""
    if not store.is_dir():
        raise BuildError(f"no store at {store}")
    data = {p.stem: read_series(p) for p in sorted(store.glob("*.csv"))}
    data |= {f"static/{p.stem}": read_series(p) for p in sorted(store.glob("static/*.csv"))}
    return data, read_status(store)


def period_end(when: str) -> date:
    """The last day of the period a stored date names (``YYYY``, ``YYYY-MM`` or a day)."""
    if len(when) == 4:
        return date(int(when), 12, 31)
    if len(when) == 7:
        return pd.Period(when, freq="M").end_time.date()
    return date.fromisoformat(when)


def weo_vintage(status: Mapping) -> str | None:
    info = status["sources"].get("imf_datamapper", {}).get("info", {})
    return info.get("weo_vintage")


def vintage_end(vintage: str) -> date:
    """``"April 2026"`` -> the last day of April 2026."""
    month, year = vintage.split()
    return period_end(f"{year}-{MONTH_NUMBERS[month]:02d}")


def superseded(sid: str, data: Mapping[str, pd.Series]) -> bool:
    """True for an NSO CPI series of an older base year when a newer base is stored: it
    stopped when the new base began, so its age says nothing."""
    match = re.fullmatch(r"(nso_cpi_\w+_b)(\d{4})", sid)
    if match is None:
        return False
    prefix, base = match.groups()
    return any(k.startswith(prefix) and k[len(prefix) :] > base for k in data)


def series_stale(sid: str, data: Mapping[str, pd.Series], today: date) -> bool:
    """True when a stored series is missing or older than its ``max_age_days`` (an NSO CPI
    series of a superseded base never is)."""
    if superseded(sid, data):
        return False
    if sid not in data or data[sid].empty:
        return True
    limit = SERIES[sid].max_age_days
    return limit is not None and (today - period_end(data[sid].index[-1])).days > limit


def health(data: Mapping[str, pd.Series], status: Mapping, today: date) -> dict[str, str]:
    """Each source's status: ``"stale"`` when its last fetch failed or one of its series is
    too old, ``"fallback"`` when it is stale but another source fills its role, else ``"ok"``.

    The WEO's forecasts run years ahead, so the DataMapper's age is that of its vintage.
    """
    stale = set()
    for src in SOURCE_IDS:
        failed = status["sources"].get(src, {}).get("status") == "stale"
        ids = [sid for sid, spec in SERIES.items() if spec.source == src]
        if src == "imf_datamapper":
            vintage = weo_vintage(status)
            limit = max(SERIES[sid].max_age_days or 0 for sid in ids)
            old = vintage is None or (today - vintage_end(vintage)).days > limit
            old = old or any(sid not in data for sid in ids)
        else:
            old = any(series_stale(sid, data, today) for sid in ids)
        if failed or old:
            stale.add(src)
    out = {}
    for src in SOURCE_IDS:
        if src not in stale:
            out[src] = "ok"
        elif src in FALLBACKS and FALLBACKS[src][1] not in stale:
            out[src] = "fallback"
        else:
            out[src] = "stale"
    return out


# -- the series behind the pages -----------------------------------------------------------
def change_pct(x: pd.Series, k: int) -> pd.Series:
    """The k-month percent change of a stored monthly series, as a stored series.

    The pages show these to readers as "% change", so they are true percent changes;
    the regressions use 100 x log changes (:func:`pipeline.models.dlog`) instead.
    """
    m = models.monthly(x)
    change = 100 * (m / m.shift(k) - 1)
    return series((p.strftime("%Y-%m"), v) for p, v in change.items())


def change_pct_annual(a: pd.Series) -> pd.Series:
    """The percent change of a stored annual series on the previous year."""
    m = models.annual(a)
    change = 100 * (m / m.shift(1) - 1)
    return series((str(p), v) for p, v in change.items())


def weo(
    data: Mapping[str, pd.Series],
    sid: str,
    vintage: str | None,
    key: str,
    after: str | None = None,
) -> dict:
    """The WEO forecasts of one indicator: the years from the vintage's year on and, with
    ``after`` (the last actual year), only the years after it, so that a stale vintage
    never shows a year as both actual and forecast."""
    first = vintage.split()[-1] if vintage else "9999"
    ahead = data.get(sid, series([]))
    ahead = ahead[ahead.index >= first]
    if after is not None:
        ahead = ahead[ahead.index > after]
    return {"vintage": vintage, "years": list(ahead.index), key: [s.num(v) for v in ahead]}


FX_DAILY_TOLERANCE = 0.005  # the consensus against the BoM daily weekday mean, from 2001


def check_fx_consensus(fx: pd.Series, daily: pd.Series) -> None:
    """Raise :class:`BuildError` unless every consensus month from 2001 on that has a BoM
    daily weekday mean lies within 0.5% of it (the largest gap in the 2026-09 data is
    0.25%, in July 2017)."""
    mean = transform.weekday_mean(daily)
    months = [m for m in fx.index if m >= transform.FX_DAILY_FROM and m in mean.index]
    if not months:
        return
    gap = (fx[months] / mean[months] - 1).abs()
    worst = gap.idxmax()
    if gap[worst] > FX_DAILY_TOLERANCE:
        raise BuildError(
            f"the consensus exchange rate for {worst}, {fx[worst]:g}, is "
            f"{100 * gap[worst]:.2f}% from the BoM daily weekday mean {mean[worst]:g} "
            "(limit 0.5%)"
        )


def pages(data: Mapping[str, pd.Series], status: Mapping, states: Mapping[str, str]):
    """The model inputs, the estimates and every JSON record (with the derived series)."""
    stale = {src for src, state in states.items() if state != "ok"}
    try:
        inputs = transform.model_inputs(data, stale)
        est = models.estimate(inputs)
    except (KeyError, ValueError, IndexError) as exc:
        raise BuildError(f"the model inputs are incomplete: {type(exc).__name__}: {exc}") from exc

    fx = inputs[models.FX]
    check_fx_consensus(fx, data.get("bom_usdmnt_daily", series([])))
    cpi_yoy = transform.cpi(data, "yoy")
    if "nso" in stale and "imf_cpi_yoy" in data:
        cpi_yoy = transform.extend(cpi_yoy, data["imf_cpi_yoy"])
    decisions = data["bom_policy_rate_decisions"]
    policy = transform.policy_month_end(decisions, max(fx.index[-1], cpi_yoy.index[-1]))
    copper = inputs[models.COPPER]
    copper_avg = transform.annual_mean(copper)
    copper_change = change_pct_annual(copper_avg)
    fx_12m = change_pct(fx, 12)
    decembers = fx_12m[fx_12m.index.str.endswith("-12")]
    dec_dec = series((m[:4], v) for m, v in decembers.items())
    vintage = weo_vintage(status)

    years = (
        pd.DataFrame({"fx_dec_dec_pct": dec_dec, "copper_avg_pct": copper_change})
        .sort_index()
        .loc[YEARS_FROM : dec_dec.index[-1]]
    )
    coal_uv = transform.unit_value(data["nso_export_coal_kusd"], data["nso_export_coal_kt"])
    growth_last = data["wdi_gdp_growth"].index[-1]
    boom_years = [str(y) for y in range(int(BOOM_BUST_FROM), int(growth_last) + 1)]
    boom = pd.DataFrame(
        {
            "gdp_growth_pct": data["wdi_gdp_growth"],
            "cpi_pct": data.get("imf_weo_cpi_inflation", series([])),
            "fx_dec_dec_pct": dec_dec,
            "policy_rate_dec_pct": series(
                (m[:4], v) for m, v in policy.items() if m.endswith("-12")
            ),
            "fdi_pct_gdp": data.get("wdi_fdi_pct_gdp", series([])),
            "current_account_pct_gdp": data.get("wdi_current_account_pct_gdp", series([])),
            "gov_debt_pct_gdp": data.get("imf_weo_gov_debt_pct_gdp", series([])),
            "exports_usd_bn": transform.annual_sum(data["nso_exports_total_musd"]) / 1e3,
            "copper_pct": copper_change,
        }
    ).reindex(boom_years)
    _, weights_source = transform.mxpi_weights(
        {g: data[sid] for g, sid in transform.COMTRADE.items()},
        {g: transform.annual_sum(data[sid]) for g, sid in transform.NSO_EXPORTS.items()},
    )

    out = {
        "copper": s.copper_page(est["copper"], est["fit12"]),
        "coal": s.coal_page(
            est["coal"], data["nso_export_coal_kt"], coal_uv, data["pinksheet_coal_australian"]
        ),
        "prices": s.prices_page(
            est["passthrough_dl"],
            est["passthrough_pref"],
            {"cpi_yoy_pct": cpi_yoy, "policy_rate_pct": policy, "fx_12m_pct": fx_12m},
            years,
            weo(data, "imf_weo_cpi_inflation", vintage, "cpi_avg_pct"),
        ),
        "growth": s.growth_page(
            est["growth"],
            weights_source,
            weo(data, "imf_weo_gdp_growth", vintage, "gdp_growth_pct", after=growth_last),
            boom,
        ),
    }
    prices, weights = models.mxpi_inputs(inputs)
    derived = {
        "derived_usdmnt_monthly_avg": fx,
        "derived_cpi_mom": inputs[models.CPI_MOM],
        "derived_cpi_yoy": cpi_yoy,
        "derived_usd_broad_index": inputs[models.USD],
        "derived_cnyusd_monthly_avg": inputs[models.CNY],
        "derived_coal_unit_value_usd_t": coal_uv,
        "derived_mxpi_pct": transform.mxpi(prices, weights),
        **{sid: inputs[sid] for sid in models.WEIGHTS.values()},
    }
    tiles = overview_tiles(data, inputs, cpi_yoy, policy, coal_uv, states, vintage)
    out["overview"] = s.overview(tiles, out)
    return inputs, out, derived


def overview_tiles(data, inputs, cpi_yoy, policy, coal_uv, states, vintage) -> list[dict]:
    """The six tiles of the home page. A tile is stale when its source is; the CPI tile
    says ``"fallback"`` when the IMF continues NSO's CPI, and the exchange-rate tile when
    the BoM is stale and the consensus rests on NSO's and the IMF's averages alone."""

    def status(src: str, fallback: bool = False) -> str:
        if fallback and states[src] == "fallback":
            return "fallback"
        return "ok" if states[src] == "ok" else "stale"

    if states["bom"] == "ok":
        fx_status = "ok"
    elif "ok" in (states["nso"], states["imf_sdmx"]):
        fx_status = "fallback"
    else:
        fx_status = "stale"
    fx = inputs[models.FX]
    copper = inputs[models.COPPER]
    volume = data["nso_export_coal_kt"] / 1e3
    decisions = data["bom_policy_rate_decisions"]
    last_day = decisions.index[-1]
    year_before = (pd.Timestamp(last_day) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    before = decisions[decisions.index <= year_before]
    policy_change = None
    if len(before):
        policy_change = {
            "value": decisions.iloc[-1] - before.iloc[-1],
            "unit": "pp",
            "label": f"vs {s.month_name(year_before[:7])}",
        }
    growth = data["wdi_gdp_growth"]
    forecast = weo(data, "imf_weo_gdp_growth", vintage, "gdp_growth_pct", after=growth.index[-1])
    gdp_detail = None
    if forecast["years"]:
        gdp_detail = {
            "value": forecast["gdp_growth_pct"][0],
            "unit": "%",
            "label": f"IMF {forecast['years'][0]} forecast",
        }
    uv_last = coal_uv.get(volume.index[-1])
    return [
        s.tile(
            "fx",
            "MNT per US dollar, monthly average",
            fx,
            "MNT per USD",
            "derived",
            fx_status,
            s.pct_change(fx),
        ),
        s.tile(
            "cpi",
            "Consumer prices, year on year",
            cpi_yoy,
            "%",
            "nso",
            status("nso", fallback=True),
            s.pp_change(cpi_yoy),
        ),
        s.tile(
            "policy_rate",
            "Policy rate",
            policy,
            "%",
            "bom",
            status("bom"),
            policy_change,
            value=decisions.iloc[-1],
            period=last_day,
        ),
        s.tile(
            "copper",
            "Copper, LME",
            copper,
            "USD per tonne",
            "pinksheet",
            status("pinksheet"),
            s.pct_change(copper),
        ),
        s.tile(
            "coal",
            "Coal exports",
            volume,
            "million tonnes",
            "nso",
            status("nso"),
            s.pct_change(volume),
            detail=None
            if uv_last is None
            else {"value": uv_last, "unit": "USD per tonne", "label": "unit value"},
        ),
        s.tile(
            "gdp",
            "Real GDP growth",
            growth,
            "%",
            "wdi",
            status("wdi"),
            None,
            detail=gdp_detail,
        ),
    ]


# -- the data page -------------------------------------------------------------------------
DERIVED_LABELS = {
    "derived_usdmnt_monthly_avg": (
        "MNT per US dollar, monthly average (consensus of BoM, NSO and IMF)",
        "MNT per USD",
    ),
    "derived_cpi_mom": ("CPI, national, month on month (newest NSO base)", "percent"),
    "derived_cpi_yoy": ("CPI, national, year on year (newest NSO base)", "percent"),
    "derived_usd_broad_index": (
        "Broad US dollar index, TWEXBMTH spliced to TWEXBGSMTH",
        "index, January 2006 = 100",
    ),
    "derived_cnyusd_monthly_avg": ("CNY per US dollar, monthly average", "CNY per USD"),
    "derived_coal_unit_value_usd_t": ("Coal exports, value per tonne", "USD per tonne"),
    "derived_mxpi_pct": ("Mongolia's export-price index, change", "percent (100 dlog)"),
    **{
        f"derived_mxpi_weight_{g}": (f"Export-price index weight: {g.replace('_', ' ')}", "share")
        for g in transform.MXPI_GOODS
    },
}
STATIC = {
    "static/fred_twexbmth": (
        "fred",
        "Broad US dollar index, TWEXBMTH (discontinued; static seed)",
        "index, January 1997 = 100",
        True,
    ),
    **{
        sid: (
            "comtrade",
            f"Exports of {g.replace('_', ' ')}, 1996-2007 (static seed)",
            "million USD",
            False,
        )
        for g, sid in transform.COMTRADE.items()
    },
}
EXTRA_SOURCES = (
    {
        "id": "comtrade",
        "publisher": "UN Comtrade",
        "name": "Mongolia's exports by HS code, 1996-2007 (a static seed, never fetched)",
        "method": "GET",
        "url": "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
        "body": None,
        "frequency": "frozen",
        "license": "UN Comtrade terms of use",
        "redistribute": False,
    },
    {
        "id": "derived",
        "publisher": "tugrik",
        "name": "Series this project derives from the sources above",
        "method": None,
        "url": "https://github.com/ZorigoKH/tugrik",
        "body": None,
        "frequency": "with each build",
        "license": "attribute the underlying sources",
        "redistribute": True,
    },
)


def csv_name(sid: str) -> str:
    return sid.removeprefix("static/") + ".csv"


def sources_page(
    data: Mapping[str, pd.Series], derived: Mapping[str, pd.Series], states: Mapping, today: date
) -> tuple[list[dict], dict[str, bytes]]:
    """``sources.json`` and the CSV downloads (``{file name: bytes}``)."""
    csvs: dict[str, bytes] = {}
    entries = []

    def row(sid: str, label: str, units: str, s_: pd.Series, state: str, share: bool) -> dict:
        if share:
            csvs[csv_name(sid)] = to_csv(s_)
        return {
            "id": sid.removeprefix("static/"),
            "label": label,
            "units": units,
            "first": s_.index[0] if len(s_) else None,
            "last": s_.index[-1] if len(s_) else None,
            "status": state,
            "csv": f"csv/{csv_name(sid)}" if share else None,
        }

    for src_id in SOURCE_IDS:
        src = SOURCES[src_id]
        rows = []
        for sid, spec in SERIES.items():
            if spec.source != src_id or sid not in data:
                continue
            old = series_stale(sid, data, today) and src_id != "imf_datamapper"
            state = "stale" if states[src_id] == "stale" or old else "ok"
            rows.append(row(sid, spec.label, spec.units, data[sid], state, spec.redistribute))
        rows += [
            row(sid, label, units, data[sid], "ok", share)
            for sid, (owner, label, units, share) in STATIC.items()
            if owner == src_id and sid in data
        ]
        entries.append(
            {
                "id": src_id,
                "publisher": src.publisher,
                "name": src.name,
                "method": src.method,
                "url": src.url,
                "body": None,
                "frequency": src.frequency,
                "license": src.license,
                "redistribute": all(
                    SERIES[r["id"]].redistribute for r in rows if r["id"] in SERIES
                ),
                "series": rows,
            }
        )
    for extra in EXTRA_SOURCES:
        if extra["id"] == "derived":
            rows = [
                row(sid, *DERIVED_LABELS[sid], derived[sid], "ok", True) for sid in sorted(derived)
            ]
        else:
            rows = [
                row(sid, label, units, data[sid], "ok", share)
                for sid, (owner, label, units, share) in STATIC.items()
                if owner == extra["id"] and sid in data
            ]
        entries.append({**extra, "series": rows})
    return s.clean(entries), csvs


# -- meta ----------------------------------------------------------------------------------
REFERENCE = (
    # (id, label, page, reference value from the 2026-09 trial, path to the current value)
    (
        "copper_h12",
        "copper, 12-month sum, 2001 to now",
        "copper",
        -0.226,
        ("samples", "full", "copper", 12, "est"),
    ),
    (
        "copper_h12_se",
        "its standard error",
        "copper",
        0.059,
        ("samples", "full", "copper", 12, "se"),
    ),
    (
        "copper_h3_post2017",
        "copper, months 0-3, 2017 to now",
        "copper",
        -0.024,
        ("samples", "post2017", "copper", 3, "est"),
    ),
    (
        "passthrough_h12",
        "pass-through at 12 months (B3)",
        "prices",
        0.130,
        ("specs", "preferred", "cum", 12, "est"),
    ),
    (
        "passthrough_long_run",
        "pass-through, long run (B3)",
        "prices",
        0.215,
        ("specs", "preferred", "long_run", "est"),
    ),
    (
        "growth_mxpi_l1",
        "growth on export prices a year earlier (C2)",
        "growth",
        0.085,
        ("fit", "mxpi_l1", "est"),
    ),
    (
        "growth_sum",
        "growth on export prices, both years (C2)",
        "growth",
        0.115,
        ("fit", "sum", "est"),
    ),
    ("coal_2021_mt", "coal exports in 2021, Mt", "coal", 16.1, ("annual", "2021", "volume_mt")),
    (
        "coal_2021_vs_2019",
        "coal exports in 2021, % of 2019",
        "coal",
        44.0,
        ("annual", "2021", "volume_vs_2019_pct"),
    ),
)


def lookup(page: Any, path: tuple) -> Any:
    """Follow a path of keys, list positions and ids (``"full"`` finds the item with that
    ``id``, ``"2021"`` the one with that ``year``) into a page; None if it is not there."""
    for key in path:
        if isinstance(page, list) and isinstance(key, str):
            page = next((x for x in page if key in (x.get("id"), x.get("year"))), None)
        elif isinstance(page, list):
            page = page[key] if key < len(page) else None
        elif isinstance(page, dict):
            page = page.get(key)
        if page is None:
            return None
    return page


def meta(
    data: Mapping[str, pd.Series],
    status: Mapping,
    states: Mapping[str, str],
    inputs: Mapping[str, pd.Series],
    out: Mapping[str, Any],
) -> dict[str, Any]:
    sources = []
    for src in SOURCE_IDS:
        entry = status["sources"].get(src, {})
        ids = [sid for sid, spec in SERIES.items() if spec.source == src and sid in data]
        last = max((data[sid].index[-1] for sid in ids), default=None)
        sources.append(
            {
                "id": src,
                "status": states[src],
                "last_obs": entry.get("last_obs") or last,
                "last_changed": entry.get("last_changed"),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": None,
        "through": {
            "fx": inputs[models.FX].index[-1],
            "cpi": inputs[models.CPI_MOM].index[-1],
            "policy_rate": data["bom_policy_rate_decisions"].index[-1],
            "commodities": inputs[models.COPPER].index[-1],
            "trade": inputs[models.COAL_KT].index[-1],
            "gdp": inputs[models.GROWTH].index[-1],
            "weo_vintage": weo_vintage(status),
        },
        "sources": sources,
        "stale": sorted(src for src, state in states.items() if state != "ok"),
        "revisions": {
            src: int(status["sources"].get(src, {}).get("revisions", 0)) for src in SOURCE_IDS
        },
        "reference": [
            {
                "id": ref_id,
                "label": label,
                "page": page,
                "reference": value,
                "current": s.num(lookup(out[page], path)),
            }
            for ref_id, label, page, value, path in REFERENCE
        ],
        "versions": {"pipeline": __version__, "sandwich": sandwich.__version__},
    }


# -- writing -------------------------------------------------------------------------------
def to_json(obj: Any) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def published(out: Path, csv_dir: Path) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """The data files now in place: (JSON by name, CSV by name)."""
    pages_ = {f"{p}.json": (out / f"{p}.json") for p in (*PAGES, "meta")}
    return (
        {k: p.read_bytes() for k, p in pages_.items() if p.is_file()},
        {p.name: p.read_bytes() for p in sorted(csv_dir.glob("*.csv"))},
    )


def _anchor(path: Path) -> Path:
    """The nearest existing directory at or above ``path``."""
    while not path.is_dir():
        path = path.parent
    return path


def write_atomically(
    out: Path, csv_dir: Path, files: Mapping[str, bytes], csvs: Mapping[str, bytes]
) -> list[str]:
    """Stage every file in a temporary directory, validate the JSON, then move the files
    that changed into place: the CSV files (and remove those no longer published), the
    pages, then ``meta.json``. Returns what changed. Nothing is created outside the
    temporary directory until the files have passed validation."""
    stage = Path(tempfile.mkdtemp(prefix=".tugrik-build-", dir=_anchor(out.parent)))
    try:
        (stage / "data").mkdir()
        (stage / "csv").mkdir()
        for name, content in files.items():
            (stage / "data" / name).write_bytes(content)
        for name, content in csvs.items():
            (stage / "csv" / name).write_bytes(content)
        errors = validate(stage / "data")
        if errors:
            raise BuildError("the new data failed validation:\n  " + "\n  ".join(errors))
        out.mkdir(parents=True, exist_ok=True)
        csv_dir.mkdir(parents=True, exist_ok=True)
        changed = []

        def replace(source: Path, target: Path) -> None:
            if target.is_file() and target.read_bytes() == source.read_bytes():
                return
            os.replace(source, target)
            changed.append(str(target))

        for name in sorted(csvs):
            replace(stage / "csv" / name, csv_dir / name)
        for path in sorted(csv_dir.glob("*.csv")):
            if path.name not in csvs:
                path.unlink()
                changed.append(f"{path} (removed)")
        for name in sorted(n for n in files if n != "meta.json"):
            replace(stage / "data" / name, out / name)
        replace(stage / "data" / "meta.json", out / "meta.json")
        return changed
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def save_inputs(inputs: Mapping[str, pd.Series], directory: Path) -> None:
    """Write the model inputs to ``directory`` as ``<id>.csv`` files (the store's format)."""
    directory.mkdir(parents=True, exist_ok=True)
    for sid, s_ in sorted(inputs.items()):
        (directory / f"{sid}.csv").write_bytes(to_csv(s_))


def read_inputs(directory: Path) -> dict[str, pd.Series]:
    """Model inputs saved by :func:`save_inputs`."""
    return {p.stem: read_series(p) for p in sorted(Path(directory).glob("*.csv"))}


# -- the build -----------------------------------------------------------------------------
def build(
    store: str | os.PathLike,
    out: str | os.PathLike,
    csv_dir: str | os.PathLike,
    *,
    today: date | None = None,
    inputs_dir: str | os.PathLike | None = None,
    log: Log = print,
) -> dict[str, Any]:
    """Build the site's data from ``store`` into ``out`` and ``csv_dir``; return meta.json.

    Raises :class:`BuildError`, having written nothing, when the store lacks what the
    models need, when the consensus exchange rate strays from the BoM daily rate
    (:func:`check_fx_consensus`) or when the output fails validation.
    """
    store, out, csv_dir = Path(store), Path(out), Path(csv_dir)
    today = today or date.today()
    data, status = read_store(store)
    states = health(data, status, today)
    inputs, out_pages, derived = pages(data, status, states)
    out_pages["sources"], csvs = sources_page(data, derived, states, today)
    info = meta(data, status, states, inputs, out_pages)
    files = {f"{name}.json": to_json(out_pages[name]) for name in PAGES}

    # generated_at moves only when something else changed: try the previous date first
    try:
        before = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        before = {}
    info["generated_at"] = before.get("generated_at") if isinstance(before, dict) else None
    files["meta.json"] = to_json(info)
    if info["generated_at"] is None or (files, csvs) != published(out, csv_dir):
        info["generated_at"] = today.isoformat()
        files["meta.json"] = to_json(info)

    changed = write_atomically(out, csv_dir, files, csvs)
    if inputs_dir is not None:
        save_inputs(inputs, Path(inputs_dir))
    stale = ", ".join(info["stale"]) or "none"
    log(
        f"built through {info['through']['fx']} (stale: {stale}): "
        + (f"{len(changed)} file(s) changed" if changed else "no changes")
    )
    for name in ("copper", "coal", "prices", "growth"):
        for key in sorted(k for k in out_pages[name] if k.startswith("takeaway")):
            log(f"  {name}.{key}: {out_pages[name][key]}")
    return info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.build",
        description="Build the site's JSON and CSV downloads from the store (offline).",
    )
    parser.add_argument("--store", required=True, help="the store directory, e.g. data")
    parser.add_argument("--out", required=True, help="the JSON directory, e.g. web/data")
    parser.add_argument("--csv", required=True, help="the CSV directory, e.g. web/public/csv")
    parser.add_argument(
        "--today", metavar="YYYY-MM-DD", help="judge staleness on this date (default: today)"
    )
    parser.add_argument(
        "--save-inputs", metavar="DIR", help="also write the model inputs to DIR as CSV files"
    )
    args = parser.parse_args(argv)
    try:
        today = date.fromisoformat(args.today) if args.today else None
    except ValueError:
        parser.error(f"--today {args.today!r} is not YYYY-MM-DD")
    try:
        build(args.store, args.out, args.csv, today=today, inputs_dir=args.save_inputs)
    except BuildError as exc:
        print(f"pipeline.build: aborted, nothing written: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
