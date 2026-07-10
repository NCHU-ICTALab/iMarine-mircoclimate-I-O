from __future__ import annotations

import json

import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.run_model_benchmark import run_model_benchmark


def test_v13_model_benchmark_runner_writes_report(tmp_path):
    dataset_path = tmp_path / "benchmark.csv"
    pd.DataFrame(
        {
            "feature_a": [1, 2, 3, 4, 5, 6, 7, 8],
            "feature_b": [8, 7, 6, 5, 4, 3, 2, 1],
            "obs_time": pd.date_range("2026-07-10", periods=8, freq="h").astype(str),
            "wind_speed": [2.0, 2.2, 2.5, 2.8, 3.0, 3.4, 3.8, 4.1],
        }
    ).to_csv(dataset_path, index=False)

    report = run_model_benchmark(
        dataset_path=dataset_path,
        target_column="wind_speed",
        output_dir=tmp_path / "reports",
        config_path=None,
        algorithms=["random_forest"],
        test_fraction=0.25,
    )

    report_path = tmp_path / "reports" / "benchmark_report.json"
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_path"] == str(report_path)
    assert saved["target_column"] == "wind_speed"
    assert saved["requested_algorithms"] == ["random_forest"]
    assert saved["results"]["random_forest"]["requested_algorithm"] == "random_forest"
    assert saved["results"]["random_forest"]["actual_estimator"] == "RandomForestRegressor"
