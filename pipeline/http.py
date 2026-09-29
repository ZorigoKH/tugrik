"""HTTP for the fetch stage: one session, plain defaults, retries and a polite pace.

Every request goes through :class:`Http`, which wraps a single ``requests.Session``:

* No custom ``User-Agent``. The session sends ``python-requests``'s default, the only one that
  works everywhere: the IMF's edge returns 403 for custom and browser user agents, and FRED
  hangs on browser ones.
* Timeouts of 10 s to connect and 90 s to read.
* Three attempts. A connection error, a timeout, 429 or a 5xx is retried after 2 s, then 4 s.
  Other errors (403, 404) fail at once, since asking again gets the same answer.
* At most two requests a second to NSO's server (``data.1212.mn``).

A request that fails for good raises :class:`FetchError`. That is a soft failure: the fetch
stage marks the source stale and carries on with the others.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlsplit

import requests

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 90.0
ATTEMPTS = 3
BACKOFF = 2.0  # seconds after the first failed attempt; doubles after each further one
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MIN_INTERVAL = {"data.1212.mn": 0.5}  # seconds between requests to one host

Log = Callable[[dict], object]


class FetchError(Exception):
    """A request failed for good (after retries, or at once for a 4xx other than 429)."""


class Http:
    """The one HTTP client of a fetch run. ``get`` and ``post`` return a ``requests.Response``.

    ``session``, ``sleep`` and ``clock`` are replaceable so tests can run without a network
    or real waiting. ``log``, if given, receives one dict per attempt (method, url, status,
    bytes, seconds); :mod:`pipeline.probe` uses it to report on every endpoint.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        attempts: int = ATTEMPTS,
        sleep: Callable[[float], object] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        log: Log | None = None,
    ) -> None:
        self.session = session if session is not None else requests.Session()
        self.attempts = attempts
        self.sleep = sleep
        self.clock = clock
        self.log = log
        self._last: dict[str, float] = {}  # host -> clock() of its last request

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send one request, retrying transient failures; raise :class:`FetchError` if it fails."""
        kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))
        problem = ""
        for attempt in range(self.attempts):
            if attempt:
                self.sleep(BACKOFF * 2 ** (attempt - 1))
            self._pace(url)
            start = self.clock()
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                # the class name only: the message can hold object addresses that change per run
                problem = type(exc).__name__
                self._record(method, url, problem, 0, start)
                continue
            self._record(method, url, resp.status_code, len(resp.content), start)
            if resp.status_code < 400:
                return resp
            problem = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUS:
                break
        raise FetchError(f"{method} {url}: {problem}")

    def _pace(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        gap = MIN_INTERVAL.get(host)
        if gap is None:
            return
        last = self._last.get(host)
        if last is not None:
            wait = gap - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def _record(self, method: str, url: str, status: int | str, size: int, start: float) -> None:
        if self.log is not None:
            seconds = round(self.clock() - start, 2)
            self.log(
                {"method": method, "url": url, "status": status, "bytes": size, "seconds": seconds}
            )
