"""Parsers, on small synthetic payloads in the real shapes. No network, no real data."""

import pandas as pd
import payloads as p
import pytest

from pipeline.registry import SERIES
from pipeline.sources import bom, fred, imf_datamapper, imf_sdmx, nso, pinksheet, series, wdi


def ids(source: str) -> set[str]:
    return {sid for sid, spec in SERIES.items() if spec.source == source}


def test_series_drops_missing_sorts_and_rejects_conflicting_duplicates():
    s = series([("2026-02", 2.0), ("2026-01", 1.0), ("2026-03", None), ("2026-02", 2.0)])
    assert list(s.index) == ["2026-01", "2026-02"]
    assert s.dtype == float
    with pytest.raises(ValueError, match="appears twice"):
        series([("2026-01", 1.0), ("2026-01", 1.5)])


# -- Bank of Mongolia ----------------------------------------------------------------------
def test_bom_reads_thousands_separators_and_rate_dates():
    payload = p.bom_payload(rate=3594.47, months=["2026-07", "2026-08"])
    payload["monthly"]["data"].append({"RATE_DATE": "1993-01", "USD": "-"})  # no rate
    out = bom.parse(payload)
    assert set(out) == ids("bom")
    assert out["bom_usdmnt_monthly_avg"].to_dict() == {"2026-07": 3594.47, "2026-08": 3594.47}
    daily = out["bom_usdmnt_daily"]
    assert daily.index[0] == "2026-07-01" and daily.index[-1] == "2026-08-31"
    assert out["bom_policy_rate_decisions"].to_dict() == {"2024-01-10": 13.0, "2025-03-14": 12.0}
    assert out["bom_cpi_yoy"].iloc[-1] == 5.0


def test_bom_number():
    assert bom.number("3,594.47") == 3594.47
    assert bom.number("11,685.28") == 11685.28
    assert bom.number("-") is None
    assert bom.number(None) is None


def test_bom_rejects_an_unsuccessful_answer():
    payload = p.bom_payload(months=["2026-08"])
    payload["policy"] = {"success": False, "message": "error"}
    with pytest.raises(ValueError, match="success"):
        bom.parse(payload)


# -- NSO -----------------------------------------------------------------------------------
def test_nso_parses_every_table_by_cyrillic_dimension_codes():
    out = nso.parse(p.nso_payload(rate=3594.47))
    assert set(out) == ids("nso")
    assert out["nso_usdmnt_monthly_avg"]["2026-08"] == 3594.47
    assert out["nso_exports_total_musd"].index[-1] == "2026-08"
    # base 2015 ends in 2024-12 and base 2023 starts in 2025-01 (see payloads.nso_cpi)
    assert out["nso_cpi_yoy_b2015"].index[-1] == "2024-12"
    assert out["nso_cpi_yoy_b2023"].index[0] == "2025-01"
    assert len(out["nso_cpi_mom_b2020"]) == len(p.MONTHS)


def test_nso_query_uses_codes_and_the_all_filter():
    body = nso.query(nso.QUERIES["cpi_mom"])
    assert body["response"] == {"format": "json-stat2"}
    assert body["query"][0] == {
        "code": "Суурь он",
        "selection": {"filter": "all", "values": ["*"]},
    }
    assert body["query"][1]["selection"] == {"filter": "item", "values": ["0"]}


def test_nso_turns_year_to_date_totals_into_monthly_flows():
    months = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
    ds = p.nso_commodities(volume=10.0, value=7.0, months=months)
    # the table starts in November: the first year's months do not start in January
    with pytest.raises(ValueError, match="do not run from January"):
        nso.parse({**p.nso_payload(), "commodities": ds})
    cumulative = series(p.ytd({"2025-01": 5.0, "2025-02": 7.0, "2025-12": 1.0}).items())
    with pytest.raises(ValueError, match="do not run from January"):
        nso.ytd_to_monthly(cumulative)

    flows = {"2025-01": 5.0, "2025-02": 0.0, "2025-03": 2.5, "2026-01": 4.0, "2026-02": 1.0}
    totals = series(p.ytd(flows).items())
    monthly = nso.ytd_to_monthly(totals)
    assert monthly.to_dict() == flows  # January is its own total, then differences
    for year in ("2025", "2026"):  # a year's flows add up to its last total
        in_year = monthly[monthly.index.str.startswith(year)]
        assert in_year.sum() == pytest.approx(totals[totals.index.str.startswith(year)].iloc[-1])


def test_nso_rejects_a_falling_year_to_date_total():
    falling = series([("2026-01", 10.0), ("2026-02", 9.0)])
    with pytest.raises(ValueError, match="falls"):
        nso.ytd_to_monthly(falling)


def test_nso_commodity_flows_in_the_parse():
    out = nso.parse(p.nso_payload())
    coal = out["nso_export_coal_kt"]
    assert (coal == 100.0).all() and len(coal) == len(p.MONTHS)
    assert (out["nso_export_gold_kusd"] == 5000.0).all()


def test_nso_checks_that_a_code_still_means_the_same_thing():
    payload = p.nso_payload()
    labels = payload["fx"]["dimension"][nso.CURRENCY]["category"]["label"]
    labels["2"] = " EUR"
    with pytest.raises(ValueError, match="expected 'USD'"):
        nso.parse(payload)


def test_nso_reads_the_sparse_json_stat_form():
    dense = p.nso_exports(12.5, months=["2026-07", "2026-08"])
    sparse = {**dense, "value": {"0": 12.5, "1": 12.5}}
    assert nso.table(sparse)["value"].tolist() == nso.table(dense)["value"].tolist()
    sparse["value"] = {"0": 12.5}
    assert nso.table(sparse)["value"].tolist()[1] is None


def test_nso_new_base_year_becomes_an_unknown_series():
    bases = {**p.BASES, "3": "2026=100"}
    out = nso.parse({**p.nso_payload(), "cpi_mom": p.nso_cpi(0.5, bases=bases)})
    assert "nso_cpi_mom_b2026" in out and "nso_cpi_mom_b2026" not in SERIES


# -- Pink Sheet ----------------------------------------------------------------------------
def test_pinksheet_reads_monthly_prices_by_name():
    payload = {"url": p.XLSX_URL, "xlsx": p.pinksheet_xlsx(missing=2)}
    out = pinksheet.parse(payload)
    assert set(out) == ids("pinksheet")
    assert out["pinksheet_copper"]["2026-08"] == 9000.0
    assert len(out["pinksheet_copper"]) == len(p.MONTHS)
    # "…" is missing, so the coal series starts two months later
    assert out["pinksheet_coal_australian"].index[0] == p.MONTHS[2]
    assert pinksheet.info(payload) == {"updated_on": "2026-09-02", "url": p.XLSX_URL}


def test_pinksheet_checks_units():
    columns = [("Copper", "($/kg)", 9.0) if c[0] == "Copper" else c for c in p.PINK_COLUMNS]
    xlsx = p.pinksheet_xlsx(columns=columns)
    with pytest.raises(ValueError, match="Copper"):
        pinksheet.parse({"url": p.XLSX_URL, "xlsx": xlsx})


def test_pinksheet_link_scraper():
    assert pinksheet.find_link(p.commodity_page()) == p.XLSX_URL
    with pytest.raises(ValueError, match="no link"):
        pinksheet.find_link("<html><a href='/en/research/commodity-markets'>prices</a></html>")


# -- IMF -----------------------------------------------------------------------------------
def test_sdmx_filters_by_transformation_and_drops_1900_rows():
    text = p.sdmx_er("MNG", avg=3500.0, eop=3510.0, months=["2026-07", "2026-08"])
    avg = imf_sdmx.sdmx_series(text, TYPE_OF_TRANSFORMATION="PA_RT")
    eop = imf_sdmx.sdmx_series(text, TYPE_OF_TRANSFORMATION="EOP_RT")
    assert avg.to_dict() == {"2026-07": 3500.0, "2026-08": 3500.0}  # no 1900-01 row
    assert eop.to_dict() == {"2026-07": 3510.0, "2026-08": 3510.0}


def test_sdmx_parse_gives_every_series():
    payload = {
        "er_mng": p.sdmx_er("MNG", 3500.0, 3500.0),
        "cpi_mng": p.sdmx_cpi(5.0, 0.5),
        "pcps": p.sdmx_pcps({"PCOPP": 9000.0, "PGOLD": 2000.0, "PZINC": 2500.0}),
        "er_chn": p.sdmx_er("CHN", 7.1, 7.2),
    }
    out = imf_sdmx.parse(payload)
    assert set(out) == ids("imf_sdmx")
    assert (out["imf_cpi_yoy"] == 5.0).all()  # the IX rows are not mixed in
    assert (out["imf_cpi_mom"] == 0.5).all()
    assert (out["imf_pcps_gold"] == 2000.0).all()
    assert (out["imf_cnyusd_monthly_avg"] == 7.1).all()


def test_sdmx_complains_about_a_missing_column():
    with pytest.raises(ValueError, match="no column"):
        imf_sdmx.sdmx_series("A,B\n1,2\n", TYPE_OF_TRANSFORMATION="PA_RT")


def test_datamapper_reads_mongolia_and_china_from_an_all_countries_answer():
    payload = {
        code: p.datamapper(code, {"2025": 6.8, "2026": 5.3}, {"2025": 5.0, "2026": 4.2})
        for code in imf_datamapper.INDICATORS
    }
    out = imf_datamapper.parse(payload)
    assert set(out) == ids("imf_datamapper")
    assert out["imf_weo_gdp_growth"].to_dict() == {"2025": 6.8, "2026": 5.3}
    assert out["imf_weo_china_gdp_growth"].to_dict() == {"2025": 5.0, "2026": 4.2}
    assert imf_datamapper.info(payload) == {"weo_vintage": "April 2026"}
    del payload["BCA_NGDPD"]["values"]["BCA_NGDPD"]["MNG"]
    with pytest.raises(ValueError, match="no values for MNG"):
        imf_datamapper.parse(payload)


# -- WDI and FRED --------------------------------------------------------------------------
def test_wdi_drops_nulls_and_insists_on_one_page():
    answer = p.wdi_answer({"2023": 7.4, "2024": 5.0, "2025": None})
    payload = dict.fromkeys(wdi.SERIES, answer)
    out = wdi.parse(payload)
    assert set(out) == ids("wdi")
    assert out["wdi_gdp_growth"].to_dict() == {"2023": 7.4, "2024": 5.0}
    payload["wdi_fdi_pct_gdp"] = p.wdi_answer({"2024": 1.0}, pages=2)
    with pytest.raises(ValueError, match="2 pages"):
        wdi.parse(payload)
    payload["wdi_fdi_pct_gdp"] = [{"message": [{"id": "120", "value": "Invalid value"}]}]
    with pytest.raises(ValueError, match="meta, rows"):
        wdi.parse(payload)


def test_fred_reads_dots_as_missing():
    payload = {
        "fred_usd_broad_index": p.fred_csv("TWEXBGSMTH", {"2026-07": 118.9, "2026-08": None}),
        "fred_cnyusd_monthly_avg": p.fred_csv("EXCHUS", {"2026-07": 7.1, "2026-08": 7.0}),
    }
    out = fred.parse(payload)
    assert set(out) == ids("fred")
    assert out["fred_usd_broad_index"].to_dict() == {"2026-07": 118.9}
    assert out["fred_cnyusd_monthly_avg"].index.tolist() == ["2026-07", "2026-08"]
    payload["fred_cnyusd_monthly_avg"] = "<html>error</html>"
    with pytest.raises(ValueError, match="header"):
        fred.parse(payload)


def test_every_series_index_is_plain_date_strings():
    out = fred.parse({sid: p.fred_csv(fid, {"2026-08": 1.0}) for sid, fid in fred.SERIES.items()})
    assert isinstance(out["fred_usd_broad_index"], pd.Series)
    assert all(isinstance(d, str) for d in out["fred_usd_broad_index"].index)
