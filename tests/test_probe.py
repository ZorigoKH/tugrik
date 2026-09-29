"""The endpoint probe, on a fake transport: every request of a source goes out, even after
one of them fails."""

import payloads as p

from pipeline import probe
from pipeline.fetch import load_sources
from pipeline.sources import bom, nso


def test_a_failed_request_does_not_stop_the_rest_of_its_source():
    blocked = {bom.DAILY: 403, nso.API + nso.TABLES["cpi_mom"]: 403}
    session, adapter = p.session(p.serve(p.world(), status=blocked))
    sources = {name: load_sources()[name] for name in ("bom", "nso")}
    rows = probe.probe(sources, session, sleep=lambda s: None)
    assert len(adapter.sent) == 4 + 5  # every BoM and NSO endpoint was asked
    failed = [row for row in rows if not probe.ok(row)]
    assert [(row["source"], row["status"]) for row in failed] == [("bom", 403), ("nso", 403)]
    assert not any("error" in row for row in rows)  # each source's fetch ran to the end


def test_the_probe_reports_every_endpoint_when_all_answer():
    session, adapter = p.session(p.serve(p.world()))
    rows = probe.probe(load_sources(), session, sleep=lambda s: None)
    assert len(rows) == len(adapter.sent) == 4 + 5 + 2 + 4 + 4 + 4 + 2
    assert all(probe.ok(row) for row in rows)
