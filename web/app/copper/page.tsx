import type { Metadata } from "next";
import Link from "next/link";

import { ActualFitted } from "@/components/charts/ActualFitted";
import { CoefStrip, type CoefRow } from "@/components/charts/CoefStrip";
import { ResponseChart, type ResponseSeries } from "@/components/charts/ResponseChart";
import { Caveats, PageHeader, Section, Takeaway } from "@/components/Section";
import { NumbersTable, Table } from "@/components/Table";
import { getCopper, pageTitle } from "@/lib/data";
import { dec, fixed, month, pval, span, tstat } from "@/lib/format";
import type { CopperSampleId, Est } from "@/lib/types";

export function generateMetadata(): Metadata {
  return { title: pageTitle("copper"), description: getCopper().takeaway };
}

/** The chart's units: % tugrik weakening after a 10% copper fall, i.e. −10 × the sum. */
function weakening(e: Est) {
  return { est: -10 * e.est, lo: -10 * e.hi, hi: -10 * e.lo };
}

/** Log points with a sign: "+28.9". */
function lp(x: number): string {
  return fixed(x, 1, true);
}

/** "2.3 (1.1 to 3.4)" */
function withCi(p: { est: number; lo: number; hi: number }, digits = 1): string {
  return `${fixed(p.est, digits)} (${fixed(p.lo, digits)} to ${fixed(p.hi, digits)})`;
}

export default function CopperPage() {
  const c = getCopper();
  const sample = (id: CopperSampleId) => c.samples.find((s) => s.id === id)!;
  const full = sample("full");
  const pre = sample("pre2017");
  const post = sample("post2017");
  const last = c.horizons.length - 1;

  const series: ResponseSeries[] = [
    {
      key: "pre2017",
      label: `${pre.start.slice(0, 4)}–${pre.end.slice(0, 4)}`,
      points: pre.copper.map(weakening),
      role: "context",
      band: true,
      dashed: true,
    },
    {
      key: "post2017",
      label: `${post.start.slice(0, 4)}–now`,
      points: post.copper.map(weakening),
      role: "accent",
      band: true,
    },
  ];
  const responseLabel =
    `Cumulative tugrik weakening in the months after a 10% fall in the copper price, months 0 ` +
    `to 12, with 95% bands. ` +
    series
      .map((s) => {
        const p = s.points[last]!;
        const early = s.points[3]!;
        return (
          `${s.label}: ${fixed(early.est, 1)}% by month 3 and ${fixed(p.est, 1)}% by month 12 ` +
          `(95% CI ${fixed(p.lo, 1)} to ${fixed(p.hi, 1)}%)`
        );
      })
      .join("; ") +
    ".";

  const f = c.fit12;
  const fLast = f.months.length - 1;
  const fitLabel =
    `The 12-month change in MNT per US dollar in log points, actual and predicted (dashed) by ` +
    `copper and coal prices six months earlier and the broad dollar, ${month(f.months[0]!)} ` +
    `to ${month(f.months[fLast]!)}; R² ${dec(f.r2)}. Latest: actual ` +
    `${lp(f.actual_pct[fLast]!)}, predicted ${lp(f.fitted_pct[fLast]!)}.`;
  const yearEnds = f.months
    .map((m, i) => ({ m, i }))
    .filter(({ m, i }) => m.endsWith("-12") || i === fLast);

  const coefRows: CoefRow[] = [
    { key: "copper", label: "copper", sub: "months 0–12", ...full.copper[last]!, role: "accent" },
    { key: "coal", label: "world coal", sub: "months 0–12", ...full.coal_h12, role: "context" },
    { key: "usd", label: "broad dollar", sub: "same month", ...c.controls.usd, role: "context" },
    { key: "cny", label: "CNY per US$", sub: "same month", ...c.controls.cny, role: "context" },
  ];
  const coefLabel =
    `Effects on MNT per US dollar of a 1% rise in each, ${full.label}, with 95% intervals: ` +
    coefRows
      .map((r) => `${r.label} (${r.sub}) ${dec(r.est)} (${dec(r.lo)} to ${dec(r.hi)})`)
      .join("; ") +
    ".";
  const coefEst: Record<string, Est> = {
    copper: full.copper[last]!,
    coal: full.coal_h12,
    usd: c.controls.usd,
    cny: c.controls.cny,
  };

  return (
    <article>
      <PageHeader title={pageTitle("copper")} takeaway={c.takeaway}>
        <p>
          When the price of copper falls, Mongolia earns fewer dollars and the tugrik weakens:
          more tugrik are needed to buy one US dollar. The first chart follows that over a year.
          Each point is the total weakening, month by month, after a one-off 10% fall in the
          copper price, estimated from the monthly data with the world coal price, the dollar and
          the Chinese yuan held constant.
        </p>
        <p>
          The shaded bands are 95% intervals: a band that stays above zero means the weakening
          can be told apart from none at all. The two lines split the sample at 2017, when an IMF
          programme began, to show whether the size or the timing of the response changed.
        </p>
      </PageHeader>

      <Section
        id="response"
        title="after a 10% fall in copper"
        intro={
          <p>
            Cumulative % weakening of the tugrik against the US dollar in the months after a 10%
            fall in the copper price (−10 × the sum of the copper coefficients up to that month).
            Hover, tap or use the arrow keys to read a month.
          </p>
        }
      >
        <ResponseChart
          horizons={c.horizons}
          series={series}
          kind="pct"
          yLabel="% weaker tugrik"
          xLabel="months after the fall"
          label={responseLabel}
        />
        <NumbersTable
          caption="Cumulative % weakening of the tugrik after a 10% copper fall, with 95% intervals, by month and sample."
          minWidth="52rem"
          columns={[
            { label: "month" },
            ...c.samples.map((s) => ({ label: s.label, align: "right" as const })),
          ]}
          rows={c.horizons.map((h) => ({
            key: String(h),
            cells: [String(h), ...c.samples.map((s) => withCi(weakening(s.copper[h]!)))],
          }))}
        />
        <div className="mt-8">
          <h3 className="text-sm">each sample, at months 3 and 12</h3>
          <p className="mt-1 max-w-2xl text-xs text-muted">
            % weaker tugrik after a 10% copper fall, 95% interval in brackets. The same regression
            is run on each sample; months are listed as used.
          </p>
          <div className="mt-3">
            <Table
              caption="The copper regression on five samples: the weakening by month 3 and month 12, sample size, Newey–West lags and R²."
              minWidth="44rem"
              columns={[
                { label: "sample", align: "left" },
                { label: "months" },
                { label: "by month 3" },
                { label: "by month 12" },
                { label: "n" },
                { label: "lags" },
                { label: "R²" },
              ]}
              rows={c.samples.map((s) => ({
                key: s.id,
                cells: [
                  s.label,
                  span(s.start, s.end),
                  withCi(weakening(s.copper[3]!)),
                  withCi(weakening(s.copper[last]!)),
                  String(s.nobs),
                  String(s.maxlags),
                  dec(s.r2),
                ],
              }))}
            />
          </div>
        </div>
      </Section>

      <Section
        id="fit"
        title="how much of the tugrik it explains"
        intro={
          <p>
            The tugrik&rsquo;s change over 12 months (up means weaker) against the change a simple
            model predicts, dashed, from the copper and coal prices six months earlier and the
            broad US dollar index. Changes are in log points (100 × the change in the natural
            log), as in the regression: about the % change for small moves, less than it for
            large ones (+29 log points is +34%). Shaded: the global financial crisis, the
            commodity bust and China&rsquo;s border closures.
          </p>
        }
      >
        <Takeaway>{c.takeaway_fit}</Takeaway>
        <ActualFitted
          months={f.months}
          actual={f.actual_pct}
          fitted={f.fitted_pct}
          actualLabel="actual"
          fittedLabel="predicted"
          episodes={c.episodes}
          yLabel="change in MNT per US$ over 12 months, log points (up = weaker tugrik)"
          label={fitLabel}
        />
        <NumbersTable
          caption="The 12-month change in MNT per US dollar in log points, actual and predicted, each December and the latest month."
          columns={[
            { label: "12 months to" },
            { label: "actual, log points" },
            { label: "predicted, log points" },
          ]}
          rows={yearEnds.map(({ m, i }) => ({
            key: m,
            cells: [month(m), lp(f.actual_pct[i]!), lp(f.fitted_pct[i]!)],
          }))}
          minWidth="20rem"
        />
        <div className="mt-8">
          <h3 className="text-sm">the fitted model</h3>
          <p className="mt-1 max-w-2xl text-xs text-muted">
            {f.nobs} months, {span(f.months[0]!, f.months[fLast]!)}; Newey–West standard errors
            with {f.maxlags} lags, because consecutive 12-month changes overlap; R² {dec(f.r2)}.
          </p>
          <div className="mt-3">
            <Table
              caption="Coefficients of the 12-month fit with Newey–West standard errors, t-statistics, p-values and 95% intervals."
              columns={[
                { label: "12-month change in", align: "left" },
                { label: "coef" },
                { label: "se" },
                { label: "t" },
                { label: "p" },
                { label: "95% CI" },
              ]}
              rows={[
                { name: "copper, 6 months earlier", e: f.copper_t6 },
                { name: "world coal, 6 months earlier", e: f.coal_t6 },
                { name: "broad dollar, same months", e: f.usd },
              ].map(({ name, e }) => ({
                key: name,
                cells: [
                  name,
                  dec(e.est, 3),
                  dec(e.se, 3),
                  tstat(e.t),
                  pval(e.p),
                  `${dec(e.lo, 3)} to ${dec(e.hi, 3)}`,
                ],
              }))}
              minWidth="36rem"
            />
          </div>
        </div>
      </Section>

      <Section
        id="strip"
        title="copper, coal, the dollar and the yuan"
        intro={
          <p>
            The same regression as the first chart ({full.label}), read differently: the %
            change in MNT per US dollar for a 1% rise in each. Below zero means a stronger
            tugrik. Copper and world coal are summed over months 0–12; the dollar and the yuan
            enter in the same month only. A whisker that crosses zero cannot be told apart from
            no effect.
          </p>
        }
      >
        <CoefStrip
          rows={coefRows}
          axisLabel="% change in MNT per US$ per 1% rise (below zero = stronger tugrik)"
          label={coefLabel}
        />
        <NumbersTable
          caption="Effects on MNT per US dollar of a 1% rise in each, with Newey–West standard errors."
          columns={[
            { label: "a 1% rise in", align: "left" },
            { label: "coef" },
            { label: "se" },
            { label: "t" },
            { label: "p" },
            { label: "95% CI" },
          ]}
          rows={coefRows.map((r) => {
            const e = coefEst[r.key]!;
            return {
              key: r.key,
              cells: [
                `${r.label}, ${r.sub}`,
                dec(e.est, 3),
                dec(e.se, 3),
                tstat(e.t),
                pval(e.p),
                `${dec(e.lo, 3)} to ${dec(e.hi, 3)}`,
              ],
            };
          })}
          minWidth="36rem"
        />
      </Section>

      <Caveats>
        <li>
          These are associations in monthly data, not a controlled experiment. Copper prices are
          set in world markets, which makes it unlikely that the tugrik drives them, but other
          things that move with copper (Chinese demand, investment into Mongolia) are folded into
          the estimate.
        </li>
        <li>
          The monthly tugrik is this site&rsquo;s own consensus of three published averages (Bank
          of Mongolia, NSO, IMF), because each has a few wrong months; see the method.
        </li>
        <li>
          There is no free price for coking coal, which is most of what Mongolia sells, so
          &ldquo;world coal&rdquo; is the Australian thermal price. Its lack of effect says little
          about coal income itself; see <Link href="/coal">coal</Link>.
        </li>
        <li>
          In the 2026-09 exploration the effect within the first three months did not hold up:
          it halved without the 2008–09 crash and vanished after 2017. That is why the site
          reports the 12-month total.
        </li>
        <li>
          The regime was not constant: a managed float, IMF programmes in 2009 and 2017, and
          central-bank intervention.
        </li>
      </Caveats>
    </article>
  );
}
