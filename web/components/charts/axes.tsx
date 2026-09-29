// Gridlines, axis labels and legend swatches shared by the charts.

import type { Scale } from "@/lib/scale";

/**
 * Horizontal gridlines across [left, right] with their labels to the left. The line at
 * `zero` (if it is a tick) is drawn as the baseline.
 */
export function YGrid({
  ticks,
  y,
  left,
  right,
  format,
  zero = 0,
  fontSize = 11,
}: {
  ticks: number[];
  y: Scale;
  left: number;
  right: number;
  format: (v: number) => string;
  zero?: number | null;
  fontSize?: number;
}) {
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line
            x1={left}
            x2={right}
            y1={y(t)}
            y2={y(t)}
            stroke={t === zero ? "var(--base)" : "var(--grid)"}
            strokeWidth={t === zero ? 1.5 : 1}
            shapeRendering="crispEdges"
          />
          <text
            x={left - 6}
            y={y(t) + 4}
            textAnchor="end"
            fontSize={fontSize}
            className="text-muted num"
          >
            {format(t)}
          </text>
        </g>
      ))}
    </g>
  );
}

/** Tick marks and labels under an x-axis: `ticks` are positions in data units. */
export function XAxis({
  ticks,
  x,
  y,
  format,
}: {
  ticks: number[];
  x: Scale;
  y: number;
  format: (v: number) => string;
}) {
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line
            x1={x(t)}
            x2={x(t)}
            y1={y}
            y2={y + 4}
            stroke="var(--base)"
            shapeRendering="crispEdges"
          />
          <text x={x(t)} y={y + 17} textAnchor="middle" fontSize={11} className="text-muted num">
            {format(t)}
          </text>
        </g>
      ))}
    </g>
  );
}

/** A vertical guide at the point a readout shows. */
export function Guide({ x, top, bottom }: { x: number; top: number; bottom: number }) {
  return (
    <line
      x1={x}
      x2={x}
      y1={top}
      y2={bottom}
      stroke="var(--muted)"
      strokeWidth={1}
      shapeRendering="crispEdges"
      pointerEvents="none"
    />
  );
}

/** A small legend mark in the text above a chart. */
export function Swatch({
  color,
  shape,
}: {
  color: string;
  shape: "line" | "dash" | "step" | "box" | "hollow" | "dot";
}) {
  const common = { width: 22, height: 12, "aria-hidden": true, className: "shrink-0" } as const;
  if (shape === "box" || shape === "hollow") {
    return (
      <svg {...common}>
        <rect
          x={6}
          y={2}
          width={10}
          height={8}
          rx={1.5}
          fill={shape === "hollow" ? "none" : color}
          stroke={shape === "hollow" ? color : "none"}
          strokeWidth={1.5}
        />
      </svg>
    );
  }
  if (shape === "dot") {
    return (
      <svg {...common}>
        <circle cx={11} cy={6} r={4} fill={color} stroke="var(--bg)" strokeWidth={1.5} />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path
        d={shape === "step" ? "M1,9H11V3H21" : "M1,6H21"}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeDasharray={shape === "dash" ? "4 3" : undefined}
        strokeLinecap="round"
      />
    </svg>
  );
}
