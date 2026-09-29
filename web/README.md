# tugrik: the website

A static Next.js site about Mongolia's economy: how the price of copper moves the tugrik, why
coal income follows the Chinese border, how much of a weaker tugrik reaches consumer prices,
and how growth follows export prices a year later. Every number and sentence on it comes from
the JSON in `web/data`, which the Python pipeline in `pipeline/` writes.

## How data flows

```
BoM, NSO, Pink Sheet, IMF, WDI, FRED
   │  python -m pipeline.fetch --store data          (network; one source at a time)
   ▼
data/*.csv + data/status.json                         (the committed store)
   │  python -m pipeline.build --store data --out web/data --csv web/public/csv
   ▼                                                  (offline, deterministic)
web/data/*.json + web/public/csv/*.csv
   │  npm run build                                   (lib/data.ts checks every file)
   ▼
web/out/                                              (static HTML)
```

1. **`python -m pipeline.build`** turns the store into `meta.json`, `overview.json`,
   `copper.json`, `coal.json`, `prices.json`, `growth.json` and `sources.json`, plus a CSV per
   redistributable series. The takeaway sentences are generated there, from the estimates.
2. **`python -m pipeline.validate web/data`** checks the schema and the invariants (contiguous
   months, lo ≤ est ≤ hi, 13 horizons, the coal identity, weights summing to 1, and that each
   sentence still matches its template).
3. **`npm run build`** (in `web/`) reads those files at build time in `lib/data.ts`, whose
   hand-written validators (`assertMeta`, `assertCopper`, …) throw on a missing or ill-typed
   field, so bad data fails the build instead of producing a broken page.
4. Next writes a fully static site to **`web/out/`**: `index.html`, `copper.html`,
   `coal.html`, `prices.html`, `growth.html`, `data.html`, `method.html` and `csv/`.

## Develop

Node 20.9 or later.

```bash
cd web
npm ci
npm run dev         # http://localhost:3000
npm run typecheck   # next typegen && tsc --noEmit
npm run build       # static export to out/
```

To preview the export, serve `out/` with any static file server that maps `/copper` to
`copper.html` (for example `npx serve out`).

## Layout

```
app/
  layout.tsx          header, footer (data-through date), fonts, metadata
  page.tsx            /: the latest numbers (tiles with sparklines) and the four findings
  copper/ coal/ prices/ growth/   one analysis page each
  data/page.tsx       sources, endpoints, freshness, licences, CSV downloads, schedule
  method/page.tsx     data fixes, the frozen regressions, caveats, reference numbers
  globals.css         design tokens (light and dark) and chart roles
components/
  Section.tsx         page header, sections, takeaways, caveats
  Table.tsx           numeric tables (each chart's numbers, folded under it)
  StatusBadge.tsx     ok / stale / fallback
  charts/             hand-written SVG charts, no chart library:
                      ResponseChart, ActualFitted, CoefStrip, DecompBars, Panels,
                      YearScatter, GrowthBars, ShareArea, Sparkline, StatTile
lib/
  types.ts            the JSON schema as TypeScript types
  data.ts             build-time loading and validation
  format.ts           percent, pp, MNT, $/t, month and tick formatting (typographic minus)
  scale.ts            scales and ticks for the charts
  site.ts             title, repository link, page list
data/                 written by pipeline.build; do not edit by hand
public/csv/           written by pipeline.build; do not edit by hand
```

Charts are client components only so they can measure their width (text stays at its real
size on a phone) and offer hover, tap and keyboard readouts; the static HTML already contains
every chart. Each has `role="img"`, an `aria-label` summary and a table of its numbers.

Chart colours follow one rule: the accent blue is Mongolia's own series or the headline
estimate, gray is a comparison. There is no red or green.
