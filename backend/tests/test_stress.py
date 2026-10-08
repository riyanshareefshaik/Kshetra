import numpy as np

from app.dev.synthetic import field_frame
from app.ml.season_detection import detect_seasons
from app.ml.stress_detection import detect_stress


def kharif(df):
    return detect_seasons(df)[0]


def test_dry_spell_during_growth():
    df = field_frame()
    df.loc["2020-08-01":"2020-08-25", "rainfall_mm"] = 0.0
    events = detect_stress(df, kharif(df), "paddy")
    dry = [e for e in events if e["event_type"] == "dry_spell"]
    assert len(dry) == 1
    assert dry[0]["evidence"]["dry_days"] == 25
    assert 0 < dry[0]["severity"] <= 1


def test_flood_needs_heavy_rain_and_radar_water():
    df = field_frame()
    df.loc["2020-09-01":"2020-09-03", "rainfall_mm"] = 80.0
    s1_day = df.loc["2020-09-01":"2020-09-08", "sar_vv"].dropna().index[0]
    df.loc[s1_day, "sar_vv"] = -20.0
    events = detect_stress(df, kharif(df), "paddy")
    flood = [e for e in events if e["event_type"] == "flood"]
    assert flood and flood[0]["evidence"]["radar_standing_water"]


def test_early_paddy_flooding_is_not_stress():
    df = field_frame()
    events = detect_stress(df, kharif(df), "paddy")
    assert not [e for e in events if e["event_type"] in ("flood", "waterlogging")]


def test_sudden_damage_from_observed_ndvi_drop():
    df = field_frame()
    obs_days = df.loc["2020-08-20":"2020-09-10"].query("ndvi_source == 's2'").index
    df.loc[obs_days[2], "ndvi"] = df.loc[obs_days[1], "ndvi"] - 0.25
    events = detect_stress(df, kharif(df), "paddy")
    dmg = [e for e in events if e["event_type"] == "sudden_damage"]
    assert dmg and dmg[0]["evidence"]["days"] <= 12


def test_heat_around_flowering():
    df = field_frame()
    df.loc["2020-09-15":"2020-09-19", "temp_max_c"] = 40.0
    events = detect_stress(df, kharif(df), "paddy")
    heat = [e for e in events if e["event_type"] == "heat_stress"]
    assert heat and heat[0]["evidence"]["hot_days"] == 5


def test_normal_season_has_no_events():
    df = field_frame()
    df["temp_max_c"] = np.where(df.index.month.isin([4, 5]), 39.0, 33.0)   # summer heat outside seasons
    assert detect_stress(df, kharif(df), "paddy") == []


def test_normally_dry_rabi_is_not_a_dry_spell():
    df = field_frame()
    rabi = detect_seasons(df)[1]
    assert rabi.season == "rabi"
    assert [e for e in detect_stress(df, rabi, "pulses") if e["event_type"] == "dry_spell"] == []
