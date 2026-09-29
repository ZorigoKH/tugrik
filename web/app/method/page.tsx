import type { Metadata } from "next";
import Link from "next/link";

import { Table } from "@/components/Table";
import { getCopper, getGrowth, getMeta, getPrices } from "@/lib/data";
import { date, fixed } from "@/lib/format";
import { PAGE_LINKS, REPO_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "method",
  description:
    "How tugrik turns public data into its charts and sentences: the data fixes, the frozen " +
    "regressions, the standard errors, and what the numbers cannot tell you.",
};

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="mt-14 scroll-mt-6 text-lg font-medium">
      {children}
    </h2>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="mt-8 font-medium">{children}</h3>;
}

const CONTENTS = [
  ["data-fixes", "data fixes"],
  ["regressions", "the regressions in plain English"],
  ["standard-errors", "standard errors and small samples"],
  ["frozen", "frozen specifications and the methods changelog"],
  ["reference", "the 2026-09 reference numbers"],
  ["did-not-hold", "what didn't hold up"],
  ["limitations", "limitations"],
] as const;

/** Every change to a specification or a definition, newest first. */
const CHANGELOG: { date: string; change: string }[] = [
  {
    date: "2026-09-29",
    change:
      "The changes the pages show as % (the tugrik's 12-month and December-to-December " +
      "change, the copper price's annual change) are percent changes; they were 100 × log " +
      "changes. A big depreciation is now a rise of 15% or more in MNT per US dollar, not " +
      "15 log points; the same four years qualify. The regressions still use log changes.",
  },
  {
    date: "2026-09-28",
    change:
      "A partial year of coal exports is compared with the same months of 2019; the " +
      "exploration compared it with all of 2019.",
  },
  {
    date: "2026-09-28",
    change:
      "A year's export-price index needs only the previous year's weights; the exploration " +
      "also required the current year's. No value for 1997–2025 changes.",
  },
  {
    date: "2026-09-28",
    change:
      "The specification list below is frozen, as chosen after the exploration of 27 Sep 2026.",
  },
];

/** A reference value and the current one with the same number of decimals. */
function refDigits(x: number): number {
  return Math.abs(x) >= 10 ? 1 : 3;
}

export default function Method() {
  const meta = getMeta();
  const copper = getCopper();
  const growth = getGrowth();
  const prices = getPrices();
  const full = copper.samples.find((s) => s.id === "full")!;
  const post = copper.samples.find((s) => s.id === "post2017")!;
  const pageHref = (id: string) => PAGE_LINKS.find((p) => p.id === id)?.href ?? "/";

  return (
    <article className="max-w-3xl">
      <header className="pt-10 sm:pt-16">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">method</h1>
        <p className="mt-5 text-lg leading-snug sm:text-xl">
          How the numbers are made, in plain English, and what they cannot tell you.
        </p>
      </header>

      <nav aria-label="contents" className="mt-8 text-sm">
        <ol className="list-decimal space-y-1 pl-7 text-muted marker:text-line">
          {CONTENTS.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`}>{label}</a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="space-y-4 [&_p]:leading-relaxed">
        <p className="mt-10">
          Two stages make the site. A fetch step downloads each source on a schedule and stores
          it as plain CSV files. A build step, which never touches the network, turns the stored
          files into every number, chart and sentence on the site; run twice on the same files it
          gives the same bytes. Every change in the regressions below is 100 × the change in the
          natural log, so a coefficient on a price change is an elasticity: the % response to a
          1% move. Where the pages show such changes they call them log points; a change shown
          as % is an ordinary percent change.
        </p>

        <H2 id="data-fixes">data fixes</H2>
        <H3>one exchange rate from three</H3>
        <p>
          The Bank of Mongolia, the National Statistics Office and the IMF each publish a monthly
          average of tugrik per US dollar, and each has a few wrong months: the IMF&rsquo;s July
          2009 and April 2010 are about 10 tugrik off, its January 2012 about 20 and its October
          2016 about 60 (2.7%); the Bank of Mongolia&rsquo;s July 1996 and some end-of-month
          values in 2007–10; the NSO&rsquo;s April 2002 and November 2010. The site therefore
          builds its own consensus:
        </p>
        <ul className="list-disc space-y-1 pl-5 marker:text-line">
          <li>
            from 2001, the published average closest to the mean of the Bank of Mongolia&rsquo;s
            official daily rate over the month&rsquo;s weekdays (ties go to the NSO, then the
            IMF, then the Bank);
          </li>
          <li>1994–2000, the median of the published averages;</li>
          <li>1993, the Bank of Mongolia&rsquo;s average;</li>
          <li>July 1990 to 1992, the IMF&rsquo;s (the administered rate before the float).</li>
        </ul>
        <p>
          No rule ever picks one of the known wrong months, and the build checks that every
          month since 2001 lies within 0.5% of the daily mean, and stops if one does not (in
          September 2026 the largest gap was 0.25%). Where the chosen figure is the Bank of
          Mongolia&rsquo;s own, it appears in the downloadable consensus series.
        </p>

        <H3>consumer prices across three base years</H3>
        <p>
          The NSO publishes the CPI on base years 2015, 2020 and 2023, and revises the overlap
          each time. The site takes each month from the newest base that has it. The Bank of
          Mongolia reports inflation as first published; the two can differ by up to 1.4
          percentage points, so the Bank&rsquo;s figures are used only as a cross-check. If the
          NSO goes stale, the IMF&rsquo;s CPI fills the months after it ends.
        </p>

        <H3>trade: year to date to monthly</H3>
        <p>
          The NSO publishes exports as running totals from January. January&rsquo;s flow is its
          total; each later month is the change in the running total. The build refuses a year
          whose months do not add up to its last total, or in which a running total falls. The
          price per tonne of coal is export value divided by tonnes.
        </p>

        <H3>the export-price index</H3>
        <p>
          Mongolia has no official export-price index, so the site builds one from the World
          Bank&rsquo;s annual average prices of its six main exports:
        </p>
        <pre className="formula">{`mxpi_t = Σ_i  w_i,t−1 × 100·Δln p_i,t
i ∈ {coal, copper, gold, iron ore, oil, zinc}`}</pre>
        <p>
          The weights w are each good&rsquo;s share of the six goods&rsquo; exports the year
          before, so a year&rsquo;s index does not depend on that year&rsquo;s volumes. The one
          exception is the first year, 1996: there are no 1995 shares, so it uses its own. It
          enters the growth regression as 1997&rsquo;s &ldquo;year before&rdquo;; in the
          September 2026 data, starting the regression in 1998 instead moves the coefficient
          from 0.0849 to 0.0854 (t 3.66 to 3.52). The shares come from UN Comtrade for
          1996–2007 (a frozen seed), the NSO from 2011, and a straight line between 2007 and
          2011; the build checks that each year&rsquo;s shares sum to 1 (to 1e-9). A year needs
          twelve months of prices for all six goods.
        </p>

        <H3>the dollar and the policy rate</H3>
        <p>
          The Fed&rsquo;s broad dollar index was redefined in 2006. The old index (TWEXBMTH) runs
          to December 2005 and is rescaled onto the current one (TWEXBGSMTH) by their ratio in
          January 2006, so the two join without a jump. The policy rate is the rate in force at
          the end of each month; of two decisions in one month, the later counts. CNY per dollar
          comes from FRED, with the IMF&rsquo;s series filling in if FRED goes stale.
        </p>

        <H2 id="regressions">the regressions in plain English</H2>
        <p>
          Each is ordinary least squares on the published data, run by the author&rsquo;s{" "}
          <a href="https://github.com/ZorigoKH/Sandwich">sandwich</a> library.
        </p>

        <H3>copper and the tugrik</H3>
        <pre className="formula">{`Δmnt_t = a + Σ_j=0..12 b_j·Δcopper_t−j + Σ_j=0..12 c_j·Δcoal_t−j
         + d·Δusd_t + e·Δcny_t + ε_t`}</pre>
        <p>
          The monthly change in tugrik per dollar on this month&rsquo;s and the previous twelve
          months&rsquo; changes in the copper price and the Australian thermal coal price, with
          the broad dollar and the yuan in the same month. The sum b_0 + … + b_h is the total
          response after h months to a 1% copper move; the chart shows −10 times it, the
          weakening after a 10% fall. It is estimated on five samples: all months since 2001;
          without the crash of September 2008 to June 2009; 2001–2016; 2017 on; and 2017 on
          without China&rsquo;s border closures of February 2020 to December 2022.
        </p>
        <pre className="formula">{`Δ12mnt_t = a + b·Δ12copper_t−6 + c·Δ12coal_t−6 + d·Δ12usd_t + ε_t`}</pre>
        <p>
          The second chart uses 12-month changes and prices six months earlier, from December
          2002, to show how much of the tugrik&rsquo;s year-on-year movement they account for (R²).
        </p>

        <H3>pass-through to consumer prices</H3>
        <pre className="formula">{`π_t = a + Σ_j=0..12 b_j·Δmnt_t−j + month dummies + ε_t                  (plain)
π_t = … + ρ1·π_t−1 + ρ2·π_t−2 + Σ_j=0..3 Δoil_t−j + Σ_j=0..12 Δcopper_t−j   (preferred)
long run = (b_0 + … + b_12) / (1 − ρ1 − ρ2)`}</pre>
        <p>
          Monthly CPI inflation on the tugrik&rsquo;s depreciation this month and in the last
          twelve, with a dummy for each calendar month, from January 2002. The preferred version
          adds two months of past inflation (prices are sticky), the Brent oil price in dollars
          and the copper price, which stands in for the commodity cycle that moves demand and
          the tugrik together. Its standard error for the long run comes from the delta method.
          It is also run without September 2008 to December 2009, on 2002–2013, and on 2014 on.
        </p>

        <H3>growth and export prices</H3>
        <pre className="formula">{`growth_t = a + b0·mxpi_t + b1·mxpi_t−1 + ε_t`}</pre>
        <p>
          Real GDP growth (World Bank) on the export-price index this year and last year, from{" "}
          {growth.fit.start}. It is re-run without 2009, without 2020, without both, without 2011,
          and without 2021–23.
        </p>

        <H3>coal: tonnes and price</H3>
        <pre className="formula">{`Δln value = Δln tonnes + Δln (value ÷ tonnes)`}</pre>
        <p>
          Not a regression: an identity, true by definition for full calendar years. The build
          checks that the three published changes add up (to 1e-9) and that each matches the
          change in its published annual level: value, tonnes and value per tonne.
        </p>

        <H2 id="standard-errors">standard errors and small samples</H2>
        <p>
          Monthly changes are not independent draws: averages of daily rates build in overlap,
          and shocks cluster. Every standard error is therefore Newey–West (heteroskedasticity-
          and autocorrelation-consistent, Bartlett kernel) with L = ⌊4(T/100)^(2/9)⌋ lags:{" "}
          {full.maxlags} for the {full.nobs} months of the copper regression, {post.maxlags} for
          the {post.nobs} months since 2017, and {growth.fit.maxlags} for the {growth.fit.nobs}{" "}
          years of growth. The overlapping 12-month changes use {copper.fit12.maxlags} lags,
          since consecutive observations share eleven months. Tests use the t distribution with
          n − k degrees of freedom, and sums of coefficients are tested with the full covariance
          matrix (√(c′Vc)).
        </p>
        <p>
          With {growth.fit.nobs} years, Newey–West standard errors are too small and reject too
          often. The growth page therefore also reports the ordinary and HC1 p-values, and its
          sentence says to treat the result as descriptive. The pass-through estimates use{" "}
          {prices.specs[0]!.nobs} months but are poorly identified for a different reason; see
          below.
        </p>

        <H2 id="frozen">frozen specifications and the methods changelog</H2>
        <p>
          The regressions were chosen after exploring many lag lengths and samples in September
          2026, without any correction for multiple testing. To stop that search from continuing
          every month, the list is frozen: the build never scans lags, leads or samples, and a
          change to any specification is a code change, dated below. Only months after September
          2026 are genuinely out of sample.
        </p>
        <ul className="list-disc space-y-1 pl-5 marker:text-line">
          <li>
            <code>copper_dl12</code>: the tugrik on copper and coal, lags 0–12, five samples.
          </li>
          <li>
            <code>fx_fit12</code>: 12-month changes on prices six months earlier.
          </li>
          <li>
            <code>passthrough_dl</code> and <code>passthrough_pref</code>, with three subsamples.
          </li>
          <li>
            <code>growth</code>, with five sets of dropped years.
          </li>
          <li>
            <code>coal_decomp</code>: the coal identity.
          </li>
        </ul>
        <Table
          caption="Methods changelog: each change to a specification or definition, with its date."
          minWidth="24rem"
          captionVisible
          columns={[{ label: "date" }, { label: "change", align: "left" }]}
          rows={CHANGELOG.map((c, i) => ({ key: String(i), cells: [date(c.date), c.change] }))}
        />

        <H2 id="reference">the 2026-09 reference numbers</H2>
        <p>
          The headline estimates as first published, next to what the current data give. They
          move as new months arrive and old ones are revised.
        </p>
        <Table
          caption="Headline estimates from the September 2026 reference build and from the current data."
          minWidth="30rem"
          columns={[
            { label: "estimate", align: "left" },
            { label: "page", align: "left" },
            { label: "2026-09" },
            { label: "now" },
          ]}
          rows={meta.reference.map((r) => ({
            key: r.id,
            cells: [
              r.label,
              <Link key="p" href={pageHref(r.page)}>
                {r.page}
              </Link>,
              fixed(r.reference, refDigits(r.reference)),
              r.current === null ? "—" : fixed(r.current, refDigits(r.reference)),
            ],
          }))}
        />

        <H2 id="did-not-hold">what didn&rsquo;t hold up</H2>
        <p>The September 2026 exploration tried these as well. They are not shown, because:</p>
        <ul className="list-disc space-y-2 pl-5 marker:text-line">
          <li>
            <strong className="font-medium">The copper effect within three months.</strong> Over
            2001–2026 a 10% copper fall goes with 1.2–1.6% tugrik weakening within three months,
            but without September 2008 to June 2009 that halves, and since 2017 it is nil.
          </li>
          <li>
            <strong className="font-medium">Falls mattering more than rises.</strong> The
            asymmetry comes entirely from the 2008–09 crash; outside it, rises and falls have the
            same effect.
          </li>
          <li>
            <strong className="font-medium">The gold price.</strong> No effect on the tugrik.
          </li>
          <li>
            <strong className="font-medium">The World Bank&rsquo;s terms of trade and mining
            output in tonnes.</strong> Neither explains growth (19 and 20 years of data).
          </li>
          <li>
            <strong className="font-medium">Export receipts.</strong> Higher exports go with a
            stronger tugrik, but once copper prices six months earlier are included the effect
            more than halves and is not significant.
          </li>
          <li>
            <strong className="font-medium">The Bank of Mongolia&rsquo;s reaction.</strong> A
            10% depreciation over three months goes with a policy rate about 0.3 pp higher the
            next month, with an R² of 0.09: too weak to show.
          </li>
          <li>
            <strong className="font-medium">FDI and growth.</strong> They move together, but
            investment responds to growth as much as it causes it.
          </li>
        </ul>

        <H2 id="limitations">limitations</H2>
        <ul className="list-disc space-y-2 pl-5 marker:text-line">
          <li>
            These are associations, not causal effects, and the specifications were chosen after
            looking at the data.
          </li>
          <li>
            Growth has {growth.fit.nobs} observations; one year (2009, 2011, 2020) can move the
            estimate.
          </li>
          <li>
            Pass-through is poorly identified: depreciations coincide with commodity busts. There
            is no import-price index or split of the CPI into traded goods, and fuel and meat
            prices are partly administered.
          </li>
          <li>
            There is no free coking-coal benchmark, and the Australian thermal price is a poor
            proxy. Coal income depends on China&rsquo;s border policy, which no series measures.
          </li>
          <li>
            The regime was not constant: a managed float, IMF programmes in 2009 and 2017, and
            intervention in the currency market. Monthly averages build overlap into monthly
            changes.
          </li>
          <li>
            Every exchange-rate source has defects; the consensus rule is this project&rsquo;s own
            construction. CPI has three base years, and revised and as-first-reported figures
            differ by up to 1.4 pp.
          </li>
          <li>
            Coverage lags: the World Bank&rsquo;s FDI and current account end a year or two back.
            The IMF&rsquo;s forecasts belong to the IMF, and their vintage is labelled.
          </li>
          <li>
            The Bank of Mongolia&rsquo;s endpoints are undocumented, carry no licence and are
            hosted in Mongolia. They could change or disappear without notice.
          </li>
          <li>
            The headline numbers move as data arrive. The site shows what the current data say,
            next to the 2026-09 reference numbers above.
          </li>
        </ul>
        <p className="mt-10 text-sm text-muted">
          Sources, licences and downloads: <Link href="/data">data</Link>. The code, the tests
          and the frozen specifications: <a href={REPO_URL}>GitHub</a>.
        </p>
      </div>
    </article>
  );
}
