"use client";

import { fixed, tickNum } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { Swatch, YGrid } from "./axes";
import { LIVE, bandIndex, pointerX, stepHandlers, useActive } from "./interaction";
import { vbarPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

/** One year: the change in value split exactly into volume and price (100 × log changes). */
export type DecompYear = { year: string; volume: number; price: number; total: number };

/** "+26.6" */
const signed = (v: number) => fixed(v, 1, true);

/**
 * Diverging stacked bars: each year's change in export value as the change in tonnes
 * (filled, accent) plus the change in price per tonne (outlined, context), positive parts
 * stacked up from zero and negative parts down, with a dot at the total. Filled against
 * outlined tells the parts apart without relying on colour. The two parts add up to the
 * dot exactly, because log changes add.
 */
export function DecompBars({
  years,
  volumeLabel,
  priceLabel,
  totalLabel,
  yLabel,
  label,
}: {
  years: DecompYear[];
  volumeLabel: string;
  priceLabel: string;
  totalLabel: string;
  yLabel: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  const n = years.length;
  const last = n - 1;
  const height = width < 520 ? 280 : 340;
  const top = 8;
  const bottom = height - 26;
  const left = 40;
  const right = width - 6;
  const band = (right - left) / n;
  const barW = Math.min(26, Math.round(band * 0.64 * 100) / 100);

  // Positive parts stack upward from zero, negative parts downward.
  const stacks = years.map((r) => {
    const up = Math.max(0, r.volume) + Math.max(0, r.price);
    const down = Math.min(0, r.volume) + Math.min(0, r.price);
    return { up, down };
  });
  const { ticks, domain } = niceTicks(
    Math.min(...stacks.map((s) => s.down)),
    Math.max(...stacks.map((s) => s.up)),
    width < 520 ? 5 : 7,
  );
  const y = linear(domain, [bottom, top]);
  const cx = (i: number) => Math.round((left + band * (i + 0.5)) * 100) / 100;
  const labelEvery = Math.ceil((textWidth("2020", 11) + 6) / band);

  /** The volume segment starts at zero; the price segment sits on top of it when the two
   * have the same sign, and starts at zero otherwise. */
  function segments(r: DecompYear) {
    const sameSign = r.volume * r.price > 0;
    const priceBase = sameSign ? r.volume : 0;
    return [
      { key: "volume", from: 0, to: r.volume, hollow: false, outer: !sameSign },
      { key: "price", from: priceBase, to: priceBase + r.price, hollow: true, outer: true },
    ];
  }

  const shown = active ?? last;
  const s = years[shown]!;
  const handlers = stepHandlers({
    indexAt: (e) => bandIndex(pointerX(e, width), left, right, n),
    active,
    setActive,
    clear,
    last,
    big: 5,
  });

  return (
    <div ref={root}>
      <div
        className="mb-3 flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:gap-x-6"
        {...LIVE}
      >
        <span className="text-muted num">{s.year}</span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--accent)" shape="box" />
          <span>
            {volumeLabel} <span className="num">{signed(s.volume)}</span>
          </span>
        </span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--context)" shape="hollow" />
          <span>
            <span className="text-muted">{priceLabel}</span>{" "}
            <span className="num">{signed(s.price)}</span>
          </span>
        </span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--fg)" shape="dot" />
          <span>
            {totalLabel} <span className="num">{signed(s.total)}</span>
          </span>
        </span>
      </div>
      <p className="mb-1 text-xs text-muted">{yLabel}</p>
      <div ref={ref}>
        <svg
          className="chart outline-none focus-visible:outline-2"
          role="img"
          aria-label={label}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          {...handlers}
        >
          <YGrid ticks={ticks} y={y} left={left} right={right} format={tickNum} />
          {years.map((r, i) => (
            <g key={r.year} opacity={active === null || active === i ? 1 : 0.45}>
              {segments(r).map((g) =>
                g.hollow ? (
                  // inset by half the stroke so the outline stays inside the bar's width
                  <path
                    key={g.key}
                    d={vbarPath(cx(i) - barW / 2 + 0.75, barW - 1.5, y(g.from), y(g.to), g.outer ? 3 : 0)}
                    fill="none"
                    stroke="var(--context)"
                    strokeWidth={1.5}
                  />
                ) : (
                  <path
                    key={g.key}
                    d={vbarPath(cx(i) - barW / 2, barW, y(g.from), y(g.to), g.outer ? 3 : 0)}
                    fill="var(--accent)"
                  />
                ),
              )}
              <circle
                cx={cx(i)}
                cy={y(r.total)}
                r={4}
                fill="var(--fg)"
                stroke="var(--bg)"
                strokeWidth={2}
              />
              {i % labelEvery === 0 && (
                <text
                  x={cx(i)}
                  y={bottom + 17}
                  textAnchor="middle"
                  fontSize={11}
                  className="text-muted num"
                >
                  {r.year}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
