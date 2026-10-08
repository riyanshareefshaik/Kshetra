"""When and where to sell (feature 6) from Agmarknet prices stored in mandi_prices.

* Trend: weekly median modal price for the crop in the state over the last year.
* Seasonality: average price by calendar month over all stored years (needs a year of history).
* Mandis: latest modal price per market (last 30 days), with distance from the field.
  Markets are located with OpenStreetMap Nominatim (free; 1 request/second; cached forever).
"""
import math
import time
from datetime import date, timedelta

import httpx

from app.services.cache import cached
from app.services.prices import COMMODITY_MATCH, price_per_quintal

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MAX_GEOCODE = 12
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _pattern(crop: str) -> str:
    return "(" + "|".join(COMMODITY_MATCH.get(crop, [crop])) + ")"


def geocode(market: str, district: str, state: str) -> dict | None:
    with httpx.Client(headers={"User-Agent": "Kshetra/1.0 (farm advisory; non-commercial)"}) as c:
        r = c.get(NOMINATIM_URL, timeout=20, params={
            "q": f"{market}, {district}, {state}, India", "format": "json", "limit": 1, "countrycodes": "in"})
        r.raise_for_status()
        hits = r.json()
    time.sleep(1.0)                                       # Nominatim usage policy: max 1 request per second
    return {"lat": float(hits[0]["lat"]), "lon": float(hits[0]["lon"])} if hits else None


def km(a_lat, a_lon, b_lat, b_lon) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def market_view(conn, crop: str, field: dict, today: date | None = None, locate=None) -> dict:
    today = today or date.today()  # noqa: DTZ011 - local calendar day
    locate = locate or geocode
    state = field.get("state")
    pat = _pattern(crop)
    trend = conn.execute(
        """SELECT date_trunc('week', arrival_date)::date AS week,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY modal_price) AS price, count(*) AS n
           FROM mandi_prices WHERE commodity ~* %s AND (%s::text IS NULL OR lower(state) = lower(%s))
             AND arrival_date >= %s AND modal_price > 0
           GROUP BY 1 ORDER BY 1""",
        (pat, state, state, today - timedelta(days=365)),
    ).fetchall()
    by_month = conn.execute(
        """SELECT extract(month FROM arrival_date)::int AS m, avg(modal_price) AS price,
                  count(DISTINCT extract(year FROM arrival_date)) AS years
           FROM mandi_prices WHERE commodity ~* %s AND (%s::text IS NULL OR lower(state) = lower(%s))
             AND modal_price > 0 GROUP BY 1 ORDER BY 1""",
        (pat, state, state),
    ).fetchall()
    markets = conn.execute(
        """SELECT DISTINCT ON (market, district) market, district, state, arrival_date, modal_price, variety
           FROM mandi_prices WHERE commodity ~* %s AND (%s::text IS NULL OR lower(state) = lower(%s))
             AND arrival_date >= %s AND modal_price > 0
           ORDER BY market, district, arrival_date DESC""",
        (pat, state, state, today - timedelta(days=30)),
    ).fetchall()

    markets.sort(key=lambda m: m["modal_price"], reverse=True)
    for i, m in enumerate(markets):
        m["arrival_date"] = m["arrival_date"].isoformat()
        m["distance_km"] = None
        if i < MAX_GEOCODE and field.get("lat") is not None:
            try:
                loc = cached(conn, "nominatim", {"q": [m["market"], m["district"], m["state"]]},
                             lambda m=m: locate(m["market"], m["district"], m["state"]))
            except httpx.HTTPError:
                loc = None
            if loc:
                m["distance_km"] = round(km(field["lat"], field["lon"], loc["lat"], loc["lon"]))

    out = {"crop": crop, "state": state,
           "trend": [{"week": r["week"].isoformat(), "price": round(float(r["price"])), "n": r["n"]} for r in trend],
           "markets": markets[:20],
           "reference": price_per_quintal(conn, crop, state, field.get("district"), today),
           "advice": []}
    if len(trend) >= 8:
        last = sum(r["price"] for r in trend[-4:]) / 4
        prev = sum(r["price"] for r in trend[-8:-4]) / 4
        change = 100 * (last - prev) / prev if prev else 0
        word = "rising" if change > 3 else "falling" if change < -3 else "steady"
        out["advice"].append({"code": "trend", "word": word, "change_pct": round(change),
                              "text": f"Prices are {word}: {change:+.0f}% over the last 4 weeks."})
    if len(by_month) >= 10 and min(r["years"] for r in by_month) >= 1:
        best = max(by_month, key=lambda r: r["price"])
        now = next((r for r in by_month if r["m"] == today.month), None)
        out["seasonality"] = [{"month": MONTHS[r["m"] - 1], "price": round(float(r["price"]))} for r in by_month]
        if now and best["m"] != today.month and best["price"] > now["price"] * 1.05:
            gain = 100 * (best["price"] - now["price"]) / now["price"]
            out["advice"].append({"code": "seasonal", "best_month": best["m"], "this_month": today.month,
                                  "gain_pct": round(gain),
                                  "text": f"Prices are usually highest in {MONTHS[best['m'] - 1]} (about {gain:.0f}% above "
                                          f"{MONTHS[today.month - 1]}). If you can store the crop safely, waiting may pay; "
                                          "past patterns are not a guarantee."})
    near = [m for m in markets if m["distance_km"] is not None]
    if near:
        # Best price after a rough transport cost of Rs 2 per quintal per km.
        best = max(near, key=lambda m: m["modal_price"] - 2 * m["distance_km"])
        out["advice"].append({"code": "best_market", "market": best["market"], "km": best["distance_km"],
                              "price": round(best["modal_price"]), "date": best["arrival_date"],
                              "text": f"Best nearby option: {best['market']} ({best['distance_km']} km), "
                                      f"Rs {best['modal_price']:.0f}/quintal on {best['arrival_date']}."})
    if not markets:
        out["advice"].append({"code": "no_data", "text": "No recent mandi prices stored for this crop in your state yet."})
    return out
