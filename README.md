# tugrik

[![tests](https://github.com/ZorigoKH/tugrik/actions/workflows/ci.yml/badge.svg)](https://github.com/ZorigoKH/tugrik/actions/workflows/ci.yml)
[![data](https://github.com/ZorigoKH/tugrik/actions/workflows/data.yml/badge.svg)](https://github.com/ZorigoKH/tugrik/actions/workflows/data.yml)
![python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![license](https://img.shields.io/badge/license-MIT-green)

**Mongolia's economy explained by the price of copper, and by how many coal trucks China lets
across the border.**

Mongolia digs copper and coal and sells nearly all of both to China. `tugrik` is a static
website (*tögrög, copper and coal: Mongolia's economy in four charts*) that asks what this
does to the country's money, its prices and its growth. A Python pipeline turns public data
from seven publishers into JSON, a Next.js site draws it with hand-written SVG charts, and a
scheduled GitHub Actions job refreshes it three times a month. The tests run offline.
Site: (link coming soon)

## What the site shows

There is one page per finding. The sentences in quotes are the site's own: the build generates
each one from the current estimates, using a template with thresholds, so the wording changes
when the numbers do. Nothing is typed in by hand. The figures below come from the build of
28 September 2026, with data through August 2026.

### 1. Copper moves the tugrik, with a lag (`/copper`)

> A 10% fall in the copper price has been followed by a 2.3% weaker tugrik over the next 12
> months (95% CI 1.1–3.4%, 2001–2026). Since 2017 it arrives after month 3: of the 2.0% (95%
> CI 1.1–3.0%), 0.2% comes in months 0–3. World coal prices show no such effect (+0.06, the
> wrong sign).

The regression runs month by month. The change in MNT per US dollar is regressed on copper
(lags 0–12), Australian thermal coal (lags 0–12), the broad dollar and CNY/USD. Each row of
the table shows the cumulative effect of a 10% copper fall:

| sample | months | tugrik weaker after 12 months | 95% CI | of which months 0–3 |
|---|---:|---:|---|---:|
| 2001–2026 | 308 | 2.3% | 1.1–3.4% | 1.2% |
| without the financial crisis (Sep 2008–Jun 2009) | 298 | 1.9% | 0.9–3.0% | 0.7% |
| 2001–2016 | 192 | 2.1% | 0.7–3.4% | 1.2% |
| 2017–2026 | 116 | 2.0% | 1.1–3.0% | 0.2% |
| 2017–2026 without the border closures | 81 | 2.2% | 0.5–3.9% | 0.6% |

> Copper and coal prices six months earlier and the dollar account for about half of the
> tugrik's year-on-year moves (R² = 0.49).

### 2. Coal is a volume story (`/coal`)

> Coal income followed the Chinese border: shipments fell to 44% of their 2019 tonnage in 2021
> and reached 246% in 2025, while Mongolia's price per tonne went from 172 to 64 USD/t.

The page splits each year's change in coal export value exactly into the change in tonnes
plus the change in price per tonne. This is arithmetic, not a regression.

| year | exports, Mt | % of 2019 | Mongolia's price, USD/t | Australian benchmark, USD/t | value, USD m |
|---|---:|---:|---:|---:|---:|
| 2019 | 36.6 | 100 | 84 | 78 | 3,079 |
| 2021 | 16.1 | 44 | 172 | 138 | 2,774 |
| 2023 | 69.6 | 190 | 128 | 173 | 8,898 |
| 2025 | 90.0 | 246 | 64 | 108 | 5,769 |
| 2026, Jan–Aug | 77.8 | | 70 | 130 | 5,435 |

> Mongolia's coal fetched $75/t in Aug 2026 against $135 for the Australian benchmark. Since
> 2017 it has sold for between 36% and 232% of the benchmark, so world coal prices say little
> about what Mongolia earns.

### 3. A weaker tugrik barely shows in prices, as far as the data can tell (`/prices`)

> About 13% of a depreciation shows up in consumer prices within a year, but the data can't
> rule out zero or 28% (95% CI −2% to 28%).

The page regresses monthly CPI inflation (NSO) on depreciation, lags 0–12, with month
dummies. The preferred specification also includes two lags of inflation, oil and copper.

| specification | within 12 months | 95% CI | long run |
|---|---:|---|---:|
| plain distributed lag | −2% | −20% to 15% | |
| preferred, 2002–2026 | 13% | −2% to 28% | 22% (−2% to 45%) |
| preferred, without Sep 2008–Dec 2009 | 9% | −6% to 25% | 16% |
| preferred, 2002–2013 | 19% | −10% to 48% | 33% |
| preferred, 2014–2026 | 14% | 0% to 28% | 22% (1% to 43%) |

> The big depreciations (2009, 2013, 2016 and 2022: MNT per US$ up 15% or more, December to
> December) all came in years of falling copper prices. That is one reason the raw link from
> the tugrik to prices (−2% of a depreciation within a year, 95% CI −20% to 15%) cannot be
> told apart from zero.

### 4. Growth follows export prices a year later (`/growth`)

> A 10% rise in Mongolia's export prices has been followed by about 0.85 pp faster growth the
> next year (29 years; t = 3.7 with HAC, p = 0.016 without — treat as descriptive).

Real GDP growth (WDI, 1997–2025) is regressed on the change in an export-price index this
year and last year. The index weights copper, coal, gold, iron ore, oil and zinc prices by
Mongolia's own export shares in the previous year. Dropping the years that could drive the
result leaves it standing:

| dropped | years | effect of last year's export prices | t (HAC) |
|---|---:|---:|---:|
| none | 29 | 0.085 | 3.66 |
| 2009 | 28 | 0.088 | 3.69 |
| 2020 | 28 | 0.075 | 3.48 |
| 2009 and 2020 | 27 | 0.078 | 3.23 |
| 2011 | 28 | 0.066 | 3.47 |
| 2021–2023 | 26 | 0.091 | 3.37 |

> The IMF expects 5.3% in 2026 and about 5% a year after that.
>
> Coal went from none of these exports in 1996 to 67% in 2023; in 2025, copper and coal split
> them 42/41.

The home page adds the latest value of each headline series with a three-year sparkline:
MNT 3,594 per US dollar (Aug average), CPI 12.5% year on year, a 12.5% policy rate, copper at
$14,326/t, coal exports of 9.4 Mt at $75/t (August) and growth of 6.8% (2025). `/data` lists
every source with its endpoint, freshness, licence and CSV downloads. `/method` explains the
data fixes and the regressions, and shows what didn't hold up. It also sets the 2026-09
reference numbers next to the current ones.

## How it works

```
  Bank of Mongolia · NSO · World Bank Pink Sheet · IMF SDMX · IMF DataMapper · WDI · FRED
        │
        │  python -m pipeline.fetch --store data         network; one source at a time
        ▼
  data/*.csv + data/status.json                          the committed store
        │
        │  python -m pipeline.build --store data \       offline, pure, deterministic
        │      --out web/data --csv web/public/csv
        ▼
  web/data/*.json + web/public/csv/*.csv
        │
        │  npm run build                                 lib/data.ts checks every file
        ▼
  web/out/                                               static HTML
```

The work is split into two stages. **fetch** is the only code that uses the network. **build**
turns whatever is in the store into the site's data, and it is what the tests and local
development run.

**Fetch checks every source on its own before it writes anything:**

1. **Sanity.** Every expected series must be present, and no unexpected one (a new NSO CPI base
   year shows up as an unknown series and needs a human). Dates must be well formed, and
   monthly series may not skip a month. Values must stay within bounds (MNT/USD 1–20,000, CPI
   m/m −10 to 30, copper 500–50,000 USD/t, volumes ≥ 0, policy rate 0–30). No series may end
   earlier than the stored one or lose more than one row. The Pink Sheet's "Updated on" date
   must be at most 45 days old, because its download URL rotates and old URLs freeze.
2. **Revision guard.** Stored history may only move within a tolerance. Exchange rates may
   move 0.1% (after 2 months), Pink Sheet prices 0.5%, NSO trade 2% (after 12 months) and NSO
   CPI 0.05 pp (after 3 months). Past policy-rate decisions may not change at all. A breach
   fails the source unless it is named in `--accept-revisions`. WDI and IMF annual data are
   revised on schedule, so their revisions are accepted and counted.
3. **Cross-source checks.** The latest month of each published monthly FX average must be
   within 0.5% of the BoM daily weekday mean, or, when the BoM's daily rate is missing, of the
   other averages for that month. The Pink Sheet must be within 2% of the IMF for copper, gold
   and zinc. NSO CPI must be within 0.5 pp of the IMF's, and WDI growth within 0.3 pp of the
   WEO's. A breach rejects the side that changed, unless that source is named in
   `--accept-revisions`.
4. **Writes.** A source that passes has its changed files replaced atomically (a temporary
   file, then `os.replace`). A source that fails keeps its previous data, is marked stale in
   `data/status.json` and prints a `::warning::`. If three or more sources fail, or a source
   fails with nothing stored yet, the run writes nothing and exits 1.

The HTTP layer uses one `requests` session with the default User-Agent (the IMF's edge refuses
custom and browser ones), 10 s to connect and 90 s to read. It makes three attempts, backing off
2 s and then 4 s, and sends at most two requests a second to NSO.

**Build** runs the transforms, the frozen regressions and the takeaway templates, then writes
everything to a temporary directory. There `pipeline.validate` checks the schema and the
invariants: contiguous months, lo ≤ est ≤ hi, 13 horizons per response, the coal identity to
1e-9 (with each change matching its published annual levels), export weights that sum to 1,
and every sentence consistent with its estimate. Only then
are the files moved into place, with `meta.json` last. The output is deterministic: keys are
sorted, floats are rounded to 6 decimals, NaN becomes `null`, and `generated_at` moves only when
other content changed, so a rebuild of an unchanged store changes no bytes. A source counts as
stale if its last fetch failed or its data are older than the registry allows. When NSO or FRED
is stale, the IMF's CPI or CNY/USD continues the series, and the site says so.

**The data fixes.** No single FX source is clean, so the monthly exchange rate follows a
consensus rule. From 2001, each month uses whichever of the NSO, IMF and BoM averages is
closest to the BoM daily weekday mean. That removes known one-source defects, and every month
since 2001 ends up within about 0.25% of the daily mean; the build stops if a month is more
than 0.5% away. CPI is spliced from three NSO base years,
newest first. NSO trade tables are cumulative from January, so they are turned into monthly
flows. The broad dollar index is ratio-spliced from the discontinued TWEXBMTH to TWEXBGSMTH at
2006-01.

**The regressions** are few, and they are frozen in `pipeline/models.py`. Each one is OLS with
Newey–West (HAC) standard errors from [sandwich](https://github.com/ZorigoKH/Sandwich), using
`floor(4(T/100)^(2/9))` lags, or 12 for overlapping year-on-year changes. Confidence intervals
use t with n − k degrees of freedom, and cumulative effects are linear combinations with the
HAC covariance. The build never searches over lags or samples: a change to a specification is
a code change, and it is logged in the methods changelog on `/method`.

**The schedule.** [`data.yml`](.github/workflows/data.yml) runs at 02:41 UTC on the 3rd, 12th
and 20th of each month. The Pink Sheet is out about the 2nd and NSO trade and CPI by about the
11th. The job fetches, builds and validates. If `data/` or `web/` changed, it commits as
`github-actions[bot]` ("Refresh the data through 2026-08") and pushes. A stale source makes the
job pass with a warning. An aborted fetch fails it, so GitHub sends an email. A manual run takes
an `accept_revisions` input, which lets the named sources' updates through both the revision
guard and the cross-source checks. [`probe.yml`](.github/workflows/probe.yml) is run by hand. It
sends one request per endpoint, carrying on past a failed one, and reports the status, size
and latency, which shows whether a GitHub
runner can reach the BoM, NSO and the IMF DataMapper. The scheduled jobs install with
[`ci/constraints.txt`](ci/constraints.txt), which pins the numpy, pandas and scipy minor
versions so the output stays byte-for-byte stable.

## Data sources

| publisher | series | endpoint | frequency | licence | CSV on the site |
|---|---|---|---|---|---|
| Bank of Mongolia | USD/MNT daily and monthly average; policy-rate decisions; CPI as reported | `POST https://www.mongolbank.mn/en/currency-rate-movement/data` (and `/data/monthly`), `…/en/policy-interest-rate/data`, `…/en/inflation/data` | daily | none stated; public central-bank data, attributed to the Bank of Mongolia | no |
| National Statistics Office of Mongolia | CPI m/m and y/y (three base years); USD/MNT average and end of month; exports by good, value and volume | `POST https://data.1212.mn/api/v1/en/NSO/…` (PxWeb, json-stat2) | monthly | official statistics; reuse citing "Source: Mongolian Statistical Service" | yes |
| World Bank, Pink Sheet | copper, Australian thermal coal, gold, iron ore, Brent, zinc | `CMO-Historical-Data-Monthly.xlsx`, link scraped from `https://www.worldbank.org/en/research/commodity-markets` | monthly | CC BY 4.0 | yes |
| IMF, SDMX 2.1 | MNT/USD average and end of month; CPI; copper, gold and zinc (PCPS); CNY/USD | `GET https://api.imf.org/external/sdmx/2.1/data/…` | monthly | IMF terms: free reuse with attribution | yes |
| IMF, DataMapper | WEO growth, inflation, government debt and current account (with forecasts); China growth | `GET https://www.imf.org/external/datamapper/api/v2/…` | twice a year | IMF terms: free reuse with attribution | yes |
| World Bank, WDI | GDP growth; China GDP growth; FDI and current account, % of GDP | `GET https://api.worldbank.org/v2/country/…` | annual | CC BY 4.0 | yes |
| FRED | broad dollar index (TWEXBGSMTH); CNY per US dollar (EXCHUS) | `GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=…` | monthly | Federal Reserve Board data; cite FRED | yes |
| UN Comtrade (static seed) | Mongolia's exports of the six goods, 1996–2007 | never fetched; see [`data/static/README.md`](data/static/README.md) | frozen | UN Comtrade terms of use | no |
| FRED (static seed) | the discontinued broad dollar index TWEXBMTH | never fetched | frozen | Federal Reserve Board data; cite FRED | yes |

The site does not offer raw BoM data as a download, because the BoM states no licence. The
series this project derives, such as the consensus exchange rate, the spliced CPI and the
export-price index, are downloadable with their sources credited. `/data` lists every series
with its first and last observation and its status.

## Run it

Python 3.10 or later, and Node 20.9 or later for the site.

```bash
git clone https://github.com/ZorigoKH/tugrik.git && cd tugrik
pip install -e ".[dev]"

python -m pipeline.build --store data --out web/data --csv web/public/csv   # offline: store -> JSON
python -m pipeline.validate web/data                                        # schema and invariants
cd web && npm ci && npm run build                                           # the static site, in web/out/
```

The build prints the takeaways it generated. To refresh the store from the publishers, which
needs the network and takes about a minute:

```bash
python -m pipeline.probe                    # can this machine reach every endpoint?
python -m pipeline.fetch --store data       # every source; a failing one keeps its data
python -m pipeline.fetch --store data --only nso --accept-revisions nso
```

Then build again. To get output that is byte-identical to the scheduled job's, install with
`pip install -e . -c ci/constraints.txt` on Python 3.12 or later.
[web/README.md](web/README.md) explains how the site reads the data.

## Tests

```bash
pytest                                  # 153 tests, offline, about 10 seconds
ruff check . && ruff format --check .
```

- **Parsers** run on small synthetic payloads in each publisher's real shape. No real BoM
  data is committed. The payloads cover BoM's `"3,594.47"` strings, NSO's json-stat2 with
  Cyrillic dimension codes and year-to-date totals, a Pink Sheet workbook built with openpyxl
  (a leading "Mismatch Details" sheet, `2026M08`, `…` for missing), the link scraper failing
  loudly, an all-countries DataMapper answer, SDMX CSV with stray 1900 rows, WDI nulls and
  FRED's `.`.
- **HTTP.** No custom User-Agent is ever sent. A 503, 503, 200 sequence succeeds after backing
  off. A 403 fails at once, as a soft failure. NSO gets at most two requests a second.
- **Transforms.** The tests cover the consensus rule on a month where the IMF is 10 MNT off,
  the weekday mean and end of month, the newest-base CPI splice, the policy step function with
  two decisions in one month, lagged export weights that sum to 1, and the exact coal identity.
- **Models.** `nw_lags` gives 308 → 5, 116 → 4 and 29 → 3. A simulated distributed lag with
  AR(1) errors recovers its Σβ. The `lincom` standard error is √(c′Vc), and HAC standard
  errors match statsmodels.
- **The reference vintage.** `tests/fixtures/store_2026-09/` holds the model inputs of
  September 2026 and reproduces the exploratory regressions to 5e-4: copper Σ₀..₁₂ = −0.226
  (se 0.059), pass-through 0.130 at 12 months and 0.215 in the long run, growth 0.085, and
  coal exports in 2021 of 16.1 Mt, 44.0% of 2019.
- **Takeaways.** Every branch of every template is tested: significant or not, with the
  timing clause on and off, the coal clause, and the "can't rule out" clause.
- **Safety.** A fetch that raises leaves the store byte-identical. One failing source goes
  stale while the build still succeeds; three abort with nothing written. A revision beyond
  tolerance is rejected unless accepted, and so is a new NSO base year. An exchange-rate
  average that is off is rejected even when the BoM is down, while an old bad month never
  blocks a later update. Two builds give identical bytes. Validation rejects a missing field,
  a NaN, a gap, or a sentence that disagrees with its numbers.

CI runs lint, the tests and an offline build on Python 3.10 to 3.13. A second workflow
typechecks and builds the site on Node 22.

## Limitations

- These are reduced-form associations, not causal effects. The shipped specifications were
  chosen after an exploration, in September 2026, that tried many lags and samples with no
  correction for multiple testing. Freezing them now means that only new months are genuinely
  out of sample.
- Growth has only 29 years, and HAC standard errors over-reject at that size, so the page also
  shows non-robust p-values. A single year (2009, 2011, 2020) can move the estimates.
- Pass-through is poorly identified, because depreciations coincide with commodity busts.
  There is no import-price or tradables CPI split, and fuel and meat prices are partly
  administered.
- There is no free coking-coal benchmark, and Australian thermal coal is a poor proxy.
  Coal income depends on China's border policy, which no series measures.
- The regime has not been constant: a managed float, IMF programmes in 2009 and 2017, and FX
  intervention. Monthly averages also put an MA(1) into the changes.
- Every FX source has defects. The consensus rule is this project's own construction, and it
  is documented on `/method`. CPI comes in three base years, and the revised and as-reported
  figures differ by up to 1.4 pp.
- Coverage lags. WDI FDI and the current account end in 2024, and the IMF's forecasts belong to
  the IMF (the vintage is labelled).
- The BoM endpoints are undocumented, carry no licence and are hosted in Mongolia. They could
  change or disappear without notice. If they do, the monthly FX average falls back to NSO and
  the IMF, and the policy rate goes stale.
- Headline numbers move as new data arrive. The site shows what the current data say, next to
  the 2026-09 reference numbers.

## Built on sandwich

The regressions run on [sandwich](https://github.com/ZorigoKH/Sandwich), my NumPy
econometrics engine, which also powers [unbundle](https://github.com/ZorigoKH/unbundle).
Every covariance estimator in it is bread · meat · bread, and only the meat changes.

## Layout

```
pipeline/
  http.py            one requests session: timeouts, retries, NSO pacing, default User-Agent
  sources/           bom, nso, pinksheet, imf_sdmx, imf_datamapper, wdi, fred:
                     fetch(http) -> payload, parse(payload) -> series (pure)
  registry.py        every stored series: units, bounds, max age, revision tolerance, licence
  fetch.py           sanity checks, revision guard, cross-source checks, atomic store writes
  transform.py       FX consensus, weekday mean, CPI splice, policy step, YTD -> monthly,
                     unit values, export-price index, broad-dollar splice
  models.py          nw_lags, dl_fit, lincom, cumulative; the frozen specifications
  summarize.py       estimates -> JSON records; the takeaway templates
  build.py           store -> web/data/*.json and web/public/csv/
  validate.py        the schema and invariants of web/data
  probe.py           one request per endpoint: status, bytes, latency
data/                the committed store: <series_id>.csv (date,value) and status.json
data/static/         frozen seeds (Comtrade 1996-2007, FRED TWEXBMTH) and their provenance
tests/               153 tests; fixtures/store_2026-09/ is the reference vintage
web/                 the Next.js site (see web/README.md)
ci/constraints.txt   numpy, pandas, scipy and openpyxl minor versions for the scheduled jobs
.github/workflows/   ci (tests), web (site build), data (scheduled refresh), probe (by hand)
```

## Data credits and license

Exchange rates, policy rate and reported inflation: Bank of Mongolia. Consumer prices,
exchange rates and exports: Source: Mongolian Statistical Service (National Statistics Office
of Mongolia). Commodity prices: World Bank Commodity Price Data (The Pink Sheet), CC BY 4.0.
GDP, FDI and current account: World Bank World Development Indicators, CC BY 4.0. Exchange
rates, CPI, commodity prices and the World Economic Outlook: International Monetary Fund.
Broad dollar and CNY/USD: Board of Governors of the Federal Reserve System, via FRED. Exports
1996–2007: UN Comtrade. The data keep their publishers' terms.

Code: MIT. © 2026 Zorigtbaatar Khasbaatar.
