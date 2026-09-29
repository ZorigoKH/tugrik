# The 2026-09 reference vintage

The model inputs of the frozen regressions, as the build derived them from the store fetched
on 2026-09-28 (data through August 2026). `tests/test_reference.py` runs every frozen
specification on these files and checks that they reproduce the trial regressions of
2026-09-27 (`copper Σ0..12 = −0.226`, `B3 h12 = 0.130`, `C2 mxpi(t−1) = 0.085`, coal in
2021 = 16.1 Mt, and the rest listed there).

They were written by

    python -m pipeline.build --store data --out <tmp> --csv <tmp> --save-inputs tests/fixtures/store_2026-09

and are never updated: new data changes the site's numbers, not these.

Each file is `date,value`, as in the store. Only derived and redistributable series are here:

| file | what | from |
|---|---|---|
| `derived_usdmnt_monthly_avg.csv` | MNT per US dollar, monthly average, by the consensus rule | BoM, NSO and IMF averages, checked against the BoM daily rate |
| `derived_cpi_mom.csv` | CPI m/m, newest NSO base first | NSO |
| `derived_usd_broad_index.csv` | broad dollar index, TWEXBMTH ratio-spliced to TWEXBGSMTH | FRED |
| `derived_cnyusd_monthly_avg.csv` | CNY per US dollar (EXCHUS) | FRED |
| `derived_mxpi_weight_*.csv` | export shares of the six goods (1996–2007 Comtrade, 2008–2010 interpolated, NSO from 2011) | UN Comtrade, NSO |
| `pinksheet_*.csv` | copper, Australian coal, gold, iron ore, Brent, zinc | World Bank Pink Sheet (CC BY 4.0) |
| `nso_export_coal_kusd.csv`, `nso_export_coal_kt.csv` | coal exports, monthly value and tonnes | NSO |
| `wdi_gdp_growth.csv` | real GDP growth | World Bank WDI (CC BY 4.0) |

No raw Bank of Mongolia data is included: the BoM states no licence.
