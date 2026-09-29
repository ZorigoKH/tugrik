// Site-wide constants.

export const REPO_URL = "https://github.com/ZorigoKH/tugrik";
export const AUTHOR = "Zori Khasbaatar";
export const TITLE = "tugrik";
export const SUBTITLE = "tögrög, copper and coal: Mongolia's economy in four charts.";

/** The four analysis pages, in the order of the overview cards. */
export const PAGE_LINKS = [
  { id: "copper", href: "/copper", nav: "copper" },
  { id: "coal", href: "/coal", nav: "coal" },
  { id: "prices", href: "/prices", nav: "prices" },
  { id: "growth", href: "/growth", nav: "growth" },
] as const;

/** Short names for the `source` ids of the overview tiles and the data page. */
export const SOURCE_NAMES: Record<string, string> = {
  bom: "Bank of Mongolia",
  nso: "NSO Mongolia",
  pinksheet: "World Bank Pink Sheet",
  imf_sdmx: "IMF",
  imf_datamapper: "IMF WEO",
  wdi: "World Bank WDI",
  fred: "FRED",
  comtrade: "UN Comtrade",
  derived: "consensus of BoM, NSO and IMF",
};

/** The page each overview tile links to. */
export const TILE_PAGES: Record<string, string> = {
  fx: "/copper",
  cpi: "/prices",
  policy_rate: "/prices",
  copper: "/copper",
  coal: "/coal",
  gdp: "/growth",
};
