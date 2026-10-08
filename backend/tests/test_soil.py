import pytest

from app.services.soil import parse_soilgrids, usda_texture


def layer(name, v1, v2, v3):
    return {"name": name, "depths": [
        {"label": "0-5cm", "values": {"mean": v1}},
        {"label": "5-15cm", "values": {"mean": v2}},
        {"label": "15-30cm", "values": {"mean": v3}},
    ]}


def test_depth_weighted_means_and_unit_conversion():
    payload = {"properties": {"layers": [
        layer("clay", 400, 420, 440),   # g/kg
        layer("sand", 300, 290, 280),
        layer("silt", 300, 290, 280),
        layer("phh2o", 75, 78, 80),     # pH*10
        layer("nitrogen", 120, 100, 80),  # cg/kg
        layer("bdod", 140, 145, 150),   # cg/cm3
    ]}}
    out = parse_soilgrids(payload)
    # (400*5 + 420*10 + 440*15) / 30 / 10
    assert out["clay_pct"] == pytest.approx(42.67, abs=0.01)
    assert out["ph_h2o"] == pytest.approx(7.85, abs=0.01)
    assert out["nitrogen_g_per_kg"] == pytest.approx(0.93, abs=0.01)
    assert out["bulk_density"] == pytest.approx(1.47, abs=0.01)
    assert out["soil_texture"] == "clay"


def test_missing_values_give_none():
    payload = {"properties": {"layers": [layer("clay", None, None, None)]}}
    out = parse_soilgrids(payload)
    assert out["clay_pct"] is None
    assert out["soil_texture"] is None


@pytest.mark.parametrize("sand,silt,clay,expected", [
    (90, 5, 5, "sand"),
    (40, 40, 20, "loam"),
    (20, 65, 15, "silt loam"),
    (65, 20, 15, "sandy loam"),
    (30, 35, 35, "clay loam"),
    (10, 55, 35, "silty clay loam"),
    (20, 25, 55, "clay"),
    (55, 15, 30, "sandy clay loam"),
])
def test_usda_texture(sand, silt, clay, expected):
    assert usda_texture(sand, silt, clay) == expected
