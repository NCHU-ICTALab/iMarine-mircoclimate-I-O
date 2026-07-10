import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.train_surge_residual_model import train_surge_residual_model


def test_train_surge_residual_model_writes_artifact_and_report(tmp_path):
    observed = tmp_path / "observed"
    observed.mkdir()
    times = pd.date_range("2026-06-01", periods=80, freq="1h", tz="Asia/Taipei")
    tide = 100 + 20 * np.sin(np.arange(80) / 6.0) + np.linspace(0, 3, 80)
    pd.DataFrame({"obs_time": times, "tide_level": tide}).to_csv(observed / "C4P01.csv", index=False)
    for station_id, offset in [("C4Q01", 0.0), ("COMC08", 1.0)]:
        pd.DataFrame(
            {
                "obs_time": times,
                "air_pressure": 1010 + offset + np.sin(np.arange(80) / 8.0),
                "wind_speed": 5 + offset,
                "wind_gust": 7 + offset,
                "wind_direction": 180,
                "wave_height": 0.5 + offset * 0.1,
                "wave_period": 6 + offset,
            }
        ).to_csv(observed / f"{station_id}.csv", index=False)

    report = train_surge_residual_model(
        observed_dir=observed,
        output_dir=tmp_path / "models",
        report_dir=tmp_path / "reports",
        project_root=tmp_path,
        target_stations=["C4P01"],
        feature_stations=["C4Q01", "COMC08"],
        min_rows=40,
    )

    assert report["trained"] is True
    assert "C4P01" in report["trained_models"]
    assert (tmp_path / "models" / "C4P01_surge_residual.joblib").exists()
    assert (tmp_path / "reports" / "surge_residual_training_report.json").exists()
