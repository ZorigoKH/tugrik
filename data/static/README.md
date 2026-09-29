# Static seeds

Frozen inputs that the fetch stage never downloads. Each file is `date,value`, like the rest
of the store. They were retrieved on 2026-09-27 and are not expected to change: one covers
years that are closed, the other a discontinued series.

## Comtrade: Mongolia's exports of six goods, 1996–2007

`comtrade_mng_exports_{good}_musd.csv`, one row per year, in **million US dollars**.
Mongolia is the reporter (496), the world is the partner (0), and the flow is exports (X).
The customs code is C00, the mode of transport is 0 and the second partner is 0, which
together select the total.

| file | HS code | goods |
|---|---|---|
| `comtrade_mng_exports_coal_hs2701_musd.csv` | 2701 | coal |
| `comtrade_mng_exports_copper_conc_hs2603_musd.csv` | 2603 | copper ores and concentrates |
| `comtrade_mng_exports_gold_hs7108_musd.csv` | 7108 | gold, unwrought or semi-manufactured |
| `comtrade_mng_exports_iron_ore_hs2601_musd.csv` | 2601 | iron ores and concentrates |
| `comtrade_mng_exports_crude_oil_hs2709_musd.csv` | 2709 | crude petroleum oils |
| `comtrade_mng_exports_zinc_conc_hs2608_musd.csv` | 2608 | zinc ores and concentrates |

- **Source:** the UN Comtrade public preview API, one request per year:
  `https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=496&period={YYYY}&partnerCode=0,156&flowCode=X&cmdCode=TOTAL,2701,2603,7108,2601,2709,2608,2529,2613&customsCode=C00&motCode=0&partner2Code=0&includeDesc=true`.
  The value is `primaryValue` (US dollars) divided by 10⁶.
- **Missing years:** a year with no record for a good is absent from its file. The gaps are
  gold before 1998, coal in 1999, iron ore in 1996, 1998 and 1999, and zinc before 2002 and
  in 2003.
  Comtrade has no row for these years, so the trial regressions treated them as zero exports.
- **Use:** these are the weights of Mongolia's export-price index (mxpi) for 1996–2007. Each
  good's share of the six is taken in the previous year and renormalised. The weights are
  interpolated linearly over 2008–2010 and come from NSO for 2011 onwards.
- **Why a seed:** the public API allows about one request a second and refuses further calls
  (403) after about 150. It is not suitable for a scheduled job, and these years will not change.
- **Terms:** UN Comtrade terms of use. The site credits UN Comtrade.

## FRED: the old broad dollar index, TWEXBMTH

`fred_twexbmth.csv`, monthly from 1973-01 to 2019-12. This is the trade-weighted US dollar
index against a broad group of currencies, with January 1997 = 100.

- **Source:** `https://fred.stlouisfed.org/graph/fredgraph.csv?id=TWEXBMTH`, from the Board
  of Governors of the Federal Reserve System via FRED. The Fed discontinued the series in
  January 2020.
- **Use:** the build uses this series up to 2005-12. It rescales those months by the ratio
  TWEXBGSMTH / TWEXBMTH in 2006-01, so that they join the current broad index (TWEXBGSMTH,
  January 2006 = 100), which the fetch stage downloads. The file keeps the whole series,
  including 2006-01, so that the ratio can be computed.
- **Terms:** Federal Reserve Board data. Cite FRED.
