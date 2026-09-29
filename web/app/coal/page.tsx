import type { Metadata } from "next";
import Link from "next/link";

import { DecompBars, type DecompYear } from "@/components/charts/DecompBars";
import { Panels } from "@/components/charts/Panels";
import { Caveats, PageHeader, Section, Takeaway } from "@/components/Section";
import { NumbersTable, Table } from "@/components/Table";
import { getCoal, pageTitle } from "@/lib/data";
import { fixed, grouped, month, mt, pct, span, usdT } from "@/lib/format";

export function generateMetadata(): Metadata {
  return { title: pageTitle("coal"), description: getCoal().takeaway };
}

/** "+26.6", or "—" for a missing value. */
function signed(v: number | null): string {
  return v === null ? "—" : fixed(v, 1, true);
}

function orDash(v: number | null, f: (x: number) => string): string {
  return v === null ? "—" : f(v);
}

export default function CoalPage() {
  const c = getCoal();
  const full = c.annual.filter((r) => !r.partial);
  const partial = c.annual.filter((r) => r.partial);
  const bars: DecompYear[] = full.flatMap((r) =>
    r.dlog_value === null || r.dlog_volume === null || r.dlog_unit_value === null
      ? []
      : [{ year: r.year, volume: r.dlog_volume, price: r.dlog_unit_value, total: r.dlog_value }],
  );
  const byVolume = [...bars].sort((a, b) => a.volume - b.volume);
  const byPrice = [...bars].sort((a, b) => a.price - b.price);
  const decompLabel =
    `Change in the value of Mongolia's coal exports each year from ${bars[0]!.year} to ` +
    `${bars.at(-1)!.year}, split exactly into the change in tonnes and the change in price per ` +
    `tonne, in log points. Tonnes ranged from ${signed(byVolume[0]!.volume)} ` +
    `(${byVolume[0]!.year}) to ${signed(byVolume.at(-1)!.volume)} (${byVolume.at(-1)!.year}); ` +
    `price per tonne from ${signed(byPrice[0]!.price)} (${byPrice[0]!.year}) to ` +
    `${signed(byPrice.at(-1)!.price)} (${byPrice.at(-1)!.year}).`;

  const m = c.monthly;
  const mLast = m.months.length - 1;
  const panelsLabel =
    `Monthly coal exports from ${month(m.months[0]!)} to ${month(m.months[mLast]!)}: tonnes ` +
    `per month, and Mongolia's value per tonne against the Australian thermal benchmark, with ` +
    `China's border closures shaded. Latest, ${month(m.months[mLast]!)}: ` +
    `${orDash(m.volume_mt[mLast]!, mt)}, ${orDash(m.unit_value_usd_t[mLast]!, usdT)} against ` +
    `${orDash(m.benchmark_usd_t[mLast]!, usdT)} for the benchmark.`;

  return (
    <article>
      <PageHeader title={pageTitle("coal")} takeaway={c.takeaway}>
        <p>
          Mongolia&rsquo;s coal goes to China by truck and rail, so how much it earns depends on
          two things: how many tonnes cross the border and what each tonne fetches. The first
          chart splits each year&rsquo;s change in coal export income into exactly those two
          parts.
        </p>
        <p>
          Changes are in log points (100 × the change in the natural log), because log changes
          add up: the change in tonnes plus the change in price per tonne equals the change in
          income, with nothing left over. For small changes a log point is about 1%; +69 is
          roughly a doubling and −69 roughly a halving.
        </p>
      </PageHeader>

      <Section
        id="decomposition"
        title="tonnes or price?"
        intro={
          <p>
            Each bar is one year&rsquo;s change on the year before: the filled blue part is the
            change in tonnes shipped, the outlined gray part the change in price per tonne, and
            the dot the change in total income. Parts with the same sign stack; parts with opposite signs point away
            from zero on either side. Full years only; this year so far is below the chart. Hover, tap or use
            the arrow keys to read a year.
          </p>
        }
      >
        <DecompBars
          years={bars}
          volumeLabel="tonnes"
          priceLabel="price per tonne"
          totalLabel="income"
          yLabel="change on the year before, log points"
          label={decompLabel}
        />
        {partial.map((r) => (
          <p key={r.year} className="mt-4 max-w-2xl text-sm text-muted">
            {r.year} so far ({span(`${r.year}-01`, r.through)}):{" "}
            <span className="num text-fg">{mt(r.volume_mt)}</span> for{" "}
            <span className="num text-fg">${grouped(r.value_musd)}m</span>
            {r.unit_value_usd_t !== null && (
              <>
                {" "}
                at <span className="num text-fg">{usdT(r.unit_value_usd_t)}</span>
              </>
            )}
            {r.volume_vs_2019_pct !== null && (
              <>
                ; the tonnage is{" "}
                <span className="num text-fg">{pct(r.volume_vs_2019_pct, 0)}</span> of the same
                months of 2019
              </>
            )}
            .
          </p>
        ))}
        <NumbersTable
          caption="Mongolia's coal exports by year: value, tonnes, tonnage against 2019, value per tonne, the Australian benchmark, and the change in value split into tonnes and price (log points)."
          minWidth="50rem"
          columns={[
            { label: "year" },
            { label: "value, $m" },
            { label: "tonnes, Mt" },
            { label: "% of 2019 tonnes" },
            { label: "value, $/t" },
            { label: "benchmark, $/t" },
            { label: "Δ value" },
            { label: "Δ tonnes" },
            { label: "Δ price" },
          ]}
          rows={c.annual.map((r) => ({
            key: r.year,
            muted: r.partial,
            cells: [
              r.partial ? `${r.year} (to ${month(r.through)})` : r.year,
              grouped(r.value_musd),
              fixed(r.volume_mt, 1),
              orDash(r.volume_vs_2019_pct, (v) => fixed(v, 0)),
              orDash(r.unit_value_usd_t, (v) => fixed(v, 0)),
              orDash(r.benchmark_usd_t, (v) => fixed(v, 0)),
              signed(r.dlog_value),
              signed(r.dlog_volume),
              signed(r.dlog_unit_value),
            ],
          }))}
        />
      </Section>

      <Section
        id="monthly"
        title="month by month"
        intro={
          <p>
            Tonnes shipped each month, and what a tonne of Mongolia&rsquo;s coal was worth (export
            value ÷ tonnes) against the Australian thermal coal price, the only free world
            benchmark. Shaded: China&rsquo;s border closures ({span(c.border.start, c.border.end)}
            ).
          </p>
        }
      >
        <Takeaway>{c.takeaway_gap}</Takeaway>
        <Panels
          months={m.months}
          panels={[
            {
              key: "volume",
              title: "coal exports, million tonnes a month",
              kind: "mt",
              zero: true,
              series: [
                { key: "volume", label: "tonnes", values: m.volume_mt, role: "accent" },
              ],
            },
            {
              key: "price",
              title: "price per tonne, US$",
              kind: "usd_t",
              zero: true,
              series: [
                {
                  key: "unit",
                  label: "Mongolia's coal",
                  values: m.unit_value_usd_t,
                  role: "accent",
                },
                {
                  key: "benchmark",
                  label: "Australian benchmark",
                  values: m.benchmark_usd_t,
                  role: "context",
                  dashed: true,
                },
              ],
            },
          ]}
          shade={[{ label: "border closures", ...c.border }]}
          label={panelsLabel}
        />
        <NumbersTable
          caption="Monthly coal exports: tonnes, Mongolia's value per tonne and the Australian thermal benchmark."
          minWidth="26rem"
          columns={[
            { label: "month" },
            { label: "tonnes, Mt" },
            { label: "Mongolia, $/t" },
            { label: "benchmark, $/t" },
          ]}
          rows={m.months.map((mo, i) => ({
            key: mo,
            cells: [
              month(mo),
              orDash(m.volume_mt[i]!, (v) => fixed(v, 2)),
              orDash(m.unit_value_usd_t[i]!, (v) => fixed(v, 1)),
              orDash(m.benchmark_usd_t[i]!, (v) => fixed(v, 1)),
            ],
          }))}
        />
      </Section>

      <Caveats>
        <li>
          This page is arithmetic, not a regression: income = tonnes × price per tonne holds by
          definition, and the chart only shows which of the two moved.
        </li>
        <li>
          &ldquo;Price per tonne&rdquo; is a unit value: export value divided by tonnes, as the
          National Statistics Office reports them. It mixes coking and thermal coal and moves
          when the mix changes, not only when prices do.
        </li>
        <li>
          The NSO publishes trade year to date; monthly figures are the differences between
          consecutive months. Recent months are revised as customs data arrive.
        </li>
        <li>
          There is no free coking-coal benchmark, and the Australian thermal price is a poor proxy
          for what Mongolia sells. No series measures China&rsquo;s border policy directly.
        </li>
        <li>
          For the same reason, the world coal price in the tugrik regressions (see{" "}
          <Link href="/copper">copper</Link>) tracks Mongolia&rsquo;s coal income only loosely.
        </li>
      </Caveats>
    </article>
  );
}
