from kaohsiung_microclimate_lstm.src.risk.level_mapping import (
    map_rain_amount_to_level,
    map_rain_probability_to_level,
    map_wind_gust_to_level,
    map_wind_gust_to_operation_level,
    map_wind_speed_to_level,
)


CONFIG = {
    "wind_gust": {"uncertainty_buffer_mps": 1.2},
    "dispatch_thresholds": {
        "rain_probability": {"watch": 0.30, "warning": 0.50, "high_risk": 0.70},
        "wind_speed_mps": {"watch": 8.0, "warning": 10.8, "high_risk": 13.9, "stop": 17.2},
        "wind_gust_mps": {"watch": 10.8, "warning": 13.9, "high_risk": 17.2, "stop": 30.0},
    },
    "rain_amount_thresholds_mm": {"light": 1.0, "heavy_1hr": 40.0, "torrential_3hr": 100.0, "severe_torrential_3hr": 200.0},
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


def test_gust_20_9_no_longer_stop():
    detail = map_wind_gust_to_operation_level(20.9, CONFIG, use_buffer=False)

    assert detail["operation_level"] != "stop"
    assert map_wind_gust_to_level(30.0, CONFIG, use_buffer=False) == "stop"


def test_rain_amount_thresholds():
    assert map_rain_amount_to_level(0.5, 1, CONFIG) == "normal"
    assert map_rain_amount_to_level(1.0, 1, CONFIG) == "watch"
    assert map_rain_amount_to_level(40.0, 1, CONFIG) == "warning"
    assert map_rain_amount_to_level(100.0, 3, CONFIG) == "high_risk"
    assert map_rain_amount_to_level(200.0, 3, CONFIG) == "stop"
    assert map_rain_amount_to_level(200.0, 24, CONFIG) == "not_applicable"
