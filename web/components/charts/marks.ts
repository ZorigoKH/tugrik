// Shared SVG mark geometry.

/**
 * A vertical bar `w` wide from `y0` (the baseline) to `y1` with a rounded data end and a
 * square baseline end; `r = 0` gives a plain rectangle (an inner segment of a stack).
 */
export function vbarPath(x: number, w: number, y0: number, y1: number, r = 3): string {
  const h = Math.abs(y1 - y0);
  if (h < 0.5) return "";
  const rr = Math.min(r, h, w / 2);
  const dir = y1 >= y0 ? 1 : -1; // SVG y grows downward: dir 1 is a bar below the baseline
  const ye = y1 - dir * rr;
  return [
    `M${x},${y0}`,
    `V${ye}`,
    `Q${x},${y1} ${x + rr},${y1}`,
    `H${x + w - rr}`,
    `Q${x + w},${y1} ${x + w},${ye}`,
    `V${y0}`,
    "Z",
  ].join(" ");
}

/**
 * An SVG path through the points that breaks at missing values (null). With `step`, each
 * value holds until the next point, as a policy rate does between decisions.
 */
export function seriesPath(xs: number[], ys: (number | null)[], step = false): string {
  let d = "";
  let open = false;
  for (let i = 0; i < xs.length; i++) {
    const y = ys[i];
    if (y === null || y === undefined) {
      open = false;
      continue;
    }
    const x = xs[i]!.toFixed(1);
    if (!open) d += `M${x},${y.toFixed(1)}`;
    else if (step) d += `H${x}V${y.toFixed(1)}`;
    else d += `L${x},${y.toFixed(1)}`;
    open = true;
  }
  return d;
}

/** A closed band between two lines: along `y1` left to right, back along `y0`. */
export function areaPath(xs: number[], y0: number[], y1: number[]): string {
  let d = "";
  for (let i = 0; i < xs.length; i++) {
    d += `${i === 0 ? "M" : "L"}${xs[i]!.toFixed(1)},${y1[i]!.toFixed(1)}`;
  }
  for (let i = xs.length - 1; i >= 0; i--) {
    d += `L${xs[i]!.toFixed(1)},${y0[i]!.toFixed(1)}`;
  }
  return `${d}Z`;
}

/** The CSS colour of a chart role. */
export function roleColor(role: "accent" | "context"): string {
  return role === "accent" ? "var(--accent)" : "var(--context)";
}
