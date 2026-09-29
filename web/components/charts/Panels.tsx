"use client";

import { type ValueKind, fmt, month, monthIndex, tick } from "@/lib/format";
import { linear, niceTicks, yearTicks } from "@/lib/scale";

import { Guide, Swatch, XAxis, YGrid } from "./axes";
import { LIVE, nearestIndex, pointerX, stepHandlers, useActive } from "./interaction";
import { roleColor, seriesPath } from "./marks";
import { useWidth } from "./useWidth";

export type PanelSeries = {
  key: string;
  label: string;
  /** one value per month; null where there is none */
  values: (number | null)[];
  role: "accent" | "context";
  /** hold each value until the next month (a policy rate between decisions) */
  step?: boolean;
  /** draw the line dashed, so it differs from the others by more than its colour */
  dashed?: boolean;
};

export type Panel = {
  key: string;
  title: string;
  kind: ValueKind;
  series: PanelSeries[];
  /** draw a zero line and keep zero on the axis */
  zero?: boolean;
};

const TITLE_H = 22;
const GAP = 14;

/**
 * Small multiples on one shared monthly x-axis, stacked in a single SVG so the months line
 * up exactly: each panel has its own y-axis and one or more lines (optionally as steps).
 * Shaded windows run through every panel. The readout above names every value at the
 * hovered, tapped or keyed month; at rest it shows the latest month.
 */
export function Panels({
  months,
  panels,
  shade,
  shadeNote,
  label,
}: {
  months: string[];
  panels: Panel[];
  shade: { label: string; start: string; end: string }[];
  /** the key under the chart; by default each window's label and months */
  shadeNote?: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const { active, setActive, root, clear } = useActive();

  const last = months.length - 1;
  const plotH = width < 520 ? 120 : 150;
  const left = 48;
  const right = width - 10;
  const m0 = monthIndex(months[0]!);
  const m1 = monthIndex(months[last]!);
  const x = linear([m0, m1], [left, right]);
  const xs = months.map((m) => x(monthIndex(m)));
  const xTicks = yearTicks(m0, m1, Math.floor((right - left) / 48));
  const height = panels.length * (TITLE_H + plotH + GAP) - GAP + 26;

  const layout = panels.map((p, k) => {
    const top = k * (TITLE_H + plotH + GAP) + TITLE_H;
    const bottom = top + plotH;
    const vals = p.series.flatMap((s) => s.values.filter((v): v is number => v !== null));
    const lo = Math.min(...vals, ...(p.zero ? [0] : []));
    const hi = Math.max(...vals, ...(p.zero ? [0] : []));
    const pad = p.zero ? 0 : (hi - lo) * 0.05;
    const { ticks, domain } = niceTicks(lo - pad, hi + pad, 4);
    return { top, bottom, ticks, y: linear(domain, [bottom, top]) };
  });
  const plotTop = layout[0]!.top;
  const plotBottom = layout.at(-1)!.bottom;

  const shades = shade
    .map((s) => ({
      ...s,
      x0: x(Math.max(m0, monthIndex(s.start))),
      x1: x(Math.min(m1, monthIndex(s.end) + 1)),
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
      <div className="mb-3 space-y-1 text-sm" {...LIVE}>
        <p className="text-muted num">{month(months[shown]!)}</p>
        {panels.map((p) => (
          <p key={p.key} className="flex flex-wrap gap-x-5 gap-y-1">
            {p.series.map((s) => {
              const v = s.values[shown];
              return (
                <span key={s.key} className="flex items-center gap-2">
                  <Swatch
                    color={roleColor(s.role)}
                    shape={s.step ? "step" : s.dashed ? "dash" : "line"}
                  />
                  <span>
                    <span className={s.role === "accent" ? "" : "text-muted"}>{s.label}</span>{" "}
                    <span className="num">{v === null || v === undefined ? "—" : fmt(p.kind, v)}</span>
                  </span>
                </span>
              );
            })}
          </p>
        ))}
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
          {shades.map((s) => (
            <rect
              key={s.start}
              x={s.x0}
              y={plotTop}
              width={Math.round((s.x1 - s.x0) * 100) / 100}
              height={plotBottom - plotTop}
              fill="var(--grid)"
              opacity={0.6}
            />
          ))}
          {panels.map((p, k) => {
            const { top, bottom, ticks, y } = layout[k]!;
            return (
              <g key={p.key}>
                <text x={0} y={top - 8} fontSize={12} className="text-fg">
                  {p.title}
                </text>
                <YGrid
                  ticks={ticks}
                  y={y}
                  left={left}
                  right={right}
                  format={(v) => tick(p.kind, v)}
                  zero={p.zero ? 0 : null}
                />
                {p.series.map((s) => (
                  <path
                    key={s.key}
                    d={seriesPath(
                      xs,
                      s.values.map((v) => (v === null ? null : y(v))),
                      s.step,
                    )}
                    fill="none"
                    stroke={roleColor(s.role)}
                    strokeWidth={s.role === "accent" ? 1.75 : 1.5}
                    strokeDasharray={s.dashed ? "5 4" : undefined}
                    strokeLinejoin="round"
                  />
                ))}
                {active !== null &&
                  p.series.map((s) => {
                    const v = s.values[active];
                    return v === null || v === undefined ? null : (
                      <circle
                        key={s.key}
                        cx={xs[active]}
                        cy={y(v)}
                        r={3.5}
                        fill={roleColor(s.role)}
                        stroke="var(--bg)"
                        strokeWidth={2}
                        pointerEvents="none"
                      />
                    );
                  })}
              </g>
            );
          })}
          <XAxis ticks={xTicks} x={x} y={plotBottom} format={(m) => String(m / 12)} />
          {active !== null && <Guide x={xs[active]!} top={plotTop} bottom={plotBottom} />}
        </svg>
      </div>
      {shades.length > 0 && (
        <p className="mt-2 flex items-start gap-2 text-xs text-muted">
          <Swatch color="var(--grid)" shape="box" />
          <span>
            shaded:{" "}
            {shadeNote ??
              shade.map((s, i) => (
                <span key={s.start}>
                  {i > 0 && ", "}
                  {s.label} ({month(s.start)} – {month(s.end)})
                </span>
              ))}
          </span>
        </p>
      )}
    </div>
  );
}
