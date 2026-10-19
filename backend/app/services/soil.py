"""Topsoil (0-30 cm) properties from ISRIC SoilGrids 2.0 (free, CC-BY 4.0, no key).

The REST API is in beta with a fair-use limit (~5 requests/minute), so each
field is queried once and cached.
"""
import httpx

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}   # thickness weights
# SoilGrids property -> (fields column, divisor to convert mapped units to column units)
PROPERTIES = {
    "clay": ("clay_pct", 10),            # g/kg -> %
    "sand": ("sand_pct", 10),
    "silt": ("silt_pct", 10),
    "soc": ("soc_g_per_kg", 10),         # dg/kg -> g/kg
    "phh2o": ("ph_h2o", 10),             # pH*10 -> pH
    "nitrogen": ("nitrogen_g_per_kg", 100),  # cg/kg -> g/kg
    "cec": ("cec_cmol_per_kg", 10),      # mmol(c)/kg -> cmol(c)/kg
    "bdod": ("bulk_density", 100),       # cg/cm3 -> g/cm3
}


def fetch_soilgrids(client: httpx.Client, lat: float, lon: float) -> dict:
    resp = client.get(
        SOILGRIDS_URL,
        params=[("lon", round(lon, 5)), ("lat", round(lat, 5))]
        + [("property", p) for p in PROPERTIES]
        + [("depth", d) for d in DEPTHS]
        + [("value", "mean")],
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def parse_soilgrids(payload: dict) -> dict:
    """Thickness-weighted 0-30 cm means in the units of the fields table, plus USDA texture."""
    out: dict = {}
    for layer in payload["properties"]["layers"]:
        name = layer["name"]
        if name not in PROPERTIES:
            continue
        column, divisor = PROPERTIES[name]
        total = weight = 0.0
        for depth in layer["depths"]:
            mean = depth["values"].get("mean")
            w = DEPTHS.get(depth["label"])
            if mean is not None and w:
                total += mean * w
                weight += w
        out[column] = round(total / weight / divisor, 2) if weight else None

    if all(out.get(k) is not None for k in ("clay_pct", "sand_pct", "silt_pct")):
        out["soil_texture"] = usda_texture(out["sand_pct"], out["silt_pct"], out["clay_pct"])
    else:
        out["soil_texture"] = None
    out["soil_source"] = "soilgrids_v2"
    return out


def usda_texture(sand: float, silt: float, clay: float) -> str:
    """USDA soil texture class from sand/silt/clay percentages."""
    total = sand + silt + clay
    if total <= 0:
        return "unknown"
    sand, silt, clay = (100 * x / total for x in (sand, silt, clay))
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy sand"
    if clay >= 40:
        if silt >= 40:
            return "silty clay"
        if sand > 45:
            return "sandy clay"
        return "clay"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 27:
        if sand <= 20:
            return "silty clay loam"
        if sand <= 45:
            return "clay loam"
        return "sandy clay loam"
    if clay >= 20 and sand > 45 and silt < 28:
        return "sandy clay loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if silt >= 50:
        return "silt loam"
    if clay >= 7 and sand <= 52 and silt >= 28:
        return "loam"
    return "sandy loam"
