"""Small synthetic payloads in the shapes the publishers really send (no real data).

Each builder returns what the source's ``fetch`` would return, or the raw HTTP body. The
``world`` function assembles a whole consistent set - every source agreeing with the others,
so the cross-source checks pass - keyed by URL, for a fake HTTP transport.
"""

from __future__ import annotations

import io
import json
from datetime import date, timedelta

import openpyxl
import requests

from pipeline.sources import bom, fred, imf_datamapper, imf_sdmx, nso, pinksheet, wdi

MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)][:32]  # ..2026-08
YEARS = [str(y) for y in range(2010, 2026)]


# -- Bank of Mongolia ----------------------------------------------------------------------
def money(value: float) -> str:
    """How the BoM writes a number: ``"3,594.47"``."""
    return f"{value:,.2f}"


def bom_payload(rate: float = 3500.0, months: list[str] = MONTHS) -> dict:
    first = date.fromisoformat(months[0] + "-01")
    last = date.fromisoformat(months[-1] + "-28")
    while (last + timedelta(days=1)).month == last.month:
        last += timedelta(days=1)
    days = [first + timedelta(days=k) for k in range((last - first).days + 1)]
    return {
        "daily": {
            "success": True,
            "data": [{"RATE_DATE": d.isoformat(), "USD": money(rate), "EUR": "-"} for d in days][
                ::-1
            ],
        },
        "monthly": {
            "success": True,
            "data": [{"RATE_DATE": m, "USD": money(rate), "KZT": "0.00"} for m in months][::-1],
        },
        "policy": {
            "success": True,
            "data": [
                {"EFFECTIVE_FROM": "2024-01-10", "POLICY_RATE": "13.00", "REPO": "15.00"},
                {"EFFECTIVE_FROM": "2025-03-14", "POLICY_RATE": "12.00", "REPO": "14.00"},
            ],
        },
        "inflation": {
            "success": True,
            "data": [{"STAT_DATE": m, "STATE_YEARLY": "5.0", "UB_YEARLY": None} for m in months],
        },
    }


# -- NSO json-stat2 ------------------------------------------------------------------------
def jsonstat(dims: list[tuple[str, str, list[tuple[str, str]]]], values: list) -> dict:
    """A json-stat2 dataset. ``dims`` is ``[(id, label, [(code, label), ...]), ...]``."""
    return {
        "version": "2.0",
        "class": "dataset",
        "label": "synthetic",
        "source": "National Statistics Office of Mongolia",
        "updated": "2026-09-09T08:00:00Z",
        "id": [d[0] for d in dims],
        "size": [len(d[2]) for d in dims],
        "dimension": {
            dim: {
                "label": text,
                "category": {
                    "index": {code: i for i, (code, _) in enumerate(cats)},
                    "label": dict(cats),
                },
            }
            for dim, text, cats in dims
        },
        "value": values,
    }


def month_dim(months: list[str]) -> tuple[str, str, list[tuple[str, str]]]:
    """NSO lists months newest first, coded "0", "1", ..."""
    return (nso.MONTH, "Month", [(str(i), m) for i, m in enumerate(reversed(months))])


BASES = {"0": "2015=100", "1": "2020=100", "2": "2023=100"}


def nso_cpi(value: float, months: list[str] = MONTHS, bases: dict[str, str] = BASES) -> dict:
    """Overall index for each base; base 2015 stops in 2024-12, base 2023 starts in 2025-01."""
    newest_first = list(reversed(months))
    values = []
    for label in bases.values():
        for m in newest_first:
            present = not (label == "2015=100" and m > "2024-12") and not (
                label == "2023=100" and m < "2025-01"
            )
            values.append(value if present else None)
    return jsonstat(
        [
            (nso.BASE_YEAR, "Reference year", list(bases.items())),
            (nso.GROUP, "Group", [("0", "Overall index")]),
            month_dim(months),
        ],
        values,
    )


def nso_fx(avg: float, eop: float, months: list[str] = MONTHS) -> dict:
    n = len(months)
    return jsonstat(
        [(nso.CURRENCY, "Indicators", [("2", " USD"), ("10", "  USD")]), month_dim(months)],
        [avg] * n + [eop] * n,
    )


def nso_exports(value: float, months: list[str] = MONTHS) -> dict:
    return jsonstat(
        [(nso.TRADE_INDICATOR, "Main indicators", [("11", " Exports")]), month_dim(months)],
        [value] * len(months),
    )


def ytd(flows: dict[str, float]) -> dict[str, float]:
    """Year-to-date totals from monthly flows."""
    totals, running, year = {}, 0.0, None
    for month in sorted(flows):
        if month[:4] != year:
            year, running = month[:4], 0.0
        running += flows[month]
        totals[month] = running
    return totals


def nso_commodities(volume: float, value: float, months: list[str] = MONTHS) -> dict:
    goods = [(code, " " + name) for code, (_, _, name) in nso.GOODS.items()]
    totals = {"0": ytd(dict.fromkeys(months, volume)), "1": ytd(dict.fromkeys(months, value))}
    values = [totals[m][month] for m in ("0", "1") for _ in goods for month in reversed(months)]
    return jsonstat(
        [
            (nso.MEASURE, "Statistical indicator", [("0", "Volume"), ("1", " Value(USD.thous)")]),
            (nso.COMMODITY, "Main commodities", goods),
            (nso.MONTH, "Month (cumulative)", month_dim(months)[2]),
        ],
        values,
    )


def nso_payload(rate: float = 3500.0, cpi_yoy: float = 5.0) -> dict:
    return {
        "cpi_mom": nso_cpi(0.5),
        "cpi_yoy": nso_cpi(cpi_yoy),
        "fx": nso_fx(rate, rate),
        "exports": nso_exports(1500.0),
        "commodities": nso_commodities(100.0, 5000.0),
    }


# -- World Bank Pink Sheet -----------------------------------------------------------------
PINK_COLUMNS = [
    ("Crude oil, average", "($/bbl)", 79.0),
    ("Crude oil, Brent", "($/bbl)", 80.0),
    ("Coal, Australian", "($/mt)", 120.0),
    ("Coal, South African **", "($/mt)", 95.0),
    ("Copper", "($/mt)", 9000.0),
    ("Gold", "($/troy oz)", 2000.0),
    ("Iron ore, cfr spot", "($/dmtu)", 100.0),
    ("Zinc", "($/mt)", 2500.0),
]
XLSX_URL = (
    "https://thedocs.worldbank.org/en/doc/0123456789abcdef0123456789abcdef-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)


def pinksheet_xlsx(
    months: list[str] = MONTHS,
    updated: str = "September 02, 2026",
    missing: int = 0,
    columns: list[tuple[str, str, float]] = PINK_COLUMNS,
) -> bytes:
    """The workbook: a "Mismatch Details" sheet first, then "Monthly Prices" with the title
    block, headers in row 5 (index 4), units in row 6 (index 5) and ``…`` for the first
    ``missing`` months of Australian coal."""
    book = openpyxl.Workbook()
    book.active.title = "Mismatch Details"
    book.active.append(["MISMATCH DETAILS"])
    sheet = book.create_sheet("Monthly Prices")
    sheet.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    sheet.append(["monthly prices in nominal US dollars, 1960 to present"])
    sheet.append(["(monthly series are available only in nominal US dollars)"])
    sheet.append([f"Updated on {updated}"])
    sheet.append([None, *(name for name, _, _ in columns)])
    sheet.append([None, *(unit for _, unit, _ in columns)])
    for i, month in enumerate(months):
        row = [
            "…" if name == "Coal, Australian" and i < missing else price
            for name, _, price in columns
        ]
        sheet.append([month.replace("-", "M"), *row])
    sheet.append(["Note: synthetic"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def commodity_page(url: str = XLSX_URL) -> str:
    return (
        '<html><body><a href="https://thedocs.worldbank.org/en/doc/x/CMO-Pink-Sheet.pdf">PDF</a>'
        f'<a class="btn" href="{url}">Monthly prices</a>'
        f'<a href="{url.replace("Monthly", "Annual")}">Annual prices</a></body></html>'
    )


# -- IMF SDMX CSV --------------------------------------------------------------------------
def sdmx_csv(columns: list[str], rows: list[dict]) -> str:
    """An SDMX-CSV answer: the given columns plus the metadata columns the IMF adds."""
    header = ["DATAFLOW", *columns, "TIME_PERIOD", "OBS_VALUE", "SCALE", "FULL_DESCRIPTION"]
    lines = [",".join(header)]
    for row in rows:
        cells = [
            "IMF.STA:X(1.0.0)",
            *(row[c] for c in columns),
            row["TIME_PERIOD"],
            str(row["OBS_VALUE"]),
            "0",
            '"A description, with a comma"',
        ]
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def sdmx_er(country: str, avg: float, eop: float, months: list[str] = MONTHS) -> str:
    columns = ["COUNTRY", "INDICATOR", "TYPE_OF_TRANSFORMATION", "FREQUENCY"]
    rows = []
    for kind, value in (("EOP_RT", eop), ("PA_RT", avg)):
        rows.append(
            {"COUNTRY": country, "INDICATOR": "XDC_USD", "TYPE_OF_TRANSFORMATION": kind,
             "FREQUENCY": "M", "TIME_PERIOD": "1900-M01", "OBS_VALUE": 1}
        )  # fmt: skip
        for m in months:
            rows.append(
                {"COUNTRY": country, "INDICATOR": "XDC_USD", "TYPE_OF_TRANSFORMATION": kind,
                 "FREQUENCY": "M", "TIME_PERIOD": m.replace("-", "-M"), "OBS_VALUE": value}
            )  # fmt: skip
    return sdmx_csv(columns, rows)


def sdmx_cpi(yoy: float, mom: float, months: list[str] = MONTHS) -> str:
    columns = ["COUNTRY", "INDEX_TYPE", "COICOP_1999", "TYPE_OF_TRANSFORMATION", "FREQUENCY"]
    rows = []
    for kind, value in (("IX", 130.0), ("YOY_PCH_PA_PT", yoy), ("POP_PCH_PA_PT", mom)):
        for m in months:
            rows.append(
                {"COUNTRY": "MNG", "INDEX_TYPE": "CPI", "COICOP_1999": "_T",
                 "TYPE_OF_TRANSFORMATION": kind, "FREQUENCY": "M",
                 "TIME_PERIOD": m.replace("-", "-M"), "OBS_VALUE": value}
            )  # fmt: skip
    return sdmx_csv(columns, rows)


def sdmx_pcps(prices: dict[str, float], months: list[str] = MONTHS) -> str:
    columns = ["COUNTRY", "INDICATOR", "DATA_TRANSFORMATION", "FREQUENCY"]
    rows = [
        {"COUNTRY": "G001", "INDICATOR": code, "DATA_TRANSFORMATION": "USD", "FREQUENCY": "M",
         "TIME_PERIOD": m.replace("-", "-M"), "OBS_VALUE": value}
        for code, value in prices.items()
        for m in months
    ]  # fmt: skip
    return sdmx_csv(columns, rows)


# -- IMF DataMapper, WDI, FRED -------------------------------------------------------------
def datamapper(code: str, mng: dict[str, float], chn: dict[str, float]) -> dict:
    """All countries, as the API answers even when asked for one."""
    return {
        "indicators": {
            code: {
                "label": code,
                "source": "World Economic Outlook (April 2026)",
                "unit": "Annual percent change",
                "dataset": "WEO",
                "last-modified": "2026-04-08 16:07:34",
            }
        },
        "values": {code: {"USA": {"2025": 2.0}, "MNG": mng, "CHN": chn}},
        "api": {"version": "2", "output-method": "json"},
    }


def wdi_answer(values: dict[str, float | None], pages: int = 1) -> list:
    rows = [
        {"indicator": {"id": "X", "value": "X"}, "countryiso3code": "MNG", "date": year,
         "value": value, "unit": "", "obs_status": "", "decimal": 1}
        for year, value in sorted(values.items(), reverse=True)
    ]  # fmt: skip
    return [{"page": 1, "pages": pages, "per_page": 100, "total": len(rows)}, rows]


def fred_csv(fred_id: str, values: dict[str, float | None]) -> str:
    lines = [f"observation_date,{fred_id}"]
    lines += [f"{m}-01,{'.' if v is None else v}" for m, v in values.items()]
    return "\n".join(lines) + "\n"


# -- the whole world -----------------------------------------------------------------------
def world(rate: float = 3500.0, growth: float = 5.0) -> dict[str, bytes]:
    """Every endpoint's body, keyed by URL (the BoM's without their query strings)."""
    each_year = {y: growth for y in [*YEARS, "2026", "2027"]}
    body = {
        bom.DAILY: bom_payload(rate)["daily"],
        bom.MONTHLY: bom_payload(rate)["monthly"],
        bom.POLICY: bom_payload(rate)["policy"],
        bom.INFLATION: bom_payload(rate)["inflation"],
        pinksheet.PAGE: commodity_page(),
        XLSX_URL: pinksheet_xlsx(),
        imf_sdmx.URLS["er_mng"]: sdmx_er("MNG", rate, rate),
        imf_sdmx.URLS["cpi_mng"]: sdmx_cpi(5.0, 0.5),
        imf_sdmx.URLS["pcps"]: sdmx_pcps({"PCOPP": 9000.0, "PGOLD": 2000.0, "PZINC": 2500.0}),
        imf_sdmx.URLS["er_chn"]: sdmx_er("CHN", 7.1, 7.1),
        **{
            f"{imf_datamapper.API}{code}/MNG": datamapper(code, each_year, each_year)
            for code in imf_datamapper.INDICATORS
        },
        **{
            wdi.API.format(country=country, code=code): wdi_answer(
                {**dict.fromkeys(YEARS, growth), "2009": None}
            )
            for country, code in wdi.SERIES.values()
        },
        fred.URL.format(id="TWEXBGSMTH"): fred_csv("TWEXBGSMTH", dict.fromkeys(MONTHS, 120.0)),
        fred.URL.format(id="EXCHUS"): fred_csv("EXCHUS", dict.fromkeys(MONTHS, 7.1)),
    }
    for key, table in nso.TABLES.items():
        body[nso.API + table] = nso_payload(rate)[key]
    return {
        url: content if isinstance(content, bytes) else as_bytes(content)
        for url, content in body.items()
    }


def as_bytes(content) -> bytes:
    if isinstance(content, str):
        return content.encode("utf-8")
    return json.dumps(content, ensure_ascii=False).encode("utf-8")


# -- a fake transport ----------------------------------------------------------------------
class FakeAdapter(requests.adapters.BaseAdapter):
    """Answers requests from ``route(request) -> (status, body)`` and remembers them."""

    def __init__(self, route) -> None:
        super().__init__()
        self.route = route
        self.sent: list[requests.PreparedRequest] = []

    def send(self, request, **kwargs):
        self.sent.append(request)
        status, body = self.route(request)
        response = requests.Response()
        response.status_code = status
        response._content = body
        response.url = request.url
        response.request = request
        response.encoding = "utf-8"
        return response

    def close(self) -> None:
        pass


def session(route) -> tuple[requests.Session, FakeAdapter]:
    s = requests.Session()
    adapter = FakeAdapter(route)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s, adapter


def serve(bodies: dict[str, bytes], status: dict[str, int] | None = None):
    """A route over ``world()``-style bodies; ``status`` overrides the code for some URLs."""
    status = status or {}

    def route(request):
        url = request.url
        key = url if url in bodies else url.split("?")[0]
        if key not in bodies:
            return 404, b"not found"
        return status.get(key, 200), bodies[key]

    return route
