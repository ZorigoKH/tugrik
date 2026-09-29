"""The HTTP client, on a fake transport: user agent, retries, soft failures and pacing."""

import payloads as p
import pytest
import requests

from pipeline.fetch import load_sources
from pipeline.http import BACKOFF, FetchError, Http


def answers(*statuses):
    """A route that answers with these status codes in turn."""
    queue = list(statuses)

    def route(request):
        status = queue.pop(0)
        if isinstance(status, Exception):
            raise status
        return status, b"{}"

    return route


def test_no_custom_user_agent_is_ever_sent():
    """Every source's real fetch, through one fake session: only the library's default UA."""
    session, adapter = p.session(p.serve(p.world()))
    http = Http(session, sleep=lambda s: None)
    for module in load_sources().values():
        module.fetch(http)
    assert len(adapter.sent) == 4 + 5 + 2 + 4 + 4 + 4 + 2
    default = requests.utils.default_user_agent()
    assert {r.headers["User-Agent"] for r in adapter.sent} == {default}


def test_the_imf_sdmx_asks_for_csv():
    session, adapter = p.session(p.serve(p.world()))
    load_sources()["imf_sdmx"].fetch(Http(session, sleep=lambda s: None))
    assert {r.headers["Accept"] for r in adapter.sent} == {
        "application/vnd.sdmx.data+csv;version=1.0.0"
    }


def test_two_503s_then_200_succeeds_after_backing_off():
    session, adapter = p.session(answers(503, 503, 200))
    waits = []
    resp = Http(session, sleep=waits.append).get("https://api.worldbank.org/v2/x")
    assert resp.status_code == 200
    assert len(adapter.sent) == 3
    assert waits == [BACKOFF, 2 * BACKOFF]


def test_timeouts_are_retried_then_fail_softly():
    session, adapter = p.session(answers(*[requests.ConnectTimeout("slow")] * 3))
    with pytest.raises(FetchError, match="ConnectTimeout"):
        Http(session, sleep=lambda s: None).get("https://fred.stlouisfed.org/x")
    assert len(adapter.sent) == 3


def test_403_fails_at_once_as_a_soft_failure():
    session, adapter = p.session(answers(403, 200))
    waits = []
    with pytest.raises(FetchError, match="HTTP 403"):
        Http(session, sleep=waits.append).get("https://www.imf.org/external/datamapper/api/v2/X")
    assert len(adapter.sent) == 1 and waits == []


def test_timeouts_are_set_on_every_request():
    seen = []

    class Recording(requests.Session):
        def request(self, method, url, **kwargs):
            seen.append(kwargs.get("timeout"))
            return super().request(method, url, **kwargs)

    session = Recording()
    session.mount("https://", p.FakeAdapter(answers(200)))
    Http(session).get("https://api.worldbank.org/v2/x")
    assert seen == [(10.0, 90.0)]


def test_nso_gets_at_most_two_requests_a_second():
    session, _ = p.session(answers(200, 200, 200))
    waits = []
    http = Http(session, sleep=waits.append, clock=lambda: 100.0)  # no time passes
    http.post("https://data.1212.mn/api/v1/en/NSO/a.px")
    http.post("https://data.1212.mn/api/v1/en/NSO/b.px")
    http.get("https://api.worldbank.org/v2/x")  # other hosts are not paced
    assert waits == [0.5]


def test_the_log_sees_every_attempt():
    session, _ = p.session(answers(503, 200))
    rows = []
    Http(session, sleep=lambda s: None, log=rows.append).get("https://example.org/x")
    assert [r["status"] for r in rows] == [503, 200]
    assert set(rows[0]) == {"method", "url", "status", "bytes", "seconds"}
