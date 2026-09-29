"""Check the site's data before anything publishes it.

    python -m pipeline.validate web/data

Every file is checked against the schema - exactly the expected fields, each of the right
type, numbers finite and rounded to 6 decimals, months ``"YYYY-MM"`` and years ``"YYYY"`` -
and against the invariants the site relies on:

* months (and years) strictly increasing with none missing, and parallel lists of equal
  length;
* ``lo <= est <= hi`` for every estimate, and 13 horizons (0-12) in every response;
* the coal identity: dlog value = dlog volume + dlog unit value, within 1e-9, and each of
  the three is 100 x the log change of its published annual level (value, tonnes, value
  per tonne) between consecutive full years, within 1e-4 (the levels are rounded);
* the export-price weights of each year sum to 1, within 1e-9 (the build also checks the
  unrounded shares, in :func:`pipeline.transform.mxpi_weights`);
* every takeaway is non-empty and is exactly what its template in
  :mod:`pipeline.summarize` writes for the published numbers, so a sentence can never
  disagree with its estimate's interval; the overview cards repeat the pages' takeaways.

Exits 1 listing every problem. ``pipeline.build`` runs the same checks on its output before
moving it into place.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from . import SCHEMA_VERSION
from .summarize import PAGES, TAKEAWAYS

IDENTITY = 1e-9
LEVELS = 1e-4  # log points: a published change against its rounded published levels
COAL_CHANGES = (
    ("dlog_value", "value_musd"),
    ("dlog_volume", "volume_mt"),
    ("dlog_unit_value", "unit_value_usd_t"),
)
HORIZONS = list(range(13))
COPPER_SAMPLES = ["full", "ex_gfc", "pre2017", "post2017", "post2017_ex_border"]
GOODS = {"coal", "copper", "gold", "iron_ore", "oil", "zinc"}
FILES = ("meta", "overview", "copper", "coal", "prices", "growth", "sources")

_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_YEAR = re.compile(r"\d{4}")
_DATE = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")

Check = Callable[[Any], bool]


# -- types ---------------------------------------------------------------------------------
def is_num(x: Any) -> bool:
    """A finite JSON number with at most 6 decimals."""
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and round(x, 6) == x
    )


def is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def is_str(x: Any) -> bool:
    return isinstance(x, str)


def is_text(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def is_bool(x: Any) -> bool:
    return isinstance(x, bool)


def is_month(x: Any) -> bool:
    return isinstance(x, str) and _MONTH.fullmatch(x) is not None


def is_year(x: Any) -> bool:
    return isinstance(x, str) and _YEAR.fullmatch(x) is not None


def is_date(x: Any) -> bool:
    return isinstance(x, str) and _DATE.fullmatch(x) is not None


def is_period(x: Any) -> bool:
    return is_year(x) or is_month(x) or is_date(x)


def optional(check: Check) -> Check:
    return lambda x: x is None or check(x)


def list_of(check: Check) -> Check:
    return lambda x: isinstance(x, list) and all(check(v) for v in x)


def one_of(*allowed: Any) -> Check:
    return lambda x: x in allowed


def is_list(x: Any) -> bool:
    return isinstance(x, list)


def is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def str_map(x: Any) -> bool:
    return isinstance(x, dict) and all(is_str(k) and is_str(v) for k, v in x.items())


EST = {"est": is_num, "se": is_num, "t": is_num, "p": is_num, "lo": is_num, "hi": is_num}
NUMS = list_of(optional(is_num))

META = {
    "schema_version": is_int,
    "generated_at": is_date,
    "through": is_dict,
    "sources": is_list,
    "stale": list_of(is_text),
    "revisions": lambda x: is_dict(x) and all(is_int(v) for v in x.values()),
    "reference": is_list,
    "versions": str_map,
}
THROUGH = {
    "fx": is_month,
    "cpi": is_month,
    "policy_rate": is_date,
    "commodities": is_month,
    "trade": is_month,
    "gdp": is_year,
    "weo_vintage": optional(is_text),
}
META_SOURCE = {
    "id": is_text,
    "status": one_of("ok", "stale", "fallback"),
    "last_obs": optional(is_period),
    "last_changed": optional(is_date),
}
REFERENCE = {
    "id": is_text,
    "label": is_text,
    "page": one_of(*(p for p, _ in PAGES)),
    "reference": is_num,
    "current": optional(is_num),
}
OVERVIEW = {"tiles": is_list, "cards": is_list}
TILE = {
    "id": is_text,
    "label": is_text,
    "value": is_num,
    "unit": is_text,
    "period": is_period,
    "change": optional(is_dict),
    "detail": optional(is_dict),
    "spark": is_dict,
    "source": is_text,
    "status": one_of("ok", "stale", "fallback"),
}
AMOUNT = {"value": is_num, "unit": is_text, "label": is_text}
SPARK = {"dates": list_of(is_period), "values": NUMS}
CARD = {"page": is_text, "title": is_text, "takeaway": is_text}

COPPER = {
    "schema_version": is_int,
    "takeaway": is_text,
    "takeaway_fit": is_text,
    "horizons": is_list,
    "samples": is_list,
    "controls": is_dict,
    "fit12": is_dict,
    "episodes": is_list,
}
SAMPLE = {
    "id": is_text,
    "label": is_text,
    "start": is_month,
    "end": is_month,
    "nobs": is_int,
    "maxlags": is_int,
    "r2": is_num,
    "copper": is_list,
    "coal_h12": is_dict,
}
FIT12 = {
    "months": list_of(is_month),
    "actual_pct": list_of(is_num),
    "fitted_pct": list_of(is_num),
    "nobs": is_int,
    "r2": is_num,
    "maxlags": is_int,
    "copper_t6": is_dict,
    "coal_t6": is_dict,
    "usd": is_dict,
}
WINDOW = {"label": is_text, "start": is_month, "end": is_month}

COAL = {
    "schema_version": is_int,
    "takeaway": is_text,
    "takeaway_gap": is_text,
    "annual": is_list,
    "monthly": is_dict,
    "border": is_dict,
}
COAL_YEAR = {
    "year": is_year,
    "partial": is_bool,
    "through": is_month,
    "value_musd": is_num,
    "volume_mt": is_num,
    "unit_value_usd_t": optional(is_num),
    "benchmark_usd_t": optional(is_num),
    "dlog_value": optional(is_num),
    "dlog_volume": optional(is_num),
    "dlog_unit_value": optional(is_num),
    "volume_vs_2019_pct": optional(is_num),
}
COAL_MONTHLY = {
    "months": list_of(is_month),
    "volume_mt": NUMS,
    "unit_value_usd_t": NUMS,
    "benchmark_usd_t": NUMS,
}
BORDER = {"start": is_month, "end": is_month}

PRICES = {
    "schema_version": is_int,
    "takeaway": is_text,
    "takeaway_context": is_text,
    "horizons": is_list,
    "specs": is_list,
    "subsamples": is_list,
    "context": is_dict,
    "years": is_list,
    "weo": is_dict,
}
SPEC = {
    "id": one_of("dl", "preferred"),
    "label": is_text,
    "start": is_month,
    "end": is_month,
    "nobs": is_int,
    "maxlags": is_int,
    "r2": is_num,
    "cum": is_list,
    "long_run": optional(is_dict),
    "oil_sum": optional(is_dict),
    "copper_sum": optional(is_dict),
    "rho": optional(lambda x: isinstance(x, list) and len(x) == 2 and all(map(is_num, x))),
}
SUBSAMPLE = {
    "id": is_text,
    "label": is_text,
    "start": is_month,
    "end": is_month,
    "nobs": is_int,
    "h12": is_dict,
    "long_run": is_dict,
}
CONTEXT = {
    "months": list_of(is_month),
    "cpi_yoy_pct": NUMS,
    "policy_rate_pct": NUMS,
    "fx_12m_pct": NUMS,
}
PRICE_YEAR = {
    "year": is_year,
    "fx_dec_dec_pct": optional(is_num),
    "copper_avg_pct": optional(is_num),
}
WEO_CPI = {"vintage": optional(is_text), "years": list_of(is_year), "cpi_avg_pct": NUMS}

GROWTH = {
    "schema_version": is_int,
    "takeaway": is_text,
    "takeaway_weo": is_text,
    "takeaway_mix": is_text,
    "annual": is_list,
    "fit": is_dict,
    "robustness": is_list,
    "weo": is_dict,
    "boom_bust": is_list,
}
GROWTH_YEAR = {
    "year": is_year,
    "gdp_growth_pct": optional(is_num),
    "mxpi_pct": optional(is_num),
    "mxpi_lag_pct": optional(is_num),
    "weights": is_dict,
    "weights_source": one_of("comtrade", "interpolated", "nso"),
}
GROWTH_FIT = {
    "start": is_year,
    "end": is_year,
    "nobs": is_int,
    "maxlags": is_int,
    "r2": is_num,
    "const": is_dict,
    "mxpi": is_dict,
    "mxpi_l1": is_dict,
    "sum": is_dict,
    "p_l1_nonrobust": is_num,
    "p_l1_hc1": is_num,
}
ROBUSTNESS = {"drop": list_of(is_year), "nobs": is_int, "mxpi_l1": is_dict}
WEO_GROWTH = {"vintage": optional(is_text), "years": list_of(is_year), "gdp_growth_pct": NUMS}
BOOM_BUST = {
    "year": is_year,
    **{
        k: optional(is_num)
        for k in (
            "gdp_growth_pct",
            "cpi_pct",
            "fx_dec_dec_pct",
            "policy_rate_dec_pct",
            "fdi_pct_gdp",
            "current_account_pct_gdp",
            "gov_debt_pct_gdp",
            "exports_usd_bn",
            "copper_pct",
        )
    },
}

SOURCE = {
    "id": is_text,
    "publisher": is_text,
    "name": is_text,
    "method": optional(one_of("GET", "POST")),
    "url": lambda x: isinstance(x, str) and x.startswith("https://"),
    "body": lambda x: x is None or isinstance(x, (dict, str)),
    "frequency": is_text,
    "license": is_text,
    "redistribute": is_bool,
    "series": is_list,
}
SOURCE_SERIES = {
    "id": is_text,
    "label": is_text,
    "units": is_text,
    "first": optional(is_period),
    "last": optional(is_period),
    "status": one_of("ok", "stale"),
    "csv": optional(lambda x: isinstance(x, str) and re.fullmatch(r"csv/[\w.-]+\.csv", x)),
}


# -- checks --------------------------------------------------------------------------------
def _shape(obj: Any, schema: Mapping[str, Check], where: str, errors: list[str]) -> bool:
    """Exactly the schema's keys, each passing its check. Appends problems; True if none."""
    if not isinstance(obj, dict):
        errors.append(f"{where}: expected an object")
        return False
    before = len(errors)
    for key in sorted(set(schema) - set(obj)):
        errors.append(f"{where}: missing {key}")
    for key in sorted(set(obj) - set(schema)):
        errors.append(f"{where}: unexpected field {key}")
    for key, check in schema.items():
        if key in obj and not check(obj[key]):
            errors.append(f"{where}.{key}: bad value {str(obj[key])[:80]!r}")
    return len(errors) == before


def _items(objs: Any, schema: Mapping[str, Check], where: str, errors: list[str]) -> list[dict]:
    """The items of a list that pass :func:`_shape` (the others are reported)."""
    if not isinstance(objs, list):
        errors.append(f"{where}: expected a list")
        return []
    return [o for i, o in enumerate(objs) if _shape(o, schema, f"{where}[{i}]", errors)]


def _est(obj: Any, where: str, errors: list[str]) -> bool:
    if not _shape(obj, EST, where, errors):
        return False
    if not obj["lo"] <= obj["est"] <= obj["hi"] or obj["se"] < 0 or not 0 <= obj["p"] <= 1:
        errors.append(f"{where}: not lo <= est <= hi with se >= 0 and 0 <= p <= 1")
        return False
    return True


def _response(objs: Any, where: str, errors: list[str]) -> None:
    """A list of 13 estimates, one per horizon."""
    if not isinstance(objs, list) or len(objs) != len(HORIZONS):
        errors.append(f"{where}: expected {len(HORIZONS)} horizons")
        return
    for h, e in enumerate(objs):
        _est(e, f"{where}[{h}]", errors)


def _next(period: str) -> str:
    if len(period) == 4:
        return str(int(period) + 1)
    return (pd.Period(period, freq="M") + 1).strftime("%Y-%m")


def _contiguous(periods: list[str], where: str, errors: list[str]) -> None:
    """Months (or years) strictly increasing, none missing."""
    for a, b in zip(periods, periods[1:], strict=False):
        if len(a) != len(b) or _next(a) != b:
            errors.append(f"{where}: {b} does not follow {a}")
            return


def _parallel(obj: Mapping[str, Any], keys: list[str], where: str, errors: list[str]) -> None:
    lengths = {k: len(obj[k]) for k in keys if isinstance(obj.get(k), list)}
    if len(set(lengths.values())) > 1:
        errors.append(f"{where}: lists of different lengths {lengths}")


def _takeaways(name: str, page: Mapping[str, Any], errors: list[str]) -> None:
    """Each takeaway is what its template writes for the page's own numbers."""
    for key, template in TAKEAWAYS[name].items():
        try:
            expected = template(page)
        except Exception as exc:  # a template failing on bad data is a validation error
            errors.append(f"{name}.{key}: the template fails: {type(exc).__name__}: {exc}")
            continue
        if page.get(key) != expected:
            errors.append(f"{name}.{key}: does not match its numbers; expected {expected!r}")


def check_meta(meta: Any, errors: list[str]) -> None:
    if not _shape(meta, META, "meta", errors):
        return
    if meta["schema_version"] != SCHEMA_VERSION:
        errors.append(f"meta: schema_version {meta['schema_version']} != {SCHEMA_VERSION}")
    _shape(meta["through"], THROUGH, "meta.through", errors)
    _items(meta["sources"], META_SOURCE, "meta.sources", errors)
    _items(meta["reference"], REFERENCE, "meta.reference", errors)


def check_overview(overview: Any, pages: Mapping[str, Any], errors: list[str]) -> None:
    if not _shape(overview, OVERVIEW, "overview", errors):
        return
    for i, tile in enumerate(_items(overview["tiles"], TILE, "overview.tiles", errors)):
        where = f"overview.tiles[{i}]"
        for key in ("change", "detail"):
            if tile[key] is not None:
                _shape(tile[key], AMOUNT, f"{where}.{key}", errors)
        if _shape(tile["spark"], SPARK, f"{where}.spark", errors):
            dates = tile["spark"]["dates"]
            if not 2 <= len(dates) <= 36:
                errors.append(f"{where}.spark: {len(dates)} points (want 2 to 36)")
            if any(len(d) == 10 for d in dates):
                errors.append(f"{where}.spark: sparklines are monthly or annual")
            else:
                _contiguous(dates, f"{where}.spark.dates", errors)
            _parallel(tile["spark"], ["dates", "values"], f"{where}.spark", errors)
    cards = _items(overview["cards"], CARD, "overview.cards", errors)
    if [c["page"] for c in cards] != [p for p, _ in PAGES]:
        errors.append("overview.cards: one card per page, in order")
    for card in cards:
        page = pages.get(card["page"])
        if isinstance(page, dict) and card["takeaway"] != page.get("takeaway"):
            errors.append(
                f"overview.cards: the {card['page']} card's takeaway differs from its page's"
            )


def check_copper(page: Any, errors: list[str]) -> None:
    if not _shape(page, COPPER, "copper", errors):
        return
    if page["horizons"] != HORIZONS:
        errors.append("copper.horizons: expected 0..12")
    samples = _items(page["samples"], SAMPLE, "copper.samples", errors)
    if [s["id"] for s in samples] != COPPER_SAMPLES:
        errors.append(f"copper.samples: expected {COPPER_SAMPLES}")
    for i, s in enumerate(samples):
        _response(s["copper"], f"copper.samples[{i}].copper", errors)
        _est(s["coal_h12"], f"copper.samples[{i}].coal_h12", errors)
    if _shape(page["controls"], {"usd": is_dict, "cny": is_dict}, "copper.controls", errors):
        for key in ("usd", "cny"):
            _est(page["controls"][key], f"copper.controls.{key}", errors)
    fit = page["fit12"]
    if _shape(fit, FIT12, "copper.fit12", errors):
        _contiguous(fit["months"], "copper.fit12.months", errors)
        _parallel(fit, ["months", "actual_pct", "fitted_pct"], "copper.fit12", errors)
        if fit["nobs"] != len(fit["months"]):
            errors.append("copper.fit12: nobs differs from the number of months")
        for key in ("copper_t6", "coal_t6", "usd"):
            _est(fit[key], f"copper.fit12.{key}", errors)
    _items(page["episodes"], WINDOW, "copper.episodes", errors)
    if not errors:
        _takeaways("copper", page, errors)


def check_coal(page: Any, errors: list[str]) -> None:
    if not _shape(page, COAL, "coal", errors):
        return
    years = _items(page["annual"], COAL_YEAR, "coal.annual", errors)
    _contiguous([r["year"] for r in years], "coal.annual", errors)
    for r in years:
        parts = [r["dlog_value"], r["dlog_volume"], r["dlog_unit_value"]]
        if None in parts:
            continue
        if abs(parts[0] - parts[1] - parts[2]) > IDENTITY:
            errors.append(f"coal.annual {r['year']}: dlog value != dlog volume + dlog unit value")
    for before, r in zip(years, years[1:], strict=False):
        if before["partial"] or r["partial"] or int(r["year"]) != int(before["year"]) + 1:
            continue
        for change, level in COAL_CHANGES:
            a, b = before[level], r[level]
            if a is None or b is None or a <= 0 or b <= 0:
                continue
            implied = 100 * math.log(b / a)
            if r[change] is None or abs(r[change] - implied) > LEVELS:
                errors.append(
                    f"coal.annual {r['year']}: {change} is {r[change]}, but 100 x the log "
                    f"change of {level} is {implied:.6f}"
                )
    monthly = page["monthly"]
    if _shape(monthly, COAL_MONTHLY, "coal.monthly", errors):
        _contiguous(monthly["months"], "coal.monthly.months", errors)
        _parallel(monthly, list(COAL_MONTHLY), "coal.monthly", errors)
    _shape(page["border"], BORDER, "coal.border", errors)
    if not errors:
        _takeaways("coal", page, errors)


def check_prices(page: Any, errors: list[str]) -> None:
    if not _shape(page, PRICES, "prices", errors):
        return
    if page["horizons"] != HORIZONS:
        errors.append("prices.horizons: expected 0..12")
    specs = _items(page["specs"], SPEC, "prices.specs", errors)
    if [s["id"] for s in specs] != ["dl", "preferred"]:
        errors.append("prices.specs: expected dl, preferred")
    for i, s in enumerate(specs):
        _response(s["cum"], f"prices.specs[{i}].cum", errors)
        for key in ("long_run", "oil_sum", "copper_sum"):
            if s[key] is not None:
                _est(s[key], f"prices.specs[{i}].{key}", errors)
    for i, s in enumerate(_items(page["subsamples"], SUBSAMPLE, "prices.subsamples", errors)):
        _est(s["h12"], f"prices.subsamples[{i}].h12", errors)
        _est(s["long_run"], f"prices.subsamples[{i}].long_run", errors)
    context = page["context"]
    if _shape(context, CONTEXT, "prices.context", errors):
        _contiguous(context["months"], "prices.context.months", errors)
        _parallel(context, list(CONTEXT), "prices.context", errors)
    years = _items(page["years"], PRICE_YEAR, "prices.years", errors)
    _contiguous([r["year"] for r in years], "prices.years", errors)
    if _shape(page["weo"], WEO_CPI, "prices.weo", errors):
        _contiguous(page["weo"]["years"], "prices.weo.years", errors)
        _parallel(page["weo"], ["years", "cpi_avg_pct"], "prices.weo", errors)
    if not errors:
        _takeaways("prices", page, errors)


def check_growth(page: Any, errors: list[str]) -> None:
    if not _shape(page, GROWTH, "growth", errors):
        return
    annual = _items(page["annual"], GROWTH_YEAR, "growth.annual", errors)
    _contiguous([r["year"] for r in annual], "growth.annual", errors)
    for r in annual:
        w = r["weights"]
        if set(w) != GOODS or not all(is_num(v) and 0 <= v <= 1 for v in w.values()):
            errors.append(f"growth.annual {r['year']}: weights must be six shares in [0, 1]")
        elif abs(sum(w.values()) - 1) > IDENTITY:
            errors.append(f"growth.annual {r['year']}: weights sum to {sum(w.values())}, not 1")
    fit = page["fit"]
    if _shape(fit, GROWTH_FIT, "growth.fit", errors):
        for key in ("const", "mxpi", "mxpi_l1", "sum"):
            _est(fit[key], f"growth.fit.{key}", errors)
    for i, r in enumerate(_items(page["robustness"], ROBUSTNESS, "growth.robustness", errors)):
        _est(r["mxpi_l1"], f"growth.robustness[{i}].mxpi_l1", errors)
    if _shape(page["weo"], WEO_GROWTH, "growth.weo", errors):
        _contiguous(page["weo"]["years"], "growth.weo.years", errors)
        _parallel(page["weo"], ["years", "gdp_growth_pct"], "growth.weo", errors)
    boom = _items(page["boom_bust"], BOOM_BUST, "growth.boom_bust", errors)
    _contiguous([r["year"] for r in boom], "growth.boom_bust", errors)
    if not errors:
        _takeaways("growth", page, errors)


def check_sources(page: Any, errors: list[str]) -> None:
    for i, src in enumerate(_items(page, SOURCE, "sources", errors)):
        for row in _items(src["series"], SOURCE_SERIES, f"sources[{i}].series", errors):
            if row["csv"] is not None and row["csv"] != f"csv/{row['id']}.csv":
                errors.append(f"sources[{i}]: {row['id']} links {row['csv']}")


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def load(directory: Path, name: str, errors: list[str]) -> Any:
    path = directory / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError) as exc:
        errors.append(f"{name}.json: {exc}")
        return None


def validate(directory: str | Path) -> list[str]:
    """Every problem with the data files in ``directory`` (an empty list if none)."""
    directory = Path(directory)
    errors: list[str] = []
    data = {name: load(directory, name, errors) for name in FILES}
    if errors:
        return errors
    check_meta(data["meta"], errors)
    for name, check in (
        ("copper", check_copper),
        ("coal", check_coal),
        ("prices", check_prices),
        ("growth", check_growth),
    ):
        page_errors: list[str] = []
        check(data[name], page_errors)
        if isinstance(data[name], dict) and data[name].get("schema_version") != SCHEMA_VERSION:
            page_errors.append(f"{name}: schema_version is not {SCHEMA_VERSION}")
        errors += page_errors
    check_overview(data["overview"], data, errors)
    check_sources(data["sources"], errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.validate",
        description="Check the site's data files against the schema and its invariants.",
    )
    parser.add_argument("directory", help="the JSON directory, e.g. web/data")
    args = parser.parse_args(argv)
    errors = validate(args.directory)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"{len(errors)} problem(s) in {args.directory}", file=sys.stderr)
        return 1
    print(f"{args.directory}: ok")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
