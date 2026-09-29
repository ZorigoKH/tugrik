"""Every series in the store: what it is, where it comes from and what counts as broken.

``SERIES`` maps a series id (also its file name, ``data/<id>.csv``) to a :class:`Series`.
The fetch stage uses it to check each download (dates, gaps, bounds) and to decide how much
a stored value may be revised before a human has to look (:class:`Revision`). The build
uses the labels, units, ``max_age_days`` and ``redistribute`` (whether the site offers the
series as a CSV download).

``SOURCES`` describes the seven publishers for the site's data page.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Revision:
    """How far a stored observation may move when it is fetched again.

    ``kind`` is ``"relative"`` (a share of the stored value), ``"absolute"`` (in the series'
    units), ``"exact"`` (no change at all, and no observation may disappear) or ``"accept"``
    (revisions are expected; they are counted, never blocked). Only observations dated from
    ``since`` on are guarded, and the last ``recent`` months of the stored series may change
    freely: recent data are provisional.
    """

    kind: str
    tolerance: float = 0.0
    recent: int = 0
    since: str = ""


# FX: any month older than 2 months changes by more than 0.1%
FX = Revision("relative", 0.001, recent=2)
# Pink Sheet: any month since 1990 changes by more than 0.5% (known rounding noise on copper
# is at most 0.5 USD/t); the IMF's commodity prices, a cross-check only, get the same rule
# with their last two months free
PRICES = Revision("relative", 0.005, since="1990-01")
PCPS = Revision("relative", 0.005, recent=2, since="1990-01")
# the broad dollar index is revised when the Fed updates its trade weights
DOLLAR = Revision("relative", 0.005, recent=2)
# NSO trade: a month older than 12 months changes by more than 2% (recent customs data
# revise freely)
TRADE = Revision("relative", 0.02, recent=12)
# CPI: a monthly percent change older than 3 months moves by more than 0.05 percentage points
CPI = Revision("absolute", 0.05, recent=3)
# BoM policy rate: any past decision changes
DECISIONS = Revision("exact")
# WDI and IMF annual: revisions are expected (WDI every July, WEO in April and October)
ANNUAL = Revision("accept")


@dataclass(frozen=True)
class Series:
    """One stored series. ``freq`` is ``"D"`` (daily), ``"M"`` (monthly), ``"A"`` (annual)
    or ``"E"`` (events: one row per policy decision, dated the day it took effect).

    ``bounds`` apply from ``bounds_from`` on (CPI changes before 1996 were hyperinflation);
    observations before ``start`` are dropped when fetched (NSO's exchange rates have no
    data for 1989-1993). ``max_age_days`` is how old the last observation may be, counted
    from the end of its period, before the site calls the series stale.
    """

    id: str
    source: str
    label: str
    freq: str
    units: str
    bounds: tuple[float, float]
    revision: Revision
    max_age_days: int | None
    redistribute: bool
    bounds_from: str = ""
    start: str = ""


MNT = (1.0, 20_000.0)
CPI_MOM = (-10.0, 30.0)
CPI_YOY = (-20.0, 100.0)
FLOW = (0.0, 1e9)  # volumes and values are never negative

# fmt: off
_SERIES = [
    # -- Bank of Mongolia -----------------------------------------------------------------
    Series("bom_usdmnt_daily", "bom", "MNT per US dollar, official daily rate", "D",
           "MNT per USD", MNT, FX, 10, False),
    Series("bom_usdmnt_monthly_avg", "bom", "MNT per US dollar, monthly average (BoM)", "M",
           "MNT per USD", MNT, FX, 45, False),
    Series("bom_policy_rate_decisions", "bom", "Policy rate, by decision", "E",
           "percent", (0.0, 30.0), DECISIONS, None, False),
    Series("bom_cpi_yoy", "bom", "CPI inflation as reported by the BoM, national, year on year",
           "M", "percent", CPI_YOY, CPI, 60, False),
    # -- NSO --------------------------------------------------------------------------------
    *[
        Series(f"nso_cpi_{kind}_b{base}", "nso",
               f"CPI, national, {what} ({base}=100 base)", "M", "percent",
               bounds, CPI, 60, True, bounds_from="1996-01")
        for kind, what, bounds in (("mom", "month on month", CPI_MOM),
                                   ("yoy", "year on year", CPI_YOY))
        for base in (2015, 2020, 2023)
    ],
    Series("nso_usdmnt_monthly_avg", "nso", "MNT per US dollar, monthly average (NSO)", "M",
           "MNT per USD", MNT, FX, 60, True, start="1994-01"),
    Series("nso_usdmnt_eop", "nso", "MNT per US dollar, end of month (NSO)", "M",
           "MNT per USD", MNT, FX, 60, True),
    Series("nso_exports_total_musd", "nso", "Exports, total", "M",
           "million USD", (0.0, 10_000.0), TRADE, 60, True),
    *[
        Series(f"nso_export_{good}_{suffix}", "nso", f"Exports of {name}, {what}", "M",
               units, FLOW, TRADE, 60, True)
        for good, name, unit, unit_name in (
            ("coal", "coal", "kt", "thousand tonnes"),
            ("copper_conc", "copper concentrate", "kt", "thousand tonnes"),
            ("gold", "gold", "t", "tonnes"),
            ("iron_ore", "iron ore", "kt", "thousand tonnes"),
            ("crude_oil", "crude oil", "kbbl", "thousand barrels"),
            ("zinc_conc", "zinc concentrate", "kt", "thousand tonnes"),
        )
        for suffix, what, units in (("kusd", "value", "thousand USD"),
                                    (unit, "volume", unit_name))
    ],
    # -- World Bank Pink Sheet --------------------------------------------------------------
    Series("pinksheet_copper", "pinksheet", "Copper, LME grade A", "M",
           "USD per tonne", (500.0, 50_000.0), PRICES, 45, True),
    Series("pinksheet_coal_australian", "pinksheet", "Coal, Australian thermal", "M",
           "USD per tonne", (5.0, 1_000.0), PRICES, 45, True),
    Series("pinksheet_gold", "pinksheet", "Gold", "M",
           "USD per troy ounce", (30.0, 20_000.0), PRICES, 45, True),
    Series("pinksheet_iron_ore", "pinksheet", "Iron ore, cfr spot", "M",
           "USD per dry metric ton unit", (5.0, 1_000.0), PRICES, 45, True),
    Series("pinksheet_brent", "pinksheet", "Crude oil, Brent", "M",
           "USD per barrel", (1.0, 500.0), PRICES, 45, True),
    Series("pinksheet_zinc", "pinksheet", "Zinc", "M",
           "USD per tonne", (100.0, 20_000.0), PRICES, 45, True),
    # -- IMF SDMX ---------------------------------------------------------------------------
    Series("imf_usdmnt_monthly_avg", "imf_sdmx", "MNT per US dollar, monthly average (IMF)",
           "M", "MNT per USD", MNT, FX, 75, True),
    Series("imf_usdmnt_eop", "imf_sdmx", "MNT per US dollar, end of month (IMF)", "M",
           "MNT per USD", MNT, FX, 75, True),
    Series("imf_cpi_yoy", "imf_sdmx", "CPI, year on year (IMF)", "M",
           "percent", CPI_YOY, CPI, 90, True, bounds_from="1996-01"),
    Series("imf_cpi_mom", "imf_sdmx", "CPI, month on month (IMF)", "M",
           "percent", CPI_MOM, CPI, 90, True, bounds_from="1996-01"),
    Series("imf_pcps_copper", "imf_sdmx", "Copper (IMF PCPS)", "M",
           "USD per tonne", (500.0, 50_000.0), PCPS, 75, True),
    Series("imf_pcps_gold", "imf_sdmx", "Gold (IMF PCPS)", "M",
           "USD per troy ounce", (30.0, 20_000.0), PCPS, 75, True),
    Series("imf_pcps_zinc", "imf_sdmx", "Zinc (IMF PCPS)", "M",
           "USD per tonne", (100.0, 20_000.0), PCPS, 75, True),
    Series("imf_cnyusd_monthly_avg", "imf_sdmx", "CNY per US dollar, monthly average (IMF)",
           "M", "CNY per USD", (0.5, 20.0), FX, 75, True),
    # -- IMF DataMapper (WEO) ---------------------------------------------------------------
    Series("imf_weo_gdp_growth", "imf_datamapper", "Real GDP growth (IMF WEO)", "A",
           "percent", (-50.0, 50.0), ANNUAL, 400, True),
    Series("imf_weo_cpi_inflation", "imf_datamapper", "CPI inflation, average (IMF WEO)", "A",
           "percent", (-20.0, 1_000.0), ANNUAL, 400, True),
    Series("imf_weo_gov_debt_pct_gdp", "imf_datamapper", "General government gross debt "
           "(IMF WEO)", "A", "percent of GDP", (0.0, 500.0), ANNUAL, 400, True),
    Series("imf_weo_current_account_pct_gdp", "imf_datamapper", "Current account balance "
           "(IMF WEO)", "A", "percent of GDP", (-100.0, 100.0), ANNUAL, 400, True),
    Series("imf_weo_china_gdp_growth", "imf_datamapper", "China real GDP growth (IMF WEO)",
           "A", "percent", (-50.0, 50.0), ANNUAL, 400, True),
    # -- WDI --------------------------------------------------------------------------------
    Series("wdi_gdp_growth", "wdi", "Real GDP growth (WDI)", "A",
           "percent", (-50.0, 50.0), ANNUAL, 550, True),
    # FDI and the current account arrive 1.5 to 2 years after their year ends: 2024's
    # value is still the latest in mid 2027, about 1,000 days after it
    Series("wdi_fdi_pct_gdp", "wdi", "Foreign direct investment, net inflows (WDI)", "A",
           "percent of GDP", (-100.0, 100.0), ANNUAL, 1100, True),
    Series("wdi_current_account_pct_gdp", "wdi", "Current account balance (WDI)", "A",
           "percent of GDP", (-100.0, 100.0), ANNUAL, 1100, True),
    Series("wdi_china_gdp_growth", "wdi", "China real GDP growth (WDI)", "A",
           "percent", (-50.0, 50.0), ANNUAL, 550, True),
    # -- FRED -------------------------------------------------------------------------------
    Series("fred_usd_broad_index", "fred", "Nominal broad US dollar index (TWEXBGSMTH)", "M",
           "index, January 2006 = 100", (20.0, 300.0), DOLLAR, 75, True),
    Series("fred_cnyusd_monthly_avg", "fred", "CNY per US dollar, monthly average (EXCHUS)",
           "M", "CNY per USD", (0.5, 20.0), FX, 75, True),
]
# fmt: on

SERIES: dict[str, Series] = {s.id: s for s in _SERIES}


@dataclass(frozen=True)
class Source:
    """A publisher, as the site's data page shows it."""

    id: str
    publisher: str
    name: str
    method: str
    url: str
    frequency: str
    license: str
    updated_max_age_days: int | None = None  # the release date it states must be this recent


# fmt: off
SOURCES: dict[str, Source] = {
    s.id: s
    for s in (
        Source("bom", "Bank of Mongolia", "Exchange rates, policy rate and inflation", "POST",
               "https://www.mongolbank.mn/en/currency-rate-movement/data", "daily",
               "none stated; public central-bank data, attributed to the Bank of Mongolia"),
        Source("nso", "National Statistics Office of Mongolia", "CPI, exchange rates and "
               "exports (PxWeb)", "POST", "https://data.1212.mn/api/v1/en/NSO/", "monthly",
               "official statistics; reuse citing \"Source: Mongolian Statistical Service\""),
        Source("pinksheet", "World Bank", "Commodity Price Data (The Pink Sheet), monthly",
               "GET", "https://www.worldbank.org/en/research/commodity-markets", "monthly",
               "CC BY 4.0", updated_max_age_days=45),
        Source("imf_sdmx", "International Monetary Fund", "Exchange rates, CPI and primary "
               "commodity prices (SDMX 2.1)", "GET", "https://api.imf.org/external/sdmx/2.1/",
               "monthly", "IMF terms of use: free reuse with attribution"),
        Source("imf_datamapper", "International Monetary Fund", "World Economic Outlook "
               "(DataMapper API v2)", "GET", "https://www.imf.org/external/datamapper/api/v2/",
               "twice a year", "IMF terms of use: free reuse with attribution"),
        Source("wdi", "World Bank", "World Development Indicators (API v2)", "GET",
               "https://api.worldbank.org/v2/", "annual", "CC BY 4.0"),
        Source("fred", "Federal Reserve Bank of St. Louis", "FRED: broad dollar index and "
               "CNY per USD", "GET", "https://fred.stlouisfed.org/graph/fredgraph.csv",
               "monthly", "Federal Reserve Board data; cite FRED"),
    )
}
# fmt: on
