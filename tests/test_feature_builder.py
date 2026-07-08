import pandas as pd

from kaohsiung_microclimate_lstm.src.data.feature_builder import build_multistation_features


def test_feature_builder_excludes_forbidden_and_aggregates_nearby():
    cfg = {
        "features": {
            "target_station": ["wind_speed", "cwa_pop"],
            "forbidden_if_not_historical": ["cwa_pop"],
            "nearby_station_aggregation": {
                "enabled": True,
                "variables": ["wind_speed", "precipitation_1hr"],
            },
        }
    }
    target = pd.DataFrame({"wind_speed": [3.0], "cwa_pop": [0.9]})
    nearby = pd.DataFrame({"wind_speed": [2.0, 4.0], "precipitation_1hr": [0.0, 1.0]})
    features = build_multistation_features(target, nearby, cfg)
    assert features["wind_speed"] == 3.0
    assert "cwa_pop" not in features
    assert features["nearby_wind_speed_mean"] == 3.0
    assert features["nearby_precipitation_1hr_max"] == 1.0
    assert features["nearby_active_station_count"] == 2
    assert features["nearby_rain_station_count"] == 1
