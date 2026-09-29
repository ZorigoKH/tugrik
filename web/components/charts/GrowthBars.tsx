"use client";

import { pct, tickPct } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { Swatch, YGrid } from "./axes";
import { LIVE, bandIndex, pointerX, stepHandlers, useActive } from "./interaction";
import { vbarPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

export type GrowthYear = { year: string; value: number; forecast: boolean };

/**
 * One bar per year from zero: actual growth filled in the accent, forecasts hollow in the
 * context gray under a label naming whose forecast it is. The readout names the hovered,
 * tapped or keyed year; at rest, the last actual year.
 */
export function GrowthBars({
  years,
  forecastLabel,
  yLabel,
  label,
}: {
  years: GrowthYear[];
  forecastLabel: string;
  yLabel: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  const n = years.length;
  const height = width < 520 ? 250 : 300;
  const top = 22;
  const bottom = height - 26;
  const left = 40;
  const right = width - 6;
  const band = (right - left) / n;
  const barW = Math.min(18, Math.round(band * 0.68 * 100) / 100);
  const { ticks, domain } = niceTicks(
    Math.min(0, ...years.map((r) => r.value)),
    Math.max(0, ...years.map((r) => r.value)),
    5,
  );
  const y = linear(domain, [bottom, top]);
  const cx = (i: number) => Math.round((left + band * (i + 0.5)) * 100) / 100;
  const labelEvery = Math.ceil((textWidth("2020", 11) + 8) / band);
  const lastActual = years.findLastIndex((r) => !r.forecast);
  const firstForecast = years.findIndex((r) => r.forecast);

  const shown = active ?? lastActual;
  const s = years[shown]!;
  const handlers = stepHandlers({
    indexAt: (e) => bandIndex(pointerX(e, width), left, right, n),
    active,
    setActive,
    clear,
    last: n - 1,
    rest: lastActual,
    big: 5,
  });

  return (
    <div ref={root}>
      <div className="mb-3 flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:gap-x-6">
        <span className="flex items-center gap-2">
          <Swatch color="var(--accent)" shape="box" />
          actual
        </span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--context)" shape="hollow" />
          <span className="text-muted">{forecastLabel}</span>
        </span>
        <span {...LIVE}>
          <span className="num text-muted">{s.year}</span>{" "}
          <span className="num">{pct(s.value)}</span>
          {s.forecast && <span className="text-muted"> (forecast)</span>}
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
          <YGrid ticks={ticks} y={y} left={left} right={right} format={tickPct} />
          {firstForecast >= 0 && (
            // Over the forecast bars, flush right so it never runs off a narrow chart.
            <text x={right} y={top - 8} textAnchor="end" fontSize={11} className="text-muted">
              {forecastLabel}
            </text>
          )}
          {years.map((r, i) => (
            <g key={r.year} opacity={active === null || active === i ? 1 : 0.45}>
              {r.forecast ? (
                <path
                  d={vbarPath(cx(i) - barW / 2 + 0.75, barW - 1.5, y(0), y(r.value))}
                  fill="none"
                  stroke="var(--context)"
                  strokeWidth={1.5}
                />
              ) : (
                <path d={vbarPath(cx(i) - barW / 2, barW, y(0), y(r.value))} fill="var(--accent)" />
              )}
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
