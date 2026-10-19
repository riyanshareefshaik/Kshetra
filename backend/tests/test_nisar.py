from datetime import date

import h5py
import numpy as np
import pytest
from pyproj import Transformer

from app.services.nisar import field_means, parse_cmr, read_gcov_file, to_rows

EPSG = 32644  # UTM 44N covers the Krishna delta


def make_gcov(path, band="LSAR", hh=0.1, hv=0.01):
    """Small synthetic GCOV file with the documented NISAR layout."""
    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    cx, cy = to_utm(80.779, 16.4405)
    xs = cx + np.arange(-50, 50) * 20.0          # 20 m posting
    ys = cy + np.arange(50, -50, -1) * 20.0      # north-up
    with h5py.File(path, "w") as h5:
        g = h5.create_group(f"/science/{band}/GCOV/grids/frequencyA")
        g["xCoordinates"] = xs
        g["yCoordinates"] = ys
        proj = g.create_dataset("projection", data=EPSG)
        proj.attrs["epsg_code"] = EPSG
        g["HHHH"] = np.full((100, 100), hh, dtype="float32")
        hvarr = np.full((100, 100), hv, dtype="float32")
        hvarr[0, 0] = np.nan
        g["HVHV"] = hvarr
        h5[f"/science/{band}/identification/zeroDopplerStartTime"] = b"2026-07-15T00:41:12.000000"


FIELD = {"type": "Polygon", "coordinates": [[
    [80.7786, 16.4401], [80.7794, 16.4401], [80.7794, 16.4409], [80.7786, 16.4409], [80.7786, 16.4401]]]}
OUTSIDE = {"type": "Polygon", "coordinates": [[
    [81.5, 17.0], [81.501, 17.0], [81.501, 17.001], [81.5, 17.001], [81.5, 17.0]]]}


def test_field_means_from_gcov(tmp_path):
    path = tmp_path / "gcov.h5"
    make_gcov(path)
    band, acq, stats = read_gcov_file(path, {"f1": FIELD, "far": OUTSIDE})
    assert band == "L"
    assert acq == date(2026, 7, 15)
    assert stats["f1"]["hh"] == pytest.approx(-10.0, abs=1e-3)
    assert stats["f1"]["hv"] == pytest.approx(-20.0, abs=1e-3)
    assert stats["f1"]["pixels"] > 10
    assert "far" not in stats


def test_s_band_and_rows(tmp_path):
    path = tmp_path / "s.h5"
    make_gcov(path, band="SSAR", hh=0.05)
    with h5py.File(path) as h5:
        band, acq, stats = field_means(h5, {"f1": FIELD})
    assert band == "S"
    row = to_rows(band, acq, stats["f1"])
    assert set(row) == {"date", "nisar_s_hh", "nisar_s_hv"}
    assert row["nisar_s_hh"] == pytest.approx(-13.01, abs=0.01)


def test_parse_cmr_picks_h5_https_links():
    payload = {"feed": {"entry": [
        {"title": "NISAR_L2_GCOV_A", "time_start": "2026-08-01T00:00:00Z", "links": [
            {"href": "s3://bucket/a.h5"},
            {"href": "https://datapool.asf.alaska.edu/GCOV/NISAR/a.h5"},
            {"href": "https://datapool.asf.alaska.edu/GCOV/NISAR/a.png"}]},
        {"title": "no-data", "time_start": "2026-08-02T00:00:00Z", "links": []},
    ]}}
    assert parse_cmr(payload) == [
        {"id": "NISAR_L2_GCOV_A", "date": "2026-08-01", "url": "https://datapool.asf.alaska.edu/GCOV/NISAR/a.h5"}]
