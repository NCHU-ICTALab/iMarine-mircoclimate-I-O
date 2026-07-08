from kaohsiung_microclimate_lstm.src.risk.level_mapping import (
    map_rain_probability_to_level,
    map_wind_gust_to_level,
    map_wind_speed_to_level,
)


CONFIG = {
    "wind_gust": {"uncertainty_buffer_mps": 1.2},
    "dispatch_thresholds": {
        "rain_probability": {"watch": 0.30, "warning": 0.50, "high_risk": 0.70},
        "wind_speed_mps": {"watch": 8.0, "warning": 10.8, "high_risk": 13.9, "stop": 17.2},
        "wind_gust_mps": {"watch": 10.8, "warning": 13.9, "high_risk": 17.2, "stop": 20.8},
    },
}


def test_rain_probability_thresholds():
    assert map_rain_probability_to_level(0.29, CONFIG) == "normal"
    assert map_rain_probability_to_level(0.30, CONFIG) == "watch"
    assert map_rain_probability_to_level(0.50, CONFIG) == "warning"
    assert map_rain_probability_to_level(0.70, CONFIG) == "high_risk"


def test_wind_speed_thresholds():
    assert map_wind_speed_to_level(7.9, CONFIG) == "normal"
    assert map_wind_speed_to_level(8.0, CONFIG) == "watch"
    assert map_wind_speed_to_level(10.8, CONFIG) == "warning"
    assert map_wind_speed_to_level(13.9, CONFIG) == "high_risk"
    assert map_wind_speed_to_level(17.2, CONFIG) == "stop"


def test_gust_buffer_is_conservative():
    assert map_wind_gust_to_level(9.7, CONFIG, use_buffer=False) == "normal"
    assert map_wind_gust_to_level(9.7, CONFIG, use_buffer=True) == "watch"
