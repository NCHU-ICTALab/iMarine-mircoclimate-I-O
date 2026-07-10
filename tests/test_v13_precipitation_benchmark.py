from __future__ import annotations

import json

import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.run_precipitation_benchmark_v13 import run_precipitation_benchmark_v13


def test_precipitation_benchmark_uses_lag_features_and_writes_report(tmp_path):
    periods = 40
    frame = pd.DataFrame(
        {
            "obs_time": pd.date_range("2026-07-01", periods=periods, freq="h"),
            "nearby_cwa_station_count": 2,
            "nearby_cwa_precipitation_1hr_max": [0, 0, 1, 2] * 10,
            "nearby_cwa_precipitation_1hr_max_lag1": [0, 0, 0, 1] * 10,
            "nearby_cwa_precipitation_1hr_max_roll3": [0, 0, 0.3, 1.0] * 10,
            "nearby_cwa_precipitation_roll3": [0, 0, 0.3, 1.0] * 10,
            "nearby_cwa_precipitation_roll6": [0, 0, 0.2, 0.5] * 10,
            "nearby_cwa_wind_speed_max": range(periods),
            "nearby_cwa_wind_gust_max": range(periods),
            "hour_sin": 0.0,
            "hour_cos": 1.0,
            "target_rain_event_H1": [0, 0, 1, 1] * 10,
            "target_nearby_precipitation_1hr_H1": [0, 0, 1, 2] * 10,
        }
    )
    dataset_path = tmp_path / "rain.parquet"
    frame.to_parquet(dataset_path, index=False)

    report = run_precipitation_benchmark_v13(
        dataset_path=dataset_path,
        output_dir=tmp_path / "reports",
        config_path=None,
        algorithms=["random_forest"],
        horizons=["H1"],
    )

    saved = json.loads((tmp_path / "reports" / "precipitation_benchmark_v13.json").read_text(encoding="utf-8"))
    assert report["report_path"] == str(tmp_path / "reports" / "precipitation_benchmark_v13.json")
    assert "nearby_cwa_wind_speed_max" not in saved["feature_columns"]
    assert "nearby_cwa_wind_gust_max" not in saved["feature_columns"]
    assert "nearby_cwa_precipitation_1hr_max_lag1" in saved["feature_columns"]
    assert saved["horizons"]["H1"]["results"]["random_forest"]["actual_classifier"] == "RandomForestClassifier"
