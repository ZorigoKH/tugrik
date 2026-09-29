"""One module per publisher, all with the same two functions.

* ``fetch(http)`` downloads the raw payload (bytes, text or decoded JSON) with a
  :class:`pipeline.http.Http`. It is the only part that touches the network.
* ``parse(payload)`` turns the payload into ``{series_id: pd.Series}``. It is pure: no
  network, no clock, no files, so the tests run it on small synthetic payloads.

A module may also define ``info(payload)``, a few facts about the release (the date the
publisher says it was updated, the WEO vintage) that :mod:`pipeline.fetch` records in
``data/status.json``.

Every series is indexed by date strings - ``YYYY-MM-DD`` for days, ``YYYY-MM`` for months,
``YYYY`` for years - sorted, with float values and no missing values.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd

SOURCE_IDS = ("bom", "nso", "pinksheet", "imf_sdmx", "imf_datamapper", "wdi", "fred")


def series(pairs: Iterable[tuple[str, float | None]]) -> pd.Series:
    """A clean series from ``(date, value)`` pairs: missing values dropped, sorted by date.

    Raises ValueError if a date appears twice with different values.
    """
    data: dict[str, float] = {}
    for date, value in pairs:
        if value is None:
            continue
        value = float(value)
        if math.isnan(value):
            continue
        date = str(date)
        if date in data and data[date] != value:
            raise ValueError(f"{date} appears twice, as {data[date]:g} and {value:g}")
        data[date] = value
    dates = sorted(data)
    return pd.Series([data[d] for d in dates], index=pd.Index(dates, dtype=object), dtype=float)
