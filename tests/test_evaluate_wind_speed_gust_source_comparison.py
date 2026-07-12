import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.evaluate_wind_speed_gust_source_comparison import evaluate_wind_speed_gust_source_comparison


def test_evaluate_wind_speed_gust_source_comparison_keeps_legacy_when_history_insufficient(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets:
  precipitation: {variables: [precipitation_1hr]}
  wind_speed_gust: {variables: [wind_speed, wind_gust]}
wind_speed_gust_prediction_source: legacy_lstm
wind_speed_gust_source_comparison: {min_required_khwd_rows: 10}
""",
        encoding="utf-8",
    )
    raw = tmp_path / "data" / "raw" / "observed_hourly"
    raw.mkdir(parents=True)
    pd.DataFrame(
        {
            "obs_time": ["2026-07-12T00:00:00+08:00"],
            "wind_speed": [18.0],
            "wind_gust": [20.0],
        }
    ).to_csv(raw / "KHWD01.csv", index=False)

    report = evaluate_wind_speed_gust_source_comparison(cfg, tmp_path)

    assert report["formal_comparison_ready"] is False
    assert report["recommended_default_source"] == "legacy_lstm"
    assert (tmp_path / "results" / "model_benchmark_v13" / "wind_speed_gust_source_comparison" / "comparison_report.json").exists()
