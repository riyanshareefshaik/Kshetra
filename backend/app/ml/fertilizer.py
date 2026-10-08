"""Fertilizer calculator (feature 5): bags of urea, DAP and MOP for this field.

1. Start from the recommended dose (N-P2O5-K2O kg/ha) for the crop and season
   (database/seeds/crop_varieties.csv, package-of-practices values).
2. Adjust each nutrient by the soil test rating, as on India's Soil Health Card:
   low -> x1.25, medium -> x1.0, high -> x0.75. Ratings (available nutrient, kg/ha):
   N <280 low, 280-560 medium, >560 high; P <10, 10-25, >25; K <120, 120-280, >280.
   Without a soil test the medium (standard) dose is used.
3. Convert to products: DAP (18-46-0) covers P2O5 and some N, urea (46% N) the rest of N,
   MOP (60% K2O) the potash. Split timings are standard for each crop.
"""
import math

RATING = {"n": (280, 560), "p": (10, 25), "k": (120, 280)}
FACTOR = {"low": 1.25, "medium": 1.0, "high": 0.75}
PRODUCTS = {
    # name: (nutrient share, bag kg, Rs per bag, price note)
    "urea": (0.46, 45, 266.50, "subsidised MRP, 45 kg bag"),
    "dap": (0.46, 50, 1350.0, "MRP Rs 1,350 per 50 kg bag (2026)"),
    "mop": (0.60, 50, 1610.0, "approximate; check your dealer"),
}
DAP_N = 0.18
ZN_LOW_PPM = 0.6

SPLITS = {
    "paddy": ["N: 1/3 at transplanting, 1/3 at tillering (~25 days), 1/3 at panicle initiation (~50 days)",
              "P: all at transplanting", "K: half at transplanting, half at panicle initiation"],
    "maize": ["N: 1/3 at sowing, 1/3 at knee-high (~30 days), 1/3 at tasseling (~50 days)",
              "P and K: all at sowing"],
    "cotton": ["N: in 3 equal splits at 30, 60 and 90 days", "P: all at sowing", "K: half at sowing, half at 60 days"],
    "pulses": ["Apply all N and P at sowing (pulses fix most of their own nitrogen)"],
    "chilli": ["N and K: in 4 splits (transplanting, 30, 60, 90 days)", "P: all at transplanting"],
    "sugarcane": ["N: in 3 splits at 30, 60 and 90 days", "P: all at planting", "K: half at planting, half at 90 days"],
}


def rate(nutrient: str, value: float | None) -> str | None:
    if value is None:
        return None
    low, high = RATING[nutrient]
    return "low" if value < low else "medium" if value <= high else "high"


def calculate(crop: str, rdf: tuple[float, float, float], soil: dict | None, area_ha: float) -> dict:
    """rdf: recommended (N, P2O5, K2O) kg/ha. soil: latest soil test (n_kg_ha, p_kg_ha, k_kg_ha, ph, zn_ppm)."""
    soil = soil or {}
    ratings = {k: rate(k, soil.get(f"{k}_kg_ha")) for k in ("n", "p", "k")}
    n, p, k = (base * FACTOR[ratings[key] or "medium"] for base, key in zip(rdf, ("n", "p", "k")))
    dose = {"n_kg_ha": round(n), "p2o5_kg_ha": round(p), "k2o_kg_ha": round(k)}

    dap = p / PRODUCTS["dap"][0]
    urea = max(n - dap * DAP_N, 0) / PRODUCTS["urea"][0]
    mop = k / PRODUCTS["mop"][0]
    items = []
    total = 0.0
    for name, kg_ha in (("urea", urea), ("dap", dap), ("mop", mop)):
        if kg_ha <= 0:
            continue
        _share, bag, price, note = PRODUCTS[name]
        kg = kg_ha * area_ha
        bags = math.ceil(kg / bag * 2) / 2              # round up to half bags
        cost = bags * price
        total += cost
        items.append({"product": name.upper(), "kg_per_ha": round(kg_ha), "kg_for_field": round(kg),
                      "bags": bags, "bag_kg": bag, "cost_rs": round(cost), "price_note": note})

    notes = []
    if not soil:
        notes.append("No soil test yet: this is the standard dose. A free Soil Health Card test makes it fit your soil.")
    zn = soil.get("zn_ppm")
    if zn is not None and zn < ZN_LOW_PPM:
        notes.append(f"Zinc is low ({zn} ppm): apply 25 kg zinc sulphate per hectare at sowing/transplanting.")
    ph = soil.get("ph")
    if ph is not None and ph > 8.5:
        notes.append(f"Soil is alkaline (pH {ph}): apply gypsum as advised by your soil lab before sowing.")
    elif ph is not None and ph < 5.5:
        notes.append(f"Soil is acidic (pH {ph}): apply agricultural lime as advised by your soil lab.")
    return {"crop": crop, "area_ha": round(area_ha, 3), "standard_dose": dict(zip(("n_kg_ha", "p2o5_kg_ha", "k2o_kg_ha"), rdf)),
            "ratings": ratings, "dose": dose, "products": items, "total_cost_rs": round(total),
            "schedule": SPLITS.get(crop, []), "notes": notes,
            "disclaimer": "Standard recommendations adjusted by soil test; confirm with your agriculture officer."}
