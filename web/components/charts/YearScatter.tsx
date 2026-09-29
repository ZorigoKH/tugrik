"use client";

import { type KeyboardEvent, type PointerEvent, useMemo } from "react";

import { spct, tickPct } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { Swatch, XAxis, YGrid } from "./axes";
import { LIVE, useActive } from "./interaction";
import { textWidth, useWidth } from "./useWidth";

export type YearPoint = { year: string; x: number; y: number; labelled: boolean };

const HIT = 28; // px: how close the pointer must be to pick a point

/**
 * One dot per year (x and y in percent), the years named in `labelled` written next to
 * their dots, and a fitted line from (x0, y0) to (x1, y1). Hover, tap or the arrow keys
 * pick a year; the readout below names it.
 */
export function YearScatter({
  points,
  fit,
  xLabel,
  yLabel,
  fitLabel,
  label,
}: {
  points: YearPoint[];
  fit: { x0: number; y0: number; x1: number; y1: number };
  xLabel: string;
  yLabel: string;
  fitLabel: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  // Keyboard order: left to right. From rest, ArrowRight picks the leftmost dot and
  // ArrowLeft the rightmost.
  const order = useMemo(
    () =>
      points
        .map((p, i) => ({ p, i }))
        .sort((a, b) => a.p.x - b.p.x)
        .map((o) => o.i),
    [points],
  );

  const height = width < 520 ? 300 : 380;
  const top = 12;
  const bottom = height - 26;
  const left = 44;
  const right = width - 12;
  const xt = niceTicks(
    Math.min(0, ...points.map((p) => p.x)),
    Math.max(0, ...points.map((p) => p.x)),
    Math.max(4, Math.floor((right - left) / 70)),
  );
  const yt = niceTicks(
    Math.min(0, ...points.map((p) => p.y)),
    Math.max(0, ...points.map((p) => p.y)),
    width < 520 ? 5 : 6,
  );
  const x = linear(xt.domain, [left, right]);
  const y = linear(yt.domain, [bottom, top]);

  function nearest(e: PointerEvent<SVGSVGElement>): number | null {
    const rect = e.currentTarget.getBoundingClientRect();
    const scale = width / rect.width;
    const px = (e.clientX - rect.left) * scale;
    const py = (e.clientY - rect.top) * scale;
    let best: number | null = null;
    let bestD = HIT * HIT;
    points.forEach((p, i) => {
      const d = (x(p.x) - px) ** 2 + (y(p.y) - py) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best;
  }

  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    const pos = active === null ? -1 : order.indexOf(active);
    let next: number | null | undefined;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") next = order[(pos + 1) % order.length];
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown")
      next = pos === -1 ? order.at(-1) : order[(pos - 1 + order.length) % order.length];
    else if (e.key === "Home") next = order[0];
    else if (e.key === "End") next = order.at(-1);
    else if (e.key === "Escape") next = null;
    if (next === undefined) return;
    e.preventDefault();
    setActive(next);
  }

  const sel = active === null ? null : points[active]!;

  return (
    <div ref={root}>
      <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="flex items-center gap-2">
          <Swatch color="var(--accent)" shape="dot" />a year
        </span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--context)" shape="line" />
          <span className="text-muted">{fitLabel}</span>
        </span>
      </div>
      <p className="mb-1 text-xs text-muted">{yLabel}</p>
      <div ref={ref}>
        <svg
          className="chart outline-none focus-visible:outline-2"
          role="img"
          aria-label={label}
          tabIndex={0}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          onPointerMove={(e) => {
            if (e.pointerType === "mouse") setActive(nearest(e));
          }}
          onPointerDown={(e) => setActive(nearest(e))}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") clear();
          }}
          onKeyDown={onKey}
          onBlur={clear}
        >
          <YGrid ticks={yt.ticks} y={y} left={left} right={right} format={tickPct} />
          <XAxis ticks={xt.ticks} x={x} y={bottom} format={tickPct} />
          {xt.ticks.includes(0) && (
            <line
              x1={x(0)}
              x2={x(0)}
              y1={top}
              y2={bottom}
              stroke="var(--base)"
              strokeWidth={1}
              shapeRendering="crispEdges"
            />
          )}
          <line
            x1={x(fit.x0)}
            x2={x(fit.x1)}
            y1={y(fit.y0)}
            y2={y(fit.y1)}
            stroke="var(--context)"
            strokeWidth={2}
            strokeLinecap="round"
          />
          {points.map((p, i) => (
            <circle
              key={p.year}
              cx={x(p.x)}
              cy={y(p.y)}
              r={4.5}
              fill="var(--accent)"
              stroke="var(--bg)"
              strokeWidth={1.5}
              opacity={active === null || active === i ? 1 : 0.45}
            />
          ))}
          {points.map((p, i) => {
            if (!p.labelled && active !== i) return null;
            const flip = x(p.x) + 8 + textWidth(p.year, 11) > right;
            return (
              <text
                key={`l${p.year}`}
                x={flip ? x(p.x) - 8 : x(p.x) + 8}
                y={y(p.y) - 7}
                textAnchor={flip ? "end" : "start"}
                fontSize={11}
                className="num text-fg"
                paintOrder="stroke"
                stroke="var(--bg)"
                strokeWidth={3}
                strokeLinejoin="round"
                pointerEvents="none"
              >
                {p.year}
              </text>
            );
          })}
          {sel && (
            <circle
              cx={x(sel.x)}
              cy={y(sel.y)}
              r={8}
              fill="none"
              stroke="var(--fg)"
              strokeWidth={1.5}
              pointerEvents="none"
            />
          )}
        </svg>
      </div>
      <p className="mt-1 text-right text-xs text-muted">{xLabel}</p>
      <p className="mt-3 min-h-[1.6rem] text-sm" {...LIVE}>
        {sel ? (
          <span className="num">
            {sel.year}: export prices {spct(sel.x)} the year before, growth {spct(sel.y)}
          </span>
        ) : (
          <span className="text-muted">Hover or tap a dot to see its year.</span>
        )}
      </p>
    </div>
  );
}
