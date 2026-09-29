"use client";

import { fixed } from "@/lib/format";
import { linear, spread } from "@/lib/scale";

import { Guide, Swatch, XAxis, YGrid } from "./axes";
import { LIVE, nearestIndex, pointerX, stepHandlers, useActive } from "./interaction";
import { areaPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

export type ShareLayer = {
  key: string;
  label: string;
  /** one share (0-1) per year */
  values: number[];
  /** a CSS colour: the accent for copper, grays for the rest */
  color: string;
};

const FONT = 11;

/** 0.412 -> "41%" */
const share = (v: number) => `${fixed(100 * v, 0)}%`;

/**
 * Shares that add up to 1 each year, stacked bottom to top in the order given, each layer
 * labelled directly at the right edge (labels are nudged apart where layers are thin). The
 * readout above lists every share for the hovered, tapped or keyed year; at rest, the last.
 */
export function ShareArea({
  years,
  layers,
  label,
}: {
  years: string[];
  layers: ShareLayer[];
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  const last = years.length - 1;
  const labelW = Math.max(...layers.map((l) => textWidth(l.label, FONT))) + 12;
  const height = width < 520 ? 240 : 300;
  const top = 8;
  const bottom = height - 26;
  const left = 40;
  const right = width - labelW;
  const x = linear([0, last], [left, right]);
  const y = linear([0, 1], [bottom, top]);
  const xs = years.map((_, i) => x(i));
  const every = [1, 2, 5, 10].find((k) => ((right - left) / last) * k >= 44) ?? 10;
  const xTicks = years.map((_, i) => i).filter((i) => Number(years[i]) % every === 0);

  // Running totals: layer k fills from below[k] to below[k] + values[k].
  const below = layers.map((_, k) =>
    years.map((_, i) => layers.slice(0, k).reduce((sum, l) => sum + l.values[i]!, 0)),
  );
  const mids = layers.map((l, k) => y(below[k]![last]! + l.values[last]! / 2));
  const labelYs = spread(mids, FONT + 2, top + 4, bottom);

  const shown = active ?? last;
  const handlers = stepHandlers({
    indexAt: (e) => nearestIndex(pointerX(e, width), left, right, last),
    active,
    setActive,
    clear,
    last,
    big: 5,
  });

  return (
    <div ref={root}>
      <div className="mb-3 text-sm" {...LIVE}>
        <p className="num text-muted">{years[shown]}</p>
        <p className="flex flex-wrap gap-x-5 gap-y-1">
          {[...layers].reverse().map((l) => (
            <span key={l.key} className="flex items-center gap-2">
              <Swatch color={l.color} shape="box" />
              <span>
                {l.label} <span className="num">{share(l.values[shown]!)}</span>
              </span>
            </span>
          ))}
        </p>
      </div>
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
          {layers.map((l, k) => (
            <path
              key={l.key}
              d={areaPath(
                xs,
                below[k]!.map((b) => y(b)),
                below[k]!.map((b, i) => y(b + l.values[i]!)),
              )}
              fill={l.color}
              stroke="var(--bg)"
              strokeWidth={0.75}
              strokeLinejoin="round"
            />
          ))}
          <YGrid
            ticks={[0, 0.5, 1]}
            y={y}
            left={left}
            right={right}
            format={share}
            zero={null}
          />
          <XAxis ticks={xTicks} x={x} y={bottom} format={(i) => years[i]!} />
          {layers.map((l, i) => (
            <text
              key={l.key}
              x={right + 8}
              y={labelYs[i]! + 4}
              fontSize={FONT}
              className={l.key === "copper" ? "text-fg" : "text-muted"}
            >
              {l.label}
            </text>
          ))}
          {active !== null && <Guide x={xs[active]!} top={top} bottom={bottom} />}
        </svg>
      </div>
    </div>
  );
}
