from datetime import date

from app.ml.season_detection import detect_seasons, season_name
from tests.synth import field_frame


def test_detects_kharif_and_rabi_each_year():
    seasons = detect_seasons(field_frame())
    got = [(s.year, s.season) for s in seasons]
    assert got == [(2020, "kharif"), (2020, "rabi"), (2021, "kharif"), (2021, "rabi"),
                   (2022, "kharif"), (2022, "rabi")]


def test_paddy_sowing_from_radar_flooding():
    k = detect_seasons(field_frame())[0]
    assert k.date_detection == "sar"
    assert date(2020, 7, 1) <= k.sowing_date <= date(2020, 7, 12)
    assert abs((k.peak_date - date(2020, 9, 20)).days) <= 3
    assert date(2020, 10, 25) <= k.harvest_date <= date(2020, 11, 20)
    assert k.flood_signal_db >= 3
    assert 0.75 <= k.peak_ndvi <= 0.82


def test_pulses_sowing_from_greenup():
    r = detect_seasons(field_frame())[1]
    assert r.date_detection == "ndvi"
    assert date(2020, 11, 20) <= r.sowing_date <= date(2020, 12, 10)
    assert r.harvest_date > r.peak_date > r.sowing_date


def test_in_progress_season_has_no_harvest():
    seasons = detect_seasons(field_frame(years=(2020, 2021), end=date(2021, 9, 25)))
    last = seasons[-1]
    assert (last.year, last.season) == (2021, "kharif")
    assert last.in_progress and last.harvest_date is None


def test_season_names():
    assert season_name(date(2023, 7, 1)) == ("kharif", 2023)
    assert season_name(date(2023, 11, 1)) == ("rabi", 2023)
    assert season_name(date(2024, 1, 10)) == ("rabi", 2023)
    assert season_name(date(2024, 3, 1)) == ("zaid", 2024)


def test_too_little_data():
    assert detect_seasons(field_frame().iloc[:30]) == []
