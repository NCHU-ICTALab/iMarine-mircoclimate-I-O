import pandas as pd

from kaohsiung_microclimate_lstm.src.data.port_local_training_dataset import build_port_local_training_dataset


def _config():
    return {
        "forecast": {"anchors": {"H1": 30, "H2": 60, "H3": 90, "H4": 120}},
        "port_local_training": {"label_alignment": {"tolerance_minutes": 30}},
        "port_local_model": {"train_rain_probability_if_labels_available": True},
    }


def _frames(periods=20):
    times = pd.date_range("2026-07-01 00:00:00+08:00", periods=periods, freq="30min")
    return {
        "KHWD01": pd.DataFrame(
            {
                "obs_time": times,
                "wind_speed": range(periods),
                "wind_gust": [value + 2 for value in range(periods)],
                "wind_direction": 180,
                "wind_gust_direction": 200,
            }
        ),
        "KHWD04": pd.DataFrame(
            {
                "obs_time": times,
                "wind_speed": [value + 1 for value in range(periods)],
                "wind_gust": [value + 3 for value in range(periods)],
                "wind_direction": 190,
                "wind_gust_direction": 210,
            }
        ),
    }


def test_build_port_local_training_dataset_features_and_labels():
    result = build_port_local_training_dataset(_frames(), {}, _config())
    dataset = result["dataset"]

    assert "khwd_wind_speed_mean" in result["feature_columns"]
    assert "khwd_wind_direction_sin_mean" in result["feature_columns"]
    assert "khwd_wind_gust_max_roll3" in result["feature_columns"]
    assert "target_wind_speed_H1" in result["label_columns"]
    assert "target_wind_gust_H4" in result["label_columns"]
    assert dataset["target_wind_speed_H1"].notna().sum() > 0
    assert result["dataset_report"]["label_alignment_method"] == "nearest_with_tolerance"
