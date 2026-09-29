"use client";

import { fixed, month, monthIndex, tickNum } from "@/lib/format";
import { linear, niceTicks, yearTicks } from "@/lib/scale";

import { Guide, Swatch, XAxis, YGrid } from "./axes";
import { LIVE, nearestIndex, pointerX, stepHandlers, useActive } from "./interaction";
import { seriesPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

export type Episode = { label: string; start: string; end: string };

/** "+28.9" */
const signed = (v: number) => fixed(v, 1, true);

/**
 * Two monthly lines in log points (100 × the change in the natural log), the actual series
 * solid in the accent and a model's fitted values dashed in the context gray, over shaded
 * episodes. An episode is labelled inside its shading when the label fits, and always in
 * the key below the chart.
 */
export function ActualFitted({
  months,
  actual,
  fitted,
  actualLabel,
  fittedLabel,
  episodes,
  yLabel,
  label,
}: {
  months: string[];
  actual: number[];
  fitted: number[];
  actualLabel: string;
  fittedLabel: string;
  episodes: Episode[];
  yLabel: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  const last = months.length - 1;
  const height = width < 520 ? 250 : 320;
  const top = 18;
  const bottom = height - 26;
  const left = 44;
  const right = width - 10;
  const m0 = monthIndex(months[0]!);
  const m1 = monthIndex(months[last]!);
  const x = linear([m0, m1], [left, right]);
  const { ticks, domain } = niceTicks(
    Math.min(0, ...actual, ...fitted),
    Math.max(0, ...actual, ...fitted),
    width < 520 ? 5 : 6,
  );
  const y = linear(domain, [bottom, top]);
  const xs = months.map((m) => x(monthIndex(m)));
  const xTicks = yearTicks(m0, m1, Math.floor((right - left) / 52));

  const shades = episodes
    .map((ep) => ({
      ...ep,
      x0: x(Math.max(m0, monthIndex(ep.start))),
      x1: x(Math.min(m1, monthIndex(ep.end) + 1)),
    }))
    .filter((s) => s.x1 > s.x0);

  const shown = active ?? last;
  const handlers = stepHandlers({
    indexAt: (e) => nearestIndex(pointerX(e, width), left, right, last),
    active,
    setActive,
    clear,
    last,
  });

  return (
    <div ref={root}>
      <div
        className="mb-3 flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:gap-x-6"
        {...LIVE}
      >
        <span className="text-muted num">12 months to {month(months[shown]!)}</span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--accent)" shape="line" />
          <span>
            {actualLabel} <span className="num">{signed(actual[shown]!)}</span>
          </span>
        </span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--context)" shape="dash" />
          <span>
            <span className="text-muted">{fittedLabel}</span>{" "}
            <span className="num">{signed(fitted[shown]!)}</span>
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
          {shades.map((s) => (
            <g key={s.label}>
              <rect
                x={s.x0}
                y={top}
                width={Math.round((s.x1 - s.x0) * 100) / 100}
                height={bottom - top}
                fill="var(--grid)"
                opacity={0.6}
              />
              {textWidth(s.label, 10) + 6 <= s.x1 - s.x0 && (
                <text x={s.x0 + 4} y={top - 5} fontSize={10} className="text-muted">
                  {s.label}
                </text>
              )}
            </g>
          ))}
          <YGrid ticks={ticks} y={y} left={left} right={right} format={tickNum} />
          <XAxis ticks={xTicks} x={x} y={bottom} format={(m) => String(m / 12)} />
          <path
            d={seriesPath(
              xs,
              fitted.map((v) => y(v)),
            )}
            fill="none"
            stroke="var(--context)"
            strokeWidth={1.5}
            strokeDasharray="5 4"
            strokeLinejoin="round"
          />
          <path
            d={seriesPath(
              xs,
              actual.map((v) => y(v)),
            )}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={1.75}
            strokeLinejoin="round"
          />
          {active !== null && (
            <g pointerEvents="none">
              <Guide x={xs[active]!} top={top} bottom={bottom} />
              <circle
                cx={xs[active]}
                cy={y(fitted[active]!)}
                r={3.5}
                fill="var(--context)"
                stroke="var(--bg)"
                strokeWidth={2}
              />
              <circle
                cx={xs[active]}
                cy={y(actual[active]!)}
                r={3.5}
                fill="var(--accent)"
                stroke="var(--bg)"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>
      </div>
      <p className="mt-2 flex items-start gap-2 text-xs text-muted">
        <Swatch color="var(--grid)" shape="box" />
        <span>
          shaded:{" "}
          {episodes.map((ep, i) => (
            <span key={ep.label}>
              {i > 0 && ", "}
              {ep.label} ({month(ep.start)} – {month(ep.end)})
            </span>
          ))}
        </span>
      </p>
    </div>
  );
}
