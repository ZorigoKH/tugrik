import Link from "next/link";

import { StatTile } from "@/components/charts/StatTile";
import { NumbersTable } from "@/components/Table";
import { getMeta, getOverview } from "@/lib/data";
import { amount, date, month, period } from "@/lib/format";
import { PAGE_LINKS, SUBTITLE, TILE_PAGES, TITLE } from "@/lib/site";

export default function Home() {
  const meta = getMeta();
  const { tiles, cards } = getOverview();
  const t = meta.through;
  const through: [string, string][] = [
    ["tugrik", month(t.fx)],
    ["consumer prices", month(t.cpi)],
    ["policy rate", date(t.policy_rate)],
    ["commodity prices", month(t.commodities)],
    ["exports", month(t.trade)],
    ["GDP", t.gdp],
    ["IMF forecasts", t.weo_vintage ?? "not available"],
  ];
  const pageName = (href: string) => PAGE_LINKS.find((p) => p.href === href)?.nav ?? href;

  return (
    <>
      <section className="pt-10 sm:pt-16">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{TITLE}</h1>
        <p className="mt-2 text-muted">{SUBTITLE}</p>
        <p className="mt-6 max-w-3xl text-xl leading-snug sm:text-2xl">
          Mongolia sells copper and coal to China. What does that do to its money, its prices and
          its growth?
        </p>
        <div className="mt-6 max-w-2xl space-y-4 text-muted">
          <p>
            Copper concentrate and coal make up most of what Mongolia sells abroad, and nearly all
            of both goes to China. Copper trades at a world price. Coal goes by truck and rail
            across one border, so how much of it China lets through matters as much as its price.
          </p>
          <p>
            This site rebuilds four results from public data each month: how the tugrik follows
            copper, why coal income follows the border, how little of a weaker tugrik shows up in
            consumer prices, and how growth follows export prices a year later. Every sentence
            below is generated from the current estimates. <Link href="/method">How it works</Link>
            .
          </p>
        </div>
      </section>

      <section aria-labelledby="latest" className="mt-14">
        <h2 id="latest" className="text-sm text-muted">
          the latest numbers
        </h2>
        <ul className="mt-2 grid grid-cols-1 gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
          {tiles.map((tile) => {
            const href = TILE_PAGES[tile.id] ?? "/data";
            return (
              <li key={tile.id}>
                <StatTile tile={tile} href={href} page={pageName(href)} />
              </li>
            );
          })}
        </ul>
        <NumbersTable
          summary="the numbers behind the sparklines"
          caption="Each tile's sparkline: its first and last observation, and its lowest and highest value."
          minWidth="40rem"
          columns={[
            { label: "series", align: "left" },
            { label: "first" },
            { label: "lowest" },
            { label: "highest" },
            { label: "latest" },
          ]}
          rows={tiles.map((tile) => {
            const { dates, values } = tile.spark;
            const known = values.flatMap((v, i) => (v === null ? [] : [{ d: dates[i]!, v }]));
            const low = known.reduce((a, b) => (b.v < a.v ? b : a));
            const high = known.reduce((a, b) => (b.v > a.v ? b : a));
            const at = (x: { d: string; v: number }) =>
              `${amount(x.v, tile.unit)} (${period(x.d)})`;
            return {
              key: tile.id,
              cells: [tile.label, at(known[0]!), at(low), at(high), at(known.at(-1)!)],
            };
          })}
        />
        <p className="mt-4 text-xs text-muted">
          Sources publish on different schedules, so the data run to different dates:{" "}
          {through.map(([k, v], i) => (
            <span key={k}>
              {i > 0 && " · "}
              <span className="whitespace-nowrap">
                {k} <span className="num text-fg">{v}</span>
              </span>
            </span>
          ))}
          .
        </p>
      </section>

      <section aria-labelledby="findings" className="mt-16">
        <h2 id="findings" className="text-lg font-medium">
          four findings
        </h2>
        <ol className="mt-4 grid grid-cols-1 border-t border-line sm:grid-cols-2">
          {cards.map((c, i) => {
            const href = PAGE_LINKS.find((p) => p.id === c.page)!.href;
            return (
              <li
                key={c.page}
                className={`border-b border-line py-6 sm:px-6 ${
                  i % 2 === 0 ? "sm:border-r sm:pl-0" : "sm:pr-0"
                }`}
              >
                <p className="text-xs text-muted num">{i + 1}</p>
                <h3 className="mt-1 font-medium">
                  <Link href={href}>{c.title}</Link>
                </h3>
                <p className="mt-3 text-sm leading-relaxed">{c.takeaway}</p>
              </li>
            );
          })}
        </ol>
      </section>
    </>
  );
}
