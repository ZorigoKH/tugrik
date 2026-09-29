"use client";

import { type ValueKind, fmt, interval, tick } from "@/lib/format";
import { linear, niceTicks, spread } from "@/lib/scale";

import { Guide, Swatch, XAxis, YGrid } from "./axes";
import { LIVE, nearestIndex, pointerX, stepHandlers, useActive } from "./interaction";
import { areaPath, roleColor, seriesPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

/** One horizon's estimate and its 95% interval, already in the units the chart shows. */
export type ResponsePoint = { est: number; lo: number; hi: number };

export type ResponseSeries = {
  key: string;
  label: string;
  /** one point per horizon */
  points: ResponsePoint[];
  role: "accent" | "context";
  /** draw the 95% band */
  band: boolean;
  dashed?: boolean;
};

const FONT = 12;

/**
 * Cumulative responses by horizon (months 0-12), each a line with an optional 95% band,
 * against a zero line. The readout above the chart names every series' value at the
 * hovered, tapped or keyed month; at rest it shows month 12.
 */
export function ResponseChart({
  horizons,
  series,
  kind,
  yLabel,
  xLabel,
  label,
}: {
  horizons: number[];
  series: ResponseSeries[];
  kind: ValueKind;
  yLabel: string;
  xLabel: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  const last = horizons.length - 1;
  const ends = series.map((s) => fmt(kind, s.points[last]!.est));
  const endRoom = Math.max(...ends.map((e) => textWidth(e, FONT))) + 18;

  const height = width < 520 ? 250 : 320;
  const top = 10;
  const bottom = height - 26;
  const left = 44;
  const right = width - endRoom;
  const all = series.flatMap((s) =>
    s.points.flatMap((p) => (s.band ? [p.lo, p.hi] : [p.est])),
  );
  const { ticks, domain } = niceTicks(Math.min(0, ...all), Math.max(0, ...all), 5);
  const x = linear([horizons[0]!, horizons[last]!], [left, right]);
  const y = linear(domain, [bottom, top]);
  const xs = horizons.map((h) => x(h));
  const every = (right - left) / last >= 26 ? 1 : 3;
  const xTicks = horizons.filter((h) => h % every === 0);
  const endYs = spread(
    series.map((s) => y(s.points[last]!.est)),
    FONT + 3,
    top + 4,
    bottom,
  );

  const shown = active ?? last;
  const handlers = stepHandlers({
    indexAt: (e) => nearestIndex(pointerX(e, width), left, right, last),
    active,
    setActive,
    clear,
    last,
    big: 3,
  });

  return (
    <div ref={root}>
      <div className="mb-3 flex flex-col gap-1 text-sm" {...LIVE}>
        <span className="text-muted num">month {horizons[shown]}</span>
        {[...series].reverse().map((s) => {
          const p = s.points[shown]!;
          return (
            <span key={s.key} className="flex items-start gap-2">
              <span className="mt-[0.3lh]">
                <Swatch color={roleColor(s.role)} shape={s.dashed ? "dash" : "line"} />
              </span>
              <span>
                <span className={s.role === "accent" ? "" : "text-muted"}>{s.label}</span>{" "}
                <span className="num">{fmt(kind, p.est)}</span>
                {s.band && (
                  <span className="num text-muted">
                    {" "}
                    (95% CI {interval(p.lo, p.hi, (v) => fmt(kind, v))})
                  </span>
                )}
              </span>
            </span>
          );
        })}
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
          <YGrid ticks={ticks} y={y} left={left} right={right} format={(v) => tick(kind, v)} />
          <XAxis ticks={xTicks} x={x} y={bottom} format={(v) => String(v)} />
          {series.map((s) =>
            s.band ? (
              <path
                key={`band-${s.key}`}
                d={areaPath(
                  xs,
                  s.points.map((p) => y(p.lo)),
                  s.points.map((p) => y(p.hi)),
                )}
                fill={roleColor(s.role)}
                fillOpacity={s.role === "accent" ? 0.16 : 0.2}
              />
            ) : null,
          )}
          {series.map((s) => (
            <path
              key={s.key}
              d={seriesPath(
                xs,
                s.points.map((p) => y(p.est)),
              )}
              fill="none"
              stroke={roleColor(s.role)}
              strokeWidth={2}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {series.map((s, i) => (
            <g key={`end-${s.key}`}>
              <circle
                cx={right}
                cy={y(s.points[last]!.est)}
                r={3.5}
                fill={roleColor(s.role)}
                stroke="var(--bg)"
                strokeWidth={2}
              />
              <text
                x={right + 10}
                y={endYs[i]! + 4}
                fontSize={FONT}
                className={`num ${s.role === "accent" ? "text-fg" : "text-muted"}`}
              >
                {ends[i]}
              </text>
            </g>
          ))}
          {active !== null && (
            <g pointerEvents="none">
              <Guide x={xs[active]!} top={top} bottom={bottom} />
              {series.map((s) => (
                <circle
                  key={s.key}
                  cx={xs[active]}
                  cy={y(s.points[active]!.est)}
                  r={4}
                  fill={roleColor(s.role)}
                  stroke="var(--bg)"
                  strokeWidth={2}
                />
              ))}
            </g>
          )}
        </svg>
      </div>
      <p className="mt-1 text-right text-xs text-muted">{xLabel}</p>
    </div>
  );
}
