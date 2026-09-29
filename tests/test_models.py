"""The regression helpers: the lag rule, HAC fits, linear combinations and the long run."""

import numpy as np
import pandas as pd
import pytest

from pipeline import models as m
from pipeline.sources import series


def test_nw_lags_rule_of_thumb():
    assert [m.nw_lags(t) for t in (308, 116, 29, 27)] == [5, 4, 3, 2]


def simulated(n: int = 3000, beta=(0.3, -0.2, 0.5, 0.1), rho: float = 0.6, seed: int = 1):
    """y_t = 1 + sum_j beta_j x_{t-j} + u_t, with u an AR(1) and x white noise."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    e = rng.normal(0, 1, n)
    u = np.zeros(n)
    for t in range(1, n):
        u[t] = rho * u[t - 1] + e[t]
    index = pd.period_range("1800-01", periods=n, freq="M")
    xs = pd.Series(x, index)
    y = 1.0 + sum(b * xs.shift(j) for j, b in enumerate(beta)) + pd.Series(u, index)
    return y, xs


def test_distributed_lag_recovers_the_sum_of_betas():
    beta = (0.3, -0.2, 0.5, 0.1)
    y, x = simulated(beta=beta)
    fit = m.dl_fit(y, m.lags(x, "x", 0, 3))
    assert fit.maxlags == m.nw_lags(fit.nobs)
    total = m.cumulative(fit, "x", 3)
    assert len(total) == 4
    assert total[3].est == pytest.approx(sum(beta), abs=4 * total[3].se)
    assert total[3].lo < sum(beta) < total[3].hi
    assert total[0].est == pytest.approx(beta[0], abs=4 * total[0].se)


def test_lincom_standard_error_is_sqrt_c_v_c():
    y, x = simulated(n=400)
    fit = m.dl_fit(y, m.lags(x, "x", 0, 3))
    weights = {"x_L0": 1.0, "x_L2": -2.0, "const": 0.5}
    got = m.lincom(fit, weights)
    c = np.array([weights.get(n, 0.0) for n in fit.res.names])
    assert got.est == pytest.approx(c @ fit.res.params)
    assert got.se == pytest.approx(np.sqrt(c @ fit.res.cov @ c))
    assert got.t == pytest.approx(got.est / got.se)
    assert got.lo < got.est < got.hi
    single = m.coef(fit, "x_L1")
    i = fit.res.names.index("x_L1")
    assert single.se == pytest.approx(fit.res.bse[i])
    assert single.p == pytest.approx(fit.res.pvalues[i])


def test_long_run_is_the_ratio_with_a_delta_method_se():
    y, x = simulated(n=600)
    x_lags = pd.concat([m.lags(x, "x", 0, 1), m.lags(y, "y", 1, 2)], axis=1)
    fit = m.dl_fit(y, x_lags)
    b = dict(zip(fit.res.names, fit.res.params, strict=True))
    lr = m.long_run(fit, ["x_L0", "x_L1"], ["y_L1", "y_L2"])
    assert lr.est == pytest.approx((b["x_L0"] + b["x_L1"]) / (1 - b["y_L1"] - b["y_L2"]))

    def ratio(params):
        p = dict(zip(fit.res.names, params, strict=True))
        return (p["x_L0"] + p["x_L1"]) / (1 - p["y_L1"] - p["y_L2"])

    step = 1e-6
    grad = np.array(
        [
            (ratio(fit.res.params + step * e) - ratio(fit.res.params - step * e)) / (2 * step)
            for e in np.eye(len(fit.res.params))
        ]
    )
    assert lr.se == pytest.approx(np.sqrt(grad @ fit.res.cov @ grad), rel=1e-5)


def test_dl_fit_uses_complete_rows_within_the_sample():
    y, x = simulated(n=300)
    y = m.drop(y, [("1805-01", "1805-12")])
    fit = m.dl_fit(y, m.lags(x, "x", 0, 2), start="1801-01", end="1820-12")
    assert fit.start == "1801-01" and fit.end == "1820-12"
    assert fit.nobs == 20 * 12 - 12
    assert pd.Period("1805-06", freq="M") not in fit.periods
    with pytest.raises(ValueError, match="observations"):
        m.dl_fit(y, m.lags(x, "x", 0, 2), start="1801-01", end="1801-03")


def test_hac_matches_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    y, x = simulated(n=250)
    x_lags = m.lags(x, "x", 0, 3)
    fit = m.dl_fit(y, x_lags, maxlags=12)
    data = pd.concat([y.rename("y"), x_lags], axis=1).dropna()
    ref = sm.OLS(data["y"], sm.add_constant(data.drop(columns="y"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": 12, "use_correction": False}, use_t=True
    )
    assert np.allclose(fit.res.params, ref.params, rtol=1e-10)
    assert np.allclose(fit.res.bse, ref.bse, rtol=1e-8)
    assert np.allclose(fit.res.pvalues, ref.pvalues, rtol=1e-6)


def test_monthly_fills_gaps_so_shifts_are_months():
    s = series([("2020-01", 1.0), ("2020-02", 2.0), ("2020-04", 4.0)])
    out = m.monthly(s)
    assert list(out.index.astype(str)) == ["2020-01", "2020-02", "2020-03", "2020-04"]
    assert np.isnan(out.shift(1).iloc[-1])  # March is missing, so April's lag is too
    assert m.lags(out, "s", 1, 1)["s_L1"].tolist()[1] == 1.0


def test_month_dummies_leave_january_out():
    index = pd.period_range("2020-01", "2021-12", freq="M")
    d = m.month_dummies(index)
    assert list(d.columns) == [f"m_{k}" for k in range(2, 13)]
    assert d.loc["2020-01"].sum() == 0 and d.loc["2021-07", "m_7"] == 1.0
    assert (d.sum(axis=1) <= 1).all()


def test_coal_decomposition_is_exact_and_full_years_only():
    months = [p.strftime("%Y-%m") for p in pd.period_range("2018-01", "2021-03", freq="M")]
    rng = np.random.default_rng(3)
    volume = series(zip(months, rng.uniform(1000, 3000, len(months)), strict=True))
    value = series(zip(months, volume.to_numpy() * rng.uniform(50, 200, len(months)), strict=True))
    bench = series(zip(months, rng.uniform(60, 120, len(months)), strict=True))
    a = m.coal_decomp({m.COAL_KUSD: value, m.COAL_KT: volume, m.COAL: bench})
    assert list(a.index) == ["2018", "2019", "2020", "2021"]
    assert a.loc["2018", ["dlog_value", "dlog_volume", "dlog_unit_value"]].isna().all()
    assert a.loc["2021", ["dlog_value", "dlog_volume", "dlog_unit_value"]].isna().all()
    for year in ("2019", "2020"):
        r = a.loc[year]
        assert r["dlog_value"] == pytest.approx(r["dlog_volume"] + r["dlog_unit_value"], abs=1e-12)
    assert a.loc["2019", "volume_vs_2019_pct"] == pytest.approx(100.0)
    # a part year is compared with the same months of 2019
    q1 = volume.loc["2021-01":"2021-03"].sum() / volume.loc["2019-01":"2019-03"].sum()
    assert a.loc["2021", "volume_vs_2019_pct"] == pytest.approx(100 * q1)
    assert a.loc["2021", "benchmark_usd_t"] == pytest.approx(bench.loc["2021-01":].mean())
    assert a.loc["2020", "unit_value_usd_t"] == pytest.approx(
        value.loc["2020-01":"2020-12"].sum() / volume.loc["2020-01":"2020-12"].sum()
    )
