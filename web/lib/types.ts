// Types for the JSON that `python -m pipeline.build` writes to web/data. They mirror the
// schema in pipeline/validate.py exactly. Rates and changes are in percent (12.5 is 12.5%),
// as the sources publish them; elasticities are unitless; months are "YYYY-MM" and years
// "YYYY". lib/data.ts checks each file against these at build time.

/** "YYYY-MM" */
export type Month = string;
/** "YYYY" */
export type Year = string;

/** An estimate with its HAC standard error, t, two-sided p and 95% t-based interval. */
export type Est = { est: number; se: number; t: number; p: number; lo: number; hi: number };

export const STATUSES = ["ok", "stale", "fallback"] as const;
export type Status = (typeof STATUSES)[number];

export const PAGE_IDS = ["copper", "coal", "prices", "growth"] as const;
export type PageId = (typeof PAGE_IDS)[number];

// -- meta.json -------------------------------------------------------------------------------
export type Meta = {
  schema_version: number;
  generated_at: string;
  through: {
    fx: Month;
    cpi: Month;
    /** "YYYY-MM-DD": the latest decision */
    policy_rate: string;
    commodities: Month;
    trade: Month;
    gdp: Year;
    /** "April 2026" */
    weo_vintage: string | null;
  };
  sources: { id: string; status: Status; last_obs: string | null; last_changed: string | null }[];
  stale: string[];
  revisions: Record<string, number>;
  /** The 2026-09 reference numbers next to the current ones (shown on /method). */
  reference: {
    id: string;
    label: string;
    page: PageId;
    reference: number;
    current: number | null;
  }[];
  versions: Record<string, string>;
};

// -- overview.json ---------------------------------------------------------------------------
export const TILE_UNITS = ["MNT per USD", "%", "USD per tonne", "million tonnes"] as const;
export type TileUnit = (typeof TILE_UNITS)[number];

export type Amount = { value: number; unit: string; label: string };

export type Tile = {
  id: string;
  label: string;
  value: number;
  unit: TileUnit;
  /** a year, month or day */
  period: string;
  change: Amount | null;
  detail: Amount | null;
  spark: { dates: string[]; values: (number | null)[] };
  source: string;
  status: Status;
};

export type Card = { page: PageId; title: string; takeaway: string };

export type Overview = { tiles: Tile[]; cards: Card[] };

// -- copper.json -----------------------------------------------------------------------------
export const COPPER_SAMPLES = [
  "full",
  "ex_gfc",
  "pre2017",
  "post2017",
  "post2017_ex_border",
] as const;
export type CopperSampleId = (typeof COPPER_SAMPLES)[number];

export type Window = { label: string; start: Month; end: Month };

export type CopperSample = {
  id: CopperSampleId;
  label: string;
  start: Month;
  end: Month;
  nobs: number;
  maxlags: number;
  r2: number;
  /** Σ of copper lags 0..h for h = 0..12; negative = higher copper, stronger tugrik */
  copper: Est[];
  coal_h12: Est;
};

export type Copper = {
  schema_version: number;
  takeaway: string;
  takeaway_fit: string;
  horizons: number[];
  samples: CopperSample[];
  controls: { usd: Est; cny: Est };
  fit12: {
    months: Month[];
    actual_pct: number[];
    fitted_pct: number[];
    nobs: number;
    r2: number;
    maxlags: number;
    copper_t6: Est;
    coal_t6: Est;
    usd: Est;
  };
  episodes: Window[];
};

// -- coal.json -------------------------------------------------------------------------------
export type CoalYear = {
  year: Year;
  partial: boolean;
  through: Month;
  value_musd: number;
  volume_mt: number;
  unit_value_usd_t: number | null;
  benchmark_usd_t: number | null;
  dlog_value: number | null;
  dlog_volume: number | null;
  dlog_unit_value: number | null;
  volume_vs_2019_pct: number | null;
};

export type Coal = {
  schema_version: number;
  takeaway: string;
  takeaway_gap: string;
  annual: CoalYear[];
  monthly: {
    months: Month[];
    volume_mt: (number | null)[];
    unit_value_usd_t: (number | null)[];
    benchmark_usd_t: (number | null)[];
  };
  border: { start: Month; end: Month };
};

// -- prices.json -----------------------------------------------------------------------------
export type PassThroughSpec = {
  id: "dl" | "preferred";
  label: string;
  start: Month;
  end: Month;
  nobs: number;
  maxlags: number;
  r2: number;
  /** cumulative pp of CPI per 1% depreciation, h = 0..12 */
  cum: Est[];
  long_run: Est | null;
  oil_sum: Est | null;
  copper_sum: Est | null;
  rho: [number, number] | null;
};

export type Subsample = {
  id: string;
  label: string;
  start: Month;
  end: Month;
  nobs: number;
  h12: Est;
  long_run: Est;
};

export type Prices = {
  schema_version: number;
  takeaway: string;
  takeaway_context: string;
  horizons: number[];
  specs: PassThroughSpec[];
  subsamples: Subsample[];
  context: {
    months: Month[];
    cpi_yoy_pct: (number | null)[];
    policy_rate_pct: (number | null)[];
    fx_12m_pct: (number | null)[];
  };
  years: { year: Year; fx_dec_dec_pct: number | null; copper_avg_pct: number | null }[];
  weo: { vintage: string | null; years: Year[]; cpi_avg_pct: (number | null)[] };
};

// -- growth.json -----------------------------------------------------------------------------
export const GOODS = ["copper", "coal", "gold", "iron_ore", "oil", "zinc"] as const;
export type Good = (typeof GOODS)[number];

export const WEIGHT_SOURCES = ["comtrade", "interpolated", "nso"] as const;

export type GrowthYear = {
  year: Year;
  gdp_growth_pct: number | null;
  mxpi_pct: number | null;
  mxpi_lag_pct: number | null;
  weights: Record<Good, number>;
  weights_source: (typeof WEIGHT_SOURCES)[number];
};

export type BoomBustYear = {
  year: Year;
  gdp_growth_pct: number | null;
  cpi_pct: number | null;
  fx_dec_dec_pct: number | null;
  policy_rate_dec_pct: number | null;
  fdi_pct_gdp: number | null;
  current_account_pct_gdp: number | null;
  gov_debt_pct_gdp: number | null;
  exports_usd_bn: number | null;
  copper_pct: number | null;
};

export type Growth = {
  schema_version: number;
  takeaway: string;
  takeaway_weo: string;
  takeaway_mix: string;
  annual: GrowthYear[];
  fit: {
    start: Year;
    end: Year;
    nobs: number;
    maxlags: number;
    r2: number;
    const: Est;
    mxpi: Est;
    mxpi_l1: Est;
    sum: Est;
    p_l1_nonrobust: number;
    p_l1_hc1: number;
  };
  robustness: { drop: Year[]; nobs: number; mxpi_l1: Est }[];
  weo: { vintage: string | null; years: Year[]; gdp_growth_pct: (number | null)[] };
  boom_bust: BoomBustYear[];
};

// -- sources.json ----------------------------------------------------------------------------
export type SourceSeries = {
  id: string;
  label: string;
  units: string;
  first: string | null;
  last: string | null;
  status: "ok" | "stale";
  /** "csv/<id>.csv", or null when the series may not be redistributed */
  csv: string | null;
};

export type Source = {
  id: string;
  publisher: string;
  name: string;
  /** null for the project's derived series, which are not fetched */
  method: "GET" | "POST" | null;
  url: string;
  body: Record<string, unknown> | string | null;
  frequency: string;
  license: string;
  redistribute: boolean;
  series: SourceSeries[];
};
