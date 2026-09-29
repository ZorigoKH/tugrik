"""The fetch stage's safety rules, offline.

Most tests use four fake sources (``a`` to ``d``) with one or two monthly series each and a
small registry; the last ones run the real source modules against a fake HTTP transport
serving the synthetic payloads of :mod:`payloads`.
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

import payloads as p
import pytest

from pipeline import fetch as f
from pipeline.http import FetchError, Http
from pipeline.registry import SERIES, Revision, Series
from pipeline.sources import nso, pinksheet, series

TODAY = date(2026, 9, 28)
FX = Revision("relative", 0.001, recent=2)
MONTHS = p.MONTHS  # 2024-01 .. 2026-08


def spec(sid: str, source: str, revision: Revision = FX, bounds=(0.0, 1e6), freq="M") -> Series:
    return Series(sid, source, sid, freq, "units", bounds, revision, 60, True)


REGISTRY = {
    s.id: s
    for s in (
        spec("a_x", "a"),
        spec("a_y", "a"),
        spec("b_x", "b"),
        spec("c_x", "c"),
        spec("d_x", "d", revision=Revision("exact"), freq="E"),
    )
}


class Source:
    """A fake source: ``fetch`` returns ``data`` ({series id: {date: value}}) or raises."""

    def __init__(self, data=None, error: Exception | None = None):
        self.data, self.error = data, error

    def fetch(self, http):
        if self.error is not None:
            raise self.error
        return self.data

    def parse(self, payload):
        return {sid: series(values.items()) for sid, values in payload.items()}


def sources(value: float = 100.0, months: list[str] = MONTHS) -> dict[str, Source]:
    out = {
        name: Source({sid: dict.fromkeys(months, value) for sid in REGISTRY if sid[0] == name})
        for name in "abc"
    }
    out["d"] = Source({"d_x": {"2024-01-10": 13.0, "2025-03-14": 12.0}})
    return out


def run(store, srcs, **kwargs) -> tuple[int, list[str]]:
    logs: list[str] = []
    kwargs.setdefault("today", TODAY)
    code = f.run(store, sources=srcs, registry=REGISTRY, http=object(), log=logs.append, **kwargs)
    return code, logs


def snapshot(store: Path) -> dict[str, bytes]:
    return {x.name: x.read_bytes() for x in sorted(Path(store).glob("*")) if x.is_file()}


@pytest.fixture
def store(tmp_path) -> Path:
    """A store after one successful run."""
    code, _ = run(tmp_path, sources())
    assert code == 0
    return tmp_path


# -- writing and rerunning -----------------------------------------------------------------
def test_first_run_writes_every_series_and_the_status(store):
    assert set(snapshot(store)) == {f"{sid}.csv" for sid in REGISTRY} | {"status.json"}
    assert (store / "a_x.csv").read_text().splitlines()[:2] == ["date,value", "2024-01,100.0"]
    status = f.read_status(store)
    assert status["sources"]["a"]["status"] == "ok"
    assert status["sources"]["a"]["last_obs"] == "2026-08"
    assert status["sources"]["a"]["last_changed"] == "2026-09-28"
    assert status["series"]["a_x"] == {
        "source": "a",
        "first": "2024-01",
        "last_obs": "2026-08",
        "rows": 32,
        "last_changed": "2026-09-28",
    }
    assert not list(store.glob(".tmp-*"))


def test_a_rerun_on_the_same_data_changes_no_bytes(store):
    before = snapshot(store)
    code, logs = run(store, sources(), today=date(2026, 10, 3))  # even days later
    assert code == 0
    assert snapshot(store) == before
    assert "a: ok, 2 series through 2026-08, 0 files changed" in logs


def test_new_data_updates_only_the_files_that_changed(store):
    before = snapshot(store)
    srcs = sources()
    srcs["b"].data["b_x"]["2026-09"] = 101.0
    code, _ = run(store, srcs, today=date(2026, 10, 3))
    assert code == 0
    after = snapshot(store)
    assert after["b_x.csv"].endswith(b"2026-09,101.0\n")
    assert {name for name in after if after[name] != before[name]} == {"b_x.csv", "status.json"}
    status = f.read_status(store)
    assert status["sources"]["b"]["last_changed"] == "2026-10-03"
    assert status["sources"]["a"]["last_changed"] == "2026-09-28"


# -- failing sources -----------------------------------------------------------------------
def test_a_fetch_that_raises_leaves_the_store_byte_identical(store):
    before = snapshot(store)
    srcs = sources()
    srcs["a"] = Source(error=RuntimeError("boom"))
    code, logs = run(store, srcs)
    assert code == 0
    after = snapshot(store)
    assert {k: v for k, v in after.items() if k != "status.json"} == {
        k: v for k, v in before.items() if k != "status.json"
    }
    status = f.read_status(store)["sources"]["a"]
    assert status["status"] == "stale"
    assert status["error"] == "fetch failed: RuntimeError: boom"
    assert status["last_obs"] == "2026-08" and status["last_changed"] == "2026-09-28"
    assert any(line.startswith("::warning::a is stale") for line in logs)


def test_one_failing_source_is_stale_and_the_others_still_update(store):
    srcs = sources(value=100.0, months=[*MONTHS, "2026-09"])
    srcs["c"] = Source(error=FetchError("GET https://example.org: HTTP 403"))
    code, _ = run(store, srcs)
    assert code == 0
    status = f.read_status(store)["sources"]
    assert status["c"]["status"] == "stale" and "HTTP 403" in status["c"]["error"]
    assert status["a"]["status"] == "ok" and status["a"]["last_obs"] == "2026-09"
    assert (store / "c_x.csv").read_text().splitlines()[-1] == "2026-08,100.0"


def test_a_stale_source_recovers(store):
    srcs = sources()
    srcs["a"] = Source(error=RuntimeError("boom"))
    run(store, srcs)
    code, _ = run(store, sources())
    assert code == 0
    status = f.read_status(store)["sources"]["a"]
    assert status["status"] == "ok" and status["error"] is None


def test_three_failing_sources_abort_and_write_nothing(store):
    before = snapshot(store)
    srcs = sources(value=100.0, months=[*MONTHS, "2026-09"])
    for name in "abc":
        srcs[name] = Source(error=RuntimeError("down"))
    code, logs = run(store, srcs)
    assert code == 1
    assert snapshot(store) == before
    assert any("fetch aborted, nothing written" in line for line in logs)


def test_a_failure_on_the_first_run_aborts(tmp_path):
    srcs = sources()
    srcs["d"] = Source(error=RuntimeError("down"))
    code, logs = run(tmp_path / "data", srcs)
    assert code == 1
    assert not (tmp_path / "data").exists()
    assert any("d failed with no previous data" in line for line in logs)


def test_only_fetches_the_named_sources(store):
    srcs = sources(value=100.0, months=[*MONTHS, "2026-09"])
    srcs["a"] = Source(error=AssertionError("must not be fetched"))
    code, _ = run(store, srcs, only=["b"])
    assert code == 0
    status = f.read_status(store)["sources"]
    assert status["b"]["last_obs"] == "2026-09" and status["a"]["last_obs"] == "2026-08"


# -- sanity --------------------------------------------------------------------------------
def breaking(change):
    """Sources whose ``a`` data has been modified by ``change(data)``."""
    srcs = sources()
    change(srcs["a"].data)
    return srcs


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d["a_x"].pop("2025-06"), "1 missing months inside, from 2025-06"),
        (lambda d: d["a_x"].update({"2026-08": 2e6}), "values outside [0, 1e+06]"),
        (lambda d: d["a_x"].update({"2026-13": 1.0}), "malformed date '2026-13'"),
        (lambda d: d["a_x"].update({"2026-08": float("inf")}), "not finite"),
        (lambda d: d.update({"a_x": {}}), "a_x: no observations"),
        (lambda d: d.pop("a_y"), "series missing from the download: a_y"),
        (lambda d: d.update({"a_z": {"2026-01": 1.0}}), "registry does not know: a_z"),
    ],
)
def test_sanity_failures_mark_the_source_stale(store, change, problem):
    before = snapshot(store)
    code, _ = run(store, breaking(change))
    assert code == 0
    status = f.read_status(store)["sources"]["a"]
    assert status["status"] == "stale"
    assert problem in status["error"]
    assert snapshot(store)["a_x.csv"] == before["a_x.csv"]


def test_a_series_may_not_end_earlier_or_lose_rows(store):
    code, _ = run(store, breaking(lambda d: d["a_x"].pop("2026-08")))
    assert (
        "a_x: ends 2026-07, before the stored 2026-08"
        in f.read_status(store)["sources"]["a"]["error"]
    )
    code, _ = run(store, breaking(lambda d: [d["a_y"].pop(m) for m in MONTHS[:2]]))
    assert "a_y: 30 rows, down from 32" in f.read_status(store)["sources"]["a"]["error"]


def test_losing_one_row_is_allowed(store):
    code, _ = run(store, breaking(lambda d: d["a_y"].pop(MONTHS[0])))
    assert code == 0 and f.read_status(store)["sources"]["a"]["status"] == "ok"


def test_bounds_can_start_at_a_date():
    s = replace(spec("cpi", "a", bounds=(-10.0, 30.0)), bounds_from="1996-01")
    old_hyperinflation = series([("1995-12", 32.9), ("1996-01", 1.0)])
    assert f.sanity(s, old_hyperinflation, None) == []
    assert f.sanity(s, series([("1996-01", 31.0)]), None) != []


def test_the_pinksheet_release_must_be_recent():
    ids = [sid for sid in SERIES if SERIES[sid].source == "pinksheet"]
    parsed = pinksheet.parse({"url": p.XLSX_URL, "xlsx": p.pinksheet_xlsx()})
    old = {"updated_on": "2026-07-01"}
    problems, _ = f.check_source("pinksheet", parsed, ids, SERIES, {}, old, TODAY, ())
    assert problems == ["the release is dated 2026-07-01, 89 days ago"]
    fresh = {"updated_on": "2026-09-02"}
    assert f.check_source("pinksheet", parsed, ids, SERIES, {}, fresh, TODAY, ()) == ([], 0)


def test_a_new_nso_cpi_base_code_is_rejected():
    bases = {**p.BASES, "3": "2026=100"}
    parsed = nso.parse({**p.nso_payload(), "cpi_yoy": p.nso_cpi(5.0, bases=bases)})
    ids = [sid for sid in SERIES if SERIES[sid].source == "nso"]
    problems, _ = f.check_source("nso", parsed, ids, SERIES, {}, {}, TODAY, ["nso"])
    assert problems[0].startswith("series the registry does not know: nso_cpi_yoy_b2026")
    assert "CPI splice need a human" in problems[0]


# -- the revision guard --------------------------------------------------------------------
def test_a_revision_beyond_tolerance_is_rejected_and_accept_lets_it_through(store):
    revised = breaking(lambda d: d["a_x"].update({"2025-01": 100.2}))  # 0.2% > 0.1%
    code, _ = run(store, revised)
    assert code == 0
    status = f.read_status(store)["sources"]["a"]
    assert status["status"] == "stale"
    assert "1 revisions beyond tolerance (a_x 2025-01: 100 -> 100.2)" in status["error"]
    assert "--accept-revisions a" in status["error"]
    assert "2025-01,100.0" in (store / "a_x.csv").read_text()

    code, _ = run(store, revised, accept=["a"])
    assert code == 0
    status = f.read_status(store)["sources"]["a"]
    assert status["status"] == "ok" and status["revisions"] == 1
    assert "2025-01,100.2" in (store / "a_x.csv").read_text()


def test_small_and_recent_revisions_pass(store):
    small = breaking(lambda d: d["a_x"].update({"2025-01": 100.05, "2026-07": 150.0}))
    code, _ = run(store, small)
    assert code == 0
    status = f.read_status(store)["sources"]["a"]
    assert status["status"] == "ok" and status["revisions"] == 2


def test_revisions_count_stays_until_the_data_change_again(store):
    run(store, breaking(lambda d: d["a_x"].update({"2026-08": 101.0})))
    assert f.read_status(store)["sources"]["a"]["revisions"] == 1
    run(store, breaking(lambda d: d["a_x"].update({"2026-08": 101.0})))
    assert f.read_status(store)["sources"]["a"]["revisions"] == 1


def test_a_past_policy_decision_may_not_change():
    decisions = spec("rate", "d", revision=Revision("exact"), freq="E")
    old = series([("2024-01-10", 13.0), ("2025-03-14", 12.0)])
    assert f.revisions(decisions, series([*old.items(), ("2026-09-17", 12.5)]), old) == ([], 0)
    changed = series([("2024-01-10", 13.0), ("2025-03-14", 11.5)])
    assert f.revisions(decisions, changed, old) == (["rate 2025-03-14: 12 -> 11.5"], 1)
    removed = series([("2025-03-14", 12.0)])
    assert f.revisions(decisions, removed, old) == (["rate 2024-01-10: 13 -> removed"], 1)


def test_annual_revisions_are_accepted_and_counted():
    annual = spec("gdp", "w", revision=Revision("accept"), freq="A")
    old = series([("2023", 7.4), ("2024", 5.0)])
    assert f.revisions(annual, series([("2023", 7.2), ("2024", 4.9), ("2025", 6.8)]), old) == (
        [],
        2,
    )


def test_cpi_revisions_are_measured_in_points():
    cpi = spec("cpi", "n", revision=Revision("absolute", 0.05, recent=3))
    old = series([(m, 1.0) for m in MONTHS])
    ok = series([(m, 1.04 if m == "2025-01" else 1.0) for m in MONTHS])
    bad = series([(m, 1.1 if m == "2025-01" else 1.0) for m in MONTHS])
    assert f.revisions(cpi, ok, old) == ([], 1)
    assert f.revisions(cpi, bad, old)[0] == ["cpi 2025-01: 1 -> 1.1"]


# -- cross-source checks -------------------------------------------------------------------
def fx(value: float, months: list[str]) -> dict:
    daily = p.bom_payload(3500.0, months)["daily"]["data"]
    return {
        "bom_usdmnt_daily": series((r["RATE_DATE"], 3500.0) for r in daily),
        "bom_usdmnt_monthly_avg": series((m, 3500.0) for m in months),
        "nso_usdmnt_monthly_avg": series((m, value) for m in months),
    }


def split(data: dict) -> dict:
    """{series id: series} -> {source: {series id: series}}."""
    out: dict = {}
    for sid, s in data.items():
        out.setdefault(SERIES[sid].source, {})[sid] = s
    return out


def test_a_cross_check_rejects_the_side_that_changed():
    stored = fx(3500.0, MONTHS[:-1])
    new = split(fx(3500.0, MONTHS))  # both sides add August...
    new["nso"]["nso_usdmnt_monthly_avg"] = series((m, 3500.0) for m in MONTHS[:-1])
    assert f.cross_check(new, stored, SERIES, print) == {}
    # ...but NSO's August is 3% off: both changed, so the checked side (NSO) goes
    new["nso"]["nso_usdmnt_monthly_avg"] = series(
        (m, 3605.0 if m == MONTHS[-1] else 3500.0) for m in MONTHS
    )
    rejected = f.cross_check(new, stored, SERIES, print)
    assert list(rejected) == ["nso"]
    assert "nso_usdmnt_monthly_avg 2026-08 = 3605 is 3.00% from" in rejected["nso"]


def test_a_cross_check_rejects_the_reference_when_only_it_changed():
    stored = fx(3500.0, MONTHS)
    daily = stored["bom_usdmnt_daily"].copy()
    daily[daily.index.str.startswith("2026-08")] = 3700.0  # the BoM revises August's rates
    new = split({**stored, "bom_usdmnt_daily": daily})  # the averages are unchanged
    rejected = f.cross_check(new, stored, SERIES, print)
    assert list(rejected) == ["bom"]


def test_a_disagreement_already_in_the_store_is_only_noted():
    stored = fx(3605.0, MONTHS)
    notes: list[str] = []
    assert f.cross_check({}, stored, SERIES, notes.append) == {}
    assert len(notes) == 1 and "nothing new to reject" in notes[0]


def test_without_the_bom_daily_rate_the_averages_check_each_other():
    """The BoM's fetch failed: its stored daily rate ends in August, so September's
    averages are checked against each other."""
    stored = {**fx(3500.0, MONTHS), "imf_usdmnt_monthly_avg": series((m, 3500.0) for m in MONTHS)}
    september = [*MONTHS, "2026-09"]

    def average(value):
        return series((m, value if m == "2026-09" else 3500.0) for m in september)

    new = {
        "nso": {"nso_usdmnt_monthly_avg": average(3850.0)},  # 10% off
        "imf_sdmx": {"imf_usdmnt_monthly_avg": average(3500.0)},
    }
    rejected = f.cross_check(new, stored, SERIES, print)
    # both are new and nothing says which is right, so neither goes in
    assert sorted(rejected) == ["imf_sdmx", "nso"]
    assert "2026-09 = 3850 is 10.00% from the median of the other averages 3500" in rejected["nso"]
    # the IMF's September came in an earlier run: only the newer side, NSO's, is rejected
    stored["imf_usdmnt_monthly_avg"] = average(3500.0)
    assert list(f.cross_check(new, stored, SERIES, print)) == ["nso"]
    # and they agree: nothing is rejected
    new["nso"]["nso_usdmnt_monthly_avg"] = average(3501.0)
    assert f.cross_check(new, stored, SERIES, print) == {}


FX_REGISTRY = {
    sid: SERIES[sid]
    for sid in (
        "bom_usdmnt_daily",
        "bom_usdmnt_monthly_avg",
        "nso_usdmnt_monthly_avg",
        "imf_usdmnt_monthly_avg",
    )
}


def fx_sources(months: list[str], imf: dict[str, float] | None = None) -> dict[str, Source]:
    """The BoM, NSO and the IMF all publishing 3500 MNT per USD, except the IMF's ``imf``
    months."""
    data = {**fx(3500.0, months), "imf_usdmnt_monthly_avg": series((m, 3500.0) for m in months)}
    for m, value in (imf or {}).items():
        data["imf_usdmnt_monthly_avg"][m] = value
    return {
        name: Source({sid: dict(s.items()) for sid, s in part.items()})
        for name, part in split(data).items()
    }


def fx_run(store, srcs, **kwargs) -> int:
    kwargs.setdefault("today", TODAY)
    return f.run(store, sources=srcs, registry=FX_REGISTRY, http=object(), log=print, **kwargs)


def test_an_fx_defect_in_an_older_month_does_not_hold_a_source_back(tmp_path):
    assert fx_run(tmp_path, fx_sources(MONTHS)) == 0
    september = [*MONTHS, "2026-09"]
    bad = {"2026-09": 3535.0}  # 1% above the daily mean
    assert fx_run(tmp_path, fx_sources(september, bad), today=date(2026, 10, 3)) == 0
    status = f.read_status(tmp_path)["sources"]["imf_sdmx"]
    assert status["status"] == "stale"
    assert "imf_usdmnt_monthly_avg 2026-09 = 3535 is 1.00% from the BoM daily" in status["error"]
    assert "rerun with --accept-revisions imf_sdmx" in status["error"]
    # a month later September is no longer the latest: the IMF's update goes in
    october = [*september, "2026-10"]
    assert fx_run(tmp_path, fx_sources(october, bad), today=date(2026, 11, 3)) == 0
    assert f.read_status(tmp_path)["sources"]["imf_sdmx"]["status"] == "ok"
    assert "2026-09,3535.0" in (tmp_path / "imf_usdmnt_monthly_avg.csv").read_text()


def test_accept_revisions_waives_a_cross_source_check(tmp_path):
    assert fx_run(tmp_path, fx_sources(MONTHS)) == 0
    september = fx_sources([*MONTHS, "2026-09"], {"2026-09": 3535.0})
    assert fx_run(tmp_path, september, today=date(2026, 10, 3), accept=["imf_sdmx"]) == 0
    assert f.read_status(tmp_path)["sources"]["imf_sdmx"]["status"] == "ok"
    assert "2026-09,3535.0" in (tmp_path / "imf_usdmnt_monthly_avg.csv").read_text()


def test_the_other_cross_checks():
    months = MONTHS
    base = {
        "pinksheet_copper": series((m, 9000.0) for m in months),
        "imf_pcps_copper": series((m, 9000.0) for m in months),
        "nso_cpi_yoy_b2023": series((m, 5.0) for m in months),
        "imf_cpi_yoy": series((m, 5.0) for m in months),
        "wdi_gdp_growth": series((y, 5.0) for y in p.YEARS),
        "imf_weo_gdp_growth": series((y, 5.0) for y in p.YEARS),
    }
    assert f.cross_check(split(base), {}, SERIES, print) == {}
    off = {
        "pinksheet_copper": series((m, 9500.0) for m in months),  # 5.6% above the IMF
        "nso_cpi_yoy_b2023": series((m, 5.7) for m in months),  # 0.7 pp
        "wdi_gdp_growth": series((y, 5.4) for y in p.YEARS),  # 0.4 pp
    }
    rejected = f.cross_check(split({**base, **off}), {}, SERIES, print)
    assert sorted(rejected) == ["nso", "pinksheet", "wdi"]


# -- the real sources, through a fake transport --------------------------------------------
def real_run(store: Path, route, **kwargs) -> tuple[int, list[str]]:
    session, _ = p.session(route)
    logs: list[str] = []
    code = f.run(
        store, today=TODAY, http=Http(session, sleep=lambda s: None), log=logs.append, **kwargs
    )
    return code, logs


def test_every_real_source_end_to_end_and_a_byte_identical_rerun(tmp_path):
    code, logs = real_run(tmp_path, p.serve(p.world()))
    assert code == 0, logs
    status = f.read_status(tmp_path)
    assert {name: s["status"] for name, s in status["sources"].items()} == dict.fromkeys(
        ["bom", "fred", "imf_datamapper", "imf_sdmx", "nso", "pinksheet", "wdi"], "ok"
    )
    assert set(status["series"]) == set(SERIES)
    assert status["sources"]["imf_datamapper"]["info"] == {"weo_vintage": "April 2026"}
    assert status["sources"]["pinksheet"]["info"]["updated_on"] == "2026-09-02"
    before = snapshot(tmp_path)
    code, _ = real_run(tmp_path, p.serve(p.world()))
    assert code == 0 and snapshot(tmp_path) == before


def test_a_403_from_the_imf_is_a_soft_failure(tmp_path):
    real_run(tmp_path, p.serve(p.world()))
    before = snapshot(tmp_path)
    blocked = {"https://www.imf.org/external/datamapper/api/v2/NGDP_RPCH/MNG": 403}
    code, logs = real_run(tmp_path, p.serve(p.world(), status=blocked))
    assert code == 0
    status = f.read_status(tmp_path)["sources"]
    assert status["imf_datamapper"]["status"] == "stale"
    assert "HTTP 403" in status["imf_datamapper"]["error"]
    assert all(status[n]["status"] == "ok" for n in status if n != "imf_datamapper")
    after = snapshot(tmp_path)
    assert all(after[k] == before[k] for k in after if k.startswith("imf_weo_"))


def test_a_rejected_real_cross_check(tmp_path):
    real_run(tmp_path, p.serve(p.world()))
    bodies = p.world()
    bodies.update({k: v for k, v in p.world(growth=5.5).items() if "api.worldbank.org" in k})
    code, _ = real_run(tmp_path, p.serve(bodies))
    assert code == 0
    status = f.read_status(tmp_path)["sources"]
    assert status["wdi"]["status"] == "stale"
    assert "GDP growth" in status["wdi"]["error"]
    assert status["imf_datamapper"]["status"] == "ok"
