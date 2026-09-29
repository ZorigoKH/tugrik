"""Fetch: update the store in ``data/`` from the publishers, one source at a time.

    python -m pipeline.fetch --store data [--only SRC,...] [--accept-revisions SRC,...]
                                          [--today YYYY-MM-DD]

For each source in :mod:`pipeline.sources` this downloads the payload, parses it into series
and checks them:

1. **Sanity.** Every series of the source in the registry is there, and no other (a new NSO
   CPI base year shows up as an unknown series); dates are well formed, sorted and unique; a
   monthly series has no month missing inside it; values are finite and within the
   registry's bounds; no series ends before the stored one or loses more than one row; a
   publisher's stated release date is recent (the Pink Sheet's within 45 days).
2. **Revision guard.** Stored observations may not move beyond the registry's tolerance
   (:class:`pipeline.registry.Revision`), unless the source is named in
   ``--accept-revisions``.
3. **Cross-source checks** (:data:`CHECKS`), whenever both sides are available. Each check
   compares a *checked* series with a *reference* (for the latest month of each published
   monthly average of MNT per USD, the BoM daily rate, or the other averages when the
   daily rate does not cover that month; the IMF for the Pink Sheet, NSO's CPI and WDI's
   growth). A breach rejects the newer side's update: the side whose data changed in this
   run, or the checked side if both did. The rejected sources' stored data then stand in,
   and the checks run again. A source named in ``--accept-revisions`` is never rejected
   here: the breach is logged, and a human has vouched for the update.

A source that passes has its changed files replaced atomically (a temporary file, then
``os.replace``); unchanged files are left alone. A source that fails keeps its previous
files, is marked stale in ``data/status.json`` and gets a ``::warning::`` line for GitHub
Actions. The run exits 1 and writes nothing at all if 3 or more sources fail, or if a
source fails that has no previous files (the first run).

``data/status.json`` records, per source and per series, the last observation and the date
its stored data last changed - never the time of the last check, so a run that finds no new
data changes no bytes.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

from . import STORE_VERSION
from .http import Http
from .registry import SERIES, SOURCES, Series
from .sources import SOURCE_IDS, series
from .transform import newest_base, weekday_mean

MAX_FAILED = 3  # this many failed sources abort the run

FX_TOLERANCE = 0.005  # the latest month of a published monthly average vs its reference
FX_AVERAGES = ("bom_usdmnt_monthly_avg", "nso_usdmnt_monthly_avg", "imf_usdmnt_monthly_avg")
PRICE_TOLERANCE = 0.02  # Pink Sheet vs IMF PCPS, copper, gold and zinc
PRICE_SINCE = "1992-01"
CPI_TOLERANCE = 0.5  # percentage points, NSO vs IMF CPI year on year
CPI_MONTHS = 24
GROWTH_TOLERANCE = 0.3  # percentage points, WDI vs IMF WEO real GDP growth
GROWTH_YEARS = 10

DATE = {
    "D": re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"),
    "E": re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"),
    "M": re.compile(r"\d{4}-(0[1-9]|1[0-2])"),
    "A": re.compile(r"\d{4}"),
}

Log = Callable[[str], object]


def load_sources() -> dict[str, ModuleType]:
    return {name: importlib.import_module(f"pipeline.sources.{name}") for name in SOURCE_IDS}


# -- the store -----------------------------------------------------------------------------
def read_series(path: Path) -> pd.Series:
    """A stored ``date,value`` CSV as a series."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        if next(reader, None) != ["date", "value"]:
            raise ValueError(f"{path}: the header must be date,value")
        return series((row[0], float(row[1])) for row in reader if row)


def number(value: float) -> str:
    """A value as the store writes it: rounded to 6 decimals, in its shortest exact form."""
    return repr(round(float(value), 6) + 0.0)  # + 0.0 turns -0.0 into 0.0


def to_csv(s: pd.Series) -> bytes:
    lines = ["date,value", *(f"{d},{number(v)}" for d, v in s.items())]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_files(store: Path, files: Mapping[str, bytes]) -> None:
    """Write ``files`` into ``store``: all are staged as temporary files first, then each is
    moved into place with ``os.replace``, so a reader never sees half a file."""
    staged: list[tuple[str, Path]] = []
    try:
        for name, data in files.items():
            fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=store)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, 0o644)
            staged.append((tmp, store / name))
        for tmp, target in staged:
            os.replace(tmp, target)
    finally:
        for tmp, _ in staged:
            if os.path.exists(tmp):
                os.remove(tmp)


def read_status(store: Path) -> dict:
    try:
        status = json.loads((store / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    return {
        "sources": dict(status.get("sources", {})),
        "series": dict(status.get("series", {})),
    }


def to_json(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


# -- checks on one source ------------------------------------------------------------------
def normalize(s: pd.Series, spec: Series | None) -> pd.Series:
    """Drop observations before the registry's ``start`` and round as the store does."""
    if spec is not None and spec.start:
        s = s[s.index >= spec.start]
    return series((d, round(float(v), 6) + 0.0) for d, v in s.items())


def months_between(first: str, last: str) -> list[str]:
    """Every ``YYYY-MM`` from ``first`` to ``last``."""
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def sanity(spec: Series, new: pd.Series, old: pd.Series | None) -> list[str]:
    """What is wrong with one freshly parsed series (an empty list if nothing)."""
    if new.empty:
        return [f"{spec.id}: no observations"]
    bad = [d for d in new.index if not DATE[spec.freq].fullmatch(d)]
    if bad:
        return [f"{spec.id}: malformed date {bad[0]!r}"]
    problems = []
    if not new.index.is_monotonic_increasing or new.index.has_duplicates:
        problems.append(f"{spec.id}: dates are not sorted and unique")
    if not np.isfinite(new.to_numpy()).all():
        problems.append(f"{spec.id}: values that are not finite")
    if spec.freq == "M":
        missing = sorted(set(months_between(new.index[0], new.index[-1])) - set(new.index))
        if missing:
            problems.append(f"{spec.id}: {len(missing)} missing months inside, from {missing[0]}")
    lo, hi = spec.bounds
    checked = new[new.index >= spec.bounds_from]
    outside = checked[(checked < lo) | (checked > hi)]
    if len(outside):
        problems.append(
            f"{spec.id}: {len(outside)} values outside [{lo:g}, {hi:g}], "
            f"such as {outside.index[0]} = {outside.iloc[0]:g}"
        )
    if old is not None and len(old):
        if new.index[-1] < old.index[-1]:
            problems.append(f"{spec.id}: ends {new.index[-1]}, before the stored {old.index[-1]}")
        if len(new) < len(old) - 1:
            problems.append(f"{spec.id}: {len(new)} rows, down from {len(old)}")
    return problems


def months_before(month: str, k: int) -> str:
    """The ``YYYY-MM`` month ``k`` months before ``month``."""
    total = int(month[:4]) * 12 + int(month[5:7]) - 1 - k
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def revisions(spec: Series, new: pd.Series, old: pd.Series | None) -> tuple[list[str], int]:
    """Compare a new series with the stored one.

    Returns the revisions beyond the registry's tolerance and the number of stored
    observations that moved or disappeared at all.
    """
    if old is None or old.empty:
        return [], 0
    rule = spec.revision
    common = old.index.intersection(new.index)
    moved = [d for d in common if abs(new[d] - old[d]) > 1e-9]
    gone = [d for d in old.index if d not in new.index]
    if rule.kind == "accept":
        return [], len(moved) + len(gone)
    newest_guarded = months_before(old.index[-1][:7], rule.recent)

    def guarded(d: str) -> bool:
        return d >= rule.since and d[:7] <= newest_guarded

    breaches = []
    for d in moved:
        if not guarded(d):
            continue
        before, after = old[d], new[d]
        if rule.kind == "relative":
            too_far = abs(after - before) > rule.tolerance * abs(before)
        elif rule.kind == "absolute":
            too_far = abs(after - before) > rule.tolerance + 1e-9
        else:  # exact
            too_far = True
        if too_far:
            breaches.append(f"{spec.id} {d}: {before:g} -> {after:g}")
    if rule.kind == "exact":
        breaches += [f"{spec.id} {d}: {old[d]:g} -> removed" for d in gone if guarded(d)]
    return breaches, len(moved) + len(gone)


def check_source(
    name: str,
    parsed: Mapping[str, pd.Series],
    ids: list[str],
    registry: Mapping[str, Series],
    stored: Mapping[str, pd.Series],
    info: Mapping[str, str],
    today: date,
    accept: Collection[str],
) -> tuple[list[str], int]:
    """Sanity checks and the revision guard for one source: (problems, revised count)."""
    problems = []
    unknown = sorted(set(parsed) - set(ids))
    if unknown:
        hint = ""
        if any(sid.startswith("nso_cpi_") for sid in unknown):
            hint = " (a new CPI base year: the registry and the CPI splice need a human)"
        problems.append(f"series the registry does not know: {', '.join(unknown)}{hint}")
    missing = [sid for sid in ids if sid not in parsed]
    if missing:
        problems.append(f"series missing from the download: {', '.join(missing)}")
    for sid in ids:
        if sid in parsed:
            problems += sanity(registry[sid], parsed[sid], stored.get(sid))
    source = SOURCES.get(name)
    limit = source.updated_max_age_days if source else None
    if limit is not None and "updated_on" in info:
        age = (today - date.fromisoformat(info["updated_on"])).days
        if age > limit:
            problems.append(f"the release is dated {info['updated_on']}, {age} days ago")
    if problems:
        return problems, 0
    breaches: list[str] = []
    revised = 0
    for sid in ids:
        found, moved = revisions(registry[sid], parsed[sid], stored.get(sid))
        breaches += found
        revised += moved
    if breaches and name not in accept:
        more = len(breaches) - 3
        shown = "; ".join(breaches[:3]) + (f"; and {more} more" if more > 0 else "")
        problems.append(
            f"{len(breaches)} revisions beyond tolerance ({shown}); if they are genuine, "
            f"rerun with --accept-revisions {name}"
        )
    return problems, revised


# -- checks across sources -----------------------------------------------------------------
@dataclass(frozen=True)
class Breach:
    """Two sources disagree. ``checked`` and ``reference`` name the series on each side."""

    checked: tuple[str, ...]
    reference: tuple[str, ...]
    message: str


Get = Callable[[str], "pd.Series | None"]


def check_fx(get: Get) -> list[Breach]:
    """The latest month of each published monthly average of MNT per USD within 0.5% of a
    reference for that month (all three are within 0.04% of the daily mean in 2024-2026).

    The reference is the BoM daily weekday mean. When the daily rate does not cover the
    month (the BoM's fetch failing, say), it is the median of the other averages for that
    month. With only two averages, each is checked against the other, so a disagreement
    rejects whichever of them is new in this run, and both if both are: nothing says which
    is right. Only the latest month is checked: a defect in an older month, which the
    consensus rule routes around, never holds a source back.
    """
    daily = get("bom_usdmnt_daily")
    reference = weekday_mean(daily) if daily is not None else series([])
    averages = {sid: get(sid) for sid in FX_AVERAGES}
    averages = {sid: s for sid, s in averages.items() if s is not None and len(s)}
    out = []
    for sid, average in averages.items():
        month = average.index[-1]
        if month in reference.index:
            against, sides = float(reference[month]), ("bom_usdmnt_daily",)
            what = "the BoM daily weekday mean"
        else:
            others = {o: s[month] for o, s in averages.items() if o != sid and month in s.index}
            if not others:
                continue
            against, sides = float(np.median(list(others.values()))), tuple(others)
            what = "the median of the other averages"
        gap = abs(average[month] / against - 1)
        if gap > FX_TOLERANCE:
            out.append(
                Breach(
                    (sid,),
                    sides,
                    f"{sid} {month} = {average[month]:g} is {100 * gap:.2f}% from {what} "
                    f"{against:g} (limit 0.5%)",
                )
            )
    return out


def check_prices(get: Get) -> list[Breach]:
    """Pink Sheet copper, gold and zinc within 2% of the IMF's PCPS since 1992."""
    out = []
    for metal in ("copper", "gold", "zinc"):
        ours, imf = get(f"pinksheet_{metal}"), get(f"imf_pcps_{metal}")
        if ours is None or imf is None:
            continue
        months = ours.index.intersection(imf.index)
        months = months[months >= PRICE_SINCE]
        if len(months) == 0:
            continue
        gap = (ours[months] / imf[months] - 1).abs()
        if gap.max() > PRICE_TOLERANCE:
            worst = gap.idxmax()
            out.append(
                Breach(
                    (f"pinksheet_{metal}",),
                    (f"imf_pcps_{metal}",),
                    f"Pink Sheet {metal} {worst} = {ours[worst]:g} is {100 * gap[worst]:.1f}% "
                    f"from the IMF's {imf[worst]:g} (limit 2%)",
                )
            )
    return out


NSO_CPI_YOY = tuple(sid for sid in SERIES if sid.startswith("nso_cpi_yoy_b"))


def check_cpi(get: Get) -> list[Breach]:
    """NSO CPI year on year (newest base) within 0.5 pp of the IMF's over the last 24 months."""
    bases = {int(sid[-4:]): get(sid) for sid in NSO_CPI_YOY}
    bases = {base: s for base, s in bases.items() if s is not None}
    imf = get("imf_cpi_yoy")
    if not bases or imf is None:
        return []
    nso = newest_base(bases)
    months = nso.index.intersection(imf.index).sort_values()[-CPI_MONTHS:]
    if len(months) == 0:
        return []
    gap = (nso[months] - imf[months]).abs()
    if gap.max() <= CPI_TOLERANCE:
        return []
    worst = gap.idxmax()
    return [
        Breach(
            NSO_CPI_YOY,
            ("imf_cpi_yoy",),
            f"NSO CPI y/y {worst} = {nso[worst]:g}% and the IMF's {imf[worst]:g}% differ by "
            f"{gap[worst]:.2f} pp (limit 0.5)",
        )
    ]


def check_growth(get: Get) -> list[Breach]:
    """WDI real GDP growth within 0.3 pp of the IMF WEO's over the last 10 common years."""
    wdi, imf = get("wdi_gdp_growth"), get("imf_weo_gdp_growth")
    if wdi is None or imf is None:
        return []
    years = wdi.index.intersection(imf.index).sort_values()[-GROWTH_YEARS:]
    if len(years) == 0:
        return []
    gap = (wdi[years] - imf[years]).abs()
    if gap.max() <= GROWTH_TOLERANCE:
        return []
    worst = gap.idxmax()
    return [
        Breach(
            ("wdi_gdp_growth",),
            ("imf_weo_gdp_growth",),
            f"GDP growth {worst}: WDI {wdi[worst]:g}% and IMF {imf[worst]:g}% differ by "
            f"{gap[worst]:.2f} pp (limit 0.3)",
        )
    ]


CHECKS: tuple[Callable[[Get], list[Breach]], ...] = (
    check_fx,
    check_prices,
    check_cpi,
    check_growth,
)


def cross_check(
    new: Mapping[str, Mapping[str, pd.Series]],
    stored: Mapping[str, pd.Series],
    registry: Mapping[str, Series],
    log: Log,
    checks=CHECKS,
    accept: Collection[str] = (),
) -> dict[str, str]:
    """Run the checks on the newest data that has passed so far and return the updates to
    reject, as ``{source: reason}``.

    Every breach in a round rejects its newer side: the side whose data changed in this
    run, or the checked side if both did. The rejected sources' stored data then stand in
    for them and the checks run again, until a round rejects nothing. A breach between two
    sides that are both stored data has no update to reject, and one that blames a source
    in ``accept`` is waived by hand; both are only logged.
    """
    rejected: dict[str, str] = {}
    noted: set[str] = set()

    def get(sid: str) -> pd.Series | None:
        spec = registry.get(sid)
        if spec is None:
            return None
        if spec.source in new and spec.source not in rejected:
            return new[spec.source].get(sid)
        return stored.get(sid)

    def updated(side: tuple[str, ...]) -> str | None:
        """The source of this side if it brings new data in this run, else None."""
        for sid in side:
            spec = registry.get(sid)
            if spec is None or spec.source not in new or spec.source in rejected:
                continue
            candidate, before = new[spec.source].get(sid), stored.get(sid)
            if candidate is not None and (before is None or to_csv(candidate) != to_csv(before)):
                return spec.source
        return None

    while True:
        found: dict[str, str] = {}
        for check in checks:
            for breach in check(get):
                culprit = updated(breach.checked) or updated(breach.reference)
                if culprit is not None and culprit not in accept:
                    found.setdefault(culprit, breach.message)
                    continue
                why = (
                    "in the stored data; nothing new to reject"
                    if culprit is None
                    else f"{culprit}'s update accepted by hand"
                )
                if breach.message not in noted:
                    log(f"note: {breach.message} ({why})")
                    noted.add(breach.message)
        if not found:
            return rejected
        rejected.update(found)


# -- the run -------------------------------------------------------------------------------
def describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def last_obs(data: Mapping[str, pd.Series]) -> str | None:
    """The latest date across a source's series (the formats sort correctly together)."""
    dates = [s.index[-1] for s in data.values() if s is not None and len(s)]
    return max(dates) if dates else None


def run(
    store: str | os.PathLike,
    *,
    only: Collection[str] | None = None,
    accept: Collection[str] = (),
    today: date | None = None,
    http: Http | None = None,
    sources: Mapping[str, ModuleType] | None = None,
    registry: Mapping[str, Series] | None = None,
    log: Log = print,
) -> int:
    """Fetch, check and store; return the exit code (0, or 1 if the run was aborted)."""
    store = Path(store)
    today = today or date.today()
    registry = SERIES if registry is None else registry
    sources = load_sources() if sources is None else sources
    http = Http() if http is None else http
    ids_of = {name: [sid for sid, s in registry.items() if s.source == name] for name in sources}
    stored = {
        sid: read_series(store / f"{sid}.csv")
        for sid in registry
        if (store / f"{sid}.csv").is_file()
    }
    names = [name for name in sources if only is None or name in only]

    new: dict[str, dict[str, pd.Series]] = {}
    failed: dict[str, str] = {}
    revised: dict[str, int] = {}
    infos: dict[str, dict] = {}
    for name in names:
        module = sources[name]
        log(f"{name}: fetching")
        try:
            payload = module.fetch(http)
            parsed = module.parse(payload)
            info = module.info(payload) if hasattr(module, "info") else {}
        except Exception as exc:  # whatever goes wrong with one source, the others go on
            failed[name] = f"fetch failed: {describe(exc)}"
            continue
        parsed = {sid: normalize(s, registry.get(sid)) for sid, s in parsed.items()}
        problems, moved = check_source(
            name, parsed, ids_of[name], registry, stored, info, today, accept
        )
        if problems:
            failed[name] = "; ".join(problems)
            continue
        new[name], revised[name], infos[name] = parsed, moved, dict(info)

    for name, reason in cross_check(new, stored, registry, log, accept=accept).items():
        failed[name] = (
            f"cross-source check: {reason}; if the update is right, rerun with "
            f"--accept-revisions {name}"
        )
        del new[name]

    unseeded = [name for name in failed if any(sid not in stored for sid in ids_of[name])]
    if len(failed) >= MAX_FAILED or unseeded:
        for name, reason in failed.items():
            log(f"::error::{name} failed: {reason}")
        why = (
            f"{', '.join(unseeded)} failed with no previous data to keep"
            if unseeded
            else f"{len(failed)} sources failed (the limit is {MAX_FAILED - 1})"
        )
        log(f"::error::fetch aborted, nothing written: {why}")
        return 1

    store.mkdir(parents=True, exist_ok=True)
    changed: dict[str, list[str]] = {}
    for name, data in new.items():
        files = {f"{sid}.csv": to_csv(data[sid]) for sid in ids_of[name]}
        changed[name] = sorted(
            file
            for file, content in files.items()
            if not (store / file).is_file() or (store / file).read_bytes() != content
        )
        write_files(store, {file: files[file] for file in changed[name]})

    status = read_status(store)
    iso = today.isoformat()
    for name in names:
        previous = status["sources"].get(name, {})
        if name in failed:
            status["sources"][name] = {
                "status": "stale",
                "error": failed[name],
                "last_obs": previous.get("last_obs")
                or last_obs({sid: stored.get(sid) for sid in ids_of[name]}),
                "last_changed": previous.get("last_changed"),
                "revisions": previous.get("revisions", 0),
                "info": previous.get("info", {}),
            }
            continue
        data, updated = new[name], bool(changed[name])
        for sid in ids_of[name]:
            s = data[sid]
            was = status["series"].get(sid, {})
            status["series"][sid] = {
                "source": name,
                "first": s.index[0],
                "last_obs": s.index[-1],
                "rows": len(s),
                "last_changed": iso
                if f"{sid}.csv" in changed[name]
                else was.get("last_changed", iso),
            }
        status["sources"][name] = {
            "status": "ok",
            "error": None,
            "last_obs": last_obs(data),
            "last_changed": iso if updated else previous.get("last_changed", iso),
            "revisions": revised[name] if updated else previous.get("revisions", 0),
            "info": infos[name],
        }
    status["store_version"] = STORE_VERSION
    content = to_json(status)
    path = store / "status.json"
    if not path.is_file() or path.read_bytes() != content:
        write_files(store, {"status.json": content})

    for name in names:
        entry = status["sources"][name]
        if name in failed:
            log(f"::warning::{name} is stale, its previous data kept: {failed[name]}")
        else:
            files = changed[name]
            log(
                f"{name}: ok, {len(ids_of[name])} series through {entry['last_obs']}, "
                f"{len(files)} files changed"
                + (f", {revised[name]} stored observations revised" if revised[name] else "")
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.fetch",
        description="Download every source, check it and update the store (data/*.csv).",
    )
    parser.add_argument("--store", required=True, help="the store directory, e.g. data")
    parser.add_argument("--only", metavar="SRC,...", help="fetch only these sources")
    parser.add_argument(
        "--accept-revisions",
        metavar="SRC,...",
        default="",
        help="accept these sources' updates as fetched: revisions beyond the registry's "
        "tolerance and disagreements with another source are logged, not rejected",
    )
    parser.add_argument(
        "--today", metavar="YYYY-MM-DD", help="the date to record (default: the current date)"
    )
    args = parser.parse_args(argv)

    def names(text: str | None) -> list[str] | None:
        if text is None:
            return None
        found = [part.strip() for part in text.split(",") if part.strip()]
        unknown = [n for n in found if n not in SOURCE_IDS]
        if unknown:
            parser.error(f"unknown source {unknown[0]!r}; the sources are {', '.join(SOURCE_IDS)}")
        return found

    today = date.fromisoformat(args.today) if args.today else None
    return run(
        args.store,
        only=names(args.only),
        accept=names(args.accept_revisions) or (),
        today=today,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
