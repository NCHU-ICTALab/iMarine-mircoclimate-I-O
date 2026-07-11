import json

import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.evaluate_upstream_lead_features import evaluate_upstream_lead_features


def test_evaluate_upstream_lead_features_writes_skip_report_when_columns_missing(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets: {}
""".lstrip(),
        encoding="utf-8",
    )
    dataset = tmp_path / "dataset.pkl"
    pd.DataFrame({"obs_time": pd.date_range("2026-07-01", periods=4), "nearby_cwa_wind_speed_max": [1, 2, 3, 4]}).to_pickle(dataset)

    report = evaluate_upstream_lead_features(config, dataset, tmp_path / "reports", project_root=tmp_path)

    assert report["evaluated"] is False
    assert report["reason"] == "dataset_has_no_upstream_subset_columns"
    saved = json.loads((tmp_path / "reports" / "comparison_report.json").read_text(encoding="utf-8"))
    assert saved["evaluated"] is False
