"use client";

import {
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useRef,
  useState,
} from "react";

import { useTapOutside } from "./useTapOutside";

/**
 * Props for the text a chart's readout sits in: screen readers announce it when the arrow
 * keys (or a tap) move it, since the chart itself is a single image to them.
 */
export const LIVE = { "aria-live": "polite", "aria-atomic": true } as const;

/**
 * The point a chart's readout shows: null at rest (the chart then shows its latest value).
 * A tapped point stays until the reader taps outside `root`, since touch has no hover to end.
 */
export function useActive() {
  const [active, setActive] = useState<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const clear = useCallback(() => setActive(null), []);
  useTapOutside(root, active !== null, clear);
  return { active, setActive, root, clear };
}

/** The pointer's x in the chart's own coordinates (the SVG may be scaled to fit). */
export function pointerX(e: PointerEvent<SVGSVGElement>, width: number): number {
  const rect = e.currentTarget.getBoundingClientRect();
  return ((e.clientX - rect.left) / rect.width) * width;
}

/** The nearest of `last + 1` evenly spaced points between `left` and `right`. */
export function nearestIndex(px: number, left: number, right: number, last: number): number {
  const t = (px - left) / (right - left || 1);
  return Math.max(0, Math.min(last, Math.round(t * last)));
}

/** The bar under `px` when `n` bars share [left, right] equally. */
export function bandIndex(px: number, left: number, right: number, n: number): number {
  const i = Math.floor(((px - left) / (right - left || 1)) * n);
  return Math.max(0, Math.min(n - 1, i));
}

/**
 * Pointer and keyboard handlers for an SVG whose readout steps through `last + 1` points:
 * hover or tap picks a point, the arrow keys move one (with shift, `big`), Home and End jump
 * to the ends and Escape returns to rest. The arrows start from `rest`, the point the
 * readout shows at rest (by default the last one).
 */
export function stepHandlers({
  indexAt,
  active,
  setActive,
  clear,
  last,
  rest = last,
  big = 12,
}: {
  indexAt: (e: PointerEvent<SVGSVGElement>) => number;
  active: number | null;
  setActive: (i: number | null) => void;
  clear: () => void;
  last: number;
  rest?: number;
  big?: number;
}) {
  return {
    tabIndex: 0,
    onPointerMove: (e: PointerEvent<SVGSVGElement>) => setActive(indexAt(e)),
    onPointerDown: (e: PointerEvent<SVGSVGElement>) => setActive(indexAt(e)),
    onPointerLeave: (e: PointerEvent<SVGSVGElement>) => {
      if (e.pointerType === "mouse") clear();
    },
    onKeyDown: (e: KeyboardEvent<SVGSVGElement>) => {
      const cur = active ?? rest;
      const step = e.shiftKey ? big : 1;
      let next: number | null;
      if (e.key === "ArrowLeft" || e.key === "ArrowDown") next = Math.max(0, cur - step);
      else if (e.key === "ArrowRight" || e.key === "ArrowUp") next = Math.min(last, cur + step);
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = last;
      else if (e.key === "Escape") next = null;
      else return;
      e.preventDefault();
      setActive(next);
    },
    onBlur: clear,
  };
}
