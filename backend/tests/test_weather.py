from datetime import date

from app.services.weather import parse_nasa_power, parse_open_meteo


def test_open_meteo_daily_with_soil_moisture_averaged():
    payload = {
        "daily": {
            "time": ["2024-07-01", "2024-07-02"],
            "precipitation_sum": [12.5, 0.0],
            "temperature_2m_max": [33.1, 34.0],
            "temperature_2m_min": [25.2, 26.0],
            "temperature_2m_mean": [28.9, 29.5],
            "et0_fao_evapotranspiration": [3.9, 5.1],
        },
        "hourly": {
            "time": ["2024-07-01T00:00", "2024-07-01T01:00", "2024-07-02T00:00"],
            "soil_moisture_0_to_7cm": [0.30, 0.32, None],
        },
    }
    rows = parse_open_meteo(payload)
    assert rows[0] == {
        "date": date(2024, 7, 1), "rainfall_mm": 12.5, "temp_max_c": 33.1, "temp_min_c": 25.2,
        "temp_mean_c": 28.9, "et0_mm": 3.9, "soil_moisture": 0.31,
    }
    assert rows[1]["soil_moisture"] is None


def test_nasa_power_missing_values_become_none():
    payload = {"properties": {"parameter": {
        "PRECTOTCORR": {"20240701": 4.2, "20240702": -999.0},
        "T2M_MAX": {"20240701": 33.0, "20240702": 34.0},
        "T2M_MIN": {"20240701": 25.0, "20240702": 26.0},
        "T2M": {"20240701": 29.0, "20240702": 30.0},
    }}}
    rows = parse_nasa_power(payload)
    assert [r["date"] for r in rows] == [date(2024, 7, 1), date(2024, 7, 2)]
    assert rows[0]["rainfall_mm"] == 4.2
    assert rows[1]["rainfall_mm"] is None
