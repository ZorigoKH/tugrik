import type { Metadata } from "next";
import Link from "next/link";

import { GrowthBars, type GrowthYear as BarYear } from "@/components/charts/GrowthBars";
import { ShareArea, type ShareLayer } from "@/components/charts/ShareArea";
import { YearScatter, type YearPoint } from "@/components/charts/YearScatter";
import { Caveats, PageHeader, Section, Takeaway } from "@/components/Section";
import { NumbersTable, Table } from "@/components/Table";
import { getGrowth, pageTitle } from "@/lib/data";
import { dec, fixed, listing, pct, pval, tstat, vintage as shortVintage } from "@/lib/format";
import { type Est, GOODS, type Good } from "@/lib/types";

export function generateMetadata(): Metadata {
  return { title: pageTitle("growth"), description: getGrowth().takeaway };
}

/** How many of the largest misses the scatter names. */
const LABELLED = 4;

const GOOD_LABELS: Record<Good, string> = {
  copper: "copper",
  coal: "coal",
  gold: "gold",
  iron_ore: "iron ore",
  oil: "oil",
  zinc: "zinc",
};

/** Copper in the accent, coal in a dark gray, the four small goods in alternating light grays. */
const GOOD_COLORS: Record<Good, string> = {
  copper: "var(--accent)",
  coal: "var(--share-strong)",
  gold: "var(--share-1)",
  iron_ore: "var(--share-2)",
  oil: "var(--share-1)",
  zinc: "var(--share-2)",
};

const WEIGHT_SOURCE_LABELS: Record<string, string> = {
  comtrade: "from UN Comtrade",
  interpolated: "interpolated",
  nso: "from the National Statistics Office",
};

function orDash(v: number | null, f: (x: number) => string): string {
  return v === null ? "—" : f(v);
}

function estRow(name: string, e: Est, digits = 3) {
  return {
    key: name,
    cells: [
      name,
      dec(e.est, digits),
      dec(e.se, digits),
      tstat(e.t),
      pval(e.p),
      `${dec(e.lo, digits)} to ${dec(e.hi, digits)}`,
    ],
  };
}

export default function GrowthPage() {
  const g = getGrowth();
  const f = g.fit;

  // The regression's own years, with its fitted values and misses.
  const sample = g.annual.flatMap((r) =>
    r.year >= f.start &&
    r.year <= f.end &&
    r.gdp_growth_pct !== null &&
    r.mxpi_pct !== null &&
    r.mxpi_lag_pct !== null
      ? [{ year: r.year, y: r.gdp_growth_pct, x0: r.mxpi_pct, x1: r.mxpi_lag_pct }]
      : [],
  );
  const fitted = (r: (typeof sample)[number]) =>
    f.const.est + f.mxpi.est * r.x0 + f.mxpi_l1.est * r.x1;
  const misses = sample
    .map((r) => ({ year: r.year, miss: Math.abs(r.y - fitted(r)) }))
    .sort((a, b) => b.miss - a.miss)
    .slice(0, LABELLED)
    .map((r) => r.year);
  const points: YearPoint[] = sample.map((r) => ({
    year: r.year,
    x: r.x1,
    y: r.y,
    labelled: misses.includes(r.year),
  }));
  // The fit line: C2 with this year's export prices held at their sample mean.
  const meanX0 = sample.reduce((s, r) => s + r.x0, 0) / sample.length;
  const xs = sample.map((r) => r.x1);
  const line = (x: number) => f.const.est + f.mxpi.est * meanX0 + f.mxpi_l1.est * x;
  const lineEnds = { x0: Math.min(...xs), x1: Math.max(...xs) };
  const fitLine = { ...lineEnds, y0: line(lineEnds.x0), y1: line(lineEnds.x1) };
  const scatterLabel =
    `Scatter of real GDP growth against the change in Mongolia's export prices the year ` +
    `before, ${f.start} to ${f.end}, ${sample.length} years, with the fitted line (slope ` +
    `${dec(f.mxpi_l1.est, 3)}). The largest misses are ${misses.join(", ")}.`;

  const vintage = g.weo.vintage === null ? "IMF WEO" : `IMF WEO ${shortVintage(g.weo.vintage)}`;
  const bars: BarYear[] = [
    ...g.annual.flatMap((r) =>
      r.year >= f.start && r.gdp_growth_pct !== null
        ? [{ year: r.year, value: r.gdp_growth_pct, forecast: false }]
        : [],
    ),
    ...g.weo.years.flatMap((y, i) => {
      const v = g.weo.gdp_growth_pct[i];
      return v === null || v === undefined ? [] : [{ year: y, value: v, forecast: true }];
    }),
  ];
  const actual = bars.filter((b) => !b.forecast);
  const forecast = bars.filter((b) => b.forecast);
  const lowest = actual.reduce((a, b) => (b.value < a.value ? b : a));
  const highest = actual.reduce((a, b) => (b.value > a.value ? b : a));
  const barsLabel =
    `Real GDP growth each year from ${actual[0]!.year} to ${actual.at(-1)!.year}, lowest ` +
    `${pct(lowest.value)} in ${lowest.year} and highest ${pct(highest.value)} in ` +
    `${highest.year}` +
    (forecast.length
      ? `, then the ${vintage} forecast: ` +
        forecast.map((b) => `${b.year} ${pct(b.value)}`).join(", ")
      : "") +
    ".";

  const years = g.annual.map((r) => r.year);
  const layers: ShareLayer[] = GOODS.map((good) => ({
    key: good,
    label: GOOD_LABELS[good],
    values: g.annual.map((r) => r.weights[good]),
    color: GOOD_COLORS[good],
  }));
  // Consecutive years with the same source of weights, for the intro.
  const runs: { source: string; from: string; to: string }[] = [];
  for (const r of g.annual) {
    const run = runs.at(-1);
    if (run && run.source === r.weights_source) run.to = r.year;
    else runs.push({ source: r.weights_source, from: r.year, to: r.year });
  }
  const first = g.annual[0]!;
  const lastYear = g.annual.at(-1)!;
  const mixLabel =
    `Shares of copper, coal, gold, iron ore, oil and zinc in these six exports, ` +
    `${first.year} to ${lastYear.year}. ${first.year}: ` +
    GOODS.map((k) => `${GOOD_LABELS[k]} ${pct(100 * first.weights[k], 0)}`).join(", ") +
    `. ${lastYear.year}: ` +
    GOODS.map((k) => `${GOOD_LABELS[k]} ${pct(100 * lastYear.weights[k], 0)}`).join(", ") +
    ".";

  return (
    <article>
      <PageHeader title={pageTitle("growth")} takeaway={g.takeaway}>
        <p>
          Mongolia&rsquo;s export-price index measures how the world prices of what it sells
          changed from one year to the next: copper, coal, gold, iron ore, oil and zinc, each
          weighted by its share of these exports the year before. When the index rises, the same
          tonnes earn more dollars.
        </p>
        <p>
          The scatter puts each year&rsquo;s growth against the index&rsquo;s change a year
          earlier. The line is a regression of growth on the index this year and last year, drawn
          with this year&rsquo;s change held at its average. With only {f.nobs} years, one or two
          unusual years can move it; the tables below drop them one at a time.
        </p>
      </PageHeader>

      <Section
        id="scatter"
        title="export prices, then growth"
        intro={
          <p>
            One dot per year, {f.start}–{f.end}. Across: the % change in the export-price index the
            year before (100 × log change). Up: real GDP growth. The {LABELLED} years the line
            misses most are named. Hover, tap or use the arrow keys to read a year.
          </p>
        }
      >
        <YearScatter
          points={points}
          fit={fitLine}
          xLabel="export prices, % change the year before"
          yLabel="real GDP growth, %"
          fitLabel="fitted line"
          label={scatterLabel}
        />
        <NumbersTable
          caption="Each year: the change in the export-price index the year before and the same year, real GDP growth, the regression's fitted value and the miss."
          minWidth="36rem"
          columns={[
            { label: "year" },
            { label: "export prices, year before %" },
            { label: "export prices, same year %" },
            { label: "growth %" },
            { label: "fitted %" },
            { label: "miss, pp" },
          ]}
          rows={sample.map((r) => ({
            key: r.year,
            cells: [
              r.year,
              fixed(r.x1, 1, true),
              fixed(r.x0, 1, true),
              fixed(r.y, 1),
              fixed(fitted(r), 1),
              fixed(r.y - fitted(r), 1, true),
            ],
          }))}
        />
        <div className="mt-8">
          <h3 className="text-sm">the regression</h3>
          <p className="mt-1 max-w-2xl text-xs text-muted">
            Real GDP growth (pp) on the % change in the export-price index this year and last year,{" "}
            {f.start}–{f.end}, {f.nobs} years; Newey–West standard errors with {f.maxlags} lags; R²{" "}
            {dec(f.r2)}. HAC standard errors are too small with this few years, so the p-value on
            last year&rsquo;s change is also given without them:{" "}
            <span className="num text-fg">{pval(f.p_l1_nonrobust)}</span> (ordinary) and{" "}
            <span className="num text-fg">{pval(f.p_l1_hc1)}</span> (HC1).
          </p>
          <div className="mt-3">
            <Table
              caption="Growth regression coefficients with Newey–West standard errors."
              minWidth="36rem"
              columns={[
                { label: "term", align: "left" },
                { label: "coef" },
                { label: "se" },
                { label: "t" },
                { label: "p" },
                { label: "95% CI" },
              ]}
              rows={[
                estRow("constant", f.const, 2),
                estRow("export prices, same year", f.mxpi),
                estRow("export prices, year before", f.mxpi_l1),
                estRow("both years together", f.sum),
              ]}
            />
          </div>
        </div>
        <div className="mt-8">
          <h3 className="text-sm">dropping unusual years</h3>
          <p className="mt-1 max-w-2xl text-xs text-muted">
            The coefficient on last year&rsquo;s export prices, re-estimated without the years
            listed.
          </p>
          <div className="mt-3">
            <Table
              caption="The coefficient on the export-price index the year before, with years dropped."
              minWidth="30rem"
              columns={[
                { label: "without", align: "left" },
                { label: "years" },
                { label: "coef" },
                { label: "t" },
                { label: "95% CI" },
              ]}
              rows={[
                {
                  key: "none",
                  cells: [
                    "(all years)",
                    String(f.nobs),
                    dec(f.mxpi_l1.est, 3),
                    tstat(f.mxpi_l1.t),
                    `${dec(f.mxpi_l1.lo, 3)} to ${dec(f.mxpi_l1.hi, 3)}`,
                  ],
                },
                ...g.robustness.map((r) => ({
                  key: r.drop.join("+"),
                  cells: [
                    r.drop.length > 2
                      ? `${r.drop[0]}–${r.drop.at(-1)}`
                      : r.drop.join(" and "),
                    String(r.nobs),
                    dec(r.mxpi_l1.est, 3),
                    tstat(r.mxpi_l1.t),
                    `${dec(r.mxpi_l1.lo, 3)} to ${dec(r.mxpi_l1.hi, 3)}`,
                  ],
                })),
              ]}
            />
          </div>
        </div>
      </Section>

      <Section
        id="growth-bars"
        title="growth, and the IMF's forecast"
        intro={
          <p>
            Real GDP growth each year (World Bank), then the IMF&rsquo;s forecast from its World
            Economic Outlook{g.weo.vintage ? ` of ${g.weo.vintage}` : ""}. Hover, tap or use the
            arrow keys to read a year.
          </p>
        }
      >
        <Takeaway>{g.takeaway_weo}</Takeaway>
        <GrowthBars
          years={bars}
          forecastLabel={vintage}
          yLabel="real GDP growth, %"
          label={barsLabel}
        />
        <NumbersTable
          caption="Real GDP growth by year, actual then the IMF forecast."
          minWidth="18rem"
          columns={[{ label: "year" }, { label: "growth %" }, { label: "kind", align: "left" }]}
          rows={bars.map((b) => ({
            key: b.year,
            muted: b.forecast,
            cells: [b.year, fixed(b.value, 1), b.forecast ? `forecast, ${vintage}` : "actual"],
          }))}
        />
      </Section>

      <Section
        id="mix"
        title="what the index is made of"
        intro={
          <p>
            Each good&rsquo;s share of the six exports in the index, by year:{" "}
            {listing(
              runs.map((r) => `${r.from}–${r.to} ${WEIGHT_SOURCE_LABELS[r.source] ?? r.source}`),
            )}
            . Each year&rsquo;s index uses the previous year&rsquo;s shares; the first year,{" "}
            {first.year}, has no previous year and uses its own.
          </p>
        }
      >
        <Takeaway>{g.takeaway_mix}</Takeaway>
        <ShareArea years={years} layers={layers} label={mixLabel} />
        <NumbersTable
          caption="Shares of the six goods in the export-price index weights, by year, and where the shares come from."
          minWidth="40rem"
          columns={[
            { label: "year" },
            ...GOODS.map((k) => ({ label: `${GOOD_LABELS[k]} %` })),
            { label: "source", align: "left" as const },
          ]}
          rows={g.annual.map((r) => ({
            key: r.year,
            cells: [
              r.year,
              ...GOODS.map((k) => fixed(100 * r.weights[k], 1)),
              r.weights_source,
            ],
          }))}
        />
      </Section>

      <Section
        id="boom-bust"
        title="boom and bust, year by year"
        intro={
          <p>
            The two commodity cycles since 2008 in one table: the 2011–12 boom and the bust to 2016,
            then the border closures of 2020–22 and the recovery. Growth and CPI are as
            published; the MNT per US$ and copper price columns are % changes.
          </p>
        }
      >
        <Table
          caption="Mongolia's economy by year: growth, inflation, the tugrik, the policy rate, FDI, the current account, government debt, exports and the copper price."
          minWidth="60rem"
          columns={[
            { label: "year" },
            { label: "growth %" },
            { label: "CPI %" },
            { label: "MNT per US$, Dec–Dec %" },
            { label: "policy rate, Dec %" },
            { label: "FDI, % GDP" },
            { label: "current account, % GDP" },
            { label: "gov. debt, % GDP" },
            { label: "exports, $bn" },
            { label: "copper price %" },
          ]}
          rows={g.boom_bust.map((r) => ({
            key: r.year,
            cells: [
              r.year,
              orDash(r.gdp_growth_pct, (v) => fixed(v, 1)),
              orDash(r.cpi_pct, (v) => fixed(v, 1)),
              orDash(r.fx_dec_dec_pct, (v) => fixed(v, 1, true)),
              orDash(r.policy_rate_dec_pct, (v) => fixed(v, 2)),
              orDash(r.fdi_pct_gdp, (v) => fixed(v, 1)),
              orDash(r.current_account_pct_gdp, (v) => fixed(v, 1)),
              orDash(r.gov_debt_pct_gdp, (v) => fixed(v, 1)),
              orDash(r.exports_usd_bn, (v) => fixed(v, 1)),
              orDash(r.copper_pct, (v) => fixed(v, 1, true)),
            ],
          }))}
        />
        <p className="mt-3 max-w-3xl text-xs text-muted">
          Growth, FDI and the current account: World Bank WDI. CPI (annual average) and
          government debt: IMF World Economic Outlook. The tugrik: this site&rsquo;s consensus
          monthly average. Policy rate: Bank of Mongolia, at the end of December. Exports: NSO.
          Copper price: the change in its annual average (World Bank Pink Sheet). A dash means
          the source has not published the year yet.
        </p>
      </Section>

      <Caveats>
        <li>
          {f.nobs} years is a small sample. Newey–West standard errors are too small at this
          size, so treat the result as descriptive; the ordinary p-value is given next to the
          robust t-statistic.
        </li>
        <li>
          One year can move the estimate. The table above re-estimates without the years the
          2026-09 exploration found most influential; that list is frozen, like the regression.
        </li>
        <li>
          The index covers prices only. Growth also depends on volumes, and on investment, which
          drove the 2011–12 boom (see the FDI column above).
        </li>
        <li>
          The IMF forecasts belong to the IMF and change twice a year; the vintage is labelled.
          WDI&rsquo;s FDI and current account run a year or two behind. See{" "}
          <Link href="/data">the data</Link>.
        </li>
      </Caveats>
    </article>
  );
}
