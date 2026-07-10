import pandas as pd

from kaohsiung_microclimate_lstm.src.data.nearby_historical_training_dataset import build_nearby_historical_training_dataset


def test_nearby_historical_training_dataset_builds_features_and_labels():
    times = pd.date_range("2026-07-01 00:00", periods=12, freq="30min")
    frames = {
        "C0V890": pd.DataFrame({"obs_time": times, "wind_speed": range(12), "wind_gust": range(2, 14), "wind_direction": 180, "wind_gust_direction": 200, "precipitation_1hr": [0, 1] * 6}),
        "C0V490": pd.DataFrame({"obs_time": times, "wind_speed": range(1, 13), "wind_gust": range(3, 15), "wind_direction": 190, "wind_gust_direction": 210, "precipitation_1hr": [0, 0] * 6}),
    }
    ranking = {
        "selected_station_ids": ["C0V890", "C0V490"],
        "ranked_stations": [
            {"station_id": "C0V890", "distance_to_port_km": 2.0},
            {"station_id": "C0V490", "distance_to_port_km": 3.0},
        ],
    }
    cfg = {"forecast": {"anchors": {"H1": 30, "H2": 60, "H3": 90, "H4": 120}}}

    result = build_nearby_historical_training_dataset(frames, ranking, cfg)

    assert "nearby_cwa_wind_speed_max" in result["feature_columns"]
    assert "distance_weighted_precipitation" in result["feature_columns"]
    assert "target_nearby_wind_speed_H1" in result["label_columns"]
    assert "target_nearby_precipitation_1hr_H1" in result["label_columns"]
    assert "target_nearby_precipitation_amount_H1" in result["label_columns"]
    assert "target_rain_event_H4" in result["label_columns"]
    assert result["dataset"]["target_nearby_wind_gust_H1"].notna().sum() > 0
