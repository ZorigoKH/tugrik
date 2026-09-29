"""The frozen regressions: helpers, then one function per specification.

Every regression is ``sandwich.OLS(y, add_constant(X)).fit(cov_type="HAC", maxlags=L)``:
ordinary least squares with Newey-West (Bartlett kernel) standard errors, L =
floor(4 (T/100)^(2/9)) lags (:func:`nw_lags`), except the overlapping 12-month changes of
:func:`fx_fit12`, which use L = 12 because they are MA(11) by construction. Inference uses
t with n - k degrees of freedom. Every change is 100 dlog, so a coefficient on a price change
is an elasticity. A sum of lag coefficients is tested as a linear combination with the HAC
covariance (:func:`lincom`).

The list of specifications is frozen: the build never scans lags, leads or samples, and a
change here is a methods change, recorded with its date on the site's method page.

* :func:`copper_dl12` (trial A11): the tugrik on copper and coal prices, lags 0-12.
* :func:`fx_fit12` (A9): the 12-month change of the tugrik on prices six months earlier.
* :func:`passthrough_dl` (B1) and :func:`passthrough_pref` (B3, with B4-B6): CPI on the
  tugrik, lags 0-12.
* :func:`growth` (C2, C9): real GDP growth on the export-price index and its lag.
* :func:`coal_decomp` (D1): coal export value = volume x unit value (arithmetic).

Each takes the model inputs, a mapping of series ids to series as
:func:`pipeline.transform.model_inputs` builds them, and returns plain dicts of
:class:`Est` values and :class:`Fit` objects; :mod:`pipeline.summarize` turns those into
the site's JSON.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sandwich import OLS, RegressionResults, add_constant
from scipy import stats

from . import transform

HORIZON = 12
OVERLAP_LAGS = 12  # HAC lags for overlapping 12-month changes

# model input ids (the files of tests/fixtures/store_2026-09)
FX = "derived_usdmnt_monthly_avg"
CPI_MOM = "derived_cpi_mom"
USD = "derived_usd_broad_index"
CNY = "derived_cnyusd_monthly_avg"
COPPER = "pinksheet_copper"
COAL = "pinksheet_coal_australian"
BRENT = "pinksheet_brent"
GROWTH = "wdi_gdp_growth"
COAL_KUSD = "nso_export_coal_kusd"
COAL_KT = "nso_export_coal_kt"
PRICES = {
    "coal": COAL,
    "copper": COPPER,
    "gold": "pinksheet_gold",
    "iron_ore": "pinksheet_iron_ore",
    "oil": BRENT,
    "zinc": "pinksheet_zinc",
}
WEIGHTS = {good: f"derived_mxpi_weight_{good}" for good in transform.MXPI_GOODS}

Inputs = Mapping[str, pd.Series]


# -- helpers -------------------------------------------------------------------------------
@dataclass(frozen=True)
class Est:
    """An estimate with its HAC standard error, t, two-sided p and 95% t-based interval."""

    est: float
    se: float
    t: float
    p: float
    lo: float
    hi: float


@dataclass(frozen=True)
class Fit:
    """A fitted regression and the sample it used."""

    res: RegressionResults
    periods: pd.PeriodIndex  # the observations used, in order
    maxlags: int

    @property
    def nobs(self) -> int:
        return int(self.res.nobs)

    @property
    def start(self) -> str:
        return str(self.periods[0])

    @property
    def end(self) -> str:
        return str(self.periods[-1])

    @property
    def r2(self) -> float:
        return float(self.res.r2)


def nw_lags(nobs: int) -> int:
    """The Newey-West rule of thumb, floor(4 (T/100)^(2/9)): 308 -> 5, 116 -> 4, 29 -> 3."""
    return int(math.floor(4 * (nobs / 100.0) ** (2.0 / 9.0)))


def monthly(s: pd.Series) -> pd.Series:
    """A stored monthly series on a regular monthly PeriodIndex (gaps become NaN), so that
    shifting by k positions is shifting by k months."""
    s = s.copy()
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.reindex(pd.period_range(s.index[0], s.index[-1], freq="M"))


def annual(s: pd.Series) -> pd.Series:
    """A stored annual series on a regular yearly PeriodIndex (gaps become NaN)."""
    s = s.copy()
    s.index = pd.PeriodIndex(s.index, freq="Y")
    return s.reindex(pd.period_range(s.index[0], s.index[-1], freq="Y"))


def dlog(s: pd.Series, k: int = 1) -> pd.Series:
    """100 x the k-period log change."""
    return 100 * np.log(s).diff(k)


def lags(s: pd.Series, name: str, lo: int, hi: int) -> pd.DataFrame:
    """Columns ``{name}_L{j}`` holding ``s`` lagged j periods, for j = lo..hi."""
    return pd.concat({f"{name}_L{j}": s.shift(j) for j in range(lo, hi + 1)}, axis=1)


def names(prefix: str, lo: int, hi: int) -> list[str]:
    return [f"{prefix}_L{j}" for j in range(lo, hi + 1)]


def month_dummies(index: pd.PeriodIndex) -> pd.DataFrame:
    """Eleven calendar-month dummies ``m_2`` .. ``m_12`` (January is the base)."""
    return pd.DataFrame(
        {f"m_{m}": (index.month == m).astype(float) for m in range(2, 13)}, index=index
    )


def drop(s: pd.Series, windows: Sequence[tuple[str, str]]) -> pd.Series:
    """``s`` with the observations in each ``(first, last)`` window set to NaN."""
    s = s.copy()
    for first, last in windows:
        s.loc[first:last] = np.nan
    return s


def dl_fit(
    y: pd.Series,
    x: pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
    maxlags: int | None = None,
) -> Fit:
    """OLS of ``y`` on a constant and the regressors ``x`` with HAC standard errors.

    Only the periods from ``start`` to ``end`` where ``y`` and every column of ``x`` are
    present are used. ``maxlags`` defaults to :func:`nw_lags` of the sample size.
    """
    data = pd.concat([y.rename("y"), x], axis=1).loc[start:end].dropna()
    if len(data) <= x.shape[1] + 1:
        raise ValueError(f"only {len(data)} observations for {x.shape[1] + 1} coefficients")
    lags_ = nw_lags(len(data)) if maxlags is None else maxlags
    res = OLS(data["y"], add_constant(data.drop(columns="y"))).fit(cov_type="HAC", maxlags=lags_)
    return Fit(res, data.index, lags_)


def _est(value: float, se: float, df: int) -> Est:
    t = value / se
    p = float(2 * stats.t.sf(abs(t), df))
    half = float(stats.t.ppf(0.975, df)) * se
    return Est(float(value), float(se), float(t), p, float(value - half), float(value + half))


def lincom(fit: Fit, weights: Mapping[str, float]) -> Est:
    """The linear combination sum_i w_i beta_i, with SE sqrt(c' V c) from the HAC covariance."""
    res = fit.res
    c = np.zeros(len(res.names))
    for name, w in weights.items():
        c[res.names.index(name)] = w
    return _est(float(c @ res.params), float(np.sqrt(c @ res.cov @ c)), res.df_inference)


def coef(fit: Fit, name: str) -> Est:
    """One coefficient as an :class:`Est`."""
    return lincom(fit, {name: 1.0})


def cumulative(fit: Fit, prefix: str, horizon: int = HORIZON) -> list[Est]:
    """Sums of the lag coefficients ``{prefix}_L0`` .. ``{prefix}_Lh`` for h = 0..horizon."""
    return [lincom(fit, dict.fromkeys(names(prefix, 0, h), 1.0)) for h in range(horizon + 1)]


def long_run(fit: Fit, num: Sequence[str], den: Sequence[str]) -> Est:
    """(sum of the ``num`` coefficients) / (1 - sum of the ``den`` coefficients), with its
    standard error by the delta method: the long-run effect in a model with lags of y."""
    res = fit.res
    b, v = res.params, res.cov
    i_num = [res.names.index(n) for n in num]
    i_den = [res.names.index(n) for n in den]
    s, r = b[i_num].sum(), b[i_den].sum()
    grad = np.zeros(len(b))
    grad[i_num] = 1 / (1 - r)
    grad[i_den] = s / (1 - r) ** 2
    return _est(float(s / (1 - r)), float(np.sqrt(grad @ v @ grad)), res.df_inference)


# -- copper_dl12 (A11) ---------------------------------------------------------------------
@dataclass(frozen=True)
class Sample:
    id: str
    label: str
    start: str
    end: str | None
    excluded: tuple[tuple[str, str], ...] = ()


GFC = ("2008-09", "2009-06")
BORDER = ("2020-02", "2022-12")

COPPER_SAMPLES = (
    Sample("full", "2001 to now", "2001-01", None),
    Sample("ex_gfc", "2001 to now, without Sep 2008 to Jun 2009", "2001-01", None, (GFC,)),
    Sample("pre2017", "2001 to 2016", "2001-01", "2016-12"),
    Sample("post2017", "2017 to now", "2017-01", None),
    Sample(
        "post2017_ex_border",
        "2017 to now, without the border closures (Feb 2020 to Dec 2022)",
        "2017-01",
        None,
        (BORDER,),
    ),
)


def _fx_inputs(inputs: Inputs) -> dict[str, pd.Series]:
    return {
        "fx": monthly(inputs[FX]),
        "copper": monthly(inputs[COPPER]),
        "coal": monthly(inputs[COAL]),
        "usd": monthly(inputs[USD]),
        "cny": monthly(inputs[CNY]),
    }


def copper_dl12(inputs: Inputs) -> dict[str, dict]:
    """A11: 100 dlog MNT/USD on copper and Australian coal price changes at lags 0-12, the
    broad dollar and CNY/USD (lag 0), in five samples.

    Returns ``{sample id: {"sample", "fit", "copper": [Est x 13], "coal_h12", "usd", "cny"}}``
    where ``copper[h]`` is the sum of the copper coefficients at lags 0..h.
    """
    s = _fx_inputs(inputs)
    x = pd.concat(
        [
            lags(dlog(s["copper"]), "cu", 0, HORIZON),
            lags(dlog(s["coal"]), "coal", 0, HORIZON),
            dlog(s["usd"]).rename("usd_L0"),
            dlog(s["cny"]).rename("cny_L0"),
        ],
        axis=1,
    )
    y = dlog(s["fx"])
    out = {}
    for sample in COPPER_SAMPLES:
        fit = dl_fit(drop(y, sample.excluded), x, sample.start, sample.end)
        out[sample.id] = {
            "sample": sample,
            "fit": fit,
            "copper": cumulative(fit, "cu"),
            "coal_h12": lincom(fit, dict.fromkeys(names("coal", 0, HORIZON), 1.0)),
            "usd": coef(fit, "usd_L0"),
            "cny": coef(fit, "cny_L0"),
        }
    return out


# -- fx_fit12 (A9) -------------------------------------------------------------------------
FIT12_START = "2002-12"
FIT12_LEAD = 6


def fx_fit12(inputs: Inputs) -> dict:
    """A9: the 12-month log change of MNT/USD on the 12-month changes of copper and coal six
    months earlier and of the broad dollar in the same months, from 2002-12, HAC lags 12.

    Returns ``{"fit", "actual", "fitted", "copper_t6", "coal_t6", "usd"}``; ``actual`` and
    ``fitted`` are series over the sample.
    """
    s = _fx_inputs(inputs)
    x = pd.concat(
        [
            dlog(s["copper"], 12).shift(FIT12_LEAD).rename("cu12"),
            dlog(s["coal"], 12).shift(FIT12_LEAD).rename("coal12"),
            dlog(s["usd"], 12).rename("usd12"),
        ],
        axis=1,
    )
    fit = dl_fit(dlog(s["fx"], 12), x, FIT12_START, maxlags=OVERLAP_LAGS)
    return {
        "fit": fit,
        "actual": pd.Series(np.asarray(fit.res.fitted) + np.asarray(fit.res.resid), fit.periods),
        "fitted": pd.Series(np.asarray(fit.res.fitted), fit.periods),
        "copper_t6": coef(fit, "cu12"),
        "coal_t6": coef(fit, "coal12"),
        "usd": coef(fit, "usd12"),
    }


# -- passthrough (B1, B3) ------------------------------------------------------------------
PASSTHROUGH_START = "2002-01"
PASSTHROUGH_SUBSAMPLES = (
    Sample(
        "ex_gfc",
        "2002 to now, without Sep 2008 to Dec 2009",
        "2002-01",
        None,
        (("2008-09", "2009-12"),),
    ),
    Sample("early", "2002 to 2013", "2002-01", "2013-12"),
    Sample("late", "2014 to now", "2014-01", None),
)
DEPRECIATION = names("de", 0, HORIZON)
CPI_LAGS = ["pi_L1", "pi_L2"]


def _passthrough_data(inputs: Inputs) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """CPI m/m and the regressors of B1 and of B3."""
    pi = monthly(inputs[CPI_MOM])
    fx = monthly(inputs[FX])
    brent, copper = monthly(inputs[BRENT]), monthly(inputs[COPPER])
    dl = pd.concat([lags(dlog(fx), "de", 0, HORIZON), month_dummies(pi.index)], axis=1)
    preferred = pd.concat(
        [
            dl,
            lags(pi, "pi", 1, 2),
            lags(dlog(brent), "oil", 0, 3),
            lags(dlog(copper), "cu", 0, HORIZON),
        ],
        axis=1,
    )
    return pi, dl, preferred


WHOLE = Sample("full", "2002 to now", PASSTHROUGH_START, None)


def passthrough_dl(inputs: Inputs) -> dict:
    """B1: NSO CPI m/m on the depreciation 100 dlog MNT/USD at lags 0-12 and 11
    calendar-month dummies, from 2002-01.

    Returns ``{"sample", "fit", "cum": [Est x 13], "long_run": None, "oil_sum": None,
    "copper_sum": None, "rho": None}``, where ``cum[h]`` sums the depreciation lags 0..h.
    """
    pi, dl, _ = _passthrough_data(inputs)
    fit = dl_fit(pi, dl, WHOLE.start, WHOLE.end)
    return {
        "sample": WHOLE,
        "fit": fit,
        "cum": cumulative(fit, "de"),
        "long_run": None,
        "oil_sum": None,
        "copper_sum": None,
        "rho": None,
    }


def passthrough_pref(inputs: Inputs) -> dict:
    """B3, the preferred pass-through: B1 plus CPI m/m at lags 1-2, Brent (USD) changes at
    lags 0-3 and copper changes at lags 0-12, which stand in for the commodity-driven demand
    cycle. The long run is sum(beta) / (1 - rho1 - rho2) by the delta method.

    Returns ``{"full": spec, "subsamples": [spec x 3]}``: the whole sample, then without Sep
    2008 to Dec 2009 (B4), 2002-2013 (B5) and 2014 on (B6). Each spec is ``{"sample", "fit",
    "cum": [Est x 13], "long_run", "oil_sum", "copper_sum", "rho": [rho1, rho2]}``.
    """
    pi, _, preferred = _passthrough_data(inputs)

    def spec(sample: Sample) -> dict:
        fit = dl_fit(drop(pi, sample.excluded), preferred, sample.start, sample.end)
        i1, i2 = (fit.res.names.index(n) for n in CPI_LAGS)
        return {
            "sample": sample,
            "fit": fit,
            "cum": cumulative(fit, "de"),
            "long_run": long_run(fit, DEPRECIATION, CPI_LAGS),
            "oil_sum": lincom(fit, dict.fromkeys(names("oil", 0, 3), 1.0)),
            "copper_sum": lincom(fit, dict.fromkeys(names("cu", 0, HORIZON), 1.0)),
            "rho": [float(fit.res.params[i1]), float(fit.res.params[i2])],
        }

    return {"full": spec(WHOLE), "subsamples": [spec(s) for s in PASSTHROUGH_SUBSAMPLES]}


# -- growth (C2, C9) -----------------------------------------------------------------------
GROWTH_START = "1997"
GROWTH_DROPS = (
    ("2009",),
    ("2020",),
    ("2009", "2020"),
    ("2011",),
    ("2021", "2022", "2023"),
)


def mxpi_inputs(inputs: Inputs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Annual mean prices and export shares (years x goods) from the model inputs."""
    prices = pd.DataFrame({g: transform.annual_mean(inputs[sid]) for g, sid in PRICES.items()})
    weights = pd.DataFrame({g: inputs[sid] for g, sid in WEIGHTS.items()})
    return prices, weights


def growth(inputs: Inputs) -> dict:
    """C2: WDI real GDP growth on mxpi(t) and mxpi(t-1), from 1997.

    Returns ``{"fit", "const", "mxpi", "mxpi_l1", "sum", "p_l1_nonrobust", "p_l1_hc1",
    "robustness": [{"drop", "fit", "mxpi_l1"}], "data", "weights"}``, where ``data`` holds
    growth, mxpi and its lag by year and ``weights`` the export shares. With about 29 years,
    HAC standard
    errors over-reject, so the p-values of plain OLS and of HC1 are reported too. The C9
    variants drop 2009, 2020, both, 2011, or 2021-2023.
    """
    prices, weights = mxpi_inputs(inputs)
    index = annual(transform.mxpi(prices, weights))
    g = annual(inputs[GROWTH])
    data = pd.concat(
        [g.rename("growth"), index.rename("mxpi"), index.shift(1).rename("mxpi_L1")], axis=1
    )
    x = data[["mxpi", "mxpi_L1"]]
    fit = dl_fit(data["growth"], x, GROWTH_START)
    used = data.loc[fit.periods]
    plain = OLS(used["growth"], add_constant(used[["mxpi", "mxpi_L1"]]))
    i = fit.res.names.index("mxpi_L1")
    robustness = []
    for years in GROWTH_DROPS:
        y = drop(data["growth"], [(yr, yr) for yr in years])
        variant = dl_fit(y, x, GROWTH_START)
        robustness.append(
            {"drop": list(years), "fit": variant, "mxpi_l1": coef(variant, "mxpi_L1")}
        )
    return {
        "fit": fit,
        "const": coef(fit, "const"),
        "mxpi": coef(fit, "mxpi"),
        "mxpi_l1": coef(fit, "mxpi_L1"),
        "sum": lincom(fit, {"mxpi": 1.0, "mxpi_L1": 1.0}),
        "p_l1_nonrobust": float(plain.fit().pvalues[i]),
        "p_l1_hc1": float(plain.fit(cov_type="HC1").pvalues[i]),
        "robustness": robustness,
        "data": data,
        "weights": weights,
    }


# -- coal_decomp (D1) ----------------------------------------------------------------------
COAL_BASE_YEAR = "2019"


def coal_decomp(inputs: Inputs) -> pd.DataFrame:
    """D1: Mongolia's coal exports by calendar year, from NSO's monthly flows.

    Columns: ``months`` (how many), ``through`` (the last month), ``value_musd``,
    ``volume_mt``, ``unit_value_usd_t`` (value / volume), ``benchmark_usd_t`` (the mean
    Australian thermal price over the same months), ``dlog_value``, ``dlog_volume`` and
    ``dlog_unit_value`` (100 dlog against the previous year; full years only, so that
    dlog value = dlog volume + dlog unit value exactly) and ``volume_vs_2019_pct`` (the
    tonnage against the same months of 2019).
    """
    value, volume = inputs[COAL_KUSD], inputs[COAL_KT]
    bench = inputs[COAL]
    rows = {}
    for year in sorted(set(value.index.str[:4])):
        months = [m for m in value.index if m.startswith(year) and m in volume.index]
        same_2019 = [f"{COAL_BASE_YEAR}{m[4:]}" for m in months]
        rows[year] = {
            "months": len(months),
            "through": months[-1],
            "value_musd": value[months].sum() / 1e3,
            "volume_mt": volume[months].sum() / 1e3,
            "benchmark_usd_t": bench.reindex(months).mean(),
            "volume_2019_same_months": volume.reindex(same_2019).sum() / 1e3,
        }
    a = pd.DataFrame.from_dict(rows, orient="index")
    a["unit_value_usd_t"] = a["value_musd"] / a["volume_mt"]
    full = a["months"] == 12
    for col, src in (
        ("dlog_value", "value_musd"),
        ("dlog_volume", "volume_mt"),
        ("dlog_unit_value", "unit_value_usd_t"),
    ):
        change = 100 * np.log(a[src]).diff()  # the NSO series have no gaps, nor the years
        a[col] = change.where(full & full.shift(1, fill_value=False))
    has_base = COAL_BASE_YEAR in a.index
    a["volume_vs_2019_pct"] = (
        100 * a["volume_mt"] / a["volume_2019_same_months"] if has_base else np.nan
    )
    return a.drop(columns="volume_2019_same_months")


# -- everything ----------------------------------------------------------------------------
def estimate(inputs: Inputs) -> dict:
    """Every frozen specification on one set of model inputs."""
    return {
        "copper": copper_dl12(inputs),
        "fit12": fx_fit12(inputs),
        "passthrough_dl": passthrough_dl(inputs),
        "passthrough_pref": passthrough_pref(inputs),
        "growth": growth(inputs),
        "coal": coal_decomp(inputs),
    }
