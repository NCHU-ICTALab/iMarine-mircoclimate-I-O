import pandas as pd

from kaohsiung_microclimate_lstm.src.data.nearby_aggregation import build_nearby_aggregated_features


def test_nearby_aggregation_builds_latest_station_features():
    frames = {
        "467441": pd.DataFrame(
            {
                "obs_time": ["2026-07-08T00:00:00+08:00"],
                "wind_speed": [3.0],
                "wind_gust": [5.0],
                "precipitation_1hr": [0.0],
            }
        ),
        "C4Q01": pd.DataFrame(
            {
                "obs_time": ["2026-07-08T00:00:00+08:00"],
                "wind_speed": [2.0],
                "wind_gust": [8.0],
                "precipitation_1hr": [1.0],
            }
        ),
        "C4Q02": pd.DataFrame(
            {
                "obs_time": ["2026-07-08T00:00:00+08:00"],
                "wind_speed": [4.0],
                "wind_gust": [6.0],
                "precipitation_1hr": [0.0],
            }
        ),
    }

    result = build_nearby_aggregated_features(frames, "467441", {})
    features = result["features"].iloc[0]

    assert result["nearby_station_ids_used"] == ["C4Q01", "C4Q02"]
    assert features["nearby_wind_speed_mean"] == 3.0
    assert features["nearby_wind_speed_max"] == 4.0
    assert features["target_wind_speed_minus_nearby_mean"] == 0.0
    assert features["nearby_wind_gust_max"] == 8.0
    assert features["nearby_precipitation_1hr_sum"] == 1.0
    assert features["nearby_rainy_station_count"] == 1
    assert features["nearby_rainy_station_ratio"] == 0.5
