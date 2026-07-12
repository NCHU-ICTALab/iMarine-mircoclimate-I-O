import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.report_low_risk_cleanup import build_low_risk_cleanup_report


def test_low_risk_cleanup_report_flags_small_port_local_dataset(tmp_path):
    dataset = tmp_path / "data" / "processed" / "port_local_training_dataset.parquet"
    dataset.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "obs_time": pd.date_range("2026-07-01", periods=3),
            "target_wind_speed_H1": [1.0, None, None],
            "target_wind_speed_H2": [None, None, None],
        }
    ).to_parquet(dataset)

    report = build_low_risk_cleanup_report(tmp_path)

    item = report["items"]["port_local_training_dataset"]
    assert item["sample_count"] == 3
    assert item["label_valid_count"]["target_wind_speed_H2"] == 0
    assert item["warning"] == "dataset_present_but_not_training_ready"


def test_low_risk_cleanup_report_finds_nested_extra_historical_weather_stations(tmp_path):
    nested = tmp_path / "data" / "raw" / "historical_weather" / "C0V610"
    nested.mkdir(parents=True)
    (nested / "C0V610_20230101_20260708.csv").write_text("obs_time,wind_speed\n", encoding="utf-8")

    report = build_low_risk_cleanup_report(tmp_path)

    item = report["items"]["extra_historical_weather_stations"]
    assert item["extra_station_ids"] == ["C0V610"]
    assert item["warning"] == "extra_raw_stations_not_used_for_training"
