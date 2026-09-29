import type { Metadata } from "next";

import { Panels } from "@/components/charts/Panels";
import { ResponseChart, type ResponseSeries } from "@/components/charts/ResponseChart";
import { Caveats, PageHeader, Section, Takeaway } from "@/components/Section";
import { NumbersTable, Table } from "@/components/Table";
import { getPrices, pageTitle } from "@/lib/data";
import { dec, fixed, listing, month, pct, span, spct } from "@/lib/format";
import type { Est } from "@/lib/types";

export function generateMetadata(): Metadata {
  return { title: pageTitle("prices"), description: getPrices().takeaway };
}

/**
 * The same threshold as BIG_DEPRECIATION in pipeline/summarize.py: a rise of 15% or more in
 * MNT per US dollar, December to December.
 */
const BIG_DEPRECIATION = 15;

/** Pass-through as a % of the depreciation: 0.13 pp of CPI per 1% is 13%. */
function share(e: Est) {
  return { est: 100 * e.est, lo: 100 * e.lo, hi: 100 * e.hi };
}

/** "13.0% (−1.9% to 27.8%)" */
function withCi(e: Est | null): string {
  if (e === null) return "—";
  const s = share(e);
  return `${pct(s.est)} (${pct(s.lo)} to ${pct(s.hi)})`;
}

function orDash(v: number | null | undefined, f: (x: number) => string): string {
  return v === null || v === undefined ? "—" : f(v);
}

export default function PricesPage() {
  const p = getPrices();
  const dl = p.specs.find((s) => s.id === "dl")!;
  const pref = p.specs.find((s) => s.id === "preferred")!;
  const last = p.horizons.length - 1;

  const series: ResponseSeries[] = [
    {
      key: "dl",
      label: "plain distributed lag",
      points: dl.cum.map(share),
      role: "context",
      band: false,
      dashed: true,
    },
    {
      key: "preferred",
      label: "preferred",
      points: pref.cum.map(share),
      role: "accent",
      band: true,
    },
  ];
  const s12 = share(pref.cum[last]!);
  const responseLabel =
    `Cumulative share of a 1% depreciation of the tugrik that shows up in consumer prices, ` +
    `months 0 to 12. Preferred specification: ${pct(s12.est)} by month 12 (95% CI ` +
    `${pct(s12.lo)} to ${pct(s12.hi)}). Plain distributed lag, dashed: ` +
    `${pct(share(dl.cum[last]!).est)} by month 12.`;

  const cx = p.context;
  const cLast = cx.months.length - 1;
  const big = p.years.filter(
    (y) => y.fx_dec_dec_pct !== null && y.fx_dec_dec_pct >= BIG_DEPRECIATION,
  );
  const shade = big.map((y) => ({ label: y.year, start: `${y.year}-01`, end: `${y.year}-12` }));
  const contextLabel =
    `Consumer prices and the policy rate, and the 12-month % change in MNT per US dollar, ` +
    `${month(cx.months[0]!)} to ${month(cx.months[cLast]!)}. Latest: CPI ` +
    `${orDash(cx.cpi_yoy_pct[cLast], pct)} year on year, policy rate ` +
    `${orDash(cx.policy_rate_pct[cLast], pct)}, MNT per US dollar ` +
    `${orDash(cx.fx_12m_pct[cLast], spct)} over 12 months. Shaded: years when MNT per US ` +
    `dollar rose ${BIG_DEPRECIATION}% or more, ${listing(big.map((y) => y.year))}.`;

  // One row per year (December values) and the latest month.
  const copperBy = new Map(p.years.map((y) => [y.year, y.copper_avg_pct]));
  const contextRows = cx.months
    .map((m, i) => ({ m, i }))
    .filter(({ m, i }) => m.endsWith("-12") || i === cLast);

  return (
    <article>
      <PageHeader title={pageTitle("prices")} takeaway={p.takeaway}>
        <p>
          A weaker tugrik makes imports dearer: fuel, food, cars and machinery are mostly bought
          in dollars or yuan. The question is how much of a depreciation reaches the prices people
          pay, and how fast. The first chart answers it month by month: after a 1% fall in the
          tugrik against the dollar, how many percent of that 1% has shown up in the consumer
          price index.
        </p>
        <p>
          The preferred line holds constant what else moves prices at the same time: last
          months&rsquo; inflation, the oil price and the copper price. The dashed line leaves them
          out. The shaded band is the preferred line&rsquo;s 95% interval; where it includes
          zero, the data cannot tell the pass-through apart from none.
        </p>
      </PageHeader>

      <Section
        id="pass-through"
        title="from the tugrik to consumer prices"
        intro={
          <p>
            Cumulative % of a 1% depreciation that shows up in the consumer price index (pp of CPI
            per 1% depreciation × 100), {span(pref.start, pref.end)}. Hover, tap or use the
            arrow keys to read a month.
          </p>
        }
      >
        <ResponseChart
          horizons={p.horizons}
          series={series}
          kind="pct"
          yLabel="% of the depreciation in consumer prices"
          xLabel="months after the depreciation"
          label={responseLabel}
        />
        <NumbersTable
          caption="Cumulative % of a 1% depreciation that shows up in consumer prices, by month, with 95% intervals."
          minWidth="30rem"
          columns={[
            { label: "month" },
            { label: "preferred" },
            { label: "plain distributed lag" },
          ]}
          rows={p.horizons.map((h) => ({
            key: String(h),
            cells: [String(h), withCi(pref.cum[h]!), withCi(dl.cum[h]!)],
          }))}
        />
        <div className="mt-8">
          <h3 className="text-sm">the two specifications</h3>
          <p className="mt-1 max-w-2xl text-xs text-muted">
            Monthly CPI inflation on the tugrik&rsquo;s depreciation in months 0–12 and month
            dummies; the preferred one adds two months of past inflation, the oil price (months
            0–3) and the copper price (months 0–12). The long run divides by 1 − ρ₁ − ρ₂, the
            persistence of inflation. % of the depreciation, 95% intervals in brackets.
          </p>
          <div className="mt-3">
            <Table
              caption="The two pass-through specifications: sample, fit and cumulative effects."
              minWidth="48rem"
              columns={[
                { label: "specification", align: "left" },
                { label: "n" },
                { label: "lags" },
                { label: "R²" },
                { label: "by month 12" },
                { label: "long run" },
                { label: "ρ₁, ρ₂" },
              ]}
              rows={p.specs.map((s) => ({
                key: s.id,
                cells: [
                  s.label,
                  String(s.nobs),
                  String(s.maxlags),
                  dec(s.r2),
                  withCi(s.cum[last]!),
                  withCi(s.long_run),
                  s.rho === null ? "—" : `${dec(s.rho[0])}, ${dec(s.rho[1])}`,
                ],
              }))}
            />
          </div>
          {pref.oil_sum && pref.copper_sum && (
            <p className="mt-3 max-w-2xl text-xs text-muted">
              Controls in the preferred specification, pp of monthly CPI per 1%: oil, months 0–3,{" "}
              <span className="num text-fg">{dec(pref.oil_sum.est, 3)}</span> (
              {dec(pref.oil_sum.lo, 3)} to {dec(pref.oil_sum.hi, 3)}); copper, months 0–12,{" "}
              <span className="num text-fg">{dec(pref.copper_sum.est, 3)}</span> (
              {dec(pref.copper_sum.lo, 3)} to {dec(pref.copper_sum.hi, 3)}).
            </p>
          )}
        </div>
        <div className="mt-8">
          <h3 className="text-sm">other samples</h3>
          <p className="mt-1 max-w-2xl text-xs text-muted">
            The preferred specification on parts of the sample. % of the depreciation, 95%
            intervals in brackets.
          </p>
          <div className="mt-3">
            <Table
              caption="The preferred pass-through specification on subsamples: the share by month 12 and in the long run."
              minWidth="40rem"
              columns={[
                { label: "sample", align: "left" },
                { label: "n" },
                { label: "by month 12" },
                { label: "long run" },
              ]}
              rows={[
                {
                  key: "full",
                  cells: [
                    `whole sample, ${span(pref.start, pref.end)}`,
                    String(pref.nobs),
                    withCi(pref.cum[last]!),
                    withCi(pref.long_run),
                  ],
                },
                ...p.subsamples.map((s) => ({
                  key: s.id,
                  cells: [s.label, String(s.nobs), withCi(s.h12), withCi(s.long_run)],
                })),
              ]}
            />
          </div>
        </div>
      </Section>

      <Section
        id="context"
        title="why the raw link is weak"
        intro={
          <p>
            Consumer price inflation and the Bank of Mongolia&rsquo;s policy rate (a step at each
            decision), with the % change in tugrik per US dollar over 12 months underneath (up
            means a weaker tugrik). Shaded: years in which tugrik per US dollar rose{" "}
            {BIG_DEPRECIATION}% or more from December to December.
          </p>
        }
      >
        <Takeaway>{p.takeaway_context}</Takeaway>
        <Panels
          months={cx.months}
          panels={[
            {
              key: "rates",
              title: "consumer prices and the policy rate, %",
              kind: "pct",
              zero: true,
              series: [
                {
                  key: "cpi",
                  label: "CPI, year on year",
                  values: cx.cpi_yoy_pct,
                  role: "accent",
                },
                {
                  key: "policy",
                  label: "policy rate",
                  values: cx.policy_rate_pct,
                  role: "context",
                  step: true,
                },
              ],
            },
            {
              key: "fx",
              title: "MNT per US$, 12-month change, % (up = weaker tugrik)",
              kind: "pct",
              zero: true,
              series: [
                {
                  key: "fx",
                  label: "MNT per US$, 12 months",
                  values: cx.fx_12m_pct,
                  role: "accent",
                },
              ],
            },
          ]}
          shade={shade}
          shadeNote={`years when MNT per US$ rose ${BIG_DEPRECIATION}% or more, December to December (${listing(big.map((y) => y.year))})`}
          label={contextLabel}
        />
        <NumbersTable
          caption="Each December and the latest month: CPI inflation year on year, the policy rate, the 12-month % change in MNT per US dollar, and the % change in the average copper price over the calendar year."
          minWidth="36rem"
          columns={[
            { label: "month" },
            { label: "CPI y/y %" },
            { label: "policy rate %" },
            { label: "MNT per US$, 12 months %" },
            { label: "copper, year average %" },
          ]}
          rows={contextRows.map(({ m, i }) => ({
            key: m,
            cells: [
              month(m),
              orDash(cx.cpi_yoy_pct[i], (v) => fixed(v, 1)),
              orDash(cx.policy_rate_pct[i], (v) => fixed(v, 2)),
              orDash(cx.fx_12m_pct[i], (v) => fixed(v, 1, true)),
              m.endsWith("-12") ? orDash(copperBy.get(m.slice(0, 4)), (v) => fixed(v, 1, true)) : "—",
            ],
          }))}
        />
        {p.weo.years.length > 0 && (
          <p className="mt-6 max-w-2xl text-sm text-muted">
            The IMF&rsquo;s forecasts of average inflation
            {p.weo.vintage ? ` (World Economic Outlook, ${p.weo.vintage})` : ""}:{" "}
            {p.weo.years.map((y, i) => (
              <span key={y}>
                {i > 0 && ", "}
                <span className="whitespace-nowrap">
                  {y} <span className="num text-fg">{orDash(p.weo.cpi_avg_pct[i], pct)}</span>
                </span>
              </span>
            ))}
            .
          </p>
        )}
      </Section>

      <Caveats>
        <li>
          Pass-through is poorly identified here. The big depreciations came with commodity
          busts and weak demand, which hold prices down at the same time as the weaker tugrik
          pushes them up; the controls absorb only part of that.
        </li>
        <li>
          There is no import-price index and no split of CPI into traded and non-traded goods,
          and fuel and meat prices are partly administered.
        </li>
        <li>
          CPI has three base years (2015, 2020 and 2023). The site uses each month&rsquo;s figure
          from the newest base that has it; revised and as-first-reported figures differ by up to
          1.4 pp.
        </li>
        <li>
          The specification was chosen after exploring several, with no correction for multiple
          testing; only months after September 2026 are genuinely out of sample.
        </li>
      </Caveats>
    </article>
  );
}
