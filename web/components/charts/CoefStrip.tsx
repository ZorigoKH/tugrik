"use client";

import { dec, tickNum } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { roleColor } from "./marks";
import { useWidth } from "./useWidth";

export type CoefRow = {
  key: string;
  label: string;
  /** what the coefficient sums over, e.g. "months 0–12" */
  sub: string;
  est: number;
  lo: number;
  hi: number;
  role: "accent" | "context";
};

const ROW = 54;
const AXIS_H = 26;

/**
 * One row per coefficient on a shared scale: a dot at the estimate with a whisker for its
 * 95% interval, against a zero line. Each row's label and value sit above its whisker, so
 * the strip reads the same on a phone as on a wide screen.
 */
export function CoefStrip({
  rows,
  axisLabel,
  label,
}: {
  rows: CoefRow[];
  axisLabel: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const left = 8;
  const right = width - 8;
  const lo = Math.min(0, ...rows.map((r) => r.lo));
  const hi = Math.max(0, ...rows.map((r) => r.hi));
  const { ticks, domain } = niceTicks(lo, hi, Math.max(3, Math.floor((right - left) / 80)));
  const x = linear(domain, [left, right]);
  const plotBottom = rows.length * ROW;
  const height = plotBottom + AXIS_H;
  const cy = (i: number) => i * ROW + 36;

  return (
    <div>
      <div ref={ref}>
        <svg
          className="chart"
          role="img"
          aria-label={label}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={x(t)}
                x2={x(t)}
                y1={0}
                y2={plotBottom}
                stroke={t === 0 ? "var(--base)" : "var(--grid)"}
                strokeWidth={t === 0 ? 1.5 : 1}
                shapeRendering="crispEdges"
              />
              <text
                x={x(t)}
                y={plotBottom + 18}
                textAnchor="middle"
                fontSize={11}
                className="text-muted num"
              >
                {tickNum(t)}
              </text>
            </g>
          ))}
          {rows.map((r, i) => (
            <g key={r.key}>
              <text x={left} y={i * ROW + 16} fontSize={13} className="text-fg">
                {r.label} <tspan className="text-muted">{r.sub}</tspan>
              </text>
              <text
                x={right}
                y={i * ROW + 16}
                textAnchor="end"
                fontSize={12}
                className="num text-fg"
              >
                {dec(r.est)}
              </text>
              <line
                x1={x(r.lo)}
                x2={x(r.hi)}
                y1={cy(i)}
                y2={cy(i)}
                stroke={roleColor(r.role)}
                strokeWidth={1.75}
              />
              {[r.lo, r.hi].map((v, k) => (
                <line
                  key={k}
                  x1={x(v)}
                  x2={x(v)}
                  y1={cy(i) - 5}
                  y2={cy(i) + 5}
                  stroke={roleColor(r.role)}
                  strokeWidth={1.75}
                />
              ))}
              <circle
                cx={x(r.est)}
                cy={cy(i)}
                r={5}
                fill={roleColor(r.role)}
                stroke="var(--bg)"
                strokeWidth={2}
              />
            </g>
          ))}
        </svg>
      </div>
      <p className="mt-1 text-right text-xs text-muted">{axisLabel}</p>
    </div>
  );
}
