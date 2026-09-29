"""The transforms: exchange rates, CPI splice, policy rate, trade and export prices."""

import numpy as np
import pandas as pd
import pytest

from pipeline.sources import series
from pipeline.transform import (
    annual_mean,
    annual_sum,
    broad_dollar,
    extend,
    fx_consensus,
    month_end,
    mxpi,
    mxpi_weights,
    newest_base,
    policy_month_end,
    unit_value,
    weekday_mean,
)


def test_weekday_mean_skips_weekends():
    # 2026-08-01 is a Saturday; the weekend rates are far off and must not count
    days = [(f"2026-08-{d:02d}", 3600.0) for d in (1, 2)]
    days += [(f"2026-08-{d:02d}", 3500.0 + d) for d in range(3, 32) if d not in (8, 9, 15, 16)]
    days += [(f"2026-08-{d:02d}", 3600.0) for d in (8, 9, 15, 16, 22, 23, 29, 30)]
    days = [(d, v) for d, v in dict(days).items()]
    out = weekday_mean(series(days))
    weekdays = [3500.0 + d for d in range(3, 32) if d not in (8, 9, 15, 16, 22, 23, 29, 30)]
    assert out.to_dict() == {"2026-08": pytest.approx(sum(weekdays) / len(weekdays))}


def test_weekday_mean_drops_a_month_in_progress():
    days = [(f"2026-08-{d:02d}", 3500.0) for d in range(1, 32)]
    days += [(f"2026-09-{d:02d}", 3600.0) for d in range(1, 28)]
    assert weekday_mean(series(days)).to_dict() == {"2026-08": 3500.0}
    days += [("2026-09-28", 3600.0), ("2026-09-29", 3600.0), ("2026-09-30", 3600.0)]
    assert weekday_mean(series(days)).to_dict() == {"2026-08": 3500.0, "2026-09": 3600.0}


def test_newest_base_takes_each_month_from_the_newest_base():
    b2015 = series([("2022-06", 1.0), ("2022-07", 1.1)])
    b2020 = series([("2022-06", 2.0), ("2022-07", 2.1), ("2022-08", 2.2), ("2023-02", 2.3)])
    b2023 = series([("2023-02", 3.3), ("2023-03", 3.4)])
    out = newest_base({2015: b2015, 2020: b2020, 2023: b2023})
    assert out.to_dict() == {
        "2022-06": 2.0,
        "2022-07": 2.1,
        "2022-08": 2.2,
        "2023-02": 3.3,
        "2023-03": 3.4,
    }
    assert newest_base({2015: b2015}).to_dict() == b2015.to_dict()


# -- month ends ----------------------------------------------------------------------------
def test_month_end_is_the_last_observation_of_complete_months():
    days = [(f"2026-07-{d:02d}", 3500.0 + d) for d in range(1, 32)]
    days += [(f"2026-08-{d:02d}", 3600.0 + d) for d in range(1, 32)]
    days += [(f"2026-09-{d:02d}", 3700.0) for d in range(1, 28)]  # September is not over
    assert month_end(series(days)).to_dict() == {"2026-07": 3531.0, "2026-08": 3631.0}
    # a month counts once its last day is in, whatever the weekday
    assert month_end(series(days[:62])).index[-1] == "2026-08"


# -- the FX consensus ----------------------------------------------------------------------
def avgs(**by_source):
    return {name: series(values.items()) for name, values in by_source.items()}


def test_consensus_takes_the_average_closest_to_the_daily_mean():
    # 2009-07: the IMF is 10 MNT off; NSO and BoM agree with the daily mean
    averages = avgs(
        nso={"2009-07": 1438.9, "2009-08": 1420.0},
        imf={"2009-07": 1448.9, "2009-08": 1420.0},
        bom={"2009-07": 1438.9, "2009-08": 1430.0},
    )
    daily = series([("2009-07", 1438.8), ("2009-08", 1422.0)])
    values, chosen = fx_consensus(averages, daily)
    assert values.to_dict() == {"2009-07": 1438.9, "2009-08": 1420.0}
    # ties go to NSO, then the IMF, then the BoM
    assert chosen.to_dict() == {"2009-07": "nso", "2009-08": "nso"}
    averages["nso"] = series([("2009-07", 1400.0), ("2009-08", 1400.0)])
    values, chosen = fx_consensus(averages, daily)
    assert values.to_dict() == {"2009-07": 1438.9, "2009-08": 1420.0}
    assert chosen.to_dict() == {"2009-07": "bom", "2009-08": "imf"}


def test_consensus_rules_before_2001_and_without_a_daily_mean():
    averages = avgs(
        imf={"1992-12": 40.0, "1993-06": 150.0, "1996-07": 500.0, "2005-01": 1200.0},
        bom={"1992-12": 45.0, "1993-06": 155.0, "1996-07": 560.0, "2005-01": 1210.0},
        nso={"1996-07": 505.0, "2005-01": 1190.0},
    )
    values, chosen = fx_consensus(averages, series([]))
    assert values.to_dict() == {
        "1992-12": 40.0,  # the administered rate: IMF
        "1993-06": 155.0,  # 1993: the BoM
        "1996-07": 505.0,  # 1994-2000: the median, which leaves out the BoM's wrong value
        "2005-01": 1200.0,  # no daily mean: the median
    }
    assert chosen.to_dict() == {
        "1992-12": "imf",
        "1993-06": "bom",
        "1996-07": "median",
        "2005-01": "median",
    }
    # before 1990-07 nothing
    early = avgs(imf={"1990-06": 5.0, "1990-07": 5.6})
    assert fx_consensus(early, series([]))[0].to_dict() == {"1990-07": 5.6}


# -- policy rate ---------------------------------------------------------------------------
def test_policy_step_function_at_month_end():
    decisions = series(
        [
            ("2026-01-15", 10.0),
            ("2026-03-05", 11.0),
            ("2026-03-25", 12.0),  # two decisions in March: the later one holds at month end
            ("2026-05-31", 13.0),  # effective on the last day of May: counts for May
            ("2026-06-01", 12.5),
        ]
    )
    out = policy_month_end(decisions, "2026-07")
    assert out.to_dict() == {
        "2026-01": 10.0,
        "2026-02": 10.0,
        "2026-03": 12.0,
        "2026-04": 12.0,
        "2026-05": 13.0,
        "2026-06": 12.5,
        "2026-07": 12.5,
    }
    assert policy_month_end(decisions, "2026-02").index[-1] == "2026-02"


# -- trade, annual -------------------------------------------------------------------------
def test_unit_values_and_full_years():
    value = series([("2025-01", 100.0), ("2025-02", 50.0), ("2025-03", 30.0)])
    volume = series([("2025-01", 2.0), ("2025-02", 0.0), ("2025-03", 3.0)])
    assert unit_value(value, volume).to_dict() == {"2025-01": 50.0, "2025-03": 10.0}
    months = [f"2024-{k:02d}" for k in range(1, 13)] + ["2025-01", "2025-02"]
    s = series((m, float(i)) for i, m in enumerate(months))
    assert annual_sum(s).to_dict() == {"2024": 66.0}  # 2025 has only two months
    assert annual_mean(s).to_dict() == {"2024": 5.5}


# -- the export-price index ----------------------------------------------------------------
GOODS = ("coal", "copper", "gold", "iron_ore", "oil", "zinc")


def test_mxpi_weights_interpolate_between_comtrade_and_nso():
    comtrade = {g: series([("2006", 1.0), ("2007", 1.0)]) for g in GOODS}
    comtrade["coal"] = series([("2007", 5.0)])  # no coal record in 2006 means no coal exports
    nso = {g: series([("2011", 10.0)]) for g in GOODS}
    nso["copper"] = series([("2011", 50.0)])
    shares, source = mxpi_weights(comtrade, nso)
    assert list(shares.index) == ["2006", "2007", "2008", "2009", "2010", "2011"]
    assert shares.loc["2006", "coal"] == 0.0 and shares.loc["2006", "copper"] == pytest.approx(0.2)
    assert shares.loc["2007", "coal"] == pytest.approx(0.5)
    assert shares.loc["2011", "copper"] == pytest.approx(0.5)
    # 2008-2010 lie on the straight line from 2007 to 2011
    assert shares.loc["2009", "coal"] == pytest.approx((0.5 + 0.1) / 2)
    assert np.allclose(shares.sum(axis=1), 1.0)
    assert source.to_dict() == {
        "2006": "comtrade",
        "2007": "comtrade",
        "2008": "interpolated",
        "2009": "interpolated",
        "2010": "interpolated",
        "2011": "nso",
    }


def test_mxpi_weights_refuse_a_year_that_does_not_sum_to_one():
    comtrade = {g: series([("2006", 0.0), ("2007", 1.0)]) for g in GOODS}  # 2006: no exports
    nso = {g: series([("2011", 10.0)]) for g in GOODS}
    with pytest.raises(ValueError, match="export shares of 2006"):
        mxpi_weights(comtrade, nso)


def test_mxpi_uses_last_years_weights():
    years = ["2000", "2001", "2002"]
    weights = pd.DataFrame({g: [1 / 6] * 3 for g in GOODS}, index=years)  # equal shares in 2000
    weights.loc["2001"] = [1.0, 0, 0, 0, 0, 0]  # all coal in 2001
    weights.loc["2002"] = [0, 1.0, 0, 0, 0, 0]
    prices = pd.DataFrame(
        {g: [100.0, 100.0, 100.0, 100.0] for g in GOODS}, index=["1999", "2000", "2001", "2002"]
    )
    prices.loc["2001", "coal"] = 200.0  # coal doubles in 2001
    prices.loc["2002", "coal"] = 100.0  # and halves in 2002
    prices.loc["2002", "copper"] = 150.0
    out = mxpi(prices, weights)
    log2 = 100 * np.log(2)
    assert out["2000"] == pytest.approx(0.0)  # the first year uses its own weights
    assert out["2001"] == pytest.approx(log2 / 6)  # 2001 uses 2000's equal shares
    assert out["2002"] == pytest.approx(-log2)  # 2002 uses 2001's: all coal
    assert "2003" not in out.index  # no 2003 prices
    lagged = weights.shift(1).loc["2001":]
    assert np.allclose(lagged.sum(axis=1), 1.0)


def test_broad_dollar_ratio_splice():
    old = series([("2005-11", 80.0), ("2005-12", 90.0), ("2006-01", 100.0), ("2006-02", 99.0)])
    new = series([("2006-01", 110.0), ("2006-02", 111.0)])
    out = broad_dollar(old, new)
    assert out.to_dict() == pytest.approx(
        {"2005-11": 88.0, "2005-12": 99.0, "2006-01": 110.0, "2006-02": 111.0}
    )
    with pytest.raises(ValueError, match="2006-01"):
        broad_dollar(old.iloc[:2], new)


def test_extend_continues_after_the_primary_ends():
    primary = series([("2026-06", 1.0), ("2026-07", 2.0)])
    fallback = series([("2026-06", 9.0), ("2026-07", 9.0), ("2026-08", 3.0)])
    assert extend(primary, fallback).to_dict() == {"2026-06": 1.0, "2026-07": 2.0, "2026-08": 3.0}
    assert extend(series([]), fallback).to_dict() == fallback.to_dict()
