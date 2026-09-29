"""Pure transforms of stored series (no network, no clock, no files).

Every function takes and returns series indexed by date strings, as the store keeps them
(``YYYY-MM-DD``, ``YYYY-MM`` or ``YYYY``), sorted and without missing values.

* Exchange rates: :func:`weekday_mean` and :func:`month_end` of the BoM's daily rate, and
  :func:`fx_consensus`, one monthly average from three published ones.
* Consumer prices: :func:`newest_base`, NSO's CPI changes spliced across base years.
* Policy rate: :func:`policy_month_end`, the rate in force at the end of each month.
* Trade: :func:`ytd_to_monthly` (used when NSO's tables are parsed), :func:`unit_value`,
  :func:`annual_sum` and :func:`annual_mean`.
* Export prices: :func:`mxpi_weights` and :func:`mxpi`, Mongolia's export-price index.
* Dollar: :func:`broad_dollar`, the discontinued broad index spliced onto the current one.
* :func:`extend`, a series continued by a fallback source after it ends.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from .sources import series

# the FX consensus rule, by period (see fx_consensus)
FX_START = "1990-07"  # IMF only: the administered rate before the float
FX_BOM_FROM = "1993-01"  # the BoM's own average
FX_MEDIAN_FROM = "1994-01"  # the median of the published averages
FX_DAILY_FROM = "2001-01"  # whichever average is closest to the BoM daily weekday mean
FX_TIE_ORDER = ("nso", "imf", "bom")

DOLLAR_SPLICE = "2006-01"  # first month of the current broad dollar index
MXPI_GOODS = ("coal", "copper", "gold", "iron_ore", "oil", "zinc")
WEIGHTS_SUM = 1e-9  # how far a year's export shares may sum from 1


# -- exchange rates ------------------------------------------------------------------------
def _complete_months(daily: pd.Series, by_month: pd.Series) -> pd.Series:
    """``by_month`` without the last month unless ``daily`` reaches that month's last day."""
    last = pd.Timestamp(daily.index[-1])
    if not last.is_month_end:
        by_month = by_month[by_month.index < last.strftime("%Y-%m")]
    return by_month


def weekday_mean(daily: pd.Series) -> pd.Series:
    """Monthly means of the Monday-to-Friday observations of a daily series (``YYYY-MM``).

    The BoM publishes a rate for weekends too, but the official monthly averages match the
    weekday mean best. The last month is dropped unless the series reaches its last day,
    so a month still in progress never counts.
    """
    if daily.empty:
        return series([])
    days = pd.to_datetime(pd.Index(daily.index))
    weekdays = daily[days.weekday < 5]
    means = weekdays.groupby(weekdays.index.str[:7]).mean()
    return series(_complete_months(daily, means).items())


def month_end(daily: pd.Series) -> pd.Series:
    """The last observation of each month of a daily series (``YYYY-MM``).

    As in :func:`weekday_mean`, a month still in progress is left out.
    """
    if daily.empty:
        return series([])
    last = daily.groupby(daily.index.str[:7]).last()
    return series(_complete_months(daily, last).items())


def fx_consensus(
    averages: Mapping[str, pd.Series], daily_mean: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """One monthly average of MNT per US dollar from the three published ones.

    ``averages`` holds the monthly averages published by ``"nso"``, ``"imf"`` and ``"bom"``;
    ``daily_mean`` is the BoM daily rate's :func:`weekday_mean`. For each month:

    * from 2001: the published average closest to the daily weekday mean (ties go to NSO,
      then the IMF, then the BoM); in a month without a daily mean, the median of the
      published averages;
    * 1994-2000: the median of the published averages;
    * 1993: the BoM's average;
    * 1990-07 to 1992-12: the IMF's (the administered rate before the float).

    Each source has a few wrong months (IMF 2009-07 and 2010-04 off by about 10 MNT, 2012-01
    and 2016-10; BoM 1996-07 and end-of-month values in 2007-10; NSO 2002-04 and 2010-11);
    no rule above ever picks them. Returns the consensus and, for each month, which rule
    chose it (``"nso"``, ``"imf"``, ``"bom"`` or ``"median"``). A month that no source
    covers is left out.
    """
    months = sorted(set().union(*(s.index for s in averages.values())))
    values: list[tuple[str, float]] = []
    chosen: list[tuple[str, str]] = []
    for month in months:
        if month < FX_START:
            continue
        offered = {
            name: float(averages[name][month])
            for name in FX_TIE_ORDER
            if name in averages and month in averages[name].index
        }
        if month >= FX_MEDIAN_FROM:
            if not offered:
                continue
            if month >= FX_DAILY_FROM and month in daily_mean.index:
                reference = float(daily_mean[month])
                # min keeps the first of equal distances, so ties follow FX_TIE_ORDER
                name = min(offered, key=lambda k: abs(offered[k] - reference))
                values.append((month, offered[name]))
                chosen.append((month, name))
            else:
                values.append((month, float(np.median(list(offered.values())))))
                chosen.append((month, "median"))
            continue
        name = "bom" if month >= FX_BOM_FROM else "imf"
        if name in offered:
            values.append((month, offered[name]))
            chosen.append((month, name))
    labels = pd.Series(dict(chosen), dtype=object)
    return series(values), labels


# -- consumer prices -----------------------------------------------------------------------
def newest_base(by_base: Mapping[int, pd.Series]) -> pd.Series:
    """One series from several base years: each date from the newest base that has it."""
    spliced = series([])
    for base in sorted(by_base, reverse=True):
        spliced = spliced.combine_first(by_base[base]) if len(spliced) else by_base[base]
    return series(spliced.items())


# -- policy rate ---------------------------------------------------------------------------
def policy_month_end(decisions: pd.Series, last_month: str) -> pd.Series:
    """The policy rate in force at the end of each month, from the month of the first
    decision to ``last_month`` (``YYYY-MM``).

    ``decisions`` has one row per decision, dated the day it took effect. A month's value is
    the rate of the latest decision that took effect on or before its last day, so of two
    decisions in one month the later one counts.
    """
    if decisions.empty:
        return series([])
    first = decisions.index[0][:7]
    out = []
    for period in pd.period_range(first, last_month, freq="M"):
        month_end_day = period.to_timestamp(how="end").strftime("%Y-%m-%d")
        in_force = decisions[decisions.index <= month_end_day]
        out.append((period.strftime("%Y-%m"), float(in_force.iloc[-1])))
    return series(out)


# -- trade ---------------------------------------------------------------------------------
def ytd_to_monthly(cumulative: pd.Series) -> pd.Series:
    """Monthly flows from year-to-date totals.

    January's flow is January's total; every later month is the change in the running total.
    Raises ValueError if a year's months do not run from January without a gap, if a flow is
    negative (the running total fell), or if a year's flows do not add up to its last total.
    """
    flows: list[tuple[str, float]] = []
    for year, block in cumulative.groupby(cumulative.index.str[:4]):
        months = [int(d[5:7]) for d in block.index]
        if months != list(range(1, len(months) + 1)):
            raise ValueError(f"year-to-date {year}: months {months} do not run from January")
        previous = 0.0
        year_flows = []
        for when, total in block.items():
            flow = total - previous
            if flow < -1e-6:
                raise ValueError(f"year-to-date {when}: the total falls from {previous} to {total}")
            year_flows.append((when, max(flow, 0.0)))
            previous = total
        if abs(sum(f for _, f in year_flows) - previous) > 1e-6 * max(1.0, abs(previous)):
            raise ValueError(f"year-to-date {year}: the monthly flows do not add up to the total")
        flows.extend(year_flows)
    return series(flows)


def unit_value(value: pd.Series, volume: pd.Series) -> pd.Series:
    """Value per unit of volume, for the dates where the volume is positive.

    Thousand USD over thousand tonnes is USD per tonne.
    """
    both = pd.concat({"value": value, "volume": volume}, axis=1).dropna()
    both = both[both["volume"] > 0]
    return series((both["value"] / both["volume"]).items())


def _full_years(monthly: pd.Series) -> pd.Series:
    """The observations of the calendar years that have all 12 months."""
    years = monthly.index.str[:4]
    counts = pd.Series(years).value_counts()
    full = set(counts[counts == 12].index)
    return monthly[[y in full for y in years]]


def annual_sum(monthly: pd.Series) -> pd.Series:
    """Calendar-year totals (``YYYY``), for years with all 12 months."""
    full = _full_years(monthly)
    return series(full.groupby(full.index.str[:4]).sum().items())


def annual_mean(monthly: pd.Series) -> pd.Series:
    """Calendar-year means (``YYYY``), for years with all 12 months."""
    full = _full_years(monthly)
    return series(full.groupby(full.index.str[:4]).mean().items())


# -- export prices -------------------------------------------------------------------------
def _years(first: str, last: str) -> list[str]:
    return [str(y) for y in range(int(first), int(last) + 1)]


def mxpi_weights(
    comtrade: Mapping[str, pd.Series], nso: Mapping[str, pd.Series]
) -> tuple[pd.DataFrame, pd.Series]:
    """Each good's share of the six goods' exports, by year, and where each year's come from.

    ``comtrade`` and ``nso`` map each good of :data:`MXPI_GOODS` to annual export values
    (any one unit per source). Comtrade's years (1996-2007) come first; a good missing from
    a Comtrade year had no recorded exports and counts as zero. NSO's years (full years from
    2011) follow. The years in between are interpolated linearly, good by good, so every row
    still sums to 1 (checked: within 1e-9, or ValueError). Returns the shares (years x
    goods) and the source of each year: ``"comtrade"``, ``"interpolated"`` or ``"nso"``.
    """
    old = pd.DataFrame({g: comtrade[g] for g in MXPI_GOODS}).sort_index().fillna(0.0)
    new = pd.DataFrame({g: nso[g] for g in MXPI_GOODS}).sort_index().dropna()
    shares = pd.concat([old.div(old.sum(axis=1), axis=0), new.div(new.sum(axis=1), axis=0)])
    shares = shares[~shares.index.duplicated(keep="last")]
    years = _years(shares.index.min(), shares.index.max())
    shares = shares.reindex(years).interpolate(limit_area="inside")
    total = shares.sum(axis=1)
    off = (total - 1).abs()
    if off.isna().any() or off.max() > WEIGHTS_SUM:
        worst = off.fillna(np.inf).idxmax()
        raise ValueError(f"the export shares of {worst} sum to {total[worst]}, not 1")
    source = pd.Series(
        [
            "nso" if y in new.index else "comtrade" if y in old.index else "interpolated"
            for y in years
        ],
        index=years,
        dtype=object,
    )
    return shares, source


def mxpi(prices: pd.DataFrame, weights: pd.DataFrame) -> pd.Series:
    """Mongolia's export-price index, percent change: sum_i w_i,t-1 * 100 dlog p_i,t.

    ``prices`` holds annual mean prices (years x goods) and ``weights`` the shares from
    :func:`mxpi_weights`. Each year uses the previous year's shares; the first year of the
    shares (1996) has no previous year and uses its own, which /method discloses. A year
    needs a price change for all six goods.
    """
    goods = list(MXPI_GOODS)
    first, last = weights.index.min(), weights.index.max()
    years = _years(first, str(int(last) + 1))
    lagged = weights[goods].reindex(years).shift(1)
    lagged.loc[first] = weights.loc[first, goods]
    prices = prices[goods].reindex(_years(str(int(first) - 1), years[-1]))
    change = 100 * np.log(prices).diff()
    index = (lagged * change.reindex(years)).sum(axis=1, min_count=len(goods))
    return series(index.items())


# -- dollar --------------------------------------------------------------------------------
def broad_dollar(old: pd.Series, new: pd.Series, at: str = DOLLAR_SPLICE) -> pd.Series:
    """The broad dollar index: ``new`` from ``at`` on, ``old`` before it, rescaled by the
    ratio new/old in ``at`` so the two join without a jump (a ratio splice)."""
    if at not in old.index or at not in new.index:
        raise ValueError(f"the broad dollar splice needs both indexes in {at}")
    ratio = new[at] / old[at]
    before = old[old.index < at] * ratio
    return series([*before.items(), *new[new.index >= at].items()])


# -- fallbacks -----------------------------------------------------------------------------
def extend(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    """``primary``, continued by ``fallback``'s observations after ``primary`` ends."""
    if primary.empty:
        return fallback.copy()
    after = fallback[fallback.index > primary.index[-1]]
    return series([*primary.items(), *after.items()])


# -- the model inputs ----------------------------------------------------------------------
COMTRADE = {
    "coal": "static/comtrade_mng_exports_coal_hs2701_musd",
    "copper": "static/comtrade_mng_exports_copper_conc_hs2603_musd",
    "gold": "static/comtrade_mng_exports_gold_hs7108_musd",
    "iron_ore": "static/comtrade_mng_exports_iron_ore_hs2601_musd",
    "oil": "static/comtrade_mng_exports_crude_oil_hs2709_musd",
    "zinc": "static/comtrade_mng_exports_zinc_conc_hs2608_musd",
}
NSO_EXPORTS = {
    "coal": "nso_export_coal_kusd",
    "copper": "nso_export_copper_conc_kusd",
    "gold": "nso_export_gold_kusd",
    "iron_ore": "nso_export_iron_ore_kusd",
    "oil": "nso_export_crude_oil_kusd",
    "zinc": "nso_export_zinc_conc_kusd",
}
OLD_DOLLAR = "static/fred_twexbmth"
PASSED_THROUGH = (
    "pinksheet_copper",
    "pinksheet_coal_australian",
    "pinksheet_gold",
    "pinksheet_iron_ore",
    "pinksheet_brent",
    "pinksheet_zinc",
    "nso_export_coal_kusd",
    "nso_export_coal_kt",
    "wdi_gdp_growth",
)


def cpi(store: Mapping[str, pd.Series], kind: str) -> pd.Series:
    """NSO's national CPI, ``kind`` ``"mom"`` or ``"yoy"``, newest base first."""
    prefix = f"nso_cpi_{kind}_b"
    return newest_base({int(k[len(prefix) :]): s for k, s in store.items() if k.startswith(prefix)})


def fx_average(store: Mapping[str, pd.Series]) -> tuple[pd.Series, pd.Series]:
    """:func:`fx_consensus` of the store's three published averages and the BoM daily rate."""
    averages = {
        name: store[f"{name}_usdmnt_monthly_avg"]
        for name in FX_TIE_ORDER
        if f"{name}_usdmnt_monthly_avg" in store
    }
    daily = store.get("bom_usdmnt_daily", series([]))
    return fx_consensus(averages, weekday_mean(daily))


def model_inputs(
    store: Mapping[str, pd.Series], stale: frozenset[str] | set[str] = frozenset()
) -> dict[str, pd.Series]:
    """The series the frozen regressions read, from the store.

    ``store`` maps series ids to stored series (static seeds as ``static/<name>``) and
    ``stale`` names the sources whose data is out of date. Derived series:

    * ``derived_usdmnt_monthly_avg``: :func:`fx_average`;
    * ``derived_cpi_mom``: NSO CPI m/m, newest base first; if NSO is stale, continued by the
      IMF's CPI m/m;
    * ``derived_usd_broad_index``: :func:`broad_dollar` of TWEXBMTH and TWEXBGSMTH;
    * ``derived_cnyusd_monthly_avg``: FRED's CNY/USD; if FRED is stale, continued by the IMF's;
    * ``derived_mxpi_weight_{good}``: :func:`mxpi_weights` from Comtrade and NSO's exports.

    Pink Sheet prices, NSO's coal exports and WDI growth pass through unchanged.
    """
    inputs = {sid: store[sid] for sid in PASSED_THROUGH}
    inputs["derived_usdmnt_monthly_avg"] = fx_average(store)[0]
    cpi_mom = cpi(store, "mom")
    if "nso" in stale and "imf_cpi_mom" in store:
        cpi_mom = extend(cpi_mom, store["imf_cpi_mom"])
    inputs["derived_cpi_mom"] = cpi_mom
    inputs["derived_usd_broad_index"] = broad_dollar(
        store[OLD_DOLLAR], store["fred_usd_broad_index"]
    )
    cny = store["fred_cnyusd_monthly_avg"]
    if "fred" in stale and "imf_cnyusd_monthly_avg" in store:
        cny = extend(cny, store["imf_cnyusd_monthly_avg"])
    inputs["derived_cnyusd_monthly_avg"] = cny
    shares, _ = mxpi_weights(
        {g: store[sid] for g, sid in COMTRADE.items()},
        {g: annual_sum(store[sid]) for g, sid in NSO_EXPORTS.items()},
    )
    for good in MXPI_GOODS:
        inputs[f"derived_mxpi_weight_{good}"] = series(shares[good].items())
    return inputs
