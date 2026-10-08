"""Sentinel-2 NDVI and Sentinel-1 SAR field averages from Google Earth Engine.

Uses the free non-commercial Earth Engine tier (Community tier: 150 EECU-hours
per month). One request per field per year per sensor returns only field-mean
numbers, which costs a few EECU-seconds, and every result is cached in api_cache.

Sentinel-2: COPERNICUS/S2_HARMONIZED (Level-1C, consistent back to 2017 over
India, where surface reflectance only starts in late 2018) with Google's
Cloud Score+ mask, which also catches cloud shadows.

Sentinel-1: COPERNICUS/S1_GRD, IW mode, VV+VH, already calibrated and
terrain-corrected to dB. Averaged in linear power, returned in dB.
"""
import math
from collections import defaultdict
from datetime import date

from app.config import get_settings

S2_COLLECTION = "COPERNICUS/S2_HARMONIZED"
CLOUD_SCORE_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S1_COLLECTION = "COPERNICUS/S1_GRD"
CLEAR_THRESHOLD = 0.60       # Cloud Score+ cs_cdf >= 0.60 counts as clear
MIN_CLEAR_FRACTION = 0.60    # keep a date only if >= 60% of the field is clear

_initialized = False


def init_ee():
    """Initialize Earth Engine once. Run `earthengine authenticate` beforehand."""
    global _initialized
    import ee

    if not _initialized:
        project = get_settings().gee_project
        if not project:
            raise RuntimeError("GEE_PROJECT is not set; see README 'Getting the free keys'.")
        ee.Initialize(project=project)
        _initialized = True
    return ee


def fetch_s2_ndvi(geometry: dict, start: date, end: date) -> list[dict]:
    """Per-image field-mean NDVI and clear fraction. Raw EE output, cached by the caller."""
    ee = init_ee()
    geom = ee.Geometry(geometry)
    cs = ee.ImageCollection(CLOUD_SCORE_COLLECTION)
    images = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(geom)
        .filterDate(start.isoformat(), end.isoformat())
        .linkCollection(cs, ["cs_cdf"])
    )

    def per_image(img):
        clear = img.select("cs_cdf").gte(CLEAR_THRESHOLD)
        ndvi = img.normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(clear)
        stats = ndvi.addBands(clear.rename("clear")).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=10, maxPixels=1e8
        )
        return ee.Feature(
            None,
            {
                "date": img.date().format("YYYY-MM-dd"),
                "ndvi": stats.get("ndvi"),
                "clear": stats.get("clear"),
            },
        )

    fc = ee.FeatureCollection(images.map(per_image))
    return [f["properties"] for f in fc.getInfo()["features"]]


def fetch_s1_sar(geometry: dict, start: date, end: date) -> list[dict]:
    """Per-image field-mean VV/VH in linear power plus orbit pass. Raw EE output."""
    ee = init_ee()
    geom = ee.Geometry(geometry)
    images = (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(geom)
        .filterDate(start.isoformat(), end.isoformat())
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )

    def per_image(img):
        linear = ee.Image(10).pow(img.select(["VV", "VH"]).divide(10))
        stats = linear.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=10, maxPixels=1e8
        )
        return ee.Feature(
            None,
            {
                "date": img.date().format("YYYY-MM-dd"),
                "vv_lin": stats.get("VV"),
                "vh_lin": stats.get("VH"),
                "pass": img.get("orbitProperties_pass"),
            },
        )

    fc = ee.FeatureCollection(images.map(per_image))
    return [f["properties"] for f in fc.getInfo()["features"]]


def parse_s2(raw: list[dict]) -> list[dict]:
    """Merge same-day tiles (clear-weighted), and drop mostly cloudy dates."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in raw:
        by_day[r["date"]].append(r)

    rows = []
    for day, items in sorted(by_day.items()):
        clear = max((i.get("clear") or 0.0) for i in items)
        valid = [i for i in items if i.get("ndvi") is not None and (i.get("clear") or 0) > 0]
        ndvi = None
        if valid and clear >= MIN_CLEAR_FRACTION:
            w = sum(i["clear"] for i in valid)
            ndvi = round(sum(i["ndvi"] * i["clear"] for i in valid) / w, 4)
        rows.append(
            {
                "date": date.fromisoformat(day),
                "ndvi": ndvi,
                "cloud_pct": round(100 * (1 - clear), 1),
            }
        )
    return rows


def to_db(linear: float | None) -> float | None:
    if linear is None or linear <= 0:
        return None
    return round(10 * math.log10(linear), 3)


def parse_s1(raw: list[dict]) -> list[dict]:
    """Keep the orbit direction with the most acquisitions (backscatter differs
    between ascending and descending geometry), merge same-day frames, convert to dB."""
    valid = [r for r in raw if r.get("vv_lin") and r.get("vh_lin")]
    if not valid:
        return []
    passes = defaultdict(int)
    for r in valid:
        passes[r.get("pass")] += 1
    main_pass = max(passes, key=passes.get)

    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        if r.get("pass") == main_pass:
            by_day[r["date"]].append(r)

    rows = []
    for day, items in sorted(by_day.items()):
        vv = sum(i["vv_lin"] for i in items) / len(items)
        vh = sum(i["vh_lin"] for i in items) / len(items)
        rows.append({"date": date.fromisoformat(day), "sar_vv": to_db(vv), "sar_vh": to_db(vh)})
    return rows
