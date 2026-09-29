// Reads web/data at build time (server components only) and checks every file against the
// schema in lib/types.ts. Any missing or ill-typed field throws, so `next build` fails on bad
// data instead of publishing a broken page. pipeline/validate.py runs stricter checks
// (exact field sets, 6-decimal rounding, the takeaway templates) before the files are
// written; these are the ones the pages rely on.

import fs from "node:fs";
import path from "node:path";

import {
  COPPER_SAMPLES,
  type Coal,
  type Copper,
  type Est,
  GOODS,
  type Growth,
  type Meta,
  type Overview,
  PAGE_IDS,
  type PageId,
  type Prices,
  type Source,
  STATUSES,
  TILE_UNITS,
  WEIGHT_SOURCES,
} from "./types";

export type * from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const SCHEMA_VERSION = 1;
const HORIZONS = 13; // months 0..12
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const YEAR = /^\d{4}$/;
const DATE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
const PERIOD = /^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$/;
const SUM_TOLERANCE = 1e-6; // identities after 6-decimal rounding

class DataError extends Error {
  constructor(where: string, problem: string) {
    super(`web/data: ${where}: ${problem}`);
    this.name = "DataError";
  }
}

// -- field checks ------------------------------------------------------------------------
type Obj = Record<string, unknown>;

function obj(x: unknown, where: string): Obj {
  if (typeof x !== "object" || x === null || Array.isArray(x)) {
    throw new DataError(where, "expected an object");
  }
  return x as Obj;
}

function field(o: Obj, key: string, where: string): unknown {
  if (!(key in o)) throw new DataError(where, `missing field "${key}"`);
  return o[key];
}

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function num(o: Obj, key: string, where: string): number {
  const v = field(o, key, where);
  if (!isNum(v)) {
    throw new DataError(`${where}.${key}`, `expected a finite number, got ${JSON.stringify(v)}`);
  }
  return v;
}

function int(o: Obj, key: string, where: string): number {
  const v = num(o, key, where);
  if (!Number.isInteger(v)) throw new DataError(`${where}.${key}`, "expected an integer");
  return v;
}

function numOrNull(o: Obj, key: string, where: string): number | null {
  return field(o, key, where) === null ? null : num(o, key, where);
}

function str(o: Obj, key: string, where: string, pattern?: RegExp): string {
  const v = field(o, key, where);
  if (typeof v !== "string") throw new DataError(`${where}.${key}`, "expected a string");
  if (pattern && !pattern.test(v)) {
    throw new DataError(`${where}.${key}`, `${JSON.stringify(v)} does not match ${pattern}`);
  }
  return v;
}

/** A non-empty string: every takeaway and label. */
function text(o: Obj, key: string, where: string): string {
  const v = str(o, key, where);
  if (v.trim() === "") throw new DataError(`${where}.${key}`, "is empty");
  return v;
}

function strOrNull(o: Obj, key: string, where: string, pattern?: RegExp): string | null {
  return field(o, key, where) === null ? null : str(o, key, where, pattern);
}

function bool(o: Obj, key: string, where: string): boolean {
  const v = field(o, key, where);
  if (typeof v !== "boolean") throw new DataError(`${where}.${key}`, "expected a boolean");
  return v;
}

function oneOf<T extends string>(o: Obj, key: string, allowed: readonly T[], where: string): T {
  const v = str(o, key, where);
  if (!(allowed as readonly string[]).includes(v)) {
    throw new DataError(`${where}.${key}`, `${JSON.stringify(v)} is not one of ${allowed}`);
  }
  return v as T;
}

function list(o: Obj, key: string, where: string): unknown[] {
  const v = field(o, key, where);
  if (!Array.isArray(v)) throw new DataError(`${where}.${key}`, "expected an array");
  return v;
}

function numbers(o: Obj, key: string, where: string): number[] {
  return list(o, key, where).map((v, i) => {
    if (!isNum(v)) throw new DataError(`${where}.${key}[${i}]`, "expected a finite number");
    return v;
  });
}

/** Numbers where a missing observation is null. */
function numbersOrNull(o: Obj, key: string, where: string): (number | null)[] {
  return list(o, key, where).map((v, i) => {
    if (v !== null && !isNum(v)) {
      throw new DataError(`${where}.${key}[${i}]`, "expected a finite number or null");
    }
    return v;
  });
}

function strings(o: Obj, key: string, where: string, pattern?: RegExp): string[] {
  return list(o, key, where).map((v, i) => {
    if (typeof v !== "string" || (pattern && !pattern.test(v))) {
      throw new DataError(`${where}.${key}[${i}]`, `unexpected value ${JSON.stringify(v)}`);
    }
    return v;
  });
}

function stringMap(o: Obj, key: string, where: string): Record<string, string> {
  const m = obj(field(o, key, where), `${where}.${key}`);
  for (const [k, v] of Object.entries(m)) {
    if (typeof v !== "string") throw new DataError(`${where}.${key}.${k}`, "expected a string");
  }
  return m as Record<string, string>;
}

function sameLength(where: string, n: number, arrays: Record<string, unknown[]>): void {
  for (const [name, a] of Object.entries(arrays)) {
    if (a.length !== n) {
      throw new DataError(where, `${name} has ${a.length} entries, expected ${n}`);
    }
  }
}

/** The number of a month ("YYYY-MM") or year ("YYYY"), so consecutive periods differ by 1. */
function periodIndex(p: string): number {
  return p.length === 4 ? Number(p) : Number(p.slice(0, 4)) * 12 + Number(p.slice(5, 7)) - 1;
}

/** Months (or years) strictly increasing with none missing. */
function contiguous(periods: string[], where: string): void {
  for (let i = 1; i < periods.length; i++) {
    const a = periods[i - 1]!;
    const b = periods[i]!;
    if (a.length !== b.length || periodIndex(b) !== periodIndex(a) + 1) {
      throw new DataError(where, `${b} does not follow ${a}`);
    }
  }
}

function schemaVersion(o: Obj, where: string): void {
  const v = int(o, "schema_version", where);
  if (v !== SCHEMA_VERSION) {
    throw new DataError(`${where}.schema_version`, `${v}, but this site reads ${SCHEMA_VERSION}`);
  }
}

/** An estimate: {est, se, t, p, lo, hi} with lo <= est <= hi. */
function est(x: unknown, where: string): Est {
  const o = obj(x, where);
  const e = {
    est: num(o, "est", where),
    se: num(o, "se", where),
    t: num(o, "t", where),
    p: num(o, "p", where),
    lo: num(o, "lo", where),
    hi: num(o, "hi", where),
  };
  if (!(e.lo <= e.est && e.est <= e.hi)) throw new DataError(where, "expected lo <= est <= hi");
  if (e.se < 0 || e.p < 0 || e.p > 1) throw new DataError(where, "bad se or p");
  return e;
}

function estField(o: Obj, key: string, where: string): Est {
  return est(field(o, key, where), `${where}.${key}`);
}

function estOrNull(o: Obj, key: string, where: string): Est | null {
  return field(o, key, where) === null ? null : estField(o, key, where);
}

/** A cumulative response: one estimate per horizon 0..12. */
function response(o: Obj, key: string, where: string): Est[] {
  const items = list(o, key, where);
  if (items.length !== HORIZONS) {
    throw new DataError(`${where}.${key}`, `${items.length} horizons, expected ${HORIZONS}`);
  }
  return items.map((e, h) => est(e, `${where}.${key}[${h}]`));
}

function horizons(o: Obj, where: string): void {
  const h = numbers(o, "horizons", where);
  if (h.length !== HORIZONS || h.some((v, i) => v !== i)) {
    throw new DataError(`${where}.horizons`, "expected 0..12");
  }
}

function records(o: Obj, key: string, where: string): [Obj, string][] {
  return list(o, key, where).map((x, i) => {
    const w = `${where}.${key}[${i}]`;
    return [obj(x, w), w];
  });
}

// -- record checks -----------------------------------------------------------------------
export function assertMeta(x: unknown, where = "meta.json"): asserts x is Meta {
  const o = obj(x, where);
  schemaVersion(o, where);
  str(o, "generated_at", where, DATE);
  const t = obj(field(o, "through", where), `${where}.through`);
  const tw = `${where}.through`;
  for (const k of ["fx", "cpi", "commodities", "trade"]) str(t, k, tw, MONTH);
  str(t, "policy_rate", tw, DATE);
  str(t, "gdp", tw, YEAR);
  strOrNull(t, "weo_vintage", tw);
  for (const [s, w] of records(o, "sources", where)) {
    text(s, "id", w);
    oneOf(s, "status", STATUSES, w);
    strOrNull(s, "last_obs", w, PERIOD);
    strOrNull(s, "last_changed", w, DATE);
  }
  strings(o, "stale", where);
  const rev = obj(field(o, "revisions", where), `${where}.revisions`);
  for (const k of Object.keys(rev)) int(rev, k, `${where}.revisions`);
  for (const [r, w] of records(o, "reference", where)) {
    text(r, "id", w);
    text(r, "label", w);
    oneOf(r, "page", PAGE_IDS, w);
    num(r, "reference", w);
    numOrNull(r, "current", w);
  }
  stringMap(o, "versions", where);
}

export function assertOverview(x: unknown, where = "overview.json"): asserts x is Overview {
  const o = obj(x, where);
  for (const [t, w] of records(o, "tiles", where)) {
    text(t, "id", w);
    text(t, "label", w);
    num(t, "value", w);
    oneOf(t, "unit", TILE_UNITS, w);
    str(t, "period", w, PERIOD);
    for (const k of ["change", "detail"]) {
      if (field(t, k, w) === null) continue;
      const a = obj(t[k], `${w}.${k}`);
      num(a, "value", `${w}.${k}`);
      text(a, "unit", `${w}.${k}`);
      text(a, "label", `${w}.${k}`);
    }
    const s = obj(field(t, "spark", w), `${w}.spark`);
    const dates = strings(s, "dates", `${w}.spark`, PERIOD);
    sameLength(`${w}.spark`, dates.length, { values: numbersOrNull(s, "values", `${w}.spark`) });
    if (dates.length < 2) throw new DataError(`${w}.spark`, "needs at least 2 points");
    contiguous(dates, `${w}.spark.dates`);
    text(t, "source", w);
    oneOf(t, "status", STATUSES, w);
  }
  const cards = records(o, "cards", where);
  cards.forEach(([c, w]) => {
    oneOf(c, "page", PAGE_IDS, w);
    text(c, "title", w);
    text(c, "takeaway", w);
  });
  if (cards.map(([c]) => c.page).join() !== PAGE_IDS.join()) {
    throw new DataError(`${where}.cards`, `expected one card per page: ${PAGE_IDS}`);
  }
}

export function assertCopper(x: unknown, where = "copper.json"): asserts x is Copper {
  const o = obj(x, where);
  schemaVersion(o, where);
  text(o, "takeaway", where);
  text(o, "takeaway_fit", where);
  horizons(o, where);
  const samples = records(o, "samples", where);
  samples.forEach(([s, w]) => {
    oneOf(s, "id", COPPER_SAMPLES, w);
    text(s, "label", w);
    str(s, "start", w, MONTH);
    str(s, "end", w, MONTH);
    int(s, "nobs", w);
    int(s, "maxlags", w);
    num(s, "r2", w);
    response(s, "copper", w);
    estField(s, "coal_h12", w);
  });
  if (samples.map(([s]) => s.id).join() !== COPPER_SAMPLES.join()) {
    throw new DataError(`${where}.samples`, `expected ${COPPER_SAMPLES}`);
  }
  const c = obj(field(o, "controls", where), `${where}.controls`);
  estField(c, "usd", `${where}.controls`);
  estField(c, "cny", `${where}.controls`);

  const f = obj(field(o, "fit12", where), `${where}.fit12`);
  const fw = `${where}.fit12`;
  const months = strings(f, "months", fw, MONTH);
  contiguous(months, `${fw}.months`);
  sameLength(fw, months.length, {
    actual_pct: numbers(f, "actual_pct", fw),
    fitted_pct: numbers(f, "fitted_pct", fw),
  });
  if (int(f, "nobs", fw) !== months.length) {
    throw new DataError(`${fw}.nobs`, "differs from the number of months");
  }
  num(f, "r2", fw);
  int(f, "maxlags", fw);
  for (const k of ["copper_t6", "coal_t6", "usd"]) estField(f, k, fw);

  for (const [e, w] of records(o, "episodes", where)) {
    text(e, "label", w);
    str(e, "start", w, MONTH);
    str(e, "end", w, MONTH);
  }
}

export function assertCoal(x: unknown, where = "coal.json"): asserts x is Coal {
  const o = obj(x, where);
  schemaVersion(o, where);
  text(o, "takeaway", where);
  text(o, "takeaway_gap", where);
  const years: string[] = [];
  for (const [r, w] of records(o, "annual", where)) {
    years.push(str(r, "year", w, YEAR));
    bool(r, "partial", w);
    str(r, "through", w, MONTH);
    num(r, "value_musd", w);
    num(r, "volume_mt", w);
    for (const k of ["unit_value_usd_t", "benchmark_usd_t", "volume_vs_2019_pct"]) {
      numOrNull(r, k, w);
    }
    const v = numOrNull(r, "dlog_value", w);
    const q = numOrNull(r, "dlog_volume", w);
    const p = numOrNull(r, "dlog_unit_value", w);
    // The decomposition is an identity: dlog value = dlog volume + dlog price per tonne.
    if (v !== null && q !== null && p !== null && Math.abs(v - q - p) > SUM_TOLERANCE) {
      throw new DataError(w, "dlog_value != dlog_volume + dlog_unit_value");
    }
  }
  contiguous(years, `${where}.annual`);

  const m = obj(field(o, "monthly", where), `${where}.monthly`);
  const mw = `${where}.monthly`;
  const months = strings(m, "months", mw, MONTH);
  contiguous(months, `${mw}.months`);
  sameLength(mw, months.length, {
    volume_mt: numbersOrNull(m, "volume_mt", mw),
    unit_value_usd_t: numbersOrNull(m, "unit_value_usd_t", mw),
    benchmark_usd_t: numbersOrNull(m, "benchmark_usd_t", mw),
  });
  const b = obj(field(o, "border", where), `${where}.border`);
  str(b, "start", `${where}.border`, MONTH);
  str(b, "end", `${where}.border`, MONTH);
}

export function assertPrices(x: unknown, where = "prices.json"): asserts x is Prices {
  const o = obj(x, where);
  schemaVersion(o, where);
  text(o, "takeaway", where);
  text(o, "takeaway_context", where);
  horizons(o, where);
  const specs = records(o, "specs", where);
  specs.forEach(([s, w]) => {
    oneOf(s, "id", ["dl", "preferred"] as const, w);
    text(s, "label", w);
    str(s, "start", w, MONTH);
    str(s, "end", w, MONTH);
    int(s, "nobs", w);
    int(s, "maxlags", w);
    num(s, "r2", w);
    response(s, "cum", w);
    for (const k of ["long_run", "oil_sum", "copper_sum"]) estOrNull(s, k, w);
    if (field(s, "rho", w) !== null && numbers(s, "rho", w).length !== 2) {
      throw new DataError(`${w}.rho`, "expected [rho1, rho2] or null");
    }
  });
  if (specs.map(([s]) => s.id).join() !== "dl,preferred") {
    throw new DataError(`${where}.specs`, "expected dl, preferred");
  }
  for (const [s, w] of records(o, "subsamples", where)) {
    text(s, "id", w);
    text(s, "label", w);
    str(s, "start", w, MONTH);
    str(s, "end", w, MONTH);
    int(s, "nobs", w);
    estField(s, "h12", w);
    estField(s, "long_run", w);
  }
  const c = obj(field(o, "context", where), `${where}.context`);
  const cw = `${where}.context`;
  const months = strings(c, "months", cw, MONTH);
  contiguous(months, `${cw}.months`);
  sameLength(cw, months.length, {
    cpi_yoy_pct: numbersOrNull(c, "cpi_yoy_pct", cw),
    policy_rate_pct: numbersOrNull(c, "policy_rate_pct", cw),
    fx_12m_pct: numbersOrNull(c, "fx_12m_pct", cw),
  });
  const years: string[] = [];
  for (const [r, w] of records(o, "years", where)) {
    years.push(str(r, "year", w, YEAR));
    numOrNull(r, "fx_dec_dec_pct", w);
    numOrNull(r, "copper_avg_pct", w);
  }
  contiguous(years, `${where}.years`);
  const weo = obj(field(o, "weo", where), `${where}.weo`);
  strOrNull(weo, "vintage", `${where}.weo`);
  const wy = strings(weo, "years", `${where}.weo`, YEAR);
  contiguous(wy, `${where}.weo.years`);
  sameLength(`${where}.weo`, wy.length, {
    cpi_avg_pct: numbersOrNull(weo, "cpi_avg_pct", `${where}.weo`),
  });
}

export function assertGrowth(x: unknown, where = "growth.json"): asserts x is Growth {
  const o = obj(x, where);
  schemaVersion(o, where);
  text(o, "takeaway", where);
  text(o, "takeaway_weo", where);
  text(o, "takeaway_mix", where);
  const years: string[] = [];
  for (const [r, w] of records(o, "annual", where)) {
    years.push(str(r, "year", w, YEAR));
    for (const k of ["gdp_growth_pct", "mxpi_pct", "mxpi_lag_pct"]) numOrNull(r, k, w);
    const weights = obj(field(r, "weights", w), `${w}.weights`);
    let total = 0;
    for (const g of GOODS) {
      const share = num(weights, g, `${w}.weights`);
      if (share < 0 || share > 1) throw new DataError(`${w}.weights.${g}`, "not in [0, 1]");
      total += share;
    }
    if (Object.keys(weights).length !== GOODS.length || Math.abs(total - 1) > SUM_TOLERANCE) {
      throw new DataError(`${w}.weights`, `expected ${GOODS} summing to 1, got ${total}`);
    }
    oneOf(r, "weights_source", WEIGHT_SOURCES, w);
  }
  contiguous(years, `${where}.annual`);

  const f = obj(field(o, "fit", where), `${where}.fit`);
  const fw = `${where}.fit`;
  str(f, "start", fw, YEAR);
  str(f, "end", fw, YEAR);
  int(f, "nobs", fw);
  int(f, "maxlags", fw);
  num(f, "r2", fw);
  for (const k of ["const", "mxpi", "mxpi_l1", "sum"]) estField(f, k, fw);
  num(f, "p_l1_nonrobust", fw);
  num(f, "p_l1_hc1", fw);

  for (const [r, w] of records(o, "robustness", where)) {
    strings(r, "drop", w, YEAR);
    int(r, "nobs", w);
    estField(r, "mxpi_l1", w);
  }
  const weo = obj(field(o, "weo", where), `${where}.weo`);
  strOrNull(weo, "vintage", `${where}.weo`);
  const wy = strings(weo, "years", `${where}.weo`, YEAR);
  contiguous(wy, `${where}.weo.years`);
  sameLength(`${where}.weo`, wy.length, {
    gdp_growth_pct: numbersOrNull(weo, "gdp_growth_pct", `${where}.weo`),
  });
  const boom: string[] = [];
  for (const [r, w] of records(o, "boom_bust", where)) {
    boom.push(str(r, "year", w, YEAR));
    for (const k of [
      "gdp_growth_pct",
      "cpi_pct",
      "fx_dec_dec_pct",
      "policy_rate_dec_pct",
      "fdi_pct_gdp",
      "current_account_pct_gdp",
      "gov_debt_pct_gdp",
      "exports_usd_bn",
      "copper_pct",
    ]) {
      numOrNull(r, k, w);
    }
  }
  contiguous(boom, `${where}.boom_bust`);
}

export function assertSources(x: unknown, where = "sources.json"): asserts x is Source[] {
  if (!Array.isArray(x)) throw new DataError(where, "expected an array");
  x.forEach((item, i) => {
    const w = `${where}[${i}]`;
    const s = obj(item, w);
    text(s, "id", w);
    text(s, "publisher", w);
    text(s, "name", w);
    if (field(s, "method", w) !== null) oneOf(s, "method", ["GET", "POST"] as const, w);
    str(s, "url", w, /^https:\/\//);
    text(s, "frequency", w);
    text(s, "license", w);
    bool(s, "redistribute", w);
    field(s, "body", w);
    for (const [r, rw] of records(s, "series", w)) {
      const id = text(r, "id", rw);
      text(r, "label", rw);
      text(r, "units", rw);
      strOrNull(r, "first", rw, PERIOD);
      strOrNull(r, "last", rw, PERIOD);
      oneOf(r, "status", ["ok", "stale"] as const, rw);
      const csv = strOrNull(r, "csv", rw);
      if (csv !== null && csv !== `csv/${id}.csv`) {
        throw new DataError(`${rw}.csv`, `expected csv/${id}.csv`);
      }
    }
  });
}

// -- loading -----------------------------------------------------------------------------
function readJson(rel: string): unknown {
  const file = path.join(DATA_DIR, rel);
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (err) {
    throw new DataError(rel, `cannot read (${(err as Error).message})`);
  }
}

/** Reads and checks one file once per build. */
function loader<T>(file: string, check: (x: unknown, where: string) => void): () => T {
  let cached: T | undefined;
  return () => {
    if (cached === undefined) {
      const x = readJson(file);
      check(x, file);
      cached = x as T;
    }
    return cached;
  };
}

export const getMeta = loader<Meta>("meta.json", assertMeta);
export const getCopper = loader<Copper>("copper.json", assertCopper);
export const getCoal = loader<Coal>("coal.json", assertCoal);
export const getPrices = loader<Prices>("prices.json", assertPrices);
export const getGrowth = loader<Growth>("growth.json", assertGrowth);
export const getSources = loader<Source[]>("sources.json", assertSources);

const readOverview = loader<Overview>("overview.json", assertOverview);

/** The overview, checked against the other files: every card repeats its page's takeaway,
 * and every tile's source is one of sources.json. */
export function getOverview(): Overview {
  const o = readOverview();
  const takeaways: Record<string, string> = {
    copper: getCopper().takeaway,
    coal: getCoal().takeaway,
    prices: getPrices().takeaway,
    growth: getGrowth().takeaway,
  };
  for (const c of o.cards) {
    if (c.takeaway !== takeaways[c.page]) {
      throw new DataError("overview.json.cards", `the ${c.page} card differs from its page`);
    }
  }
  const ids = new Set(getSources().map((s) => s.id));
  for (const t of o.tiles) {
    if (!ids.has(t.source)) {
      throw new DataError("overview.json.tiles", `${t.id}: unknown source ${t.source}`);
    }
  }
  return o;
}

/** An analysis page's title, as its overview card gives it. */
export function pageTitle(page: PageId): string {
  return getOverview().cards.find((c) => c.page === page)!.title;
}
