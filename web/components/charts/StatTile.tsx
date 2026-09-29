import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import { amount, date, period } from "@/lib/format";
import { SOURCE_NAMES } from "@/lib/site";
import type { Tile } from "@/lib/types";

import { Sparkline } from "./Sparkline";

/** "Aug 2026", "2025", or for a policy rate (dated by its decision) "decision of 17 Sep 2026". */
function when(p: string): string {
  return p.length === 10 ? `decision of ${date(p)}` : period(p);
}

/**
 * One latest value on the overview: the number, when it is from, its change on a year
 * earlier, a detail line where the tile has one, and a sparkline of the last 36
 * observations. The tile links to the page that explains the series.
 */
export function StatTile({ tile, href, page }: { tile: Tile; href: string; page: string }) {
  const unitNote = tile.unit === "MNT per USD" ? "MNT per US$" : null;
  const { dates, values } = tile.spark;
  const known = values.filter((v): v is number => v !== null);
  const sparkLabel =
    `${tile.label}, ${period(dates[0]!)} to ${period(dates.at(-1)!)}: from ` +
    `${amount(known[0]!, tile.unit)} to ${amount(known.at(-1)!, tile.unit)}; lowest ` +
    `${amount(Math.min(...known), tile.unit)}, highest ${amount(Math.max(...known), tile.unit)}.`;

  return (
    <div className="flex h-full flex-col border-t border-line py-5">
      <p className="flex items-baseline justify-between gap-3 text-xs text-muted">
        <span>{tile.label}</span>
        {tile.status !== "ok" && <StatusBadge status={tile.status} />}
      </p>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span className="num text-3xl">{amount(tile.value, tile.unit)}</span>
        {unitNote && <span className="text-sm text-muted">{unitNote}</span>}
      </p>
      <p className="mt-1 text-xs text-muted">
        {when(tile.period)}
        {tile.detail && (
          <>
            {" · "}
            {tile.detail.label}{" "}
            <span className="num text-fg">{amount(tile.detail.value, tile.detail.unit)}</span>
          </>
        )}
      </p>
      {tile.change && (
        <p className="mt-1 text-xs text-muted">
          <span className="num text-fg">
            {amount(tile.change.value, tile.change.unit, true)}
          </span>{" "}
          {tile.change.label}
        </p>
      )}
      <div className="mt-auto pt-4">
        <Sparkline values={values} step={tile.id === "policy_rate"} label={sparkLabel} />
        <p className="mt-2 flex items-baseline justify-between gap-3 text-xs text-muted">
          <span>
            {period(dates[0]!)} – {period(dates.at(-1)!)} · {SOURCE_NAMES[tile.source] ?? tile.source}
          </span>
          <Link href={href}>{page}</Link>
        </p>
      </div>
    </div>
  );
}
