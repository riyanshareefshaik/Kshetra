"""Field boundary from a dropped pin (F1).

Earth Engine (free, non-commercial): stack four seasonal NDVI medians from the
last year of Sentinel-2 plus red/NIR medians, segment them with SNIC
superpixels, and take the segment under the pin. Neighbouring fields usually
differ in crop timing, so the seasonal stack separates them better than one
image does. The result is a proposal: the farmer confirms or redraws it.

If Earth Engine is unavailable or the segment is implausible, a 90 m square
around the pin is returned instead (boundary_source 'pin_buffer').
"""
import math
from datetime import date, timedelta

from shapely.geometry import mapping, shape

from app.services.earth_engine import CLEAR_THRESHOLD, CLOUD_SCORE_COLLECTION, init_ee

MIN_HA, MAX_HA = 0.05, 25.0
SQUARE_HALF_M = 45.0


def pin_square(lat: float, lon: float, half_m: float = SQUARE_HALF_M) -> dict:
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
            [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
    return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]}


def fetch_segment(lat: float, lon: float, today: date | None = None) -> dict | None:
    """GeoJSON polygon of the SNIC segment under the pin (raw EE output)."""
    ee = init_ee()
    end = today or date.today()  # noqa: DTZ011 - local calendar day
    start = end - timedelta(days=365)
    pt = ee.Geometry.Point([lon, lat])
    region = pt.buffer(400).bounds()
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
          .filterDate(start.isoformat(), end.isoformat())
          .linkCollection(ee.ImageCollection(CLOUD_SCORE_COLLECTION), ["cs_cdf"])
          .map(lambda img: img.updateMask(img.select("cs_cdf").gte(CLEAR_THRESHOLD))))
    ndvi = s2.map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("ndvi"))
    quarters = []
    for q in range(4):
        q0 = start + timedelta(days=91 * q)
        quarters.append(ndvi.filterDate(q0.isoformat(), (q0 + timedelta(days=91)).isoformat())
                        .median().rename(f"ndvi_q{q}"))
    stack = (ee.Image.cat(quarters + [s2.select(["B4", "B8"]).median().divide(10000)])
             .unmask(0).clip(region))
    snic = ee.Algorithms.Image.Segmentation.SNIC(
        image=stack, size=6, compactness=0.5, connectivity=8, neighborhoodSize=64)
    clusters = snic.select("clusters")
    cid = clusters.reduceRegion(ee.Reducer.first(), pt, 10).get("clusters")
    vectors = (clusters.eq(ee.Number(cid)).selfMask()
               .reduceToVectors(geometry=region, scale=10, geometryType="polygon", maxPixels=1e8))
    feat = vectors.filterBounds(pt).first()
    geom = ee.Feature(feat).geometry().simplify(5)
    return geom.getInfo()


def plausible(geometry: dict | None) -> bool:
    if not geometry or geometry.get("type") != "Polygon":
        return False
    poly = shape(geometry)
    lat = poly.centroid.y
    # Equirectangular area estimate; precise enough for a sanity check.
    m2 = poly.area * (111_320 ** 2) * math.cos(math.radians(lat))
    return MIN_HA <= m2 / 10_000 <= MAX_HA


def auto_boundary(lat: float, lon: float, fetch=fetch_segment) -> dict:
    try:
        geom = fetch(lat, lon)
        if plausible(geom):
            return {"geometry": mapping(shape(geom)), "boundary_source": "auto_ndvi",
                    "note": "Proposed from Sentinel-2 segmentation; check it matches your field."}
        note = "Satellite segment was not a plausible field; using a square around the pin."
    except Exception as exc:  # noqa: BLE001 - any EE problem falls back to the square
        note = f"Satellite boundary unavailable ({type(exc).__name__}); using a square around the pin."
    return {"geometry": pin_square(lat, lon), "boundary_source": "pin_buffer", "note": note}
