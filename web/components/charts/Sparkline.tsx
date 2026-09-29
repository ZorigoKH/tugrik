"use client";

import { linear } from "@/lib/scale";

import { seriesPath } from "./marks";
import { useWidth } from "./useWidth";

const HEIGHT = 36;

/**
 * A small line with no axes: the shape of the last few years at a glance, with a dot on the
 * latest value. With `step`, each value holds until the next (a policy rate). Missing values
 * break the line.
 */
export function Sparkline({
  values,
  step = false,
  label,
}: {
  values: (number | null)[];
  step?: boolean;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(240);
  const known = values.filter((v): v is number => v !== null);
  const lo = Math.min(...known);
  const hi = Math.max(...known);
  const pad = (hi - lo) * 0.08 || 1;
  const x = linear([0, Math.max(1, values.length - 1)], [3, width - 4]);
  const y = linear([lo - pad, hi + pad], [HEIGHT - 3, 3]);
  const xs = values.map((_, i) => x(i));
  const lastIndex = values.findLastIndex((v) => v !== null);
  const last = values[lastIndex];

  return (
    <div ref={ref}>
      <svg
        className="chart"
        role="img"
        aria-label={label}
        width={width}
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
      >
        <path
          d={seriesPath(
            xs,
            values.map((v) => (v === null ? null : y(v))),
            step,
          )}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
        {last !== null && last !== undefined && (
          <circle
            cx={xs[lastIndex]}
            cy={y(last)}
            r={3}
            fill="var(--accent)"
            stroke="var(--bg)"
            strokeWidth={1.5}
          />
        )}
      </svg>
    </div>
  );
}
