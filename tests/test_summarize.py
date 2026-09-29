"""The takeaway templates: every branch, on small hand-made pages, and the number format."""

import math

import numpy as np
import pandas as pd
import pytest

from pipeline import summarize as s

MINUS = "−"  # U+2212


def ci(est, lo, hi, se=0.05):
    return {"est": est, "se": se, "t": est / se, "p": 0.5, "lo": lo, "hi": hi}


# -- numbers -------------------------------------------------------------------------------
def test_signed_uses_the_typographic_minus_and_no_sign_on_zero():
    assert s.signed(-0.0234, ".2f") == f"{MINUS}0.02"
    assert s.signed(0.057, "+.2f") == "+0.06"
    assert s.signed(-0.0004, "+.2f") == "0.00"
    assert s.signed(-0.4, ".0f") == "0"
    assert "-" not in s.signed(-12.5, ".1f")


def test_num_and_clean():
    assert s.num(float("nan")) is None and s.num(None) is None and s.num(math.inf) is None
    assert s.num(-0.0) == 0.0 and math.copysign(1, s.num(-0.0)) == 1
    assert s.num(0.1234567) == 0.123457
    out = s.clean({"a": np.float64(1.23456789), "b": (np.int64(3), np.nan), "c": np.bool_(True)})
    assert out == {"a": 1.234568, "b": [3, None], "c": True}
    assert type(out["b"][0]) is int and type(out["c"]) is bool


def test_weight_row_sums_to_one_after_rounding():
    shares = pd.Series(
        {
            "coal": 1 / 3,
            "copper": 1 / 3,
            "gold": 1 / 6,
            "iron_ore": 1 / 18,
            "oil": 1 / 18,
            "zinc": 1 / 18,
        }
    )
    row = s.weight_row(shares)
    assert abs(sum(row.values()) - 1) <= 1e-12
    assert all(round(v, 6) == v for v in row.values())


def test_month_name_and_listing():
    assert s.month_name("2026-08") == "Aug 2026"
    assert s.listing(["2009"]) == "2009"
    assert s.listing(["2009", "2013", "2016"]) == "2009, 2013 and 2016"


# -- copper --------------------------------------------------------------------------------
def copper_page(full12, post3, post12, coal, r2=0.49):
    flat = ci(0.0, -0.1, 0.1)
    return {
        "samples": [
            {
                "id": "full",
                "start": "2001-01",
                "end": "2026-08",
                "copper": [flat] * 12 + [full12],
                "coal_h12": coal,
            },
            {
                "id": "post2017",
                "start": "2017-01",
                "end": "2026-08",
                "copper": [flat] * 3 + [post3] + [flat] * 8 + [post12],
                "coal_h12": flat,
            },
        ],
        "fit12": {"r2": r2},
    }


def test_copper_takeaway_as_on_the_site():
    page = copper_page(
        full12=ci(-0.226, -0.343, -0.109),
        post3=ci(-0.024, -0.08, 0.03),
        post12=ci(-0.204, -0.301, -0.107),
        coal=ci(0.057, -0.002, 0.116),
    )
    assert s.copper_takeaway(page) == (
        "A 10% fall in the copper price has been followed by a 2.3% weaker tugrik over the "
        "next 12 months (95% CI 1.1–3.4%, 2001–2026). Since 2017 it arrives after month 3: "
        "of the 2.0% (95% CI 1.1–3.0%), 0.2% comes in months 0–3. World coal prices show no "
        "such effect (+0.06, the wrong sign)."
    )


def test_copper_takeaway_not_significant():
    page = copper_page(
        full12=ci(-0.05, -0.15, 0.03),
        post3=ci(-0.01, -0.05, 0.03),
        post12=ci(-0.2, -0.3, -0.1),
        coal=ci(-0.2, -0.3, -0.1),  # coal strengthens the tugrik: no coal clause
    )
    text = s.copper_takeaway(page)
    assert text.startswith("The tugrik's move in the 12 months after a 10% fall")
    assert f"cannot be told apart from zero (95% CI {MINUS}0.3 to 1.5%, 2001–2026)." in text
    assert "+0.5%" in text
    assert "Since 2017" in text  # the timing clause stands on the post-2017 numbers
    assert "World coal" not in text


def test_copper_timing_clause_off():
    big_early = copper_page(
        ci(-0.2, -0.3, -0.1), ci(-0.1, -0.2, 0.0), ci(-0.2, -0.3, -0.1), ci(-0.2, -0.3, -0.1)
    )
    assert "Since 2017" not in s.copper_takeaway(big_early)  # 0.1 is not < 0.25 x 0.2
    unclear = copper_page(
        ci(-0.2, -0.3, -0.1), ci(-0.01, -0.05, 0.03), ci(-0.2, -0.4, 0.01), ci(-0.2, -0.3, -0.1)
    )
    assert "Since 2017" not in s.copper_takeaway(unclear)  # post-2017 CI includes zero


def test_copper_timing_clause_needs_a_weakening():
    # since 2017 a significant *strengthening*: the clause would call it the weakening
    stronger = copper_page(
        ci(-0.226, -0.343, -0.109),
        ci(0.001, -0.05, 0.05),
        ci(0.02, 0.01, 0.03),
        ci(-0.2, -0.3, -0.1),
    )
    assert "Since 2017" not in s.copper_takeaway(stronger)
    # the full sample significantly the other way: "it" would contradict the first sentence
    flipped = copper_page(
        ci(0.1, 0.05, 0.15), ci(-0.01, -0.05, 0.03), ci(-0.2, -0.3, -0.1), ci(-0.2, -0.3, -0.1)
    )
    assert "Since 2017" not in s.copper_takeaway(flipped)


def test_copper_coal_clause_when_not_significant():
    page = copper_page(
        ci(-0.2, -0.3, -0.1), ci(-0.1, -0.2, 0.0), ci(-0.2, -0.3, -0.1), ci(-0.02, -0.08, 0.04)
    )
    assert s.copper_takeaway(page).endswith(
        f"World coal prices show no such effect ({MINUS}0.02, not significant)."
    )


def test_copper_takeaway_wrong_sign_significant():
    page = copper_page(
        ci(0.1, 0.05, 0.15), ci(0.0, -0.1, 0.1), ci(0.1, -0.1, 0.3), ci(-0.2, -0.3, -0.1)
    )
    assert "a 1.0% stronger tugrik" in s.copper_takeaway(page)
    assert "(95% CI 0.5–1.5%" in s.copper_takeaway(page)


@pytest.mark.parametrize(
    ("r2", "words"),
    [
        (0.7, "most"),
        (0.49, "about half"),
        (0.3, "about a third"),
        (0.12, "a small part"),
        (0.05, "almost none"),
    ],
)
def test_copper_fit_takeaway_words(r2, words):
    text = s.copper_fit_takeaway({"fit12": {"r2": r2}})
    assert f"account for {words} of the tugrik's year-on-year moves (R² = {r2:.2f})." in text


# -- coal ----------------------------------------------------------------------------------
def coal_year(year, volume_vs, uv, dq, du, partial=False):
    return {
        "year": year,
        "partial": partial,
        "volume_mt": volume_vs / 3,
        "unit_value_usd_t": uv,
        "volume_vs_2019_pct": volume_vs,
        "dlog_volume": dq,
        "dlog_unit_value": du,
    }


BORDER = {"start": "2020-02", "end": "2022-12"}


def test_coal_takeaway_volume_led():
    page = {
        "border": BORDER,
        "annual": [
            coal_year("2019", 100.0, 84.1, 0.9, 8.5),
            coal_year("2020", 78.3, 74.2, -24.4, -12.6),
            coal_year("2021", 44.03, 172.1, -57.6, 84.2),
            coal_year("2022", 86.9, 204.4, 68.0, 17.2),
            coal_year("2023", 190.2, 127.8, 78.3, -46.9),
            coal_year("2024", 228.8, 103.8, 18.5, -20.8),
            coal_year("2025", 245.9, 64.1, 7.2, -48.3),
            coal_year("2026", 310.0, 69.9, None, None, partial=True),
        ],
    }
    assert s.coal_takeaway(page) == (
        "Coal income followed the Chinese border: shipments fell to 44% of their 2019 tonnage "
        "in 2021 and reached 246% in 2025, while Mongolia's price per tonne went from 172 to "
        "64 USD/t."
    )


def test_coal_takeaway_price_led_and_short_of_2019():
    page = {
        "border": BORDER,
        "annual": [
            coal_year("2020", 90.0, 70.0, -5.0, -40.0),
            coal_year("2021", 80.0, 150.0, -10.0, 70.0),
            coal_year("2022", 95.0, 90.0, 15.0, -50.0),
        ],
    }
    text = s.coal_takeaway(page)
    assert text.startswith("Coal income followed prices more than the border:")
    assert "were back to only 95% in 2022" in text


def test_coal_takeaway_without_border_years():
    page = {"border": BORDER, "annual": [coal_year("2012", 57.0, 90.9, -1.8, -16.0)]}
    assert s.coal_takeaway(page) == "In 2012 Mongolia exported 19.0 Mt of coal at 91 USD/t."


def test_coal_gap_takeaway():
    wide = {
        "monthly": {
            "months": ["2017-01", "2017-02", "2026-08"],
            "unit_value_usd_t": [50.0, 150.0, 75.48],
            "benchmark_usd_t": [100.0, 100.0, 135.2],
        }
    }
    assert s.coal_gap_takeaway(wide) == (
        "Mongolia's coal fetched $75/t in Aug 2026 against $135 for the Australian benchmark. "
        "Since 2017 it has sold for between 50% and 150% of the benchmark, so world coal "
        "prices say little about what Mongolia earns."
    )
    narrow = {
        "monthly": {
            "months": ["2017-01", "2017-02"],
            "unit_value_usd_t": [90.0, 100.0],
            "benchmark_usd_t": [100.0, 100.0],
        }
    }
    assert s.coal_gap_takeaway(narrow).endswith("so the two have moved together.")
    none = {
        "monthly": {"months": ["2017-01"], "unit_value_usd_t": [None], "benchmark_usd_t": [1.0]}
    }
    assert s.coal_gap_takeaway(none).startswith("There is no month")


# -- prices --------------------------------------------------------------------------------
def prices_page(pref12, dl12=None, years=()):
    dl12 = dl12 or ci(-0.023, -0.201, 0.154)
    flat = ci(0.0, -0.1, 0.1)
    return {
        "specs": [
            {"id": "dl", "cum": [flat] * 12 + [dl12]},
            {"id": "preferred", "cum": [flat] * 12 + [pref12]},
        ],
        "years": list(years),
    }


def test_prices_takeaway_cannot_rule_out():
    page = prices_page(ci(0.1297, -0.0188, 0.2782))
    assert s.prices_takeaway(page) == (
        "About 13% of a depreciation shows up in consumer prices within a year, but the data "
        f"can't rule out zero or 28% (95% CI {MINUS}2% to 28%)."
    )


def test_prices_takeaway_significant_and_negative():
    assert s.prices_takeaway(prices_page(ci(0.142, 0.004, 0.281))) == (
        "About 14% of a depreciation shows up in consumer prices within a year (95% CI 0% to 28%)."
    )
    # zero or below, but the interval reaches well above zero: never "none shows up"
    assert s.prices_takeaway(prices_page(ci(-0.023, -0.201, 0.154))) == (
        "The share of a depreciation that shows up in consumer prices within a year cannot be "
        f"told apart from zero (estimate {MINUS}2%); the data can't rule out up to 15% (95% CI "
        f"{MINUS}20% to 15%)."
    )
    assert "can't rule out up to 15%" in s.prices_takeaway(prices_page(ci(0.0, -0.15, 0.15)))
    assert s.prices_takeaway(prices_page(ci(-0.05, -0.09, -0.01))) == (
        f"Consumer prices have fallen, not risen, after depreciations: {MINUS}5% of a "
        f"depreciation within a year (95% CI {MINUS}9% to {MINUS}1%)."
    )


def year(y, fx, cu):
    return {"year": y, "fx_dec_dec_pct": fx, "copper_avg_pct": cu}


def test_prices_context_takeaway():
    years = [
        year("2008", 5.0, -2.3),
        year("2009", 17.7, -26.0),
        year("2013", 19.9, -7.9),
        year("2016", 24.4, -11.7),
        year("2022", 20.4, -5.3),
        year("2023", -0.3, None),
    ]
    assert s.prices_context_takeaway(prices_page(ci(0.1, 0, 0.2), years=years)) == (
        "The big depreciations (2009, 2013, 2016 and 2022: MNT per US$ up 15% or more, December "
        "to December) all came in years of falling copper prices. That is one reason the raw "
        "link from the "
        f"tugrik to prices ({MINUS}2% of a depreciation within a year, 95% CI {MINUS}20% to "
        "15%) cannot be told apart from zero."
    )
    years[1] = year("2009", 17.7, 5.0)
    text = s.prices_context_takeaway(prices_page(ci(0.1, 0, 0.2), years=years))
    assert "3 of the 4 came in years of falling copper prices. That is one reason" in text
    years[2] = year("2013", 19.9, 1.0)  # only 2 of 4: no "one reason"
    text = s.prices_context_takeaway(prices_page(ci(0.1, 0, 0.2), years=years))
    assert "2 of the 4 came in years of falling copper prices. The raw link" in text


def test_prices_context_takeaway_without_big_years_and_significant_raw_link():
    page = prices_page(ci(0.1, 0, 0.2), dl12=ci(0.2, 0.1, 0.3), years=[year("2010", 5.0, 3.0)])
    assert s.prices_context_takeaway(page) == (
        "MNT per US$ never rose 15% or more in a year (December to December) in these data. "
        "The raw link from the tugrik to prices is 20% of a depreciation within a year, "
        "95% CI 10% to 30%."
    )


# -- growth --------------------------------------------------------------------------------
def growth_page(b, nobs=29, p=0.016):
    return {"fit": {"nobs": nobs, "mxpi_l1": b, "p_l1_nonrobust": p}}


def test_growth_takeaway_as_on_the_site():
    b = {"est": 0.0849, "se": 0.0232, "t": 3.66, "p": 0.001, "lo": 0.037, "hi": 0.133}
    assert s.growth_takeaway(growth_page(b)) == (
        "A 10% rise in Mongolia's export prices has been followed by about 0.85 pp faster "
        "growth the next year (29 years; t = 3.7 with HAC, p = 0.016 without — treat as "
        "descriptive)."
    )


def test_growth_takeaway_other_branches():
    b = {"est": -0.05, "se": 0.02, "t": -2.5, "p": 0.02, "lo": -0.09, "hi": -0.01}
    text = s.growth_takeaway(growth_page(b, nobs=35))
    assert "about 0.50 pp slower growth" in text
    assert "descriptive" not in text and f"t = {MINUS}2.5 with HAC" in text
    b = {"est": 0.02, "se": 0.03, "t": 0.67, "p": 0.5, "lo": -0.04, "hi": 0.08}
    text = s.growth_takeaway(growth_page(b, p=0.51))
    assert text.startswith(
        "Growth the year after a 10% rise in Mongolia's export prices, +0.20 pp,"
    )
    assert "cannot be told apart from zero (29 years;" in text


def test_growth_weo_takeaway():
    def page(rates):
        return {
            "weo": {"years": [str(2026 + i) for i in range(len(rates))], "gdp_growth_pct": rates}
        }

    assert s.growth_weo_takeaway(page([5.3, 5.3, 5.2, 5.0, 5.0, 5.0])) == (
        "The IMF expects 5.3% in 2026 and about 5% a year after that."
    )
    assert s.growth_weo_takeaway(page([5.3, 2.0, 7.5])) == (
        "The IMF expects 5.3% in 2026 and between 2.0% and 7.5% a year after that."
    )
    assert s.growth_weo_takeaway(page([-1.0])) == f"The IMF expects {MINUS}1.0% in 2026."
    assert s.growth_weo_takeaway(page([])) == "The IMF's growth forecasts are not available."


def test_growth_mix_takeaway():
    def row(y, coal, copper):
        return {"year": y, "weights": {"coal": coal, "copper": copper}}

    page = {
        "annual": [row("1996", 0.00004, 1.0), row("2011", 0.54, 0.23), row("2025", 0.413, 0.418)]
    }
    assert s.growth_mix_takeaway(page) == (
        "Coal went from none of these exports in 1996 to 54% in 2011; in 2025, copper and "
        "coal split them 42/41."
    )
    page["annual"][0] = row("1996", 0.04, 0.9)
    assert s.growth_mix_takeaway(page).startswith("Coal went from 4% of these exports")


# -- the registry of templates -------------------------------------------------------------
def test_every_page_takeaway_has_a_template():
    assert set(s.TAKEAWAYS) == {page for page, _ in s.PAGES}
    for templates in s.TAKEAWAYS.values():
        assert "takeaway" in templates
