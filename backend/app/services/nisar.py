"""NISAR radar (NASA-ISRO SAR) field averages from Level-2 GCOV products.

GCOV = Geocoded Polarimetric Covariance: backscatter (gamma-naught, linear
power) on a UTM grid, HDF5 format. Both bands share the layout
    /science/{LSAR|SSAR}/GCOV/grids/frequencyA/{HHHH,HVHV,xCoordinates,yCoordinates,projection}

Where the data comes from (both free):
  * L-band: NASA ASF DAAC (Earthdata Cloud). Found through NASA's CMR search,
    read with HTTP range requests, so only the pixels over the field are
    downloaded, not the multi-GB granule. Needs EARTHDATA_TOKEN.
  * S-band: ISRO Bhoonidhi (open data, from July 2026 operational). Download
    GCOV files through Bhoonidhi "Browse & Order" into data/nisar_s/ and
    ingest them with `read_gcov_file()`.

NISAR began science operations in 2025, so it only covers recent seasons;
Sentinel-1 provides radar for 2017 onward.
"""
import math
from datetime import date, datetime
from pathlib import Path

import httpx
import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
# ASF collection short names, best quality first. Check Earthdata Search if
# ASF renames them; the first one with results is used.
L_BAND_SHORT_NAMES = ["NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_PROVISIONAL_V1", "NISAR_L2_GCOV_BETA_V1"]
MIN_PIXELS = 3


# ---------------------------------------------------------------- search (L-band)

def search_l_band(client: httpx.Client, geometry: dict, start: date, end: date) -> list[dict]:
    """CMR granule search; returns [{"id", "date", "url"}] for GCOV HDF5 files over the field."""
    minx, miny, maxx, maxy = shape(geometry).bounds
    for short_name in L_BAND_SHORT_NAMES:
        resp = client.get(
            CMR_GRANULES_URL,
            params={
                "short_name": short_name,
                "bounding_box": f"{minx},{miny},{maxx},{maxy}",
                "temporal": f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z",
                "page_size": 200,
            },
            timeout=60,
        )
        resp.raise_for_status()
        granules = parse_cmr(resp.json())
        if granules:
            return granules
    return []


def parse_cmr(payload: dict) -> list[dict]:
    out = []
    for entry in payload.get("feed", {}).get("entry", []):
        url = next(
            (
                link["href"]
                for link in entry.get("links", [])
                if link.get("href", "").startswith("https") and link["href"].endswith(".h5")
            ),
            None,
        )
        if url:
            out.append({"id": entry.get("title") or entry.get("id"), "date": entry["time_start"][:10], "url": url})
    return out


def resolve_signed_url(client: httpx.Client, url: str, token: str) -> str:
    """ASF answers an authenticated request with a redirect to a short-lived signed
    S3 URL; reading that URL directly lets range requests skip re-authentication."""
    resp = client.get(url, headers={"Authorization": f"Bearer {token}", "Range": "bytes=0-0"},
                      follow_redirects=False, timeout=60)
    if resp.status_code in (301, 302, 303, 307, 308):
        return resp.headers["location"]
    resp.raise_for_status()
    return url


# ---------------------------------------------------------------- reading GCOV

def _band_group(h5) -> tuple[str, str]:
    for band in ("LSAR", "SSAR"):
        path = f"/science/{band}/GCOV/grids/frequencyA"
        if path in h5:
            return band, path
    raise ValueError("Not a NISAR GCOV file: no /science/{LSAR,SSAR}/GCOV/grids/frequencyA group")


def _epsg(group) -> int:
    proj = group["projection"]
    for attr in ("epsg_code", "epsg"):
        if attr in proj.attrs:
            return int(np.asarray(proj.attrs[attr]).item())
    return int(np.asarray(proj[()]).item())


def _acquisition_date(h5, band: str) -> date | None:
    path = f"/science/{band}/identification/zeroDopplerStartTime"
    if path in h5:
        raw = h5[path][()]
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        return datetime.fromisoformat(text[:19]).date()
    return None


def field_means(h5, geometries: dict[str, dict]) -> tuple[str, date | None, dict[str, dict]]:
    """Mean HH/HV backscatter (dB) inside each field polygon (WGS84 GeoJSON).

    Reads only the window of pixels covering each field. Returns
    (band 'L'|'S', acquisition date, {field_id: {"hh": dB, "hv": dB, "pixels": n}}).
    """
    band, gpath = _band_group(h5)
    group = h5[gpath]
    to_utm = Transformer.from_crs(4326, _epsg(group), always_xy=True).transform
    xs = group["xCoordinates"][()]
    ys = group["yCoordinates"][()]
    terms = {"hh": "HHHH", "hv": "HVHV"}

    results: dict[str, dict] = {}
    for field_id, geom in geometries.items():
        poly = shp_transform(to_utm, shape(geom))
        minx, miny, maxx, maxy = poly.bounds
        xi = np.where((xs >= minx) & (xs <= maxx))[0]
        yi = np.where((ys >= miny) & (ys <= maxy))[0]
        if xi.size == 0 or yi.size == 0:
            continue
        x0, x1, y0, y1 = xi.min(), xi.max() + 1, yi.min(), yi.max() + 1
        gx, gy = np.meshgrid(xs[x0:x1], ys[y0:y1])
        inside = contains_xy(poly, gx, gy)

        stats: dict = {}
        for key, term in terms.items():
            if term not in group:
                continue
            window = group[term][y0:y1, x0:x1].astype("float64")
            vals = window[inside & np.isfinite(window) & (window > 0)]
            if vals.size >= MIN_PIXELS:
                stats[key] = round(10 * math.log10(vals.mean()), 3)
                stats["pixels"] = int(vals.size)
        if stats:
            results[field_id] = stats
    return band[0], _acquisition_date(h5, band), results


def read_gcov_file(path: str | Path, geometries: dict[str, dict]):
    """Local GCOV file (e.g. S-band downloaded from Bhoonidhi)."""
    import h5py

    with h5py.File(path, "r") as h5:
        return field_means(h5, geometries)


def read_gcov_url(signed_url: str, geometries: dict[str, dict]):
    """Remote GCOV over HTTP range requests; downloads only the needed blocks."""
    import fsspec
    import h5py

    with fsspec.open(signed_url, "rb", block_size=4 * 1024 * 1024) as f, h5py.File(f, "r") as h5:
        return field_means(h5, geometries)


def to_rows(band: str, acq_date: date, stats: dict) -> dict:
    """field_timeseries columns for one field on one acquisition date."""
    prefix = "nisar_l" if band == "L" else "nisar_s"
    return {"date": acq_date, f"{prefix}_hh": stats.get("hh"), f"{prefix}_hv": stats.get("hv")}
