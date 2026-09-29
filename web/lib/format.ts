// Number and date formatting shared by every page and chart. Rates and changes arrive in
// percent (12.5 is 12.5%), as the sources publish them, not as decimals; negatives get a
// typographic minus (U+2212), never a hyphen.

import type { Month } from "./types";

export const MINUS = "−";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * `x` with `digits` decimals and a typographic minus. With `sign`, positives get a "+".
 * A value that rounds to zero gets no sign at all ("0.0", never "+0.0" or "−0.0"), so a
 * rounded number cannot seem to disagree in sign with its interval.
 */
export function fixed(x: number, digits: number, sign = false): string {
  let s = Math.abs(x).toFixed(digits);
  const zero = Number(s) === 0;
  if (zero) return s;
  if (x < 0) s = MINUS + s;
  else if (sign) s = "+" + s;
  return s;
}

/** Thousands separated by commas: 3594.47 -> "3,594"; 14326 -> "14,326". */
export function grouped(x: number, digits = 0): string {
  const s = fixed(x, digits);
  const negative = s.startsWith(MINUS);
  const [whole, frac] = (negative ? s.slice(1) : s).split(".");
  const body = whole!.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (negative ? MINUS : "") + body + (frac === undefined ? "" : `.${frac}`);
}

/** A percent that is already in percent: 12.5 -> "12.5%"; with `sign`, "+12.5%". */
export function pct(x: number, digits = 1, sign = false): string {
  return `${fixed(x, digits, sign)}%`;
}

/** Signed percent: "+1.4%", "−2.1%". */
export function spct(x: number, digits = 1): string {
  return pct(x, digits, true);
}

/** Percentage points: "+0.5 pp". */
export function pp(x: number, digits = 1, sign = true): string {
  return `${fixed(x, digits, sign)} pp`;
}

/** A t-statistic: "1.03", "−2.60". */
export function tstat(x: number): string {
  return fixed(x, 2);
}

/** A plain decimal with a typographic minus: elasticities, R², ratios. */
export function dec(x: number, digits = 2, sign = false): string {
  return fixed(x, digits, sign);
}

/** A p-value: "0.31", "0.016", "< 0.001". */
export function pval(p: number): string {
  return p < 0.001 ? "< 0.001" : p.toFixed(p < 0.1 ? 3 : 2);
}

/** US dollars per tonne: 75.48 -> "$75/t"; 14326 -> "$14,326/t". */
export function usdT(x: number): string {
  return `$${grouped(x)}/t`;
}

/** Million tonnes: 9.423 -> "9.4 Mt". */
export function mt(x: number): string {
  return `${fixed(x, 1)} Mt`;
}

/** MNT per US dollar with a thousands separator: 3594.47 -> "3,594". */
export function mnt(x: number): string {
  return grouped(x);
}

/**
 * A value in one of the units the overview tiles use: "3,594" (MNT per USD), "12.5%",
 * "+3.7 pp", "$14,326/t", "9.4 Mt". With `sign`, percent and pp values get a "+".
 */
export function amount(value: number, unit: string, sign = false): string {
  switch (unit) {
    case "%":
      return pct(value, 1, sign);
    case "pp":
      return pp(value, 1, sign);
    case "USD per tonne":
      return usdT(value);
    case "million tonnes":
      return mt(value);
    case "MNT per USD":
      return mnt(value);
    default:
      return `${fixed(value, 1, sign)} ${unit}`;
  }
}

/** "2026-08" -> "Aug 2026" */
export function month(m: Month): string {
  const [y, mm] = m.split("-");
  return `${MONTHS[Number(mm) - 1] ?? mm} ${y}`;
}

/** "2026-08" -> 24319, a month count that subtracts cleanly. */
export function monthIndex(m: Month): number {
  return Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - 1;
}

/** "2026-09-17" -> "17 Sep 2026" */
export function date(d: string): string {
  const [y, m, day] = d.split("-");
  return `${Number(day)} ${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

/** A year, month or day as the site writes it: "2025", "Aug 2026", "17 Sep 2026". */
export function period(p: string): string {
  if (p.length === 4) return p;
  if (p.length === 7) return month(p);
  return date(p);
}

/** A WEO vintage as the site writes it: "April 2026" -> "Apr 2026". */
export function vintage(v: string): string {
  return v.replace(/^([A-Za-z]{3})[A-Za-z]*/, "$1");
}

/** "Sep 2008 – Jun 2009" */
export function span(start: Month, end: Month): string {
  return `${month(start)} – ${month(end)}`;
}

/** An axis tick for a plain number with as few decimals as it needs. */
export function tickNum(x: number): string {
  const r = Math.round(x * 100) / 100;
  const digits = Number.isInteger(r) ? 0 : Number.isInteger(Math.round(r * 10 * 1e6) / 1e6) ? 1 : 2;
  return fixed(r, digits);
}

/** An axis tick in percent with as few decimals as it needs: 5 -> "5%", 2.5 -> "2.5%". */
export function tickPct(x: number): string {
  return `${tickNum(x)}%`;
}

/**
 * How a chart writes its values. Charts are client components, so pages pass one of these
 * names rather than a formatting function.
 */
export type ValueKind = "pct" | "num" | "mt" | "usd_t" | "share";

/** A value in a chart readout. */
export function fmt(kind: ValueKind, x: number): string {
  switch (kind) {
    case "pct":
      return pct(x);
    case "num":
      return dec(x);
    case "mt":
      return mt(x);
    case "usd_t":
      return usdT(x);
    case "share":
      return `${fixed(100 * x, 0)}%`;
  }
}

/** The same value on an axis tick. */
export function tick(kind: ValueKind, x: number): string {
  switch (kind) {
    case "pct":
      return tickPct(x);
    case "num":
      return tickNum(x);
    case "mt":
      return tickNum(x);
    case "usd_t":
      return `$${tickNum(x)}`;
    case "share":
      return `${tickNum(100 * x)}%`;
  }
}

/** A 95% interval: "0.7 to 3.4" with `f` applied to both ends. */
export function interval(lo: number, hi: number, f: (x: number) => string): string {
  return `${f(lo)} to ${f(hi)}`;
}

/** ["a", "b", "c"] -> "a, b and c" */
export function listing(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}
