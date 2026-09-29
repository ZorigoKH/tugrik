"""The build and the validator, on a synthetic store (see ``store.py``): determinism,
atomic writes, stale sources and fallbacks, what is offered for download, and what the
validator rejects."""

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
import store as st

from pipeline import build as b
from pipeline import validate as v
from pipeline.fetch import to_csv
from pipeline.registry import SERIES
from pipeline.sources import series


def quiet(*args):
    pass


@pytest.fixture(scope="module")
def synthetic():
    return st.make()


@pytest.fixture
def store(tmp_path, synthetic):
    return st.write(tmp_path / "data", synthetic)


def run(store: Path, root: Path, today: date = st.TODAY) -> dict:
    return b.build(store, root / "web" / "data", root / "web" / "csv", today=today, log=quiet)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory, synthetic):
    root = tmp_path_factory.mktemp("built")
    data = st.write(root / "data", synthetic)
    run(data, root)
    return root / "web" / "data"


# -- the build -----------------------------------------------------------------------------
def test_build_writes_valid_data(built):
    assert v.validate(built) == []
    assert sorted(p.name for p in built.iterdir()) == sorted(f"{n}.json" for n in v.FILES)
    meta = json.loads((built / "meta.json").read_text())
    assert meta["generated_at"] == st.TODAY.isoformat()
    assert meta["stale"] == [] and meta["through"]["fx"] == st.LAST_MONTH
    assert meta["through"]["weo_vintage"] == "April 2026"
    copper = json.loads((built / "copper.json").read_text())
    assert [len(x["copper"]) for x in copper["samples"]] == [13] * 5
    assert copper["takeaway"] and copper["takeaway_fit"]


def test_two_builds_give_identical_bytes(tmp_path, store):
    run(store, tmp_path)
    first = snapshot(tmp_path / "web")
    assert not list((tmp_path / "web").glob(".tugrik-build-*"))  # the stage is cleaned up
    run(store, tmp_path)
    assert snapshot(tmp_path / "web") == first


def test_generated_at_moves_only_with_the_content(tmp_path, store, synthetic):
    run(store, tmp_path)
    later = st.TODAY + timedelta(days=2)
    meta = run(store, tmp_path, today=later)
    assert meta["generated_at"] == st.TODAY.isoformat()  # nothing else changed
    copper = synthetic["pinksheet_copper"]
    changed = series([*copper.items()][:-1] + [(copper.index[-1], copper.iloc[-1] * 1.2)])
    (store / "pinksheet_copper.csv").write_bytes(to_csv(changed))
    meta = run(store, tmp_path, today=later)
    assert meta["generated_at"] == later.isoformat()


def test_csv_downloads_only_for_redistributable_series(tmp_path, store):
    run(store, tmp_path)
    names = {p.name for p in (tmp_path / "web" / "csv").iterdir()}
    for sid, spec in SERIES.items():
        assert (f"{sid}.csv" in names) == spec.redistribute, sid
    assert not any(n.startswith("bom_") or n.startswith("comtrade") for n in names)
    assert {"derived_usdmnt_monthly_avg.csv", "derived_cpi_mom.csv", "fred_twexbmth.csv"} <= names
    sources = json.loads((tmp_path / "web" / "data" / "sources.json").read_text())
    links = {r["csv"] for src in sources for r in src["series"] if r["csv"]}
    assert links == {f"csv/{n}" for n in names}
    # a CSV no longer published is removed
    (tmp_path / "web" / "csv" / "old_series.csv").write_text("date,value\n")
    run(store, tmp_path)
    assert not (tmp_path / "web" / "csv" / "old_series.csv").exists()


def test_a_failed_source_is_stale_and_the_build_succeeds(tmp_path, synthetic):
    data = st.write(tmp_path / "data", synthetic, st.status({"pinksheet": "HTTP 503"}))
    meta = run(data, tmp_path)
    assert meta["stale"] == ["pinksheet"]
    assert {x["id"]: x["status"] for x in meta["sources"]}["pinksheet"] == "stale"
    overview = json.loads((tmp_path / "web" / "data" / "overview.json").read_text())
    assert {t["id"]: t["status"] for t in overview["tiles"]}["copper"] == "stale"


def test_old_data_is_stale_by_age(tmp_path, store):
    meta = run(store, tmp_path, today=st.TODAY + timedelta(days=90))
    assert {"bom", "nso", "pinksheet", "imf_sdmx", "fred"} <= set(meta["stale"])
    assert "wdi" not in meta["stale"]


def test_stale_nso_falls_back_to_the_imf_cpi(tmp_path, synthetic):
    data = dict(synthetic)
    for sid in ("nso_cpi_mom_b2023", "nso_cpi_mom_b2020", "nso_cpi_yoy_b2023", "nso_cpi_yoy_b2020"):
        data[sid] = data[sid].loc[:"2026-06"]
    store = st.write(tmp_path / "data", data, st.status({"nso": "timed out"}))
    meta = run(store, tmp_path)
    assert {x["id"]: x["status"] for x in meta["sources"]}["nso"] == "fallback"
    assert meta["through"]["cpi"] == st.LAST_MONTH  # July and August from the IMF
    overview = json.loads((tmp_path / "web" / "data" / "overview.json").read_text())
    cpi = next(t for t in overview["tiles"] if t["id"] == "cpi")
    assert cpi["status"] == "fallback" and cpi["period"] == st.LAST_MONTH


def test_a_store_without_what_the_models_need_writes_nothing(tmp_path, store):
    (store / "pinksheet_copper.csv").unlink()
    with pytest.raises(b.BuildError, match="model inputs"):
        run(store, tmp_path)
    assert not (tmp_path / "web").exists()
    assert (
        b.main(["--store", str(store), "--out", str(tmp_path / "o"), "--csv", str(tmp_path / "c")])
        == 1
    )


def test_main_and_saved_inputs(tmp_path, store):
    args = ["--store", str(store), "--out", str(tmp_path / "o"), "--csv", str(tmp_path / "c")]
    assert b.main([*args, "--today", "2026-09-28", "--save-inputs", str(tmp_path / "in")]) == 0
    inputs = b.read_inputs(tmp_path / "in")
    assert "derived_usdmnt_monthly_avg" in inputs and not any(k.startswith("bom_") for k in inputs)
    assert v.main([str(tmp_path / "o")]) == 0


def test_the_consensus_must_stay_near_the_daily_rate(tmp_path, synthetic):
    data = dict(synthetic)
    for name in ("bom", "nso", "imf"):  # every published average 1% high in March 2015
        sid = f"{name}_usdmnt_monthly_avg"
        data[sid] = data[sid].copy()
        data[sid]["2015-03"] *= 1.01
    store = st.write(tmp_path / "data", data)
    with pytest.raises(b.BuildError, match="consensus exchange rate for 2015-03"):
        run(store, tmp_path)
    assert not (tmp_path / "web").exists()


def test_page_changes_are_percent_changes():
    x = series([("2024-12", 100.0), ("2025-01", 104.0), ("2025-12", 110.0)])
    change = b.change_pct(x, 12)
    assert list(change.index) == ["2025-12"] and change["2025-12"] == pytest.approx(10.0)
    annual = b.change_pct_annual(series([("2020", 50.0), ("2021", 75.5)]))
    assert annual.to_dict() == {"2021": pytest.approx(51.0)}


def test_a_forecast_year_that_has_an_actual_is_left_out(synthetic):
    ahead = b.weo(synthetic, "imf_weo_gdp_growth", "April 2026", "gdp_growth_pct")
    assert ahead["years"][0] == "2026"
    # WDI has 2026 while the WEO is still April 2026's: 2026 is actual, not forecast
    later = b.weo(synthetic, "imf_weo_gdp_growth", "April 2026", "gdp_growth_pct", after="2026")
    assert later["years"][0] == "2027" and len(later["gdp_growth_pct"]) == len(later["years"])


def test_wdi_is_not_stale_while_fdi_is_on_its_usual_lag(tmp_path, store):
    meta = run(store, tmp_path, today=date(2027, 6, 30))  # FDI and current account end 2024
    assert "wdi" not in meta["stale"]


def test_superseded_cpi_bases_are_not_stale(synthetic):
    assert b.superseded("nso_cpi_mom_b2015", synthetic)
    assert not b.superseded("nso_cpi_mom_b2023", synthetic)
    assert not b.series_stale("nso_cpi_mom_b2015", synthetic, st.TODAY)


# -- the validator -------------------------------------------------------------------------
@pytest.fixture
def copy(tmp_path, built):
    target = tmp_path / "data"
    shutil.copytree(built, target)
    return target


def edit(directory: Path, name: str, change) -> None:
    path = directory / f"{name}.json"
    obj = json.loads(path.read_text())
    change(obj)
    path.write_text(json.dumps(obj))


def test_validate_rejects_a_missing_field(copy):
    edit(copy, "copper", lambda o: o.pop("controls"))
    assert "copper: missing controls" in v.validate(copy)


def test_validate_rejects_nan(copy):
    path = copy / "growth.json"
    path.write_text(path.read_text().replace('"r2": ', '"r2": NaN, "x": ', 1))
    errors = v.validate(copy)
    assert len(errors) == 1 and "NaN" in errors[0]


def test_validate_rejects_a_gap(copy):
    edit(copy, "prices", lambda o: [o["context"][k].pop(5) for k in o["context"]])
    assert any("does not follow" in e for e in v.validate(copy))


def test_validate_rejects_a_takeaway_that_disagrees_with_its_numbers(copy):
    def flip(o):
        h12 = o["samples"][0]["copper"][12]
        h12["est"], h12["lo"], h12["hi"] = -h12["est"], -h12["hi"], -h12["lo"]

    edit(copy, "copper", flip)
    assert any("copper.takeaway: does not match its numbers" in e for e in v.validate(copy))


def test_validate_rejects_broken_invariants(copy):
    def bad_interval(o):
        o["specs"][1]["cum"][3]["lo"] = o["specs"][1]["cum"][3]["est"] + 1

    edit(copy, "prices", bad_interval)
    edit(copy, "growth", lambda o: o["annual"][3]["weights"].update(coal=0.9))
    edit(copy, "copper", lambda o: o["samples"][2]["copper"].pop())

    def identity(o):
        row = next(r for r in o["annual"] if r["dlog_value"] is not None)
        row["dlog_unit_value"] += 0.001

    edit(copy, "coal", identity)
    errors = "\n".join(v.validate(copy))
    assert "prices.specs[1].cum[3]: not lo <= est <= hi" in errors
    assert "weights sum to" in errors or "weights must be" in errors
    assert "expected 13 horizons" in errors
    assert "dlog value != dlog volume + dlog unit value" in errors


def test_validate_checks_coal_changes_against_their_levels(copy):
    def shift(o):  # a consistent identity, but tonnes that do not match the levels
        row = next(r for r in o["annual"] if r["dlog_volume"] is not None)
        row["dlog_volume"] = round(row["dlog_volume"] + 1, 6)
        row["dlog_unit_value"] = round(row["dlog_value"] - row["dlog_volume"], 6)

    edit(copy, "coal", shift)
    errors = "\n".join(v.validate(copy))
    assert "dlog_volume is" in errors and "log change of volume_mt" in errors
    assert "dlog value != dlog volume + dlog unit value" not in errors


def test_validate_rejects_unrounded_numbers_and_a_changed_card(copy):
    edit(copy, "growth", lambda o: o["fit"].update(r2=0.123456789))
    edit(copy, "overview", lambda o: o["cards"][0].update(takeaway="Copper is great."))
    errors = "\n".join(v.validate(copy))
    assert "growth.fit.r2: bad value" in errors
    assert "the copper card's takeaway differs" in errors
    assert v.main([str(copy)]) == 1
