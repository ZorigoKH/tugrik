"""tugrik: the data pipeline behind the website.

Two stages, kept apart so that tests and local development never touch the network:

* ``python -m pipeline.fetch --store data`` downloads from the publishers and updates the
  store: one ``data/<series_id>.csv`` per series (``date,value``) plus ``data/status.json``.
  Each source is fetched, parsed and checked on its own; a source that fails keeps its
  previous files and is marked stale.
* ``python -m pipeline.build`` (offline, deterministic) turns the store into the site's JSON.

Modules:

* :mod:`pipeline.http` - one ``requests`` session with timeouts, retries and a polite pace.
* :mod:`pipeline.sources` - one module per publisher, each a network ``fetch`` and a pure ``parse``.
* :mod:`pipeline.registry` - every stored series: units, bounds and how much it may be revised.
* :mod:`pipeline.fetch` - sanity checks, revision guard, cross-source checks and store writes.
* :mod:`pipeline.transform` - pure transforms of stored series, and the model inputs.
* :mod:`pipeline.models` - the frozen regressions (sandwich OLS with HAC standard errors).
* :mod:`pipeline.summarize` - estimates to JSON records, and the takeaway sentences.
* :mod:`pipeline.build` - store to ``web/data`` JSON and ``web/public/csv`` downloads.
* :mod:`pipeline.validate` - the schema and invariants of the JSON; the build runs it too.
* :mod:`pipeline.probe` - one request per endpoint: status, bytes and latency.
"""

__version__ = "0.1.0"
SCHEMA_VERSION = 1  # of the site's JSON files
STORE_VERSION = 1  # of data/status.json
