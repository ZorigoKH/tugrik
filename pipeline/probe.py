"""Probe: can this machine reach every endpoint? One request each: status, bytes, latency.

    python -m pipeline.probe [--only SRC,...]

It runs each source's own ``fetch`` with a single attempt per request (no retries), so it
asks exactly what the fetch stage asks, and records every request. A failed request does
not stop the source: it answers with an empty body and the source's next request goes out,
so every endpoint is tried (except one whose address comes from a failed answer, such as
the Pink Sheet's workbook link). Nothing is parsed or written. The table goes to stdout
and, on GitHub Actions, to the job summary. The exit code is 1 if any request failed.

None of the endpoints had been tried from a GitHub runner when this was written; the IMF
DataMapper, the Bank of Mongolia and NSO are the unknowns.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from .fetch import load_sources
from .http import FetchError, Http
from .sources import SOURCE_IDS


class Empty:
    """What a failed request answers during a probe: an empty body of every kind."""

    status_code = 0
    text = ""
    content = b""

    def json(self) -> dict:
        return {}


class ProbeHttp(Http):
    """:class:`Http` whose failed requests answer :class:`Empty` instead of raising, so a
    source's ``fetch`` goes on to its next request. The failure is already in the log."""

    def request(self, method: str, url: str, **kwargs):
        try:
            return super().request(method, url, **kwargs)
        except FetchError:
            return Empty()


def probe(sources=None, session=None, sleep=time.sleep) -> list[dict]:
    """One row per request: source, method, url, status, bytes, seconds (and error, if any).

    ``session`` and ``sleep`` go to :class:`Http`, so tests need no network or waiting.
    """
    sources = load_sources() if sources is None else sources
    rows: list[dict] = []
    for name, module in sources.items():

        def record(row: dict, name: str = name) -> None:
            rows.append({"source": name, **row})

        http = ProbeHttp(session, attempts=1, sleep=sleep, log=record)
        try:
            module.fetch(http)
        except Exception as exc:  # report and go on to the next source
            rows.append({"source": name, "error": f"{type(exc).__name__}: {exc}"[:200]})
    return rows


def ok(row: dict) -> bool:
    return "error" not in row and isinstance(row.get("status"), int) and row["status"] < 400


def table(rows: list[dict]) -> str:
    lines = ["| source | method | url | status | bytes | seconds |", "|---|---|---|---:|---:|---:|"]
    for row in rows:
        if "error" in row:
            lines.append(f"| {row['source']} | | {row['error']} | failed | | |")
            continue
        lines.append(
            f"| {row['source']} | {row['method']} | {row['url']} | {row['status']} | "
            f"{row['bytes']:,} | {row['seconds']:.2f} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.probe",
        description="Send each source's requests once and report status, size and latency.",
    )
    parser.add_argument("--only", metavar="SRC,...", help="probe only these sources")
    args = parser.parse_args(argv)
    sources = load_sources()
    if args.only:
        wanted = [s.strip() for s in args.only.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in SOURCE_IDS]
        if unknown:
            parser.error(f"unknown source {unknown[0]!r}")
        sources = {name: sources[name] for name in wanted}
    rows = probe(sources)
    report = table(rows)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Endpoint probe\n\n" + report + "\n")
    return 0 if rows and all(ok(row) for row in rows) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
