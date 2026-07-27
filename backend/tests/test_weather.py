from datetime import date

from app.weather import normalize_open_meteo, required_warmth, weather_suitability


def fixture():
    return {
        "daily": {
            "time": ["2026-07-27"],
            "temperature_2m_min": [18],
            "temperature_2m_max": [29],
            "apparent_temperature_min": [17],
            "apparent_temperature_max": [31],
            "precipitation_probability_max": [70],
            "precipitation_sum": [5.2],
            "weather_code": [61],
            "wind_speed_10m_max": [22],
        },
        "hourly": {
            "time": ["2026-07-27T08:00", "2026-07-27T12:00", "2026-07-27T18:00"],
            "apparent_temperature": [20, 28, 25],
            "relative_humidity_2m": [80, 60, 70],
        },
    }


def test_open_meteo_normalization_uses_active_hours():
    result = normalize_open_meteo(fixture())
    assert result[0].date == date(2026, 7, 27)
    assert result[0].planning_temp_c == 73 / 3
    assert result[0].humidity_percent == 70
    assert result[0].precipitation_probability == 70


def test_required_warmth_has_ordered_thresholds():
    assert required_warmth(-10) == 5
    assert required_warmth(10) == 3
    assert required_warmth(30) == 0


def test_weather_score_rewards_rain_capability():
    weather = normalize_open_meteo(fixture())[0]
    dry = {"warmth": 1, "breathability": 4, "water_resistance": 0}
    rain_ready = {**dry, "water_resistance": 4}
    assert weather_suitability(rain_ready, weather)[0] > weather_suitability(dry, weather)[0]
