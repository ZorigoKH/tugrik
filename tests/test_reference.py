"""The 2026-09 reference vintage: the frozen specifications on the model inputs of
``tests/fixtures/store_2026-09`` reproduce the trial regressions of 2026-09-27.

The pinned values are what the fixture gives, to 6 decimals; each rounds to the figure the
trial published (``TRIAL``), which the site shows on its method page next to the current
estimate. A change in these numbers means a change in the methods.
"""

from pathlib import Path

import pytest

from pipeline import build, models

FIXTURE = Path(__file__).parent / "fixtures" / "store_2026-09"
TOLERANCE = 5e-4

# name: (pinned value from the fixture, the trial's published figure, its decimals)
REFERENCE = {
    "copper_h12_full": (-0.225941, -0.226, 3),
    "copper_h12_full_se": (0.059264, 0.059, 3),
    "copper_h3_post2017": (-0.023515, -0.024, 3),
    "passthrough_h12": (0.129709, 0.130, 3),
    "passthrough_long_run": (0.215408, 0.215, 3),
    "growth_mxpi_l1": (0.084922, 0.085, 3),
    "growth_sum": (0.115001, 0.115, 3),
    "coal_2021_mt": (16.117590, 16.1, 1),
    "coal_2021_vs_2019_pct": (44.032235, 44.0, 1),
}


@pytest.fixture(scope="module")
def estimates():
    return models.estimate(build.read_inputs(FIXTURE))


def current(e) -> dict[str, float]:
    copper, preferred, growth, coal = e["copper"], e["passthrough_pref"], e["growth"], e["coal"]
    return {
        "copper_h12_full": copper["full"]["copper"][12].est,
        "copper_h12_full_se": copper["full"]["copper"][12].se,
        "copper_h3_post2017": copper["post2017"]["copper"][3].est,
        "passthrough_h12": preferred["full"]["cum"][12].est,
        "passthrough_long_run": preferred["full"]["long_run"].est,
        "growth_mxpi_l1": growth["mxpi_l1"].est,
        "growth_sum": growth["sum"].est,
        "coal_2021_mt": coal.loc["2021", "volume_mt"],
        "coal_2021_vs_2019_pct": coal.loc["2021", "volume_vs_2019_pct"],
    }


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_fixture_reproduces_the_trial(estimates, name):
    pinned, trial, decimals = REFERENCE[name]
    value = current(estimates)[name]
    assert value == pytest.approx(pinned, abs=TOLERANCE)
    assert round(value, decimals) == pytest.approx(trial)


def test_fixture_samples_are_the_trials(estimates):
    copper = estimates["copper"]
    assert {k: (v["fit"].nobs, v["fit"].start, v["fit"].end) for k, v in copper.items()} == {
        "full": (308, "2001-01", "2026-08"),
        "ex_gfc": (298, "2001-01", "2026-08"),
        "pre2017": (192, "2001-01", "2016-12"),
        "post2017": (116, "2017-01", "2026-08"),
        "post2017_ex_border": (81, "2017-01", "2026-08"),
    }
    assert [v["fit"].maxlags for v in copper.values()] == [5, 5, 4, 4, 3]
    fit12 = estimates["fit12"]
    assert (fit12["fit"].nobs, fit12["fit"].maxlags) == (285, 12)
    assert fit12["fit"].r2 == pytest.approx(0.488, abs=TOLERANCE)
    assert fit12["copper_t6"].est == pytest.approx(-0.179, abs=TOLERANCE)
    preferred = estimates["passthrough_pref"]
    assert preferred["full"]["fit"].nobs == 296
    assert estimates["passthrough_dl"]["cum"][12].est == pytest.approx(-0.023, abs=TOLERANCE)
    late = preferred["subsamples"][2]
    assert late["cum"][12].est == pytest.approx(0.142, abs=TOLERANCE)
    assert late["cum"][12].lo > 0
    growth = estimates["growth"]
    assert (growth["fit"].nobs, growth["fit"].start, growth["fit"].end) == (29, "1997", "2025")
    assert growth["p_l1_nonrobust"] == pytest.approx(0.016, abs=TOLERANCE)
    assert [r["fit"].nobs for r in growth["robustness"]] == [28, 28, 27, 28, 26]
