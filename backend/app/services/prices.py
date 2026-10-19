"""Crop prices for profit estimates (F8, F9).

1. Agmarknet mandi prices from data.gov.in (free key: DATA_GOV_API_KEY).
   `fetch_agmarknet` pulls the current daily price table; run
   `python -m scripts.fetch_prices` daily (or whenever online) so a price
   history builds up in mandi_prices. Profit uses the median modal price of
   the last 365 days in the field's district, else state.
2. Fallback: kharif Minimum Support Price 2026-27 (CCEA, 13 May 2026), so a
   price is always available offline. Chilli has no MSP; sugarcane uses FRP.
"""
from datetime import date, datetime, timedelta

import httpx

AGMARKNET_URL = "https://api.data.gov.in/resource/{resource}"
# "Current Daily Price of Various Commodities from Various Markets (Mandi)"
AGMARKNET_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"

# Rs per quintal. Update each year when the Cabinet announces new MSPs.
MSP_FALLBACK = {
    "paddy": (2441, "MSP 2026-27, paddy (common)"),
    "maize": (2410, "MSP 2026-27, maize"),
    "cotton": (8267, "MSP 2026-27, cotton (medium staple)"),
    "pulses": (8200, "MSP 2026-27, urad (black gram)"),
    "sugarcane": (355, "FRP 2025-26, sugarcane"),
}

# Kshetra crop -> substrings of Agmarknet commodity names
COMMODITY_MATCH = {
    "paddy": ["paddy"],
    "maize": ["maize"],
    "cotton": ["cotton"],
    "pulses": ["black gram", "green gram", "urd", "moong"],
    "chilli": ["chilli"],
    "sugarcane": ["sugarcane"],
}


def crop_for_commodity(commodity: str) -> str | None:
    name = commodity.lower()
    for crop, keys in COMMODITY_MATCH.items():
        if any(k in name for k in keys):
            return crop
    return None


def fetch_agmarknet(client: httpx.Client, api_key: str, state: str | None = None, limit: int = 1000) -> list[dict]:
    params = {"api-key": api_key, "format": "json", "limit": limit}
    if state:
        params["filters[state]"] = state
    resp = client.get(AGMARKNET_URL.format(resource=AGMARKNET_RESOURCE), params=params, timeout=60)
    resp.raise_for_status()
    return parse_agmarknet(resp.json())


def parse_agmarknet(payload: dict) -> list[dict]:
    rows = []
    for r in payload.get("records", []):
        try:
            day = datetime.strptime(r["arrival_date"], "%d/%m/%Y").date()  # noqa: DTZ007 - a calendar date
        except (KeyError, ValueError):
            continue
        rows.append({
            "arrival_date": day,
            "state": r.get("state", "").strip(),
            "district": r.get("district", "").strip(),
            "market": r.get("market", "").strip(),
            "commodity": r.get("commodity", "").strip(),
            "variety": (r.get("variety") or "").strip(),
            "min_price": _num(r.get("min_price")),
            "max_price": _num(r.get("max_price")),
            "modal_price": _num(r.get("modal_price")),
        })
    return rows


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def price_per_quintal(conn, crop: str, state: str | None, district: str | None,
                      today: date | None = None) -> dict:
    """{'rs_per_qtl', 'source'}; rs_per_qtl is None when no price is known."""
    since = (today or date.today()) - timedelta(days=365)  # noqa: DTZ011 - local calendar day
    keys = COMMODITY_MATCH.get(crop, [crop])
    pattern = "(" + "|".join(keys) + ")"
    for scope, value in (("district", district), ("state", state)):
        if not value:
            continue
        row = conn.execute(
            f"""SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY modal_price) AS p, count(*) AS n
                FROM mandi_prices WHERE lower({scope}) = lower(%s) AND commodity ~* %s
                  AND arrival_date >= %s AND modal_price > 0""",
            (value, pattern, since),
        ).fetchone()
        if row and row["n"]:
            return {"rs_per_qtl": round(float(row["p"]), 0),
                    "source": f"Agmarknet median of {row['n']} {scope} prices, last 12 months"}
    if crop in MSP_FALLBACK:
        price, label = MSP_FALLBACK[crop]
        return {"rs_per_qtl": float(price), "source": label}
    return {"rs_per_qtl": None, "source": "no price data (load Agmarknet prices)"}
