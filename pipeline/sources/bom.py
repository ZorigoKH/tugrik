"""Bank of Mongolia: official exchange rates, the policy rate and reported inflation.

The endpoints are the JSON feeds behind mongolbank.mn's own charts: undocumented, POST with
no body, no key. Numbers arrive as strings with thousands separators (``"3,594.47"``) and
``"-"`` where there is no rate. The daily feed carries the whole history since 2001 (about
4.8 MB) and includes weekends.

The BoM states no licence for these data, so none of them is offered for download on the
site (``redistribute`` is false in the registry).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from . import series

BASE = "https://www.mongolbank.mn/en"
DAILY = f"{BASE}/currency-rate-movement/data"
MONTHLY = f"{BASE}/currency-rate-movement/data/monthly"
POLICY = f"{BASE}/policy-interest-rate/data"
INFLATION = f"{BASE}/inflation/data"


def fetch(http, today: date | None = None) -> dict:
    """The four feeds, decoded from JSON."""
    today = today or date.today()
    return {
        "daily": http.post(DAILY).json(),
        "monthly": http.post(MONTHLY).json(),
        "policy": http.post(
            POLICY, params={"startDate": "1990-01-01", "endDate": today.isoformat()}
        ).json(),
        "inflation": http.post(
            INFLATION, params={"startDate": "1990-01", "endDate": today.strftime("%Y-%m")}
        ).json(),
    }


def number(text) -> float | None:
    """``"3,594.47"`` -> 3594.47; ``"-"``, ``""`` and ``None`` -> None."""
    if text is None:
        return None
    text = str(text).replace(",", "").strip()
    if text in ("", "-"):
        return None
    return float(text)


def _rows(payload: dict, part: str) -> list[dict]:
    body = payload[part]
    if not isinstance(body, dict) or body.get("success") is not True:
        raise ValueError(f"BoM {part}: the response does not say success")
    rows = body.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"BoM {part}: no data rows")
    return rows


def parse(payload: dict) -> dict[str, pd.Series]:
    daily = _rows(payload, "daily")
    monthly = _rows(payload, "monthly")
    policy = _rows(payload, "policy")
    inflation = _rows(payload, "inflation")
    return {
        "bom_usdmnt_daily": series((r["RATE_DATE"], number(r["USD"])) for r in daily),
        "bom_usdmnt_monthly_avg": series((r["RATE_DATE"], number(r["USD"])) for r in monthly),
        "bom_policy_rate_decisions": series(
            (r["EFFECTIVE_FROM"], number(r["POLICY_RATE"])) for r in policy
        ),
        "bom_cpi_yoy": series((r["STAT_DATE"], number(r["STATE_YEARLY"])) for r in inflation),
    }
