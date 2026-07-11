import pandas as pd

from kaohsiung_microclimate_lstm.src.data.nearby_historical_training_dataset import build_nearby_historical_training_dataset, _dew_point_c


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


def test_nearby_historical_training_dataset_adds_upstream_lead_features(tmp_path):
    zoning = tmp_path / "zoning.yaml"
    zoning.write_text(
        """
season_month_ranges:
  summer: [7]
typhoon_season_months: []
upstream_downstream_pairs:
  - season: summer
    upstream_station_ids: [C0V490]
""".lstrip(),
        encoding="utf-8",
    )
    times = pd.date_range("2026-07-01 00:00", periods=6, freq="30min")
    frames = {
        "C0V490": pd.DataFrame({"obs_time": times, "wind_speed": [5, 6, 7, 8, 9, 10], "wind_gust": [8, 9, 10, 11, 12, 13], "precipitation_1hr": [1, 0, 2, 0, 3, 0]}),
        "C0V890": pd.DataFrame({"obs_time": times, "wind_speed": [20] * 6, "wind_gust": [30] * 6, "precipitation_1hr": [50] * 6}),
    }
    ranking = {
        "selected_station_ids": ["C0V490", "C0V890"],
        "ranked_stations": [
            {"station_id": "C0V490", "distance_to_port_km": 3.0},
            {"station_id": "C0V890", "distance_to_port_km": 2.0},
        ],
    }
    cfg = {
        "forecast": {"anchors": {"H1": 30}},
        "zoning_config_path": str(zoning),
        "nearby_cwa_historical_training": {"enable_upstream_lead_features": True},
    }

    result = build_nearby_historical_training_dataset(frames, ranking, cfg)

    assert "upstream_subset_wind_speed_max" in result["feature_columns"]
    assert "upstream_subset_wind_speed_max_lag1" in result["feature_columns"]
    assert "upstream_subset_precipitation_roll3" in result["feature_columns"]
    assert result["dataset"].loc[0, "upstream_subset_wind_speed_max"] == 5


def test_nearby_historical_training_dataset_upstream_lead_features_disabled_by_default(tmp_path):
    zoning = tmp_path / "zoning.yaml"
    zoning.write_text(
        """
season_month_ranges:
  summer: [7]
typhoon_season_months: []
upstream_downstream_pairs:
  - season: summer
    upstream_station_ids: [C0V490]
""".lstrip(),
        encoding="utf-8",
    )
    times = pd.date_range("2026-07-01 00:00", periods=6, freq="30min")
    frames = {
        "C0V490": pd.DataFrame({"obs_time": times, "wind_speed": [5, 6, 7, 8, 9, 10], "wind_gust": [8, 9, 10, 11, 12, 13], "precipitation_1hr": [1, 0, 2, 0, 3, 0]}),
        "C0V890": pd.DataFrame({"obs_time": times, "wind_speed": [20] * 6, "wind_gust": [30] * 6, "precipitation_1hr": [50] * 6}),
    }
    ranking = {
        "selected_station_ids": ["C0V490", "C0V890"],
        "ranked_stations": [
            {"station_id": "C0V490", "distance_to_port_km": 3.0},
            {"station_id": "C0V890", "distance_to_port_km": 2.0},
        ],
    }
    # No enable_upstream_lead_features key at all, mirroring the real config.yaml default.
    cfg = {"forecast": {"anchors": {"H1": 30}}, "zoning_config_path": str(zoning)}

    result = build_nearby_historical_training_dataset(frames, ranking, cfg)

    assert "upstream_subset_wind_speed_max" not in result["feature_columns"]
    assert "upstream_subset_wind_speed_max_lag1" not in result["feature_columns"]


def test_dew_point_c_matches_saturated_air_boundary():
    dew_point = _dew_point_c(pd.Series([25.0]), pd.Series([100.0]))

    assert abs(float(dew_point.iloc[0]) - 25.0) < 0.001


def test_nearby_historical_training_dataset_pressure_humidity_features_disabled_by_default():
    times = pd.date_range("2026-07-01 00:00", periods=6, freq="1h")
    frames = {
        "C0V890": pd.DataFrame(
            {
                "obs_time": times,
                "wind_speed": [1, 2, 3, 4, 5, 6],
                "wind_gust": [2, 3, 4, 5, 6, 7],
                "precipitation_1hr": [0, 1, 0, 1, 0, 1],
                "station_pressure": [1000, 1001, 1002, 1003, 1004, 1005],
                "relative_humidity": [80, 81, 82, 83, 84, 85],
                "temperature": [28, 28, 29, 29, 30, 30],
            }
        )
    }
    ranking = {"selected_station_ids": ["C0V890"], "ranked_stations": [{"station_id": "C0V890", "distance_to_port_km": 2.0}]}
    cfg = {"forecast": {"anchors": {"H1": 60}}}

    result = build_nearby_historical_training_dataset(frames, ranking, cfg)

    assert "nearby_cwa_pressure_mean" not in result["feature_columns"]
    assert "nearby_cwa_dew_point_spread_mean" not in result["feature_columns"]


def test_nearby_historical_training_dataset_adds_pressure_humidity_features_when_enabled():
    times = pd.date_range("2026-07-01 00:00", periods=6, freq="1h")
    frames = {
        "C0V890": pd.DataFrame(
            {
                "obs_time": times,
                "wind_speed": [1, 2, 3, 4, 5, 6],
                "wind_gust": [2, 3, 4, 5, 6, 7],
                "precipitation_1hr": [0, 1, 0, 1, 0, 1],
                "station_pressure": [1000, 1001, 1002, 1003, 1004, 1005],
                "relative_humidity": [80, 81, 82, 83, 84, 85],
                "temperature": [28, 28, 29, 29, 30, 30],
            }
        ),
        "C0V490": pd.DataFrame(
            {
                "obs_time": times,
                "wind_speed": [2, 3, 4, 5, 6, 7],
                "wind_gust": [3, 4, 5, 6, 7, 8],
                "precipitation_1hr": [0, 0, 1, 0, 1, 0],
                "station_pressure": [1002, 1002, 1004, 1004, 1006, 1006],
                "relative_humidity": [70, 71, 72, 73, 74, 75],
                "temperature": [27, 27, 28, 28, 29, 29],
            }
        ),
    }
    ranking = {
        "selected_station_ids": ["C0V890", "C0V490"],
        "ranked_stations": [
            {"station_id": "C0V890", "distance_to_port_km": 2.0},
            {"station_id": "C0V490", "distance_to_port_km": 3.0},
        ],
    }
    cfg = {
        "forecast": {"anchors": {"H1": 60}},
        "nearby_cwa_historical_training": {"enable_pressure_humidity_features": True},
    }

    result = build_nearby_historical_training_dataset(frames, ranking, cfg)

    assert "nearby_cwa_pressure_mean" in result["feature_columns"]
    assert "nearby_cwa_pressure_gradient" in result["feature_columns"]
    assert "nearby_cwa_pressure_mean_trend_3h" in result["feature_columns"]
    assert "nearby_cwa_relative_humidity_mean" in result["feature_columns"]
    assert "nearby_cwa_temperature_mean" in result["feature_columns"]
    assert "nearby_cwa_dew_point_spread_mean" in result["feature_columns"]
    assert result["dataset"].loc[0, "nearby_cwa_pressure_gradient"] == 2
    assert result["dataset"]["nearby_cwa_pressure_mean_trend_3h"].notna().sum() > 0
